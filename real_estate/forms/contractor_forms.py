# -*- coding: utf-8 -*-
"""
Contractor Subcontracts & Progress Certificates Forms (Track 1 - Phase 3)
نماذج إدخال والتحقق من عقود مقاولي الباطن والمقايسات وحصر المستخلصات التفصيلية
"""
from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.utils import timezone

from real_estate.models import (
    ContractorContract,
    ContractorContractItem,
    ContractVariationOrder,
    ContractorProgressCertificate,
    ContractorCertificateItem,
    CertificatePaymentInstallmentSchedule,
    JointTerminationSurveyProtocol,
    ContractorBackcharge,
    RealEstateProject,
    PropertyBlock,
    ProjectMasterBOQItem,
)
from supplier.models import Supplier
from financial.models.currency import Currency
from cheques.models import Cheque


class ContractorContractForm(forms.ModelForm):
    """
    نموذج إنشاء وتعديل عقود مقاولي الباطن مع كافة صمامات الحوكمة
    """
    class Meta:
        model = ContractorContract
        fields = [
            'contract_number',
            'title',
            'project',
            'block',
            'contractor',
            'contract_type',
            'start_date',
            'completion_date',
            'currency',
            'initial_contract_value',
            'advance_payment_rate',
            'advance_recovery_rate',
            'retention_rate',
            'retention_cap_amount',
            'site_utilities_deduction_rate',
            'tax_regime',
            'syndicate_stamp_rate',
            'car_insurance_policy_number',
            'car_insurance_expiry_date',
            'car_insurance_deduction_rate',
            'is_assigned_to_bank',
            'assigned_bank_name',
            'assigned_bank_iban',
            'is_garnished_by_court',
            'garnishment_case_number',
            'garnishment_creditor_name',
            'garnishment_amount',
            'is_price_escalation_eligible',
            'defect_liability_period_months',
        ]
        widgets = {
            'contract_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('مثال: SUB-2026-001')}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('توصيف نطاق الأعمال')}),
            'project': forms.Select(attrs={'class': 'form-select select2-filter', 'data-placeholder': _('اختر المشروع العقاري')}),
            'block': forms.Select(attrs={'class': 'form-select select2-filter', 'data-placeholder': _('اختر العمارة / البرج (اختياري)')}),
            'contractor': forms.Select(attrs={'class': 'form-select select2-filter', 'data-placeholder': _('اختر شركة المقاولات')}),
            'contract_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'completion_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'initial_contract_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'advance_payment_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'advance_recovery_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'retention_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'retention_cap_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'site_utilities_deduction_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'tax_regime': forms.Select(attrs={'class': 'form-select'}),
            'syndicate_stamp_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0', 'max': '100'}),
            'car_insurance_policy_number': forms.TextInput(attrs={'class': 'form-control'}),
            'car_insurance_expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'car_insurance_deduction_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0', 'max': '100'}),
            'is_assigned_to_bank': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'assigned_bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'assigned_bank_iban': forms.TextInput(attrs={'class': 'form-control'}),
            'is_garnished_by_court': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'garnishment_case_number': forms.TextInput(attrs={'class': 'form-control'}),
            'garnishment_creditor_name': forms.TextInput(attrs={'class': 'form-control'}),
            'garnishment_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_price_escalation_eligible': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'defect_liability_period_months': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = RealEstateProject.objects.filter(is_archived=False).order_by('name')
        self.fields['contractor'].queryset = Supplier.objects.filter(is_active=True).order_by('name')
        self.fields['currency'].queryset = Currency.objects.all()
        self.fields['block'].required = False
        self.fields['block'].queryset = PropertyBlock.objects.all()

        self.fields['car_insurance_policy_number'].required = False
        self.fields['car_insurance_expiry_date'].required = False
        self.fields['car_insurance_deduction_rate'].required = False
        self.fields['car_insurance_deduction_rate'].initial = Decimal('0.300')

        self.fields['is_assigned_to_bank'].required = False
        self.fields['assigned_bank_name'].required = False
        self.fields['assigned_bank_iban'].required = False

        self.fields['is_garnished_by_court'].required = False
        self.fields['garnishment_case_number'].required = False
        self.fields['garnishment_creditor_name'].required = False
        self.fields['garnishment_amount'].required = False
        self.fields['garnishment_amount'].initial = Decimal('0.00')

        self.fields['is_price_escalation_eligible'].required = False
        self.fields['defect_liability_period_months'].required = False
        self.fields['defect_liability_period_months'].initial = 12

    def clean(self):
        cleaned_data = super().clean()
        is_assigned = cleaned_data.get('is_assigned_to_bank')
        bank_name = cleaned_data.get('assigned_bank_name')
        iban = cleaned_data.get('assigned_bank_iban')
        if is_assigned and (not bank_name or not iban):
            raise ValidationError(_("عند تفعيل التنازل البنكي عن المستحقات، يلزم إدخال اسم البنك ورقم الـ IBAN."))

        is_garnished = cleaned_data.get('is_garnished_by_court')
        case_no = cleaned_data.get('garnishment_case_number')
        g_amount = cleaned_data.get('garnishment_amount')
        if is_garnished and (not case_no or not g_amount):
            raise ValidationError(_("عند إثبات الحجز القضائي، يلزم تسجيل رقم الدعوى والمبلغ المحجوز."))

        start = cleaned_data.get('start_date')
        completion = cleaned_data.get('completion_date')
        if start and completion and completion < start:
            raise ValidationError(_("تاريخ نهو الأعمال التعاقدي لا يمكن أن يكون قبل تاريخ البدء."))

        return cleaned_data


class ContractorContractItemForm(forms.ModelForm):
    """
    نموذج بند مقايسة العقد التنفيذي
    """
    class Meta:
        model = ContractorContractItem
        fields = [
            'master_boq_item',
            'item_code',
            'description',
            'unit',
            'contracted_quantity',
            'unit_rate',
            'block',
            'wbs_group',
            'wbs_budget_code',
            'has_foreign_component',
            'foreign_component_percent',
        ]
        widgets = {
            'master_boq_item': forms.Select(attrs={'class': 'form-select select2-filter form-select-sm'}),
            'item_code': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'description': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'unit': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'contracted_quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm item-qty', 'step': '0.001'}),
            'unit_rate': forms.NumberInput(attrs={'class': 'form-control form-control-sm item-rate', 'step': '0.01'}),
            'block': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'wbs_group': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'wbs_budget_code': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'has_foreign_component': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'foreign_component_percent': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['master_boq_item'].required = False
        self.fields['block'].required = False
        self.fields['wbs_group'].required = False
        self.fields['wbs_budget_code'].required = False
        self.fields['has_foreign_component'].required = False
        self.fields['foreign_component_percent'].required = False

    def clean(self):
        cleaned_data = super().clean()
        qty = cleaned_data.get('contracted_quantity')
        rate = cleaned_data.get('unit_rate')
        if qty is not None and rate is not None:
            self.instance.total_budget_amount = (qty * rate).quantize(Decimal('0.01'))
            self.instance.revised_quantity = qty
        return cleaned_data


class BaseContractorContractItemFormSet(BaseInlineFormSet):
    """
    مجموعة بنود المقايسة مع التحقق من عدم التكرار وصحة الفئات
    """
    def clean(self):
        super().clean()
        item_codes = set()
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data or form.cleaned_data.get('DELETE', False):
                continue
            code = form.cleaned_data.get('item_code', '').strip().upper()
            if code:
                if code in item_codes:
                    raise ValidationError(_("كود البند '%(code)s' مكرر في مقايسة العقد.") % {'code': code})
                item_codes.add(code)


ContractorContractItemFormSet = inlineformset_factory(
    ContractorContract,
    ContractorContractItem,
    form=ContractorContractItemForm,
    formset=BaseContractorContractItemFormSet,
    extra=1,
    can_delete=True
)


class ContractVariationOrderForm(forms.ModelForm):
    """
    نموذج إنشاء أمر تغيير تعاقدي (زيادة أو تقليص أعمال)
    """
    class Meta:
        model = ContractVariationOrder
        fields = [
            'order_number',
            'variation_type',
            'description',
            'net_value_impact',
            'approved_additional_days',
            'consultant_approval_ref',
        ]
        widgets = {
            'order_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('مثال: VO-01')}),
            'variation_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'net_value_impact': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'approved_additional_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'consultant_approval_ref': forms.TextInput(attrs={'class': 'form-control'}),
        }


class AdvancePaymentDisbursementForm(forms.Form):
    """
    نموذج صرف الدفعة المقدمة الأصلية للعقد
    """
    amount = forms.DecimalField(
        label=_("مبلغ الدفعة المقدمة"),
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    payment_date = forms.DateField(
        label=_("تاريخ الصرف"),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    escrow_account_code = forms.CharField(
        label=_("كود حساب الضمان البنكي Escrow"),
        initial="11121",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    reference = forms.CharField(
        label=_("رقم الشيك أو التحويل البنكي"),
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )


class ContractorProgressCertificateForm(forms.ModelForm):
    """
    نموذج إصدار وتعديل مستخلصات المقاولين الإنشائية التراكمية
    """
    class Meta:
        model = ContractorProgressCertificate
        fields = [
            'certificate_number',
            'sequence_order',
            'certificate_type',
            'contract',
            'project',
            'contractor',
            'currency',
            'period_start',
            'period_end',
            'materials_on_site',
            'price_escalation_amount',
            'approved_suspension_standby_claims',
            'notes',
        ]
        widgets = {
            'certificate_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('مثال: CERT-2026-001')}),
            'sequence_order': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'certificate_type': forms.Select(attrs={'class': 'form-select'}),
            'contract': forms.Select(attrs={'class': 'form-select select2-filter', 'data-placeholder': _('اختر عقد المقاولة')}),
            'project': forms.Select(attrs={'class': 'form-select select2-filter', 'data-placeholder': _('اختر المشروع العقاري')}),
            'contractor': forms.Select(attrs={'class': 'form-select select2-filter', 'data-placeholder': _('اختر المقاول')}),
            'currency': forms.Select(attrs={'class': 'form-select'}),
            'period_start': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'period_end': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'materials_on_site': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'price_escalation_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'approved_suspension_standby_claims': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = RealEstateProject.objects.filter(is_archived=False).order_by('name')
        self.fields['contractor'].queryset = Supplier.objects.filter(is_active=True).order_by('name')
        self.fields['contract'].queryset = ContractorContract.objects.filter(status=ContractorContract.ContractStatus.ACTIVE).order_by('-created_at')

    def clean(self):
        cleaned_data = super().clean()
        p_start = cleaned_data.get('period_start')
        p_end = cleaned_data.get('period_end')
        if p_start and p_end and p_end < p_start:
            raise ValidationError(_("تاريخ نهاية فترة المستخلص لا يمكن أن يكون قبل تاريخ البداية."))
        return cleaned_data


class ContractorCertificateItemForm(forms.ModelForm):
    """
    نموذج سطر حصر المستخلص التفصيلي
    """
    class Meta:
        model = ContractorCertificateItem
        fields = [
            'contract_item',
            'block',
            'item_code',
            'description',
            'unit',
            'unit_rate',
            'previous_quantity',
            'current_quantity',
            'current_cumulative_percent',
            'wir_reference',
            'mir_reference',
            'is_disputed_holdback',
            'dispute_reason',
            'notes',
        ]
        widgets = {
            'contract_item': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'block': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'item_code': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'description': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'unit': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'unit_rate': forms.NumberInput(attrs={'class': 'form-control form-control-sm item-rate', 'step': '0.01'}),
            'previous_quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm prev-qty', 'step': '0.001', 'readonly': 'readonly'}),
            'current_quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm curr-qty', 'step': '0.001'}),
            'current_cumulative_percent': forms.NumberInput(attrs={'class': 'form-control form-control-sm comp-pct', 'step': '0.01', 'min': '0', 'max': '100'}),
            'wir_reference': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'mir_reference': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'is_disputed_holdback': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'dispute_reason': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }


ContractorCertificateItemFormSet = inlineformset_factory(
    ContractorProgressCertificate,
    ContractorCertificateItem,
    form=ContractorCertificateItemForm,
    extra=0,
    can_delete=True
)


class CertificateExcelImportForm(forms.Form):
    """
    نموذج استيراد شيت حصر المستخلص من ملف Excel أو CSV
    """
    file = forms.FileField(
        label=_("ملف الحصر الهندسي (Excel / CSV)"),
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx, .xls, .csv'})
    )
    replace_existing_items = forms.BooleanField(
        label=_("استبدال البنود الحالية للمستخلص"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class RetentionReleaseForm(forms.Form):
    """
    نموذج الإفراج عن تأمين حسن التنفيذ (ابتدائي أو نهائي)
    """
    RELEASE_CHOICES = (
        ("SUBSTANTIAL", _("إفراج استلام ابتدائي (50%)")),
        ("FINAL", _("إفراج استلام نهائي ورد التأمين بالكامل (50%)")),
    )
    release_type = forms.ChoiceField(
        choices=RELEASE_CHOICES,
        label=_("نوع الإفراج"),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    amount = forms.DecimalField(
        label=_("مبلغ التأمين المراد الإفراج عنه"),
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    defect_deductions = forms.DecimalField(
        label=_("خصومات إصلاح العيوب (إن وجدت)"),
        max_digits=18,
        decimal_places=2,
        initial=Decimal("0.00"),
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    release_date = forms.DateField(
        label=_("تاريخ الإفراج"),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    notes = forms.CharField(
        label=_("ملاحظات"),
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2})
    )


class StornoReversalForm(forms.Form):
    """
    نموذج إلغاء المستخلص وتوليد القيد العكسي المعياري (Storno Reversal)
    """
    reversal_reason = forms.CharField(
        label=_("سبب الإلغاء والقيد العكسي"),
        required=True,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': _('اكتب سبب الإلغاء بدقة للتدقيق المالي...')})
    )
    reversal_date = forms.DateField(
        label=_("تاريخ القيد العكسي"),
        required=False,
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )


class CertificatePaymentInstallmentForm(forms.ModelForm):
    """
    نموذج جدولة دفعات المستخلص على أقساط مؤرخة
    """
    class Meta:
        model = CertificatePaymentInstallmentSchedule
        fields = [
            'installment_number',
            'due_date',
            'amount',
            'payment_method',
        ]
        widgets = {
            'installment_number': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
        }


class InstallmentChequeSettlementForm(forms.Form):
    """
    نموذج سداد الدفعة المجدولة بشيك بنكي آجل (PDC)
    """
    cheque = forms.ModelChoiceField(
        queryset=Cheque.objects.all(),
        label=_("الشيك البنكي الصادر"),
        widget=forms.Select(attrs={'class': 'form-select select2-filter'})
    )
    settlement_date = forms.DateField(
        label=_("تاريخ السداد"),
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )


class JointTerminationSurveyForm(forms.ModelForm):
    """
    نموذج محضر الحصر المشترك لفسخ العقد واستيعاب مشونات الموقع
    """
    class Meta:
        model = JointTerminationSurveyProtocol
        fields = [
            'protocol_reference',
            'survey_date',
            'consultant_representative',
            'employer_representative',
            'contractor_representative',
            'as_built_completed_value',
            'uninstalled_materials_value',
            'snag_and_remedial_costs',
            'court_expert_minutes_number',
            'site_vacated_and_handed_over',
        ]
        widgets = {
            'protocol_reference': forms.TextInput(attrs={'class': 'form-control'}),
            'survey_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'consultant_representative': forms.TextInput(attrs={'class': 'form-control'}),
            'employer_representative': forms.TextInput(attrs={'class': 'form-control'}),
            'contractor_representative': forms.TextInput(attrs={'class': 'form-control'}),
            'as_built_completed_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'uninstalled_materials_value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'snag_and_remedial_costs': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'court_expert_minutes_number': forms.TextInput(attrs={'class': 'form-control'}),
            'site_vacated_and_handed_over': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ContractorBackchargeForm(forms.ModelForm):
    """
    نموذج تسجيل خصم بيني أو تكاليف إصلاح عيوب على المقاول
    """
    class Meta:
        model = ContractorBackcharge
        fields = [
            'certificate',
            'beneficiary_contractor',
            'snag_item',
            'default_notice',
            'reason',
            'memo_reference',
            'amount',
        ]
        widgets = {
            'certificate': forms.Select(attrs={'class': 'form-select select2-filter'}),
            'beneficiary_contractor': forms.Select(attrs={'class': 'form-select select2-filter'}),
            'snag_item': forms.Select(attrs={'class': 'form-select select2-filter'}),
            'default_notice': forms.Select(attrs={'class': 'form-select select2-filter'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'memo_reference': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }
