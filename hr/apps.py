from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hr'
    verbose_name = 'إدارة الموارد البشرية'
    
    def ready(self):
        """تفعيل الإشارات (Signals) عند تشغيل التطبيق"""
        import hr.signals  # noqa
