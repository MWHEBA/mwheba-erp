from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class FXApprovalWorkflow(models.Model):
    APPROVAL_TYPE_CHOICES = (
        ('NORMAL_POSTING_APPROVAL', _('اعتماد تقييم عادي')),
        ('RATE_OVERRIDE_APPROVAL', _('تجاوز عمر سعر الصرف المتقادم')),
        ('PERIOD_CLOSE_APPROVAL', _('اعتماد إغلاق الفترة')),
    )

    DECISION_CHOICES = (
        ('PENDING', _('قيد الانتظار')),
        ('APPROVED', _('موافق عليه')),
        ('REJECTED', _('مرفوض')),
    )

    entity_type = models.CharField(_("نوع الكيان"), max_length=50, default="FXRevaluationRun")
    entity_id = models.CharField(_("معرف الكيان"), max_length=100)
    approval_type = models.CharField(_("نوع الاعتماد"), max_length=30, choices=APPROVAL_TYPE_CHOICES, default='NORMAL_POSTING_APPROVAL')

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fx_approval_requests', verbose_name=_("طالب الاعتماد"))
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='fx_approvals_given', verbose_name=_("المُعتمد"))

    approval_date = models.DateTimeField(_("تاريخ القرار"), null=True, blank=True)
    decision = models.CharField(_("القرار"), max_length=20, choices=DECISION_CHOICES, default='PENDING')
    reason = models.TextField(_("سبب القرار / التبرير المحاسبي"), blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("سجل اعتماد وتجاوز التقييم")
        verbose_name_plural = _("سجلات اعتماد وتجاوز التقييم")

    def __str__(self):
        return f"Approval #{self.id} [{self.get_approval_type_display()}] - {self.get_decision_display()}"
