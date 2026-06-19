from django.db import models
from core.models import BaseModel


class SubscriptionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"


class DeliveryFrequency(models.TextChoices):
    DAILY = "daily", "Daily"
    ALTERNATE = "alternate", "Alternate Days"
    WEEKDAYS = "weekdays", "Mon-Fri"
    WEEKENDS = "weekends", "Sat-Sun"
    CUSTOM = "custom", "Custom Days"


class Subscription(BaseModel):
    """
    Core subscription model scoped to a tenant schema.
    """

    customer = models.ForeignKey(
        "crm.Customer", on_delete=models.CASCADE, related_name="subscriptions"
    )
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
    )
    frequency = models.CharField(
        max_length=20,
        choices=DeliveryFrequency.choices,
        default=DeliveryFrequency.DAILY,
    )
    # For CUSTOM frequency: JSON list of integers [0, 2, 4] where 0=Mon
    custom_days = models.JSONField(default=list, blank=True)

    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    # Vacation Mode / Pausing
    is_paused = models.BooleanField(default=False)
    pause_start = models.DateField(null=True, blank=True)
    pause_end = models.DateField(null=True, blank=True)
    pause_updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paused_subscriptions",
    )

    delivery_address = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)

    def __str__(self):
        return f"Subscription #{self.id[:8]} - {self.customer.name}"

    def should_deliver_on(self, target_date):
        """
        Logic to determine if a delivery should occur on a specific date.
        """
        if self.status != SubscriptionStatus.ACTIVE:
            return False

        # 1. Check for Vacation / Pause range first
        if self.pause_start and self.pause_end:
            if self.pause_start <= target_date <= self.pause_end:
                return False

        # 2. Check for "Hard Pause" (is_paused is True but no dates set)
        if self.is_paused and not (self.pause_start and self.pause_end):
            return False

        # Check frequency
        weekday = target_date.weekday()  # 0 = Monday

        if self.frequency == DeliveryFrequency.DAILY:
            return True
        elif self.frequency == DeliveryFrequency.ALTERNATE:
            # Check days from start_date
            delta = (target_date - self.start_date).days
            return delta % 2 == 0
        elif self.frequency == DeliveryFrequency.WEEKDAYS:
            return weekday < 5
        elif self.frequency == DeliveryFrequency.WEEKENDS:
            return weekday >= 5
        elif self.frequency == DeliveryFrequency.CUSTOM:
            return weekday in self.custom_days

        return False


class SubscriptionItem(BaseModel):
    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey("inventory.Product", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"


class SubscriptionSkipDate(BaseModel):
    """Specific dates requested by customer to skip delivery."""

    subscription = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="skip_dates"
    )
    skip_date = models.DateField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        unique_together = ("subscription", "skip_date")


from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Subscription)
def update_customer_trial_on_subscribe(sender, instance, created, **kwargs):
    """
    When a customer subscribes (gets an active or paused subscription),
    set customer.is_new = False and customer.trial_approved = True.
    """
    if instance.customer and instance.status in [SubscriptionStatus.ACTIVE, SubscriptionStatus.PAUSED]:
        customer = instance.customer
        if customer.is_new:
            customer.is_new = False
            customer.trial_approved = True
            customer.save(update_fields=["is_new", "trial_approved"])
