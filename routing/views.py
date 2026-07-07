from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from core.permissions import IsDriverOrReadOnly, IsERPUser
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
    filterset_fields = ["status"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        queryset = Route.objects.select_related("driver__user").prefetch_related(
            "orders__items__product__bottle_type",
            "additional_drivers__user"
        )
        driver_id = self.request.query_params.get("driver")
        if driver_id:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(driver_id=driver_id) | Q(additional_drivers__id=driver_id)
            ).distinct()
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
    filterset_fields = ["is_active", "assigned_driver"]

    def get_queryset(self):
        from django.db import connection
        if connection.schema_name == "public":
            return Zone.objects.none()
        return Zone.objects.select_related("assigned_driver")
