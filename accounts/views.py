from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.utils import timezone
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
from .models import User, OTP
from .serializers import (
    UserSerializer, UserCreateSerializer, 
    RequestOTPSerializer, LoginOTPSerializer,
    MyTokenObtainPairSerializer, SetPasswordSerializer,
    ForgotPasswordSerializer, ResetPasswordSerializer
)
from .utils import generate_otp


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        """
        Supports creating multiple user accounts in one request.
        """
        is_many = isinstance(request.data, list)
        if not is_many:
            return super().create(request, *args, **kwargs)
        
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


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

    def post(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']
        
        # 1. Check if User already exists in Public Schema
        user = User.objects.filter(phone=phone).first()
        
        # 2. If not found, search across ALL tenant schemas
        if not user:
            from crm.models import Customer
            from tenants.models import City
            from django_tenants.utils import schema_context
            
            # Iterate through all cities to find this customer
            for city in City.objects.exclude(schema_name='public'):
                with schema_context(city.schema_name):
                    customer = Customer.objects.filter(phone=phone).first()
                    if customer:
                        # Found them! Create the public User account
                        username = phone # Use phone as username for easy login
                        user = User.objects.create(
                            username=username,
                            phone=phone,
                            is_customer=True,
                            tenant_schema=city.schema_name,
                            first_name=customer.name
                        )
                        # Link the customer in the tenant schema to the new public user
                        customer.user = user
                        customer.save()
                        print(f"Global Search: Found {customer.name} in {city.name}. Linked to new User {username}")
                        break # Stop searching other cities
            
            if not user:
                return Response(
                    {"error": "No customer found with this phone number in any city."}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        
        # 3. Generate and "send" OTP
        otp_obj = generate_otp(phone)
        
        response_data = {"message": "OTP sent successfully."}
        
        response_data["otp"] = otp_obj.code
            
        return Response(response_data)


class LoginOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']
        code = serializer.validated_data['code']
        
        # Validate OTP
        otp = OTP.objects.filter(
            phone=phone, 
            code=code, 
            is_used=False,
            expires_at__gt=timezone.now()
        ).first()
        
        if not otp:
            return Response(
                {"error": "Invalid or expired OTP."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Mark as used
        otp.is_used = True
        otp.save()
        
        # Get User
        user = User.objects.get(phone=phone)
        
        # Fallback: If user has no schema (created before the update), try to find it now
        if not user.tenant_schema:
            from tenants.models import City
            from crm.models import Customer
            from django_tenants.utils import schema_context
            for city in City.objects.exclude(schema_name='public'):
                with schema_context(city.schema_name):
                    if Customer.objects.filter(phone=phone).exists():
                        user.tenant_schema = city.schema_name
                        user.save()
                        break

        # Generate JWT
        refresh = RefreshToken.for_user(user)
        
        response_data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data
        }

        # Add tenant info if available
        if user.tenant_schema:
            from tenants.models import City, Domain
            city = City.objects.filter(schema_name=user.tenant_schema).first()
            if city:
                response_data['tenant_schema'] = city.schema_name
                response_data['tenant_name'] = city.name
                # Look up the domain (smart selection based on current request host)
                current_host = request.get_host().split(':')[0]
                base_domain = '.'.join(current_host.split('.')[-2:]) if 'nip.io' not in current_host else '.'.join(current_host.split('.')[-5:])
                
                domain = Domain.objects.filter(tenant=city, domain__icontains=base_domain).first()
                if not domain:
                    domain = Domain.objects.filter(tenant=city).first()
                    
                response_data['tenant_domain'] = domain.domain if domain else None
                
                # If driver, find their active (incomplete) route
                if user.is_driver:
                    from django_tenants.utils import schema_context
                    import datetime
                    with schema_context(user.tenant_schema):
                        from orders.models import Route
                        route = Route.objects.filter(
                            driver=user,
                            delivery_date__gte=datetime.date.today(),
                            is_completed=False
                        ).order_by('delivery_date').first()
                        if route:
                            response_data['active_route_id'] = str(route.id)
        
        return Response(response_data)


class SetPasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        request.user.set_password(serializer.validated_data['password'])
        request.user.save()
        
        return Response({"message": "Password set successfully."})


class ForgotPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        
        user = User.objects.filter(email=email).first()
        if user:
            token_generator = PasswordResetTokenGenerator()
            token = token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            
            # Construct reset link (in a real app, this would be a frontend URL)
            # For now, we point to a placeholder
            reset_link = f"http://localhost:3000/reset-password?uidb64={uidb64}&token={token}"
            
            context = {
                'city_name': 'Smart Dairy ERP',
                'reset_link': reset_link,
            }
            
            html_message = render_to_string('emails/password_reset.html', context)
            
            # Send email (prints to console by default if not configured)
            send_mail(
                subject='Password Reset Request',
                message=f'Reset your password here: {reset_link}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=html_message
            )
            
        # We return success regardless of whether the email exists for security
        return Response({"message": "If an account exists with this email, a reset link has been sent."})


class ResetPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            uid = force_str(urlsafe_base64_decode(serializer.validated_data['uidb64']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
            
        token_generator = PasswordResetTokenGenerator()
        if user and token_generator.check_token(user, serializer.validated_data['token']):
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({"message": "Password reset successfully."})
        else:
            return Response({"error": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
class UserListView(generics.ListAPIView):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['tenant_schema', 'is_driver', 'is_customer', 'is_erp_user', 'is_staff', 'is_superuser']
    search_fields = ['username', 'first_name', 'last_name', 'email', 'phone']

    def get_queryset(self):
        queryset = super().get_queryset()
        group_name = self.request.query_params.get('group')
        if group_name:
            queryset = queryset.filter(groups__name=group_name)
        return queryset
