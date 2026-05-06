from django.contrib import admin
from .models import Subscription, SubscriptionItem, SubscriptionSkipDate

class SubscriptionItemInline(admin.TabularInline):
    model = SubscriptionItem
    extra = 1

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['customer', 'status', 'start_date', 'frequency', 'is_paused']
    list_filter = ['status', 'frequency', 'is_paused']
    search_fields = ['customer__name', 'delivery_address']
    inlines = [SubscriptionItemInline]

admin.site.register(SubscriptionItem)
admin.site.register(SubscriptionSkipDate)
