from django.contrib import admin
from django_tenants.admin import TenantAdminMixin
from .models import Company, City, Domain, HolidayCalendar


class DomainInline(admin.TabularInline):
    model = Domain
    max_num = 1


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "is_active"]
    search_fields = ["name", "code"]


@admin.register(City)
class CityAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ["name", "company", "state", "code", "is_active", "schema_name"]
    list_filter = ["company", "is_active"]
    inlines = [DomainInline]


@admin.register(HolidayCalendar)
class HolidayCalendarAdmin(admin.ModelAdmin):
    list_display = ["name", "date", "is_recurring"]
