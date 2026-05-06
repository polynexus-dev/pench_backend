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


class HolidayCalendarViewSet(viewsets.ModelViewSet):
    queryset = HolidayCalendar.objects.all()
    serializer_class = HolidayCalendarSerializer
