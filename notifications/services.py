import logging
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .models import FCMToken, Notification
from . import fcm as fcm_service

logger = logging.getLogger(__name__)


def send_push_notification(user, title, body, data=None, order=None, subscription=None, notification_type='general'):
    """
    Core service to dispatch notifications:
    1. Saves notification history to the DB (for in-app notification center).
    2. Sends push notification via FCM to all registered user tokens.
    3. Broadcasts real-time notification over WebSockets (if channels is active).
    """
    # 1. Save to DB
    notif = None
    try:
        notif = Notification.objects.create(
            recipient=user,
            order=order,
            subscription=subscription,
            notification_type=notification_type,
            title=title,
            body=body
        )
    except Exception as exc:
        logger.error('[Notification Service] DB save failed: %s', exc)

    # 2. Send via FCM
    try:
        tokens = list(FCMToken.objects.filter(user=user).values_list('token', flat=True))
        if tokens:
            fcm_data = data or {}
            # Include basic contextual keys in the payload dictionary
            if order:
                fcm_data['order_id'] = str(order.id)
            if subscription:
                fcm_data['subscription_id'] = str(subscription.id)
            fcm_data['notification_type'] = notification_type
            if notif:
                fcm_data['notification_id'] = str(notif.id)

            if len(tokens) == 1:
                fcm_service.send_to_device(tokens[0], title, body, fcm_data)
            else:
                fcm_service.send_to_multiple_devices(tokens, title, body, fcm_data)
        else:
            logger.info('[Notification Service] No FCM tokens registered for user: %s', user.username)
    except Exception as exc:
        logger.error('[Notification Service] FCM dispatch failed: %s', exc)

    # 3. WebSocket Broadcast
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            payload = {
                'type': 'notification.receive',
                'id': str(notif.id) if notif else None,
                'notification_type': notification_type,
                'title': title,
                'body': body,
                'order_id': str(order.id) if order else None,
                'subscription_id': str(subscription.id) if subscription else None,
            }
            async_to_sync(channel_layer.group_send)(
                f'user_{user.id}',
                {'type': 'notification_message', 'data': payload}
            )
    except Exception as exc:
        logger.error('[Notification Service] WebSocket broadcast failed: %s', exc)

    return notif
