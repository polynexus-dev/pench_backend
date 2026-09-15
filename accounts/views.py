import logging
from decimal import Decimal

from rest_framework import generics, permissions, status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from django.utils import timezone
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.db.models import Q
from .models import (
    User,
    OTP,
    PasswordChangeLog,
    LoginAuditLog,
    AccountDeletionLog,
)
from .serializers import (
    UserSerializer,
    UserCreateSerializer,
    RequestOTPSerializer,
    LoginOTPSerializer,
    MyTokenObtainPairSerializer,
    SetPasswordSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    DeleteAccountSerializer,
    PermissionSerializer,
    GroupSerializer,
)
from .utils import generate_otp
from core.permissions import IsERPUser

logger = logging.getLogger(__name__)


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer
    throttle_scope = "login"


class MyTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        try:
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            ip = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR")
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]

            is_success = status.is_success(response.status_code)
            status_str = "TOKEN_REFRESH_SUCCESS" if is_success else "TOKEN_REFRESH_FAILED"

            refresh_str = request.data.get("refresh") if isinstance(request.data, dict) else None
            user_inst = None
            username_val = "Unknown (Refresh)"

            if refresh_str:
                try:
                    token_obj = RefreshToken(refresh_str)
                    user_id = token_obj.payload.get("user_id")
                    if user_id:
                        user_inst = User.objects.filter(id=user_id).first()
                        if user_inst:
                            username_val = user_inst.username or user_inst.phone or f"User-{user_inst.id}"
                except Exception:
                    pass

            LoginAuditLog.objects.create(
                username_or_phone=username_val,
                user=user_inst,
                status=status_str,
                ip_address=ip,
                user_agent=user_agent,
            )
        except Exception:
            pass

        return response


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


class DeleteAccountView(APIView):
    """
    Permanently deletes the authenticated customer's account.

    This is a deletion, not a deactivation: the User row is destroyed, so the
    credentials stop resolving and any issued JWT becomes unusable immediately.

    What happens to tenant-side data, and why it is not a blanket delete:

    * ``crm.Customer`` is kept but scrubbed. ``orders.Order.customer`` and
      ``finance.MonthlyBill.customer`` are both ``PROTECT``, so deleting the row
      outright would either fail for every real customer or force us to destroy
      invoices the business is required to retain. Scrubbing removes the personal
      data (name, email, phone, address, geolocation, notes) while leaving the
      financial trail intact against an unidentifiable customer.
    * Subscriptions are deleted outright - they are operational records with no
      retention requirement, and their items/skip-dates cascade with them.
    * Future orders are cancelled; past orders are kept for billing but have
      their delivery address and notes scrubbed.
    * Notifications and FCM device tokens are deleted.

    An outstanding balance does not block deletion - blocking it would fail app
    store review. The amount is recorded in ``AccountDeletionLog`` instead so
    finance can follow up through normal channels.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = "delete_account"

    def post(self, request):
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "") or ""

        user = request.user

        # Staff and driver accounts are provisioned by the business, not
        # self-registered, and deleting one would orphan routes, deliveries and
        # HR records. Those are removed by an administrator instead.
        if user.is_superuser or user.is_staff or user.is_erp_user or user.is_driver:
            return Response(
                {
                    "detail": (
                        "Staff and driver accounts cannot be deleted from the app. "
                        "Please contact your administrator."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = (
            x_forwarded.split(",")[0].strip()
            if x_forwarded
            else request.META.get("REMOTE_ADDR")
        )

        user_id = user.id
        tenant_schema = user.tenant_schema

        stats = {
            "customer_anonymized": False,
            "subscriptions_removed": 0,
            "orders_cancelled": 0,
            "outstanding_balance": Decimal("0"),
        }

        try:
            # Tenant schemas and the public schema share one connection, so a
            # single transaction covers both. Without it a failure partway
            # through would leave a scrubbed customer attached to a live
            # account, and the error below would be a lie.
            with transaction.atomic():
                if tenant_schema:
                    stats.update(self._purge_tenant_data(user, tenant_schema))

                AccountDeletionLog.objects.create(
                    deleted_user_id=user_id,
                    tenant_schema=tenant_schema,
                    reason=reason,
                    outstanding_balance=stats["outstanding_balance"],
                    customer_anonymized=stats["customer_anonymized"],
                    subscriptions_removed=stats["subscriptions_removed"],
                    orders_cancelled=stats["orders_cancelled"],
                    ip_address=ip,
                )

                # Destroys the account itself. Cascades PasswordChangeLog and
                # nulls LoginAuditLog.user, both in the public schema.
                user.delete()
        except Exception:
            logger.exception("Account deletion failed for user_id=%s", user_id)
            return Response(
                {
                    "detail": (
                        "We could not complete the deletion. Your account has not "
                        "been deleted. Please try again, or contact "
                        "support@penchfoods.in."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "detail": "Your account and personal data have been permanently deleted.",
                "outstanding_balance": float(stats["outstanding_balance"]),
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _purge_tenant_data(user, tenant_schema):
        """
        Removes the customer's tenant-scoped data. Called inside the caller's
        transaction, so raising here rolls back the whole deletion and leaves
        the account untouched.
        """
        from django_tenants.utils import schema_context

        result = {
            "customer_anonymized": False,
            "subscriptions_removed": 0,
            "orders_cancelled": 0,
            "outstanding_balance": Decimal("0"),
        }

        with schema_context(tenant_schema):
            from crm.models import Customer
            from finance.models import MonthlyBill, BillStatus
            from notifications.models import FCMToken, Notification
            from orders.models import Order, OrderStatus
            from subscriptions.models import Subscription

            customer = Customer.objects.filter(user=user).first()

            if customer:
                # Balance still owed, recorded before the link is severed
                bills = MonthlyBill.objects.filter(customer=customer).exclude(
                    status=BillStatus.CANCELLED
                )
                result["outstanding_balance"] = sum(
                    (b.total_amount - b.amount_paid for b in bills), Decimal("0")
                )

                # Operational records - no retention requirement
                subs = Subscription.objects.filter(customer=customer)
                result["subscriptions_removed"] = subs.count()
                subs.delete()

                # Stop anything still scheduled for delivery
                result["orders_cancelled"] = Order.objects.filter(
                    customer=customer,
                    status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
                ).update(status=OrderStatus.CANCELLED)

                # Past orders stay for billing, but the address is personal data
                Order.objects.filter(customer=customer).update(
                    delivery_address="", delivery_notes=""
                )

                customer.user = None
                customer.name = f"Deleted customer {str(customer.id)[:8]}"
                customer.email = None
                customer.phone = ""
                customer.address = ""
                customer.notes = ""
                customer.location = None
                customer.is_active = False
                customer.save()

                result["customer_anonymized"] = True

            # Device tokens and in-app notifications live in the tenant
            # schema, so the User cascade in the public schema never reaches
            # them - they have to be removed explicitly.
            Notification.objects.filter(recipient=user).delete()
            FCMToken.objects.filter(user=user).delete()

        return result


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
