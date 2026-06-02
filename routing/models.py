from django.db import models
from core.models import BaseModel

from django.conf import settings

try:
    from django.contrib.gis.db import models as gis_models

    HAS_GIS = getattr(settings, "HAS_GDAL", False)
except Exception:
    HAS_GIS = False


class RouteStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    OPTIMIZING = "optimizing", "Optimizing"
    OPTIMIZED = "optimized", "Optimized"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class Zone(BaseModel):
    """
    Geographic delivery zone within a city.
    Each zone has a permanent driver assigned to it.
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    assigned_driver = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_zones",
        help_text="The primary driver for this zone.",
    )

    if HAS_GIS:
        boundary = gis_models.PolygonField(srid=4326, null=True, blank=True)
    else:
        boundary = models.JSONField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Zone: {self.name} ({self.assigned_driver.get_full_name() if self.assigned_driver else 'No Driver'})"


class Driver(BaseModel):
    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="driver_profile"
    )
    vehicle_plate = models.CharField(max_length=20)
    vehicle_type = models.CharField(max_length=50, default="van")
    max_capacity_kg = models.DecimalField(max_digits=8, decimal_places=2, default=500)
    is_available = models.BooleanField(default=True)
    on_trip = models.BooleanField(default=False)
    zone = models.ForeignKey(
        Zone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driver_profiles",
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="drivers",
        help_text="The primary warehouse this driver is associated with.",
    )

    def __str__(self):
        return f"Driver: {self.user.get_full_name()} ({self.vehicle_plate})"


class Route(BaseModel):
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="routes")
    additional_drivers = models.ManyToManyField(
        Driver,
        related_name="shared_routes",
        blank=True,
        help_text="Additional drivers assigned to this route in case of emergency.",
    )
    warehouse = models.ForeignKey(
        "inventory.Warehouse",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="routes",
        help_text="The warehouse this route starts and ends at.",
    )
    orders = models.ManyToManyField("orders.Order", related_name="routes", blank=True)
    name = models.CharField(max_length=200, blank=True)
    delivery_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=RouteStatus.choices, default=RouteStatus.PENDING
    )
    is_completed = models.BooleanField(default=False)
    is_test_route = models.BooleanField(
        default=False, help_text="Auto-created dummy route for GPS tracking tests."
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Conditional GIS field
    if HAS_GIS:
        geometry = gis_models.LineStringField(srid=4326, null=True, blank=True)
    else:
        geometry = models.TextField(null=True, blank=True)

    waypoints = models.JSONField(default=list, blank=True)
    optimization_error = models.TextField(blank=True)
    estimated_duration_minutes = models.IntegerField(null=True, blank=True)
    estimated_distance_km = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        label = self.name or f"Route #{str(self.id)[:8]}"
        return f"{label} — {self.driver} [{self.status}]"


class CollectionMethod(models.TextChoices):
    CASH = "cash", "Cash"
    UPI = "upi", "UPI"
    WALLET = "wallet", "Wallet"
    NONE = "none", "None"


class TrackingEvent(BaseModel):
    route = models.ForeignKey(
        Route, on_delete=models.CASCADE, related_name="tracking_events"
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="tracking_events",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=50)

    # Conditional GIS field
    if HAS_GIS:
        location = gis_models.PointField(srid=4326, null=True, blank=True)
    else:
        location = models.JSONField(null=True, blank=True)

    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    photo_proof = models.ImageField(upload_to="delivery_proofs/", null=True, blank=True)
    collection_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    collection_method = models.CharField(
        max_length=20, choices=CollectionMethod.choices, default=CollectionMethod.NONE
    )
    customer_signature = models.ImageField(
        upload_to="delivery_signatures/", null=True, blank=True
    )

    class Meta:
        ordering = ["-timestamp"]


class DailyReconciliation(BaseModel):
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name="reconciliations"
    )
    route = models.OneToOneField(
        Route, on_delete=models.CASCADE, related_name="reconciliation"
    )
    date = models.DateField()
    total_cash_collected = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    total_upi_collected = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    total_wallet_deducted = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    expected_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discrepancy = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20,
        choices=models.TextChoices("Status", "pending reconciled disputed").choices,
        default="pending",
    )
    reconciled_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_reconciliations",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]
