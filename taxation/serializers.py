from rest_framework import serializers
from .models import TaxRule, ProductTaxCategory


class TaxRuleSerializer(serializers.ModelSerializer):
    tax_type_display = serializers.CharField(source='get_tax_type_display', read_only=True)

    class Meta:
        model = TaxRule
        fields = [
            'id', 'name', 'state', 'tax_type', 'tax_type_display',
            'rate_percentage', 'tax_category', 'is_active',
            'effective_from', 'effective_to', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ProductTaxCategorySerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    tax_category_display = serializers.CharField(source='get_tax_category_display', read_only=True)

    class Meta:
        model = ProductTaxCategory
        fields = [
            'id', 'product', 'product_name', 'tax_category',
            'tax_category_display', 'hsn_code',
        ]
        read_only_fields = ['id']
