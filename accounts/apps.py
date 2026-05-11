from django.apps import AppConfig
class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        import accounts.signals
        """
        Runs group setup automatically when the server starts in local development.
        """
        import sys
        # Only run when starting the development server or a gunicorn/uvicorn worker
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv[0] or 'uvicorn' in sys.argv[0]:
            try:
                from django.contrib.auth.models import Group
                # Check if groups exist to avoid repeated overhead
                # We check for the most critical group
                if not Group.objects.filter(name='ERP_Admins').exists():
                    from django.core.management import call_command
                    # Use a separate thread or call_command to initialize
                    call_command('setup_groups')
            except Exception:
                # Avoid crashing during migrations or if DB is not ready
                pass
