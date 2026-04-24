# Forms package for supplier app

from django import forms
from django.utils.translation import gettext_lazy as _
from ..models import Supplier

try:
    from financial.models import ChartOfAccounts
except ImportError:
    ChartOfAccounts = None


class SupplierForm(forms.ModelForm):
    """
    نموذج إضافة وتعديل المورد
    """

    class Meta:
        model = Supplier
        fields = [
            "name",
            "code",
            "primary_type",
            "phone",
            "whatsapp",
            "website",
            "contact_person",
            "address",
            "tax_number",
            "working_hours",
            "is_preferred",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "اسم المورد"}
            ),
            "code": forms.TextInput(
                attrs={
                    "class": "form-control", 
                    "placeholder": "سيتم التوليد التلقائي عند الحفظ (SUP001, SUP002, SUP003, ...)"
                }
            ),
            "primary_type": forms.Select(
                attrs={"class": "form-control select2"}
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "dir": "ltr",
                    "placeholder": "+20123456789",
                }
            ),
            "whatsapp": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "dir": "ltr",
                    "placeholder": "+20123456789",
                }
            ),
            "website": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "dir": "ltr",
                    "placeholder": "https://example.com",
                }
            ),
            "contact_person": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "اسم الشخص المسؤول"}
            ),
            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "العنوان التفصيلي",
                }
            ),
            "tax_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "الرقم الضريبي"}
            ),
            "working_hours": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثال: من 9 صباحاً إلى 5 مساءً",
                }
            ),
            "is_preferred": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_code(self):
        """
        التحقق من أن كود المورد فريد (إذا تم إدخاله)
        """
        code = self.cleaned_data.get("code")
        
        # If code is empty, it will be auto-generated in model save
        if not code:
            return code
            
        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            # في حالة التعديل، نتحقق فقط إذا تم تغيير الكود
            if Supplier.objects.exclude(pk=instance.pk).filter(code=code).exists():
                raise forms.ValidationError(
                    _("هذا الكود مستخدم من قبل، الرجاء استخدام كود آخر")
                )
        else:
            # في حالة الإضافة الجديدة
            if Supplier.objects.filter(code=code).exists():
                raise forms.ValidationError(
                    _("هذا الكود مستخدم من قبل، الرجاء استخدام كود آخر")
                )
        return code

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make code field optional
        self.fields['code'].required = False

        # تحديث queryset لـ primary_type لعرض الأنواع النشطة فقط
        from ..models import SupplierType
        
        active_types = SupplierType.objects.filter(
            is_active=True
        ).select_related('settings').order_by('display_order', 'name')
        
        self.fields["primary_type"].queryset = active_types
        self.fields["primary_type"].label_from_instance = lambda obj: obj.settings.name if obj.settings else obj.name
        self.fields["primary_type"].required = True
        self.fields["primary_type"].error_messages = {
            'required': 'يجب اختيار نوع المورد',
            'invalid_choice': 'الرجاء اختيار نوع صحيح من القائمة'
        }
        
        # في حالة التعديل، نخلي حقل النوع read-only
        if self.instance and self.instance.pk:
            self.fields['primary_type'].disabled = True
            self.fields['primary_type'].help_text = 'لا يمكن تعديل نوع المورد بعد الإنشاء'
            self.fields['primary_type'].widget.attrs['class'] = 'form-control'
            self.fields['primary_type'].widget.attrs['style'] = 'background-color: #e9ecef; cursor: not-allowed;'

    def save(self, commit=True):
        """حفظ المورد"""
        supplier = super().save(commit=commit)
        return supplier


class SupplierAccountChangeForm(forms.ModelForm):
    """
    نموذج خاص لتغيير الحساب المحاسبي للمورد
    """

    class Meta:
        model = Supplier
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

            # الحسابات المؤهلة للموردين - فقط الحسابات الفرعية من حساب الموردين
            # البحث عن حساب الموردين الرئيسي
            suppliers_account = ChartOfAccounts.objects.filter(code="20100").first()

            if suppliers_account:
                # جلب جميع الحسابات الفرعية (مستوى واحد واثنين)
                qualified_accounts = (
                    ChartOfAccounts.objects.filter(
                        models.Q(id=suppliers_account.id)
                        | models.Q(parent=suppliers_account)
                        | models.Q(parent__parent=suppliers_account)
                    )
                    .filter(is_active=True, is_leaf=True)
                    .distinct()
                    .order_by("code")
                )
            else:
                qualified_accounts = ChartOfAccounts.objects.none()

            self.fields["financial_account"].queryset = qualified_accounts
            self.fields["financial_account"].empty_label = "اختر الحساب المحاسبي المناسب"
            self.fields["financial_account"].help_text = "الحسابات المتاحة: الحسابات الفرعية من حساب الموردين فقط"
            self.fields["financial_account"].label = "الحساب المحاسبي الجديد"

    def clean_financial_account(self):
        """
        التحقق من أن الحساب المختار مناسب للموردين
        """
        account = self.cleaned_data.get("financial_account")
        if account:
            # التحقق من أن الحساب من حساب الموردين أو فرعي منه
            suppliers_account = ChartOfAccounts.objects.filter(code="20100").first()
            is_valid = False

            if suppliers_account and account:
                is_valid = (
                    account.id == suppliers_account.id
                    or account.parent == suppliers_account  # الحساب الرئيسي نفسه
                    or (  # فرعي مباشر
                        account.parent and account.parent.parent == suppliers_account
                    )  # فرعي من المستوى الثاني
                )

            if not is_valid:
                raise forms.ValidationError(
                    "الحساب المختار غير مناسب للموردين. يرجى اختيار حساب من الموردين أو الحسابات الفرعية منه فقط."
                )

        return account
