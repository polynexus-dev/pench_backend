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
        is_potential_subdomain = False if is_ip else (host.count(".") > (5 if "nip.io" in host else 1))

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


from django.http import JsonResponse
import logging

version_logger = logging.getLogger("core.app_version")


class AppVersionEnforcementMiddleware:
    """
    Safety net for force updates: if a mobile client sends X-App-Name,
    X-App-Platform and X-App-Version headers and its version is below the
    configured minimum, reject with HTTP 426 Upgrade Required (503 during
    maintenance).

    With BLOCK_LEGACY_MOBILE_BUILDS, native mobile requests that lack these
    headers (builds that predate the version check) are also rejected with 426
    and a message the old app shows as its error text. Browser requests (web ERP,
    admin) never match the native user agents and are untouched.
    """

    EXEMPT_PREFIXES = (
        "/api/app-version/",
        "/admin/",
        "/static/",
        "/media/",
        "/privacy-policy/",
        "/delete-account/",
    )
    # React Native networking: OkHttp on Android, CFNetwork/Darwin on iOS
    NATIVE_UA_MARKERS = {"okhttp/": "android", "cfnetwork/": "ios", "darwin/": "ios"}
    LEGACY_MESSAGE = (
        "This version of Pench is no longer supported. Please update the app from "
        "the {store} to continue."
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def _legacy_platform(self, request):
        ua = request.headers.get("User-Agent", "").lower()
        if "mozilla/" in ua:
            return None
        for marker, platform in self.NATIVE_UA_MARKERS.items():
            if marker in ua:
                return platform
        return None

    def _legacy_response(self, platform):
        from core import app_version

        try:
            cfg = app_version.get_config("pench", platform)
        except Exception:
            cfg = None
        store = "Play Store" if platform == "android" else "App Store"
        payload = (
            app_version.build_payload(cfg, app_version.FORCE_UPDATE)
            if cfg
            else {"status": app_version.FORCE_UPDATE, "force_update": True}
        )
        payload["detail"] = payload["message"] = self.LEGACY_MESSAGE.format(store=store)
        return JsonResponse(payload, status=426)

    def __call__(self, request):
        from django.conf import settings
        from core import app_version

        if request.path.startswith(self.EXEMPT_PREFIXES):
            return self.get_response(request)

        app = request.headers.get("X-App-Name")
        platform = request.headers.get("X-App-Platform")
        version = request.headers.get("X-App-Version")

        if not version and getattr(settings, "BLOCK_LEGACY_MOBILE_BUILDS", False):
            legacy_platform = self._legacy_platform(request)
            if legacy_platform:
                version_logger.info(
                    "Blocked legacy %s build (no X-App-Version): %s %s UA=%s",
                    legacy_platform, request.method, request.path,
                    request.headers.get("User-Agent", ""),
                )
                return self._legacy_response(legacy_platform)

        if app and platform and version:
            try:
                cfg = app_version.get_config(app, platform)
            except Exception:
                cfg = None  # fail open on cache/DB errors
            if cfg is not None:
                status = app_version.evaluate(cfg, version)
                if status == app_version.FORCE_UPDATE:
                    version_logger.info(
                        "Force update: %s/%s v%s below min %s: %s %s",
                        app, platform, version, cfg.min_supported_version,
                        request.method, request.path,
                    )
                    payload = app_version.build_payload(cfg, status)
                    payload["detail"] = "App update required."
                    return JsonResponse(payload, status=426)
                if status == app_version.MAINTENANCE:
                    payload = app_version.build_payload(cfg, status)
                    payload["detail"] = "App is under maintenance."
                    return JsonResponse(payload, status=503)

        return self.get_response(request)


class AppVersionWSMiddleware:
    """
    WebSocket counterpart of AppVersionEnforcementMiddleware (Channels bypasses
    Django middleware). Rejects the handshake for mobile builds below the minimum
    version, and for legacy native builds that send no version at all.
    Version is read from the query string (app, platform, version) or X-App-* headers.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "websocket" and await self._should_block(scope):
            # Consume the connect event, then refuse the handshake
            await receive()
            await send({"type": "websocket.close", "code": 4426})
            return
        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def _should_block(self, scope):
        from urllib.parse import parse_qs
        from django.conf import settings
        from core import app_version

        headers = {
            k.decode().lower(): v.decode() for k, v in scope.get("headers", [])
        }
        query = {
            k: v[0] for k, v in parse_qs(scope.get("query_string", b"").decode()).items()
        }
        app = query.get("app") or headers.get("x-app-name")
        platform = query.get("platform") or headers.get("x-app-platform")
        version = query.get("version") or headers.get("x-app-version")

        try:
            if not version:
                if not getattr(settings, "BLOCK_LEGACY_MOBILE_BUILDS", False):
                    return False
                ua = headers.get("user-agent", "").lower()
                if "mozilla/" in ua:
                    return False
                return any(
                    m in ua for m in AppVersionEnforcementMiddleware.NATIVE_UA_MARKERS
                )

            if not app or not platform:
                return False
            cfg = app_version.get_config(app, platform)
            if cfg is None:
                return False
            return app_version.evaluate(cfg, version) in (
                app_version.FORCE_UPDATE,
                app_version.MAINTENANCE,
            )
        except Exception:
            return False  # fail open
