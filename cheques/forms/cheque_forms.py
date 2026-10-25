# -*- coding: utf-8 -*-
from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from core.enums.document_types import DocumentType
from core.services.sequence_service import SequenceService
from financial.models import ChartOfAccounts, Currency
from financial.services.treasury_security_service import TreasurySecurityService

from cheques.models import (
    Cheque,
    ChequeType,
    ChequePurpose,
    ChequeStatus,
    Checkbook,
    CheckbookLeaf,
    CheckbookLeafStatus,
)
from cheques.services.disbursement_security_service import ChequeDisbursementSecurityService


class ChequeReceivableForm(forms.ModelForm):
    """
    نموذج استلام شيك قبض وارد من عميل (أوراق قبض)
    """
    class Meta:
        model = Cheque
        fields = [
            'voucher_number',
            'cheque_number',
            'purpose',
            'amount',
            'currency',
            'original_exchange_rate',
            'issue_date',
            'due_date',
            'drawer_bank_name',
            'drawer_name',
            'payee_name',
            'customer',
            'related_sale',
            'deposit_bank_account',
            'front_image',
            'back_image',
            'notes',
        ]
        widgets = {
            'voucher_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('توليد تلقائي في حال تركه فارغاً')}),
            'cheque_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('رقم الشيك البنكي المطبوع')}),
            'purpose': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'original_exchange_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'drawer_bank_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم البنك المسحوب عليه الشيك')}),
            'drawer_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم صاحب الحساب / الساحب')}),
            'payee_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم المستفيد (الشركة)')}),
            'customer': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'related_sale': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'deposit_bank_account': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'front_image': forms.FileInput(attrs={'class': 'form-control'}),
            'back_image': forms.FileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['voucher_number'].required = False
        self.fields['currency'].queryset = Currency.objects.filter(is_active=True)
        self.fields['deposit_bank_account'].queryset = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

        # قيم مبدئية
        if not self.instance.pk:
            today = timezone.now().date()
            if not self.initial.get('issue_date'):
                self.initial['issue_date'] = today
            if not self.initial.get('due_date'):
                self.initial['due_date'] = today
            if not self.initial.get('original_exchange_rate'):
                self.initial['original_exchange_rate'] = Decimal('1.000000')

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        currency = cleaned_data.get('currency')
        rate = cleaned_data.get('original_exchange_rate')
        issue_date = cleaned_data.get('issue_date')
        due_date = cleaned_data.get('due_date')
        purpose = cleaned_data.get('purpose')
        notes = cleaned_data.get('notes')
        customer = cleaned_data.get('customer')
        related_sale = cleaned_data.get('related_sale')

        # 1. التحقق من المبلغ
        if amount is not None and amount <= Decimal('0.00'):
            self.add_error('amount', _('يجب أن يكون مبلغ الشيك أكبر من الصفر.'))

        # 2. التحقق من التواريخ
        if issue_date and due_date and due_date < issue_date:
            self.add_error('due_date', _('تاريخ استحقاق الشيك لا يمكن أن يكون سابقاً لتاريخ تحريره.'))

        # 3. التحقق من العملة وسعر الصرف
        if currency and not currency.is_functional:
            if not rate or rate <= Decimal('0.000000'):
                self.add_error('original_exchange_rate', _('يجب تحديد سعر صرف صالح للشيكات بالعملة الأجنبية.'))

        # 4. مطابقة شيكات الضمان
        if purpose == ChequePurpose.SECURITY_GUARANTEE:
            if not notes:
                self.add_error('notes', _('يجب تدوين رقم العقد أو المرجع لشيك الضمان في الملاحظات.'))
            if self.user and not (self.user.is_superuser or self.user.has_perm('cheques.manage_guarantee_cheques')):
                raise ValidationError(_("ليس لديك الصلاحية اللازمة لتسجيل شيكات الضمان خارج الميزانية."))

        # 5. مطابقة الفاتورة المرتبطة مع العميل
        if related_sale and customer and related_sale.customer != customer:
            self.add_error('related_sale', _('الفاتورة المحددة لا تخص العميل المختار.'))

        # 6. توليد رقم الإيصال المركزي إن لم يُحدد
        voucher_number = cleaned_data.get('voucher_number')
        if not voucher_number:
            cleaned_data['voucher_number'] = SequenceService.get_next_number(
                DocumentType.CHEQUE_RECEIVABLE,
                warehouse=None
            )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.cheque_type = ChequeType.RECEIVABLE
        if not instance.pk:
            instance.status = ChequeStatus.DRAFT
            if self.user:
                instance.created_by = self.user
            instance.voucher_number = self.cleaned_data['voucher_number']
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class ChequePayableForm(forms.ModelForm):
    """
    نموذج إصدار شيك دفع صادر لمورد أو مصروف (أوراق دفع)
    """
    checkbook = forms.ModelChoiceField(
        label=_('دفتر الشيكات'),
        queryset=Checkbook.objects.filter(is_active=True),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )

    class Meta:
        model = Cheque
        fields = [
            'voucher_number',
            'checkbook',
            'checkbook_leaf',
            'cheque_number',
            'purpose',
            'amount',
            'currency',
            'original_exchange_rate',
            'issue_date',
            'due_date',
            'deposit_bank_account',
            'drawer_bank_name',
            'payee_name',
            'supplier',
            'is_cross_cheque',
            'notes',
        ]
        widgets = {
            'voucher_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('توليد تلقائي في حال تركه فارغاً')}),
            'checkbook_leaf': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'cheque_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('رقم الشيك أو يُسحب من الورقة')}),
            'purpose': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'original_exchange_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'deposit_bank_account': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'drawer_bank_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم البنك المسحوب عليه الشيك')}),
            'payee_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('اسم المستفيد / المورد')}),
            'supplier': forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'}),
            'is_cross_cheque': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['voucher_number'].required = False
        self.fields['checkbook_leaf'].required = False
        self.fields['cheque_number'].required = False
        self.fields['currency'].queryset = Currency.objects.filter(is_active=True)
        self.fields['checkbook_leaf'].queryset = CheckbookLeaf.objects.filter(status=CheckbookLeafStatus.AVAILABLE)

        # فلترة الحسابات البنكية المصرح للمستخدم بالصرف منها
        banks_qs = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
        if self.user and not (self.user.is_superuser or getattr(self.user, 'is_financial_manager', False)):
            accessible = TreasurySecurityService.get_user_accessible_treasuries(self.user, action='disburse')
            if accessible.exists():
                banks_qs = accessible
        self.fields['deposit_bank_account'].queryset = banks_qs

        # قيم مبدئية
        if not self.instance.pk:
            today = timezone.now().date()
            if not self.initial.get('issue_date'):
                self.initial['issue_date'] = today
            if not self.initial.get('due_date'):
                self.initial['due_date'] = today
            if not self.initial.get('original_exchange_rate'):
                self.initial['original_exchange_rate'] = Decimal('1.000000')

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        currency = cleaned_data.get('currency')
        rate = cleaned_data.get('original_exchange_rate')
        issue_date = cleaned_data.get('issue_date')
        due_date = cleaned_data.get('due_date')
        bank_account = cleaned_data.get('deposit_bank_account')
        leaf = cleaned_data.get('checkbook_leaf')
        cheque_number = cleaned_data.get('cheque_number')

        # 1. التحقق من المبلغ
        if amount is not None and amount <= Decimal('0.00'):
            self.add_error('amount', _('يجب أن يكون مبلغ الشيك أكبر من الصفر.'))

        # 2. التحقق من التواريخ
        if issue_date and due_date and due_date < issue_date:
            self.add_error('due_date', _('تاريخ استحقاق الشيك لا يمكن أن يكون سابقاً لتاريخ تحريره.'))

        # 3. التحقق من ورقة الدفتر
        if leaf:
            if leaf.status != CheckbookLeafStatus.AVAILABLE and (not self.instance.pk or self.instance.checkbook_leaf_id != leaf.id):
                self.add_error('checkbook_leaf', _('ورقة الشيك المحددة غير متاحة للاستخدام.'))
            if not cheque_number:
                cleaned_data['cheque_number'] = leaf.serial_number

        if not cleaned_data.get('cheque_number'):
            self.add_error('cheque_number', _('يجب تحديد رقم الشيك أو اختيار ورقة من دفتر الشيكات.'))

        # 4. التحقق من حدود وسقف الصرف للمستخدم
        if self.user and bank_account and amount:
            func_amount = (amount * (rate or Decimal('1.000000'))).quantize(Decimal('0.01'))
            try:
                ChequeDisbursementSecurityService.enforce_and_reserve(
                    user=self.user,
                    bank_account_id=bank_account.id,
                    amount=func_amount
                )
            except ValidationError as ve:
                self.add_error('amount', ve.message if hasattr(ve, 'message') else str(ve))

        # 5. توليد رقم الإذن المركزي
        voucher_number = cleaned_data.get('voucher_number')
        if not voucher_number:
            cleaned_data['voucher_number'] = SequenceService.get_next_number(
                DocumentType.CHEQUE_PAYABLE,
                warehouse=None
            )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.cheque_type = ChequeType.PAYABLE
        if not instance.pk:
            instance.status = ChequeStatus.DRAFT
            if self.user:
                instance.created_by = self.user
            instance.voucher_number = self.cleaned_data['voucher_number']
        if commit:
            instance.save()
            self.save_m2m()
        return instance
