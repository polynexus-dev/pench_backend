"""notifications/fcm.py
Firebase Cloud Messaging helpers.
All credentials come from Django settings.
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def _init_firebase():
    """Lazy-initialise Firebase Admin SDK from environment-based settings."""
    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        return  # already initialised

    private_key = getattr(settings, 'FIREBASE_PRIVATE_KEY', '')
    if isinstance(private_key, str):
        private_key = private_key.replace('\\n', '\n')

    cred_dict = {
        "type":                        getattr(settings, 'FIREBASE_TYPE', 'service_account'),
        "project_id":                  getattr(settings, 'FIREBASE_PROJECT_ID', ''),
        "private_key_id":              getattr(settings, 'FIREBASE_PRIVATE_KEY_ID', ''),
        "private_key":                 private_key,
        "client_email":                getattr(settings, 'FIREBASE_CLIENT_EMAIL', ''),
        "client_id":                   getattr(settings, 'FIREBASE_CLIENT_ID', ''),
        "auth_uri":                    getattr(settings, 'FIREBASE_AUTH_URI', 'https://accounts.google.com/o/oauth2/auth'),
        "token_uri":                   getattr(settings, 'FIREBASE_TOKEN_URI', 'https://oauth2.googleapis.com/token'),
        "auth_provider_x509_cert_url": getattr(settings, 'FIREBASE_AUTH_PROVIDER_CERT_URL', 'https://www.googleapis.com/oauth2/v1/certs'),
        "client_x509_cert_url":        getattr(settings, 'FIREBASE_CLIENT_CERT_URL', ''),
        "universe_domain":             getattr(settings, 'FIREBASE_UNIVERSE_DOMAIN', 'googleapis.com'),
    }

    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)


def send_to_device(fcm_token: str, title: str, body: str, data: dict = None) -> str:
    """
    Send a push notification to a single device.
    Returns the FCM message ID.
    """
    _init_firebase()
    from firebase_admin import messaging

    msg = messaging.Message(
        token=fcm_token,
        notification=messaging.Notification(title=title, body=body),
        data={str(k): str(v) for k, v in (data or {}).items()},
        android=messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                sound='default',
                channel_id='default',
            ),
        ),
    )
    response = messaging.send(msg)
    logger.info("FCM sent to device: %s", response)
    return response


def send_to_multiple_devices(fcm_tokens: list, title: str, body: str, data: dict = None) -> dict:
    """
    Send a push notification to multiple devices at once.
    Returns { success_count, failure_count, responses }.
    """
    _init_firebase()
    from firebase_admin import messaging

    msg = messaging.MulticastMessage(
        tokens=fcm_tokens,
        notification=messaging.Notification(title=title, body=body),
        data={str(k): str(v) for k, v in (data or {}).items()},
        android=messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                sound='default',
                channel_id='default',
            ),
        ),
    )
    response = messaging.send_each_for_multicast(msg)
    logger.info("FCM multicast: success=%s failure=%s", response.success_count, response.failure_count)
    return {
        'success_count': response.success_count,
        'failure_count': response.failure_count,
        'responses': [
            {
                'message_id': r.message_id,
                'error': str(r.exception) if r.exception else None,
            }
            for r in response.responses
        ],
    }


def send_to_topic(topic: str, title: str, body: str, data: dict = None) -> str:
    """
    Broadcast a notification to all devices subscribed to a topic.
    Returns the FCM message ID.
    """
    _init_firebase()
    from firebase_admin import messaging

    msg = messaging.Message(
        topic=topic,
        notification=messaging.Notification(title=title, body=body),
        data={str(k): str(v) for k, v in (data or {}).items()},
        android=messaging.AndroidConfig(priority='high'),
    )
    response = messaging.send(msg)
    logger.info("FCM sent to topic '%s': %s", topic, response)
    return response
