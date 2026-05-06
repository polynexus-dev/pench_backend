from django.db import models
from django.contrib.gis.db import models as gis_models
from core.models import BaseModel


class OrderStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    CONFIRMED = 'confirmed', 'Confirmed'
    DISPATCHED = 'dispatched', 'Dispatched'
    IN_TRANSIT = 'in_transit', 'In Transit'
    DELIVERED = 'delivered', 'Delivered'
    CANCELLED = 'cancelled', 'Cancelled'


class Order(BaseModel):
    customer = models.ForeignKey(
        'crm.Customer',
        on_delete=models.PROTECT,
        related_name='orders'
    )
    subscription = models.ForeignKey(
        'subscriptions.Subscription',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_orders'
    )
    scheduled_delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING
    )
    delivery_address = models.TextField()
    delivery_notes = models.TextField(blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Order #{self.id} — {self.customer.name}'


class OrderItem(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(
        'inventory.Product',
        on_delete=models.PROTECT,
        related_name='order_items'
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class Package(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='packages')
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    length_cm = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    width_cm = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    height_cm = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    description = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f'Package for Order #{self.order_id}'


class Route(BaseModel):
    """
    Represents a planned delivery run for a specific day and driver.
    """
    name = models.CharField(max_length=200)
    driver = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='routes'
    )
    delivery_date = models.DateField()
    is_completed = models.BooleanField(default=False)
    
    total_distance_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    estimated_time_minutes = models.PositiveIntegerField(default=0)
    
    # GIS: Store the actual road path (LineString)
    geometry = gis_models.LineStringField(srid=4326, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.delivery_date})"


class RouteStop(BaseModel):
    """
    A specific stop in a Route, linking to an Order.
    """
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='stops')
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='route_stop')
    sequence_number = models.PositiveIntegerField()

    class Meta:
        ordering = ['sequence_number']
        unique_together = ('route', 'sequence_number')

    def __str__(self):
        return f"Stop {self.sequence_number}: {self.order.customer.name}"
