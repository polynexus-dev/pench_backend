from rest_framework import serializers
from .models import MonthlyBill, Transaction


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'bill', 'amount', 'payment_method', 'transaction_id', 'payment_date', 'notes']
        read_only_fields = ['payment_date']


class MonthlyBillSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = MonthlyBill
        fields = [
            'id', 'customer', 'customer_name', 'billing_month',
            'total_amount', 'amount_paid', 'remaining_amount',
            'status', 'status_display', 'due_date', 'invoice_number', 'transactions'
        ]
