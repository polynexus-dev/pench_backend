from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # Delivery / EMS portal
    path('api/ems/', include('routing.urls')),

    # ERP portal
    path('api/erp/', include([
        path('tenants/', include('tenants.urls')),
        path('customers/', include('crm.urls')),
        path('taxation/', include('taxation.urls')),
        path('orders/', include('orders.urls')),
        path('subscriptions/', include('subscriptions.urls')),
        path('inventory/', include('inventory.urls')),
        path('finance/', include('finance.urls')),
        path('hr/', include('hr.urls')),
        path('tracking/', include('tracking.urls')),
        path('administration/', include('administration.urls')),
    ])),

    # Accounts
    path('api/accounts/', include('accounts.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
