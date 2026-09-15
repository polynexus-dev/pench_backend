from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_alter_loginauditlog_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='AccountDeletionLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deleted_user_id', models.IntegerField(help_text='Primary key of the User row that was deleted.')),
                ('tenant_schema', models.CharField(blank=True, help_text='Tenant the customer belonged to.', max_length=63, null=True)),
                ('reason', models.TextField(blank=True, help_text='Optional reason supplied by the user.')),
                ('outstanding_balance', models.DecimalField(decimal_places=2, default=0, help_text='Unpaid balance at the moment of deletion, for finance follow-up.', max_digits=12)),
                ('customer_anonymized', models.BooleanField(default=False, help_text='True if a linked CRM customer record was found and scrubbed.')),
                ('subscriptions_removed', models.PositiveIntegerField(default=0)),
                ('orders_cancelled', models.PositiveIntegerField(default=0)),
                ('deleted_at', models.DateTimeField(auto_now_add=True)),
                ('ip_address', models.CharField(blank=True, max_length=45, null=True)),
            ],
            options={
                'verbose_name': 'Account Deletion Log',
                'verbose_name_plural': 'Account Deletion Logs',
                'ordering': ['-deleted_at'],
            },
        ),
    ]
