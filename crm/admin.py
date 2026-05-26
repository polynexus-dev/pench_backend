from django.contrib.gis import admin
from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.GISModelAdmin):
    list_display = ["name", "company", "email", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "company", "email"]
