from django.apps import AppConfig
from django.core.checks import Warning, register, Tags
from django.conf import settings


@register(Tags.security)
def check_production_cache_backend(app_configs, **kwargs):
    """System check to verify that production doesn't use in-memory/dummy caches that break multi-worker RBAC."""
    warnings = []
    if not getattr(settings, 'DEBUG', True):
        default_cache = getattr(settings, 'CACHES', {}).get('default', {})
        backend = default_cache.get('BACKEND', '')
        if 'LocMemCache' in backend or 'DummyCache' in backend:
            warnings.append(
                Warning(
                    "Production environment is using a non-persistent/in-memory cache backend (LocMemCache/DummyCache). "
                    "Multi-worker deployments will suffer cache inconsistency for RBAC permissions.",
                    hint="Configure Redis or Memcached in production settings.CACHES.",
                    id="users.W001",
                )
            )
    return warnings


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self):
        import users.signals
        users.signals.connect_signals()

