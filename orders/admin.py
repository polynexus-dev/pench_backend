from django.contrib import admin
from .models import Order, OrderItem, Package, Route, RouteStop


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class PackageInline(admin.TabularInline):
    model = Package
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "customer", "status", "total", "created_at"]
    list_filter = ["status"]
    search_fields = ["customer__name", "delivery_address"]
    inlines = [OrderItemInline, PackageInline]


from django import forms
from django.core.exceptions import ValidationError

class RouteStopInline(admin.TabularInline):
    model = RouteStop
    extra = 0
    raw_id_fields = ["order"]


class RouteAdminForm(forms.ModelForm):
    class Meta:
        model = Route
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        is_completed = cleaned_data.get("is_completed")
        status = cleaned_data.get("status")
        if self.instance.pk:
            old_instance = Route.objects.get(pk=self.instance.pk)
            # If it wasn't completed before, but now trying to set to True or completed
            if not old_instance.is_completed and (is_completed or status == "completed"):
                raise ValidationError("Manual trip completion is disabled. Trips are automatically completed by the system at 12:00 PM.")
        return cleaned_data


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    form = RouteAdminForm
    list_display = ["name", "delivery_date", "driver", "is_completed"]
    list_filter = ["delivery_date", "is_completed"]
    inlines = [RouteStopInline]
