import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def optimize_route_task(self, route_id: str):
    """
    Celery task: runs the full route optimization pipeline asynchronously.

    Triggered by POST /api/ems/routes/{id}/optimize/
    Returns 202 Accepted immediately; client polls GET /api/ems/routes/{id}/

    Args:
        route_id: str UUID of the Route to optimize.
    """
    from routing.models import Route
    from routing.services.optimizer import optimize_route

    try:
        route = Route.objects.get(id=route_id)
    except Route.DoesNotExist:
        logger.error("optimize_route_task: Route %s not found.", route_id)
        return

    logger.info("Starting optimization for route %s", route_id)
    success = optimize_route(route)

    if not success:
        logger.warning("Route %s optimization failed. Retrying...", route_id)
        try:
            raise self.retry()
        except self.MaxRetriesExceededError:
            logger.error("Route %s: max retries exceeded.", route_id)


@shared_task
def auto_generate_daily_routes(target_date_str=None):
    """
    Global Celery task that automatically creates and optimizes routes
    for all active zones across all city schemas for the target date.

    Target date defaults to today if not provided.
    """
    import datetime
    from django_tenants.utils import schema_context
    from tenants.models import City

    if target_date_str:
        target_date = datetime.date.fromisoformat(target_date_str)
    else:
        target_date = datetime.date.today()

    cities = City.objects.exclude(schema_name="public")

    results = {}
    for city in cities:
        with schema_context(city.schema_name):
            try:
                stats = generate_city_routes(target_date)
                results[city.schema_name] = stats
            except Exception as e:
                import traceback

                logger.error(
                    f"Error generating routes for {city.schema_name}: {str(e)}\n{traceback.format_exc()}"
                )
                results[city.schema_name] = {"error": str(e)}

    return results


def generate_city_routes(target_date):
    """
    Generates and optimizes routes for a specific city schema and target date.
    """
    from routing.models import Zone
    from orders.models import Order, OrderStatus
    from orders.services import create_optimized_route

    zones = Zone.objects.all()
    created_count = 0
    skipped_count = 0
    errors = {}

    for zone in zones:
        # Fetch pending/confirmed orders for this zone and target date
        orders = Order.objects.filter(
            customer__zone=zone,
            scheduled_delivery_date=target_date,
            status__in=[OrderStatus.PENDING, OrderStatus.CONFIRMED],
        ).exclude(
            customer__is_new=True,
            customer__trial_approved=False
        )

        if not orders.exists():
            skipped_count += 1
            continue

        order_ids = list(orders.values_list("id", flat=True))

        # Get assigned driver
        driver = zone.assigned_driver

        # Create optimized route
        name = f"{zone.name} - {target_date.strftime('%Y-%m-%d')}"
        try:
            route = create_optimized_route(
                name=name, driver=driver, date=target_date, order_ids=order_ids
            )
            created_count += 1
        except Exception as e:
            logger.error(
                f"Failed to generate route for Zone {zone.name} on {target_date}: {str(e)}"
            )
            errors[zone.name] = str(e)

    return {
        "status": "success",
        "created_routes": created_count,
        "skipped_zones": skipped_count,
        "errors": errors,
    }
