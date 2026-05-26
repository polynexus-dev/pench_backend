from django.contrib import admin
from .models import AdminConfiguration, AdminUserProxy
from accounts.admin import CustomUserAdmin


@admin.register(AdminConfiguration)
class AdminConfigurationAdmin(admin.ModelAdmin):
    """
    Admin configuration for the singleton model.
    """

    fieldsets = (
        (
            "Delivery Settings",
            {
                "fields": (
                    "enable_delivery_photo",
                    "require_signature",
                    "auto_assign_orders",
                )
            },
        ),
        (
            "Returnable Containers Settings",
            {"fields": ("charge_bottle_penalty", "bottle_penalty_amount")},
        ),
        ("Order Constraints", {"fields": ("max_cancellation_time",)}),
        (
            "Support & Communication",
            {"fields": ("support_contact_number", "support_email", "company_name")},
        ),
        ("Appearance", {"fields": ("theme_color",)}),
    )

    def has_add_permission(self, request):
        from django.db import connection

        if connection.schema_name == "public":
            return False
        # Prevent adding more than one configuration
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        # Prevent deleting the configuration
        return False

    def has_module_permission(self, request):
        from django.db import connection

        return connection.schema_name != "public"


@admin.register(AdminUserProxy)
class AdminUserProxyAdmin(CustomUserAdmin):
    """
    User management within the Administration module.
    """

    def has_module_permission(self, request):
        from django.db import connection

        return connection.schema_name != "public"
