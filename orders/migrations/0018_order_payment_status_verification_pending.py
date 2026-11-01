from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0017_fractional_quantity'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='payment_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('verification_pending', 'Verification Pending'), ('paid', 'Paid'), ('failed', 'Failed')], default='pending', max_length=20),
        ),
    ]
