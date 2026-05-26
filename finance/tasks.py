from celery import shared_task
import datetime
from django_tenants.utils import schema_context
from tenants.models import City
from .services import bulk_generate_monthly_bills


@shared_task
def run_monthly_billing_cycle():
    """
    Scheduled task to run on the 1st of every month.
    Generates bills for the PREVIOUS month.
    """
    today = datetime.date.today()

    # Calculate last month's year and month
    if today.month == 1:
        billing_month = 12
        billing_year = today.year - 1
    else:
        billing_month = today.month - 1
        billing_year = today.year

    cities = City.objects.all()
    results = {}

    for city in cities:
        with schema_context(city.schema_name):
            count = bulk_generate_monthly_bills(billing_year, billing_month)
            results[city.schema_name] = count
            print(
                f"Generated {count} bills for {city.schema_name} (Period: {billing_month}/{billing_year})"
            )

    return results
