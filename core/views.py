from django.views.generic import TemplateView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core import app_version


class PrivacyPolicyView(TemplateView):
    """Public, tenant-independent privacy policy page for Play Store / App Store listings."""

    template_name = "privacy_policy.html"


class AccountDeletionView(TemplateView):
    """Public account & data deletion request page required for Play Store / App Store listings."""

    template_name = "delete_account.html"


class AppVersionCheckView(APIView):
    """
    Public endpoint the mobile apps call on launch/resume to decide whether to
    force an update. Query params (or X-App-* headers):
    app (pench|customer|delivery), platform (android|ios), version (e.g. 2.3.1).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        params, headers = request.query_params, request.headers
        app = params.get("app") or headers.get("X-App-Name")
        platform = params.get("platform") or headers.get("X-App-Platform")
        version = params.get("version") or headers.get("X-App-Version")

        if not app or not platform or not version:
            return Response(
                {"detail": "app, platform and version are required."}, status=400
            )

        cfg = app_version.get_config(app, platform)
        if cfg is None:
            # No policy configured for this app/platform: let the app through.
            return Response(
                {
                    "status": app_version.OK,
                    "force_update": False,
                    "soft_update": False,
                    "maintenance_mode": False,
                }
            )

        status = app_version.evaluate(cfg, version)
        return Response(app_version.build_payload(cfg, status))
