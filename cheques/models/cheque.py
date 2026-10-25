# -*- coding: utf-8 -*-
from decimal import Decimal
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class ChequeType(models.TextChoices):
    RECEIVABLE = "RECEIVABLE", _("شيك قبض (وارد من عميل)")
    PAYABLE = "PAYABLE", _("شيك دفع (صادر لمورد/مصروف)")


class ChequePurpose(models.TextChoices):
    INVOICE_SETTLEMENT = "INVOICE_SETTLEMENT", _("سداد فاتورة قائمة")
    ADVANCE_PAYMENT = "ADVANCE_PAYMENT", _("دفعة مقدمة على الحساب")
    SECURITY_GUARANTEE = "SECURITY_GUARANTEE", _("شيك ضمان / تأمين حسن تنفيذ")


class ChequeStatus(models.TextChoices):
    DRAFT = "DRAFT", _("مسودة")
    IN_PORTFOLIO = "IN_PORTFOLIO", _("في الحافظة / الخزينة (أوراق قبض)")
    UNDER_COLLECTION = "UNDER_COLLECTION", _("برسم التحصيل في البنك")
    COLLECTED = "COLLECTED", _("محصل بالكامل بالبنك")
    PARTIALLY_COLLECTED = "PARTIALLY_COLLECTED", _("محصل جزئياً (وفاء جزئي)")
    BOUNCED = "BOUNCED", _("مرتد / مرفوض بالكامل")
    LEGAL_ACTION = "LEGAL_ACTION", _("محال للشؤون القانونية / إجراء قضائي جنحة شيك")
    LEGAL_SETTLEMENT = "LEGAL_SETTLEMENT", _("تسوية قضائية / سداد بالمحكمة")
    ENDORSED = "ENDORSED", _("مظهر لطرف ثالث / مورد")
    ENDORSED_BOUNCED = "ENDORSED_BOUNCED", _("مرتد بعد التظهير لمورد")
    ISSUED = "ISSUED", _("صادر ومسلم للمستفيد (أوراق دفع)")
    CLEARED = "CLEARED", _("تم الخصم والصرف البنكي (أوراق دفع)")
    CANCELLED = "CANCELLED", _("ملغي / تالف")
    RETURNED_TO_DRAWER = "RETURNED_TO_DRAWER", _("مسترد ومسلم للساحب (لشيكات الضمان)")


class ChequeQuerySet(models.QuerySet):
    def delete(self):
        """حماية شاملة ضد الحذف الجماعي QuerySet.delete()"""
        if self.exclude(status=ChequeStatus.DRAFT).exists():
            raise ValidationError(_("يُحظر حذف أي شيكات ترتب عليها أثر مالي أو خرجت من حالة المسودة. استخدم مسار الإلغاء الرسمي."))
        # التحقق من وجود سجلات تدقيق مرتبطة
        from cheques.models.action_log import ChequeActionLog
        if ChequeActionLog.objects.filter(cheque__in=self).exists():
            raise ValidationError(_("يُحظر حذف أي شيكات ترتب عليها سجلات تدقيق محاسبية."))
        return super().delete()


class ChequeManager(models.Manager):
    def get_queryset(self):
        return ChequeQuerySet(self.model, using=self._db)


class Cheque(models.Model):
    """
    النموذج المركزي للشيكات وأوراق القبض والدفع
    """
    voucher_number = models.CharField(max_length=50, unique=True, db_index=True, verbose_name=_('رقم الإيصال المركزي'))
    cheque_type = models.CharField(max_length=20, choices=ChequeType.choices, db_index=True, verbose_name=_('نوع الشيك'))
    purpose = models.CharField(
        max_length=30,
        choices=ChequePurpose.choices,
        default=ChequePurpose.INVOICE_SETTLEMENT,
        db_index=True,
        verbose_name=_('غرض الشيك')
    )
    status = models.CharField(
        max_length=30,
        choices=ChequeStatus.choices,
        default=ChequeStatus.DRAFT,
        db_index=True,
        verbose_name=_('حالة الشيك')
    )
    is_opening_balance = models.BooleanField(default=False, db_index=True, verbose_name=_('رصيد افتتاحي'))
    opening_batch = models.ForeignKey(
        'financial.OpeningBalanceBatch',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='opening_cheques',
        verbose_name=_('دفعة الرصيد الافتتاحي')
    )
    checkbook_leaf = models.OneToOneField(
        'cheques.CheckbookLeaf',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='cheque',
        verbose_name=_('ورقة دفتر الشيكات')
    )
    cheque_number = models.CharField(max_length=50, db_index=True, verbose_name=_('رقم الشيك الورقي'))
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name=_('مبلغ الشيك الأصلي'))
    collected_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('المبلغ المحصل'))
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'), verbose_name=_('المبلغ المتبقي'))

    currency = models.ForeignKey('financial.Currency', on_delete=models.PROTECT, verbose_name=_('العملة'))
    original_exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal('1.000000'), verbose_name=_('سعر الصرف الأولي'))
    functional_amount = models.DecimalField(max_digits=15, decimal_places=2, blank=True, verbose_name=_('المعادل بالعملة المحلية'))
    book_value_functional = models.DecimalField(max_digits=15, decimal_places=2, blank=True, verbose_name=_('القيمة الدفترية الحالية'))
    remaining_functional = models.DecimalField(max_digits=15, decimal_places=2, blank=True, default=Decimal('0.00'), verbose_name=_('المتبقي بالعملة المحلية'))

    issue_date = models.DateField(verbose_name=_('تاريخ التحرير الورقي'))
    issued_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name=_('تاريخ ووقت الاعتماد والإصدار الفعلي'))
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='issued_cheques',
        verbose_name=_('الموظف المعتمد للإصدار')
    )
    due_date = models.DateField(db_index=True, verbose_name=_('تاريخ الاستحقاق'))
    collection_date = models.DateField(null=True, blank=True, verbose_name=_('تاريخ التحصيل أو الصرف البنكي'))
    cleared_at = models.DateTimeField(null=True, blank=True, verbose_name=_('تاريخ ووقت المقاصة البنكية'))
    cleared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='cleared_cheques',
        verbose_name=_('الموظف المنفذ للتسوية البنكية')
    )

    drawer_bank_name = models.CharField(max_length=150, verbose_name=_('اسم البنك المسحوب عليه'))
    drawer_bank_branch = models.CharField(max_length=150, blank=True, verbose_name=_('فرع البنك'))
    drawer_account_number = models.CharField(max_length=100, blank=True, verbose_name=_('رقم حساب الساحب'))
    drawer_name = models.CharField(max_length=200, verbose_name=_('اسم الساحب'))
    payee_name = models.CharField(max_length=200, verbose_name=_('اسم المستفيد'))

    customer = models.ForeignKey('customer.Customer', null=True, blank=True, on_delete=models.PROTECT, related_name='cheques', verbose_name=_('العميل'))
    supplier = models.ForeignKey('supplier.Supplier', null=True, blank=True, on_delete=models.PROTECT, related_name='cheques', verbose_name=_('المورد'))
    deposit_bank_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='deposited_cheques',
        verbose_name=_('حساب البنك المودع به')
    )
    portfolio_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='portfolio_cheques',
        verbose_name=_('حساب الخزينة / الحافظة')
    )
    cost_center = models.ForeignKey(
        'financial.CostCenter',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='cheques',
        verbose_name=_('مركز التكلفة')
    )

    related_sale = models.ForeignKey('sale.Sale', null=True, blank=True, on_delete=models.SET_NULL, related_name='cheques', verbose_name=_('فاتورة المبيعات المرتبطة'))
    related_purchase = models.ForeignKey('purchase.Purchase', null=True, blank=True, on_delete=models.SET_NULL, related_name='cheques', verbose_name=_('فاتورة المشتريات المرتبطة'))
    related_customer_payment = models.ForeignKey(
        'customer.CustomerPayment',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='related_cheques',
        verbose_name=_('سند مقبوضات العميل')
    )

    legal_case_number = models.CharField(max_length=100, blank=True, verbose_name=_('رقم القضية / المحضر'))
    court_name = models.CharField(max_length=150, blank=True, verbose_name=_('المحكمة المختصة'))
    assigned_lawyer = models.CharField(max_length=150, blank=True, verbose_name=_('المحامي المتابع'))
    legal_referral_date = models.DateField(null=True, blank=True, verbose_name=_('تاريخ الإحالة للشؤون القانونية'))
    legal_custodian = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='held_legal_cheques',
        verbose_name=_('أمين العهدة القضائية للصك')
    )

    front_image = models.ImageField(upload_to='cheques/%Y/%m/', blank=True, null=True, verbose_name=_('صورة وجه الشيك'))
    back_image = models.ImageField(upload_to='cheques/%Y/%m/', blank=True, null=True, verbose_name=_('صورة ظهر الشيك'))
    rejection_slip_image = models.ImageField(upload_to='cheques/rejections/%Y/%m/', blank=True, null=True, verbose_name=_('صورة إشعار الرفض البنكي'))
    is_cross_cheque = models.BooleanField(default=False, verbose_name=_('شيك مسطر'))
    notes = models.TextField(blank=True, verbose_name=_('ملاحظات'))

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='created_cheques',
        verbose_name=_('منشئ السجل')
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    objects = ChequeManager()

    class Meta:
        verbose_name = _('شيك')
        verbose_name_plural = _('الشيكات وأوراق القبض والدفع')
        ordering = ['-due_date', '-id']
        constraints = [
            models.CheckConstraint(check=models.Q(amount__gt=Decimal('0.00')), name='chk_cheque_amount_positive'),
            models.CheckConstraint(check=models.Q(collected_amount__gte=Decimal('0.00')), name='chk_cheque_collected_non_negative'),
            models.CheckConstraint(check=models.Q(remaining_amount__gte=Decimal('0.00')), name='chk_cheque_remaining_non_negative'),
            models.CheckConstraint(check=models.Q(collected_amount__lte=models.F('amount')), name='chk_cheque_collected_lte_total'),
        ]

    def __str__(self):
        return f"{self.get_cheque_type_display()} - #{self.cheque_number} ({self.voucher_number}) - {self.amount} {self.currency.code if self.currency else ''}"

    @property
    def is_guarantee(self) -> bool:
        """مصدر الحقيقة الأوحد: شيك ضمان خارج الميزانية"""
        return self.purpose == ChequePurpose.SECURITY_GUARANTEE

    @property
    def partner_name(self) -> str:
        """اسم الطرف الآخر المتعامل معه بالشيك (عميل أو مورد أو ساحب)"""
        if self.customer_id and self.customer:
            return self.customer.name
        if self.supplier_id and self.supplier:
            return self.supplier.name
        if self.drawer_name:
            return self.drawer_name
        return str(_("غير محدد"))

    @property
    def bank_name(self) -> str:
        """اسم البنك المرتبط بالشيك (سواء حساب البنك المودع به أو المسحوب عليه)"""
        if self.deposit_bank_account:
            return self.deposit_bank_account.name
        return self.drawer_bank_name or "-"

    @property
    def is_advance_payment(self) -> bool:
        """مصدر الحقيقة الأوحد: دفعة مقدمة"""
        return self.purpose == ChequePurpose.ADVANCE_PAYMENT

    def compute_remaining_functional(self) -> Decimal:
        """
        حساب المعادل المحلي للحصة المتبقية بدقة تامة:
        book_value_functional تمثل القيمة الدفترية لكامل الشيك في الأستاذ العام،
        لذلك تُضرب في نسبة المتبقي (remaining_amount / amount) دون أي ازدواج في تطبيق النسبة.
        """
        if not self.amount or self.amount == Decimal('0.00') or not self.remaining_amount or self.remaining_amount == Decimal('0.00'):
            return Decimal('0.00')
        ratio = self.remaining_amount / self.amount
        return (ratio * self.book_value_functional).quantize(Decimal('0.01'))

    def clean(self):
        super().clean()
        if self.amount is not None:
            if self.amount <= Decimal('0.00'):
                raise ValidationError(_("مبلغ الشيك يجب أن يكون أكبر من الصفر."))
            if self.remaining_amount is None or (not self.pk and self.remaining_amount == Decimal('0.00') and (self.collected_amount or Decimal('0.00')) == Decimal('0.00')):
                self.remaining_amount = self.amount - (self.collected_amount or Decimal('0.00'))
            if self.collected_amount is not None and self.collected_amount > self.amount:
                raise ValidationError(_("المبلغ المحصل لا يمكن أن يتجاوز مبلغ الشيك الكلي."))
            if self.remaining_amount is not None and self.remaining_amount < Decimal('0.00'):
                raise ValidationError(_("المبلغ المتبقي لا يمكن أن يكون سالباً."))

        if self.cheque_type == ChequeType.RECEIVABLE and not self.customer_id and not self.is_opening_balance:
            if self.purpose != ChequePurpose.SECURITY_GUARANTEE:
                raise ValidationError(_("يجب تحديد العميل لشيكات القبض."))

        if self.cheque_type == ChequeType.PAYABLE and not self.supplier_id and not self.is_opening_balance:
            if self.purpose != ChequePurpose.SECURITY_GUARANTEE:
                pass  # شيكات الدفع قد تصرف لمصروف عام أو لمورد

    def save(self, *args, **kwargs):
        if not self.voucher_number:
            from core.services.sequence_service import SequenceService
            from core.enums.document_types import DocumentType
            doc_type = DocumentType.CHEQUE_RECEIVABLE if self.cheque_type == ChequeType.RECEIVABLE else DocumentType.CHEQUE_PAYABLE
            self.voucher_number = SequenceService.get_next_number(doc_type, date=self.issue_date)

        # احتساب المبالغ المحلية الأولية
        if self.amount is not None:
            rate = self.original_exchange_rate or Decimal('1.000000')
            calc_func = (self.amount * rate).quantize(Decimal('0.01'))
            if self.functional_amount is None:
                self.functional_amount = calc_func
            if self.book_value_functional is None:
                self.book_value_functional = calc_func
            if self.remaining_amount is None or (not self.pk and self.remaining_amount == Decimal('0.00') and (self.collected_amount or Decimal('0.00')) == Decimal('0.00')):
                self.remaining_amount = self.amount - (self.collected_amount or Decimal('0.00'))

        # سياسة تجميد البيانات المالية بعد الترحيل مع دعم العمليات المعتمدة حصراً (Post-Draft Immutability Guard)
        if self.pk:
            orig = Cheque.objects.filter(pk=self.pk).values(
                'status', 'amount', 'currency_id', 'original_exchange_rate',
                'customer_id', 'supplier_id', 'checkbook_leaf_id', 'purpose', 'voucher_number'
            ).first()
            if orig and orig['status'] != ChequeStatus.DRAFT:
                # 1. فحص تعديل ورقة دفتر الشيكات (استبدال الورقة التالفة حصراً)
                if self.checkbook_leaf_id != orig['checkbook_leaf_id']:
                    if getattr(self, '_authorized_mutation_context', None) != 'REPLACE_RUINED_LEAF':
                        raise ValidationError(_("لا يمكن تعديل ورقة دفتر الشيكات إلا عبر مسار استبدال الورقة التالفة المعتمد (CheckbookService.replace_ruined_leaf)."))

                # 2. فحص تعديل غرض الشيك (تحويل شيك الضمان لشيك تشغيلي حصراً أو التراجع عنه)
                if self.purpose != orig['purpose']:
                    if getattr(self, '_authorized_mutation_context', None) not in ['CONVERT_GUARANTEE', 'REVERSE_CONVERT_GUARANTEE']:
                        raise ValidationError(_("لا يمكن تعديل غرض الشيك إلا عبر مسار تحويل شيك الضمان المعتمد (ChequeService.convert_guarantee_to_operational) أو التراجع عنه."))

                # 3. فحص تعديل المورد (تظهير الشيك حصراً أو التراجع عنه)
                if self.supplier_id != orig['supplier_id']:
                    if getattr(self, '_authorized_mutation_context', None) not in ['ENDORSE', 'REVERSE_ENDORSE']:
                        raise ValidationError(_("لا يمكن تعديل المورد إلا عبر مسار تظهير الشيك المعتمد أو التراجع عنه."))

                # 4. الحقول المالية المجمدة تماماً لمنع التلاعب اليدوي
                immutable_fields = ['amount', 'currency_id', 'original_exchange_rate', 'customer_id', 'voucher_number']
                for f in immutable_fields:
                    val = getattr(self, f) if not f.endswith('_id') else getattr(self, f)
                    if val != orig[f]:
                        raise ValidationError(_(f"لا يمكن تعديل الحقل المالي الجوهري '{f}' لشيك تم ترحيله. يجب استخدام مسار التراجع أو الإلغاء التدقيقي."))

        # التحديث التلقائي الإلزامي لضمان عدم بقاء رصيد دفتري قديم عند التحصيل الجزئي أو إعادة التقييم
        self.remaining_functional = self.compute_remaining_functional()
        if 'update_fields' in kwargs and kwargs['update_fields'] is not None:
            fields_set = set(kwargs['update_fields'])
            fields_set.add('remaining_functional')
            kwargs['update_fields'] = list(fields_set)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != ChequeStatus.DRAFT:
            raise ValidationError(_("لا يمكن حذف شيك ترتب عليه أي أثر محاسبي أو خرج من حالة المسودة. استخدم مسار الإلغاء الرسمي."))
        if self.action_logs.exists():
            raise ValidationError(_("لا يمكن حذف شيك يحتوي على سجلات تدقيق."))
        super().delete(*args, **kwargs)
