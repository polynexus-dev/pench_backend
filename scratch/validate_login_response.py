import os
import django
import sys
from unittest.mock import patch

sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from accounts.serializers import MyTokenObtainPairSerializer

class FakeRequest:
    def __init__(self, host, secure=False):
        self.host = host
        self.secure = secure
        
    def get_host(self):
        return self.host
        
    def is_secure(self):
        return self.secure

print("=== VERIFYING LOGIN RESPONSE FULL DOMAIN IN domain_name ===")

User = get_user_model()
user = User.objects.filter(is_superuser=True).first()
if not user:
    user = User.objects.first()

if not user:
    print("No user found in database to test with!")
    sys.exit(1)

# Monkeypatch TokenObtainPairSerializer.validate
def fake_validate(self, attrs):
    return {'access': 'dummy_token', 'refresh': 'dummy_refresh'}

TokenObtainPairSerializer.validate = fake_validate

# 1. Test standard HTTP on custom port (localhost:8888)
print("\nTesting request from localhost:8888 (HTTP)...")
serializer = MyTokenObtainPairSerializer(context={'request': FakeRequest('localhost:8888', secure=False)})
serializer.user = user

try:
    data = serializer.validate({'username': user.username, 'password': 'dummy'})
    print(f"Resulting domain_name: {data.get('domain_name')}")
    print(f"Contains 'full_domain' key: {'full_domain' in data}")
    expected_val = "http://localhost:8888"
    if data.get('domain_name') == expected_val and 'full_domain' not in data:
         print("[SUCCESS] domain_name correctly matched http://localhost:8888 directly!")
    else:
         print(f"[FAILED] domain_name mismatch! Expected '{expected_val}', got '{data.get('domain_name')}'")
except Exception as e:
    print(f"Error during validation: {e}")

# 2. Test HTTPS on standard port (pench.api.polynexus.in)
print("\nTesting request from pench.api.polynexus.in (HTTPS)...")
serializer = MyTokenObtainPairSerializer(context={'request': FakeRequest('pench.api.polynexus.in', secure=True)})
serializer.user = user

try:
    data = serializer.validate({'username': user.username, 'password': 'dummy'})
    print(f"Resulting domain_name: {data.get('domain_name')}")
    print(f"Contains 'full_domain' key: {'full_domain' in data}")
    expected_val = "https://pench.api.polynexus.in"
    if data.get('domain_name') == expected_val and 'full_domain' not in data:
         print("[SUCCESS] domain_name correctly matched https://pench.api.polynexus.in directly!")
    else:
         print(f"[FAILED] domain_name mismatch! Expected '{expected_val}', got '{data.get('domain_name')}'")
except Exception as e:
    print(f"Error during validation: {e}")

print("\n=== VERIFICATION COMPLETED ===")
