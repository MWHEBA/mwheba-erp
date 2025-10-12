from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class SystemLog(models.Model):
    """
    نموذج لتخزين سجلات النظام بما في ذلك الإجراءات التي يقوم بها المستخدمون
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, verbose_name=_("المستخدم"))
    action = models.CharField(max_length=100, verbose_name=_("الإجراء"))
    model_name = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("اسم النموذج"))
    object_id = models.CharField(max_length=100, null=True, blank=True, verbose_name=_("معرف الكائن"))
    details = models.TextField(null=True, blank=True, verbose_name=_("التفاصيل"))
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name=_("عنوان IP"))
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("التاريخ والوقت"))

    class Meta:
        verbose_name = _("سجل النظام")
        verbose_name_plural = _("سجلات النظام")
        ordering = ["-timestamp"]
        
    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}" 