from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'is_erp_user', 'is_driver', 'portal', 'phone',
        ]
        read_only_fields = ['id', 'is_erp_user', 'is_driver', 'portal']


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'password', 'phone', 'is_driver', 'is_erp_user']
        read_only_fields = ['id']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
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
        
        # Add tenant info if available (except for admins)
        if not self.user.is_superuser and not self.user.is_staff:
            schema = self.user.tenant_schema
            if schema:
                from tenants.models import City, Domain
                city = City.objects.filter(schema_name=schema).first()
                if city:
                    data['city_name'] = city.name
                    # Look up the first domain associated with this city
                    domain = Domain.objects.filter(tenant=city).first()
                    data['domain_name'] = domain.domain if domain else None
        return data


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, min_length=8)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField()
    uidb64 = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)
