from django.contrib import admin
from django_tenants.admin import TenantAdminMixin
from .models import City, Domain, Zone, HolidayCalendar


class DomainInline(admin.TabularInline):
    model = Domain
    max_num = 1


@admin.register(City)
class CityAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ['name', 'state', 'code', 'is_active', 'schema_name']
    inlines = [DomainInline]


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active']


@admin.register(HolidayCalendar)
class HolidayCalendarAdmin(admin.ModelAdmin):
    list_display = ['name', 'date', 'is_recurring']
