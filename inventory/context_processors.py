from django.conf import settings
from django.urls import reverse

from .decorators import can_access, role_home_url_name


def role_nav(request):
    """Which links this user may show, using the same rule the views enforce.

    Templates read `nav.<name>` so a link is only rendered when its target won't answer 403.
    """
    user = request.user
    home_name = role_home_url_name(user)
    return {
        'nav': {
            'home': reverse(home_name) if home_name else settings.LOGIN_URL,
            'analytics': can_access(user, 'super_admin'),
            'workstation': can_access(user, 'csr_agent'),
            'csr': can_access(user, 'csr_agent'),
            'team_lead': can_access(user, 'team_lead'),
            'customers': can_access(user, 'team_lead', 'csr_agent'),
        },
    }
