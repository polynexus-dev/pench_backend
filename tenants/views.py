from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Company, City, HolidayCalendar, Domain
from .serializers import CompanySerializer, CitySerializer, HolidayCalendarSerializer


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.select_related('company').all()
    serializer_class = CitySerializer

    def get_queryset(self):
        queryset = self.queryset
        
        # Filter by company ID, code, or name if requested
        company = self.request.query_params.get('company')
        if company:
            # Check if it is a valid UUID
            import uuid
            is_uuid = False
            try:
                uuid.UUID(str(company))
                is_uuid = True
            except ValueError:
                pass

            if is_uuid:
                queryset = queryset.filter(company_id=company)
            elif company.isdigit():
                queryset = queryset.filter(company_id=company)
            else:
                from django.db.models import Q
                queryset = queryset.filter(
                    Q(company__code__iexact=company) |
                    Q(company__name__icontains=company)
                )
                
        company_id = self.request.query_params.get('company_id')
        if company_id:
            queryset = queryset.filter(company_id=company_id)
            
        company_code = self.request.query_params.get('company_code')
        if company_code:
            queryset = queryset.filter(company__code__iexact=company_code)
            
        company_name = self.request.query_params.get('company_name')
        if company_name:
            queryset = queryset.filter(company__name__icontains=company_name)
            
        return queryset

    def perform_create(self, serializer):
        # Save the city
        city = serializer.save()
        
        # Automatically create a domain for the city (replacing underscores with hyphens for DNS compliance)
        import os
        base_domain = os.environ.get('PUBLIC_DOMAIN', 'localhost')
        subdomain = city.schema_name.replace('_', '-')
        domain_name = f"{subdomain}.{base_domain}"
        
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
