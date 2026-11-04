from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0018_order_payment_status_verification_pending'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['scheduled_delivery_date', '-created_at'], name='order_sched_date_created_idx'),
        ),
    ]
