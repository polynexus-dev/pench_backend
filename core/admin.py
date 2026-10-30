from django.contrib import admin

from core.models import AppVersionConfig


@admin.register(AppVersionConfig)
class AppVersionConfigAdmin(admin.ModelAdmin):
    list_display = (
        "app",
        "platform",
        "min_supported_version",
        "latest_version",
        "maintenance_mode",
        "is_active",
        "updated_at",
    )
    list_filter = ("app", "platform", "maintenance_mode", "is_active")
    list_editable = ("min_supported_version", "latest_version", "maintenance_mode")
