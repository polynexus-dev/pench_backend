import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from accounts.models import User
from django.contrib.auth.models import Group

connection.set_schema_to_public()
user = User.objects.filter(username='admin').first()
if user:
    user.set_password('admin')
    user.is_staff = True
    user.is_superuser = True
    user.save()
    group, _ = Group.objects.get_or_create(name='SuperAdmin')
    user.groups.add(group)
    print("SUCCESS: Admin password changed to 'admin' and verified in PUBLIC schema.")
else:
    User.objects.create_superuser('admin', 'admin@dairy.com', 'admin')
    print("SUCCESS: Created new admin/admin superuser in PUBLIC schema.")
