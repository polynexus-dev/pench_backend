from rest_framework import serializers
from .models import MonthlyBill, Transaction


class TransactionSerializer(serializers.ModelSerializer):
    customer_id = serializers.ReadOnlyField(source="bill.customer.id")
    customer_name = serializers.ReadOnlyField(source="bill.customer.name")

    class Meta:
        model = Transaction
        fields = [
            "id",
            "bill",
            "customer_id",
            "customer_name",
            "amount",
            "payment_method",
            "transaction_id",
            "payment_date",
            "notes",
        ]
        read_only_fields = ["payment_date"]


class MonthlyBillSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)
    remaining_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = MonthlyBill
        fields = [
            "id",
            "customer",
            "customer_name",
            "billing_month",
            "total_amount",
            "amount_paid",
            "remaining_amount",
            "status",
            "status_display",
            "due_date",
            "invoice_number",
            "transactions",
        ]


class MonthlyBillListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for MonthlyBill list views — no nested transactions."""
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    remaining_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    transaction_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = MonthlyBill
        fields = [
            "id",
            "customer",
            "customer_name",
            "billing_month",
            "total_amount",
            "amount_paid",
            "remaining_amount",
            "status",
            "status_display",
            "due_date",
            "invoice_number",
            "transaction_count",
        ]

