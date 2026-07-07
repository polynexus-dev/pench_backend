from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Company, City, HolidayCalendar, Domain
from .serializers import CompanySerializer, CitySerializer, HolidayCalendarSerializer


class CityViewSet(viewsets.ModelViewSet):
    queryset = City.objects.select_related("company").exclude(schema_name="public")
    serializer_class = CitySerializer

    def get_queryset(self):
        queryset = self.queryset

        # Filter by company ID, code, or name if requested
        company = self.request.query_params.get("company")
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
                    Q(company__code__iexact=company)
                    | Q(company__name__icontains=company)
                )

        company_id = self.request.query_params.get("company_id")
        if company_id:
            queryset = queryset.filter(company_id=company_id)

        company_code = self.request.query_params.get("company_code")
        if company_code:
            queryset = queryset.filter(company__code__iexact=company_code)

        company_name = self.request.query_params.get("company_name")
        if company_name:
            queryset = queryset.filter(company__name__icontains=company_name)

        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        city = self.perform_create_async(serializer)
        response_serializer = self.get_serializer(city)
        return Response(
            {
                "detail": "City provisioning started successfully in the background.",
                "status": "provisioning",
                "city": response_serializer.data,
            },
            status=status.HTTP_202_ACCEPTED,
        )

    def perform_create_async(self, serializer):
        # 1. Save with is_active=False
        city = serializer.save(is_active=False)

        # 2. Automatically create domains for the city (replacing underscores with hyphens for DNS compliance)
        import os

        subdomain = city.schema_name.replace("_", "-")

        base_domain_env = os.environ.get("PUBLIC_DOMAIN")
        created_domains = set()

        # 2a. Domain from environment PUBLIC_DOMAIN
        if base_domain_env:
            domain_name_env = f"{subdomain}.{base_domain_env}"
            Domain.objects.get_or_create(
                domain=domain_name_env, tenant=city, defaults={"is_primary": True}
            )
            created_domains.add(domain_name_env)

        # 2b. Domain dynamically extracted from the request host (e.g. pench.dev.api.polynexus.in)
        if hasattr(self, "request") and self.request:
            req_host = self.request.get_host().split(":")[0]
            # Ignore standard localhost or numeric IPs when extracting request domain
            import re

            is_ip = re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", req_host)
            if (
                req_host
                and req_host != "localhost"
                and req_host != "127.0.0.1"
                and not is_ip
            ):
                domain_name_req = f"{subdomain}.{req_host}"
                if domain_name_req not in created_domains:
                    Domain.objects.get_or_create(
                        domain=domain_name_req,
                        tenant=city,
                        defaults={"is_primary": not created_domains},
                    )
                    created_domains.add(domain_name_req)

        # 2c. Fallback localhost domain for local development convenience
        domain_name_local = f"{subdomain}.localhost"
        if domain_name_local not in created_domains:
            Domain.objects.get_or_create(
                domain=domain_name_local,
                tenant=city,
                defaults={"is_primary": not created_domains},
            )

        # 3. Trigger asynchronous Celery task
        from .tasks import provision_city_schema_task

        provision_city_schema_task.delay(str(city.id))

        return city


class CompanyViewSet(viewsets.ModelViewSet):
    """
    Public schema endpoint to fetch Companies and their associated Cities.
    Used by the frontend to display a Company -> City selection flow.
    """

    queryset = Company.objects.prefetch_related("cities").filter(is_active=True)
    serializer_class = CompanySerializer


class HolidayCalendarViewSet(viewsets.ModelViewSet):
    queryset = HolidayCalendar.objects.all()
    serializer_class = HolidayCalendarSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        from django.db import connection

        if connection.tenant and hasattr(connection.tenant, "id"):
            return qs.filter(city=connection.tenant)
        return qs

    def perform_create(self, serializer):
        from django.db import connection

        if connection.tenant and hasattr(connection.tenant, "id"):
            serializer.save(city=connection.tenant)
        else:
            serializer.save()


from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.db import connection, transaction
from django_tenants.utils import schema_context
from accounts.models import User


class EraseAllDataView(APIView):
    """
    Temporary endpoint for SuperAdmin to erase all data except tenants (Cities/Domains) and superusers.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # 1. Enforce superuser only
        if not request.user.is_superuser:
            raise PermissionDenied("Only superadmins are allowed to access this endpoint.")

        logs = []

        try:
            # 2. Erase non-superuser accounts in the public schema
            with transaction.atomic():
                connection.set_schema_to_public()
                non_superusers = User.objects.filter(is_superuser=False)
                deleted_count, _ = non_superusers.delete()
                logs.append(f"Deleted {deleted_count} non-superuser account(s) from public schema.")

            # 3. Fetch all tenant cities (excluding public)
            cities = City.objects.exclude(schema_name="public")

            # 4. Clear data from all tenant schemas
            for city in cities:
                schema_name = city.schema_name
                logs.append(f"Processing tenant schema: {schema_name}")
                
                with schema_context(schema_name):
                    with connection.cursor() as cursor:
                        # Fetch all tables in the current tenant schema
                        cursor.execute("""
                            SELECT table_name 
                            FROM information_schema.tables 
                            WHERE table_schema = %s 
                            AND table_type = 'BASE TABLE'
                            AND table_name NOT IN ('django_migrations', 'django_content_type', 'spatial_ref_sys')
                        """, [schema_name])
                        
                        tables = [row[0] for row in cursor.fetchall()]
                        
                        if tables:
                            # Truncate tables using CASCADE to handle foreign key dependencies cleanly
                            quoted_tables = ", ".join([f'"{schema_name}"."{table}"' for table in tables])
                            cursor.execute(f"TRUNCATE TABLE {quoted_tables} CASCADE;")
                            logs.append(f"  Truncated {len(tables)} table(s) in schema {schema_name}.")
                        else:
                            logs.append(f"  No tables found to truncate in schema {schema_name}.")

            return Response({
                "status": "success",
                "message": "All data except tenant configurations and superusers erased successfully.",
                "logs": logs
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "status": "error",
                "message": f"An error occurred during data erasure: {str(e)}",
                "logs": logs
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

