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
                    lat = getattr(instance, 'latitude', None)
                    lon = getattr(instance, 'longitude', None)
                    location = None
                    
                    if lat is not None and lon is not None:
                        from django.conf import settings
                        if getattr(settings, 'HAS_GDAL', False):
                            from django.contrib.gis.geos import Point
                            location = Point(float(lon), float(lat))
                        else:
                            location = {"latitude": float(lat), "longitude": float(lon)}

                    Customer.objects.create(
                        user=instance,
                        name=f"{instance.first_name} {instance.last_name}".strip() or instance.username,
                        company=getattr(instance, 'company', "") or "",
                        email=instance.email or f"{instance.username}_{instance.id}@penchfoods.in",
                        phone=getattr(instance, 'phone', "") or "",
                        address=getattr(instance, 'address', "") or "",
                        notes=getattr(instance, 'notes', "") or "",
                        location=location
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

        # 3. Handle HR Employee Auto-Creation (For both Staff and Drivers)
        if (instance.is_erp_user or instance.is_driver) and hasattr(instance, 'tenant_schema') and instance.tenant_schema and instance.tenant_schema != 'public':
            from hr.models import Employee
            import datetime
            with schema_context(instance.tenant_schema):
                if not Employee.objects.filter(user=instance).exists():
                    job_title = "Driver" if instance.is_driver else "Staff"
                    Employee.objects.create(
                        user=instance,
                        job_title=job_title,
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
