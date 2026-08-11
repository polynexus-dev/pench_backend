from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegisterView,
    MeView,
    RequestOTPView,
    LoginOTPView,
    MyTokenObtainPairView,
    MyTokenRefreshView,
    SetPasswordView,
    ForgotPasswordView,
    ResetPasswordView,
    UserViewSet,
    PermissionViewSet,
    GroupViewSet,
)

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("groups", GroupViewSet, basename="group")
router.register("permissions", PermissionViewSet, basename="permission")

urlpatterns = [
    path("login/", MyTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("login/refresh/", MyTokenRefreshView.as_view(), name="token_refresh"),
    path("login-otp/", LoginOTPView.as_view(), name="login_otp"),
    path("request-otp/", RequestOTPView.as_view(), name="request_otp"),
    path("set-password/", SetPasswordView.as_view(), name="set_password"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset_password"),
    path("register/", RegisterView.as_view(), name="register"),
    path("me/", MeView.as_view(), name="me"),
    path("", include(router.urls)),
]
