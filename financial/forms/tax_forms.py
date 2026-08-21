from django import forms
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

from financial.models.tax import (
    TaxCode,
    TaxRule,
    TaxRuleCondition,
    TaxExemptionCertificate,
    TaxAccountMapping,
    TaxJurisdiction,
)
from financial.models.chart_of_accounts import ChartOfAccounts
from client.models import Customer
from supplier.models import Supplier


class TaxCodeForm(forms.ModelForm):
    class Meta:
        model = TaxCode
        fields = [
            "code",
            "name",
            "tax_type",
            "tax_nature",
            "eta_tax_type",
            "rate",
            "recoverability_percentage",
            "is_recoverable",
            "is_default",
            "effective_from",
            "effective_to",
            "is_active",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": _("مثال: VAT14")}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": _("مثال: ضريبة القيمة المضافة 14%")}),
            "tax_type": forms.Select(attrs={"class": "form-select"}),
            "tax_nature": forms.Select(attrs={"class": "form-select"}),
            "eta_tax_type": forms.TextInput(attrs={"class": "form-control", "placeholder": _("T1, T4...")}),
            "rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "recoverability_percentage": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "100"}),
            "is_recoverable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_default": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "effective_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "effective_to": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class TaxRuleForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].required = False

    class Meta:
        model = TaxRule
        fields = [
            "code",
            "name",
            "priority",
            "rule_scope",
            "scope_value",
            "tax_code",
            "jurisdiction",
            "effective_from",
            "effective_to",
            "is_active",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": _("توليد تلقائي RUL-XXX (اختياري)")}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": _("مثال: قاعدة ضريبة توريدات الخدمات")}),
            "priority": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "rule_scope": forms.Select(attrs={"class": "form-select"}),
            "scope_value": forms.TextInput(attrs={"class": "form-control", "placeholder": _("قيمة النطاق المشروط إن وجدت")}),
            "tax_code": forms.Select(attrs={"class": "form-select"}),
            "jurisdiction": forms.Select(attrs={"class": "form-select"}),
            "effective_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "effective_to": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class TaxExemptionCertificateForm(forms.ModelForm):
    class Meta:
        model = TaxExemptionCertificate
        fields = [
            "customer",
            "supplier",
            "certificate_number",
            "tax_code",
            "valid_from",
            "valid_to",
            "max_quota_amount",
            "exemption_reason",
            "attachment_reference",
            "status",
        ]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-select select2"}),
            "supplier": forms.Select(attrs={"class": "form-select select2"}),
            "certificate_number": forms.TextInput(attrs={"class": "form-control", "placeholder": _("رقم الشهادة / الإعفاء")}),
            "tax_code": forms.Select(attrs={"class": "form-select select2"}),
            "valid_from": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "valid_to": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "max_quota_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": _("0.00 (اختياري)")}),
            "exemption_reason": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": _("سبب الإعفاء المعتمد والسند القانوني")}),
            "attachment_reference": forms.TextInput(attrs={"class": "form-control", "placeholder": _("مرجع المرفق")}),
            "status": forms.Select(attrs={"class": "form-select"}, choices=(("ACTIVE", _("نشطة")), ("EXPIRED", _("منتهية")), ("REVOKED", _("ملغاة")))),
        }


class TaxAccountMappingForm(forms.ModelForm):
    class Meta:
        model = TaxAccountMapping
        fields = [
            "tax_code",
            "currency",
            "tax_nature",
            "debit_account",
            "credit_account",
            "output_tax_account",
            "input_tax_account",
            "withholding_tax_account",
        ]
        widgets = {
            "tax_code": forms.Select(attrs={"class": "form-select select2"}),
            "currency": forms.TextInput(attrs={"class": "form-control", "maxlength": 3, "placeholder": "EGP"}),
            "tax_nature": forms.Select(attrs={"class": "form-select"}),
            "debit_account": forms.Select(attrs={"class": "form-select select2"}),
            "credit_account": forms.Select(attrs={"class": "form-select select2"}),
            "output_tax_account": forms.Select(attrs={"class": "form-select select2"}),
            "input_tax_account": forms.Select(attrs={"class": "form-select select2"}),
            "withholding_tax_account": forms.Select(attrs={"class": "form-select select2"}),
        }
