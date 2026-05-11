from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group
from .models import User

@receiver(post_save, sender=User)
def sync_user_groups(sender, instance, created, **kwargs):
    """
    Automatically assigns users to groups based on their role flags.
    """
    # 0. SuperAdmin Group
    if instance.is_superuser:
        group, _ = Group.objects.get_or_create(name='SuperAdmin')
        if group not in instance.groups.all():
            instance.groups.add(group)

    # 1. ERP / Admin Group
    if instance.is_erp_user or instance.is_superuser:
        group, _ = Group.objects.get_or_create(name='ERP_Admins')
        if group not in instance.groups.all():
            instance.groups.add(group)
    
    # 2. Driver Group
    if instance.is_driver:
        group, _ = Group.objects.get_or_create(name='Drivers')
        if group not in instance.groups.all():
            instance.groups.add(group)
            
    # 3. Customer Group
    if instance.is_customer:
        group, _ = Group.objects.get_or_create(name='Customers')
        if group not in instance.groups.all():
            instance.groups.add(group)
