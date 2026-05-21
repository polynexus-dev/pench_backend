from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Company, City, HolidayCalendar, Domain
from .serializers import CompanySerializer, CitySerializer, HolidayCalendarSerializer


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.all()
    serializer_class = CitySerializer

    def perform_create(self, serializer):
        # Save the city
        city = serializer.save()
        
        # Automatically create a domain for the city (replacing underscores with hyphens for DNS compliance)
        import os
        base_domain = os.environ.get('PUBLIC_DOMAIN', 'localhost')
        domain_name = f"{city.schema_name.replace('_', '-')}.{base_domain}"
        
        Domain.objects.get_or_create(
            domain=domain_name,
            tenant=city,
            defaults={'is_primary': True}
        )


class CompanyViewSet(viewsets.ModelViewSet):
    """
    Public schema endpoint to fetch Companies and their associated Cities.
    Used by the frontend to display a Company -> City selection flow.
    """
    queryset = Company.objects.prefetch_related('cities').filter(is_active=True)
    serializer_class = CompanySerializer



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
