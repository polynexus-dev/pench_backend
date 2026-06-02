import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django_tenants.utils import schema_context
from notifications.models import FCMToken
from accounts.models import User
from tenants.models import City

# Select the nagpur tenant
city = City.objects.get(schema_name='pench_nagpur')
print("Tenant schema:", city.schema_name)

with schema_context(city.schema_name):
    # Find a user (any user)
    user = User.objects.first()
    if not user:
        print("No users found in the database.")
        exit(1)
    print("Testing with User:", user.username)

    # 1. Create a dummy token if not exists
    token_str = "dummy_fcm_token_for_testing"
    obj, created = FCMToken.objects.get_or_create(
        token=token_str,
        defaults={'user': user}
    )
    print("Token created?", created, "Token ID:", obj.id, "User ID linked:", obj.user_id)

    # 2. Query tokens for this user
    tokens = list(FCMToken.objects.filter(user=user))
    print("Queried tokens count for user:", len(tokens))
    for t in tokens:
        print("Token value:", t.token)

    # 3. Clean up the dummy token
    if created:
        obj.delete()
        print("Cleaned up dummy token.")
