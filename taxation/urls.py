from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaxRuleViewSet, ProductTaxCategoryViewSet

router = DefaultRouter()
router.register(r"rules", TaxRuleViewSet, basename="tax-rule")
router.register(
    r"product-categories", ProductTaxCategoryViewSet, basename="product-tax-category"
)

urlpatterns = [
    path("", include(router.urls)),
]
