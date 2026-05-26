from django.db import models
from core.models import BaseModel


class AdminConfiguration(BaseModel):
    """
    Singleton model for tenant-specific configuration.
    """
    # Delivery Settings
    enable_delivery_photo = models.BooleanField(
        default=False,
        help_text="If enabled, drivers must upload a photo to mark an order as delivered."
    )
    require_signature = models.BooleanField(
        default=False,
        help_text="If enabled, drivers must collect a signature on delivery."
    )
    
    # Returnable Containers Settings
    charge_bottle_penalty = models.BooleanField(
        default=False,
        help_text="Enable penalty charges for lost or broken empty bottles."
    )
    bottle_penalty_amount = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0.00,
        help_text="Default penalty charge per lost or broken bottle."
    )
    
    # Order Settings
    auto_assign_orders = models.BooleanField(
        default=True,
        help_text="Enable automatic order assignment to available drivers."
    )
    max_cancellation_time = models.PositiveIntegerField(
        default=30,
        help_text="Maximum time (in minutes) after which an order cannot be cancelled by the customer."
    )
    
    # Communication
    support_contact_number = models.CharField(max_length=20, blank=True)
    support_email = models.EmailField(blank=True)
    
    # Bottle Penalty Settings
    charge_bottle_penalty = models.BooleanField(
        default=False,
        help_text="If enabled, broken/lost bottles are tracked and penalty billing is applied during reconciliation."
    )
    bottle_penalty_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Penalty charge per broken/lost bottle (in ₹)."
    )

    # UI/UX
    company_name = models.CharField(max_length=100, blank=True)
    theme_color = models.CharField(
        max_length=7, 
        default="#007bff", 
        help_text="Hex code for the primary theme color."
    )

    class Meta:
        verbose_name = "Admin Configuration"
        verbose_name_plural = "Admin Configuration"

    def __str__(self):
        return f"Configuration for {self.company_name or 'Tenant'}"

    @classmethod
    def get_solo(cls):
        """Returns the singleton instance, creating it if it doesn't exist."""
        obj, created = cls.objects.get_or_create()
        return obj


from accounts.models import User

class AdminUserProxy(User):
    """
    A proxy for managing users from the administration app.
    This is just to group user management under the Admin Configuration module.
    """
    class Meta:
        proxy = True
        verbose_name = "User Management"
        verbose_name_plural = "User Management"
