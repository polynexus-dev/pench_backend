from rest_framework import viewsets
from .models import TaxRule, ProductTaxCategory
from .serializers import TaxRuleSerializer, ProductTaxCategorySerializer


class TaxRuleViewSet(viewsets.ModelViewSet):
    queryset = TaxRule.objects.all()
    serializer_class = TaxRuleSerializer


class ProductTaxCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductTaxCategory.objects.all().select_related("product")
    serializer_class = ProductTaxCategorySerializer
