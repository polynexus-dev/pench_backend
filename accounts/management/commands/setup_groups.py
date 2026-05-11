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
