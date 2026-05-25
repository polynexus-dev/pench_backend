from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

class Command(BaseCommand):
    help = 'Initializes default user groups and roles'

    def handle(self, *args, **options):
        groups = {
            'ERP_Admins': {
                'description': 'Full access to all ERP modules',
            },
            'SuperAdmin': {
                'description': 'Unrestricted global access',
            },
            'Inventory_Managers': {
                'description': 'Can manage products and stock',
            },
            'Logistics_Managers': {
                'description': 'Can manage orders and routes',
            },
            'Drivers': {
                'description': 'Access to driver portal APIs',
            },
            'Accountants': {
                'description': 'Access to finance and billing',
            },
            'Customers': {
                'description': 'Standard customer portal access',
            },
            'CRM_Managers': {
                'description': 'Manage customers and leads',
            },
            'HR_Managers': {
                'description': 'Manage employees and payroll',
            }
        }

        for group_name, info in groups.items():
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created group: {group_name}'))
            else:
                self.stdout.write(f'Group already exists: {group_name}')

        self.stdout.write(self.style.SUCCESS('Role initialization complete.'))

        # Sync existing users to their groups
        self.stdout.write('Syncing existing users to groups...')
        from accounts.models import User
        
        users_synced = 0
        for user in User.objects.all():
            changed = False
            if user.is_erp_user or user.is_superuser:
                group = Group.objects.get(name='ERP_Admins')
                if group not in user.groups.all():
                    user.groups.add(group)
                    changed = True
            
            if user.is_driver:
                group = Group.objects.get(name='Drivers')
                if group not in user.groups.all():
                    user.groups.add(group)
                    changed = True
                    
            if user.is_customer:
                group = Group.objects.get(name='Customers')
                if group not in user.groups.all():
                    user.groups.add(group)
                    changed = True
            
            if changed:
                users_synced += 1
        
        self.stdout.write(self.style.SUCCESS(f'Synced {users_synced} users to their respective groups.'))

        # Setup/Update Celery Beat Periodic Tasks in public schema
        self.stdout.write('Checking and setting up Celery Beat periodic tasks...')
        try:
            from django_celery_beat.models import PeriodicTask, CrontabSchedule
            from django.db import connection
            
            # Only set up periodic tasks in the public schema
            if connection.schema_name == 'public':
                # 1. generate_next_day_routes at 9:00 PM daily (Asia/Kolkata timezone)
                schedule_9pm, _ = CrontabSchedule.objects.get_or_create(
                    minute='0',
                    hour='21',
                    day_of_week='*',
                    day_of_month='*',
                    month_of_year='*',
                    timezone='Asia/Kolkata'
                )
                PeriodicTask.objects.update_or_create(
                    task='orders.tasks.generate_next_day_routes',
                    defaults={
                        'name': 'Generate Next Day Routes',
                        'crontab': schedule_9pm,
                        'enabled': True
                    }
                )
                self.stdout.write(self.style.SUCCESS('Successfully configured: Generate Next Day Routes (9:00 PM)'))
                
                # 2. auto_lock_routes_at_6am at 6:00 AM daily (Asia/Kolkata timezone)
                schedule_6am, _ = CrontabSchedule.objects.get_or_create(
                    minute='0',
                    hour='6',
                    day_of_week='*',
                    day_of_month='*',
                    month_of_year='*',
                    timezone='Asia/Kolkata'
                )
                PeriodicTask.objects.update_or_create(
                    task='orders.tasks.auto_lock_routes_at_6am',
                    defaults={
                        'name': 'Auto Lock Routes at 6 AM',
                        'crontab': schedule_6am,
                        'enabled': True
                    }
                )
                self.stdout.write(self.style.SUCCESS('Successfully configured: Auto Lock Routes at 6 AM'))

                # 3. auto_stop_trips_at_12pm at 12:00 PM daily (Asia/Kolkata timezone)
                schedule_12pm, _ = CrontabSchedule.objects.get_or_create(
                    minute='0',
                    hour='12',
                    day_of_week='*',
                    day_of_month='*',
                    month_of_year='*',
                    timezone='Asia/Kolkata'
                )
                PeriodicTask.objects.update_or_create(
                    task='orders.tasks.auto_stop_trips_at_12pm',
                    defaults={
                        'name': 'Auto Stop Trips at 12 PM',
                        'crontab': schedule_12pm,
                        'enabled': True
                    }
                )
                self.stdout.write(self.style.SUCCESS('Successfully configured: Auto Stop Trips at 12 PM'))
            else:
                self.stdout.write('Skipping Celery Beat setup (not in public schema)')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Failed to set up periodic tasks (non-fatal): {e}'))
