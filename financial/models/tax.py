import uuid
import json
import hashlib
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry
from client.models import Customer
from supplier.models import Supplier


class TaxJurisdiction(models.Model):
    """
    FIN-TAX-001 v3.0: Tax Jurisdiction Entity
    النطاق والهيئة الضريبية المختصة
    """
    code = models.CharField(_("كود الهيئة الضريبية"), max_length=50, unique=True)
    name = models.CharField(_("اسم الهيئة الضريبية"), max_length=150)
    country = models.CharField(_("الدولة"), max_length=100, default="Egypt")
    tax_authority = models.CharField(_("اسم المصلحة / الهيئة"), max_length=150, default="مصلحة الضرائب المصرية")
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("النطاق الضريبي")
        verbose_name_plural = _("النطاقات الضريبية")

    def __str__(self):
        return f"{self.name} ({self.code})"


class TaxCode(models.Model):
    """
    FIN-TAX-001 v3.0: Master Tax Code Model
    نموذج أكواد وتصنيفات الضرائب مع نسبة القابلية للاسترداد وتاريخ الإصدارات
    """
    TAX_TYPE_CHOICES = (
        ("VAT", _("ضريبة القيمة المضافة")),
        ("WITHHOLDING", _("ضريبة الخصم والإضافة")),
        ("SALES_TAX", _("ضريبة المبيعات")),
        ("EXCISE", _("ضريبة الجدول / السلع الجدولية")),
        ("ZERO_RATED", _("ضريبة بسعر صفر")),
        ("EXEMPT", _("معفى من الضريبة")),
    )

    TAX_NATURE_CHOICES = (
        ("OUTPUT", _("ضريبة مخرجات (مبيعات / التزام)")),
        ("INPUT", _("ضريبة مدخلات (مشتريات / أصل مخصوم)")),
        ("WITHHOLDING", _("خصم وإضافة (تحصيل/سداد مستقطع)")),
        ("NON_RECOVERABLE", _("ضريبة غير قابلة للاسترداد")),
    )

    code = models.CharField(_("كود الضريبة"), max_length=50, unique=True)
    name = models.CharField(_("اسم الضريبة"), max_length=150)
    version = models.IntegerField(_("إصدار كود الضريبة"), default=1)
    tax_type = models.CharField(_("نوع الضريبة"), max_length=30, choices=TAX_TYPE_CHOICES, default="VAT")
    tax_nature = models.CharField(_("طبيعة الضريبة المحاسبية"), max_length=30, choices=TAX_NATURE_CHOICES, default="OUTPUT")
    eta_tax_type = models.CharField(_("كود الضريبة بمنظومة الفاتورة الإلكترونية (ETA)"), max_length=10, blank=True, null=True, default="T1", help_text=_("مثال: T1 للقيمة المضافة، T4 للخصم تحت الحساب"))

    rate = models.DecimalField(_("نسبة الضريبة %"), max_digits=8, decimal_places=4, default=Decimal("14.0000"))
    recoverability_percentage = models.DecimalField(_("نسبة القابلية للاسترداد %"), max_digits=5, decimal_places=2, default=Decimal("100.00"))
    is_recoverable = models.BooleanField(_("قابلة للاسترداد / الخصم"), default=True)

    effective_from = models.DateField(_("سارية من"), default=timezone.now)
    effective_to = models.DateField(_("سارية إلى"), null=True, blank=True)
    is_default = models.BooleanField(_("افتراضي لنوع الضريبة"), default=False, help_text=_("تحديد هذا الكود كافتراضي لنفس نوع الضريبة"))
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("كود الضريبة")
        verbose_name_plural = _("أكواد الضرائب")

    def save(self, *args, **kwargs):
        if self.is_default:
            TaxCode.objects.filter(tax_type=self.tax_type, is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code} v{self.version} - {self.rate}%)"


class TaxRateHistory(models.Model):
    """
    FIN-TAX-001 v3.0: Tax Rate History Audit Model
    سجل تتبع التغييرات التاريخية لأسعار الضرائب
    """
    tax_code = models.ForeignKey(TaxCode, on_delete=models.CASCADE, related_name="rate_history", verbose_name=_("كود الضريبة"))
    old_rate = models.DecimalField(_("النسبة السابقة %"), max_digits=8, decimal_places=4)
    new_rate = models.DecimalField(_("النسبة الجديدة %"), max_digits=8, decimal_places=4)
    effective_date = models.DateField(_("تاريخ بدء سريان النسبة الجديدة"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("المستخدم"))
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تتبع سعر الضريبة")
        verbose_name_plural = _("سجلات تتبع أسعار الضرائب")
        ordering = ["-created_at"]


class TaxRule(models.Model):
    """
    FIN-TAX-001 v3.0: Configurable Tax Rule Engine Model
    نموذج سياسات وقواعد احتساب وتطبيق الضرائب الحاكمة
    """
    SCOPE_CHOICES = (
        ("GLOBAL", _("شامل عام")),
        ("PRODUCT", _("منتج محدد")),
        ("PRODUCT_CATEGORY", _("فئة منتجات")),
        ("CUSTOMER", _("عميل محدد")),
        ("CUSTOMER_TYPE", _("فئة عملاء")),
        ("SUPPLIER", _("مورد محدد")),
        ("SUPPLIER_TYPE", _("فئة موردين")),
        ("TRANSACTION_TYPE", _("نوع المعاملة")),
        ("LOCATION", _("الموقع / النطاق")),
    )

    code = models.CharField(_("كود القاعدة"), max_length=50, blank=True)
    name = models.CharField(_("اسم القاعدة الضريبية"), max_length=150)
    version = models.IntegerField(_("إصدار القاعدة"), default=1)
    priority = models.IntegerField(_("الأولوية (الرقم الأكبر أعلى أولوية)"), default=10)

    rule_scope = models.CharField(_("نطاق القاعدة الضريبية"), max_length=30, choices=SCOPE_CHOICES, default="GLOBAL")
    scope_value = models.CharField(_("قيمة النطاق المشروط"), max_length=255, blank=True, null=True)

    tax_code = models.ForeignKey(TaxCode, on_delete=models.PROTECT, related_name="rules", verbose_name=_("كود الضريبة"))
    jurisdiction = models.ForeignKey(TaxJurisdiction, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("النطاق الضريبي"))

    effective_from = models.DateField(_("سارية من"), default=timezone.now)
    effective_to = models.DateField(_("سارية إلى"), null=True, blank=True)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("قاعدة تطبيق الضريبة")
        verbose_name_plural = _("قواعد تطبيق الضرائب")
        ordering = ["-priority", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["code", "version"], name="unique_tax_rule_code_version")
        ]

    def save(self, *args, **kwargs):
        if not self.code:
            last_num = TaxRule.objects.count() + 1
            candidate = f"RUL-{last_num:03d}"
            while TaxRule.objects.filter(code=candidate).exists():
                last_num += 1
                candidate = f"RUL-{last_num:03d}"
            self.code = candidate
        super().save(*args, **kwargs)

    def __str__(self):
        return f"TaxRule #{self.code} v{self.version} [Priority: {self.priority}] -> {self.tax_code.code}"


class TaxRuleCondition(models.Model):
    """
    FIN-TAX-001 v3.0: Complex Tax Rule Condition Evaluation Entity
    شروط وقواعد تصفية وتطبيق الضريبة الحاكمة
    """
    OPERATOR_CHOICES = (
        ("EQUAL", _("يساوي")),
        ("NOT_EQUAL", _("لا يساوي")),
        ("IN", _("ينتمي لمجموعة")),
        ("BETWEEN", _("بين قيمتين")),
        ("GREATER_THAN", _("أكبر من")),
        ("LESS_THAN", _("أصغر من")),
    )

    rule = models.ForeignKey(TaxRule, on_delete=models.CASCADE, related_name="conditions", verbose_name=_("القاعدة الضريبية"))
    field_name = models.CharField(_("اسم الحقل المشروط"), max_length=100)
    operator = models.CharField(_("المعامل المنطقي"), max_length=20, choices=OPERATOR_CHOICES, default="EQUAL")
    value = models.CharField(_("القيمة المشروطة"), max_length=255)
    sequence = models.IntegerField(_("التسلسل"), default=1)

    class Meta:
        verbose_name = _("شرط قاعدة ضريبية")
        verbose_name_plural = _("شروط قواعد الضرائب")
        ordering = ["sequence"]

    def __str__(self):
        return f"Condition: {self.field_name} {self.operator} {self.value}"


class TaxRuleEvaluationLog(models.Model):
    """
    FIN-TAX-001 v3.0: Tax Rule Resolution Audit Log Entity
    سجل تتبع وتقييم وتحديد القواعد المستبعدة والمختارة بدقة
    """
    document_type = models.CharField(_("نوع المستند"), max_length=50)
    document_number = models.CharField(_("رقم المستند"), max_length=100)
    candidate_rules = models.JSONField(_("القواعد المرشحة"))
    selected_rule = models.CharField(_("القاعدة المختارة"), max_length=100, null=True, blank=True)
    rejected_rules = models.JSONField(_("القواعد المستبعدة مع أسباب الاستبعاد"))
    priority_score = models.IntegerField(_("درجة الأولوية"), default=0)
    evaluated_at = models.DateTimeField(_("تاريخ التقييم"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تقييم قواعد الضرائب")
        verbose_name_plural = _("سجلات تقييم قواعد الضرائب")
        ordering = ["-evaluated_at"]


class TaxAccountMapping(models.Model):
    """
    FIN-TAX-001 v3.0: Dynamic GL Account Mapping per Tax Code, Nature & Currency
    توجيه الحسابات المحاسبية للضرائب فورياً
    """
    tax_code = models.ForeignKey(TaxCode, on_delete=models.CASCADE, related_name="account_mappings", verbose_name=_("كود الضريبة"))
    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    tax_nature = models.CharField(_("طبيعة الضريبة"), max_length=30, default="OUTPUT")

    debit_account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, null=True, blank=True, related_name="tax_debit_mappings", verbose_name=_("حساب المدين (Debit Account)"))
    credit_account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, null=True, blank=True, related_name="tax_credit_mappings", verbose_name=_("حساب الدائن (Credit Account)"))

    output_tax_account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, null=True, blank=True, related_name="output_tax_mappings", verbose_name=_("حساب ضريبة المخرجات / المبيعات (التزام)"))
    input_tax_account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, null=True, blank=True, related_name="input_tax_mappings", verbose_name=_("حساب ضريبة المدخلات / المشتريات (أصل مسترد)"))
    withholding_tax_account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, null=True, blank=True, related_name="withholding_tax_mappings", verbose_name=_("حساب ضريبة الخصم والإضافة (أصل/التزام)"))

    class Meta:
        verbose_name = _("توجيه حساب الضريبة")
        verbose_name_plural = _("توجيهات حسابات الضرائب")
        unique_together = ("tax_code", "currency", "tax_nature")

    def __str__(self):
        return f"Tax Mapping [{self.tax_code.code} - {self.tax_nature} - {self.currency}]"


class TaxRegistration(models.Model):
    """
    FIN-TAX-001 v3.0: Customer/Supplier Tax Registry Model
    السجل والتسجيل الضريبي لأطراف التعامل (عميل / مورد)
    """
    PARTY_TYPE_CHOICES = (
        ("CUSTOMER", _("عميل")),
        ("SUPPLIER", _("مورد")),
    )

    party_type = models.CharField(_("نوع الطرف"), max_length=20, choices=PARTY_TYPE_CHOICES)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True, related_name="tax_registrations", verbose_name=_("العميل"))
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, null=True, blank=True, related_name="tax_registrations", verbose_name=_("المورد"))

    registration_number = models.CharField(_("رقم التسجيل الضريبي / البطاقة الضريبية"), max_length=100)
    tax_authority = models.CharField(_("المأمورية / الهيئة الضريبية"), max_length=150, blank=True, null=True)

    effective_from = models.DateField(_("تاريخ بدء التسجيل"), default=timezone.now)
    effective_to = models.DateField(_("تاريخ انتهاء التسجيل"), null=True, blank=True)
    status = models.CharField(_("الحالة"), max_length=20, default="ACTIVE")

    class Meta:
        verbose_name = _("تسجيل ضريبي لطرف")
        verbose_name_plural = _("التسجيلات الضريبية لأطراف التعامل")

    def __str__(self):
        party_name = self.customer.name if self.customer else (self.supplier.name if self.supplier else "N/A")
        return f"Tax Reg #{self.registration_number} for {party_name}"


class TaxExemptionCertificate(models.Model):
    """
    FIN-TAX-001 v3.0: Tax Exemption Management Entity
    شهادات الإعفاء الضريبي المحوكمة
    """
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True, related_name="tax_exemptions", verbose_name=_("العميل"))
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, null=True, blank=True, related_name="tax_exemptions", verbose_name=_("المورد"))

    certificate_number = models.CharField(_("رقم شهادة الإعفاء"), max_length=100, unique=True)
    tax_code = models.ForeignKey(TaxCode, on_delete=models.PROTECT, related_name="exemptions", verbose_name=_("كود الضريبة المعفى منها"))

    valid_from = models.DateField(_("صالحة من تاريخ"))
    valid_to = models.DateField(_("صالحة إلى تاريخ"))
    max_quota_amount = models.DecimalField(_("سقف مبلغ الإعفاء المعتمد (إن وجد)"), max_digits=15, decimal_places=2, null=True, blank=True, help_text=_("أقصى قيمة خاضعة للإعفاء"))
    utilized_amount = models.DecimalField(_("المبلغ المستهلك من الإعفاء"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    exemption_reason = models.TextField(_("سبب الإعفاء المعتمد قانوناً"))
    attachment_reference = models.CharField(_("مرجع المرفق / الشهادة"), max_length=255, blank=True, null=True)
    status = models.CharField(_("حالة الشهادة"), max_length=20, default="ACTIVE")

    class Meta:
        verbose_name = _("شهادة إعفاء ضريبي")
        verbose_name_plural = _("شهادات الإعفاء الضريبي")

    def is_valid_on(self, date_val, amount: Decimal = Decimal("0.00")) -> bool:
        if self.status != "ACTIVE":
            return False
        if not (self.valid_from <= date_val <= self.valid_to):
            return False
        if self.max_quota_amount is not None:
            if (self.utilized_amount + amount) > self.max_quota_amount:
                return False
        return True

    def __str__(self):
        return f"Exemption Cert #{self.certificate_number} ({self.tax_code.code})"


class TaxCalculationLine(models.Model):
    """
    FIN-TAX-001 v3.0: Line-Level Tax Calculation Result
    نتيجة احتساب الضريبة لبند المستند
    """
    document_type = models.CharField(_("نوع المستند"), max_length=50)
    document_id = models.IntegerField(_("معرف المستند"))
    document_line_id = models.IntegerField(_("معرف سطر المستند"))

    tax_code = models.ForeignKey(TaxCode, on_delete=models.PROTECT, related_name="calc_lines", verbose_name=_("كود الضريبة"))
    taxable_amount = models.DecimalField(_("المبلغ الخاضع للضريبة (الأصلي)"), max_digits=15, decimal_places=2)
    tax_rate = models.DecimalField(_("نسبة الضريبة المطبقة %"), max_digits=8, decimal_places=4)
    tax_amount = models.DecimalField(_("قيمة الضريبة المحسوبة (الأصلي)"), max_digits=15, decimal_places=2)
    exemption_reason = models.CharField(_("سبب الإعفاء (إن وجد)"), max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = _("سطر حساب الضريبة")
        verbose_name_plural = _("أسطر حساب الضرائب")

    def __str__(self):
        return f"TaxLine [{self.tax_code.code}]: Base {self.taxable_amount} -> Tax {self.tax_amount}"


class TaxEvent(models.Model):
    """
    FIN-TAX-001 v3.0: Independent Tax Domain Event Log Entity
    سجل تتبع الأحداث الضريبية الحاكمة
    """
    event_id = models.UUIDField(_("معرف الحدث"), default=uuid.uuid4, unique=True, editable=False)
    event_type = models.CharField(_("نوع الحدث الضريبي"), max_length=100)
    document_type = models.CharField(_("نوع المستند"), max_length=50)
    document_number = models.CharField(_("رقم المستند"), max_length=100)
    status = models.CharField(_("حالة الحدث"), max_length=20, default="PROCESSED")
    processed_at = models.DateTimeField(_("تاريخ المعالجة"), auto_now_add=True)

    class Meta:
        verbose_name = _("حدث ضريبي")
        verbose_name_plural = _("سجل الأحداث الضريبية")
        ordering = ["-processed_at"]


class TaxDeterminationAudit(models.Model):
    """
    FIN-TAX-001 v3.0: Immutable Tax Determination Audit Evidence Log
    سجل الإثبات والتدقيق الضريبي المحوكم غير القابل للتعديل
    """
    AUDIT_STATUS_CHOICES = (
        ("CALCULATED", _("تم الحساب")),
        ("POSTED", _("مرحل بالقيود")),
        ("REVERSED", _("معكوس")),
        ("FAILED", _("فاشل")),
    )

    document_type = models.CharField(_("نوع المستند"), max_length=50)
    document_id = models.IntegerField(_("معرف المستند"))
    document_number = models.CharField(_("رقم المستند"), max_length=100)

    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("العميل"))
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("المورد"))
    tax_code = models.ForeignKey(TaxCode, on_delete=models.PROTECT, verbose_name=_("كود الضريبة الرئيسي"))

    taxable_amount = models.DecimalField(_("المبلغ الخاضع للضريبة"), max_digits=15, decimal_places=2)
    tax_amount = models.DecimalField(_("إجمالي الضريبة بالأجنبي"), max_digits=15, decimal_places=2)
    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))
    functional_tax_amount = models.DecimalField(_("إجمالي الضريبة الوظيفي (EGP)"), max_digits=15, decimal_places=2)

    audit_status = models.CharField(_("حالة السجل"), max_length=20, choices=AUDIT_STATUS_CHOICES, default="CALCULATED")
    processed_event_id = models.CharField(_("معرف الحدث المعالج الفريد"), max_length=100, unique=True)
    correlation_id = models.UUIDField(_("معرف التتبع الفريد Correlation UUID"), default=uuid.uuid4, editable=False)
    audit_hash = models.CharField(_("التوقيع المشفر Canonical SHA256"), max_length=64)

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قيد الأستاذ"))
    created_at = models.DateTimeField(_("تاريخ التسجيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل تدقيق احتساب الضريبة")
        verbose_name_plural = _("سجلات تدقيق احتساب الضرائب")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["processed_event_id"], name="unique_tax_processed_event_id")
        ]
        indexes = [
            models.Index(fields=["correlation_id", "created_at"], name="idx_tax_audit_corr_time"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("FIN-TAX-001 Immutability Guard: TaxDeterminationAudit records are strictly INSERT-ONLY and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("FIN-TAX-001 Immutability Guard: TaxDeterminationAudit records cannot be deleted.")

    def __str__(self):
        return f"TaxAudit #{self.id} for {self.document_type} #{self.document_number} ({self.functional_tax_amount} EGP, Hash: {self.audit_hash[:8]}...)"


class TaxReversal(models.Model):
    """
    FIN-TAX-001 v3.0: Tax Reversal Log Entity
    سجل تتبع وعكس الضرائب المخصومة / المحصلة
    """
    original_audit = models.ForeignKey(TaxDeterminationAudit, on_delete=models.PROTECT, related_name="reversals", verbose_name=_("السجل الأصلي المعكوس"))
    reversal_amount = models.DecimalField(_("مبلغ الضريبة المعكوس الوظيفي"), max_digits=15, decimal_places=2)
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قيد العكس بالأستاذ"))
    reason = models.TextField(_("سبب العكس"))
    created_at = models.DateTimeField(_("تاريخ العكس"), auto_now_add=True)

    class Meta:
        verbose_name = _("عكس ضريبة")
        verbose_name_plural = _("عكوسات الضرائب")

    def __str__(self):
        return f"Tax Reversal for Audit #{self.original_audit.id} ({self.reversal_amount} EGP)"


class TaxTransactionSnapshot(models.Model):
    """
    FIN-TAX-001 v2.0: Transaction-Time Tax Snapshot Log Entity
    لقطة تجميد بيانات الضريبة والطرف في لحظة تنفيذ المعاملة التجاري
    """
    audit = models.ForeignKey(TaxDeterminationAudit, on_delete=models.CASCADE, related_name="snapshots", verbose_name=_("سجل التدقيق المرتبط"))
    document_type = models.CharField(_("نوع المستند"), max_length=50)
    document_number = models.CharField(_("رقم المستند"), max_length=100)
    customer_name = models.CharField(_("اسم العميل اللحظي"), max_length=255, blank=True, null=True)
    supplier_name = models.CharField(_("اسم المورد اللحظي"), max_length=255, blank=True, null=True)
    tax_registration_number = models.CharField(_("رقم التسجيل الضريبي اللحظي"), max_length=100, blank=True, null=True)
    applied_rule_code = models.CharField(_("كود القاعدة المطبقة"), max_length=100)
    applied_tax_rate = models.DecimalField(_("نسبة الضريبة اللحظية %"), max_digits=8, decimal_places=4)
    captured_at = models.DateTimeField(_("تاريخ التقاط اللقطة"), auto_now_add=True)

    class Meta:
        verbose_name = _("لقطة معاملة ضريبية")
        verbose_name_plural = _("لقطات المعاملات الضريبية")


class TaxExemptionSnapshot(models.Model):
    """
    FIN-TAX-001 v2.0: Transaction-Time Exemption Snapshot Entity
    لقطة تجميد بيانات الإعفاء الضريبي في لحظة المعاملة
    """
    audit = models.ForeignKey(TaxDeterminationAudit, on_delete=models.CASCADE, related_name="exemption_snapshots", verbose_name=_("سجل التدقيق المرتبط"))
    certificate_number = models.CharField(_("رقم شهادة الإعفاء"), max_length=100)
    tax_code_code = models.CharField(_("كود الضريبة المعفى منها"), max_length=50)
    valid_from = models.DateField(_("صالحة من تاريخ"))
    valid_to = models.DateField(_("صالحة إلى تاريخ"))
    exemption_reason = models.TextField(_("سبب الإعفاء"))
    captured_at = models.DateTimeField(_("تاريخ التقاط اللقطة"), auto_now_add=True)

    class Meta:
        verbose_name = _("لقطة إعفاء ضريبي")
        verbose_name_plural = _("لقطات الإعفاءات الضريبية")


class TaxAdjustment(models.Model):
    """
    FIN-TAX-001 v2.0: Tax Debit/Credit Adjustment Model
    تسويات وتعديلات الحصيلة والالتزام الضريبي (إشعارات تسوية ضريبية)
    """
    ADJUSTMENT_TYPE_CHOICES = (
        ("INCREASE", _("زيادة التزام / محصل")),
        ("DECREASE", _("تخفيض التزام / محصل")),
        ("CORRECTION", _("تصحيح خطأ محاسبي")),
    )

    original_audit = models.ForeignKey(TaxDeterminationAudit, on_delete=models.PROTECT, related_name="adjustments", verbose_name=_("السجل الأصلي"))
    adjustment_type = models.CharField(_("نوع التسوية الضريبية"), max_length=20, choices=ADJUSTMENT_TYPE_CHOICES)
    adjustment_amount = models.DecimalField(_("مبلغ التسوية (EGP)"), max_digits=15, decimal_places=2)
    reason = models.TextField(_("سبب التسوية الضريبية"))
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قيد التسوية بالأستاذ"))
    created_at = models.DateTimeField(_("تاريخ التسوية"), auto_now_add=True)

    class Meta:
        verbose_name = _("تسوية ضريبية")
        verbose_name_plural = _("تسويات ضريبية")

    def __str__(self):
        return f"TaxAdjustment [{self.adjustment_type}]: #{self.id} ({self.adjustment_amount} EGP)"
