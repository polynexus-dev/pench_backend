from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from orders.views import DriverViewSet

urlpatterns = [
    # City Admin
    path("admin/", admin.site.urls),
    # Dedicated Driver URL path
    path(
        "api/drivers/my-route/",
        DriverViewSet.as_view({"get": "my_route"}),
        name="driver-my-route",
    ),
    # City ERP Modules
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
    # City Logistics & Employee Management
    path(
        "api/ems/",
        include(
            [
                path("", include("routing.urls")),
            ]
        ),
    ),
    # Common Auth
    path("api/accounts/", include("accounts.urls")),
    # Firebase & In-App Notifications
    path("api/notifications/", include("notifications.urls")),
    path("api/v1/notifications/", include("notifications.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
