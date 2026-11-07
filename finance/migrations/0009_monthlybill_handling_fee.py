from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0008_onlinepayment_payu_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="monthlybill",
            name="handling_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=0.0,
                help_text="Packing and handling charges applied to the monthly bill based on slab.",
                max_digits=10,
            ),
        ),
    ]

