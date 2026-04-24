from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hr'
    verbose_name = 'إدارة الموارد البشرية'
    
    def ready(self):
        """تفعيل الإشارات (Signals) عند تشغيل التطبيق"""
        import hr.signals  # noqa
        import hr.signals_permissions  # noqa
        import hr.signals_permission_validation  # noqa
        import hr.signals_official_holiday  # noqa
