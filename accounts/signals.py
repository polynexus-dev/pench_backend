from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group
from django_tenants.utils import schema_context
from .models import User

@receiver(post_save, sender=User)
def sync_user_groups(sender, instance, created, **kwargs):
    """
    Automatically assigns users to groups based on their role flags.
    """
    if created:
        # 2. Handle Customer Profile Auto-Creation in Tenant Schema
        if instance.is_customer and hasattr(instance, 'tenant_schema') and instance.tenant_schema and instance.tenant_schema != 'public':
            from crm.models import Customer
            with schema_context(instance.tenant_schema):
                # Ensure we don't create duplicates
                if not Customer.objects.filter(user=instance).exists():
                    Customer.objects.create(
                        user=instance,
                        name=f"{instance.first_name} {instance.last_name}".strip() or instance.username,
                        email=instance.email or f"{instance.username}@placeholder.com",
                        phone=getattr(instance, 'phone', "") or ""
                    )

    # 0. SuperAdmin Group
    if instance.is_superuser:
        group, _ = Group.objects.get_or_create(name='SuperAdmin')
        if group not in instance.groups.all():
            instance.groups.add(group)

    # 1. ERP / Admin Group
    if instance.is_erp_user or instance.is_superuser:
        group, _ = Group.objects.get_or_create(name='ERP_Admins')
        if group not in instance.groups.all():
            instance.groups.add(group)
    
    # 2. Driver Group
    if instance.is_driver:
        group, _ = Group.objects.get_or_create(name='Drivers')
        if group not in instance.groups.all():
            instance.groups.add(group)
            
    # 3. Customer Group
    if instance.is_customer:
        group, _ = Group.objects.get_or_create(name='Customers')
        if group not in instance.groups.all():
            instance.groups.add(group)
