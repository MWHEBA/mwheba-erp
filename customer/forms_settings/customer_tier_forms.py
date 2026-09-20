"""نماذج إدارة الشرائح التجارية للعملاء"""
from django import forms
from django.utils.translation import gettext_lazy as _
from ..models import CustomerTier, PaymentTerm


class CustomerTierForm(forms.ModelForm):
    """نموذج إنشاء وتعديل الشريحة التجارية للعميل"""
    default_risk_category = forms.ChoiceField(
        choices=[
            ("LOW", _("منخفض المخاطر")),
            ("MEDIUM", _("متوسط المخاطر")),
            ("HIGH", _("مرتفع المخاطر")),
            ("low", _("منخفض المخاطر")),
            ("medium", _("متوسط المخاطر")),
            ("high", _("مرتفع المخاطر")),
        ],
        required=False,
        initial="LOW",
        widget=forms.Select(attrs={"class": "form-select", "dir": "rtl"}),
    )
    
    class Meta:
        model = CustomerTier
        fields = [
            "name",
            "code",
            "description",
            "icon",
            "color",
            "default_price_list",
            "default_payment_term",
            "default_credit_limit",
            "default_risk_category",
            "discount_percentage",
            "display_order",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": _("مثال: وكالات الدعاية والإعلان")
            }),
            "code": forms.TextInput(attrs={
                "class": "form-control text-uppercase font-monospace",
                "placeholder": _("مثال: AGENCY")
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": _("وصف مختصر لخصائص هذه الشريحة وتصنيفها...")
            }),
            "icon": forms.TextInput(attrs={
                "class": "form-control font-monospace",
                "placeholder": "fas fa-users"
            }),
            "color": forms.TextInput(attrs={
                "class": "form-control font-monospace",
                "placeholder": "var(--primary-color) أو #0d6efd"
            }),
            "default_price_list": forms.Select(attrs={
                "class": "form-select select2-filter",
                "dir": "rtl"
            }),
            "default_payment_term": forms.Select(attrs={
                "class": "form-select select2-filter",
                "dir": "rtl"
            }),
            "default_credit_limit": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0"
            }),
            "default_risk_category": forms.Select(attrs={
                "class": "form-select select2-filter",
                "dir": "rtl"
            }),
            "discount_percentage": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0",
                "max": "100"
            }),
            "display_order": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0"
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_price_list"].required = False
        self.fields["default_payment_term"].required = False
        self.fields["description"].required = False
        self.fields["icon"].required = False
        self.fields["color"].required = False
        self.fields["display_order"].required = False
        self.fields["default_credit_limit"].required = False
        self.fields["discount_percentage"].required = False
        self.fields["default_risk_category"].required = False
        self.fields["is_active"].required = False

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()
        if not code:
            raise forms.ValidationError(_("الرمز التعريفي للشريحة مطلوب."))
        qs = CustomerTier.objects.filter(code=code)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("هذا الرمز مستخدم مسبقاً، الرجاء اختيار رمز آخر."))
        return code

    def clean_default_risk_category(self):
        val = self.cleaned_data.get("default_risk_category") or "LOW"
        return str(val).upper()

    def clean_icon(self):
        return self.cleaned_data.get("icon") or "fas fa-users"

    def clean_color(self):
        return self.cleaned_data.get("color") or "var(--primary-color)"



class CustomerTierReorderForm(forms.Form):
    """نموذج إعادة ترتيب الشرائح التجارية"""
    ordered_ids = forms.CharField(widget=forms.HiddenInput())


class CustomerTierDeleteForm(forms.Form):
    """نموذج الحذف الآمن للشريحة التجارية"""
    confirm = forms.BooleanField(required=True)

    def __init__(self, tier, *args, **kwargs):
        self.tier = tier
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if self.tier.is_system:
            raise forms.ValidationError(_("لا يمكن حذف شريحة نظامية أساسية."))
        if self.tier.customers_count > 0:
            raise forms.ValidationError(_("لا يمكن حذف هذه الشريحة لوجود عملاء مرتبطين بها."))
        return cleaned_data
