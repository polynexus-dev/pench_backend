from rest_framework.permissions import BasePermission


class IsERPUser(BasePermission):
    """
    Grants access only to users with is_erp_user=True.
    Applied to all /api/erp/* views.
    """
    message = 'Access restricted to ERP users.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_erp_user or request.user.is_superuser or request.user.groups.filter(name='SuperAdmin').exists())
        )


class IsDriverUser(BasePermission):
    """Grants write access only to users with is_driver=True."""
    message = 'Access restricted to driver users.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_driver or request.user.is_superuser or request.user.groups.filter(name='SuperAdmin').exists())
        )


class IsDriverOrReadOnly(BasePermission):
    """
    Drivers can write; authenticated users can read.
    Used for tracking events.
    """
    SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in self.SAFE_METHODS:
            return True
        return request.user.is_driver


class HasGroupPermission(BasePermission):
    """
    Grants access based on user groups.
    Usage:
    permission_classes = [HasGroupPermission]
    required_groups = ['GroupName']
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser or request.user.groups.filter(name='SuperAdmin').exists():
            return True

        required_groups = getattr(view, 'required_groups', [])
        if not required_groups:
            return False
        
        return request.user.groups.filter(name__in=required_groups).exists()


class IsOwnerOrERP(BasePermission):
    """
    Object-level: allows access if user is the owner
    of the object (customer) OR an ERP user.
    """
    message = 'You do not have permission to access this resource.'

    def has_object_permission(self, request, view, obj):
        if request.user.is_erp_user:
            return True
        # obj is expected to have a .customer or .user attribute
        owner = getattr(obj, 'customer', None) or getattr(obj, 'user', None)
        if owner is None:
            return False
        return owner == request.user
