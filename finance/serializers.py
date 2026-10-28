from rest_framework import serializers
from .models import MonthlyBill, Transaction, OnlinePayment


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



class OnlinePaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    purpose_display = serializers.CharField(source="get_purpose_display", read_only=True)
    verified_by_name = serializers.SerializerMethodField()
    bill_invoice_number = serializers.CharField(
        source="bill.invoice_number", read_only=True, default=None
    )

    class Meta:
        model = OnlinePayment
        fields = [
            "id",
            "customer",
            "customer_name",
            "customer_phone",
            "amount",
            "screenshot",
            "transaction_id",
            "purpose",
            "purpose_display",
            "subscription",
            "order",
            "bill",
            "bill_invoice_number",
            "notes",
            "status",
            "status_display",
            "verified_by",
            "verified_by_name",
            "verified_at",
            "rejection_reason",
            "bill_transaction",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "purpose",
            "status",
            "verified_by",
            "verified_at",
            "rejection_reason",
            "bill_transaction",
            "created_at",
        ]

    def get_verified_by_name(self, obj):
        if obj.verified_by:
            return obj.verified_by.get_full_name() or obj.verified_by.username
        return None

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate(self, attrs):
        # Linked subscription/order/bill must belong to the paying customer.
        customer = attrs.get("customer")
        for field in ("subscription", "order", "bill"):
            linked = attrs.get(field)
            if linked and customer and linked.customer_id != customer.id:
                raise serializers.ValidationError(
                    {field: "Does not belong to this customer."}
                )
        return attrs
