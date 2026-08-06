from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser
from core.permissions import IsDriverOrReadOnly, IsERPUser, HasGroupPermission
from .models import Route, Driver, TrackingEvent, DailyReconciliation, Zone
from .serializers import (
    RouteSerializer,
    DriverSerializer,
    TrackingEventSerializer,
    DailyReconciliationSerializer,
    ReconcileActionSerializer,
    ZoneSerializer,
)
from .tasks import optimize_route_task


class RouteViewSet(viewsets.ModelViewSet):
    serializer_class = RouteSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "delivery_date", "warehouse"]
    ordering_fields = ["created_at", "delivery_date"]

    def get_queryset(self):
        queryset = Route.objects.select_related("driver__user", "warehouse").prefetch_related(
            "orders__items__product__bottle_type",
            "additional_drivers__user"
        )
        driver_id = self.request.query_params.get("driver")
        if driver_id:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(driver_id=driver_id) | Q(additional_drivers__id=driver_id)
            ).distinct()

        date_val = self.request.query_params.get("delivery_date") or self.request.query_params.get("date")
        if date_val:
            queryset = queryset.filter(delivery_date=date_val)

        warehouse_id = self.request.query_params.get("warehouse")
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)

        return queryset

    def perform_create(self, serializer):
        """Auto-complete all previous incomplete routes for the driver when a new route is created."""
        from django.db.models import Q
        from django.utils import timezone

        route = serializer.save()
        driver = route.driver

        if driver:
            # Complete all previous incomplete routes for this driver
            previous_routes = (
                Route.objects.filter(
                    Q(driver=driver) | Q(additional_drivers=driver),
                    is_completed=False,
                )
                .exclude(id=route.id)
                .distinct()
            )
            for prev_route in previous_routes:
                prev_route.status = "completed"
                prev_route.is_completed = True
                prev_route.completed_at = timezone.now()
                prev_route.save(
                    update_fields=["status", "is_completed", "completed_at"]
                )

            # Reset driver profile
            driver.on_trip = False
            driver.is_available = True
            driver.save(update_fields=["on_trip", "is_available"])

    @action(detail=True, methods=["post"], url_path="optimize")
    def optimize(self, request, pk=None):
        route = self.get_object()
        if route.status in ("optimizing", "in_progress"):
            return Response(
                {"detail": "Route is already being processed."},
                status=status.HTTP_409_CONFLICT,
            )
        optimize_route_task.delay(str(route.id))
        return Response(
            {"detail": "Optimization started.", "route_id": str(route.id)},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="geojson")
    def geojson(self, request, pk=None):
        from .serializers import RouteGeoSerializer

        route = self.get_object()
        return Response(RouteGeoSerializer(route).data)

    @action(detail=True, methods=["get"], url_path="tracking")
    def tracking(self, request, pk=None):
        route = self.get_object()
        events = route.tracking_events.order_by("timestamp")
        serializer = TrackingEventSerializer(events, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="generate-reconciliation")
    def generate_reconciliation(self, request, pk=None):
        from .services.reconciliation_service import generate_daily_reconciliation

        recon = generate_daily_reconciliation(pk)
        return Response(DailyReconciliationSerializer(recon).data)


class DriverViewSet(viewsets.ModelViewSet):
    queryset = Driver.objects.select_related("user")
    serializer_class = DriverSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["is_available"]

    def list(self, request, *args, **kwargs):
        from django.db import connection

        print(f"[DEBUG] Listing Drivers for Schema: {connection.schema_name}")
        queryset = self.filter_queryset(self.get_queryset())
        print(f"[DEBUG] Found {queryset.count()} drivers in this schema.")
        return super().list(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = instance.user
        try:
            from django.db import transaction
            with transaction.atomic():
                instance.delete()
                if user:
                    user.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response(
                {"detail": f"Cannot delete driver: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )


    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple driver profiles in one request.
        """
        from django.db import connection

        print(f"[DEBUG] Creating Driver for Schema: {connection.schema_name}")
        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)

        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="reset-credentials")
    def reset_credentials(self, request, pk=None):
        """
        Allows Admin to update or reset a Rider's Username (User ID) and Password directly.
        """
        driver = self.get_object()
        user = driver.user
        if not user:
            return Response({"detail": "User account for this driver not found."}, status=status.HTTP_400_BAD_REQUEST)

        username = request.data.get("username", "").strip()
        password = request.data.get("password", "").strip()

        if not username and not password:
            return Response({"detail": "Provide at least a new username or password."}, status=status.HTTP_400_BAD_REQUEST)

        if username and username != user.username:
            from accounts.models import User
            if User.objects.filter(username=username).exclude(id=user.id).exists():
                return Response({"detail": f"Username '{username}' is already taken by another user."}, status=status.HTTP_400_BAD_REQUEST)
            user.username = username

        if password:
            if len(password) < 4:
                return Response({"detail": "Password must be at least 4 characters long."}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(password)

        user.save()
        return Response({
            "message": "Rider credentials updated successfully!",
            "username": user.username,
            "driver_id": driver.id,
            "full_name": user.get_full_name()
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="send-credentials")
    def send_credentials(self, request, pk=None):
        """
        Generates a brand-new random password for this rider, hashes and
        stores it, and emails the plaintext password to the configured
        admin recipients (never to the API response / frontend). This
        replaces showing/decrypting the rider's existing password, which
        is not possible for a one-way hash and was never a real feature.
        """
        import secrets
        import string
        from django.conf import settings
        from django.core.mail import send_mail

        driver = self.get_object()
        user = driver.user
        if not user:
            return Response({"detail": "User account for this driver not found."}, status=status.HTTP_400_BAD_REQUEST)

        recipients = getattr(settings, "RIDER_CREDENTIALS_RECIPIENTS", [])
        if not recipients:
            return Response({"detail": "No credential recipient email is configured on the server."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        alphabet = string.ascii_letters + string.digits
        new_password = "".join(secrets.choice(alphabet) for _ in range(12))

        subject = f"Rider Login Credentials - {user.get_full_name() or user.username}"
        message = (
            f"New login credentials have been generated for rider '{user.get_full_name() or user.username}'.\n\n"
            f"Username: {user.username}\n"
            f"Password: {new_password}\n\n"
            f"Please share these with the rider directly. This password will not be shown again in the admin panel."
        )

        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                recipients,
                fail_silently=False,
            )
        except Exception as e:
            return Response({"detail": f"Failed to send credentials email: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

        # Only persist the new password once the email has actually gone out,
        # so a failed send never leaves the rider unable to log in silently.
        user.set_password(new_password)
        user.save()

        return Response({
            "message": f"Credentials sent to {', '.join(recipients)}.",
            "username": user.username,
            "driver_id": driver.id,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="check-in")
    def check_in(self, request):
        from hr.models import Employee, Attendance
        from django.utils import timezone

        driver_profile = Driver.objects.filter(user=request.user).first()
        if not driver_profile:
            return Response({"detail": "Driver profile not found."}, status=404)

        employee = Employee.objects.filter(user=request.user).first()
        if not employee:
            # Fallback: create employee profile if missing
            from hr.models import Department

            dept, _ = Department.objects.get_or_create(name="Logistics")
            employee = Employee.objects.create(
                user=request.user,
                department=dept,
                job_title="Driver",
                employee_id=f"DRV-{request.user.id}",
                date_joined=timezone.now().date(),
            )

        attendance, created = Attendance.objects.get_or_create(
            employee=employee,
            date=timezone.now().date(),
            defaults={"is_driver_ready": True},
        )

        driver_profile.is_available = True
        driver_profile.save()

        return Response(
            {
                "detail": "Check-in successful.",
                "checked_in_at": attendance.check_in,
                "is_available": driver_profile.is_available,
            }
        )


class TrackingEventViewSet(viewsets.ModelViewSet):
    queryset = TrackingEvent.objects.select_related("route", "order")
    serializer_class = TrackingEventSerializer
    permission_classes = [IsDriverOrReadOnly]
    filterset_fields = ["route", "status"]
    ordering_fields = ["timestamp"]


class DailyReconciliationViewSet(viewsets.ModelViewSet):
    queryset = DailyReconciliation.objects.select_related(
        "driver__user", "route", "reconciled_by"
    )
    serializer_class = DailyReconciliationSerializer
    permission_classes = [IsERPUser]
    filterset_fields = ["driver", "status", "date"]

    @action(detail=True, methods=["post"], url_path="reconcile")
    def reconcile(self, request, pk=None):
        ser = ReconcileActionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from .services.reconciliation_service import reconcile

        recon = reconcile(
            reconciliation_id=pk,
            actual_total=ser.validated_data["actual_total"],
            user=request.user,
            notes=ser.validated_data.get("notes", ""),
        )
        return Response(DailyReconciliationSerializer(recon).data)


class ZoneViewSet(viewsets.ModelViewSet):
    serializer_class = ZoneSerializer
    permission_classes = [IsAuthenticated]
    # Default for HasGroupPermission; only actually enforced on actions whose
    # permission_classes include HasGroupPermission (see generate_from_excel below).
    required_groups = []
    filterset_fields = ["is_active", "assigned_driver"]

    def get_queryset(self):
        from django.db import connection
        if connection.schema_name == "public":
            return Zone.objects.none()
        return Zone.objects.select_related("assigned_driver")

    @action(
        detail=False,
        methods=["post"],
        url_path="generate-from-excel",
        permission_classes=[IsAuthenticated, HasGroupPermission],
        required_groups=["ERP_Admins"],
        parser_classes=[MultiPartParser],
    )
    def generate_from_excel(self, request):
        """
        Accepts an Excel file of customers + their assigned driver/rider, and
        regenerates one non-overlapping Voronoi zone per driver from their
        customers' locations. Safe to re-run: existing zones are updated in place.
        """
        import uuid
        from django.db import connection, transaction
        from crm.models import Customer, HAS_GIS as CRM_HAS_GIS, _parse_coordinates
        from .services.excel_import import parse_customer_excel
        from .services.zone_generation import generate_voronoi_zones

        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"detail": "No file uploaded. Send it as multipart form field 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            parsed = parse_customer_excel(upload)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        rows = parsed["rows"]
        skipped = list(parsed["skipped"])
        if not rows:
            return Response(
                {"detail": "No usable rows found in the sheet.", "skipped": skipped},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Resolve each row's driver identifier to a routing.Driver, by phone then name ---
        drivers = list(Driver.objects.select_related("user"))
        phone_to_driver = {}
        name_to_driver = {}
        for d in drivers:
            if d.user:
                if d.user.phone:
                    phone_to_driver[d.user.phone.strip()] = d
                full_name = (d.user.get_full_name() or "").strip().lower()
                if full_name:
                    name_to_driver.setdefault(full_name, d)

        def resolve_driver(row):
            if row["driver_phone"] and row["driver_phone"] in phone_to_driver:
                return phone_to_driver[row["driver_phone"]]
            if row["driver_name"]:
                return name_to_driver.get(row["driver_name"].strip().lower())
            return None

        resolved_rows = []  # (row, driver)
        for row in rows:
            driver = resolve_driver(row)
            if driver is None:
                identifier = row["driver_phone"] or row["driver_name"]
                skipped.append(
                    {
                        "row_num": row["row_num"],
                        "reason": f"No matching driver found for '{identifier}'.",
                    }
                )
                continue
            resolved_rows.append((row, driver))

        distinct_driver_ids = {driver.id for _, driver in resolved_rows}
        if len(distinct_driver_ids) < 2:
            return Response(
                {
                    "detail": (
                        "Need customers mapped to at least 2 different drivers to generate a "
                        "Voronoi partition. Only matched: "
                        f"{len(distinct_driver_ids)}."
                    ),
                    "skipped": skipped,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        Point = None
        if CRM_HAS_GIS:
            from django.contrib.gis.geos import Point

        try:
            with transaction.atomic():
                # --- Add new customers only; existing ones (matched by phone/email) are left untouched ---
                all_customers = list(Customer.objects.all())
                existing_by_phone = {c.phone: c for c in all_customers if c.phone}
                existing_by_email = {c.email.lower(): c for c in all_customers if c.email}

                created_count = 0
                skipped_existing_count = 0
                driver_points = {}
                driver_by_id = {}

                for row, driver in resolved_rows:
                    customer = None
                    if row["phone"] and row["phone"] in existing_by_phone:
                        customer = existing_by_phone[row["phone"]]
                    elif row["email"] and row["email"].lower() in existing_by_email:
                        customer = existing_by_email[row["email"].lower()]

                    if customer:
                        # Already exists — skip it entirely, use its own stored location (if any)
                        # for the Voronoi calculation instead of overwriting it with the row's.
                        skipped_existing_count += 1
                        point = _parse_coordinates(customer.location) or (row["lon"], row["lat"])
                    else:
                        location = (
                            Point(row["lon"], row["lat"])
                            if CRM_HAS_GIS
                            else {"lat": row["lat"], "lng": row["lon"]}
                        )
                        phone = row["phone"] or f"IMPORT-{uuid.uuid4().hex[:10]}"
                        email = row["email"] if row["email"] not in existing_by_email else None
                        customer = Customer.objects.create(
                            name=row["name"],
                            phone=phone,
                            email=email,
                            address=row["address"],
                            location=location,
                        )
                        existing_by_phone[customer.phone] = customer
                        if customer.email:
                            existing_by_email[customer.email.lower()] = customer
                        created_count += 1
                        point = (row["lon"], row["lat"])

                    driver_points.setdefault(driver.id, []).append(point)
                    driver_by_id[driver.id] = driver

                # --- Generate the Voronoi partition, clipped to the city boundary ---
                city = connection.tenant
                clip_boundary = getattr(city, "boundary", None)
                result = generate_voronoi_zones(
                    driver_points, clip_boundary=clip_boundary, has_gis=CRM_HAS_GIS
                )

                # --- Create/update one zone per driver ---
                zones_created = 0
                zones_updated = 0
                for driver_id, geometry in result["zones"].items():
                    driver = driver_by_id[driver_id]
                    user = driver.user
                    zone = Zone.objects.filter(assigned_driver=user).first()
                    is_new = zone is None
                    if is_new:
                        zone = Zone(
                            assigned_driver=user,
                            name=f"{user.get_full_name() or user.username}'s Zone",
                        )
                    zone.boundary = geometry
                    zone.is_active = True
                    zone.save()

                    if driver.zone_id != zone.id:
                        driver.zone = zone
                        driver.save(update_fields=["zone"])

                    if is_new:
                        zones_created += 1
                    else:
                        zones_updated += 1
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Zones generated successfully.",
                "customers_created": created_count,
                "customers_skipped_existing": skipped_existing_count,
                "zones_created": zones_created,
                "zones_updated": zones_updated,
                "drivers_matched": len(distinct_driver_ids),
                "warnings": result["warnings"],
                "skipped": skipped,
            },
            status=status.HTTP_200_OK,
        )
