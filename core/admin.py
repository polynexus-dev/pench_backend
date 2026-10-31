from django.contrib import admin, messages

from core.models import AppVersionConfig


@admin.register(AppVersionConfig)
class AppVersionConfigAdmin(admin.ModelAdmin):
    list_display = (
        "app",
        "platform",
        "min_supported_version",
        "latest_version",
        "store_version",
        "auto_force_store_version",
        "maintenance_mode",
        "is_active",
        "last_store_check_at",
    )
    list_filter = ("app", "platform", "auto_force_store_version", "maintenance_mode", "is_active")
    list_editable = ("maintenance_mode",)
    readonly_fields = (
        "store_version",
        "store_version_detected_at",
        "last_store_check_at",
        "last_store_check_error",
        "updated_at",
    )
    fieldsets = (
        (None, {"fields": ("app", "platform", "is_active")}),
        ("Versions", {"fields": ("min_supported_version", "latest_version", "store_url", "update_message")}),
        (
            "Automatic store sync",
            {
                "description": "When enabled, the latest version published on the store "
                "automatically becomes the minimum supported version.",
                "fields": (
                    "auto_force_store_version",
                    "store_app_id",
                    "force_delay_minutes",
                    "store_version",
                    "store_version_detected_at",
                    "last_store_check_at",
                    "last_store_check_error",
                ),
            },
        ),
        ("Maintenance", {"fields": ("maintenance_mode", "maintenance_message")}),
    )
    actions = ["sync_from_store"]

    @admin.action(description="Sync versions from App Store / Play Store now")
    def sync_from_store(self, request, queryset):
        from core.store_versions import sync_config

        for cfg in queryset:
            result = sync_config(cfg)
            level = messages.ERROR if result.startswith("error") else messages.SUCCESS
            self.message_user(request, f"{cfg.app}/{cfg.platform}: {result}", level)
