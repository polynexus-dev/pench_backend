from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from .models import Customer, Lead, HAS_GIS


try:
    from django.contrib.gis.geos import Point
except ImportError:
    Point = None


class CustomerSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    dashboard = serializers.SerializerMethodField()
    product_rates = serializers.SerializerMethodField()
    zone_name = serializers.CharField(source="zone.name", read_only=True)
    phone = serializers.CharField(
        required=True,
        validators=[UniqueValidator(queryset=Customer.objects.all(), message="A customer with this phone number already exists.")]
    )

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "company",
            "email",
            "phone",
            "address",
            "latitude",
            "longitude",
            "notes",
            "is_active",
            "is_new",
            "trial_approved",
            "qr_code_id",
            "created_at",
            "dashboard",
            "product_rates",
            "zone",
            "zone_name",
        ]
        read_only_fields = ["id", "qr_code_id", "created_at"]

    def get_dashboard(self, obj):
        """Aggregates metrics for the customer within the current schema."""
        from subscriptions.models import Subscription, SubscriptionStatus
        from finance.models import MonthlyBill, BillStatus
        from orders.models import Order

        # 1. Active Subscriptions
        if hasattr(obj, "_prefetched_objects_cache") and "subscriptions" in obj._prefetched_objects_cache:
            active_subs = sum(1 for s in obj.subscriptions.all() if s.status == SubscriptionStatus.ACTIVE)
        else:
            active_subs = Subscription.objects.filter(
                customer=obj, status=SubscriptionStatus.ACTIVE
            ).count()

        # 2. Pending Balance
        if hasattr(obj, "_prefetched_objects_cache") and "monthly_bills" in obj._prefetched_objects_cache:
            total_pending = sum(
                (bill.total_amount - bill.amount_paid) 
                for bill in obj.monthly_bills.all() 
                if bill.status != BillStatus.CANCELLED
            )
        else:
            bills = MonthlyBill.objects.filter(customer=obj).exclude(
                status=BillStatus.CANCELLED
            )
            total_pending = sum((bill.total_amount - bill.amount_paid) for bill in bills)

        # 3. Total Orders
        if hasattr(obj, "_prefetched_objects_cache") and "orders" in obj._prefetched_objects_cache:
            total_orders = len(obj.orders.all())
        else:
            total_orders = Order.objects.filter(customer=obj).count()

        return {
            "active_subscriptions": active_subs,
            "pending_balance": float(total_pending),
            "total_orders": total_orders,
        }

    def get_product_rates(self, obj):
        """Returns the MRP, discount, and final price for all active products for this customer."""
        from inventory.models import Product, CustomerProductPrice

        # Cache active products in context to avoid N+1 query
        if 'active_products' not in self.context:
            self.context['active_products'] = list(Product.objects.filter(is_active=True))
        products = self.context['active_products']

        if hasattr(obj, "_prefetched_objects_cache") and "custom_prices" in obj._prefetched_objects_cache:
            custom_prices = {
                cp.product_id: cp
                for cp in obj.custom_prices.all()
            }
        else:
            custom_prices = {
                cp.product_id: cp
                for cp in CustomerProductPrice.objects.filter(customer=obj)
            }

        rates = []
        for p in products:
            cp = custom_prices.get(p.id)
            discount = cp.discount if cp else 0.00
            final_amount = cp.custom_price if cp else p.unit_price

            rates.append(
                {
                    "product_id": p.id,
                    "product_name": p.name,
                    "mrp": float(p.unit_price),
                    "discount": float(discount),
                    "final_amount": float(final_amount),
                }
            )
        return rates

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        loc = instance.location

        # Default to None
        ret["latitude"] = None
        ret["longitude"] = None

        if loc:
            # Case 1: GEOS Point object
            if hasattr(loc, "x") and hasattr(loc, "y"):
                ret["latitude"] = loc.y
                ret["longitude"] = loc.x
            # Case 2: Dictionary (JSONField fallback)
            elif isinstance(loc, dict):
                ret["latitude"] = loc.get("latitude") or loc.get("lat")
                ret["longitude"] = loc.get("longitude") or loc.get("lng")
            # Case 3: String (likely WKT or EWKB hex)
            elif isinstance(loc, str) and Point:
                try:
                    # Try to parse WKT string if possible
                    p = Point.from_ewkt(loc) if "SRID" in loc else Point(loc)
                    ret["latitude"] = p.y
                    ret["longitude"] = p.x
                except Exception:
                    pass

        return ret

    def create(self, validated_data):
        # Support multiple field name variations for input
        lat = validated_data.pop("latitude", None)
        lng = validated_data.pop("longitude", None)

        # Check initial_data or request for 'lat'/'lng' aliases if not in validated_data
        if lat is None:
            if hasattr(self, "initial_data") and isinstance(self.initial_data, dict):
                lat = self.initial_data.get("lat")
            if lat is None and hasattr(self, "context") and self.context.get("request"):
                req_data = self.context["request"].data
                if isinstance(req_data, dict):
                    lat = req_data.get("lat")

        if lng is None:
            if hasattr(self, "initial_data") and isinstance(self.initial_data, dict):
                lng = self.initial_data.get("lng")
            if lng is None and hasattr(self, "context") and self.context.get("request"):
                req_data = self.context["request"].data
                if isinstance(req_data, dict):
                    lng = req_data.get("lng")

        if lat is not None and lng is not None:
            if HAS_GIS and Point:
                try:
                    validated_data["location"] = Point(float(lng), float(lat))
                except (ValueError, TypeError):
                    pass
            else:
                validated_data["location"] = {"lat": float(lat), "lng": float(lng)}

        instance = super().create(validated_data)

        # Update custom prices if product_rates is provided
        product_rates_data = None
        if hasattr(self, "initial_data") and isinstance(self.initial_data, dict) and "product_rates" in self.initial_data:
            product_rates_data = self.initial_data.get("product_rates")
        else:
            request = self.context.get("request")
            if request and isinstance(request.data, dict) and "product_rates" in request.data:
                product_rates_data = request.data.get("product_rates")

        if product_rates_data and isinstance(product_rates_data, list):
            from inventory.models import CustomerProductPrice, Product

            for rate_data in product_rates_data:
                prod_id = rate_data.get("product_id")
                discount = rate_data.get("discount", 0.00)
                final_amount = rate_data.get("final_amount")

                try:
                    product = Product.objects.get(id=prod_id)
                except Product.DoesNotExist:
                    continue

                discount = float(discount) if discount is not None else 0.00
                if final_amount is not None:
                    final_amount = float(final_amount)
                    discount = float(product.unit_price) - final_amount
                else:
                    final_amount = float(product.unit_price) - discount

                if discount > 0:
                    CustomerProductPrice.objects.update_or_create(
                        customer=instance,
                        product=product,
                        defaults={"discount": discount, "custom_price": final_amount},
                    )
        return instance

    def update(self, instance, validated_data):
        lat = validated_data.pop("latitude", None)
        lng = validated_data.pop("longitude", None)

        if lat is None:
            if hasattr(self, "initial_data") and isinstance(self.initial_data, dict):
                lat = self.initial_data.get("lat")
            if lat is None and hasattr(self, "context") and self.context.get("request"):
                req_data = self.context["request"].data
                if isinstance(req_data, dict):
                    lat = req_data.get("lat")

        if lng is None:
            if hasattr(self, "initial_data") and isinstance(self.initial_data, dict):
                lng = self.initial_data.get("lng")
            if lng is None and hasattr(self, "context") and self.context.get("request"):
                req_data = self.context["request"].data
                if isinstance(req_data, dict):
                    lng = req_data.get("lng")

        if lat is not None and lng is not None:
            if HAS_GIS and Point:
                try:
                    instance.location = Point(float(lng), float(lat))
                except (ValueError, TypeError):
                    pass
            else:
                instance.location = {"lat": float(lat), "lng": float(lng)}

        updated_instance = super().update(instance, validated_data)

        # Update custom prices if product_rates is provided
        product_rates_data = None
        if hasattr(self, "initial_data") and isinstance(self.initial_data, dict) and "product_rates" in self.initial_data:
            product_rates_data = self.initial_data.get("product_rates")
        else:
            request = self.context.get("request")
            if request and isinstance(request.data, dict) and "product_rates" in request.data:
                product_rates_data = request.data.get("product_rates")

        if product_rates_data and isinstance(product_rates_data, list):
            from inventory.models import CustomerProductPrice, Product

            for rate_data in product_rates_data:
                prod_id = rate_data.get("product_id")
                discount = rate_data.get("discount", 0.00)
                final_amount = rate_data.get("final_amount")

                try:
                    product = Product.objects.get(id=prod_id)
                except Product.DoesNotExist:
                    continue

                discount = float(discount) if discount is not None else 0.00
                if final_amount is not None:
                    final_amount = float(final_amount)
                    discount = float(product.unit_price) - final_amount
                else:
                    final_amount = float(product.unit_price) - discount

                if discount <= 0:
                    CustomerProductPrice.objects.filter(
                        customer=updated_instance, product=product
                    ).delete()
                else:
                    CustomerProductPrice.objects.update_or_create(
                        customer=updated_instance,
                        product=product,
                        defaults={"discount": discount, "custom_price": final_amount},
                    )
        return updated_instance


class LeadSerializer(serializers.ModelSerializer):
    referred_by_name = serializers.CharField(source="referred_by.name", read_only=True)

    class Meta:
        model = Lead
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "referred_by",
            "referred_by_name",
            "notes",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
