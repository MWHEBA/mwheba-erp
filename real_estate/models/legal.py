# -*- coding: utf-8 -*-
"""
LegalNotice Model - نموذج الإنذارات والإخطارات القانونية للعقود العقارية
MWHEBA ERP — Real Estate Legal Escalation Pipeline
"""
import hashlib
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class LegalNotice(models.Model):
    """
    سجل الإنذارات والمطالبات القانونية لمتابعة التعثر والتصعيد التعاقدي:
    - يربط العقد والقسط المتعثر بالعميل والشركاء الضامنين.
    - يدعم مراحل التصعيد الأربعة (استباقي، تأخير ودي، إنذار قانوني، فسخ تعاقد).
    - يحفظ البصمة التشفيرية للإنذار وبنية حمولة Meta Graph API v21.0 وقناة التراجع التلقائي (SMS).
    """

    class EscalationStage(models.TextChoices):
        STAGE_1_PRE_DUE = 'STAGE_1_PRE_DUE', _('تنبيه استباقي قبل الاستحقاق (T-7 / T-3)')
        STAGE_2_GRACE_EXPIRED = 'STAGE_2_GRACE_EXPIRED', _('إشعار تأخير واحتساب غرامة (T+10)')
        STAGE_3_FORMAL_DEMAND = 'STAGE_3_FORMAL_DEMAND', _('إنذار رسمي بالسداد على يد محضر (T+30)')
        STAGE_4_RESCISSION_NOTICE = 'STAGE_4_RESCISSION_NOTICE', _('إشعار انفساخ التعاقد وإسقاط الحيازة (T+60)')

    class NoticeChannel(models.TextChoices):
        WHATSAPP = 'WHATSAPP', _('واتساب الأعمال الرسمي (Meta Cloud API)')
        SMS = 'SMS', _('رسالة نصية قصيرة SMS (احتياطي)')
        REGISTERED_MAIL = 'REGISTERED_MAIL', _('بريد مسجل بعلم الوصول')
        COURT_BAILIFF = 'COURT_BAILIFF', _('إنذار رسمي على يد محضر قضائي')

    class NoticeStatus(models.TextChoices):
        DRAFT = 'DRAFT', _('مسودة')
        SENT = 'SENT', _('تم الإرسال بنجاح')
        DELIVERED = 'DELIVERED', _('تم التسليم للمستلم')
        FAILED = 'FAILED', _('فشل الإرسال')
        FALLBACK_TRIGGERED = 'FALLBACK_TRIGGERED', _('تم التحويل للقناة البديلة (SMS)')
        SERVED = 'SERVED', _('تم الإعلان القضائي رسمياً')

    notice_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        verbose_name=_('رقم الإشعار / الإنذار')
    )
    contract = models.ForeignKey(
        'real_estate.PropertyContract',
        on_delete=models.PROTECT,
        related_name='legal_notices',
        verbose_name=_('العقد العقاري')
    )
    installment_item = models.ForeignKey(
        'sale.InstallmentItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='real_estate_legal_notices',
        verbose_name=_('قسط الاستحقاق المتعثر')
    )
    customer = models.ForeignKey(
        'customer.Customer',
        on_delete=models.PROTECT,
        related_name='real_estate_legal_notices',
        verbose_name=_('العميل المستلم / المنذر إليه')
    )
    stage = models.CharField(
        max_length=35,
        choices=EscalationStage.choices,
        default=EscalationStage.STAGE_1_PRE_DUE,
        db_index=True,
        verbose_name=_('مرحلة التصعيد القانوني')
    )
    channel = models.CharField(
        max_length=30,
        choices=NoticeChannel.choices,
        default=NoticeChannel.WHATSAPP,
        db_index=True,
        verbose_name=_('قناة الإرسال الأساسية')
    )
    status = models.CharField(
        max_length=30,
        choices=NoticeStatus.choices,
        default=NoticeStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة الإشعار')
    )
    template_name = models.CharField(
        max_length=100,
        default='re_installment_reminder',
        verbose_name=_('اسم قالب Meta المعتمد')
    )
    recipient_phone = models.CharField(
        max_length=30,
        blank=True,
        default='',
        verbose_name=_('رقم هاتف المستلم')
    )
    meta_payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('بنية حمولة Meta Graph API v21.0')
    )
    meta_message_id = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name=_('معرف رسالة Meta (wamid)')
    )
    fallback_channel_used = models.CharField(
        max_length=30,
        blank=True,
        default='',
        verbose_name=_('القناة البديلة المستخدمة عند التعذر')
    )
    fallback_error_code = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_('كود خطأ Meta الذي استوجب التراجع')
    )
    overdue_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المبلغ الأصلي المستحق')
    )
    overdue_days = models.PositiveIntegerField(
        default=0,
        verbose_name=_('أيام التأخير الفعلية')
    )
    penalty_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('غرامة التأخير التعاقدية المحسوبة')
    )
    total_demanded_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي المبلغ المطالب به')
    )
    cure_deadline_days = models.PositiveIntegerField(
        default=15,
        verbose_name=_('مهلة توفيق الأوضاع والسداد (بالأيام)')
    )
    cure_deadline_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ المهلة القانونية القصوى')
    )
    verification_token = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        verbose_name=_('بصمة التحقق التشفيرية المعتمدة (SHA-256)')
    )
    legal_letter_text = models.TextField(
        blank=True,
        default='',
        verbose_name=_('الصيغة القانونية المعتمدة للإنذار')
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ وتوقيت الإرسال')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_real_estate_legal_notices',
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
        verbose_name = _('إنذار قانوني عقاري')
        verbose_name_plural = _('الإنذارات القانونية العقارية')
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['contract', 'stage'], name='idx_re_notice_ctr_stg'),
            models.Index(fields=['customer', 'status'], name='idx_re_notice_cust_stat'),
            models.Index(fields=['verification_token'], name='idx_re_notice_vtoken'),
        ]

    def compute_verification_token(self) -> str:
        """
        حساب البصمة التشفيرية المعتمدة للإنذار القانوني (SHA-256)
        تدمج كافة المحددات الجوهرية لمنع التلاعب بالإنذارات القضائية
        """
        raw_seed = (
            f"{self.contract_id}:{self.customer_id}:{self.stage}:"
            f"{self.overdue_amount}:{self.penalty_amount}:{self.total_demanded_amount}:"
            f"{self.cure_deadline_days}:{self.cure_deadline_date}"
        )
        return hashlib.sha256(raw_seed.encode('utf-8')).hexdigest()

    def ensure_notice_number(self) -> str:
        """توليد رقم الإشعار ذرياً إذا لم يكن محدداً مسبقاً"""
        if not self.notice_number:
            try:
                from core.services.sequence_service import SequenceService
                from core.enums.document_types import DocumentType
                self.notice_number = SequenceService.get_next_number(
                    document_type=DocumentType.LEGAL_NOTICE,
                    date=timezone.localdate()
                )
            except Exception:
                import uuid
                self.notice_number = f"NOT-{uuid.uuid4().hex[:10].upper()}"
        return self.notice_number

    def clean(self):
        super().clean()
        self.ensure_notice_number()
        self.total_demanded_amount = (self.overdue_amount or Decimal('0.00')) + (self.penalty_amount or Decimal('0.00'))
        if not self.verification_token:
            self.verification_token = self.compute_verification_token()

    def save(self, *args, **kwargs):
        self.ensure_notice_number()
        self.total_demanded_amount = (self.overdue_amount or Decimal('0.00')) + (self.penalty_amount or Decimal('0.00'))
        if not self.verification_token:
            self.verification_token = self.compute_verification_token()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.notice_number} ({self.get_stage_display()}) - {self.customer.name}"
