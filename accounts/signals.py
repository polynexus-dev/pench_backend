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
        # 1. Handle Customer Profile Auto-Creation
        if instance.is_customer and hasattr(instance, 'tenant_schema') and instance.tenant_schema and instance.tenant_schema != 'public':
            from crm.models import Customer
            with schema_context(instance.tenant_schema):
                if not Customer.objects.filter(user=instance).exists():
                    Customer.objects.create(
                        user=instance,
                        name=f"{instance.first_name} {instance.last_name}".strip() or instance.username,
                        email=instance.email or f"{instance.username}@placeholder.com",
                        phone=getattr(instance, 'phone', "") or ""
                    )

        # 2. Handle Driver Profile Auto-Creation
        if instance.is_driver and hasattr(instance, 'tenant_schema') and instance.tenant_schema and instance.tenant_schema != 'public':
            from routing.models import Driver
            with schema_context(instance.tenant_schema):
                if not Driver.objects.filter(user=instance).exists():
                    Driver.objects.create(
                        user=instance,
                        vehicle_plate=f"NEW-{instance.id}", # Placeholder plate
                        vehicle_type="van"
                    )

        # 3. Handle ERP User (Employee) Auto-Creation
        if instance.is_erp_user and hasattr(instance, 'tenant_schema') and instance.tenant_schema and instance.tenant_schema != 'public':
            from hr.models import Employee
            import datetime
            with schema_context(instance.tenant_schema):
                if not Employee.objects.filter(user=instance).exists():
                    Employee.objects.create(
                        user=instance,
                        job_title="Staff",
                        employee_id=f"EMP-{instance.id}-{datetime.date.today().year}",
                        date_joined=datetime.date.today()
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
