from django.apps import AppConfig


class InventoryConfig(AppConfig):
    name = 'inventory'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        from . import signals  # noqa: F401
