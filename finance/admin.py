from django.contrib import admin
from .models import MonthlyBill, Transaction, OnlinePayment


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


@admin.register(OnlinePayment)
class OnlinePaymentAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "amount",
        "purpose",
        "status",
        "transaction_id",
        "created_at",
        "verified_by",
    )
    list_filter = ("status", "purpose", "created_at")
    search_fields = ("transaction_id", "customer__name", "customer__phone")
    readonly_fields = ("bill_transaction", "verified_by", "verified_at")
