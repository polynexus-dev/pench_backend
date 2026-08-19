from django.contrib import admin
from django.urls import path, include
from schema_graph.views import Schema
from django.conf import settings
from django.conf.urls.static import static
from core.views import PrivacyPolicyView, AccountDeletionView


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
    # Public, tenant-independent privacy policy (used for Play Store / App Store listings)
    path("privacy-policy/", PrivacyPolicyView.as_view(), name="privacy-policy"),
    # Public account deletion request page (used for Play Store Data Safety compliance)
    path("delete-account/", AccountDeletionView.as_view(), name="delete-account"),
    # ERP portal - public/shared endpoints only
    path(
        "api/erp/",
        include(
            [
                path("tenants/", include("tenants.urls")),
            ]
        ),
    ),
    # Accounts
    path("api/accounts/", include("accounts.urls")),
    # Schema Graph
    path("schema/", CleanSchema.as_view()),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
