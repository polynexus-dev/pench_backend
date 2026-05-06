from rest_framework import serializers
from .models import MonthlyBill, Transaction


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = '__all__'


class MonthlyBillSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)

    class Meta:
        model = MonthlyBill
        fields = [
            'id', 'customer', 'customer_name', 'billing_month', 
            'total_amount', 'amount_paid', 'status', 'status_display',
            'due_date', 'invoice_number', 'remaining_amount', 'transactions'
        ]
