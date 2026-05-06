from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_customer_login_support'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='tenant_schema',
            field=models.CharField(blank=True, help_text='The schema name of the tenant this customer belongs to.', max_length=63, null=True),
        ),
    ]
