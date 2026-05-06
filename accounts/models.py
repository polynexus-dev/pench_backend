from django.contrib.auth.models import AbstractUser
from django.db import models


class PortalChoice(models.TextChoices):
    DELIVERY = 'delivery', 'Delivery Portal'
    ERP = 'erp', 'ERP Portal'
    BOTH = 'both', 'Both Portals'


class User(AbstractUser):
    """
    Custom user model extending AbstractUser.
    Controls access to ERP vs Delivery portals.
    """
    is_erp_user = models.BooleanField(
        default=False,
        help_text='Grants access to the ERP portal.'
    )
    is_driver = models.BooleanField(
        default=False,
        help_text='Designates this user as a delivery driver.'
    )
    portal = models.CharField(
        max_length=10,
        choices=PortalChoice.choices,
        default=PortalChoice.ERP,
        help_text='Primary portal this user accesses.'
    )
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.email})'

    def save(self, *args, **kwargs):
        # Auto-set portal based on flags
        if self.is_driver and not self.is_erp_user:
            self.portal = PortalChoice.DELIVERY
        elif self.is_erp_user and not self.is_driver:
            self.portal = PortalChoice.ERP
        elif self.is_driver and self.is_erp_user:
            self.portal = PortalChoice.BOTH
        super().save(*args, **kwargs)
