"""
Detects the version currently published on the App Store / Play Store and
raises AppVersionConfig versions so new releases are force-updated automatically.
"""

import logging
import re
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from core.app_version import parse_version

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# Play Store embeds the current version as [[["1.0.5"]] in its page data
PLAY_VERSION_RE = re.compile(r'\[\[\["(\d+(?:\.\d+)+)"\]\]')


class StoreLookupError(Exception):
    pass


def store_url_for(platform, store_app_id):
    if platform == "android":
        return f"https://play.google.com/store/apps/details?id={store_app_id}"
    return f"https://apps.apple.com/app/id{store_app_id}"


def fetch_ios_version(app_store_id):
    country = getattr(settings, "APP_STORE_COUNTRY", "in")
    resp = requests.get(
        "https://itunes.apple.com/lookup",
        params={"id": app_store_id, "country": country, "_": int(timezone.now().timestamp())},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results or not results[0].get("version"):
        raise StoreLookupError(f"App Store returned no version for id {app_store_id}")
    return results[0]["version"]


def fetch_android_version(package_name):
    resp = requests.get(
        "https://play.google.com/store/apps/details",
        params={"id": package_name, "hl": "en", "gl": "IN"},
        headers={"User-Agent": BROWSER_UA},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    versions = {v for v in PLAY_VERSION_RE.findall(resp.text) if parse_version(v)}
    if not versions:
        raise StoreLookupError(f"Could not find a version on the Play Store page for {package_name}")
    return str(max(versions, key=parse_version))


def fetch_store_version(platform, store_app_id):
    if platform == "android":
        return fetch_android_version(store_app_id)
    return fetch_ios_version(store_app_id)


def ensure_configs():
    """Create AppVersionConfig rows for every app/platform in settings.MOBILE_APP_STORE_IDS."""
    from core.models import AppVersionConfig

    for app, platforms in getattr(settings, "MOBILE_APP_STORE_IDS", {}).items():
        for platform, store_app_id in platforms.items():
            if not store_app_id:
                continue
            AppVersionConfig.objects.get_or_create(
                app=app,
                platform=platform,
                defaults={
                    "store_app_id": store_app_id,
                    "store_url": store_url_for(platform, store_app_id),
                    "min_supported_version": "0.0.0",
                    "latest_version": "0.0.0",
                },
            )


def sync_config(cfg, now=None):
    """
    Fetch the store version for one config and apply it:
    - a newer store version immediately becomes latest_version (soft prompt)
    - after force_delay_minutes it also becomes min_supported_version (force update)
    Returns a short status string.
    """
    now = now or timezone.now()
    cfg.last_store_check_at = now

    if not cfg.store_app_id:
        cfg.last_store_check_error = "store_app_id is not set"
        cfg.save()
        return "skipped: no store_app_id"

    try:
        fetched = fetch_store_version(cfg.platform, cfg.store_app_id)
    except Exception as e:
        logger.warning("Store version lookup failed for %s/%s: %s", cfg.app, cfg.platform, e)
        cfg.last_store_check_error = str(e)[:1000]
        cfg.save()
        return f"error: {e}"

    cfg.last_store_check_error = ""
    fetched_v = parse_version(fetched)
    known_v = parse_version(cfg.store_version)

    # Only move forward; store caches/CDNs can briefly report an older version
    if known_v is None or fetched_v > known_v:
        cfg.store_version = fetched
        cfg.store_version_detected_at = now

    changes = []
    store_v = parse_version(cfg.store_version)
    if cfg.auto_force_store_version and store_v:
        latest_v = parse_version(cfg.latest_version)
        if latest_v is None or store_v > latest_v:
            cfg.latest_version = cfg.store_version
            changes.append(f"latest={cfg.store_version}")

        ready_at = cfg.store_version_detected_at + timedelta(minutes=cfg.force_delay_minutes)
        min_v = parse_version(cfg.min_supported_version)
        if now >= ready_at and (min_v is None or store_v > min_v):
            cfg.min_supported_version = cfg.store_version
            changes.append(f"min={cfg.store_version}")

    cfg.save()
    if changes:
        logger.info("AppVersionConfig %s/%s updated from store: %s", cfg.app, cfg.platform, ", ".join(changes))
    return f"store={cfg.store_version} " + (", ".join(changes) if changes else "no change")


def sync_all():
    from core.models import AppVersionConfig

    ensure_configs()
    results = {}
    for cfg in AppVersionConfig.objects.filter(is_active=True, auto_force_store_version=True):
        results[f"{cfg.app}/{cfg.platform}"] = sync_config(cfg)
    return results
