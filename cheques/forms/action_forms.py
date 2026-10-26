# -*- coding: utf-8 -*-
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from django.db import models
from financial.models import ChartOfAccounts
from financial.services.treasury_security_service import TreasurySecurityService
from supplier.models import Supplier
from cheques.models import (
    Cheque,
    ChequeType,
    ChequeStatus,
    ChequeBatchDeposit,
    ChequePurpose,
    ChequeInvoiceAllocation,
    AllocationStatus,
)
from sale.models import Sale


class ChequeActionBaseForm(forms.Form):
    """
    النموذج الأساسي لإجراءات الشيكات مع دعم مفتاح منع التكرار الحتمي (Idempotency)
    """
    idempotency_key = forms.CharField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get('idempotency_key'):
            import uuid
            self.initial['idempotency_key'] = f"IDEM-{uuid.uuid4().hex[:12]}"


class ChequeDepositActionForm(ChequeActionBaseForm):
    """
    نموذج إيداع الشيك برسم التحصيل بالبنك (DEPOSIT)
    """
    deposit_bank_account = forms.ModelChoiceField(
        label=_('حساب البنك المودع به'),
        queryset=ChartOfAccounts.objects.filter(is_active=True, is_leaf=True),
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
        required=True
    )
    action_date = forms.DateField(
        label=_('تاريخ تسليم الشيك للبنك'),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=True
    )
    notes = forms.CharField(
        label=_('ملاحظات الإيداع'),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.cheque = kwargs.pop('cheque', None)
        super().__init__(*args, **kwargs)
        # فلترة الحسابات البنكية بحسب صلاحية المستخدم
        if self.user and not (self.user.is_superuser or getattr(self.user, 'is_financial_manager', False)):
            accessible = TreasurySecurityService.get_user_accessible_treasuries(self.user, action='deposit')
            if accessible.exists():
                self.fields['deposit_bank_account'].queryset = accessible

        if self.cheque and self.cheque.deposit_bank_account:
            self.initial['deposit_bank_account'] = self.cheque.deposit_bank_account


class ChequeCollectActionForm(ChequeActionBaseForm):
    """
    نموذج إثبات التحصيل البنكي الكلي أو الجزئي (COLLECT)
    """
    amount_collected = forms.DecimalField(
        label=_('المبلغ المحصل فعلياً (بعملة الشيك)'),
        max_digits=15,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        required=True
    )
    value_date = forms.DateField(
        label=_('تاريخ القيمة البنكي الفعلي (Value Date)'),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=True
    )
    exchange_rate = forms.DecimalField(
        label=_('سعر الصرف الفعلي للتحصيل'),
        max_digits=18,
        decimal_places=6,
        initial=Decimal('1.000000'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
        required=True
    )
    bank_charges = forms.DecimalField(
        label=_('العمولات والمصاريف البنكية المقتطعة'),
        max_digits=12,
        decimal_places=2,
        initial=Decimal('0.00'),
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        required=False
    )
    bank_charges_vat = forms.DecimalField(
        label=_('ضريبة القيمة المضافة على المصاريف (14%)'),
        max_digits=12,
        decimal_places=2,
        initial=Decimal('0.00'),
        min_value=Decimal('0.00'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        required=False
    )
    deposit_bank_account = forms.ModelChoiceField(
        label=_('حساب البنك المحصل به'),
        queryset=ChartOfAccounts.objects.filter(is_active=True, is_leaf=True),
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
        required=False
    )
    notes = forms.CharField(
        label=_('ملاحظات التحصيل'),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.cheque = kwargs.pop('cheque', None)
        super().__init__(*args, **kwargs)
        if self.cheque:
            self.initial['amount_collected'] = self.cheque.remaining_amount
            if self.cheque.original_exchange_rate:
                self.initial['exchange_rate'] = self.cheque.original_exchange_rate
            if self.cheque.deposit_bank_account:
                self.initial['deposit_bank_account'] = self.cheque.deposit_bank_account

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount_collected')
        rate = cleaned_data.get('exchange_rate')
        charges = cleaned_data.get('bank_charges') or Decimal('0.00')
        vat = cleaned_data.get('bank_charges_vat') or Decimal('0.00')

        # فحص ما إذا كان الطلب إعادة محاولة لعملية تحصيل نجحت مسبقاً بنفس مفتاح عدم التكرار
        user_key = (self.data.get('idempotency_key') or '').strip()
        is_idempotent_replay = False
        if user_key and self.cheque:
            from cheques.models import ChequeActionLog, ChequeActionType
            from cheques.services.accounting_service import ChequeAccountingService
            existing_log = ChequeActionLog.objects.filter(idempotency_key=user_key).first()
            if existing_log:
                deposit_bank = cleaned_data.get('deposit_bank_account') or self.cheque.deposit_bank_account
                deposit_bank_id = deposit_bank.id if deposit_bank else None
                current_hash = ChequeAccountingService._compute_payload_hash(
                    cheque_id=self.cheque.id,
                    action_type=ChequeActionType.COLLECT,
                    amount_collected=amount,
                    exchange_rate=rate,
                    bank_charges=charges,
                    bank_charges_vat=vat,
                    bank_account_id=deposit_bank_id,
                    deposit_bank_account_id=deposit_bank_id,
                    value_date=cleaned_data.get('value_date'),
                )
                if (
                    existing_log.cheque_id != self.cheque.id
                    or existing_log.action != ChequeActionType.COLLECT
                    or existing_log.request_payload_hash != current_hash
                ):
                    self.add_error(
                        None,
                        _("تعارض في مفتاح عدم التكرار: المفتاح مستخدم مسبقاً لعملية أخرى أو بمعلمات مختلفة.")
                    )
                else:
                    is_idempotent_replay = True

        if self.cheque and amount is not None and not is_idempotent_replay:
            if amount > self.cheque.remaining_amount:
                self.add_error(
                    'amount_collected',
                    _('المبلغ المحصل ({amt}) يتجاوز الرصيد المتبقي من الشيك ({rem}).').format(
                        amt=amount,
                        rem=self.cheque.remaining_amount
                    )
                )

        if rate is not None and rate <= Decimal('0.000000'):
            self.add_error('exchange_rate', _('سعر الصرف يجب أن يكون أكبر من الصفر.'))

        # التحقق من أن صافي النقدية للبنك لا يقل عن الصفر
        if amount and rate:
            gross = (amount * rate).quantize(Decimal('0.01'))
            if (charges + vat) > gross:
                self.add_error('bank_charges', _('إجمالي المصاريف والضريبة يتجاوز المبلغ المحصل بالكامل.'))

        return cleaned_data


class ChequeBounceActionForm(ChequeActionBaseForm):
    """
    نموذج تسجيل ارتداد الشيك ورفضه بنكياً (BOUNCE)
    """
    action_date = forms.DateField(
        label=_('تاريخ إشعار الرفض البنكي'),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=True
    )
    bounce_reason = forms.CharField(
        label=_('سبب الرفض والارتداد الإلزامي'),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': _('مثال: عدم كفاية الرصيد، عدم مطابقة التوقيع، شيك متقادم...')
        }),
        required=True
    )
    rejection_notice_image = forms.ImageField(
        label=_('صورة إشعار الرفض البنكي'),
        widget=forms.FileInput(attrs={'class': 'form-control'}),
        required=False
    )
    notes = forms.CharField(
        label=_('ملاحظات إضافية'),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False
    )

    def clean_bounce_reason(self):
        reason = self.cleaned_data.get('bounce_reason', '').strip()
        if len(reason) < 3:
            raise ValidationError(_('يرجى توضيح سبب الرفض البنكي بدقة.'))
        return reason


class ChequeEndorseActionForm(ChequeActionBaseForm):
    """
    نموذج تظهير شيك قبض لمورد (ENDORSE)
    """
    supplier = forms.ModelChoiceField(
        label=_('المورد المظهر إليه الشيك'),
        queryset=Supplier.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
        required=True
    )
    action_date = forms.DateField(
        label=_('تاريخ التظهير والتسليم'),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=True
    )
    notes = forms.CharField(
        label=_('ملاحظات التظهير / مرجع الاتفاق'),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False
    )


class ChequeReversalActionForm(ChequeActionBaseForm):
    """
    نموذج التراجع التدقيقي عن آخر حركة للشيك (LIFO REVERSAL)
    """
    reason = forms.CharField(
        label=_('سبب التراجع التدقيقي الإلزامي'),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('أدخل سبب التراجع بالتفصيل (خطأ في المبلغ، إيداع في بنك خطأ)...')
        }),
        required=True
    )

    def clean_reason(self):
        reason = self.cleaned_data.get('reason', '').strip()
        if len(reason) < 5:
            raise ValidationError(_('سبب التراجع إلزامي ويجب ألا يقل عن 5 أحرف لحماية سلامة التدقيق المالي.'))
        return reason


class ChequeConvertGuaranteeActionForm(ChequeActionBaseForm):
    """
    نموذج اعتماد تحويل شيك ضمان إلى شيك تشغيلي (CONVERT_GUARANTEE)
    """
    new_purpose = forms.ChoiceField(
        label=_('الغرض التشغيلي الجديد'),
        choices=[
            (ChequePurpose.INVOICE_SETTLEMENT, _('سداد فاتورة قائمة')),
            (ChequePurpose.ADVANCE_PAYMENT, _('دفعة مقدمة على الحساب')),
        ],
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
        initial=ChequePurpose.INVOICE_SETTLEMENT,
        required=True
    )
    approval_notes = forms.CharField(
        label=_('مبررات واعتماد تحويل الضمان للتحصيل'),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('أدخل أسباب مصادرة أو تحويل شيك الضمان للتحصيل المالي...')
        }),
        required=True
    )


class ChequeBatchDepositForm(forms.Form):
    """
    نموذج إنشاء حافظة إيداع شيكات مجمعة بالبنك
    """
    bank_account = forms.ModelChoiceField(
        label=_('حساب البنك المودع به الحافظة'),
        queryset=ChartOfAccounts.objects.filter(is_active=True, is_leaf=True),
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
        required=True
    )
    deposit_date = forms.DateField(
        label=_('تاريخ تسليم الحافظة للبنك'),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=True
    )
    cheques = forms.ModelMultipleChoiceField(
        label=_('الشيكات المحددة للإيداع في الحافظة'),
        queryset=Cheque.objects.none(),
        widget=forms.SelectMultiple(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
        required=True
    )
    notes = forms.CharField(
        label=_('ملاحظات الحافظة'),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['cheques'].queryset = Cheque.objects.filter(
            cheque_type=ChequeType.RECEIVABLE,
            status=ChequeStatus.IN_PORTFOLIO,
        ).exclude(purpose=ChequePurpose.SECURITY_GUARANTEE)
        if self.user and not (self.user.is_superuser or getattr(self.user, 'is_financial_manager', False)):
            accessible = TreasurySecurityService.get_user_accessible_treasuries(self.user, action='deposit')
            if accessible.exists():
                self.fields['bank_account'].queryset = accessible

    def clean_cheques(self):
        cheques = self.cleaned_data.get('cheques')
        if not cheques or cheques.count() == 0:
            raise ValidationError(_('يجب اختيار شيك واحد على الأقل في الحافظة.'))
        return cheques


class ChequeClearActionForm(ChequeActionBaseForm):
    """
    نموذج إثبات صرف وخصم شيك الدفع الصادر من الحساب البنكي (CLEAR)
    مع دعم سعر الصرف الفعلي لحساب وتوليد فروق أسعار الصرف المحققة
    """
    clearing_date = forms.DateField(
        label=_('تاريخ الخصم الفعلي بالبنك (Value Date)'),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=True
    )
    exchange_rate = forms.DecimalField(
        label=_('سعر الصرف الفعلي عند الخصم'),
        max_digits=18,
        decimal_places=6,
        initial=Decimal('1.000000'),
        min_value=Decimal('0.000001'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
        required=False
    )
    bank_account = forms.ModelChoiceField(
        label=_('حساب البنك المخصوم منه'),
        queryset=ChartOfAccounts.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
        required=False
    )
    notes = forms.CharField(
        label=_('ملاحظات الصرف والخصم'),
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': _('أي ملاحظات على عملية الصرف البنكي...')}),
        required=False
    )

    def clean_exchange_rate(self):
        rate = self.cleaned_data.get('exchange_rate')
        if not rate:
            if self.cheque and self.cheque.original_exchange_rate:
                return self.cheque.original_exchange_rate
            return Decimal('1.000000')
        return rate

    def clean_bank_account(self):
        bank_acc = self.cleaned_data.get('bank_account')
        if not bank_acc and self.cheque:
            fallback = self.cheque.deposit_bank_account
            if not fallback and getattr(self.cheque, 'checkbook_leaf', None) and self.cheque.checkbook_leaf.checkbook:
                fallback = self.cheque.checkbook_leaf.checkbook.bank_account
            if fallback:
                bank_acc = fallback

        if not bank_acc:
            raise ValidationError(_("يجب تحديد حساب بنكي صالح للصرف والمقاصة."))

        # التحقق من عدم استخدام حسابات مراقبة أوراق القبض أو أوراق الدفع
        try:
            from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
            rec_ctrl = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_RECEIVABLE_CONTROL)
            pay_ctrl = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_PAYABLE_CONTROL)
            if bank_acc.id in [rec_ctrl.id, pay_ctrl.id]:
                raise ValidationError(_("لا يمكن اختيار حساب مراقبة أوراق القبض أو أوراق الدفع للمقاصة. يجب تحديد حساب بنكي."))
        except Exception as e:
            if isinstance(e, ValidationError):
                raise

        if bank_acc.account_type and bank_acc.account_type.category != 'asset':
            raise ValidationError(_("الحساب المالي المختار ليس حساباً نقدياً أو بنكياً."))

        # التحقق الصارم من أن الحساب هو حساب بنكي فعلي
        is_bank = (
            getattr(bank_acc, 'is_bank_account', False)
            or (bank_acc.account_type and (
                bank_acc.account_type.code.lower() == 'bank'
                or 'بنك' in bank_acc.account_type.name
                or 'مصرف' in bank_acc.account_type.name
            ))
            or ('بنك' in bank_acc.name or 'مصرف' in bank_acc.name)
            or str(bank_acc.code).startswith(('1116', '1117'))
        )
        is_prohibited = (
            getattr(bank_acc, 'is_cash_account', False)
            or getattr(bank_acc, 'is_custody_account', False)
            or str(bank_acc.code).startswith(('1119', '1122', '2112'))
        )
        if not is_bank or is_prohibited:
            raise ValidationError(_("الحساب المالي المختار ليس حساباً بنكياً صالحاً لإجراء المقاصة."))

        if self.user and not (self.user.is_superuser or getattr(self.user, 'is_financial_manager', False)):
            accessible = TreasurySecurityService.get_user_accessible_treasuries(self.user, action='disburse')
            if not accessible.filter(pk=bank_acc.pk).exists():
                raise ValidationError(_("ليس لديك صلاحية صرف أو مقاصة على هذا الحساب البنكي."))
        return bank_acc

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.cheque = kwargs.pop('cheque', None)
        super().__init__(*args, **kwargs)

        try:
            from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames
            rec_ctrl = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_RECEIVABLE_CONTROL)
            pay_ctrl = AccountRoleRegistry.get_account(AccountRoleNames.NOTES_PAYABLE_CONTROL)
            exclude_ids = [acc.id for acc in (rec_ctrl, pay_ctrl) if acc]
        except Exception:
            exclude_ids = []

        bank_q = (
            models.Q(is_bank_account=True)
            | models.Q(account_type__code__iexact="bank")
            | models.Q(account_type__name__icontains="بنك")
            | models.Q(account_type__name__icontains="مصرف")
            | models.Q(name__icontains="بنك")
            | models.Q(name__icontains="مصرف")
            | models.Q(code__startswith="1116")
            | models.Q(code__startswith="1117")
        )
        non_bank_exclude = (
            models.Q(is_cash_account=True)
            | models.Q(is_custody_account=True)
            | models.Q(code__startswith="1119")
            | models.Q(code__startswith="1122")
            | models.Q(code__startswith="2112")
        )

        bank_accounts_base = ChartOfAccounts.objects.filter(
            is_active=True,
            is_leaf=True,
            account_type__category='asset'
        ).filter(bank_q).exclude(non_bank_exclude).exclude(id__in=exclude_ids)

        if self.user and not (self.user.is_superuser or getattr(self.user, 'is_financial_manager', False)):
            accessible = TreasurySecurityService.get_user_accessible_treasuries(self.user, action='disburse')
            self.fields['bank_account'].queryset = accessible.filter(bank_q).exclude(non_bank_exclude).exclude(id__in=exclude_ids)
        else:
            self.fields['bank_account'].queryset = bank_accounts_base

        if self.cheque:
            if self.cheque.original_exchange_rate:
                self.initial['exchange_rate'] = self.cheque.original_exchange_rate

            bank_acc = self.cheque.deposit_bank_account
            if not bank_acc and getattr(self.cheque, 'checkbook_leaf', None) and self.cheque.checkbook_leaf.checkbook:
                bank_acc = self.cheque.checkbook_leaf.checkbook.bank_account
            if bank_acc:
                # التأكد من أن الحساب الافتراضي موجود ضمن الخيارات المسموحة
                if self.fields['bank_account'].queryset.filter(pk=bank_acc.pk).exists():
                    self.initial['bank_account'] = bank_acc


class ChequeReturnToDrawerActionForm(ChequeActionBaseForm):
    """
    نموذج رد واسترداد الشيك للساحب (RETURN_TO_DRAWER)
    مع إقفال الشيك بالدفاتر وإعادة فتح مديونية العميل
    """
    action_date = forms.DateField(
        label=_('تاريخ إعادة الشيك للساحب'),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        required=True
    )
    reason = forms.CharField(
        label=_('أسباب ومبررات رد الشيك للساحب'),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': _('أدخل أسباب رد الشيك للعميل (مثل: استبدال بسداد نقدي، إلغاء المعاملة، تسليم شيك بديل)...')
        }),
        required=True
    )


class ChequeAllocateToInvoiceForm(ChequeActionBaseForm):
    """
    نموذج تخصيص شيك القبض على فاتورة مبيعات محددة (ALLOCATE_TO_INVOICE)
    مع التحقق الدقيق من الحدود المالية وعدم تجاوز رصيد الشيك أو الفاتورة
    """
    sale = forms.ModelChoiceField(
        label=_('فاتورة المبيعات'),
        queryset=Sale.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
        required=True
    )
    amount = forms.DecimalField(
        label=_('مبلغ التخصيص (بعملة الشيك)'),
        max_digits=15,
        decimal_places=2,
        min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': _('0.00')}),
        required=True
    )
    notes = forms.CharField(
        label=_('ملاحظات التخصيص'),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': _('أي ملاحظات على تخصيص الشيك على هذه الفاتورة...')
        }),
        required=False
    )

    def __init__(self, *args, **kwargs):
        self.cheque = kwargs.pop('cheque', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if self.cheque and self.cheque.customer:
            qs = Sale.objects.filter(
                customer=self.cheque.customer,
                status='confirmed',
                payment_status__in=['unpaid', 'partially_paid']
            )

            # استخراج مفتاح منع التكرار للتحقق مما إذا كان الطلب إعادة تنفيذ
            idem_key = self.data.get('idempotency_key', '').strip() if self.data else None
            replayed_sale_id = None
            if idem_key:
                from customer.models import CustomerAllocationAudit
                alloc_ref = f"ALLOC:{idem_key}"
                existing_audit = CustomerAllocationAudit.objects.filter(
                    allocation_reference=alloc_ref,
                    allocation_status="APPLIED"
                ).first()
                if existing_audit:
                    existing_alloc = ChequeInvoiceAllocation.objects.filter(
                        allocation_audit=existing_audit
                    ).first()
                    if existing_alloc:
                        replayed_sale_id = existing_alloc.sale_id

            if self.cheque.currency:
                qs = qs.filter(currency=self.cheque.currency)
            else:
                qs = qs.filter(currency__isnull=True)

            open_sale_ids = [s.id for s in qs if s.amount_due > Decimal('0.00') or s.id == replayed_sale_id]
            self.fields['sale'].queryset = Sale.objects.filter(id__in=open_sale_ids).order_by('-date', '-id')
            self.fields['sale'].label_from_instance = lambda obj: (
                f"{obj.number} - {obj.date} "
                f"({_('المتبقي:')} {obj.amount_due:,.2f} {obj.currency.code if obj.currency else 'EGP'})"
            )

            already_allocated = self.cheque.invoice_allocations.filter(
                allocation_status=AllocationStatus.APPLIED
            ).aggregate(total=models.Sum('allocated_amount'))['total'] or Decimal('0.00')
            available = max(Decimal('0.00'), self.cheque.amount - already_allocated)
            self.fields['amount'].help_text = _(
                f"الرصيد المتاح غير المخصص في الشيك: {available:,.2f} {self.cheque.currency.code if self.cheque.currency else 'EGP'}"
            )

    def clean(self):
        cleaned_data = super().clean()
        sale = cleaned_data.get('sale')
        amount = cleaned_data.get('amount')

        # فحص ما إذا كان الطلب إعادة تنفيذ لنفس مفتاح عدم التكرار (Idempotency Replay)
        idem_key = self.cleaned_data.get('idempotency_key') or (self.data.get('idempotency_key', '').strip() if self.data else None)
        if idem_key and self.cheque:
            from customer.models import CustomerAllocationAudit
            alloc_ref = f"ALLOC:{idem_key}"
            existing_audit = CustomerAllocationAudit.objects.filter(
                allocation_reference=alloc_ref,
                allocation_status="APPLIED"
            ).first()
            if existing_audit:
                existing_alloc = ChequeInvoiceAllocation.objects.filter(
                    allocation_audit=existing_audit
                ).first()
                if existing_alloc:
                    # التحقق من تعارض البيانات (الشيك أو الفاتورة أو المبلغ)
                    if (
                        existing_alloc.cheque_id != self.cheque.id
                        or (sale and existing_alloc.sale_id != sale.id)
                        or (amount is not None and existing_alloc.allocated_amount != amount)
                    ):
                        raise ValidationError(
                            _("تعارض في مفتاح عدم التكرار: المفتاح مستخدم مسبقاً لعملية تخصيص أخرى أو بمبلغ مختلف.")
                        )
                    # إعادة تنفيذ متطابقة بنجاح
                    return cleaned_data

        if self.cheque and sale and amount:
            already_allocated = self.cheque.invoice_allocations.filter(
                allocation_status=AllocationStatus.APPLIED
            ).aggregate(total=models.Sum('allocated_amount'))['total'] or Decimal('0.00')
            available = max(Decimal('0.00'), self.cheque.amount - already_allocated)

            if amount > available:
                self.add_error(
                    'amount',
                    _("المبلغ المطلوب ({amount}) يتجاوز الرصيد المتاح غير المخصص في الشيك ({available}).").format(
                        amount=amount, available=available
                    )
                )

            if amount > sale.amount_due:
                self.add_error(
                    'amount',
                    _("المبلغ المطلوب ({amount}) يتجاوز المبلغ المتبقي على الفاتورة ({due}).").format(
                        amount=amount, due=sale.amount_due
                    )
                )

        return cleaned_data


class ChequeDeallocateActionForm(ChequeActionBaseForm):
    """
    نموذج إلغاء وفك تخصيص شيك القبض عن فاتورة المبيعات (DEALLOCATE)
    مع إثبات سبب العكس واستعادة مديونية الفاتورة بدفتر الأستاذ المساعد
    """
    reason = forms.CharField(
        label=_('سبب إلغاء وفك التخصيص'),
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': _('أدخل سبب فك التخصيص واستعادة مديونية الفاتورة...')
        }),
        required=True
    )



