from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0008_customer_crm_custome_name_0c497a_idx_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='assigned_driver',
            field=models.ForeignKey(
                blank=True,
                help_text="Dedicated driver for this customer. Overrides the zone's driver; the zone stays unchanged.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='dedicated_customers',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
