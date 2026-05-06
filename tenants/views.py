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
        # Defaulting to <schema_name>.localhost for local development
        domain_name = f"{city.schema_name}.localhost"
        Domain.objects.create(
            domain=domain_name,
            tenant=city,
            is_primary=True
        )


class ZoneViewSet(viewsets.ModelViewSet):
    queryset = Zone.objects.all()
    serializer_class = ZoneSerializer


class HolidayCalendarViewSet(viewsets.ModelViewSet):
    queryset = HolidayCalendar.objects.all()
    serializer_class = HolidayCalendarSerializer
