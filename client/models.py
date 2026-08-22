from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from financial.mixins import MonetaryTransactionMixin



class Customer(models.Model):
    """
    نموذج العميل المحسن مع التكامل مع النظام المرجعي
    """

    CLIENT_TYPES = (
        ("individual", _("فرد")),
        ("company", _("شركة / منشأة")),
        ("government", _("جهة حكومية")),
    )

    CONTACT_FREQUENCY_CHOICES = (
        ("weekly", _("أسبوعي")),
        ("monthly", _("شهري")),
        ("quarterly", _("ربع سنوي")),
        ("yearly", _("سنوي")),
    )

    # المعلومات الأساسية
    name = models.CharField(_("اسم العميل"), max_length=255)
    company_name = models.CharField(
        _("اسم الشركة"),
        max_length=255,
        blank=True,
        help_text=_("اسم الشركة إذا كان العميل شركة"),
    )

    # معلومات الاتصال المحسنة (من النظام المرجعي)
    contact_person = models.CharField(
        _("الشخص المسؤول / جهة الاتصال"),
        max_length=150,
        blank=True,
        null=True,
        help_text=_("اسم الشخص المسؤول أو مندوب التواصل في المؤسسة أو الشركة"),
    )
    phone = models.CharField(
        _("رقم الهاتف"), max_length=50, blank=True
    )
    phone_primary = models.CharField(
        _("رقم الهاتف الأساسي"),
        max_length=20,
        blank=True,
        help_text=_("رقم الهاتف الأساسي للتواصل"),
    )
    phone_secondary = models.CharField(
        _("رقم الهاتف الثانوي"),
        max_length=20,
        blank=True,
        help_text=_("رقم هاتف إضافي للتواصل"),
    )
    email = models.EmailField(_("البريد الإلكتروني"), blank=True, null=True)

    # معلومات العنوان المحسنة
    country = models.CharField(
        _("الدولة"),
        max_length=100,
        blank=True,
        default="مصر",
        help_text=_("دولة إقامة العميل أو مقر المنشأة"),
    )
    city = models.CharField(
        _("المدينة / المحافظة"),
        max_length=100,
        blank=True,
        help_text=_("المدينة أو المحافظة التي يقع فيها العميل"),
    )
    address = models.TextField(_("العنوان"), blank=True, null=True)

    # المعلومات المالية والإدارية
    code = models.CharField(_("كود العميل"), max_length=20, unique=True)
    credit_limit = models.DecimalField(
        _("الحد الائتماني"), max_digits=12, decimal_places=2, default=0
    )
    balance = models.DecimalField(
        _("الرصيد الحالي"), max_digits=12, decimal_places=2, default=0
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    tax_number = models.CharField(
        _("الرقم الضريبي"), max_length=50, blank=True, null=True
    )
    national_id = models.CharField(
        _("الرقم القومي (للأفراد)"),
        max_length=14,
        blank=True,
        null=True,
        help_text=_("الرقم القومي المكون من 14 رقماً للأفراد وفقاً لمنظومة الضرائب المصرية")
    )
    commercial_registry = models.CharField(
        _("السجل التجاري"),
        max_length=50,
        blank=True,
        null=True,
        help_text=_("رقم السجل التجاري للشركات والمؤسسات")
    )
    # العملة الافتراضية المعتمدة
    default_currency = models.ForeignKey(
        'financial.Currency',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("العملة الافتراضية"),
        related_name="customers_default_currency",
        help_text=_("العملة الافتراضية المعتمدة لفتح فواتير ومعاملات هذا العميل تلقائياً")
    )

    # تصنيف الكيان القانوني للعميل
    client_type = models.CharField(
        _("نوع العميل (الكيان القانوني)"),
        max_length=20,
        choices=CLIENT_TYPES,
        default="individual",
        help_text=_("تصنيف الكيان القانوني: فرد (شخص طبيعي) أو شركة أو جهة حكومية"),
    )
    # تمييز العميل (VIP)
    is_vip = models.BooleanField(
        _("عميل مميز (VIP)"),
        default=False,
        help_text=_("تمييز العميل كعميل ذو أولوية خاصة ومعاملة استثنائية"),
    )

    # معلومات إدارة العلاقات (CRM)
    last_contact_date = models.DateTimeField(
        _("تاريخ آخر اتصال"),
        null=True,
        blank=True,
        help_text=_("تاريخ آخر تواصل مع العميل"),
    )
    contact_frequency = models.CharField(
        _("تكرار الاتصال"),
        max_length=20,
        choices=CONTACT_FREQUENCY_CHOICES,
        blank=True,
        help_text=_("معدل التواصل المطلوب مع العميل"),
    )

    # الملاحظات
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    # ربط مع دليل الحسابات
    financial_account = models.OneToOneField(
        "financial.ChartOfAccounts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("الحساب المحاسبي"),
        related_name="customer",
        help_text=_("الحساب المحاسبي المرتبط بهذا العميل في دليل الحسابات"),
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="customers_created",
        null=True,
    )

    class Meta:
        verbose_name = _("عميل")
        verbose_name_plural = _("العملاء")
        ordering = ["name"]

    def __str__(self):
        if getattr(self, "contact_person", None) and self.contact_person:
            return f"{self.name or ''} ({self.contact_person})"
        if getattr(self, "company_name", None) and self.company_name and self.company_name != self.name:
            return f"{self.name or ''} ({self.company_name})"
        return str(self.name or f"Customer {self.pk or ''}")

    def save(self, *args, **kwargs):
        # مزامنة رقم الهاتف الأساسي مع حقل phone القديم
        if self.phone_primary and not self.phone:
            self.phone = self.phone_primary
        elif self.phone and not self.phone_primary:
            self.phone_primary = self.phone

        if not self.default_currency_id:
            try:
                from financial.services.exchange_rate_service import ExchangeRateService
                func_curr = ExchangeRateService.get_functional_currency()
                if func_curr:
                    self.default_currency = func_curr
            except Exception:
                pass
        super().save(*args, **kwargs)

        # مزامنة اسم الحساب المحاسبي في شجرة الحسابات إذا تغير اسم العميل
        if self.financial_account_id and self.name:
            try:
                if self.financial_account.name != self.name:
                    from financial.models import ChartOfAccounts
                    ChartOfAccounts.objects.filter(pk=self.financial_account_id).update(name=self.name)
            except Exception:
                pass

    @property
    def available_credit(self):
        """
        حساب الرصيد المتاح
        """
        return self.credit_limit - self.balance

    @property
    def actual_balance(self):
        """
        حساب المديونية الفعلية (تعتمد على الحقل المخزن المحدث آلياً لمنع N+1 Queries)
        """
        return self.balance

    @property
    def available_prepaid_balance(self):
        """
        Legacy Compatibility Wrapper: حساب الرصيد المسبق المتاح للعميل بالعملة الوظيفية (أو الافتراضية)
        """
        try:
            from financial.services.partner_advance_service import PartnerAdvanceService
            return PartnerAdvanceService.get_available_balance(self, currency=self.default_currency)
        except Exception:
            from sale.models import SalePayment
            from django.db.models import Sum, Subquery, OuterRef, Value, DecimalField
            from django.db.models.functions import Coalesce

            used_subq = (
                SalePayment.objects.filter(
                    customer_payment=OuterRef("pk"), status="posted"
                )
                .values("customer_payment")
                .annotate(s=Sum("amount"))
                .values("s")
            )
            total_free = Decimal("0.00")
            for cp in self.payments.exclude(status="cancelled").annotate(
                used=Coalesce(
                    Subquery(used_subq, output_field=DecimalField()),
                    Value(Decimal("0.00"), output_field=DecimalField()),
                )
            ):
                total_free += max(Decimal("0.00"), cp.amount - cp.used)
            return total_free


class CustomerPayment(MonetaryTransactionMixin, models.Model):
    """
    نموذج لتسجيل المدفوعات المستلمة من العملاء
    """

    PAYMENT_METHODS = (
        ("cash", _("نقدي")),
        ("bank_transfer", _("تحويل بنكي")),
        ("check", _("شيك")),
    )

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        verbose_name=_("العميل"),
        related_name="payments",
    )
    amount = models.DecimalField(_("المبلغ"), max_digits=12, decimal_places=2)
    payment_date = models.DateField(_("تاريخ الدفع"))
    payment_method = models.CharField(
        _("طريقة الدفع"), max_length=20, choices=PAYMENT_METHODS
    )
    reference_number = models.CharField(
        _("رقم المرجع"), max_length=50, blank=True, null=True
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    status = models.CharField(_("الحالة"), max_length=20, default="posted")
    financial_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("الخزينة / البنك المصدر"),
    )
    
    # ربط بأمر الشغل
    work_order = models.ForeignKey(
        "work_order.WorkOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أمر الشغل المرتبط"),
        related_name="payments",
    )

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="customer_payments_created",
        null=True,
    )

    allocated_currency_amount_cached = models.DecimalField(
        _("المبلغ المخصص المخبأ بعملة الدفعة"),
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        null=False,
    )

    class Meta:
        verbose_name = _("مدفوعات العميل")
        verbose_name_plural = _("مدفوعات العملاء")
        ordering = ["-payment_date"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(allocated_currency_amount_cached__lte=models.F("amount")) & models.Q(allocated_currency_amount_cached__gte=Decimal("0.00")),
                name="chk_customer_payment_alloc_valid_range"
            )
        ]

    def save(self, *args, **kwargs):
        self.populate_monetary_fields()
        super().save(*args, **kwargs)

    @property
    def remaining_amount(self) -> Decimal:
        """المبلغ المتبقي المتاح للتخصيص من هذه الدفعة بعملة الدفعة"""
        return max(Decimal("0.00"), self.amount - self.allocated_currency_amount_cached)

    @property
    def allocated_amount(self) -> Decimal:
        """Alias for backward compatibility"""
        return self.allocated_currency_amount_cached

    def __str__(self):
        return f"{self.customer} - {self.amount} - {self.payment_date}"



import uuid
from decimal import Decimal
from django.utils import timezone


class CustomerTransaction(models.Model):
    """
    FIN-AR-003: Customer Open Item Subledger Model
    نموذج أستاذ العملاء الفرعي المعزز بإمكانية التتبع وإدارة الفروق بالعملات الأجنبية
    """
    TYPE_CHOICES = (
        ("INVOICE", _("فاتورة مبيعات")),
        ("CREDIT_NOTE", _("إشعار دائن")),
        ("PAYMENT", _("تحصيل دائن")),
        ("ADVANCE", _("دفعة مقدمة")),
        ("WRITE_OFF", _("إعدام دين")),
    )

    STATUS_CHOICES = (
        ("OPEN", _("مفتوح")),
        ("PARTIAL", _("مسدد جزئياً")),
        ("CLOSED", _("مغلق")),
    )

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="subledger_transactions", verbose_name=_("العميل"))
    transaction_type = models.CharField(_("نوع المعاملة"), max_length=20, choices=TYPE_CHOICES)
    transaction_number = models.CharField(_("رقم المعاملة"), max_length=50)
    reference_type = models.CharField(_("نوع المرجع"), max_length=50, blank=True, null=True, default="")
    reference_id = models.CharField(_("معرف المرجع"), max_length=100, blank=True, null=True, default="")
    issue_date = models.DateField(_("تاريخ الإصدار"))
    due_date = models.DateField(_("تاريخ الاستحقاق"))

    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    foreign_amount = models.DecimalField(_("المبلغ بالعملة الأجنبية"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))
    functional_amount = models.DecimalField(_("المبلغ بالعملة الوظيفية (EGP)"), max_digits=15, decimal_places=2)
    open_amount = models.DecimalField(_("المبلغ المفتوح غير المسدد (EGP)"), max_digits=15, decimal_places=2)
    open_amount_functional = models.DecimalField(_("المبلغ المفتوح الوظيفي (EGP)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    open_amount_foreign = models.DecimalField(_("المبلغ المفتوح غير المسدد (الأصلي)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))

    status = models.CharField(_("حالة البند"), max_length=15, choices=STATUS_CHOICES, default="OPEN")
    journal_entry = models.ForeignKey("financial.JournalEntry", on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("قيد الأستاذ مرتبط"))
    created_at = models.DateTimeField(_("تاريخ التسجيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("معاملة أستاذ العملاء الفرعي")
        verbose_name_plural = _("معاملات أستاذ العملاء الفرعي")
        ordering = ["-issue_date", "-created_at"]
        indexes = [
            models.Index(fields=["customer", "due_date"], name="idx_cust_open_ar_partial", condition=models.Q(status="OPEN")),
        ]

    def __str__(self):
        return f"AR Subledger [{self.transaction_type}] #{self.transaction_number} - {self.customer.name} ({self.open_amount} EGP)"


class ImmutableAllocationAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValueError("FIN-AR-004 Immutability Guard: Bulk UPDATE operations on CustomerAllocationAudit are strictly prohibited.")

    def delete(self):
        raise ValueError("FIN-AR-004 Immutability Guard: Bulk DELETE operations on CustomerAllocationAudit are strictly prohibited.")


class ImmutableAllocationAuditManager(models.Manager):
    def get_queryset(self):
        return ImmutableAllocationAuditQuerySet(self.model, using=self._db)

    def update(self, **kwargs):
        return self.get_queryset().update(**kwargs)

    def delete(self):
        return self.get_queryset().delete()


class CustomerAllocationAudit(models.Model):
    """
    FIN-AR-004: Customer Allocation Audit Evidence Model
    سجل تدقيق وإثبات توزيعات السداد والربط غير القابل للتعديل
    """
    objects = ImmutableAllocationAuditManager()
    TYPE_CHOICES = (
        ("PAYMENT_TO_INVOICE", _("سداد فاتورة")),
        ("CREDIT_NOTE_TO_INVOICE", _("تسوية إشعار دائن")),
        ("ADVANCE_TO_INVOICE", _("تسوية دفعة مقدمة")),
        ("REVERSAL", _("عكس توزيع سداد")),
    )

    STATUS_CHOICES = (
        ("DRAFT", _("مسودة")),
        ("RESERVED", _("محتجز")),
        ("APPLIED", _("مطبق")),
        ("REVERSED", _("معكوس")),
        ("FAILED", _("تعثر")),
    )

    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="allocation_audits", verbose_name=_("العميل"))
    allocation_reference = models.CharField(_("مرجع التوزيع الفريد"), max_length=100, unique=True, default=uuid.uuid4)
    payment_transaction = models.ForeignKey(CustomerTransaction, on_delete=models.PROTECT, db_column="source_transaction_id", related_name="payment_allocations", verbose_name=_("معاملة التحصيل/الإشعار"))
    invoice_transaction = models.ForeignKey(CustomerTransaction, on_delete=models.PROTECT, db_column="target_transaction_id", related_name="invoice_allocations", verbose_name=_("معاملة الفاتورة المستهدفة"))

    source_document_type = models.CharField(_("نوع المستند المصدر"), max_length=50, blank=True, null=True)
    source_document_number = models.CharField(_("رقم المستند المصدر"), max_length=100, blank=True, null=True)
    target_document_type = models.CharField(_("نوع المستند المستهدف"), max_length=50, blank=True, null=True)
    target_document_number = models.CharField(_("رقم المستند المستهدف"), max_length=100, blank=True, null=True)

    allocation_type = models.CharField(_("نوع التوزيع"), max_length=30, choices=TYPE_CHOICES, default="PAYMENT_TO_INVOICE")
    allocated_amount = models.DecimalField(_("المبلغ المخصص بالعملة الأصلي"), max_digits=15, decimal_places=2)
    allocation_currency = models.CharField(_("عملة التوزيع"), max_length=3, default="EGP")
    exchange_rate = models.DecimalField(_("سعر الصرف"), max_digits=12, decimal_places=6, default=Decimal("1.000000"))
    functional_amount = models.DecimalField(_("المبلغ الوظيفي المخصص (EGP)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    realized_fx_difference = models.DecimalField(_("فروق عملة محققة (EGP)"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    allocation_status = models.CharField(_("حالة التوزيع"), max_length=20, choices=STATUS_CHOICES, default="APPLIED")
    reversed_audit = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="reversals", verbose_name=_("سجل التدقيق المعكوس"))
    allocation_date = models.DateField(_("تاريخ التوزيع"), default=timezone.now)
    created_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("أنشئ بواسطة"))
    evidence_hash = models.CharField(_("توقيع إثبات التوزيع SHA256"), max_length=64, blank=True, null=True)
    created_at = models.DateTimeField(_("تاريخ التسجيل"), auto_now_add=True)

    class Meta:
        verbose_name = _("تدقيق توزيعات سداد العملاء")
        verbose_name_plural = _("سجلات تدقيق توزيعات سداد العملاء")
        ordering = ["-allocation_date", "-created_at"]
        indexes = [
            models.Index(fields=["customer", "allocation_date"]),
            models.Index(fields=["allocation_reference", "created_at"], name="idx_cust_alloc_corr_time"),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("FIN-AR-004 Immutability Guard: CustomerAllocationAudit records are strictly INSERT-ONLY and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("FIN-AR-004 Immutability Guard: CustomerAllocationAudit records cannot be deleted.")

    def __str__(self):
        return f"Allocation Audit [{self.allocation_type}]: {self.source_document_number or self.payment_transaction.transaction_number} -> {self.target_document_number or self.invoice_transaction.transaction_number} ({self.allocated_amount} {self.allocation_currency})"


class PaymentTerm(models.Model):
    """
    شروط الدفع المعيارية للعملاء والموردين
    """
    name = models.CharField(_("اسم شرط الدفع"), max_length=100, unique=True)
    code = models.CharField(_("كود الشرط"), max_length=20, unique=True)
    days = models.IntegerField(_("عدد أيام الإمهال"), default=30)
    is_credit = models.BooleanField(_("يعتبر بيعاً ائتمانياً"), default=True)
    discount_percentage = models.DecimalField(_("نسبة خصم التعجيل %"), max_digits=5, decimal_places=2, default=Decimal("0.00"))
    discount_days = models.IntegerField(_("أيام خصم التعجيل"), default=0)
    is_active = models.BooleanField(_("نشط"), default=True)

    class Meta:
        verbose_name = _("شرط دفع")
        verbose_name_plural = _("شروط الدفع")
        ordering = ["days", "name"]

    def __str__(self):
        return f"{self.name} ({self.days} يوم)"


class CustomerCreditStatusHistory(models.Model):
    """
    سجل تتبع حالات الائتمان للعملاء
    """
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True, related_name="credit_status_histories", verbose_name=_("العميل"))
    old_status = models.CharField(_("الحالة السابقة"), max_length=20)
    new_status = models.CharField(_("الحالة الجديدة"), max_length=20)
    reason = models.TextField(_("السبب / الملاحظات"), blank=True, null=True)
    created_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="credit_status_created", verbose_name=_("أنشئ بواسطة"))
    created_at = models.DateTimeField(_("تاريخ التعديل"), auto_now_add=True)

    class Meta:
        verbose_name = _("سجل حالة الائتمان")
        verbose_name_plural = _("سجلات حالة الائتمان")
        ordering = ["-created_at"]


class CustomerCreditProfile(models.Model):
    """
    FIN-AR-001: Customer Credit Governance Profile Model
    الملف المحوكم لترخيص الائتمان وسقوف المخاطر للعملاء
    """
    STATUS_CHOICES = (
        ("ACTIVE", _("نشط")),
        ("WARNING", _("تحذير")),
        ("ON_HOLD", _("معلق")),
        ("BLOCKED", _("محظور")),
    )

    RISK_CHOICES = (
        ("LOW", _("منخفض المخاطر")),
        ("MEDIUM", _("متوسط المخاطر")),
        ("HIGH", _("مرتفع المخاطر")),
    )

    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name="credit_profile", verbose_name=_("العميل"))
    credit_limit = models.DecimalField(_("حد الائتمان المرخص"), max_digits=15, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(_("العملة"), max_length=3, default="EGP")
    payment_terms = models.CharField(_("شروط الدفع النصية"), max_length=50, default="NET_30")
    default_payment_term = models.ForeignKey(PaymentTerm, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("شروط الدفع المعيارية"))
    grace_period_days = models.IntegerField(_("أيام الإمهال التقديرية"), default=0)
    credit_status = models.CharField(_("حالة الائتمان"), max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    risk_category = models.CharField(_("تصنيف المخاطر"), max_length=20, choices=RISK_CHOICES, default="LOW")
    approved_by = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("اعتمد بواسطة"))
    approval_date = models.DateField(_("تاريخ الاعتماد"), null=True, blank=True)
    effective_from = models.DateField(_("تاريخ البدء"), default=timezone.now)
    effective_to = models.DateField(_("تاريخ الانتهاء"), null=True, blank=True)
    next_review_date = models.DateField(_("تاريخ المراجعة الائتمانية القادمة"), null=True, blank=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("ملف الائتمان والحوكمة للعميل")
        verbose_name_plural = _("ملفات الائتمان والحوكمة للعملاء")

    def __str__(self):
        return f"CreditProfile #{self.id} - {self.customer.name} ({self.credit_limit} {self.currency}) [{self.credit_status}]"


class CreditAuditLog(models.Model):
    """
    FIN-AR-001: Immutable Credit Governance Audit Log Model
    سجل تدقيق وتغييرات سقوف الائتمان غير القابل للتعديل
    """
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="credit_audit_logs", verbose_name=_("العميل"))
    old_status = models.CharField(_("الحالة السابقة"), max_length=20)
    new_status = models.CharField(_("الحالة الجديدة"), max_length=20)
    reason = models.TextField(_("السبب / الملاحظات"))
    related_document = models.CharField(_("المستند المرتبط"), max_length=100, blank=True, null=True)
    user = models.ForeignKey("users.User", on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("المستخدم"))
    timestamp = models.DateTimeField(_("التاريخ"), auto_now_add=True)

    class Meta:
        verbose_name = _("تدقيق حوكمة الائتمان")
        verbose_name_plural = _("سجلات تدقيق حوكمة الائتمان")
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("FIN-AR-001 Immutability Guard: CreditAuditLog records are strictly INSERT-ONLY.")
        super().save(*args, **kwargs)
