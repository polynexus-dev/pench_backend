from rest_framework import generics, permissions, status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils import timezone
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db.models import Q
from .models import User, OTP, PasswordChangeLog
from .serializers import (
    UserSerializer,
    UserCreateSerializer,
    RequestOTPSerializer,
    LoginOTPSerializer,
    MyTokenObtainPairSerializer,
    SetPasswordSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    PermissionSerializer,
    GroupSerializer,
)
from .utils import generate_otp
from core.permissions import IsERPUser


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_scope = "login"


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple user accounts in one request.

        Each row is validated and created independently, so a duplicate
        username/email or a bad row doesn't block the rest of the batch
        from being created. Rows that fail validation (e.g. already exist)
        are reported back in "skipped" instead of failing the whole request.
        """
        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)

        created = []
        skipped = []
        for index, item in enumerate(request.data):
            serializer = self.get_serializer(data=item)
            if serializer.is_valid():
                self.perform_create(serializer)
                created.append(serializer.data)
            else:
                skipped.append({"index": index, "errors": serializer.errors})

        return Response(
            {
                "created": created,
                "skipped": skipped,
                "created_count": len(created),
                "skipped_count": len(skipped),
            },
            status=status.HTTP_201_CREATED,
        )


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class RequestOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "otp_request"

    def post(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        raw_phone = phone
        last_10 = phone[-10:] if len(phone) >= 10 else phone

        # 1. Check if User already exists in Public Schema
        user = User.objects.filter(Q(phone=phone) | Q(username=phone)).first()

        # 2. If not found, search across ALL tenant schemas
        if not user:
            from crm.models import Customer
            from tenants.models import City
            from django_tenants.utils import schema_context

            # Iterate through all cities to find this customer
            for city in City.objects.exclude(schema_name="public"):
                with schema_context(city.schema_name):
                    customer = Customer.objects.filter(phone=raw_phone).first()
                    if not customer:
                        customer = Customer.objects.filter(phone__endswith=last_10).first()
                        
                    if customer:
                        # Found them! Create the public User account
                        username = phone  # Use phone as username for easy login
                        from django.db import IntegrityError
                        try:
                            user = User.objects.create(
                                username=username,
                                phone=customer.phone or raw_phone, # Prefer stored phone
                                is_customer=True,
                                tenant_schema=city.schema_name,
                                first_name=customer.name,
                            )
                        except IntegrityError:
                            # Handle race conditions or duplicate key collisions gracefully by retrieving the existing user
                            user = User.objects.filter(Q(phone=phone) | Q(username=phone)).first()
                            if not user:
                                return Response(
                                    {"error": "A user with this username or phone number already exists."},
                                    status=status.HTTP_400_BAD_REQUEST,
                                )
                        # Link the customer in the tenant schema to the new public user
                        from django.db import connection
                        connection.set_schema(city.schema_name)
                        customer.user = user
                        customer.save()
                        print(
                            f"Global Search: Found {customer.name} in {city.name}. Linked to new User {username}"
                        )
                        break  # Stop searching other cities

            if not user:
                return Response(
                    {"error": "No customer found with this phone number in any city."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # 3. Generate and "send" OTP
        try:
            # Generate OTP using the actual phone number string stored/provided
            otp_phone = user.phone if user.phone else raw_phone
            otp_obj = generate_otp(otp_phone)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        response_data = {"message": "OTP sent successfully."}

        response_data["otp"] = otp_obj.code

        return Response(response_data)


class LoginOTPView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        code = serializer.validated_data["code"]
        raw_phone = phone
        last_10 = phone[-10:] if len(phone) >= 10 else phone

        # Validate OTP
        otp = OTP.objects.filter(
            phone=phone, code=code, is_used=False, expires_at__gt=timezone.now()
        ).first()

        if not otp:
            return Response(
                {"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST
            )

        # Mark as used
        otp.is_used = True
        otp.save()

        # Get User
        user = User.objects.filter(phone=phone).first()
        if not user:
            return Response(
                {"error": "User with this phone number does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Fallback: If user has no schema (created before the update), try to find it now
        if not user.tenant_schema:
            from tenants.models import City
            from crm.models import Customer
            from django_tenants.utils import schema_context

            for city in City.objects.exclude(schema_name="public"):
                with schema_context(city.schema_name):
                    customer = Customer.objects.filter(phone=user.phone).first()
                    if not customer:
                        customer = Customer.objects.filter(phone__endswith=last_10).first()
                    if customer:
                        user.tenant_schema = city.schema_name
                        user.save(update_fields=['tenant_schema'])
                        break

        # Generate JWT
        refresh = RefreshToken.for_user(user)

        response_data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": UserSerializer(user).data,
        }

        # Add tenant info if available
        if user.tenant_schema:
            from tenants.models import City, Domain

            city = City.objects.filter(schema_name=user.tenant_schema).first()
            if city:
                response_data["tenant_schema"] = city.schema_name
                response_data["tenant_name"] = city.name
                # Look up the domain (smart selection based on current request host)
                current_host = request.get_host().split(":")[0]
                base_domain = (
                    ".".join(current_host.split(".")[-2:])
                    if "nip.io" not in current_host
                    else ".".join(current_host.split(".")[-5:])
                )

                domain = Domain.objects.filter(
                    tenant=city, domain__icontains=base_domain
                ).first()
                if not domain:
                    domain = Domain.objects.filter(tenant=city).first()

                domain_val = (
                    domain.domain.replace("_", "-")
                    if domain and domain.domain
                    else f"{user.tenant_schema.replace('_', '-')}.{base_domain}"
                )
                response_data["tenant_domain"] = domain_val

                # Format full URL domain_name for consistency with password login
                scheme = "https" if request.is_secure() else "http"
                port = ""
                host_parts = request.get_host().split(":")
                if len(host_parts) > 1:
                    port = f":{host_parts[1]}"
                response_data["domain_name"] = f"{scheme}://{domain_val}{port}"

                # If driver, find their active route
                if user.is_driver:
                    from django_tenants.utils import schema_context

                    with schema_context(user.tenant_schema):
                        # 1. Search in the delivery routing system (used by the mobile app's stop schedule)
                        from orders.models import Route as OrdersRoute
                        from django.db.models import Q

                        route = (
                            OrdersRoute.objects.filter(
                                Q(driver=user) | Q(additional_drivers=user),
                                is_completed=False,
                            )
                            .distinct()
                            .order_by("delivery_date")
                            .first()
                        )

                        if route:
                            response_data["active_route_id"] = str(route.id)
                        else:
                            # 2. Fallback to the new routing system
                            from routing.models import Route as RoutingRoute, Driver

                            driver_profile = Driver.objects.filter(user=user).first()
                            if driver_profile:
                                r_route = (
                                    RoutingRoute.objects.filter(
                                        Q(driver=driver_profile)
                                        | Q(additional_drivers=driver_profile),
                                        status__in=["pending", "in_progress"],
                                    )
                                    .distinct()
                                    .first()
                                )
                                if r_route:
                                    response_data["active_route_id"] = str(r_route.id)

                # If customer, find their customer ID
                if user.is_customer:
                    from django_tenants.utils import schema_context
                    from crm.models import Customer

                    with schema_context(user.tenant_schema):
                        customer = Customer.objects.filter(user=user).first()
                        if customer:
                            response_data["customer_id"] = str(customer.id)

        return Response(response_data)


class SetPasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SetPasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data["password"])
        request.user.save()

        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = x_forwarded.split(",")[0].strip() if x_forwarded else request.META.get("REMOTE_ADDR")
        PasswordChangeLog.objects.create(
            user=request.user,
            changed_by=request.user,
            source="self_set_password",
            ip_address=ip,
        )

        return Response({
            "message": "Password set successfully.",
            "user": UserSerializer(request.user).data
        })


class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        raw_phone = phone
        last_10 = phone[-10:] if len(phone) >= 10 else phone

        # 1. Check if User already exists in Public Schema
        user = User.objects.filter(Q(phone=phone) | Q(username=phone)).first()

        # 2. If not found, search across ALL tenant schemas (same as RequestOTPView)
        if not user:
            from crm.models import Customer
            from tenants.models import City
            from django_tenants.utils import schema_context

            # Iterate through all cities to find this customer
            for city in City.objects.exclude(schema_name="public"):
                with schema_context(city.schema_name):
                    customer = Customer.objects.filter(phone=raw_phone).first()
                    if not customer:
                        customer = Customer.objects.filter(phone__endswith=last_10).first()
                        
                    if customer:
                        # Found them! Create the public User account
                        username = phone  # Use phone as username for easy login
                        from django.db import IntegrityError
                        try:
                            user = User.objects.create(
                                username=username,
                                phone=customer.phone or raw_phone,
                                is_customer=True,
                                tenant_schema=city.schema_name,
                                first_name=customer.name,
                            )
                        except IntegrityError:
                            # Handle race conditions or duplicate key collisions gracefully by retrieving the existing user
                            user = User.objects.filter(Q(phone=phone) | Q(username=phone)).first()
                            if not user:
                                return Response(
                                    {"error": "A user with this username or phone number already exists."},
                                    status=status.HTTP_400_BAD_REQUEST,
                                )
                        # Link the customer in the tenant schema to the new public user
                        from django.db import connection
                        connection.set_schema(city.schema_name)
                        customer.user = user
                        customer.save()
                        print(
                            f"Global Search: Found {customer.name} in {city.name}. Linked to new User {username}"
                        )
                        break  # Stop searching other cities

            if not user:
                return Response(
                    {"error": "No customer found with this phone number in any city."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # 3. Generate and return OTP
        try:
            otp_phone = user.phone if user.phone else raw_phone
            otp_obj = generate_otp(otp_phone)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        response_data = {
            "message": "OTP for password reset sent successfully.",
            "otp": otp_obj.code,
        }

        return Response(response_data)


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data["phone"]
        code = serializer.validated_data["code"]
        new_password = serializer.validated_data["new_password"]

        # 1. Validate OTP
        otp = OTP.objects.filter(
            phone=phone, code=code, is_used=False, expires_at__gt=timezone.now()
        ).first()

        if not otp:
            return Response(
                {"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Get User
        user = User.objects.filter(phone=phone).first()
        if not user:
            return Response(
                {"error": "User with this phone number does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 3. Mark OTP as used
        otp.is_used = True
        otp.save()

        # 4. Set new password
        user.set_password(new_password)
        user.save()

        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = x_forwarded.split(",")[0].strip() if x_forwarded else request.META.get("REMOTE_ADDR")
        PasswordChangeLog.objects.create(
            user=user,
            changed_by=user,
            source="otp_password_reset",
            ip_address=ip,
        )

        return Response({"message": "Password reset successfully."})


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsERPUser]
    filterset_fields = [
        "tenant_schema",
        "is_driver",
        "is_customer",
        "is_erp_user",
        "is_staff",
        "is_superuser",
    ]
    search_fields = ["username", "first_name", "last_name", "email", "phone"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        group_name = self.request.query_params.get("group")
        if group_name:
            queryset = queryset.filter(groups__name=group_name)
        return queryset

    @action(detail=True, methods=["post"], url_path="assign-permissions")
    def assign_permissions(self, request, pk=None):
        user = self.get_object()
        permission_ids = request.data.get("permission_ids", [])
        if not isinstance(permission_ids, list):
            return Response(
                {"error": "permission_ids must be a list of IDs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_permissions = Permission.objects.filter(id__in=permission_ids)
        if len(valid_permissions) != len(permission_ids):
            found_ids = list(valid_permissions.values_list("id", flat=True))
            missing_ids = list(set(permission_ids) - set(found_ids))
            return Response(
                {"error": f"Invalid permission IDs: {missing_ids}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.user_permissions.set(valid_permissions)
        return Response(
            {
                "message": f"Successfully assigned {len(valid_permissions)} permissions to user {user.username}.",
                "permissions": [
                    {"id": p.id, "codename": p.codename}
                    for p in user.user_permissions.all()
                ],
            }
        )

    @action(detail=True, methods=["post"], url_path="assign-groups")
    def assign_groups(self, request, pk=None):
        user = self.get_object()
        group_ids = request.data.get("group_ids", [])
        if not isinstance(group_ids, list):
            return Response(
                {"error": "group_ids must be a list of IDs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_groups = Group.objects.filter(id__in=group_ids)
        if len(valid_groups) != len(group_ids):
            found_ids = list(valid_groups.values_list("id", flat=True))
            missing_ids = list(set(group_ids) - set(found_ids))
            return Response(
                {"error": f"Invalid group IDs: {missing_ids}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.groups.set(valid_groups)
        return Response(
            {
                "message": f"Successfully assigned {len(valid_groups)} groups to user {user.username}.",
                "groups": [g.name for g in user.groups.all()],
            }
        )


class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all().order_by("id")
    serializer_class = PermissionSerializer
    permission_classes = [permissions.IsAuthenticated, IsERPUser]
    search_fields = ["name", "codename"]


class GroupViewSet(viewsets.ModelViewSet):
    queryset = Group.objects.all().order_by("id")
    serializer_class = GroupSerializer
    permission_classes = [permissions.IsAuthenticated, IsERPUser]
    search_fields = ["name"]

    @action(detail=True, methods=["post"], url_path="assign-permissions")
    def assign_permissions(self, request, pk=None):
        group = self.get_object()
        permission_ids = request.data.get("permission_ids", [])
        if not isinstance(permission_ids, list):
            return Response(
                {"error": "permission_ids must be a list of IDs."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_permissions = Permission.objects.filter(id__in=permission_ids)
        if len(valid_permissions) != len(permission_ids):
            found_ids = list(valid_permissions.values_list("id", flat=True))
            missing_ids = list(set(permission_ids) - set(found_ids))
            return Response(
                {"error": f"Invalid permission IDs: {missing_ids}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        group.permissions.set(valid_permissions)
        return Response(
            {
                "message": f"Successfully assigned {len(valid_permissions)} permissions to group {group.name}.",
                "permissions": [
                    {"id": p.id, "codename": p.codename}
                    for p in group.permissions.all()
                ],
            }
        )
