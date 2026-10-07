# -*- coding: utf-8 -*-
"""
FIN-CORE-025: CashTransfer Model
نموذج سند التحويل المالي بين الخزن النقدية، الحسابات البنكية، وصناديق العهد
مع حوكمة التحويل المرحلي (In-Transit)، العملات المتعددة، والتحقق التشفيري
"""
import hashlib
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TransferType(models.TextChoices):
    DIRECT = "direct", _("تحويل مباشر فوري")
    IN_TRANSIT = "in_transit", _("تحويل مرحلي في الطريق")


class TransferStatus(models.TextChoices):
    DRAFT = "draft", _("مسودة")
    PENDING_APPROVAL = "pending_approval", _("بانتظار الاعتماد")
    IN_TRANSIT = "in_transit", _("في الطريق تحت التسليم")
    COMPLETED = "completed", _("مكتمل ومرحل")
    RECALLED = "recalled", _("مسترجع للمصدر")
    REJECTED = "rejected", _("مرفوض")
    REVERSED = "reversed", _("معكوس محاسبياً")


class CashTransfer(models.Model):
    """
    سند التحويل المالي المركزي بين الخزن والبنوك والعهد
    """
    # 1. الترقيم والحالة والنوع
    transfer_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_("رقم سند التحويل"),
        help_text=_("الترقيم التسلسلي الذري للسند TRF-YYYY-XXXX")
    )
    transfer_type = models.CharField(
        max_length=20,
        choices=TransferType.choices,
        default=TransferType.DIRECT,
        db_index=True,
        verbose_name=_("نمط التحويل")
    )
    status = models.CharField(
        max_length=20,
        choices=TransferStatus.choices,
        default=TransferStatus.DRAFT,
        db_index=True,
        verbose_name=_("حالة السند")
    )
    transfer_date = models.DateField(
        default=timezone.now,
        db_index=True,
        verbose_name=_("تاريخ التحويل")
    )

    # 2. الحسابات والمقرات ومراكز التكلفة
    from_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        related_name="transfers_sent",
        verbose_name=_("من حساب / خزينة")
    )
    to_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        related_name="transfers_received",
        verbose_name=_("إلى حساب / خزينة")
    )
    transit_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transfers_in_transit",
        verbose_name=_("حساب نقدية في الطريق (11190)")
    )

    from_work_location = models.ForeignKey(
        "hr.WorkLocation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("مقر / فرع الإرسال")
    )
    to_work_location = models.ForeignKey(
        "hr.WorkLocation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("مقر / فرع الاستلام")
    )

    from_cost_center = models.ForeignKey(
        "financial.CostCenter",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("مركز تكلفة المصدر")
    )
    to_cost_center = models.ForeignKey(
        "financial.CostCenter",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("مركز تكلفة المستلم")
    )
    fee_cost_center = models.ForeignKey(
        "financial.CostCenter",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("مركز تكلفة المصاريف والعمولات")
    )
    financial_category = models.ForeignKey(
        "financial.FinancialCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("تصنيف التدفقات النقدية (IAS 7)")
    )

    # 3. المبالغ والعملات وأسعار الصرف
    source_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name=_("المبلغ المسحوب / المحول")
    )
    source_currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("عملة المصدر")
    )
    source_exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("1.000000"),
        verbose_name=_("سعر صرف المصدر للعملة الوظيفية")
    )

    destination_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name=_("المبلغ المودع / المستلم")
    )
    destination_currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("عملة المستلم")
    )
    destination_exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=Decimal("1.000000"),
        verbose_name=_("سعر صرف المستلم للعملة الوظيفية")
    )

    custom_exchange_rate = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("سعر الصرف المباشر المتفق عليه")
    )
    fx_gain_loss_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("فروق أسعار الصرف المحققة")
    )
    rounding_difference = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        default=Decimal("0.0000"),
        verbose_name=_("فروق التقريب المحاسبي (54400)")
    )

    # 4. الرسوم البنكية والضرائب
    transfer_fee = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("العمولة / المصاريف البنكية")
    )
    fee_account = models.ForeignKey(
        "financial.ChartOfAccounts",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("حساب المصاريف البنكية (50200)")
    )
    is_fee_vat_inclusive = models.BooleanField(
        default=False,
        verbose_name=_("العمولة شاملة ضريبة القيمة المضافة")
    )
    fee_vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("14.00"),
        verbose_name=_("نسبة ضريبة القيمة المضافة على العمولة %")
    )
    fee_vat_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("مبلغ ضريبة القيمة المضافة على العمولة (11350)")
    )

    # 5. البيانات المصرفية الرسمية والمطابقة
    bank_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name=_("اسم المصرف / البنك")
    )
    account_number = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name=_("رقم الحساب البنكي")
    )
    iban = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("رقم الآيبان (IBAN)")
    )
    swift_code = models.CharField(
        max_length=30,
        blank=True,
        default="",
        verbose_name=_("كود السويفت (SWIFT / BIC)")
    )
    bank_reference = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        verbose_name=_("المرجع البنكي / رقم العملية")
    )
    bank_slip_attachment = models.FileField(
        upload_to="cash_transfers/slips/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("مرفق إشعار التحويل البنكي")
    )

    # 6. التفقيط اللغوي وفئات النقدية والتوقيع الرقمي
    amount_in_words = models.CharField(
        max_length=500,
        blank=True,
        default="",
        verbose_name=_("المبلغ بالحروف (التفقيط العربي)")
    )
    denominations_breakdown = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("جدول فئات النقدية الورقية المسلمة")
    )
    verification_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        verbose_name=_("التوقيع الرقمي المشفر (SHA-256 Signature)")
    )

    # 7. بيانات مندوب النقل والاستلام في الطريق
    courier_name = models.CharField(
        max_length=150,
        blank=True,
        default="",
        verbose_name=_("اسم مندوب / أمين نقل النقدية")
    )
    courier_id_number = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("رقم تحقيق شخصية المندوب")
    )
    courier_phone = models.CharField(
        max_length=50,
        blank=True,
        default="",
        verbose_name=_("رقم هاتف المندوب")
    )
    received_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("المبلغ المستلم فعلياً")
    )
    discrepancy_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("فارق العجز أو الزيادة عند الاستلام")
    )

    # 8. القيود المحاسبية المرتبطة
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_transfers_dispatch",
        verbose_name=_("قيد الصرف / التحويل المباشر")
    )
    receipt_journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_transfers_receipt",
        verbose_name=_("قيد استلام النقدية في الطريق")
    )
    reversal_journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_transfers_reversal",
        verbose_name=_("قيد العكس / الاسترجاع")
    )

    # 9. التوثيق وسجل التدقيق
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_cash_transfers",
        verbose_name=_("أنشئ بواسطة")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ ووقت الإنشاء")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("تاريخ ووقت آخر تحديث")
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("اعتمد بواسطة")
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ ووقت الاعتماد")
    )

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("استلم وأكد بواسطة")
    )
    received_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ ووقت الاستلام الفعلي")
    )

    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("عكس بواسطة")
    )
    reversed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ ووقت العكس")
    )
    reversal_reason = models.TextField(
        blank=True,
        default="",
        verbose_name=_("سبب عكس السند")
    )
    notes = models.TextField(
        blank=True,
        default="",
        verbose_name=_("بيان وملاحظات التحويل")
    )

    class Meta:
        verbose_name = _("سند تحويل مالي بين الخزن والبنوك")
        verbose_name_plural = _("سندات التحويل المالي بين الخزن والبنوك")
        ordering = ["-transfer_date", "-id"]
        indexes = [
            models.Index(fields=["to_account", "status"], name="idx_trf_to_status"),
            models.Index(fields=["from_account", "transfer_date"], name="idx_trf_from_date"),
            models.Index(fields=["bank_reference", "transfer_date"], name="idx_trf_bank_ref"),
            models.Index(fields=["created_by", "transfer_date"], name="idx_trf_creator_date"),
        ]

    def __str__(self):
        return f"{self.transfer_number} ({self.from_account.name} -> {self.to_account.name}) [{self.get_status_display()}]"

    def clean(self):
        super().clean()
        if self.from_account_id and self.to_account_id and self.from_account_id == self.to_account_id:
            raise ValidationError({"to_account": _("لا يمكن التحويل لنفس الحساب المصدر.")})

        if self.source_amount and self.source_amount <= Decimal("0.00"):
            raise ValidationError({"source_amount": _("مبلغ التحويل يجب أن يكون أكبر من صفر.")})

    def generate_verification_hash(self) -> str:
        """
        توليد توقيع تشفيري SHA-256 للسند
        """
        secret = getattr(settings, "SECRET_KEY", "mwheba-secret-key")
        payload = (
            f"{self.transfer_number}|"
            f"{self.from_account_id}|"
            f"{self.to_account_id}|"
            f"{self.source_amount}|"
            f"{self.destination_amount}|"
            f"{self.transfer_date}|"
            f"{secret}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        if not self.verification_hash and self.transfer_number:
            self.verification_hash = self.generate_verification_hash()
        super().save(*args, **kwargs)

    @property
    def is_completed(self) -> bool:
        return self.status == TransferStatus.COMPLETED

    @property
    def is_in_transit(self) -> bool:
        return self.status == TransferStatus.IN_TRANSIT
