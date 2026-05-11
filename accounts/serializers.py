from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import Group
from .models import User


class UserSerializer(serializers.ModelSerializer):
    groups = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'is_erp_user', 'is_driver', 'is_customer', 'portal', 'phone',
            'tenant_schema', 'groups', 'role',
        ]
        read_only_fields = ['id', 'is_erp_user', 'is_driver', 'is_customer', 'portal', 'tenant_schema']

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


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
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

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'password', 
            'phone', 'is_driver', 'is_erp_user', 'is_customer', 'groups', 
            'tenant_schema', 'role', 'latitude', 'longitude', 
            'address', 'company', 'notes'
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        groups_data = validated_data.pop('groups', [])
        role_name = validated_data.pop('role', None)
        password = validated_data.pop('password')
        
        # 1. Set Boolean Flags based on role name
        if role_name:
            if role_name == 'Drivers':
                validated_data['is_driver'] = True
            elif role_name == 'Customers':
                validated_data['is_customer'] = True
            elif role_name in ['Managers', 'SuperAdmin', 'Staff', 'ERP_Admins']:
                validated_data['is_erp_user'] = True

        # 2. Extract CRM fields so they don't crash User creation
        lat = validated_data.pop('latitude', None)
        lon = validated_data.pop('longitude', None)
        addr = validated_data.pop('address', None)
        comp = validated_data.pop('company', None)
        nts = validated_data.pop('notes', None)

        # 3. Create the User object
        user = User.objects.create(**validated_data)
        user.set_password(password)
        
        # Attach temporary attributes for the signal to catch
        user.latitude = lat
        user.longitude = lon
        user.address = addr
        user.company = comp
        user.notes = nts
        
        user.save()
        
        # 3. Assign to Groups
        final_groups = list(groups_data)
        if role_name:
            group, _ = Group.objects.get_or_create(name=role_name)
            final_groups.append(group)
        
        if final_groups:
            user.groups.set(final_groups)
        
        return user


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
            public_domain = Domain.objects.filter(tenant__schema_name='public').first()
            if public_domain:
                data['domain_name'] = public_domain.domain
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
                    domain = Domain.objects.filter(tenant=city).first()
                    data['domain_name'] = domain.domain if domain else None
                    
                    # If driver, find today's active route
                    if self.user.is_driver:
                        from django_tenants.utils import schema_context
                        import datetime
                        with schema_context(schema):
                            from orders.models import Route
                            # Look for the nearest upcoming active route (today or future)
                            route = Route.objects.filter(
                                driver=self.user,
                                delivery_date__gte=datetime.date.today(),
                                is_completed=False
                            ).order_by('delivery_date').first()
                            if route:
                                data['route_id'] = str(route.id)
        return data


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, min_length=8)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    uidb64 = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)
