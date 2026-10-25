# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _


class BankChequeLayout(models.Model):
    """
    معايرة أبعاد طباعة الشيكات البنكية بدقة المليمتر
    """
    bank_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        related_name='cheque_layouts',
        verbose_name=_('الحساب البنكي')
    )
    template_name = models.CharField(max_length=100, verbose_name=_('اسم القالب'))
    is_default = models.BooleanField(default=True, verbose_name=_('القالب الافتراضي'))

    paper_width_mm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('210.00'),
        verbose_name=_('عرض ورقة الشيك (ملم)')
    )
    paper_height_mm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('90.00'),
        verbose_name=_('ارتفاع ورقة الشيك (ملم)')
    )

    date_pos_x_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('150.00'), verbose_name=_('موضع التاريخ X (ملم)'))
    date_pos_y_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('15.00'), verbose_name=_('موضع التاريخ Y (ملم)'))
    date_spacing_mm = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_('المسافة بين خانات التاريخ (ملم)'))
    date_format = models.CharField(max_length=20, default='DD/MM/YYYY', verbose_name=_('تنسيق التاريخ'))

    payee_pos_x_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('40.00'), verbose_name=_('موضع المستفيد X (ملم)'))
    payee_pos_y_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('30.00'), verbose_name=_('موضع المستفيد Y (ملم)'))

    amount_digits_pos_x_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('150.00'), verbose_name=_('موضع المبلغ بالأرقام X (ملم)'))
    amount_digits_pos_y_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('30.00'), verbose_name=_('موضع المبلغ بالأرقام Y (ملم)'))

    amount_words_line1_pos_x_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('40.00'), verbose_name=_('موضع التفقيط سطر 1 X (ملم)'))
    amount_words_line1_pos_y_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('42.00'), verbose_name=_('موضع التفقيط سطر 1 Y (ملم)'))

    amount_words_line2_pos_x_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('40.00'), null=True, blank=True, verbose_name=_('موضع التفقيط سطر 2 X (ملم)'))
    amount_words_line2_pos_y_mm = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('50.00'), null=True, blank=True, verbose_name=_('موضع التفقيط سطر 2 Y (ملم)'))

    cross_mark_pos_x_mm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name=_('موضع التسطير X (ملم)'))
    cross_mark_pos_y_mm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name=_('موضع التسطير Y (ملم)'))

    font_size_pt = models.IntegerField(default=10, verbose_name=_('حجم خط الطباعة (pt)'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('معايرة أبعاد طباعة الشيك')
        verbose_name_plural = _('معايرات أبعاد طباعة الشيكات')
        ordering = ['bank_account', '-is_default', 'template_name']

    def __str__(self):
        return f"{self.bank_account.name} - {self.template_name} ({'افتراضي' if self.is_default else ''})"

    def save(self, *args, **kwargs):
        if self.is_default:
            # إلغاء الافتراضي من القوالب الأخرى لنفس الحساب
            BankChequeLayout.objects.filter(bank_account=self.bank_account).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
