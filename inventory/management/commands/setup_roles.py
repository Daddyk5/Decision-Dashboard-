from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


ROLE_PERMISSIONS = {
    'Super Admin / Client': {
        'inventory': ('inventorybatch', 'customer', 'order', 'delivery', 'payment', 'task', 'stockadjustment', 'calllog'),
        'auth': ('user', 'group'),
    },
    'Team Lead': {
        'inventory': ('inventorybatch', 'customer', 'task', 'stockadjustment', 'calllog', 'order', 'delivery', 'payment'),
    },
    'CSR Agent': {
        'inventory': ('customer', 'order', 'calllog', 'task'),
    },
    'Customer': {},
}


class Command(BaseCommand):
    help = 'Create or update the standard Rice Enterprise RBAC groups.'

    def handle(self, *args, **options):
        for role_name, app_models in ROLE_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=role_name)
            permissions = []
            for app_label, model_names in app_models.items():
                for model_name in model_names:
                    permissions.extend(
                        Permission.objects.filter(
                            content_type__app_label=app_label,
                            content_type__model=model_name,
                            codename__in=(
                                f'add_{model_name}',
                                f'change_{model_name}',
                                f'delete_{model_name}',
                                f'view_{model_name}',
                            ),
                        )
                    )
            group.permissions.set(permissions)
            self.stdout.write(self.style.SUCCESS(f'Configured {role_name} ({len(permissions)} permissions)'))
