from .decorators import user_has_role
from .models import Customer

# Shown until the customer completes their profile; also what registration stores for new accounts.
PLACEHOLDER_ADDRESS = 'To be completed'


def ensure_customer_profile(user):
    """Return the user's Customer profile, creating a starter one for Customer-role accounts.

    Returns None for accounts that are not customers, so callers never invent a profile for staff.
    """
    if not user or not user.is_authenticated or not user_has_role(user, 'customer'):
        return None
    existing = getattr(user, 'customer_profile', None)
    if existing is not None:
        return existing
    registration = getattr(user, 'registration_request', None)
    full_name = user.get_full_name() or user.get_username()
    profile, _created = Customer.objects.get_or_create(
        user=user,
        defaults={
            'company_name': (registration.company_name if registration else '') or full_name,
            'contact_person': full_name,
            'email': user.email,
            'phone': registration.phone if registration else '',
            'delivery_address': PLACEHOLDER_ADDRESS,
            'credit_limit': 0,
        },
    )
    return profile
