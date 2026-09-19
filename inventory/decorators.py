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


def _normalized_group_names(*names):
    normalized = set()
    for name in names:
        if not name:
            continue
        normalized.add(name.strip())
        normalized.add(name.strip().lower())
    return tuple(sorted(normalized))


def user_has_role(user, role):
    if not user or not user.is_authenticated:
        return False
    allowed_names = _normalized_group_names(*ROLE_GROUP_ALIASES.get(role, (ROLE_GROUPS[role],)))
    return user.groups.filter(name__in=allowed_names).exists() or user.groups.filter(name__iexact=ROLE_GROUPS.get(role, '')).exists() or user.groups.filter(name__iexact=ROLE_GROUPS[role]).exists()


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            if request.user.groups.filter(name__iexact=ROLE_GROUPS['super_admin']).exists():
                return view_func(request, *args, **kwargs)
            if any(user_has_role(request.user, role) for role in roles):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return wrapped
    return decorator


def customer_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapped(request, *args, **kwargs):
        if user_has_role(request.user, 'customer') and hasattr(request.user, 'customer_profile'):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied
    return wrapped


def current_entity_role(user):
    if user.is_superuser or user.groups.filter(name__iexact=ROLE_GROUPS['super_admin']).exists():
        return ROLE_GROUPS['super_admin']
    if user_has_role(user, 'team_lead'):
        return ROLE_GROUPS['team_lead']
    if user_has_role(user, 'csr_agent'):
        return ROLE_GROUPS['csr_agent']
    if user_has_role(user, 'customer'):
        return ROLE_GROUPS['customer']
    return 'Unassigned'
