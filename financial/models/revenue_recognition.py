import uuid
import json
import hashlib
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import AccountingPeriod, JournalEntry


class RevenueRecognitionPolicy(models.Model):
    """
    FIN-AR-002: IFRS 15 Revenue Recognition Policy Model
    نموذج سياسات الاعتراف بالإيراد المحوكمة وفق معيار IFRS 15
    """
    SCOPE_CHOICES = (
        ("GLOBAL", _("شامل عام")),
        ("CATEGORY", _("فئة منتجات")),
        ("PRODUCT", _("منتج محدد")),
    )

    TRIGGER_CHOICES = (
        ("INVOICE_ISSUANCE", _("إصدار الفاتورة")),
        ("DELIVERY_CONFIRMED", _("تأكيد التسليم")),
        ("CUSTOMER_ACCEPTANCE", _("قبول العميل")),
        ("INSTALLATION_COMPLETED", _("إتمام التركيب")),
        ("SERVICE_COMPLETED", _("إتمام الخدمة")),
        ("TIME_MILESTONE", _("جدول زمني")),
    )

    ALLOCATION_CHOICES = (
        ("DIRECT_LINE_VALUE", _("قيمة البند المباشرة")),
        ("PERCENTAGE", _("نسبة مئوية")),
        ("FIXED_AMOUNT", _("مبلغ ثابت")),
        ("STANDALONE_SELLING_PRICE", _("سعر البيع المستقل")),
    )

    FX_TREATMENT_CHOICES = (
        ("INVOICE_RATE", _("سعر صرف الفاتورة")),
        ("RECOGNITION_DATE_RATE", _("سعر صرف تاريخ الاعتراف")),
        ("AVERAGE_RATE", _("متوسط سعر الصرف")),
    )

    name = models.CharField(_("اسم السياسة"), max_length=150)
    code = models.CharField(_("كود السياسة"), max_length=50, unique=True)
    version = models.IntegerField(_("إصدار السياسة"), default=1)
    effective_from = models.DateField(_("سارية من تاريخ"), default=timezone.now)
    effective_to = models.DateField(_("سارية إلى تاريخ"), null=True, blank=True)

    rule_scope = models.CharField(_("نطاق السياسة"), max_length=20, choices=SCOPE_CHOICES, default="GLOBAL")
    scope_value = models.CharField(_("قيمة النطاق (معرف الفئة/المنتج)"), max_length=100, blank=True, null=True)

    trigger_event = models.CharField(_("حدث الاعتراف المحفز"), max_length=30, choices=TRIGGER_CHOICES, default="DELIVERY_CONFIRMED")
    allocation_method = models.CharField(_("طريقة تخصيص سعر المعاملة"), max_length=30, choices=ALLOCATION_CHOICES, default="DIRECT_LINE_VALUE")
    fx_treatment_type = models.CharField(_("معالجة أسعار الصرف IAS 21"), max_length=30, choices=FX_TREATMENT_CHOICES, default="INVOICE_RATE")

    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("سياسة الاعتراف بالإيراد")
        verbose_name_plural = _("سياسات الاعتراف بالإيراد")
        unique_together = ("code", "version")

    def __str__(self):
        return f"{self.name} v{self.version} ({self.code})"


class RevenueRecognitionAccountMapping(models.Model):
    """
    FIN-AR-002: Policy Account Mapping per Currency/Company
    خريطة الحسابات المالية للاعتراف بالإيراد والإيرادات المؤجلة وأصول العقود
    """
    policy = models.ForeignKey(RevenueRecognitionPolicy, on_delete=models.CASCADE, related_name="account_mappings", verbose_name=_("السياسة"))
    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    revenue_account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, related_name="rev_rec_mappings", verbose_name=_("حساب الإيرادات"))
    deferred_revenue_account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, related_name="deferred_rev_mappings", verbose_name=_("حساب الإيرادات المؤجلة / التزامات العقود"))
    contract_asset_account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, null=True, blank=True, related_name="contract_asset_mappings", verbose_name=_("حساب أصول العقود"))

    class Meta:
        verbose_name = _("خريطة حسابات الاعتراف بالإيراد")
        verbose_name_plural = _("خرائط حسابات الاعتراف بالإيراد")
        unique_together = ("policy", "currency")

    def __str__(self):
        return f"Account Mapping [{self.policy.code} - {self.currency}]"


class RevenueRecognitionSchedule(models.Model):
    """
    FIN-AR-002: Line-Level Revenue Recognition Schedule Model
    جدول الاستحقاق والاعتراف بالإيراد لبند الفاتورة
    """
    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("ACTIVE", _("نشط")),
        ("FULLY_RECOGNIZED", _("معترف به بالكامل")),
        ("REVERSED", _("معكوس")),
    )

    invoice_item = models.ForeignKey("sale.SalesInvoiceItem", on_delete=models.CASCADE, related_name="revenue_schedules", verbose_name=_("بند الفاتورة"))
    policy = models.ForeignKey(RevenueRecognitionPolicy, on_delete=models.PROTECT, related_name="schedules", verbose_name=_("السياسة المطبقة"))
    policy_version = models.IntegerField(_("إصدار السياسة"), default=1)
    contract_reference = models.CharField(_("مرجع العقد التجاري"), max_length=100, blank=True, null=True)

    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    allocated_transaction_price = models.DecimalField(_("سعر المعاملة المخصص بالعملة الأصلي"), max_digits=15, decimal_places=2)
    recognized_amount = models.DecimalField(_("المبلغ المعترف به تراكمياً"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    deferred_amount = models.DecimalField(_("المبلغ المؤجل المتبقي"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    contract_asset_amount = models.DecimalField(_("مبلغ أصول العقد"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    status = models.CharField(_("حالة الجدول"), max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("جدول الاعتراف بالإيراد")
        verbose_name_plural = _("جداول الاعتراف بالإيراد")
        constraints = [
            models.UniqueConstraint(fields=["invoice_item", "policy", "policy_version"], name="unique_invoice_item_policy_version")
        ]

    def __str__(self):
        return f"RevRec Schedule #{self.id} for InvoiceItem #{self.invoice_item.id} ({self.recognized_amount}/{self.allocated_transaction_price} {self.currency})"


class RevenueRecognitionScheduleLine(models.Model):
    """
    FIN-AR-002: Milestone / Period Recognition Schedule Lines
    أسطر خطة أوقات ومحطات الاعتراف الزمني والإيرادات المؤجلة
    """
    STATUS_CHOICES = (
        ("SCHEDULED", _("مجدول")),
        ("RECOGNIZED", _("تم الاعتراف")),
        ("REVERSED", _("معكوس")),
    )

    schedule = models.ForeignKey(RevenueRecognitionSchedule, on_delete=models.CASCADE, related_name="lines", verbose_name=_("الجدول الرئيسي"))
    sequence = models.IntegerField(_("التسلسل"))
    recognition_date = models.DateField(_("تاريخ المستهدف للاعتراف"))
    accounting_period = models.ForeignKey(AccountingPeriod, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("الفترة المحاسبية Target Period"))

    foreign_amount = models.DecimalField(_("المبلغ بالعملة الأجنبية"), max_digits=15, decimal_places=2)
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))
    functional_amount = models.DecimalField(_("المبلغ الوظيفي (EGP)"), max_digits=15, decimal_places=2)

    status = models.CharField(_("حالة السطر"), max_length=20, choices=STATUS_CHOICES, default="SCHEDULED")

    class Meta:
        verbose_name = _("سطر جدول الاعتراف بالإيراد")
        verbose_name_plural = _("أسطر جدول الاعتراف بالإيراد")
        ordering = ["sequence"]
        indexes = [
            models.Index(fields=["status", "recognition_date"], name="idx_rev_sched_status_date", condition=models.Q(status="SCHEDULED")),
            models.Index(fields=["schedule", "status"]),
        ]


class RevenueRecognitionEntry(models.Model):
    """
    FIN-AR-002: Immutable Revenue Recognition Audit Evidence Log
    سجل التدقيق والإثبات المحاسبي والأحداث المحوكمة للاعتراف بالإيراد
    """
    ENTRY_STATUS_CHOICES = (
        ("POSTED", _("مرحل")),
        ("REVERSED", _("معكوس")),
        ("FAILED", _("فاشل")),
    )

    EVENT_CHOICES = (
        ("DELIVERY_CONFIRMED", _("تأكيد التسليم")),
        ("CUSTOMER_ACCEPTANCE", _("قبول العميل")),
        ("INSTALLATION_COMPLETED", _("إتمام التركيب")),
        ("SERVICE_COMPLETED", _("إتمام الخدمة")),
        ("TIME_MILESTONE", _("محطة زمنية")),
        ("MANUAL_ADJUSTMENT", _("تعديل يدو ي")),
    )

    schedule = models.ForeignKey(RevenueRecognitionSchedule, on_delete=models.PROTECT, related_name="entries", verbose_name=_("جدول الاعتراف"))
    schedule_line = models.ForeignKey(RevenueRecognitionScheduleLine, on_delete=models.SET_NULL, null=True, blank=True, related_name="entries", verbose_name=_("سطر الخطة"))
    processed_event_id = models.CharField(_("معرف الحدث المعالج الفريد"), max_length=100, unique=True)
    recognition_event = models.CharField(_("حدث الاعتراف"), max_length=30, choices=EVENT_CHOICES)
    entry_status = models.CharField(_("حالة القيد/السجل"), max_length=20, choices=ENTRY_STATUS_CHOICES, default="POSTED")

    foreign_amount = models.DecimalField(_("المبلغ بالأجنبي"), max_digits=15, decimal_places=2)
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))
    functional_amount = models.DecimalField(_("المبلغ الوظيفي (EGP)"), max_digits=15, decimal_places=2)

    audit_hash = models.CharField(_("التوقيع المشفر Canonical SHA256"), max_length=64)
    correlation_id = models.UUIDField(_("معرف التتبع الفريد Correlation UUID"), default=uuid.uuid4, editable=False)

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("القيد المحاسبي بالاستاذ"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("المستخدم"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل قيود الاعتراف بالإيراد")
        verbose_name_plural = _("سجلات قيود الاعتراف بالإيراد")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["processed_event_id"], name="unique_processed_event_id")
        ]
        indexes = [
            models.Index(fields=["correlation_id", "created_at"], name="idx_rev_entry_corr_time"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("FIN-AR-002 Immutability Guard: RevenueRecognitionEntry records are strictly INSERT-ONLY and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("FIN-AR-002 Immutability Guard: RevenueRecognitionEntry records cannot be deleted.")

    def __str__(self):
        return f"RevRec Entry [{self.recognition_event}]: #{self.id} ({self.functional_amount} EGP, Hash: {self.audit_hash[:8]}...)"


class RevenueRecognitionReversal(models.Model):
    """
    FIN-AR-002: Revenue Recognition Reversal Log
    سجل تتبع وعكس عمليات الاعتراف بالإيراد السابقة
    """
    original_entry = models.ForeignKey(RevenueRecognitionEntry, on_delete=models.PROTECT, related_name="reversals", verbose_name=_("القيد الأصلي المعكوس"))
    reversal_type = models.CharField(_("نوع العكس"), max_length=50, default="FULL_REVERSAL")
    reversal_amount = models.DecimalField(_("مبلغ العكس الوظيفي (EGP)"), max_digits=15, decimal_places=2)
    reversal_date = models.DateField(_("تاريخ القيد العكسي"), default=timezone.now)
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قيد العكس بالأستاذ"))
    reason = models.TextField(_("سبب العكس"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("أنشئ بواسطة"))
    created_at = models.DateTimeField(_("تاريخ التسجيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("عكس قيد اعتراف بإيراد")
        verbose_name_plural = _("عكوسات قيود الاعتراف بالإيرادات")
        ordering = ["-created_at"]

    def __str__(self):
        return f"RevRec Reversal for Entry #{self.original_entry.id} ({self.reversal_amount} EGP)"
