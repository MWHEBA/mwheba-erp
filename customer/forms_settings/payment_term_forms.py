"""نماذج إدارة شروط الدفع والائتمان المعيارية"""
from decimal import Decimal
from django import forms
from django.utils.translation import gettext_lazy as _
from ..models import PaymentTerm


class PaymentTermForm(forms.ModelForm):
    """نموذج إنشاء وتعديل شرط الدفع المعياري"""
    
    class Meta:
        model = PaymentTerm
        fields = [
            "name",
            "code",
            "days",
            "is_credit",
            "discount_percentage",
            "discount_days",
            "is_default",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": _("مثال: سداد آجل خلال 30 يوماً")
            }),
            "code": forms.TextInput(attrs={
                "class": "form-control text-uppercase font-monospace",
                "placeholder": _("مثال: NET30")
            }),
            "days": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
                "placeholder": "30"
            }),
            "is_credit": forms.CheckboxInput(attrs={
                "class": "form-check-input"
            }),
            "discount_percentage": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "max": "100"
            }),
            "discount_days": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0"
            }),
            "is_default": forms.CheckboxInput(attrs={
                "class": "form-check-input"
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].required = False

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()
        if not code:
            return ""
        qs = PaymentTerm.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("هذا الكود مستخدم بالفعل، يرجى استخدام كود آخر."))
        return code


class PaymentTermDeleteForm(forms.Form):
    """نموذج الحذف الآمن لشرط الدفع"""
    confirm = forms.BooleanField(required=True)

    def __init__(self, payment_term, *args, **kwargs):
        self.payment_term = payment_term
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        # فحص وجود عملاء أو موردين أو شرائح مرتبطة
        has_customers = getattr(self.payment_term, 'customercreditprofile_set', None) and self.payment_term.customercreditprofile_set.exists()
        has_suppliers = getattr(self.payment_term, 'suppliers', None) and self.payment_term.suppliers.exists()
        has_tiers = getattr(self.payment_term, 'customer_tiers', None) and self.payment_term.customer_tiers.exists()
        
        if has_customers or has_suppliers or has_tiers:
            raise forms.ValidationError(_("لا يمكن حذف هذا الشرط لوجود عملاء أو موردين أو شرائح تجارية مرتبطة به."))
        return cleaned_data
