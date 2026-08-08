from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from financial.models.fiscal_year import FiscalYear
from financial.models.journal_entry import AccountingPeriod

User = settings.AUTH_USER_MODEL


class FiscalYearClosingRun(models.Model):
    """
    نموذج تتبع محاولات وإجراءات الإغلاق السنوي السلسلي (Closing Run Execution Engine)
    يتتبع كل تشغيل مع آلة الحالات (State Machine) وتحديد حقول الاستئناف عند الفشل.
    """
    STATUS_CHOICES = [
        ('DRAFT', _('مسودة مبدئية')),
        ('AUDITING', _('جاري التدقيق وفحص الاستحقاق')),
        ('READY', _('جاهز للإغلاق')),
        ('RUNNING', _('جاري تنفيذ الإغلاق')),
        ('COMPLETED', _('تم الإغلاق بنجاح')),
        ('FAILED', _('فشل الإغلاق')),
        ('REVERSED', _('معكوس / معاد فتحه')),
    ]

    closing_run_key = models.CharField(
        _("مفتاح منع تكرار الإغلاق الفريد"),
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_("مفتاح فريد لمنع تكرار الإغلاق مثل CLOSE:company:FY2025")
    )
    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name='closing_runs',
        verbose_name=_("السنة المالية")
    )
    started_at = models.DateTimeField(_("تاريخ بدء التشغيل"), default=timezone.now)
    completed_at = models.DateTimeField(_("تاريخ اكتمال التشغيل"), null=True, blank=True)
    status = models.CharField(_("حالة الإغلاق"), max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    current_step = models.CharField(_("الخطوة الحالية"), max_length=100, default='DRAFT')
    last_successful_step = models.CharField(_("آخر خطوة مكتملة بنجاح"), max_length=100, null=True, blank=True)
    
    executed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='fiscal_closing_runs',
        verbose_name=_("نفذ بواسطة")
    )
    snapshot_id = models.CharField(_("معرف لقطة التقرير الختامي"), max_length=100, null=True, blank=True)
    logs = models.JSONField(_("سجل الأحداث والأخطاء"), default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("تشغيل إغلاق سنة مالية")
        verbose_name_plural = _("تشغيلات إغلاق السنوات المالية")
        ordering = ['-started_at']

    def __str__(self):
        return f"ClosingRun #{self.id} [{self.fiscal_year.year_code}] - {self.get_status_display()}"


class PeriodModuleLock(models.Model):
    """
    نموذج حظر الموديولات الديناميكي (Granular Sub-Ledger Locking Architecture)
    يتيح حظر موديول معين (AR, AP, Inventory, Treasury, GL) بدرجات حظر متفاوتة.
    """
    LOCK_TYPE_CHOICES = [
        ('POST_BLOCK', _('منع الترحيل وإنشاء الحركات')),
        ('EDIT_BLOCK', _('منع التعديل على الحركات القائمة')),
        ('DELETE_BLOCK', _('منع الحذف')),
        ('READ_ONLY', _('قراءة فقط - حظر كامل')),
    ]

    period = models.ForeignKey(
        AccountingPeriod,
        on_delete=models.CASCADE,
        related_name='module_locks',
        verbose_name=_("الفترة المحاسبية")
    )
    module = models.CharField(
        _("الموديول"),
        max_length=50,
        db_index=True,
        help_text=_("رمز الموديول المحظور (AR, AP, INVENTORY, TREASURY, GL, PAYROLL, etc.)")
    )
    status = models.CharField(_("حالة الحظر"), max_length=20, default='locked')
    lock_type = models.CharField(
        _("درجة الحظر"),
        max_length=20,
        choices=LOCK_TYPE_CHOICES,
        default='POST_BLOCK'
    )
    locked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='module_locks_applied',
        verbose_name=_("حظر بواسطة")
    )
    locked_at = models.DateTimeField(_("تاريخ الحظر"), default=timezone.now)
    reason = models.TextField(_("سبب الحظر"), blank=True)

    class Meta:
        verbose_name = _("حظر موديول فترة محاسبية")
        verbose_name_plural = _("حظر موديولات الفترات المحاسبية")
        unique_together = ['period', 'module']
        ordering = ['period', 'module']

    def __str__(self):
        return f"Lock [{self.module}] on {self.period.name} ({self.get_lock_type_display()})"


class ClosingRule(models.Model):
    """
    نموذج قواعد فحص الإغلاق التكيفي (Closing Rule Engine)
    يفصل بين القواعد الإلزامية المطلقة والقواعد القابلة للتعديل والتهيئة.
    """
    SEVERITY_CHOICES = [
        ('MANDATORY_BLOCKER', _('حاسم إجباري - غير قابل للتجاوّز')),
        ('CONFIGURABLE_BLOCKER', _('حاسم قابل للتعديل')),
        ('WARNING', _('تحذير مسموح بالتجاوّز')),
    ]

    rule_code = models.CharField(_("كود القاعدة"), max_length=100, db_index=True, unique=True)
    name = models.CharField(_("اسم القاعدة المحاسبية"), max_length=255)
    severity = models.CharField(_("درجة الخطورة"), max_length=30, choices=SEVERITY_CHOICES, default='WARNING')
    enabled = models.BooleanField(_("مفعلة؟"), default=True)
    applies_to_company = models.CharField(_("تطبق على الشركة"), max_length=50, default='DEFAULT')
    applies_to_module = models.CharField(_("تطبق على الموديول"), max_length=50, null=True, blank=True)
    execution_order = models.IntegerField(_("ترتيب التنفيذ"), default=10)
    blocking_reason = models.TextField(_("رسالة المنع عند التفعيل"), blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("قاعدة فحص إغلاق")
        verbose_name_plural = _("قواعد فحص الإغلاق")
        ordering = ['execution_order', 'rule_code']

    def __str__(self):
        return f"[{self.rule_code}] {self.name} ({self.get_severity_display()})"
