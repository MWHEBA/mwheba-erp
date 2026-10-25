# -*- coding: utf-8 -*-
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ChequesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cheques'
    verbose_name = _('إدارة الشيكات وأوراق القبض والدفع')

    def ready(self):
        # استيراد الإشارات عند الحاجة
        try:
            import cheques.signals  # noqa: F401
        except ImportError:
            pass
