from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0007_online_payment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="onlinepayment",
            name="screenshot",
            field=models.ImageField(
                blank=True, null=True, upload_to="online_payments/"
            ),
        ),
        migrations.AlterField(
            model_name="onlinepayment",
            name="transaction_id",
            field=models.CharField(
                blank=True,
                help_text="UPI Transaction Ref / UTR / Bank Ref",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="onlinepayment",
            name="payment_gateway",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Gateway identifier (e.g. 'payu') or blank for manual screenshot upload.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="onlinepayment",
            name="gateway_txnid",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Merchant transaction ID (txnid) sent to the payment gateway.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="onlinepayment",
            name="gateway_mihpayid",
            field=models.CharField(
                blank=True,
                default="",
                help_text="PayU payment ID (mihpayid) returned by the gateway.",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="onlinepayment",
            name="gateway_mode",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Payment mode used on gateway (e.g. UPI, CC, DC, NB).",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="onlinepayment",
            name="gateway_raw_response",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Raw callback/webhook payload received from the payment gateway.",
            ),
        ),
    ]

