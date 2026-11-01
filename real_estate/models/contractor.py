# -*- coding: utf-8 -*-
"""
Subcontractor Progress Certificate Model (Wave 2 - Phase 6)
نموذج مستخلص إنجاز أعمال مقاولي الباطن والتشييد
حساب الاستقطاعات، تأمين حسن التنفيذ، استرداد الدفعات المقدمة، ضريبة الخصم والإضافة،
والربط المحكم مع دورة الاعتمادات المؤسسية والقفل التشفيري ضد التعديل بعد الاعتماد.
"""
from decimal import Decimal
import hashlib
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ContractorProgressCertificate(models.Model):
    """
    نموذج مستخلص مقاول الباطن التراكمي (Contractor Progress Certificate)
    """
    class CertificateStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة قيد الإعداد')
        PENDING_APPROVAL = 'PENDING_APPROVAL', _('قيد المراجعة والاعتماد المؤسسي')
        APPROVED = 'APPROVED', _('معتمد نهائياً وجاهز للصرف')
        REJECTED = 'REJECTED', _('مرفوض')
        PAID = 'PAID', _('تم الصرف المالي')
        CANCELLED = 'CANCELLED', _('ملغى')

    certificate_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        verbose_name=_('رقم المستخلص')
    )
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.PROTECT,
        related_name='contractor_certificates',
        verbose_name=_('المشروع العقاري')
    )
    contractor = models.ForeignKey(
        'supplier.Supplier',
        on_delete=models.PROTECT,
        related_name='real_estate_certificates',
        verbose_name=_('المقاول / مقاول الباطن')
    )
    contract_reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('رقم عقد المقاولة / أمر الشغل')
    )
    period_start = models.DateField(
        verbose_name=_('بداية فترة المستخلص')
    )
    period_end = models.DateField(
        verbose_name=_('نهاية فترة المستخلص')
    )

    # الأعمال المنفذة
    gross_certified_work = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الأعمال المنفذة تراكمياً حتى تاريخه')
    )
    previous_certified_work = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الأعمال المعتمدة في المستخلصات السابقة')
    )
    current_period_work = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('أعمال الفترة الحالية المعتمدة')
    )
    materials_on_site = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تشوينات المواد بالموقع المعتمدة')
    )

    # نسب ومبالغ الاستقطاعات
    retention_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        verbose_name=_('نسبة تأمين حسن التنفيذ / الاستقطاع (%)')
    )
    retention_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ تأمين حسن التنفيذ المحتجز')
    )
    advance_payment_recovery = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('استقطاع استرداد الدفعة المقدمة')
    )
    wht_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.00'),
        verbose_name=_('نسبة ضريبة الخصم والإضافة (%)')
    )
    wht_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ ضريبة الخصم والإضافة')
    )
    penalty_deductions = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('غرامات وملاحظات جودة مستقطعة')
    )
    net_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('صافي المستحق للصرف')
    )
    currency = models.ForeignKey(
        'financial.Currency',
        on_delete=models.PROTECT,
        related_name='contractor_certificates',
        verbose_name=_('العملة')
    )
    status = models.CharField(
        max_length=20,
        choices=CertificateStatus.choices,
        default=CertificateStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة المستخلص')
    )

    # الربط المحوكم والاعتمادات المؤسسية
    approval_request = models.ForeignKey(
        'financial.EnterpriseApprovalRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='real_estate_certificates',
        verbose_name=_('طلب الاعتماد المؤسسي المرتبط')
    )
    approval_snapshot_hash = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_('البصمة الرقمية المشفرة لبيانات الاعتماد (Mutation Lock)')
    )
    version = models.PositiveIntegerField(
        default=1,
        verbose_name=_('إصدار المستخلص')
    )
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contractor_certificates',
        verbose_name=_('قيد استحقاق المستخلص')
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_('ملاحظات وتفاصيل الأعمال')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_contractor_certificates',
        verbose_name=_('أنشئ بواسطة')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('تاريخ الإنشاء')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('تاريخ التحديث')
    )

    class Meta:
        verbose_name = _('مستخلص مقاول باطن')
        verbose_name_plural = _('مستخلصات مقاولي الباطن')
        ordering = ['-period_end', '-created_at']

    def __str__(self):
        return f"{self.certificate_number} - {self.contractor.name} ({self.net_amount} {self.currency.code})"

    def compute_amounts(self):
        """
        الحساب الرياضي والهندسي الدقيق لمبالغ المستخلص وفق المعادلة المعيارية:
        current_period_work = gross_certified_work - previous_certified_work
        base_for_retention = current_period_work + materials_on_site
        retention_amount = (base_for_retention * retention_rate / 100)
        wht_amount = (current_period_work * wht_rate / 100)
        net_amount = current_period_work + materials_on_site - retention_amount - advance_payment_recovery - wht_amount - penalty_deductions
        """
        if self.gross_certified_work < self.previous_certified_work:
            raise ValidationError(_("إجمالي الأعمال المنفذة تراكمياً لا يمكن أن يكون أقل من أعمال المستخلصات السابقة."))

        self.current_period_work = (self.gross_certified_work - self.previous_certified_work).quantize(Decimal('0.01'))
        base_for_retention = self.current_period_work + self.materials_on_site
        self.retention_amount = (base_for_retention * self.retention_rate / Decimal('100')).quantize(Decimal('0.01'))
        self.wht_amount = (self.current_period_work * self.wht_rate / Decimal('100')).quantize(Decimal('0.01'))
        self.net_amount = (
            self.current_period_work + 
            self.materials_on_site - 
            self.retention_amount - 
            self.advance_payment_recovery - 
            self.wht_amount - 
            self.penalty_deductions
        ).quantize(Decimal('0.01'))

    def compute_financial_hash(self) -> str:
        """
        توليد البصمة الرقمية المشفرة لحماية البيانات المالية من التعديل بعد الاعتماد
        """
        payload = f"{self.id or 0}:{self.gross_certified_work}:{self.retention_amount}:{self.advance_payment_recovery}:{self.wht_amount}:{self.materials_on_site}:{self.penalty_deductions}:{self.net_amount}:{self.version}"
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def clean(self):
        super().clean()
        self.compute_amounts()
        if self.net_amount < Decimal('0.00'):
            raise ValidationError(_("صافي مبلغ المستخلص لا يمكن أن يكون سالباً."))
