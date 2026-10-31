import logging

from celery import shared_task
from django_tenants.utils import schema_context

from core.store_versions import sync_all

logger = logging.getLogger(__name__)


@shared_task(name="core.tasks.sync_store_versions")
def sync_store_versions_task():
    """
    Periodically checks the App Store / Play Store for newly published versions
    and raises AppVersionConfig so outdated mobile builds are forced to update.
    """
    with schema_context("public"):
        results = sync_all()
    logger.info("Store version sync results: %s", results)
    return results
