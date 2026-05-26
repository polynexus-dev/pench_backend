from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class PhoneOrUsernameBackend(ModelBackend):
    """
    Custom authentication backend that allows users to log in using
    either their username or their phone number.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)

        try:
            # Search by username OR phone
            user = User.objects.get(Q(username=username) | Q(phone=username))

            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        except User.DoesNotExist:
            return None
        return None
