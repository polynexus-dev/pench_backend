from channels.db import database_sync_to_async
from django.db import connection
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from tenants.models import City, Domain

User = get_user_model()


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode()
        query_params = dict(x.split('=') for x in query_string.split('&') if '=' in x)
        token_key = query_params.get("token")

        if token_key:
            scope["user"] = await self.get_user(token_key)
        else:
            scope["user"] = AnonymousUser()

        print(f"[WS Auth] User: {scope['user']}")
        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def get_user(self, token_key):
        try:
            token = AccessToken(token_key)
            user_id = token.get("user_id")
            return User.objects.get(id=user_id)
        except Exception as e:
            print(f"[WS Auth Error] {e}")
            return AnonymousUser()


class TenantMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        host = headers.get(b"host", b"").decode().split(":")[0]
        
        print(f"[WS Tenant] Host Header: {host}")

        tenant = await self.get_tenant(host)
        if tenant:
            print(f"[WS Tenant] Found Tenant: {tenant.schema_name}")
            await self.set_schema(tenant.schema_name)
            scope["tenant"] = tenant
        else:
            print(f"[WS Tenant] NO TENANT FOUND for host: {host}")
        
        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def get_tenant(self, host):
        try:
            domain = Domain.objects.select_related('tenant').get(domain=host)
            return domain.tenant
        except Exception:
            return None

    @database_sync_to_async
    def set_schema(self, schema_name):
        connection.set_schema(schema_name)


class LocalDomainAutoRegisterMiddleware:
    """
    Middleware for local development that automatically registers the current
    hostname in the Public Tenant domains if it doesn't exist.
    Fixes the 'No tenant for hostname' error automatically.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        from tenants.models import City, Domain
        
        # Only run this logic if we are in DEBUG mode (local dev)
        if settings.DEBUG:
            from django.db import connection
            host = request.get_host().split(':')[0]
            print(f"[Debug] Host: {host}, Current Schema: {connection.schema_name}")
            if connection.schema_name == 'public' and '.' in host and not host.endswith('.nip.io') and host != 'localhost':
                 # This might be a city subdomain that failed to switch
                 pass
            
            if connection.schema_name == 'public' and 'nagpur' in host:
                print(f"[Debug] CRITICAL: Nagpur request but schema is PUBLIC! Check Domain table.")
            
            # Base IP/Domain logic: Only auto-register the primary entry points to Public
            # Don't auto-register subdomains (which belong to cities)
            is_potential_subdomain = host.count('.') > (4 if 'nip.io' in host else 1)
            
            if host and not is_potential_subdomain and not Domain.objects.filter(domain=host).exists():
                try:
                    public_tenant = City.objects.get(schema_name='public')
                    Domain.objects.create(
                        domain=host,
                        tenant=public_tenant,
                        is_primary=False
                    )
                    print(f"[Auto-Register] Automatically registered local domain: {host}")
                except Exception as e:
                    pass
        
        return self.get_response(request)

import json
from rest_framework_simplejwt.tokens import AccessToken
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

class TokenExpiryMiddleware(MiddlewareMixin):
    """
    Middleware that adds 'expires_in_seconds' to every JSON response
    if a valid JWT token is used.
    """
    def process_response(self, request, response):
        # Only process if user is authenticated via JWT
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                token_str = auth_header.split(' ')[1]
                token = AccessToken(token_str)
                
                exp_timestamp = token.get('exp')
                if exp_timestamp:
                    remaining = exp_timestamp - timezone.now().timestamp()
                    
                    # Add to header
                    response['X-Token-Expires-In'] = str(int(max(0, remaining)))
                    
                    # If it's a JSON response, inject the field into body
                    content_type = response.get('Content-Type', '')
                    if 'application/json' in content_type:
                        try:
                            # Only try to parse if there is content
                            if response.content:
                                data = json.loads(response.content)
                                if isinstance(data, dict):
                                    data['expires_in_seconds'] = int(max(0, remaining))
                                    response.content = json.dumps(data)
                                    # Reset content-length if modified
                                    if response.has_header('Content-Length'):
                                        response['Content-Length'] = str(len(response.content))
                        except Exception:
                            pass
            except Exception:
                pass
                
        return response
