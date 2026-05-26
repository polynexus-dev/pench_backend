from django.contrib import admin
from .models import MonthlyBill, Transaction


class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0


@admin.register(MonthlyBill)
class MonthlyBillAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "customer",
        "billing_month",
        "total_amount",
        "status",
        "due_date",
    )
    list_filter = ("status", "billing_month")
    search_fields = ("invoice_number", "customer__name")
    inlines = [TransactionInline]
    readonly_fields = ("invoice_number",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "bill",
        "amount",
        "payment_method",
        "payment_date",
        "transaction_id",
    )
    list_filter = ("payment_method", "payment_date")
    search_fields = ("transaction_id", "bill__invoice_number")
