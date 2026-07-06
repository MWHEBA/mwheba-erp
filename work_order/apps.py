from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class WorkOrderConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'work_order'
    verbose_name = _('أوامر الشغل')
