from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0019_order_sched_date_created_idx"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("cash", "Cash"),
                    ("upi", "UPI"),
                    ("payu", "PayU"),
                    ("on_account", "On Account (Monthly Bill)"),
                ],
                default="on_account",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("verification_pending", "Verification Pending"),
                    ("partial", "Partially Paid"),
                    ("paid", "Paid"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]

