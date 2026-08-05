from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from decimal import Decimal


class EmployeeCostCenterAllocation(models.Model):
    """
    نموذج توزيع رواتب الموظف على مراكز التكلفة (EmployeeCostCenterAllocation Model)
    """
    employee_id = models.CharField(_("كود / معرف الموظف"), max_length=50, db_index=True)
    employee_name = models.CharField(_("اسم الموظف"), max_length=150)
    cost_center = models.ForeignKey(
        'financial.CostCenter',
        on_delete=models.PROTECT,
        related_name='employee_allocations',
        verbose_name=_("مركز التكلفة")
    )
    percentage = models.DecimalField(_("النسبة المئوية من الراتب"), max_digits=5, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(_("تاريخ التخصيص"), auto_now_add=True)

    class Meta:
        verbose_name = _("توزيع راتب موظف")
        verbose_name_plural = _("توزيعات رواتب الموظفين")
        unique_together = ('employee_id', 'cost_center')

    def __str__(self):
        return f"{self.employee_name} ({self.employee_id}) -> {self.cost_center.code}: {self.percentage}%"


class UserCostCenterPermission(models.Model):
    """
    محرك الصلاحيات والوصول لمراكز التكلفة (UserCostCenterPermission Model)
    يدعم ALLOW / DENY والأولويات.
    """
    ACCESS_CHOICES = (
        ('ALLOW', _('سماح')),
        ('DENY', _('حظر / منع')),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cost_center_permissions',
        verbose_name=_("المستخدم")
    )
    cost_center = models.ForeignKey(
        'financial.CostCenter',
        on_delete=models.CASCADE,
        related_name='user_permissions',
        verbose_name=_("مركز التكلفة")
    )
    access_type = models.CharField(_("نوع الصلاحية"), max_length=10, choices=ACCESS_CHOICES, default='ALLOW')
    priority = models.PositiveIntegerField(_("الأولوية"), default=10, help_text=_("الرقم الأقل يعني أولوية أعلى"))
    created_at = models.DateTimeField(_("تاريخ الإضافة"), auto_now_add=True)

    class Meta:
        verbose_name = _("صلاحية مركز تكلفة لمستخدم")
        verbose_name_plural = _("صلاحيات مراكز التكلفة للمستخدمين")
        unique_together = ('user', 'cost_center')
        ordering = ['priority', 'id']

    def __str__(self):
        return f"{self.user.username} -> {self.cost_center.code}: {self.access_type}"


class CostCenterAuditLog(models.Model):
    """
    سجلات التدقيق والحوكمة لمراكز التكلفة (CostCenterAuditLog Model)
    """
    ACTION_CHOICES = (
        ('CREATED', _('إنشاء')),
        ('UPDATED', _('تحديث')),
        ('TREE_MOVED', _('نقل هيكلي')),
        ('DELETED', _('حذف')),
    )

    cost_center = models.ForeignKey(
        'financial.CostCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name=_("مركز التكلفة")
    )
    action = models.CharField(_("نوع الإجراء"), max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("القائم بالإجراء")
    )
    user_name_snapshot = models.CharField(_("لقطة اسم المستخدم"), max_length=150, blank=True, null=True)
    changes_json = models.TextField(_("تفاصيل التغييرات"), blank=True, null=True)
    timestamp = models.DateTimeField(_("التوقيت"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تدقيق مركز تكلفة")
        verbose_name_plural = _("سجلات تدقيق مراكز التكلفة")
        ordering = ['-timestamp']


class CostAllocationRuleAuditLog(models.Model):
    """
    سجلات التدقيق لقواعد التوزيع المالي (CostAllocationRuleAuditLog Model)
    """
    rule_name = models.CharField(_("اسم القاعدة"), max_length=150)
    action = models.CharField(_("الإجراء"), max_length=50)
    performed_by_name = models.CharField(_("اسم القائم بالإجراء"), max_length=150)
    details = models.TextField(_("تفاصيل الحركة"), blank=True, null=True)
    timestamp = models.DateTimeField(_("التوقيت"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تدقيق قاعدة توزيع")
        verbose_name_plural = _("سجلات تدقيق قواعد التوزيع")
        ordering = ['-timestamp']
