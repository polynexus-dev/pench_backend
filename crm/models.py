import uuid
from django.db import models
from django.conf import settings
from core.models import BaseModel

try:
    from django.contrib.gis.db import models as gis_models
    HAS_GIS = getattr(settings, 'HAS_GDAL', False)
except Exception:
    HAS_GIS = False

class Customer(BaseModel):
    """CRM customer — Scoped to schema."""
    name = models.CharField(max_length=200)
    user = models.OneToOneField(
        'accounts.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='customer_profile'
    )
    company = models.CharField(max_length=200, blank=True)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    # Conditional GIS field
    if HAS_GIS:
        location = gis_models.PointField(
            srid=4326,
            null=True,
            blank=True,
            help_text='Customer geolocation (longitude, latitude).'
        )
    else:
        location = models.JSONField(null=True, blank=True, help_text='GIS Disabled: Falling back to JSON.')

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    zone = models.ForeignKey(
        'routing.Zone',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customers'
    )
    qr_code_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    def save(self, *args, **kwargs):
        if not self.qr_code_id:
            self.qr_code_id = uuid.uuid4()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['name']
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'

    def __str__(self):
        return f'{self.name} ({self.company or self.email})'

class Lead(BaseModel):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    referred_by = models.ForeignKey(
        Customer, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='referrals'
    )
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, default='new')

    def __str__(self):
        return f'Lead: {self.name} (Ref: {self.referred_by.name if self.referred_by else "None"})'

# --- HELPERS ---
def _parse_coordinates(loc):
    """
    Tries to extract (lng, lat) from various formats.
    """
    if not loc:
        return None
    try:
        # If it's a Point object (from GIS)
        if hasattr(loc, 'x') and hasattr(loc, 'y'):
            return float(loc.x), float(loc.y)
        # If it's a dict
        if isinstance(loc, dict):
            lat = loc.get('latitude') or loc.get('lat')
            lng = loc.get('longitude') or loc.get('lng')
            if lat is not None and lng is not None:
                return float(lng), float(lat)
        # If it's a list/tuple of [lng, lat]
        if isinstance(loc, (list, tuple)) and len(loc) == 2:
            return float(loc[0]), float(loc[1])
        # If it's a string representation of JSON
        if isinstance(loc, str):
            import json
            data = json.loads(loc)
            return _parse_coordinates(data)
    except Exception:
        pass
    return None


def _point_in_polygon(x, y, polygon_coords):
    """
    Ray-casting algorithm to determine if a point (x=lng, y=lat) is inside a polygon.
    polygon_coords: list of rings, where the first ring is the exterior boundary.
    e.g. [[[x1, y1], [x2, y2], ...]]
    """
    if not polygon_coords or not isinstance(polygon_coords, list):
        return False
    # Use exterior ring
    coords = polygon_coords[0]
    if not isinstance(coords, list) or len(coords) < 3:
        return False
        
    num = len(coords)
    j = num - 1
    c = False
    for i in range(num):
        try:
            p_i = coords[i]
            p_j = coords[j]
            xi, yi = float(p_i[0]), float(p_i[1])
            xj, yj = float(p_j[0]), float(p_j[1])
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-9) + xi):
                c = not c
        except (IndexError, TypeError, ValueError, ZeroDivisionError):
            pass
        j = i
    return c


# --- SIGNALS ---
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

@receiver(post_save, sender=Customer)
def sync_customer_user_role(sender, instance, created, **kwargs):
    from django.db import connection
    from accounts.models import User
    
    current_schema = connection.schema_name
    
    # Auto-create or link User if missing
    if not instance.user and (instance.phone or instance.email):
        user = None
        if instance.phone:
            user = User.objects.filter(phone=instance.phone).first()
        if not user and instance.email:
            user = User.objects.filter(email=instance.email).first()
            
        if not user:
            # We need to create one
            username = instance.phone if instance.phone else instance.email
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}_{counter}"
                counter += 1
                
            user = User.objects.create(
                username=username,
                phone=instance.phone if instance.phone else None,
                email=instance.email,
                is_customer=True,
                tenant_schema=current_schema,
                first_name=instance.name.split()[0] if instance.name else '',
                last_name=' '.join(instance.name.split()[1:]) if instance.name and len(instance.name.split()) > 1 else ''
            )
            user.set_unusable_password()
            user.save(update_fields=['password'])
            
        Customer.objects.filter(id=instance.id).update(user=user)
        instance.user = user

    if instance.user:
        changed = False
        if not instance.user.is_customer:
            instance.user.is_customer = True
            changed = True
        if instance.user.tenant_schema != current_schema:
            instance.user.tenant_schema = current_schema
            changed = True
        if changed:
            instance.user.save(update_fields=['is_customer', 'tenant_schema'])


@receiver(pre_save, sender=Customer)
def auto_assign_customer_zone(sender, instance, **kwargs):
    """
    Automatically assign customer to zone based on coordinates when Customer is saved.
    Only recalculates if location has changed or if it's a new instance without a zone.
    """
    is_new = instance._state.adding
    location_changed = False
    zone_changed = False
    
    if not is_new:
        try:
            old_instance = Customer.objects.get(pk=instance.pk)
            old_loc = old_instance.location
            old_zone = old_instance.zone
            
            # Compare locations
            location_changed = (old_loc != instance.location)
            # Compare zones
            zone_changed = (old_zone != instance.zone)
        except Customer.DoesNotExist:
            pass

    should_auto_assign = False
    if is_new:
        if instance.zone is None:
            should_auto_assign = True
    else:
        if location_changed and not zone_changed:
            should_auto_assign = True

    if not should_auto_assign:
        return

    loc = instance.location
    if not loc:
        instance.zone = None
        return

    from routing.models import Zone
    assigned_zone = None
    
    if HAS_GIS:
        from django.contrib.gis.geos import Point
        if not isinstance(loc, Point):
            coords = _parse_coordinates(loc)
            if coords:
                loc = Point(coords[0], coords[1])
            else:
                return
        assigned_zone = Zone.objects.filter(boundary__contains=loc, is_active=True).first()
    else:
        coords = _parse_coordinates(loc)
        if coords:
            lng, lat = coords
            zones = Zone.objects.filter(is_active=True)
            for zone in zones:
                if zone.boundary:
                    poly_coords = None
                    if isinstance(zone.boundary, dict):
                        geom_type = zone.boundary.get('type')
                        if geom_type == 'Polygon':
                            poly_coords = zone.boundary.get('coordinates')
                        elif geom_type == 'MultiPolygon':
                            poly_coords_list = zone.boundary.get('coordinates', [])
                            for sub_poly in poly_coords_list:
                                if _point_in_polygon(lng, lat, sub_poly):
                                    assigned_zone = zone
                                    break
                    if assigned_zone:
                        break
                    if poly_coords and _point_in_polygon(lng, lat, poly_coords):
                        assigned_zone = zone
                        break

    instance.zone = assigned_zone


# Import here to avoid early module loading of Zone which is in TENANT_APPS
from routing.models import Zone

@receiver(post_save, sender=Zone)
def auto_assign_customers_on_zone_change(sender, instance, created, **kwargs):
    """
    Automatically assign active customers to this zone if they fall inside its boundaries
    when a Zone is created or updated.
    """
    if not instance.is_active or not instance.boundary:
        return

    customers = Customer.objects.filter(is_active=True)
    for customer in customers:
        loc = customer.location
        if not loc:
            continue

        is_inside = False
        if HAS_GIS:
            from django.contrib.gis.geos import Point
            if not isinstance(loc, Point):
                coords = _parse_coordinates(loc)
                if coords:
                    loc = Point(coords[0], coords[1])
                else:
                    continue
            is_inside = Zone.objects.filter(id=instance.id, boundary__contains=loc).exists()
        else:
            coords = _parse_coordinates(loc)
            if coords:
                lng, lat = coords
                if isinstance(instance.boundary, dict):
                    geom_type = instance.boundary.get('type')
                    if geom_type == 'Polygon':
                        poly_coords = instance.boundary.get('coordinates')
                        is_inside = _point_in_polygon(lng, lat, poly_coords)
                    elif geom_type == 'MultiPolygon':
                        poly_coords_list = instance.boundary.get('coordinates', [])
                        for sub_poly in poly_coords_list:
                            if _point_in_polygon(lng, lat, sub_poly):
                                is_inside = True
                                break

        if is_inside:
            if customer.zone != instance:
                customer.zone = instance
                customer.save(update_fields=['zone'])

