from functools import wraps

from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required


ROLE_GROUPS = {
    'super_admin': 'Super Admin / Client',
    'team_lead': 'Team Lead',
    'csr_agent': 'CSR Agent',
    'customer': 'Customer',
}

ROLE_GROUP_ALIASES = {
    'customer': ('Customer', 'Customer B2B'),
}

# Highest privilege first: a user holding several groups lands on their most privileged workspace.
ROLE_PRECEDENCE = ('super_admin', 'team_lead', 'csr_agent', 'customer')

ROLE_HOME_URL_NAMES = {
    'super_admin': 'dashboard',
    'team_lead': 'tl-dashboard',
    'csr_agent': 'workstation',
    'customer': 'customer-portal',
}


def _normalize(name):
    return ' '.join((name or '').split()).lower()


def _group_names(user):
    """Normalized names of the user's groups, so 'csr agent ' still matches 'CSR Agent'."""
    cached = getattr(user, '_normalized_group_names', None)
    if cached is None:
        cached = frozenset(_normalize(name) for name in user.groups.values_list('name', flat=True))
        user._normalized_group_names = cached
    return cached


def is_super_admin(user):
    return bool(user and user.is_authenticated and (user.is_superuser or _normalize(ROLE_GROUPS['super_admin']) in _group_names(user)))


def user_has_role(user, role):
    if not user or not user.is_authenticated:
        return False
    allowed = {_normalize(name) for name in ROLE_GROUP_ALIASES.get(role, (ROLE_GROUPS[role],))}
    return not allowed.isdisjoint(_group_names(user))


def can_access(user, *roles):
    """The single rule every role-guarded view and every role-aware link uses."""
    if not user or not user.is_authenticated:
        return False
    return is_super_admin(user) or any(user_has_role(user, role) for role in roles)


def resolve_role(user):
    """The role key ('super_admin', 'team_lead', ...) the user works as, or None if unassigned."""
    if not user or not user.is_authenticated:
        return None
    if is_super_admin(user):
        return 'super_admin'
    for role in ROLE_PRECEDENCE[1:]:
        if user_has_role(user, role):
            return role
    return None


def role_home_url_name(user):
    """URL name of the page this user can always open after signing in, or None if there isn't one.

    A customer without a Customer profile has no usable workspace (the portal would 403), so they
    are treated the same as an unassigned account.
    """
    role = resolve_role(user)
    if role == 'customer' and not hasattr(user, 'customer_profile'):
        return None
    return ROLE_HOME_URL_NAMES.get(role)


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if can_access(request.user, *roles):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrapped
    return decorator


def customer_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        from .profiles import ensure_customer_profile  # imported here because profiles imports this module

        if ensure_customer_profile(request.user) is not None:
            return view_func(request, *args, **kwargs)
        raise PermissionDenied
    return wrapped


def current_entity_role(user):
    role = resolve_role(user)
    return ROLE_GROUPS[role] if role else 'Unassigned'
