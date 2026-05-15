from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import City, Zone, HolidayCalendar, Domain
from .serializers import CitySerializer, ZoneSerializer, HolidayCalendarSerializer


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.all()
    serializer_class = CitySerializer

    def perform_create(self, serializer):
        # Save the city
        city = serializer.save()
        
        # Automatically create a domain for the city
        import os
        base_domain = os.environ.get('PUBLIC_DOMAIN', 'localhost')
        domain_name = f"{city.schema_name}.{base_domain}"
        
        Domain.objects.get_or_create(
            domain=domain_name,
            tenant=city,
            defaults={'is_primary': True}
        )


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # If we are in a tenant schema, filter zones by that city
        from django.db import connection
        if connection.tenant and hasattr(connection.tenant, 'id'):
            return qs.filter(city=connection.tenant)
        return qs

    def perform_create(self, serializer):
        # Auto-assign city if in tenant schema
        from django.db import connection
        if connection.tenant and hasattr(connection.tenant, 'id'):
            serializer.save(city=connection.tenant)
        else:
            serializer.save()


class HolidayCalendarViewSet(viewsets.ModelViewSet):
    queryset = HolidayCalendar.objects.all()
    serializer_class = HolidayCalendarSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        from django.db import connection
        if connection.tenant and hasattr(connection.tenant, 'id'):
            return qs.filter(city=connection.tenant)
        return qs

    def perform_create(self, serializer):
        from django.db import connection
        if connection.tenant and hasattr(connection.tenant, 'id'):
            serializer.save(city=connection.tenant)
        else:
            serializer.save()
