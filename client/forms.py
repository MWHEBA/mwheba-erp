from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Customer

try:
    from financial.models import ChartOfAccounts
except ImportError:
    ChartOfAccounts = None


class CustomerForm(forms.ModelForm):
    """
    نموذج إضافة وتعديل العميل
    """

    class Meta:
        model = Customer
        fields = [
            "name",
            "phone",
            "address",
            "email",
            "code",
            "credit_limit",
            "tax_number",
            "is_active",
            "notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "dir": "ltr"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "email": forms.EmailInput(attrs={"class": "form-control", "dir": "ltr"}),
            "code": forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}),
            "credit_limit": forms.NumberInput(attrs={"class": "form-control"}),
            "tax_number": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean_code(self):
        """
        التحقق من أن كود العميل فريد
        """
        code = self.cleaned_data.get("code")
        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            # في حالة التعديل، نتحقق فقط إذا تم تغيير الكود
            if Customer.objects.exclude(pk=instance.pk).filter(code=code).exists():
                raise forms.ValidationError(
                    _("هذا الكود مستخدم من قبل، الرجاء استخدام كود آخر")
                )
        else:
            # في حالة الإضافة الجديدة
            if Customer.objects.filter(code=code).exists():
                raise forms.ValidationError(
                    _("هذا الكود مستخدم من قبل، الرجاء استخدام كود آخر")
                )
        return code

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # توليد كود تلقائي للعميل الجديد
        if not self.instance.pk:
            # الحصول على آخر كود
            last_customer = Customer.objects.filter(
                code__startswith='CUST',
                code__regex=r'^CUST\d+$'
            ).order_by('-code').first()
            if last_customer and last_customer.code:
                try:
                    last_number = int(last_customer.code.replace('CUST', ''))
                    new_number = last_number + 1
                except (ValueError, IndexError):
                    new_number = 1
            else:
                new_number = 1
            
            self.initial['code'] = f'CUST{new_number:04d}'




class CustomerAccountChangeForm(forms.ModelForm):
    """
    نموذج خاص لتغيير الحساب المحاسبي للعميل
    """

    class Meta:
        model = Customer
        fields = ["financial_account"]
        widgets = {
            "financial_account": forms.Select(
                attrs={
                    "class": "form-control select2-search",
                    "data-placeholder": "ابحث واختر الحساب المحاسبي الجديد...",
                    "data-allow-clear": "true",
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if ChartOfAccounts:
            from django.db import models

            # الحسابات المؤهلة للعملاء - فقط الحسابات الفرعية من حساب العملاء
            # البحث عن حساب العملاء الرئيسي
            customers_account = ChartOfAccounts.objects.filter(code="10300").first()

            if customers_account:
                # جلب جميع الحسابات الفرعية (مستوى واحد واثنين)
                qualified_accounts = (
                    ChartOfAccounts.objects.filter(
                        models.Q(id=customers_account.id)
                        | models.Q(parent=customers_account)
                        | models.Q(parent__parent=customers_account)
                    )
                    .filter(is_active=True, is_leaf=True)
                    .distinct()
                    .order_by("code")
                )
            else:
                qualified_accounts = ChartOfAccounts.objects.none()

            self.fields["financial_account"].queryset = qualified_accounts
            self.fields["financial_account"].empty_label = "اختر الحساب المحاسبي المناسب"
            self.fields["financial_account"].help_text = "الحسابات المتاحة: الحسابات الفرعية من حساب العملاء فقط"
            self.fields["financial_account"].label = "الحساب المحاسبي الجديد"

    def clean_financial_account(self):
        account = self.cleaned_data.get("financial_account")
        if account:
            customers_account = ChartOfAccounts.objects.filter(code="10300").first()
            is_valid = False

            if customers_account and account:
                is_valid = (
                    account.id == customers_account.id
                    or account.parent == customers_account
                    or (account.parent and account.parent.parent == customers_account)
                )

            if not is_valid:
                raise forms.ValidationError(
                    "الحساب المختار غير مناسب للعملاء. يرجى اختيار حساب من العملاء أو الحسابات الفرعية منه فقط."
                )

        return account
