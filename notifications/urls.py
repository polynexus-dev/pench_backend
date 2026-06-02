from django.urls import path
from . import views

urlpatterns = [
    # ── In-app notifications ──────────────────────────────────────────────
    path('',          views.NotificationListView.as_view(), name='notification-list'),
    path('read-all/', views.MarkAllReadView.as_view(),      name='notification-read-all'),
    path('<uuid:pk>/read/', views.MarkReadView.as_view(),   name='notification-read'),

    # ── FCM Token management ──────────────────────────────────────────────
    path('save-token/', views.SaveFCMTokenView.as_view(),  name='fcm-save-token'),
    path('tokens/',     views.ListFCMTokensView.as_view(), name='fcm-tokens'),

    # ── FCM Push endpoints ────────────────────────────────────────────────
    path('send-single/',   views.SendSingleView.as_view(),   name='fcm-send-single'),
    path('send-multiple/', views.SendMultipleView.as_view(), name='fcm-send-multiple'),
    path('send-topic/',    views.SendTopicView.as_view(),    name='fcm-send-topic'),
]
