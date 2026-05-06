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
        logger.error('optimize_route_task: Route %s not found.', route_id)
        return

    logger.info('Starting optimization for route %s', route_id)
    success = optimize_route(route)

    if not success:
        logger.warning('Route %s optimization failed. Retrying...', route_id)
        try:
            raise self.retry()
        except self.MaxRetriesExceededError:
            logger.error('Route %s: max retries exceeded.', route_id)
