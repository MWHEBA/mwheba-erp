"""
نماذج العهد المالية والنقدية المستديمة والمؤقتة وبطاقات العهدة والتسويات والجرد
Enterprise Financial Custody & Petty Cash Models
"""

from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class CustodyAdvanceStatus(models.TextChoices):
    DRAFT = "draft", _("مسودة")
    PENDING_APPROVAL = "pending_approval", _("بانتظار الاعتماد")
    ACTIVE = "active", _("نشطة / جارية")
    PARTIALLY_SETTLED = "partially_settled", _("مسواة جزئياً")
    SETTLED = "settled", _("مسواة بالكامل")
    OVERDUE = "overdue", _("متأخرة عن موعد الاستحقاق")
    WRITTEN_OFF = "written_off", _("معدومة / إعدام استثنائي")
    CANCELLED = "cancelled", _("ملغاة")


class SettlementStatus(models.TextChoices):
    DRAFT = "draft", _("مسودة")
    SUBMITTED = "submitted", _("مقدمة للمراجعة")
    APPROVED = "approved", _("معتمدة")
    POSTED = "posted", _("مرحلة محاسبياً")
    REJECTED = "rejected", _("مرفوضة")
    REVERSED = "reversed", _("معكوسة / ملغاة")


class SettlementLineType(models.TextChoices):
    DIRECT_EXPENSE = "direct_expense", _("مصروف مباشر (نثريات/مشتريات)")
    UNVOUCHERED_PETTY = "unvouchered_petty", _("نثريات بدون فاتورة (إقرار داخلي)")
    SUPPLIER_INVOICE = "supplier_invoice", _("سداد فاتورة مورد مسجلة")
    SUPPLIER_ADVANCE = "supplier_advance", _("دفعة مقدمة لمورد")
    NOTES_PAYABLE = "notes_payable", _("سداد ورقة دفع / شيك تحت الصرف")
    STOCK_RECEIPT_GRNI = "stock_receipt_grni", _("سداد بضاعة مخزنية (GRNI)")
    LABOR_SHEET = "labor_sheet", _("كشف يوميات عمالة مؤقتة بالموقع")
    CUSTOMS_FACILITATION = "customs_facilitation", _("نثريات وإكراميات تخليص جمركي ولوجستيات")
    FUEL_EXPENSE = "fuel_expense", _("مصروف وقود / بنزين سيارات")
    REFUNDABLE_DEPOSIT = "refundable_deposit", _("تأمينات مؤقتة مستردة لدى الغير")
    PURCHASE_REFUND = "purchase_refund", _("استرداد نقدي من مورد (مرتجع)")
    BANK_CHARGE = "bank_charge", _("عمولة سحب آلي ATM / رسوم بنكية")
    GOVERNMENT_FEE = "government_fee", _("رسوم حكومية وسيادية إلكترونية")
    CHECK_DELIVERY = "check_delivery", _("تسليم شيك بنكي لمورد")


class SettlementLineStatus(models.TextChoices):
    PENDING = "pending", _("قيد المراجعة")
    APPROVED = "approved", _("معتمد بالكامل")
    ADJUSTED = "adjusted", _("معتمد بمبلغ معدل")
    REJECTED = "rejected", _("مرفوض")


class PaymentChannel(models.TextChoices):
    CASH = "cash", _("نقداً (كاش)")
    CORPORATE_CARD = "card", _("بطاقة عهدة بنكية (POS / Online)")
    INSTAPAY = "instapay", _("إنستاباي (InstaPay)")
    MOBILE_WALLET = "wallet", _("محفظة إلكترونية (Vodafone Cash, etc.)")
    CHECK = "check", _("شيك بنكي")
    BANK_TRANSFER = "bank_transfer", _("تحويل بنكي مباشر")


class VarianceRouting(models.TextChoices):
    HR_DEDUCTION = "hr_deduction", _("استقطاع من راتب الموظف (HR)")
    PARTNER_ACCOUNT = "partner_account", _("حساب جاري الشريك / المالك")
    EXPENSE_LOSS = "expense_loss", _("تحميل على حساب خسائر وعجز معتمد")
    CARRY_FORWARD = "carry_forward", _("ترحيل على العهدة القادمة")


class EmployeeCustodyAdvance(models.Model):
    """
    نموذج صرف وتغذية العهد المؤقتة للموظفين
    Temporary Advances & Floats
    """

    advance_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("رقم طلب / سند العهدة"),
        help_text=_("ترقيم آلي فريد عبر SequenceService"),
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="custody_advances",
        verbose_name=_("الموظف المستلم للعهدة"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_advances_created",
        verbose_name=_("المستخدم / طالب الصرف"),
    )
    source_treasury = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        related_name="custody_disbursements",
        verbose_name=_("الخزينة / الحساب البنكي المصدر للصرف"),
    )
    work_location = models.ForeignKey(
        "hr.WorkLocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_advances",
        verbose_name=_("مقر العمل / الفرع"),
    )
    cost_center = models.ForeignKey(
        "financial.CostCenter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_advances",
        verbose_name=_("مركز التكلفة الافتراضي"),
    )
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name=_("مبلغ العهدة الأصلي"),
    )
    top_up_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي مبالغ التغذية الإضافية"),
    )
    settled_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي المبالغ المسواة بالمستندات"),
    )
    returned_cash_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي النقدية الفائضة الموردة للخزينة"),
    )
    current_balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("الرصيد المتبقي في ذمة الموظف"),
    )
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        related_name="custody_advances",
        verbose_name=_("عملة العهدة"),
    )
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal("1.000000"),
        verbose_name=_("سعر الصرف وقت الصرف"),
    )
    issue_date = models.DateField(
        default=timezone.now,
        verbose_name=_("تاريخ الصرف"),
    )
    due_date = models.DateField(
        verbose_name=_("تاريخ الاستحقاق المتوقع للتسوية"),
    )
    purpose = models.TextField(
        verbose_name=_("الغرض من العهدة / بيان المأمورية"),
    )
    signed_acknowledgment_file = models.FileField(
        upload_to="custody/acknowledgments/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("إقرار استلام العهدة / سند الأمانة الموقع"),
    )
    status = models.CharField(
        max_length=20,
        choices=CustodyAdvanceStatus.choices,
        default=CustodyAdvanceStatus.ACTIVE,
        verbose_name=_("حالة العهدة"),
        db_index=True,
    )
    is_per_diem_split = models.BooleanField(
        default=False,
        verbose_name=_("صرف عهدة مأمورية سفر مركبة (بدل مقطوع + عهدة فواتير)"),
    )
    per_diem_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("مبلغ بدل السفر اليومي المقطوع المعفى من الفواتير"),
    )
    settlement_principal_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("أصل التمويل الخاضع للتسوية الفاتورية"),
        help_text=_("صافي مبلغ العهدة الخاضع للتسوية بعد استبعاد البدل المقطوع المعفى"),
    )
    refunds_collected_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي المقبوضات النقدية من المرتجعات"),
        help_text=_("المبالغ النقدية المحصلة من مرتجعات الموردين والتي تزيد النقدية بيد الموظف"),
    )
    shortage_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي العجز المحمل على الموظف"),
        help_text=_("مبالغ العجز في العهدة المحولة لذمة الموظف كسلفة رواتب أو استقطاع HR"),
    )
    transferred_out_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي المبالغ المحولة لموظف آخر"),
    )
    transferred_in_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي المبالغ المستلمة بمناقلة من موظف آخر"),
    )
    custody_type = models.CharField(
        max_length=20,
        choices=[
            ("temporary", _("سلفة مؤقتة")),
            ("permanent", _("عهدة مستديمة")),
        ],
        default="temporary",
        verbose_name=_("نوع العهدة"),
        db_index=True,
    )
    custody_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="custody_advances_linked",
        verbose_name=_("حساب الأستاذ العام للعهدة"),
        help_text=_("حساب الأستاذ العام الخاص بالعهدة المستديمة (إن وجد)"),
    )
    imprest_ceiling = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("سقف العهدة المستديمة الافتراضي"),
    )
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_advance_entries",
        verbose_name=_("قيد صرف العهدة اليومي"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_("ملاحظات إضافية"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ الإنشاء"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("تاريخ التحديث"),
    )

    class Meta:
        verbose_name = _("عهدة موظف مؤقتة")
        verbose_name_plural = _("عهد الموظفين المؤقتة")
        ordering = ["-issue_date", "-id"]
        indexes = [
            models.Index(fields=["employee", "status"]),
            models.Index(fields=["status", "due_date"]),
            models.Index(fields=["work_location", "status"]),
        ]
        permissions = [
            ("can_disburse_custody", _("صلاحية صرف وتغذية العهد النقدية")),
            ("can_transfer_custody", _("صلاحية إجراء مناقلة العهد")),
        ]

    def __str__(self):
        return f"{self.advance_number} - {self.employee} ({self.amount} {self.currency.code})"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": _("مبلغ العهدة يجب أن يكون أكبر من الصفر.")})
        if self.pk:
            orig = EmployeeCustodyAdvance.objects.filter(pk=self.pk).first()
            if orig and orig.status != CustodyAdvanceStatus.DRAFT:
                errors = {}
                if self.amount != orig.amount:
                    errors["amount"] = _("حظر حوكمة: لا يجوز تعديل مبلغ العهدة بعد الصرف أو انتقالها من حالة المسودة.")
                if self.currency_id != orig.currency_id:
                    errors["currency"] = _("حظر حوكمة: لا يجوز تغيير عملة العهدة بعد الصرف.")
                if self.source_treasury_id != orig.source_treasury_id:
                    errors["source_treasury"] = _("حظر حوكمة: لا يجوز تغيير الخزينة المصدرة بعد الصرف.")
                if self.employee_id != orig.employee_id:
                    errors["employee"] = _("حظر حوكمة: لا يجوز تغيير الموظف المستلم للعهدة بعد الصرف.")
                if self.custody_type != orig.custody_type:
                    errors["custody_type"] = _("حظر حوكمة: لا يجوز تغيير نوع العهدة بعد الصرف.")
                if errors:
                    raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status not in [CustodyAdvanceStatus.DRAFT, CustodyAdvanceStatus.CANCELLED] or self.journal_entry_id:
            raise ValidationError(
                _("حظر حوكمة: لا يجوز حذف عهدة نشطة أو منصرفة أو لها قيد محاسبي. المسار الوحيد هو الإلغاء أو العكس.")
            )
        super().delete(*args, **kwargs)

    def update_balance(self, save=True):
        """
        إعادة احتساب الرصيد المتبقي وتحديث الحالة تلقائياً
        المعادلة الصامدة:
        الرصيد المتاح = (أصل التمويل الخاضع للتسوية أو المبلغ الأصلي)
                       + التغذية الإضافية
                       + المبالغ المستلمة بمناقلة
                       + المقبوضات النقدية من المرتجعات
                       - المنصرفات المسواة بالمستندات
                       - النقدية الموردة للخزينة
                       - العجز المحمل على الموظف
                       - المبالغ المحولة لموظف آخر
        """
        base_amount = (
            self.settlement_principal_amount
            if self.settlement_principal_amount is not None
            else self.amount
        )
        self.current_balance = (
            base_amount
            + (self.top_up_amount or Decimal("0.00"))
            + (self.transferred_in_amount or Decimal("0.00"))
            + (self.refunds_collected_amount or Decimal("0.00"))
            - (self.settled_amount or Decimal("0.00"))
            - (self.returned_cash_amount or Decimal("0.00"))
            - (self.shortage_amount or Decimal("0.00"))
            - (self.transferred_out_amount or Decimal("0.00"))
        )

        if self.custody_type != "permanent":
            if self.current_balance <= Decimal("0.00") and self.status != CustodyAdvanceStatus.WRITTEN_OFF:
                self.status = CustodyAdvanceStatus.SETTLED
            elif (
                (
                    (self.settled_amount and self.settled_amount > Decimal("0.00"))
                    or (self.returned_cash_amount and self.returned_cash_amount > Decimal("0.00"))
                    or (self.shortage_amount and self.shortage_amount > Decimal("0.00"))
                )
                and self.current_balance > Decimal("0.00")
            ):
                self.status = CustodyAdvanceStatus.PARTIALLY_SETTLED
            elif (
                self.status == CustodyAdvanceStatus.ACTIVE
                and self.due_date
                and self.due_date < timezone.localdate()
                and self.current_balance > Decimal("0.00")
            ):
                self.status = CustodyAdvanceStatus.OVERDUE

        if save and self.pk:
            update_fields = [
                "current_balance",
                "status",
                "settled_amount",
                "returned_cash_amount",
                "refunds_collected_amount",
                "shortage_amount",
                "top_up_amount",
                "transferred_out_amount",
                "transferred_in_amount",
            ]
            self.save(update_fields=update_fields)


class PettyCashSettlement(models.Model):
    """
    نموذج سند تسوية العهدة النقدية والمصروفات
    Petty Cash Settlement & Multi-Line Expense Reconciliation
    """

    settlement_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("رقم سند التسوية"),
        help_text=_("ترقيم آلي فريد عبر SequenceService"),
    )
    custody_advance = models.ForeignKey(
        EmployeeCustodyAdvance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settlements",
        verbose_name=_("العهدة المؤقتة المرتبطة"),
    )
    custody_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="account_settlements",
        verbose_name=_("حساب العهدة المستديمة / البطاقة البنكية"),
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="custody_settlements",
        verbose_name=_("الموظف مقدم التسوية"),
    )
    settlement_date = models.DateField(
        default=timezone.now,
        verbose_name=_("تاريخ سند التسوية"),
    )
    work_location = models.ForeignKey(
        "hr.WorkLocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_settlements",
        verbose_name=_("المقر الرئيسي للتسوية"),
    )
    is_partial = models.BooleanField(
        default=False,
        verbose_name=_("تسوية جزئية"),
        help_text=_("تسوية جزء من العهدة مع بقاء الرصيد المتبقي مستمراً"),
    )
    is_direct_instant = models.BooleanField(
        default=False,
        verbose_name=_("صرف وتسوية فورية مباشرة في خطوة واحدة"),
    )
    is_write_off = models.BooleanField(
        default=False,
        verbose_name=_("إعدام عهدة استثنائي معتمد"),
    )
    total_expenses = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي المصروفات والنثريات"),
    )
    total_supplier_payments = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي سدادات الموردين وأوراق الدفع"),
    )
    total_stock_payments = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي تسويات بضاعة المخزن (GRNI)"),
    )
    total_bank_charges = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي العمولات والرسوم البنكية"),
    )
    total_tax = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي ضريبة القيمة المضافة المستردة"),
    )
    total_wht = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي ضريبة الخصم والتحصيل (WHT)"),
    )
    total_discounts_earned = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي الخصومات المكتسبة"),
    )
    total_settled_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("صافي إجمالي التسوية المعتمدة"),
    )
    cash_returned_to_treasury = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("فائض النقدية المورد فعلياً للخزينة"),
    )
    shortage_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("مبلغ العجز غير المبرر"),
    )
    overage_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("مبلغ الزيادة في العهدة"),
    )
    variance_routing = models.CharField(
        max_length=20,
        choices=VarianceRouting.choices,
        default=VarianceRouting.HR_DEDUCTION,
        verbose_name=_("طريقة توجيه الفروق والعجز"),
    )
    partner_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_variance_settlements",
        verbose_name=_("حساب جاري الشريك (عند التوجيه للشريك)"),
    )
    status = models.CharField(
        max_length=20,
        choices=SettlementStatus.choices,
        default=SettlementStatus.DRAFT,
        verbose_name=_("حالة التسوية"),
        db_index=True,
    )
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_settlement_entries",
        verbose_name=_("قيد اليومية المركب الموحد"),
    )
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="custody_settlements",
        verbose_name=_("عملة التسوية"),
    )
    expenses_absorbed = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("النفقات الممتصة من نقدية العهدة"),
        help_text=_("المبالغ الفعلية الممتصة والمخصومة من رصيد العهدة"),
    )
    refunds_collected = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("المقبوضات النقدية المحصلة من المرتجعات"),
        help_text=_("المبالغ النقدية المقبوضة من الموردين نتيجة المرتجعات"),
    )
    overrun_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("فائض المنصرفات المسدد من جيب الموظف (مستحقات)"),
        help_text=_("المبالغ المصروفة بالزيادة عن رصيد العهدة والمستحقة للموظف"),
    )
    eligible_replenishment_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("مبلغ الاستعاضة المؤهل للصرف"),
        help_text=_("صافي المبلغ المؤهل لاستعاضة صندوق العهدة المستديمة"),
    )
    is_replenished = models.BooleanField(
        default=False,
        verbose_name=_("تمت استعاضة العهدة المستديمة"),
        help_text=_("مؤشر صرف قيد الاستعاضة التعويضي لصندوق العهدة المستديمة"),
    )
    replenishment_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_replenishment_entries",
        verbose_name=_("قيد استعاضة العهدة المستديمة"),
    )
    rejection_reason = models.TextField(
        blank=True,
        verbose_name=_("سبب الرفض المسبب"),
        help_text=_("بيان أسباب رفض التسوية من قبل المراجع أو المدير المالي"),
    )
    reversal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_reversal_entries",
        verbose_name=_("قيد العكس المحاسبي"),
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settlements_submitted",
        verbose_name=_("قدمت بواسطة"),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settlements_approved",
        verbose_name=_("اعتمدت بواسطة"),
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ وتوقيت الاعتماد"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_("ملاحظات وقرار لجنة الاعتماد"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ الإنشاء"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("تاريخ التحديث"),
    )

    class Meta:
        verbose_name = _("سند تسوية عهدة")
        verbose_name_plural = _("سندات تسوية العهد")
        ordering = ["-settlement_date", "-id"]
        indexes = [
            models.Index(fields=["employee", "status"]),
            models.Index(fields=["settlement_date", "status"]),
        ]
        permissions = [
            ("can_post_settlement", _("صلاحية ترحيل تسويات العهد")),
            ("can_reverse_settlement", _("صلاحية العكس المحاسبي لتسويات العهد")),
            ("can_audit_custody", _("صلاحية جرد واعتماد محاضر العهد")),
        ]

    def __str__(self):
        return f"{self.settlement_number} - {self.employee} ({self.total_settled_amount} EGP)"

    def clean(self):
        super().clean()
        if self.cash_returned_to_treasury is not None and self.cash_returned_to_treasury < Decimal("0.00"):
            raise ValidationError({"cash_returned_to_treasury": _("المبلغ المردود للخزينة لا يمكن أن يكون سالباً.")})
        if self.shortage_amount is not None and self.shortage_amount < Decimal("0.00"):
            raise ValidationError({"shortage_amount": _("مبلغ العجز لا يمكن أن يكون سالباً.")})
        if self.custody_advance_id:
            adv = self.custody_advance or EmployeeCustodyAdvance.objects.filter(pk=self.custody_advance_id).first()
            if adv:
                if self.employee_id and self.employee_id != adv.employee_id:
                    raise ValidationError({"employee": _("الموظف في سند التسوية يجب أن يتطابق مع الموظف المستلم للعهدة النقدية.")})
                from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
                expected_acc = adv.custody_account_id or getattr(AccountRoleRegistry.get_account(AccountRoleNames.CUSTODY_TEMPORARY_CONTROL), "id", None)
                if self.custody_account_id and expected_acc and self.custody_account_id != expected_acc:
                    raise ValidationError({"custody_account": _("حساب العهدة في التسوية يجب أن يتطابق مع الحساب المحاسبي للسلفة النقدية المرتبطة.")})
        if self.pk:
            orig = PettyCashSettlement.objects.filter(pk=self.pk).first()
            if orig and (orig.status in [SettlementStatus.POSTED, SettlementStatus.REVERSED] or orig.journal_entry_id) and not getattr(self, "_allow_custody_reversal", False):
                locked_fields = [
                    "custody_advance_id",
                    "custody_account_id",
                    "employee_id",
                    "currency_id",
                    "settlement_date",
                    "total_expenses",
                    "total_supplier_payments",
                    "total_stock_payments",
                    "total_bank_charges",
                    "total_tax",
                    "total_wht",
                    "total_discounts_earned",
                    "total_settled_amount",
                    "cash_returned_to_treasury",
                    "shortage_amount",
                    "overage_amount",
                    "expenses_absorbed",
                    "refunds_collected",
                    "overrun_amount",
                ]
                errors = {}
                for field in locked_fields:
                    if getattr(self, field, None) != getattr(orig, field, None):
                        errors[field] = _("حظر حوكمة: لا يمكن تعديل هذا الحقل المالي بعد ترحيل أو عكس سند التسوية.")
                if self.status != orig.status and (self.status != SettlementStatus.REVERSED or orig.status != SettlementStatus.POSTED):
                    errors["status"] = _("حظر حوكمة: لا يمكن تعديل حالة تسوية مرحلة أو معكوسة إلا عبر العكس المحاسبي المعتمد.")
                if errors:
                    raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status in [SettlementStatus.POSTED, SettlementStatus.REVERSED] or self.journal_entry_id:
            raise ValidationError(
                _("حظر حوكمة: لا يجوز حذف تسوية مرحلة محاسبياً أو معكوسة. يجب إجراء عكس محاسبي (Reversal) للحفاظ على التدقيق.")
            )
        super().delete(*args, **kwargs)


class PettyCashSettlementLineQuerySet(models.QuerySet):
    def update(self, **kwargs):
        for line in self.select_related("settlement"):
            if (
                line.settlement
                and (
                    line.settlement.status in [SettlementStatus.POSTED, SettlementStatus.REVERSED]
                    or line.settlement.journal_entry_id
                )
                and not getattr(line.settlement, "_allow_custody_reversal", False)
            ):
                raise ValidationError(_("حظر حوكمة: لا يمكن تعديل بنود تسوية مرحلة أو معكوسة محاسبياً."))
        return super().update(**kwargs)

    def delete(self):
        for line in self.select_related("settlement"):
            if (
                line.settlement
                and (
                    line.settlement.status in [SettlementStatus.POSTED, SettlementStatus.REVERSED]
                    or line.settlement.journal_entry_id
                )
                and not getattr(line.settlement, "_allow_custody_reversal", False)
            ):
                raise ValidationError(_("حظر حوكمة: لا يمكن حذف بنود من تسوية مرحلة أو معكوسة محاسبياً."))
        return super().delete()


class PettyCashSettlementLine(models.Model):
    """
    بنود وسطور سند تسوية العهدة التفصيلية
    Petty Cash Settlement Line Items
    """

    settlement = models.ForeignKey(
        PettyCashSettlement,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("سند التسوية الرئيسي"),
    )
    line_number = models.PositiveIntegerField(
        default=1,
        verbose_name=_("رقم السطر"),
    )
    line_type = models.CharField(
        max_length=30,
        choices=SettlementLineType.choices,
        default=SettlementLineType.DIRECT_EXPENSE,
        verbose_name=_("نوع المعاملة / البند"),
    )
    status = models.CharField(
        max_length=20,
        choices=SettlementLineStatus.choices,
        default=SettlementLineStatus.APPROVED,
        verbose_name=_("حالة اعتماد البند"),
    )
    rejection_reason = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("سبب الرفض أو تعديل المبلغ"),
    )
    payment_channel = models.CharField(
        max_length=20,
        choices=PaymentChannel.choices,
        default=PaymentChannel.CASH,
        verbose_name=_("طريقة وسيلة الدفع"),
    )
    rrn_reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("الرقم المرجعي للتحويل / RRN"),
        help_text=_("الرقم المرجعي لتحويلات إنستاباي أو المحافظ الإلكترونية أو نقاط البيع POS"),
    )
    check_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("رقم الشيك / ورقة الدفع"),
    )
    expense_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="settlement_expense_lines",
        verbose_name=_("حساب المصروف"),
    )
    target_work_location = models.ForeignKey(
        "hr.WorkLocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settlement_lines",
        verbose_name=_("المقر المستفيد من المصروف"),
    )
    cost_center = models.ForeignKey(
        "financial.CostCenter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="settlement_lines",
        verbose_name=_("مركز التكلفة"),
    )
    project_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name=_("اسم أو رقم المشروع"),
    )
    supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_payments",
        verbose_name=_("المورد المسجل"),
    )
    supplier_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name=_("اسم المورد / الجهة (للمشتريات العابرة)"),
    )
    supplier_tax_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name=_("الرقم الضريبي للمورد"),
        help_text=_("9 أرقام للتحقق الضريبي الرسمي"),
    )
    invoice_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("رقم فاتورة المورد / الإيصال"),
    )
    invoice_date = models.DateField(
        default=timezone.now,
        verbose_name=_("تاريخ الفاتورة"),
    )
    purchase_invoice = models.ForeignKey(
        "purchase.Purchase",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_settlement_lines",
        verbose_name=_("فاتورة المشتريات المرتبطة"),
    )
    applied_supplier_advance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("الدفعة المقدمة المخصومة للمورد"),
    )
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        related_name="settlement_lines",
        verbose_name=_("عملة الفاتورة"),
    )
    foreign_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("المبلغ بالعملة الأجنبية"),
    )
    exchange_rate = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=Decimal("1.000000"),
        verbose_name=_("سعر الصرف المعتمد للسطر"),
    )
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        verbose_name=_("المبلغ الإجمالي بالفاتورة (شامل الضريبة)"),
    )
    approved_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("المبلغ المعتمد للصرف"),
    )
    tax_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("مبلغ ضريبة القيمة المضافة المستردة"),
    )
    wht_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("نسبة ضريبة الخصم والتحصيل %"),
    )
    wht_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("مبلغ ضريبة الخصم والتحصيل (WHT)"),
    )
    discount_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("مبلغ الخصم المكتسب الفوري"),
    )
    is_unvouchered = models.BooleanField(
        default=False,
        verbose_name=_("مصروف نثريات بدون فاتورة ضريبية"),
    )
    is_lost_receipt_affidavit = models.BooleanField(
        default=False,
        verbose_name=_("إقرار فقدان / تعذر فاتورة أصلية (غير معتمد ضريبياً)"),
    )
    receipt_file = models.FileField(
        upload_to="custody/receipts/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("ملف الفاتورة / الإيصال المرفق (PDF أو صورة)"),
    )
    receipt_image = models.ImageField(
        upload_to="custody/receipts/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("صورة الفاتورة / الإيصال الممسوح ضوئياً"),
    )
    description = models.TextField(
        verbose_name=_("بيان وتفاصيل المصروف"),
    )
    government_service_code = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("رقم أمر الدفع / رمز الخدمة الحكومية"),
    )
    customs_bl_container = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("رقم بوليصة الشحن / الحاوية الجمركية"),
    )
    vehicle_plate_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("رقم لوحة السيارة (لمصروفات الوقود)"),
    )
    odometer_reading = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("قراءة عداد الكيلومترات"),
    )
    fuel_liters = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("عدد لترات الوقود"),
    )

    class Meta:
        verbose_name = _("بند تسوية عهدة")
        verbose_name_plural = _("بنود تسوية العهد")
        ordering = ["settlement", "line_number"]
        indexes = [
            models.Index(fields=["supplier_tax_id", "invoice_number", "invoice_date"]),
            models.Index(fields=["expense_account", "status"]),
        ]

    objects = PettyCashSettlementLineQuerySet.as_manager()

    def __str__(self):
        return f"{self.settlement.settlement_number} - سطر {self.line_number} ({self.amount} EGP)"

    def clean(self):
        super().clean()
        if self.settlement_id:
            settlement = getattr(self, "settlement", None) or PettyCashSettlement.objects.filter(pk=self.settlement_id).first()
            if (
                settlement
                and (
                    settlement.status in [SettlementStatus.POSTED, SettlementStatus.REVERSED]
                    or settlement.journal_entry_id
                )
                and not getattr(settlement, "_allow_custody_reversal", False)
            ):
                if not self.pk:
                    raise ValidationError(_("حظر حوكمة: لا يمكن إضافة بنود جديدة لتسوية مرحلة أو معكوسة محاسبياً."))
                else:
                    raise ValidationError(_("حظر حوكمة: لا يمكن تعديل بنود تسوية مرحلة أو معكوسة محاسبياً."))

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        settlement = getattr(self, "settlement", None) or (PettyCashSettlement.objects.filter(pk=self.settlement_id).first() if self.settlement_id else None)
        if settlement and (
            settlement.status in [SettlementStatus.POSTED, SettlementStatus.REVERSED]
            or settlement.journal_entry_id
        ) and not getattr(settlement, "_allow_custody_reversal", False):
            raise ValidationError(_("حظر حوكمة: لا يمكن حذف بند من تسوية مرحلة محاسبياً أو معكوسة."))
        super().delete(*args, **kwargs)


class CustodyTransfer(models.Model):
    """
    نموذج التحويل والمناقلة المعتمدة بين عهد الموظفين
    Custody Peer-to-Peer Transfers
    """

    transfer_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("رقم سند التحويل"),
    )
    from_employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="custody_transfers_sent",
        verbose_name=_("الموظف المحول منه"),
    )
    to_employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="custody_transfers_received",
        verbose_name=_("الموظف المحول إليه"),
    )
    from_advance = models.ForeignKey(
        EmployeeCustodyAdvance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_out",
        verbose_name=_("العهدة المحول منها"),
    )
    to_advance = models.ForeignKey(
        EmployeeCustodyAdvance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_in",
        verbose_name=_("العهدة المحول إليها"),
    )
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name=_("المبلغ المحول"),
    )
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        related_name="custody_transfers",
        verbose_name=_("العملة"),
    )
    transfer_date = models.DateField(
        default=timezone.now,
        verbose_name=_("تاريخ التحويل"),
    )
    status = models.CharField(
        max_length=20,
        choices=CustodyAdvanceStatus.choices,
        default=CustodyAdvanceStatus.ACTIVE,
        verbose_name=_("حالة التحويل"),
    )
    signed_transfer_file = models.FileField(
        upload_to="custody/transfers/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("محضر التحويل الموقع من الطرفين"),
    )
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custody_transfer_entries",
        verbose_name=_("قيد التحويل المحاسبي"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_("سبب التحويل والمناقلة"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ الإنشاء"),
    )

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": _("مبلغ التحويل يجب أن يكون أكبر من الصفر.")})
        if self.from_employee_id and self.to_employee_id and self.from_employee_id == self.to_employee_id:
            raise ValidationError({"to_employee": _("لا يمكن إجراء مناقلة لنفس الموظف.")})
        if self.from_advance_id:
            adv = getattr(self, "from_advance", None) or EmployeeCustodyAdvance.objects.filter(pk=self.from_advance_id).first()
            if adv:
                if self.from_employee_id and adv.employee_id != self.from_employee_id:
                    raise ValidationError({"from_advance": _("السلفة المصدر المحددة لا تخص الموظف المسلّم.")})
                if self.currency_id and adv.currency_id != self.currency_id:
                    raise ValidationError({"currency": _("عملة المناقلة يجب أن تطابق عملة السلفة المصدر.")})
        if self.to_advance_id:
            to_adv = getattr(self, "to_advance", None) or EmployeeCustodyAdvance.objects.filter(pk=self.to_advance_id).first()
            if to_adv:
                if self.to_employee_id and to_adv.employee_id != self.to_employee_id:
                    raise ValidationError({"to_advance": _("السلفة المستقبلة المحددة لا تخص الموظف المستلم.")})
                if self.currency_id and to_adv.currency_id != self.currency_id:
                    raise ValidationError({"currency": _("عملة المناقلة يجب أن تطابق عملة السلفة المستقبلة.")})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("تحويل ومناقلة عهدة")
        verbose_name_plural = _("تحويلات ومناقلات العهد")
        ordering = ["-transfer_date", "-id"]

    def __str__(self):
        return f"{self.transfer_number} - من {self.from_employee} إلى {self.to_employee} ({self.amount})"

    def delete(self, *args, **kwargs):
        if self.journal_entry_id:
            raise ValidationError(_("حظر حوكمة: لا يجوز حذف مناقلة عهدة مرحلة محاسبياً ولها قيد يومية."))
        super().delete(*args, **kwargs)


class PettyCashCount(models.Model):
    """
    نموذج محضر الجرد الفعلي للعهدة النقدية
    Petty Cash Count & Surprise Cash Audit
    """

    count_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("رقم محضر الجرد"),
    )
    custody_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cash_counts",
        verbose_name=_("حساب العهدة المستديمة / الخزينة"),
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="custody_counts",
        verbose_name=_("الموظف المسؤول عن الصندوق"),
    )
    count_date = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("تاريخ وتوقيت الجرد الفعلي بالدقيقة"),
    )
    auditor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="custody_audits_conducted",
        verbose_name=_("القائم بالجرد (المراجع الداخلي)"),
    )
    gl_balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        verbose_name=_("الرصيد الدفتري المسجل في السيستم"),
    )
    actual_cash_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        verbose_name=_("النقدية الفعلية الموجودة بالدرج"),
    )
    pending_vouchers_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("إجمالي الفواتير والإيصالات المعلقة تحت التسوية"),
    )
    variance_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("مبلغ الفارق (عجز / زيادة)"),
    )
    variance_type = models.CharField(
        max_length=20,
        choices=(
            ("matched", _("مطابق تماماً")),
            ("shortage", _("عجز في النقدية")),
            ("overage", _("زيادة في النقدية")),
        ),
        default="matched",
        verbose_name=_("نتيجة الجرد"),
    )
    denomination_breakdown = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("تفقيط فئات النقدية المعدودة"),
        help_text=_("مثال: {'200': 10, '100': 5, '50': 2}"),
    )
    signed_count_file = models.FileField(
        upload_to="custody/counts/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("محضر الجرد الورقي الموقع"),
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_("ملاحظات وتوصيات المراجع"),
    )
    status = models.CharField(
        max_length=20,
        choices=(
            ("draft", _("مسودة")),
            ("approved", _("معتمد")),
            ("adjusted", _("تمت تسوية الفروق")),
        ),
        default="approved",
        verbose_name=_("حالة المحضر"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ التسجيل"),
    )

    class Meta:
        verbose_name = _("محضر جرد عهدة نقدية")
        verbose_name_plural = _("محاضر جرد العهد النقدية")
        ordering = ["-count_date", "-id"]

    def __str__(self):
        return f"{self.count_number} - {self.employee} ({self.variance_type})"
