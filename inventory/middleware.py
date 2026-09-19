from .decorators import current_entity_role
from django.core.exceptions import PermissionDenied


class EntityRoleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.entity_role = current_entity_role(request.user) if request.user.is_authenticated else 'Guest'
        if request.user.is_authenticated and request.entity_role == 'Customer':
            blocked_prefixes = ('/admin/', '/tl/dashboard/', '/workstation/', '/customers/', '/calls/', '/batches/', '/tasks/')
            if request.path.startswith(blocked_prefixes):
                raise PermissionDenied
        return self.get_response(request)
