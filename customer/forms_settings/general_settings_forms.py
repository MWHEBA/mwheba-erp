"""نماذج إعدادات العملاء والترقيم والائتمان العامة"""
from django import forms
from django.utils.translation import gettext_lazy as _
from ..models import CustomerGeneralSettings


class CustomerGeneralSettingsForm(forms.ModelForm):
    """نموذج حفظ إعدادات العملاء العامة وبادئة التكويد والائتمان"""
    
    class Meta:
        model = CustomerGeneralSettings
        fields = [
            "code_prefix",
            "code_digits",
            "default_credit_limit",
            "default_grace_period_days",
            "credit_limit_enforcement",
        ]
        widgets = {
            "code_prefix": forms.TextInput(attrs={
                "class": "form-control font-monospace text-uppercase",
                "placeholder": "CUST-"
            }),
            "code_digits": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "2",
                "max": "8"
            }),
            "default_credit_limit": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0"
            }),
            "default_grace_period_days": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0"
            }),
            "credit_limit_enforcement": forms.Select(attrs={
                "class": "form-select",
                "dir": "rtl"
            }),
        }
