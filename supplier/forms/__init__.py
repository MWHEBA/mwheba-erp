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
            "phone",
            "secondary_phone",
            "email",
            "whatsapp",
            "website",
            "contact_person",
            "address",
            "city",
            "country",
            "tax_number",
            "delivery_time",
            "min_order_amount",
            "payment_terms",
            "working_hours",
            "is_preferred",
            "pricing_notes",
            "discount_policy",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "اسم المورد"}
            ),
            "code": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "كود المورد"}
            ),
            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "dir": "ltr",
                    "placeholder": "+20123456789",
                }
            ),
            "secondary_phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "dir": "ltr",
                    "placeholder": "+20123456789",
                }
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "dir": "ltr",
                    "placeholder": "supplier@example.com",
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
            "city": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "المدينة"}
            ),
            "country": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "البلد"}
            ),
            "tax_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "الرقم الضريبي"}
            ),
            "delivery_time": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "placeholder": "عدد الأيام"}
            ),
            "min_order_amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                    "min": "0",
                    "placeholder": "0.00",
                }
            ),
            "payment_terms": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثال: نقداً، آجل 30 يوم",
                }
            ),
            "working_hours": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثال: من 9 صباحاً إلى 5 مساءً",
                }
            ),
            "is_preferred": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "pricing_notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "ملاحظات خاصة بالتسعير",
                }
            ),
            "discount_policy": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "تفاصيل سياسة الخصومات",
                }
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_code(self):
        """
        التحقق من أن كود المورد فريد
        """
        code = self.cleaned_data.get("code")
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

        # إضافة حقل أنواع الموردين - الجلب من الإعدادات الديناميكية
        from ..models import SupplierType, SupplierTypeSettings

        # التأكد من وجود الإعدادات ومزامنتها
        SupplierType.sync_with_settings()

        # جلب الأنواع النشطة من الإعدادات الديناميكية
        active_types = SupplierType.objects.filter(
            settings__is_active=True
        ).select_related('settings').order_by('settings__display_order', 'name')

        self.fields["supplier_types"] = forms.ModelMultipleChoiceField(
            queryset=active_types,
            widget=forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            required=False,
            label="أنواع المورد",
        )

        # تحديد القيم الحالية لأنواع الموردين في حالة التعديل
        if self.instance and self.instance.pk:
            self.fields["supplier_types"].initial = self.instance.supplier_types.all()

    def save(self, commit=True):
        """حفظ المورد مع أنواع الموردين"""
        supplier = super().save(commit=commit)

        if commit:
            # حفظ أنواع الموردين
            supplier_types = self.cleaned_data.get("supplier_types")
            if supplier_types is not None:
                supplier.supplier_types.set(supplier_types)

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
            suppliers_account = ChartOfAccounts.objects.filter(code="21010").first()

            if suppliers_account:
                # جلب جميع الحسابات الفرعية (مستوى واحد واثنين)
                qualified_accounts = (
                    ChartOfAccounts.objects.filter(
                        models.Q(id=suppliers_account.id)
                        | models.Q(parent=suppliers_account)  # الحساب الرئيسي نفسه
                        | models.Q(  # الحسابات الفرعية المباشرة
                            parent__parent=suppliers_account
                        )  # الحسابات الفرعية من المستوى الثاني
                    )
                    .filter(is_active=True, is_leaf=True)
                    .distinct()
                    .order_by("code")
                )
            else:
                # في حالة عدم وجود حساب الموردين، عرض قائمة فارغة
                qualified_accounts = ChartOfAccounts.objects.none()

            self.fields["financial_account"].queryset = qualified_accounts
            self.fields[
                "financial_account"
            ].empty_label = "اختر الحساب المحاسبي المناسب"
            self.fields[
                "financial_account"
            ].help_text = "الحسابات المتاحة: الحسابات الفرعية من حساب الموردين فقط"
            self.fields["financial_account"].label = "الحساب المحاسبي الجديد"

    def clean_financial_account(self):
        """
        التحقق من أن الحساب المختار مناسب للموردين
        """
        account = self.cleaned_data.get("financial_account")
        if account:
            # التحقق من أن الحساب من حساب الموردين أو فرعي منه
            suppliers_account = ChartOfAccounts.objects.filter(code="21010").first()
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
