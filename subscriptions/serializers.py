from rest_framework import serializers
from .models import Subscription, SubscriptionItem, SubscriptionSkipDate


class SubscriptionItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = SubscriptionItem
        fields = ["id", "product", "product_name", "quantity"]


class SubscriptionSkipDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionSkipDate
        fields = ["id", "skip_date", "reason"]


class SubscriptionSerializer(serializers.ModelSerializer):
    items = SubscriptionItemSerializer(many=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    frequency_display = serializers.CharField(
        source="get_frequency_display", read_only=True
    )
    pause_updated_by_name = serializers.SerializerMethodField()
    # Optional online payment submitted with the subscription - stored as an OnlinePayment
    payment_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, write_only=True, required=False
    )
    payment_screenshot = serializers.ImageField(write_only=True, required=False)
    payment_transaction_id = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=100
    )
    latest_payment = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "id",
            "customer",
            "customer_name",
            "status",
            "status_display",
            "frequency",
            "frequency_display",
            "custom_days",
            "start_date",
            "end_date",
            "is_paused",
            "pause_start",
            "pause_end",
            "pause_updated_by",
            "pause_updated_by_name",
            "delivery_address",
            "special_instructions",
            "payment_amount",
            "payment_screenshot",
            "payment_transaction_id",
            "latest_payment",
            "items",
        ]
        read_only_fields = ["id", "pause_updated_by"]

    def get_pause_updated_by_name(self, obj):
        if obj.pause_updated_by:
            return obj.pause_updated_by.get_full_name() or obj.pause_updated_by.username
        return None

    def get_latest_payment(self, obj):
        payment = obj.online_payments.order_by("-created_at").first()
        if not payment:
            return None
        request = self.context.get("request")
        screenshot = payment.screenshot.url if payment.screenshot else None
        if screenshot and request:
            screenshot = request.build_absolute_uri(screenshot)
        return {
            "id": str(payment.id),
            "amount": float(payment.amount),
            "status": payment.status,
            "screenshot": screenshot,
            "created_at": payment.created_at,
        }

    def validate(self, attrs):
        has_amount = attrs.get("payment_amount") is not None
        has_screenshot = attrs.get("payment_screenshot") is not None
        if has_screenshot and not has_amount:
            raise serializers.ValidationError(
                {"payment_amount": "Payment amount is required with a payment screenshot."}
            )
        if has_amount and not has_screenshot:
            raise serializers.ValidationError(
                {"payment_screenshot": "A payment screenshot is required with a payment amount."}
            )
        if has_amount and attrs["payment_amount"] <= 0:
            raise serializers.ValidationError(
                {"payment_amount": "Payment amount must be greater than zero."}
            )
        return attrs

    def _record_payment(self, subscription, payment_data):
        if not payment_data.get("payment_screenshot"):
            return
        from finance.models import OnlinePayment, OnlinePaymentPurpose

        request = self.context.get("request")
        OnlinePayment.objects.create(
            customer=subscription.customer,
            subscription=subscription,
            purpose=OnlinePaymentPurpose.SUBSCRIPTION,
            amount=payment_data["payment_amount"],
            screenshot=payment_data["payment_screenshot"],
            transaction_id=payment_data.get("payment_transaction_id", ""),
            submitted_by=request.user if request and request.user.is_authenticated else None,
        )

    @staticmethod
    def _pop_payment_data(validated_data):
        return {
            key: validated_data.pop(key, None)
            for key in ("payment_amount", "payment_screenshot", "payment_transaction_id")
        }

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        payment_data = self._pop_payment_data(validated_data)

        # Check if pause/vacation is set at creation
        request = self.context.get("request")
        if request and request.user:
            if (
                validated_data.get("is_paused")
                or validated_data.get("pause_start")
                or validated_data.get("pause_end")
            ):
                validated_data["pause_updated_by"] = request.user

        subscription = Subscription.objects.create(**validated_data)
        for item_data in items_data:
            SubscriptionItem.objects.create(subscription=subscription, **item_data)
        self._record_payment(subscription, payment_data)
        return subscription

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        payment_data = self._pop_payment_data(validated_data)

        # Check if pause/vacation fields are being modified
        request = self.context.get("request")
        if request and request.user:
            is_paused_changed = (
                "is_paused" in validated_data
                and validated_data["is_paused"] != instance.is_paused
            )
            pause_start_changed = (
                "pause_start" in validated_data
                and validated_data["pause_start"] != instance.pause_start
            )
            pause_end_changed = (
                "pause_end" in validated_data
                and validated_data["pause_end"] != instance.pause_end
            )

            if is_paused_changed or pause_start_changed or pause_end_changed:
                validated_data["pause_updated_by"] = request.user

        instance = super().update(instance, validated_data)

        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                SubscriptionItem.objects.create(subscription=instance, **item_data)

        self._record_payment(instance, payment_data)
        return instance


class SubscriptionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for Subscription list views — no nested items."""
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    frequency_display = serializers.CharField(
        source="get_frequency_display", read_only=True
    )
    item_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "customer",
            "customer_name",
            "status",
            "status_display",
            "frequency",
            "frequency_display",
            "custom_days",
            "start_date",
            "end_date",
            "is_paused",
            "pause_start",
            "pause_end",
            "delivery_address",
            "special_instructions",
            "item_count",
        ]

