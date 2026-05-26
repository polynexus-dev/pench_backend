from django.contrib import admin
from django.urls import path, include
from schema_graph.views import Schema
from django.conf import settings
from django.conf.urls.static import static


class CleanSchema(Schema):
    def models(self):
        """
        Filter out abstract base models and internal Django models
        that create too many inheritance lines.
        """
        models = super().models()
        excluded_models = [
            "BaseModel",
            "UUIDModel",
            "TimestampedModel",
            "AbstractUser",
            "AbstractBaseUser",
            "PermissionsMixin",
        ]
        return [m for m in models if m.__name__ not in excluded_models]


urlpatterns = [
    path("admin/", admin.site.urls),
    # Delivery / EMS portal
    path("api/ems/", include("routing.urls")),
    # ERP portal
    path(
        "api/erp/",
        include(
            [
                path("tenants/", include("tenants.urls")),
                path("", include("crm.urls")),
                path("taxation/", include("taxation.urls")),
                path("orders/", include("orders.urls")),
                path("subscriptions/", include("subscriptions.urls")),
                path("inventory/", include("inventory.urls")),
                path("finance/", include("finance.urls")),
                path("hr/", include("hr.urls")),
                path("tracking/", include("tracking.urls")),
                path("administration/", include("administration.urls")),
            ]
        ),
    ),
    # Accounts
    path("api/accounts/", include("accounts.urls")),
    # Schema Graph
    path("schema/", CleanSchema.as_view()),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
