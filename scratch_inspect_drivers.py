import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

print("All Drivers:")
for u in User.objects.filter(is_driver=True):
    print(f"Username: {u.username}, Phone: {u.phone}, Schema: {u.tenant_schema}")
