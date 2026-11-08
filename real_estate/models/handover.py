# -*- coding: utf-8 -*-
"""
PropertyHandoverReceipt - نموذج محضر تسليم واستلام الوحدات العقارية
MWHEBA ERP — Real Estate Wave 3 (Phase 10: Handover & IFRS 15 Revenue Recognition)
"""
import uuid
import hashlib
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService


class PropertyHandoverReceipt(models.Model):
    """
    محضر استلام وتسليم الوحدة العقارية (Physical / Deemed Handover Protocol)
    - ينقل السيطرة الفعلية والقانونية على الوحدة وفق معيار IFRS 15
    - يدعم التسليم الفعلي بموجب محضر موقع أو التسليم الحُكمي بقوة العقد وقانون البناء
    - يوثق قراءات العدادات، المفاتيح، والتوكيلات، ويوثق هاش تحقق مشفر SHA-256 لمنع التلاعب
    """

    class HandoverType(models.TextChoices):
        PHYSICAL = 'PHYSICAL', _('تسليم فعلي ومعاينة ميدانية بمحضر موقع')
        DEEMED = 'DEEMED', _('تسليم حُكمي بقوة العقد والإنذار الرسمي')

    class HandoverStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة محضر')
        PENDING_INSPECTION = 'PENDING_INSPECTION', _('قيد المعاينة والفحص الميداني')
        EXECUTED = 'EXECUTED', _('معتمد ومنفذ رسمياً')
        CANCELLED = 'CANCELLED', _('ملغي')

    receipt_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        blank=True,
        verbose_name=_('رقم محضر التسليم')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.PROTECT,
        related_name='handover_receipts',
        verbose_name=_('العقد العقاري المرتبط')
    )
    unit = models.ForeignKey(
        'real_estate.PropertyUnit',
        on_delete=models.PROTECT,
        related_name='handover_receipts',
        verbose_name=_('الوحدة العقارية')
    )
    handover_type = models.CharField(
        max_length=20,
        choices=HandoverType.choices,
        default=HandoverType.PHYSICAL,
        db_index=True,
        verbose_name=_('نوع التسليم')
    )
    status = models.CharField(
        max_length=20,
        choices=HandoverStatus.choices,
        default=HandoverStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة المحضر')
    )
    handover_date = models.DateField(
        default=timezone.localdate,
        verbose_name=_('تاريخ الاستلام والتسليم')
    )
    legal_notice = models.ForeignKey(
        'real_estate.LegalNotice',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='handover_receipts',
        verbose_name=_('الإخطار القانوني المرتبط (للتسليم الحُكمي)')
    )
    site_engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='inspected_handovers',
        verbose_name=_('مهندس الموقع المشرف على التسليم')
    )
    client_signatory_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name=_('اسم المستلم / الوكيل الحاضر')
    )
    client_signatory_national_id = models.CharField(
        max_length=30,
        blank=True,
        verbose_name=_('الرقم القومي للمستلم')
    )
    power_of_attorney_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('رقم وسنة التوكيل الرسمي (إن وُجد)')
    )

    # قراءات العدادات والمفاتيح
    electric_meter_reading = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('قراءة عداد الكهرباء')
    )
    water_meter_reading = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('قراءة عداد المياه')
    )
    gas_meter_reading = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('قراءة عداد الغاز')
    )
    keys_handed_over_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('عدد المفاتيح المسلمة')
    )
    access_cards_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('عدد كروت الدخول الذكية المسلمة')
    )
    notes = models.TextField(
        blank=True,
        verbose_name=_('ملاحظات وإقرارات الاستلام')
    )

    # الأثر المالي والقيود المرتبطة وفق IFRS 15
    recognized_revenue_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ الإيراد المحقق عند التسليم')
    )
    interim_cogs_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكلفة مبيعات الوحدة التقديرية (Interim COGS)')
    )
    revenue_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='handover_revenue_receipts',
        verbose_name=_('قيد إثبات الإيراد المحقق')
    )
    cogs_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='handover_cogs_receipts',
        verbose_name=_('قيد تكلفة مبيعات الوحدة (WIP Allocation)')
    )

    # التوثيق والتحقق ضد التلاعب
    verification_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        verbose_name=_('هاش التحقق الرقمي المشفر (SHA-256)')
    )
    public_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        verbose_name=_('الرمز العام للتحقق الإلكتروني')
    )
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='executed_handovers',
        verbose_name=_('اعتمده ونفذه')
    )
    executed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ الاعتماد والتنفيذ')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_handovers',
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
        verbose_name = _('محضر استلام وتسليم وحدة')
        verbose_name_plural = _('محاضر استلام وتسليم الوحدات')
        ordering = ['-handover_date', '-id']

    def __str__(self):
        return f"{self.receipt_number or 'HDR-DRAFT'} - {self.unit.unit_code} ({self.get_handover_type_display()})"

    def clean(self):
        super().clean()
        # 1. التحقق من مطابقة الوحدة مع عقد البيع
        if self.contract_id and self.unit_id:
            if self.contract.unit_id != self.unit_id:
                raise ValidationError({
                    'unit': _('الوحدة المختارة لا تتطابق مع الوحدة المحددة في العقد العقاري.')
                })

        # 2. التحقق من حالة العقد
        if self.contract_id:
            if self.contract.status not in [
                self.contract.ContractStatus.ACTIVE,
                self.contract.ContractStatus.COMPLETED
            ]:
                raise ValidationError({
                    'contract': _('لا يمكن إنشاء محضر تسليم لعقد غير سارٍ (الحالة الحالية: %(status)s).') % {
                        'status': self.contract.get_status_display()
                    }
                })

        # 3. التحقق من اشتراطات التسليم الحُكمي (Deemed Handover)
        if self.handover_type == self.HandoverType.DEEMED:
            if not self.legal_notice_id:
                raise ValidationError({
                    'legal_notice': _('التسليم الحُكمي يتطلب ربط إخطار قانوني رسمي معتمد بالاستلام.')
                })

        # 4. التحقق من اشتراطات التسليم الفعلي المكتمل
        if self.handover_type == self.HandoverType.PHYSICAL and self.status == self.HandoverStatus.EXECUTED:
            if not self.client_signatory_name:
                raise ValidationError({
                    'client_signatory_name': _('يلزم تسجيل اسم المستلم أو الوكيل الحاضر للتسليم الفعلي.')
                })

        # 5. صمام أمان الجاهزية الميدانية واكتمال البنود والعيوب الحرجة (Handover Blocker)
        if self.status == self.HandoverStatus.EXECUTED and self.unit_id:
            # التحقق من نسبة إنجاز الوحدة الميدانية (100% إلزامية لكافة الوحدات)
            unit_pct = getattr(self.unit, 'progress_percentage', Decimal('0.00')) or Decimal('0.00')
            if unit_pct < Decimal('100.00'):
                raise ValidationError({
                    'unit': _(
                        'لا يمكن اعتماد التسليم النهائي للوحدة العقارية نظراً لعدم اكتمال الأعمال الميدانية '
                        '(نسبة الإنجاز الحالية: %(progress)s%% والمطلوب: 100%%).'
                    ) % {'progress': unit_pct}
                })

            # التحقق من خلو الوحدة من الملاحظات الفنية الحرجة المانعة للتسليم (CRITICAL_BLOCKER)
            from real_estate.models.engineering import UnitSnagItem
            critical_open_snags = self.unit.snag_items.filter(
                severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER
            ).exclude(
                status=UnitSnagItem.SnagStatus.VERIFIED_BY_ENGINEER
            ).count()

            if critical_open_snags > 0:
                raise ValidationError({
                    'unit': _(
                        'يُحظر اعتماد وتسليم الوحدة لوجود عدد (%(count)s) ملاحظة فنية حرجة مانعة للتسليم '
                        '(CRITICAL_BLOCKER) قيد المعالجة ولم يتم اعتماد تلافيها هندسياً.'
                    ) % {'count': critical_open_snags}
                })

    def generate_verification_hash(self) -> str:
        """
        توليد بصمة تحقق رقمية مشفرة SHA-256 لمنع تزوير محضر التسليم
        """
        exec_id = self.executed_by_id or ""
        payload = (
            f"{self.receipt_number}|{self.contract.contract_number}|{self.unit.unit_code}|"
            f"{self.handover_type}|{self.handover_date}|{self.recognized_revenue_amount}|"
            f"{self.interim_cogs_amount}|{exec_id}"
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        if self.status == self.HandoverStatus.EXECUTED and self.unit_id:
            unit_pct = getattr(self.unit, 'progress_percentage', Decimal('0.00')) or Decimal('0.00')
            if unit_pct < Decimal('100.00'):
                raise ValidationError({
                    'unit': _(
                        'لا يمكن اعتماد التسليم النهائي للوحدة العقارية نظراً لعدم اكتمال الأعمال الميدانية '
                        '(نسبة الإنجاز الحالية: %(progress)s%% والمطلوب: 100%%).'
                    ) % {'progress': unit_pct}
                })
            from real_estate.models.engineering import UnitSnagItem
            if self.unit.snag_items.filter(
                severity=UnitSnagItem.SnagSeverity.CRITICAL_BLOCKER
            ).exclude(status=UnitSnagItem.SnagStatus.VERIFIED_BY_ENGINEER).exists():
                raise ValidationError({
                    'unit': _('يُحظر اعتماد وتسليم الوحدة لوجود ملاحظات فنية حرجة مانعة للتسليم (CRITICAL_BLOCKER).')
                })
        if not self.receipt_number:
            self.receipt_number = SequenceService.get_next_number(
                document_type=DocumentType.UNIT_HANDOVER,
                date=self.handover_date or timezone.localdate()
            )
        if not self.verification_hash and self.status == self.HandoverStatus.EXECUTED:
            self.verification_hash = self.generate_verification_hash()
        super().save(*args, **kwargs)
