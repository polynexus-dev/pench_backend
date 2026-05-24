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
            try:
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

                        comp_name = getattr(instance, 'company', "") or ""
                        if not comp_name:
                            from tenants.models import City
                            city = City.objects.filter(schema_name=instance.tenant_schema).select_related('company').first()
                            if city and city.company:
                                comp_name = city.company.name

                        zone_val = getattr(instance, 'zone', None)
                        zone_id = zone_val if zone_val and zone_val != "" else None

                        Customer.objects.create(
                            user=instance,
                            name=f"{instance.first_name} {instance.last_name}".strip() or instance.username,
                            company=comp_name,
                            email=instance.email or f"{instance.username}_{instance.id}@penchfoods.in",
                            phone=getattr(instance, 'phone', "") or "",
                            address=getattr(instance, 'address', "") or "",
                            notes=getattr(instance, 'notes', "") or "",
                            location=location,
                            zone_id=zone_id
                        )
            except Exception:
                pass

        # 2. Handle Driver Profile Auto-Creation
        if instance.is_driver and hasattr(instance, 'tenant_schema') and instance.tenant_schema and instance.tenant_schema != 'public':
            try:
                from routing.models import Driver
                with schema_context(instance.tenant_schema):
                    if not Driver.objects.filter(user=instance).exists():
                        zone_val = getattr(instance, 'zone', None)
                        zone_id = zone_val if zone_val and zone_val != "" else None
                        warehouse_val = getattr(instance, 'warehouse', None)
                        warehouse_id = warehouse_val if warehouse_val and warehouse_val != "" else None
                        Driver.objects.create(
                            user=instance,
                            vehicle_plate=getattr(instance, 'vehicle_plate', None) or f"NEW-{instance.id}",
                            vehicle_type=getattr(instance, 'vehicle_type', None) or "van",
                            max_capacity_kg=getattr(instance, 'max_capacity_kg', None) or 500,
                            zone_id=zone_id,
                            warehouse_id=warehouse_id
                        )
                        if zone_id:
                            from routing.models import Zone
                            Zone.objects.filter(id=zone_id).update(assigned_driver=instance)
            except Exception:
                pass

        # 3. Handle HR Employee Auto-Creation (For both Staff and Drivers)
        if (instance.is_erp_user or instance.is_driver) and hasattr(instance, 'tenant_schema') and instance.tenant_schema and instance.tenant_schema != 'public':
            try:
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
            except Exception:
                pass

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
