from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import CommandError, BaseCommand


ROLES = ('Super Admin / Client', 'Team Lead', 'CSR Agent', 'Customer')


class Command(BaseCommand):
    help = 'Create one named user account and assign exactly one enterprise role group.'

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)
        parser.add_argument('--email', default='')
        parser.add_argument('--role', required=True, choices=ROLES)
        parser.add_argument('--superuser', action='store_true', help='Create a Django superuser; only valid for Super Admin / Client.')

    def handle(self, *args, **options):
        username = options['username']
        role = options['role']
        is_superuser = options['superuser']
        if is_superuser and role != 'Super Admin / Client':
            raise CommandError('--superuser is only valid for Super Admin / Client.')

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            raise CommandError(f'User {username!r} already exists.')

        password = getpass(f'Password for {username}: ')
        confirmation = getpass('Password (again): ')
        if not password or password != confirmation:
            raise CommandError('Passwords are empty or do not match.')

        user = User.objects.create_user(username=username, email=options['email'], password=password)
        user.is_staff = is_superuser
        user.is_superuser = is_superuser
        user.save(update_fields=('is_staff', 'is_superuser'))
        user.groups.add(Group.objects.get(name=role))
        self.stdout.write(self.style.SUCCESS(f'Created {role} account: {username}'))
