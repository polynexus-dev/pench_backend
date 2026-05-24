from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from .models import User


class UserSerializer(serializers.ModelSerializer):
    customer_dashboard = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    user_permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'is_erp_user', 'is_driver', 'is_customer', 'portal', 'phone',
            'tenant_schema', 'groups', 'role', 'customer_dashboard',
            'user_permissions', 'is_superuser', 'is_staff',
        ]
        read_only_fields = ['id', 'is_erp_user', 'is_driver', 'is_customer', 'portal', 'tenant_schema', 'is_superuser', 'is_staff']

    def get_customer_dashboard(self, obj):
        """
        Aggregates dashboard data for customers by switching to their tenant schema.
        Visible to the customer themselves and Admins.
        """
        if not obj.is_customer or not obj.tenant_schema:
            return None
            
        from django_tenants.utils import schema_context
        from django.db.models import Sum, F
        
        try:
            with schema_context(obj.tenant_schema):
                from subscriptions.models import Subscription, SubscriptionStatus
                from finance.models import MonthlyBill, BillStatus
                from orders.models import Order
                
                # 1. Active Subscriptions
                active_subs = Subscription.objects.filter(
                    customer__user=obj, 
                    status=SubscriptionStatus.ACTIVE
                ).count()
                
                # 2. Pending Balance (Sum of total - paid for all non-cancelled bills)
                bills = MonthlyBill.objects.filter(
                    customer__user=obj
                ).exclude(status=BillStatus.CANCELLED)
                
                total_pending = 0
                for bill in bills:
                    total_pending += (bill.total_amount - bill.amount_paid)
                
                # 3. Total Orders
                total_orders = Order.objects.filter(customer__user=obj).count()
                
                return {
                    "active_subscriptions": active_subs,
                    "pending_balance": float(total_pending),
                    "total_orders": total_orders,
                    "schema": obj.tenant_schema
                }
        except Exception as e:
            # Silently fail if schema or models are not accessible to prevent crashing the User API
            return {"error": "Dashboard data temporarily unavailable"}

    def get_groups(self, obj):
        return [group.name for group in obj.groups.all()]

    def get_role(self, obj):
        if obj.is_superuser or obj.groups.filter(name='SuperAdmin').exists():
            return "SuperAdmin"
        if obj.is_erp_user:
            mgmt_group = obj.groups.exclude(name='Customers').first()
            return mgmt_group.name if mgmt_group else "ERP_Admin"
        if obj.is_driver:
            return "Driver"
        if obj.is_customer:
            return "Customer"
        return "User"

    def get_user_permissions(self, obj):
        return [
            {"id": p.id, "name": p.name, "codename": p.codename}
            for p in obj.user_permissions.all()
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        company_id = None
        company_name = None
        if instance.tenant_schema and instance.tenant_schema != 'public':
            from tenants.models import City
            city = City.objects.filter(schema_name=instance.tenant_schema).select_related('company').first()
            if city and city.company:
                company_id = str(city.company.id)
                company_name = city.company.name
        ret['company_id'] = company_id
        ret['company_name'] = company_name
        return ret


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    phone = serializers.CharField(required=True)
    email = serializers.EmailField(required=True)
    role = serializers.CharField(write_only=True, required=False) # New Role field
    groups = serializers.SlugRelatedField(
        many=True,
        slug_field='name',
        queryset=Group.objects.all(),
        required=False
    )

    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    address = serializers.CharField(required=False, allow_blank=True)
    company = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    
    # Driver and Customer profile-specific fields
    zone = serializers.CharField(required=False, allow_blank=True, write_only=True)
    warehouse = serializers.CharField(required=False, allow_blank=True, write_only=True)
    vehicle_plate = serializers.CharField(required=False, allow_blank=True, write_only=True)
    vehicle_type = serializers.CharField(required=False, allow_blank=True, write_only=True)
    max_capacity_kg = serializers.DecimalField(required=False, max_digits=8, decimal_places=2, write_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'password', 
            'phone', 'is_driver', 'is_erp_user', 'is_customer', 'groups', 
            'tenant_schema', 'role', 'latitude', 'longitude', 
            'address', 'company', 'notes', 'zone', 'warehouse', 'vehicle_plate',
            'vehicle_type', 'max_capacity_kg', 'is_superuser', 'is_staff'
        ]
        read_only_fields = ['id', 'is_superuser', 'is_staff']

    def create(self, validated_data):
        groups_data = validated_data.pop('groups', [])
        role_name = validated_data.pop('role', None)
        password = validated_data.pop('password')
        
        # Resolve tenant_schema to the correct schema name if provided
        tenant_schema = validated_data.get('tenant_schema', None)
        if tenant_schema:
            from tenants.models import City
            from django.db.models import Q
            city = City.objects.filter(
                Q(schema_name__iexact=tenant_schema) |
                Q(schema_name__iexact=tenant_schema.replace('-', '_')) |
                Q(code__iexact=tenant_schema) |
                Q(name__iexact=tenant_schema)
            ).first()
            
            if city:
                validated_data['tenant_schema'] = city.schema_name
            else:
                raise serializers.ValidationError({
                    "tenant_schema": f"Tenant schema or city '{tenant_schema}' does not exist."
                })

        # 1. Set Boolean Flags based on role name
        if role_name:
            if role_name == 'Drivers':
                validated_data['is_driver'] = True
            elif role_name == 'Customers':
                validated_data['is_customer'] = True
            elif role_name in ['Managers', 'SuperAdmin', 'Staff', 'ERP_Admins']:
                validated_data['is_erp_user'] = True
                if role_name == 'SuperAdmin':
                    validated_data['is_superuser'] = True
                    validated_data['is_staff'] = True
                elif role_name == 'Staff':
                    validated_data['is_staff'] = True

        # 2. Extract CRM fields so they don't crash User creation
        lat = validated_data.pop('latitude', None)
        lon = validated_data.pop('longitude', None)
        addr = validated_data.pop('address', None)
        comp = validated_data.pop('company', None)
        nts = validated_data.pop('notes', None)
        
        # Profile-specific fields
        zone = validated_data.pop('zone', None)
        warehouse = validated_data.pop('warehouse', None)
        plate = validated_data.pop('vehicle_plate', None)
        v_type = validated_data.pop('vehicle_type', None)
        cap = validated_data.pop('max_capacity_kg', None)

        # 3. Instantiate the User object (do not save to DB yet)
        user = User(**validated_data)
        user.set_password(password)
        
        # Attach temporary attributes for the signal to catch
        user.latitude = lat
        user.longitude = lon
        user.address = addr
        user.company = comp
        user.notes = nts
        user.zone = zone
        user.warehouse = warehouse
        user.vehicle_plate = plate
        user.vehicle_type = v_type
        user.max_capacity_kg = cap
        
        # Save to DB (this triggers post_save signal exactly once, with all attributes populated)
        user.save()
        
        # 3. Assign to Groups
        final_groups = list(groups_data)
        if role_name:
            group, _ = Group.objects.get_or_create(name=role_name)
            final_groups.append(group)
        
        if final_groups:
            user.groups.set(final_groups)
        
        return user

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if not instance.is_customer:
            ret.pop('latitude', None)
            ret.pop('longitude', None)
        
        company_id = None
        company_name = None
        if instance.tenant_schema and instance.tenant_schema != 'public':
            from tenants.models import City
            city = City.objects.filter(schema_name=instance.tenant_schema).select_related('company').first()
            if city and city.company:
                company_id = str(city.company.id)
                company_name = city.company.name
        ret['company_id'] = company_id
        ret['company_name'] = company_name
        return ret


class RequestOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class LoginOTPSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        
        # Route Admin/ERP users to the Public Domain
        if self.user.is_superuser or self.user.is_erp_user or self.user.groups.filter(name='SuperAdmin').exists():
            from tenants.models import Domain
            request = self.context.get('request')
            current_host = request.get_host().split(':')[0] if request else 'localhost'
            base_domain = '.'.join(current_host.split('.')[-2:]) if 'nip.io' not in current_host else '.'.join(current_host.split('.')[-5:])
            
            public_domain = Domain.objects.filter(tenant__schema_name='public', domain__icontains=base_domain).first()
            if not public_domain:
                public_domain = Domain.objects.filter(tenant__schema_name='public').first()
                
            if public_domain:
                data['domain_name'] = public_domain.domain.replace('_', '-')
            else:
                data['domain_name'] = 'localhost' # Fallback for local testing
                
        # Route Drivers/Customers to their specific Tenant Domain
        else:
            from django.db import connection
            schema = self.user.tenant_schema
            
            # Fallback to current connection tenant if user field is empty
            if not schema and hasattr(connection, 'tenant'):
                schema = getattr(connection.tenant, 'schema_name', None)

            # If still 'public', search for an active city as a last resort
            if (not schema or schema == 'public') and (self.user.is_driver or self.user.is_customer):
                from tenants.models import City
                city = City.objects.filter(is_active=True).exclude(schema_name='public').first()
                if city:
                    schema = city.schema_name

            if schema and schema != 'public':
                from tenants.models import City, Domain
                city = City.objects.filter(schema_name=schema).first()
                if city:
                    data['sid'] = city.schema_name
                    data['city_name'] = city.name
                    
                    request = self.context.get('request')
                    current_host = request.get_host().split(':')[0] if request else 'localhost'
                    base_domain = '.'.join(current_host.split('.')[-2:]) if 'nip.io' not in current_host else '.'.join(current_host.split('.')[-5:])
                    
                    domain = Domain.objects.filter(tenant=city, domain__icontains=base_domain).first()
                    if not domain:
                        domain = Domain.objects.filter(tenant=city).first()
                    
                    data['domain_name'] = domain.domain.replace('_', '-') if domain and domain.domain else f"{schema.replace('_', '-')}.{base_domain}"
                    
                    # If driver, find their active route
                    if self.user.is_driver:
                        from django_tenants.utils import schema_context
                        with schema_context(schema):
                            # 1. Search in the delivery routing system (used by the mobile app's stop schedule)
                            from orders.models import Route as OrdersRoute
                            from django.db.models import Q
                            route = OrdersRoute.objects.filter(
                                Q(driver=self.user) | Q(additional_drivers=self.user),
                                is_completed=False
                            ).distinct().order_by('delivery_date').first()
                            
                            if route:
                                data['active_route_id'] = str(route.id)
                            else:
                                # 2. Fallback to the new routing system
                                from routing.models import Route as RoutingRoute, Driver
                                driver_profile = Driver.objects.filter(user=self.user).first()
                                if driver_profile:
                                    r_route = RoutingRoute.objects.filter(
                                        Q(driver=driver_profile) | Q(additional_drivers=driver_profile),
                                        status__in=['pending', 'in_progress']
                                    ).distinct().first()
                                    if r_route:
                                        data['active_route_id'] = str(r_route.id)
        return data


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, min_length=8)


class ForgotPasswordSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class ResetPasswordSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)


class PermissionSerializer(serializers.ModelSerializer):
    content_type = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
        required=False,
        allow_null=True
    )
    content_type_name = serializers.CharField(source='content_type.app_label', read_only=True)

    class Meta:
        model = Permission
        fields = ['id', 'name', 'codename', 'content_type', 'content_type_name']
        validators = []  # Disable UniqueTogetherValidator to allow content_type to be optional

    def create(self, validated_data):
        if not validated_data.get('content_type'):
            # Default ContentType to User
            user_content_type = ContentType.objects.get_for_model(User)
            validated_data['content_type'] = user_content_type
        return super().create(validated_data)


class GroupSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Permission.objects.all(),
        required=False
    )
    permissions_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions', 'permissions_detail']

    def get_permissions_detail(self, obj):
        return [
            {"id": p.id, "name": p.name, "codename": p.codename}
            for p in obj.permissions.all()
        ]
