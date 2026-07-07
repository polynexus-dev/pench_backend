from rest_framework import serializers
from .models import (
    Product,
    RawMaterial,
    Stock,
    Warehouse,
    BottleType,
    CustomerBottleBalance,
    BottleTransaction,
    CustomerProductPrice,
    StockMovement,
)


class WarehouseSerializer(serializers.ModelSerializer):
    drivers = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Warehouse
        fields = ["id", "name", "address", "is_active", "drivers"]

    def get_drivers(self, obj):
        try:
            from django.apps import apps

            Driver = apps.get_model("routing", "Driver")
            drivers = Driver.objects.filter(warehouse=obj).select_related("user")
            return [
                {
                    "id": str(d.id),
                    "name": (
                        (d.user.get_full_name() or d.user.username)
                        if d.user
                        else "Unknown"
                    ),
                    "vehicle_plate": d.vehicle_plate,
                    "phone": d.user.phone if d.user else None,
                }
                for d in drivers
            ]
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Error in WarehouseSerializer.get_drivers: {e}", exc_info=True
            )
            return []


class RawMaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawMaterial
        fields = ["id", "name", "sku", "description", "unit", "is_active"]


class BottleTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BottleType
        fields = ["id", "name", "deposit_amount", "volume_ml", "is_active"]


class ProductSerializer(serializers.ModelSerializer):
    bottle_type_name = serializers.CharField(source="bottle_type.name", read_only=True)
    raw_material_name = serializers.CharField(
        source="raw_material.name", read_only=True
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "sku",
            "description",
            "unit_price",
            "unit",
            "is_active",
            "bottle_type",
            "bottle_type_name",
            "is_returnable",
            "raw_material",
            "raw_material_name",
        ]


class StockSerializer(serializers.ModelSerializer):
    raw_material_name = serializers.CharField(
        source="raw_material.name", read_only=True
    )
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = Stock
        fields = [
            "id",
            "raw_material",
            "raw_material_name",
            "warehouse",
            "warehouse_name",
            "quantity",
            "reorder_level",
        ]


class BottleTransactionSerializer(serializers.ModelSerializer):
    bottle_type_name = serializers.CharField(source="bottle_type.name", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    transaction_type_display = serializers.CharField(
        source="get_transaction_type_display", read_only=True
    )

    class Meta:
        model = BottleTransaction
        fields = [
            "id",
            "bottle_type",
            "bottle_type_name",
            "customer",
            "customer_name",
            "order",
            "transaction_type",
            "transaction_type_display",
            "quantity",
            "notes",
            "recorded_by",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def create(self, validated_data):
        from .services.bottle_service import record_bottle_transaction

        request = self.context.get("request")
        user = request.user if request and not request.user.is_anonymous else None

        customer = validated_data.get("customer")
        order = validated_data.get("order")
        if not customer and order:
            customer = order.customer

        txn = record_bottle_transaction(
            bottle_type=validated_data["bottle_type"],
            quantity=validated_data["quantity"],
            transaction_type=validated_data["transaction_type"],
            customer=customer,
            order=order,
            user=user,
        )

        if validated_data.get("notes"):
            txn.notes = validated_data["notes"]
            txn.save(update_fields=["notes"])

        return txn


class CustomerBottleBalanceSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    bottle_type_name = serializers.CharField(source="bottle_type.name", read_only=True)

    class Meta:
        model = CustomerBottleBalance
        fields = [
            "id",
            "customer",
            "customer_name",
            "bottle_type",
            "bottle_type_name",
            "balance",
            "broken_balance",
        ]


class CustomerProductPriceSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = CustomerProductPrice
        fields = [
            "id",
            "customer",
            "customer_name",
            "product",
            "product_name",
            "custom_price",
        ]


class StockMovementSerializer(serializers.ModelSerializer):
    raw_material_name = serializers.CharField(
        source="raw_material.name", read_only=True
    )
    raw_material_sku = serializers.CharField(source="raw_material.sku", read_only=True)
    raw_material_unit = serializers.CharField(
        source="raw_material.unit", read_only=True
    )
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    recorded_by_name = serializers.CharField(
        source="recorded_by.get_full_name", read_only=True
    )
    movement_type_display = serializers.CharField(
        source="get_movement_type_display", read_only=True
    )

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "warehouse",
            "warehouse_name",
            "raw_material",
            "raw_material_name",
            "raw_material_sku",
            "raw_material_unit",
            "movement_type",
            "movement_type_display",
            "quantity",
            "reference",
            "notes",
            "recorded_by",
            "recorded_by_name",
            "created_at",
        ]
