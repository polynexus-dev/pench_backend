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
        token_key = None

        # 1. Try to get token from Sec-WebSocket-Protocol header (highly secure)
        headers = dict(scope.get("headers", []))
        sec_protocol = headers.get(b"sec-websocket-protocol", b"").decode()
        if sec_protocol:
            protocols = [p.strip() for p in sec_protocol.split(",")]
            for i, p in enumerate(protocols):
                if p == "access_token" and i + 1 < len(protocols):
                    token_key = protocols[i + 1]
                    break
                elif p.startswith("Bearer-") or p.startswith("Bearer_"):
                    token_key = p.split("-", 1)[1] if "-" in p else p.split("_", 1)[1]
                    break

        # 2. Fallback to query string parameter
        if not token_key:
            query_string = scope.get("query_string", b"").decode()
            query_params = dict(
                x.split("=") for x in query_string.split("&") if "=" in x
            )
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

        # Extract tenant subdomain from query string if present
        query_string = scope.get("query_string", b"").decode()
        query_params = dict(
            x.split("=") for x in query_string.split("&") if "=" in x
        )
        x_tenant = query_params.get("tenant")

        if x_tenant:
            x_tenant_clean = x_tenant.replace("_", "-")
            host = f"{x_tenant_clean}.localhost"
            print(f"[WS Tenant Override] Spoofed Host to: {host}")
        else:
            # Fallback to x-tenant header if present
            x_tenant_header = headers.get(b"x-tenant", b"").decode()
            if x_tenant_header:
                x_tenant_header_clean = x_tenant_header.replace("_", "-")
                host = f"{x_tenant_header_clean}.localhost"
                print(f"[WS Tenant Header Override] Spoofed Host to: {host}")

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
            domain = Domain.objects.select_related("tenant").get(domain=host)
            return domain.tenant
        except Exception:
            return None

    @database_sync_to_async
    def set_schema(self, schema_name):
        connection.set_schema(schema_name)


class LocalDomainAutoRegisterMiddleware:
    """
    Middleware that automatically registers hostnames in the Tenant Domain table
    if they do not exist but a corresponding tenant schema exists.
    Acts as an on-the-fly self-healing router across staging/dev environments.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from tenants.models import City, Domain
        from django.db import connection
        from django.conf import settings

        # Check for custom X-Tenant header to spoof the host for django-tenants
        x_tenant = request.headers.get("X-Tenant")
        if x_tenant:
            # Replace underscores with hyphens to satisfy RFC 1034/1035 constraints (no underscores in domains)
            x_tenant_clean = x_tenant.replace("_", "-")
            port_suffix = ""
            host_header = request.META.get("HTTP_HOST", "")
            if ":" in host_header:
                port_suffix = ":" + host_header.split(":")[1]
            spoofed_host = f"{x_tenant_clean}.localhost{port_suffix}"
            request.META["HTTP_HOST"] = spoofed_host
            print(f"[X-Tenant Override] Spoofed HTTP_HOST to: {spoofed_host}")

        host = request.get_host().split(":")[0]

        # Only allow auto-registration in local or development host environments
        is_local = (
            settings.DEBUG
            or host == "localhost"
            or host == "127.0.0.1"
            or host.endswith(".nip.io")
            or host.endswith(".localhost")
        )
        if not is_local:
            return self.get_response(request)

        # Check if the host is a raw IPv4 address
        is_ip = False
        parts = host.split(".")
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            is_ip = True

        # 1. On-the-fly self-healing for city subdomains (skip for raw IP hosts)
        if host and not is_ip and not Domain.objects.filter(domain=host).exists():
            parts = host.split(".")
            if len(parts) > 1:
                subdomain_candidate = parts[0]
                # Replace hyphens back to underscores to match schema conventions
                schema_name_candidate = subdomain_candidate.replace("-", "_")

                try:
                    # Query for a matching City tenant
                    city = City.objects.filter(
                        schema_name=schema_name_candidate
                    ).first()
                    if not city:
                        # Try exact match as fallback
                        city = City.objects.filter(
                            schema_name=subdomain_candidate
                        ).first()

                    if city:
                        Domain.objects.create(
                            domain=host, tenant=city, is_primary=False
                        )
                        print(
                            f"[Self-Healing Auto-Register] Dynamically registered city domain: {host} for schema {city.schema_name}"
                        )
                except Exception as e:
                    print(
                        f"[Self-Healing Auto-Register Error] Failed to auto-register subdomain {host}: {e}"
                    )
                    pass

        # 2. Base IP/Domain logic: Only auto-register the primary entry points to Public
        # Don't auto-register subdomains (which belong to cities), unless it's a raw IP address
        is_potential_subdomain = False if is_ip else (host.count(".") > (4 if "nip.io" in host else 1))

        if (
            host
            and not is_potential_subdomain
            and not Domain.objects.filter(domain=host).exists()
        ):
            try:
                public_tenant = City.objects.get(schema_name="public")
                Domain.objects.create(
                    domain=host, tenant=public_tenant, is_primary=False
                )
                print(
                    f"[Auto-Register] Automatically registered public host domain: {host}"
                )
            except Exception as e:
                pass

        return self.get_response(request)


import json
from rest_framework_simplejwt.tokens import AccessToken
from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin


class TokenExpiryMiddleware(MiddlewareMixin):
    """
    Middleware that adds 'X-Token-Expires-In' header to every response
    if a valid JWT token is used. Removes JSON body mutation to eliminate
    CPU overhead and response corruption risks.
    """

    def process_response(self, request, response):
        if response is None:
            return response

        # Only process if user is authenticated via JWT
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                token_str = auth_header.split(" ")[1]
                token = AccessToken(token_str)

                exp_timestamp = token.get("exp")
                if exp_timestamp:
                    remaining = exp_timestamp - timezone.now().timestamp()

                    # Add to header
                    response["X-Token-Expires-In"] = str(int(max(0, remaining)))
            except Exception:
                pass

        return response
