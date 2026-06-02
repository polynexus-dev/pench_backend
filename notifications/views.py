"""notifications/views.py
In-app notification CRUD + FCM push endpoints.
"""
import logging
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, FCMToken
from . import fcm as fcm_service

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Serializers
# ────────────────────────────────────────────────────────────────────────────

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'notification_type', 'title', 'body', 'is_read', 'created_at', 'order', 'subscription']


class FCMTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = FCMToken
        fields = ['id', 'token', 'created_at']


class SendSingleSerializer(serializers.Serializer):
    token = serializers.CharField()
    title = serializers.CharField()
    body  = serializers.CharField()
    data  = serializers.DictField(child=serializers.CharField(), required=False, default=dict)


class SendMultipleSerializer(serializers.Serializer):
    tokens = serializers.ListField(child=serializers.CharField(), min_length=1)
    title  = serializers.CharField()
    body   = serializers.CharField()
    data   = serializers.DictField(child=serializers.CharField(), required=False, default=dict)


class SendTopicSerializer(serializers.Serializer):
    topic = serializers.CharField()
    title = serializers.CharField()
    body  = serializers.CharField()
    data  = serializers.DictField(child=serializers.CharField(), required=False, default=dict)


# ────────────────────────────────────────────────────────────────────────────
# In-app notification views
# ────────────────────────────────────────────────────────────────────────────

class NotificationListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient_id=self.request.user.id)


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        notif = Notification.objects.filter(pk=pk, recipient_id=request.user.id).first()
        if not notif:
            return Response({'detail': 'Not found.'}, status=404)
        notif.is_read = True
        notif.save()
        return Response({'detail': 'Marked as read.'})


class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        count = Notification.objects.filter(
            recipient_id=request.user.id, is_read=False
        ).update(is_read=True)
        return Response({'detail': f'{count} notifications marked as read.'})


# ────────────────────────────────────────────────────────────────────────────
# FCM token management
# ────────────────────────────────────────────────────────────────────────────

class SaveFCMTokenView(APIView):
    """
    POST /notifications/save-token/
    Body: { "token": "<fcm_token>" }
    Saves the token for the logged-in user. Idempotent — ignores duplicates.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'error': 'token is required'}, status=400)

        obj, created = FCMToken.objects.get_or_create(
            token=token,
            defaults={'user_id': request.user.id}
        )
        # If token exists but belongs to another user, re-assign (device switch)
        if not created and obj.user_id != request.user.id:
            obj.user_id = request.user.id
            obj.save()

        return Response({'success': True, 'id': str(obj.id)}, status=200)


class ListFCMTokensView(APIView):
    """
    GET /notifications/tokens/
    Returns all FCM tokens for the logged-in user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tokens = FCMToken.objects.filter(user_id=request.user.id)
        return Response({'tokens': [t.token for t in tokens]})


# ────────────────────────────────────────────────────────────────────────────
# FCM push endpoints
# ────────────────────────────────────────────────────────────────────────────

class SendSingleView(APIView):
    """
    POST /notifications/send-single/
    Body: { token, title, body, data? }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        ser = SendSingleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            message_id = fcm_service.send_to_device(d['token'], d['title'], d['body'], d.get('data'))
            return Response({'success': True, 'message_id': message_id})
        except Exception as e:
            logger.error("FCM send-single error: %s", e)
            return Response({'success': False, 'error': str(e)}, status=500)


class SendMultipleView(APIView):
    """
    POST /notifications/send-multiple/
    Body: { tokens: [], title, body, data? }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        ser = SendMultipleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            result = fcm_service.send_to_multiple_devices(
                d['tokens'], d['title'], d['body'], d.get('data')
            )
            return Response({'success': True, **result})
        except Exception as e:
            logger.error("FCM send-multiple error: %s", e)
            return Response({'success': False, 'error': str(e)}, status=500)


class SendTopicView(APIView):
    """
    POST /notifications/send-topic/
    Body: { topic, title, body, data? }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        ser = SendTopicSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        try:
            message_id = fcm_service.send_to_topic(d['topic'], d['title'], d['body'], d.get('data'))
            return Response({'success': True, 'message_id': message_id})
        except Exception as e:
            logger.error("FCM send-topic error: %s", e)
            return Response({'success': False, 'error': str(e)}, status=500)
