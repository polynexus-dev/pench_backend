from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import AdminConfiguration
from .serializers import AdminConfigurationSerializer


class AdminConfigurationViewSet(viewsets.ModelViewSet):
    """
    API endpoint for viewing and editing tenant-specific configuration.
    """
    queryset = AdminConfiguration.objects.all()
    serializer_class = AdminConfigurationSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_object(self):
        # Always return the single instance
        obj, created = AdminConfiguration.objects.get_or_create()
        return obj

    def list(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        # Override create to act like an update/get
        return self.update(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='driver-settings',
            permission_classes=[permissions.IsAuthenticated])
    def driver_settings(self, request):
        """
        Lightweight endpoint for the driver mobile app.
        Returns only the settings relevant to drivers (e.g. broken bottle tracking).
        """
        from django_tenants.utils import schema_context
        from django.db import connection

        user = request.user
        schema = user.tenant_schema
        context_schema = schema if connection.schema_name == 'public' and schema else connection.schema_name

        with schema_context(context_schema):
            config = AdminConfiguration.get_solo()
            charge_bottle_penalty = config.charge_bottle_penalty

        return Response({
            'charge_bottle_penalty': charge_bottle_penalty,
        })

