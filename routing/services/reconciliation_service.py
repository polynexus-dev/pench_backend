import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from routing.models import (
    Route,
    TrackingEvent,
    DailyReconciliation,
    CollectionMethod,
    ReconciliationStatus,
)

logger = logging.getLogger(__name__)


@transaction.atomic
def generate_daily_reconciliation(route_id):
    """
    Aggregates all collections from tracking events for a given route
    and creates a DailyReconciliation record.
    """
    route = Route.objects.get(id=route_id)
    events = TrackingEvent.objects.filter(route=route, status="delivered")

    cash = events.filter(collection_method=CollectionMethod.CASH).aggregate(
        total=Sum("collection_amount")
    )["total"] or Decimal("0.00")
    upi = events.filter(collection_method=CollectionMethod.UPI).aggregate(
        total=Sum("collection_amount")
    )["total"] or Decimal("0.00")
    wallet = events.filter(collection_method=CollectionMethod.WALLET).aggregate(
        total=Sum("collection_amount")
    )["total"] or Decimal("0.00")

    expected = route.orders.aggregate(total=Sum("total"))["total"] or Decimal("0.00")

    reconciliation, created = DailyReconciliation.objects.update_or_create(
        route=route,
        defaults={
            "driver": route.driver,
            "date": route.created_at.date(),
            "total_cash_collected": cash,
            "total_upi_collected": upi,
            "total_wallet_deducted": wallet,
            "expected_total": expected,
            "actual_total": Decimal("0.00"),  # To be filled by supervisor
            "status": ReconciliationStatus.PENDING,
        },
    )

    logger.info(
        f"Generated reconciliation for Route #{route_id}. Expected: ₹{expected}"
    )
    return reconciliation


@transaction.atomic
def reconcile(reconciliation_id, actual_total, user, notes=""):
    """Marks a reconciliation as complete and records discrepancies."""
    recon = DailyReconciliation.objects.get(id=reconciliation_id)

    recon.actual_total = Decimal(str(actual_total))
    recon.discrepancy = recon.actual_total - (
        recon.total_cash_collected + recon.total_upi_collected
    )
    recon.status = (
        ReconciliationStatus.RECONCILED
        if recon.discrepancy == 0
        else ReconciliationStatus.DISPUTED
    )
    recon.reconciled_by = user
    recon.notes = notes
    recon.save()

    logger.info(
        f"Reconciliation {reconciliation_id} completed. Discrepancy: ₹{recon.discrepancy}"
    )
    return recon
