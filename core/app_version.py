"""Version comparison helpers for mobile force-update checks."""

from django.core.cache import cache
from packaging.version import InvalidVersion, Version

CACHE_TIMEOUT = 60
CACHE_KEY = "app_version_config:{app}:{platform}"

FORCE_UPDATE = "force_update"
SOFT_UPDATE = "soft_update"
MAINTENANCE = "maintenance"
OK = "ok"


def parse_version(value):
    """Parse '2.3.1' (or '2.3.1+45') into a comparable Version; None if invalid."""
    if not value:
        return None
    try:
        return Version(str(value).strip().split("+")[0])
    except InvalidVersion:
        return None


def get_config(app, platform):
    """Return the active AppVersionConfig for app/platform, cached briefly."""
    from core.models import AppVersionConfig

    app = (app or "").strip().lower()
    platform = (platform or "").strip().lower()
    key = CACHE_KEY.format(app=app, platform=platform)
    cfg = cache.get(key)
    if cfg is None:
        # Cache misses as False too, so unconfigured apps don't hit the DB on every request.
        cfg = (
            AppVersionConfig.objects.filter(
                app=app, platform=platform, is_active=True
            ).first()
            or False
        )
        cache.set(key, cfg, CACHE_TIMEOUT)
    return cfg or None


def clear_cache(app, platform):
    cache.delete(CACHE_KEY.format(app=app, platform=platform))


def evaluate(cfg, version):
    """Return the update status of a client version against a config."""
    if cfg.maintenance_mode:
        return MAINTENANCE
    current = parse_version(version)
    if current is None:
        # Unknown/garbled version: fail open rather than locking users out.
        return OK
    min_v = parse_version(cfg.min_supported_version)
    latest_v = parse_version(cfg.latest_version)
    if min_v and current < min_v:
        return FORCE_UPDATE
    if latest_v and current < latest_v:
        return SOFT_UPDATE
    return OK


def build_payload(cfg, status):
    return {
        "status": status,
        "force_update": status == FORCE_UPDATE,
        "soft_update": status == SOFT_UPDATE,
        "maintenance_mode": status == MAINTENANCE,
        "min_supported_version": cfg.min_supported_version,
        "latest_version": cfg.latest_version,
        "store_url": cfg.store_url,
        "message": (
            cfg.maintenance_message if status == MAINTENANCE else cfg.update_message
        ),
    }
