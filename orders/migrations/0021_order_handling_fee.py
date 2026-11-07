from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0020_alter_order_payment_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="handling_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=0.0,
                help_text="Packing and handling charges applied based on order amount slab.",
                max_digits=10,
            ),
        ),
    ]

