from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = [
        "username",
        "email",
        "is_erp_user",
        "is_driver",
        "portal",
        "is_active",
    ]
    list_filter = ["is_erp_user", "is_driver", "portal", "is_active"]
    fieldsets = UserAdmin.fieldsets + (
        ("Portal Access", {"fields": ("is_erp_user", "is_driver", "portal", "phone")}),
    )
