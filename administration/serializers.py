from rest_framework import serializers
from .models import AdminConfiguration


class AdminConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminConfiguration
        fields = "__all__"
