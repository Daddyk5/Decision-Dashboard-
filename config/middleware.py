import re

from django.conf import settings
from django.shortcuts import redirect


class LoginGatekeeperMiddleware:
    """Keep every application route behind the central login screen."""

    public_paths = frozenset({'/login/', '/register/', '/terms/', '/privacy/', '/confirm-success/'})
    confirmation_path = re.compile(r'^/confirm-email/[^/]+/[^/]+/$')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        is_public = path in self.public_paths or bool(self.confirmation_path.match(path))
        is_static = settings.STATIC_URL and path.startswith(settings.STATIC_URL)
        if not request.user.is_authenticated and not is_public and not is_static:
            return redirect(f'{settings.LOGIN_URL}?next={request.get_full_path()}')
        return self.get_response(request)