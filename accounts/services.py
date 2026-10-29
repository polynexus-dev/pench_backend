import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def revoke_customer_account(user):
    """
    Removes a customer's login after their CRM profile is deleted from the dashboard.

    Users that also hold a staff/ERP/driver role keep their account and only lose
    the customer flag. Everyone else is locked out first (inactive, unusable
    password) and then hard-deleted through the ORM, so on_delete rules on
    LoginAuditLog, PasswordChangeLog, notifications etc. are honoured. If the hard
    delete still fails, the account stays locked rather than silently usable.

    Must run in the tenant context the customer belonged to, so tenant-side
    relations to the user are reachable by the delete collector.

    Returns "kept", "deleted" or "deactivated".
    """
    if user.is_staff or user.is_superuser or user.is_erp_user or user.is_driver:
        user.is_customer = False
        user.save(update_fields=["is_customer"])
        return "kept"

    user.is_active = False
    user.set_unusable_password()
    user.save(update_fields=["is_active", "password"])

    try:
        with transaction.atomic():
            user.delete()
        return "deleted"
    except Exception:
        logger.exception(
            "Hard delete failed for user_id=%s; account left deactivated", user.pk
        )
        return "deactivated"


def sync_default_location_to_customer(location):
    """
    Copies a user's default saved location onto their CRM Customer profile, which
    is what routing, zone assignment and new orders read the delivery point from.
    Saving the customer re-runs zone auto-assignment for the new coordinates.

    No-op for non-default locations and for users without a customer profile.
    Errors are not swallowed: the caller's transaction should roll back rather
    than leave the app showing a default that deliveries don't use.
    """
    user = location.user
    if not location.is_default or not user.is_customer or not user.tenant_schema:
        return False

    from django_tenants.utils import schema_context
    from crm.models import Customer, HAS_GIS

    lat, lng = float(location.latitude), float(location.longitude)
    if HAS_GIS:
        from django.contrib.gis.geos import Point

        point = Point(lng, lat, srid=4326)
    else:
        point = {"latitude": lat, "longitude": lng}

    address = location.address
    if location.landmark:
        address = f"{address}, Landmark: {location.landmark}"

    with schema_context(user.tenant_schema):
        customer = Customer.objects.filter(user=user).first()
        if not customer:
            return False
        customer.location = point
        customer.address = address
        customer.save()
    return True
