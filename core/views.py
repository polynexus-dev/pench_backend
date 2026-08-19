from django.views.generic import TemplateView


class PrivacyPolicyView(TemplateView):
    """Public, tenant-independent privacy policy page for Play Store / App Store listings."""

    template_name = "privacy_policy.html"


class AccountDeletionView(TemplateView):
    """Public account & data deletion request page required for Play Store / App Store listings."""

    template_name = "delete_account.html"
