import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def provision_city_schema_task(self, city_id: str):
    """
    Celery task to provision a new City's schema asynchronously.

    Runs migrations under the new schema, and then marks the city as is_active = True.
    """
    from tenants.models import City

    try:
        city = City.objects.get(id=city_id)
    except City.DoesNotExist:
        logger.error("provision_city_schema_task: City %s not found.", city_id)
        return

    logger.info(
        "Starting background schema provisioning for City: %s (%s)",
        city.name,
        city.schema_name,
    )

    try:
        # Create database schema and run all migrations
        city.create_schema(sync_schema=True)

        # Mark city as active once fully migrated
        city.is_active = True
        city.save()

        logger.info(
            "Successfully provisioned schema %s for City %s",
            city.schema_name,
            city.name,
        )
    except Exception as e:
        logger.exception(
            "Error provisioning schema %s for City %s", city.schema_name, city.name
        )
        try:
            # Retry once on failure
            raise self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.error(
                "Max retries exceeded for provisioning City %s schema", city.name
            )
            # Ensure it remains is_active = False so admins know it failed
            city.is_active = False
            city.save()
