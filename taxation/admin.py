from django.contrib import admin
from .models import TaxRule, ProductTaxCategory


@admin.register(TaxRule)
class TaxRuleAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "state",
        "tax_type",
        "rate_percentage",
        "tax_category",
        "is_active",
        "effective_from",
    ]
    list_filter = ["tax_type", "tax_category", "is_active", "state"]
    search_fields = ["name", "state"]


@admin.register(ProductTaxCategory)
class ProductTaxCategoryAdmin(admin.ModelAdmin):
    list_display = ["product", "tax_category", "hsn_code"]
    list_filter = ["tax_category"]
    search_fields = ["product__name", "hsn_code"]
