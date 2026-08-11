from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, PasswordChangeLog, LoginAuditLog


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = [
        "username",
        "email",
        "is_erp_user",
        "is_driver",
        "portal",
        "password_changed_at",
        "is_active",
    ]
    list_filter = ["is_erp_user", "is_driver", "portal", "is_active"]
    readonly_fields = UserAdmin.readonly_fields + ("password_changed_at",)
    fieldsets = UserAdmin.fieldsets + (
        (
            "Portal Access & Security",
            {
                "fields": (
                    "is_erp_user",
                    "is_driver",
                    "portal",
                    "phone",
                    "password_changed_at",
                )
            },
        ),
    )


@admin.register(PasswordChangeLog)
class PasswordChangeLogAdmin(admin.ModelAdmin):
    list_display = ["user", "changed_at", "changed_by", "source", "ip_address"]
    list_filter = ["source", "changed_at"]
    search_fields = ["user__username", "user__email", "user__phone", "changed_by__username"]
    readonly_fields = ["user", "changed_at", "changed_by", "source", "ip_address"]


@admin.register(LoginAuditLog)
class LoginAuditLogAdmin(admin.ModelAdmin):
    list_display = ["username_or_phone", "user", "status", "attempt_time", "ip_address"]
    list_filter = ["status", "attempt_time"]
    search_fields = ["username_or_phone", "user__username", "user__email", "ip_address"]
    readonly_fields = ["username_or_phone", "user", "status", "attempt_time", "ip_address", "user_agent"]

