# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class Checkbook(models.Model):
    """
    دفاتر الشيكات الصادرة المسلمة من البنوك لحسابات الشركة الجارية
    """
    name = models.CharField(max_length=100, verbose_name=_('اسم الدفتر'))
    bank_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        related_name='checkbooks',
        verbose_name=_('الحساب البنكي')
    )
    serial_prefix = models.CharField(max_length=20, blank=True, verbose_name=_('بادئة الأرقام'))
    serial_from = models.BigIntegerField(verbose_name=_('بداية الترقيم التسلسلي'))
    serial_to = models.BigIntegerField(verbose_name=_('نهاية الترقيم التسلسلي'))
    leaf_count = models.PositiveIntegerField(blank=True, verbose_name=_('عدد أوراق الدفتر'))
    current_serial = models.BigIntegerField(blank=True, verbose_name=_('الرقم التسلسلي التالي'))
    is_active = models.BooleanField(default=True, verbose_name=_('نشط'))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='registered_checkbooks',
        verbose_name=_('مسجل الدفتر')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('دفتر شيكات')
        verbose_name_plural = _('دفاتر الشيكات')
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                check=models.Q(serial_to__gte=models.F('serial_from')),
                name='chk_checkbook_range_valid'
            ),
            models.CheckConstraint(
                check=models.Q(current_serial__gte=models.F('serial_from')),
                name='chk_checkbook_current_serial_gte_from'
            )
        ]

    def __str__(self):
        prefix = f"{self.serial_prefix}-" if self.serial_prefix else ""
        return f"{self.name} ({prefix}{self.serial_from} -> {prefix}{self.serial_to})"

    def clean(self):
        super().clean()
        if self.serial_from is not None and self.serial_to is not None:
            if self.serial_to < self.serial_from:
                raise ValidationError(_("نهاية الترقيم التسلسلي يجب أن تكون أكبر من أو تساوي بداية الترقيم."))
            expected_count = self.serial_to - self.serial_from + 1
            if not self.leaf_count:
                self.leaf_count = expected_count
            elif self.leaf_count != expected_count:
                raise ValidationError(_("عدد أوراق الدفتر لا يطابق نطاق الأرقام التسلسلية المحدد."))

        if self.current_serial is None and self.serial_from is not None:
            self.current_serial = self.serial_from

        if self.bank_account_id and self.serial_from is not None and self.serial_to is not None:
            # التحقق من عدم تداخل النطاقات لنفس الحساب البنكي
            overlapping = Checkbook.objects.filter(
                bank_account_id=self.bank_account_id,
                serial_prefix=self.serial_prefix
            ).exclude(pk=self.pk).filter(
                models.Q(serial_from__lte=self.serial_to) & models.Q(serial_to__gte=self.serial_from)
            )
            if overlapping.exists():
                raise ValidationError(_("نطاق أرقام هذا الدفتر يتداخل مع دفتر شيكات آخر مسجل لنفس الحساب البنكي."))

    def save(self, *args, **kwargs):
        if self.serial_from is not None and self.serial_to is not None and not self.leaf_count:
            self.leaf_count = self.serial_to - self.serial_from + 1
        if self.current_serial is None and self.serial_from is not None:
            self.current_serial = self.serial_from
        self.full_clean()
        is_new = self.pk is None
        with transaction.atomic():
            # قفل سجل الحساب البنكي ذرياً لمنع السباق التزامني
            from financial.models import ChartOfAccounts
            ChartOfAccounts.objects.filter(pk=self.bank_account_id).select_for_update().exists()
            super().save(*args, **kwargs)

            # توليد الأوراق الذرية تلقائياً عند الإنشاء لأول مرة
            if is_new and not self.leaves.exists():
                leaves = []
                for serial in range(self.serial_from, self.serial_to + 1):
                    formatted_serial = f"{self.serial_prefix}{serial}" if self.serial_prefix else str(serial)
                    leaves.append(CheckbookLeaf(
                        checkbook=self,
                        serial_number=formatted_serial,
                        status=CheckbookLeaf.LeafStatus.AVAILABLE
                    ))
                CheckbookLeaf.objects.bulk_create(leaves)


class CheckbookLeaf(models.Model):
    """
    أوراق الشيك الصادرة من الدفتر الذري
    """
    class LeafStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', _('متاح للاستخدام')
        ISSUED = 'ISSUED', _('محرر ومسند لشيك')
        VOIDED = 'VOIDED', _('تالف / ملغي في الدفتر')
        CANCELLED = 'CANCELLED', _('ملغي إدارياً')

    checkbook = models.ForeignKey(
        Checkbook,
        on_delete=models.CASCADE,
        related_name='leaves',
        verbose_name=_('الدفتر التابع له')
    )
    serial_number = models.CharField(max_length=50, db_index=True, verbose_name=_('الرقم التسلسلي المطبوع'))
    status = models.CharField(
        max_length=20,
        choices=LeafStatus.choices,
        default=LeafStatus.AVAILABLE,
        db_index=True,
        verbose_name=_('حالة الورقة')
    )
    voided_reason = models.TextField(blank=True, verbose_name=_('سبب الإتلاف أو الإلغاء'))
    voided_image = models.ImageField(
        upload_to='checkbooks/voided/%Y/',
        blank=True,
        null=True,
        verbose_name=_('صورة ورقة الشيك التالفة')
    )

    class Meta:
        verbose_name = _('ورقة دفتر شيكات')
        verbose_name_plural = _('أوراق دفاتر الشيكات')
        unique_together = [('checkbook', 'serial_number')]
        ordering = ['id']

    def __str__(self):
        return f"{self.checkbook.name} - #{self.serial_number} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.status == self.LeafStatus.VOIDED and not self.voided_reason:
            raise ValidationError(_("يجب تدوين سبب إتلاف أو إلغاء ورقة الشيك رسمياً (voided_reason)."))


CheckbookLeafStatus = CheckbookLeaf.LeafStatus
