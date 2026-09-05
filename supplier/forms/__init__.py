from decimal import Decimal
from django import forms
from django.utils.translation import gettext_lazy as _
from ..models import Supplier

try:
    from financial.models import ChartOfAccounts
except ImportError:
    ChartOfAccounts = None


class SupplierForm(forms.ModelForm):
    """
    نموذج إضافة وتعديل المورد المتكامل والشامل
    """

    class Meta:
        model = Supplier
        fields = [
            "name",
            "code",
            "entity_type",
            "primary_type",
            "national_id",
            "commercial_registry",
            "tax_number",
            "is_preferred",
            "is_active",
            "is_pricing_supplier",
            "provided_services",
            "contact_person",
            "phone",
            "secondary_phone",
            "whatsapp",
            "email",
            "website",
            "country",
            "city",
            "address",
            "default_currency",
            "credit_limit",
            "default_payment_term",
            "grace_period_days",
            "bank_name",
            "bank_account_number",
            "bank_beneficiary_name",
            "working_hours",
            "delivery_time_days",
            "min_order_amount",
            "supplier_rating",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "اسم المورد / المنشأة"}
            ),
            "code": forms.TextInput(
                attrs={
                    "class": "form-control", 
                    "readonly": "readonly"
                }
            ),
            "entity_type": forms.Select(
                attrs={"class": "form-select select2 select2-filter", "dir": "rtl"}
            ),
            "primary_type": forms.Select(
                attrs={"class": "form-select select2 select2-filter", "dir": "rtl"}
            ),
            "national_id": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "الرقم القومي (14 رقماً)",
                    "maxlength": "14",
                    "dir": "ltr",
                }
            ),
            "commercial_registry": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "رقم السجل التجاري",
                }
            ),
            "tax_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "الرقم الضريبي (مثال: 123-456-789)"}
            ),
            "default_currency": forms.Select(
                attrs={"class": "form-select select2 select2-filter", "dir": "rtl"}
            ),
            "default_payment_term": forms.Select(
                attrs={"class": "form-select select2 select2-filter", "dir": "rtl"}
            ),
            "credit_limit": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "0.00", "step": "0.01"}
            ),
            "grace_period_days": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "0", "min": "0"}
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
                    "placeholder": "+20100000000",
                }
            ),
            "whatsapp": forms.TextInput(
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
            "website": forms.URLInput(
                attrs={
                    "class": "form-control",
                    "dir": "ltr",
                    "placeholder": "https://example.com",
                }
            ),
            "country": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مصر"}
            ),
            "city": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "القاهرة / الجيزة"}
            ),
            "contact_person": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "اسم الشخص المسؤول / المفوض"}
            ),
            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "العنوان التفصيلي وموقع الاستلام أو التوريد",
                }
            ),
            "bank_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "مثال: البنك الأهلي المصري / بنك مصر / CIB"}
            ),
            "bank_account_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "رقم الحساب أو الآيبان الدولي (IBAN)", "dir": "ltr"}
            ),
            "bank_beneficiary_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "اسم المستفيد المطابق للحساب البنكي"}
            ),
            "working_hours": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "مثال: من 9 صباحاً إلى 5 مساءً",
                }
            ),
            "delivery_time_days": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "متوسط أيام التسليم", "min": "0"}
            ),
            "min_order_amount": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "0.00", "step": "0.01"}
            ),
            "supplier_rating": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "من 1.0 إلى 5.0", "step": "0.1", "min": "1", "max": "5"}
            ),
            "is_preferred": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_pricing_supplier": forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_is_pricing_supplier"}),
            "provided_services": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
        }

    def clean_code(self):
        """
        التحقق من أن كود المورد فريد وقفل التعديل إذا كانت له حركات
        """
        code = self.cleaned_data.get("code")
        if not code:
            return code
            
        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            if Supplier.objects.exclude(pk=instance.pk).filter(code=code).exists():
                raise forms.ValidationError(
                    _("هذا الكود مستخدم من قبل، الرجاء استخدام كود آخر")
                )
            # قفل الكود عند وجود حركات مشتريات أو دفعات
            if instance.code and code != instance.code:
                try:
                    from purchase.models import Purchase
                    from supplier.models.supplier_advance import SupplierAdvancePayment
                    has_tx = (
                        Purchase.objects.filter(supplier=instance).exists()
                        or SupplierAdvancePayment.objects.filter(supplier=instance).exists()
                    )
                    if has_tx:
                        raise forms.ValidationError(
                            _("لا يمكن تعديل كود المورد لوجود حركات وفواتير مرتبطة به")
                        )
                except forms.ValidationError:
                    raise
                except Exception:
                    pass
        else:
            if Supplier.objects.filter(code=code).exists():
                raise forms.ValidationError(
                    _("هذا الكود مستخدم من قبل، الرجاء استخدام كود آخر")
                )
        return code

    def clean(self):
        cleaned_data = super().clean()
        entity_type = cleaned_data.get("entity_type")
        national_id = cleaned_data.get("national_id")

        if not entity_type:
            cleaned_data["entity_type"] = "company"
            
        if cleaned_data.get("credit_limit") is None:
            cleaned_data["credit_limit"] = Decimal("0.00")

        if cleaned_data.get("grace_period_days") is None:
            cleaned_data["grace_period_days"] = 0

        if entity_type == "individual" and national_id:
            from utils.validators import validate_national_id
            result = validate_national_id(national_id, raise_exception=False)
            if not result.get("is_valid", False):
                error_msg = result.get("error_message") or _("الرقم القومي غير صحيح. يجب أن يتكون من 14 رقماً مصرياً صالحاً.")
                self.add_error("national_id", error_msg)

        # حماية وتعشيق منظومة التسعير والخدمات (Safety Guards)
        is_pricing = cleaned_data.get("is_pricing_supplier", False)
        provided_svcs = cleaned_data.get("provided_services")
        
        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            from ..models import SupplierService
            active_services = SupplierService.objects.filter(supplier=instance, is_active=True)
            has_active_services = active_services.exists()

            # 1. منع إطفاء مفتاح مورد التسعير إذا كان للمورد خدمات نشطة
            if not is_pricing and has_active_services:
                self.add_error(
                    "is_pricing_supplier",
                    _("لا يمكن إلغاء اعتماد المورد كمورد تسعير لوجود خدمات وأسعار نشطة مسجلة له بالفعل.")
                )

            # 2. منع إلغاء تحديد خدمة لها بنود أسعار نشطة
            if has_active_services and provided_svcs is not None:
                selected_type_ids = set(svc.id for svc in provided_svcs)
                active_type_ids = set(active_services.values_list('service_type_id', flat=True))
                removed_type_ids = active_type_ids - selected_type_ids
                if removed_type_ids:
                    from ..models import ServiceType
                    removed_names = list(ServiceType.objects.filter(id__in=removed_type_ids).values_list('name', flat=True))
                    self.add_error(
                        "provided_services",
                        _("لا يمكن إلغاء الخدمات التالية لوجود بنود تسعير نشطة مرتبطة بها للمورد: {}").format("، ".join(removed_names))
                    )

        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "entity_type" in self.fields:
            self.fields["entity_type"].required = False
        if "credit_limit" in self.fields:
            self.fields["credit_limit"].required = False
        if "grace_period_days" in self.fields:
            self.fields["grace_period_days"].required = False
        if "is_pricing_supplier" in self.fields:
            self.fields["is_pricing_supplier"].required = False
        if "provided_services" in self.fields:
            from ..models import ServiceType
            self.fields["provided_services"].queryset = ServiceType.objects.filter(is_active=True).order_by('order', 'name')
            self.fields["provided_services"].widget = forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"})
            self.fields["provided_services"].widget.choices = self.fields["provided_services"].choices
            self.fields["provided_services"].required = False

        # حجب خيارات التسعير تماماً إذا كان موديول التسعير غير مفعّل في النظام
        try:
            from core.models import SystemModule
            is_pricing_enabled = SystemModule.objects.filter(code='printing_pricing', is_enabled=True).exists()
        except Exception:
            is_pricing_enabled = True

        if not is_pricing_enabled:
            if "is_pricing_supplier" in self.fields:
                self.fields["is_pricing_supplier"].widget = forms.HiddenInput()
                self.fields["is_pricing_supplier"].initial = False
            if "provided_services" in self.fields:
                self.fields["provided_services"].widget = forms.MultipleHiddenInput()
                self.fields["provided_services"].required = False

        if not self.instance.pk and not self.initial.get("default_currency"):
            try:
                from financial.services.exchange_rate_service import ExchangeRateService
                func_curr = ExchangeRateService.get_functional_currency()
                if func_curr:
                    self.initial["default_currency"] = func_curr.id
            except Exception:
                pass

        # توليد كود تلقائي للمورد الجديد
        if not self.instance.pk and not self.initial.get("code"):
            last_supplier = Supplier.objects.filter(
                code__startswith='SUP'
            ).order_by('-id').first()
            if last_supplier and last_supplier.code:
                try:
                    digits = ''.join(filter(str.isdigit, last_supplier.code))
                    new_number = int(digits) + 1 if digits else 1
                except Exception:
                    new_number = 1
            else:
                new_number = 1
            
            self.initial['code'] = f'SUP{new_number:03d}'
        
        self.fields['code'].required = True

        from ..models import SupplierType
        active_types = SupplierType.objects.filter(
            is_active=True
        ).select_related('settings').order_by('display_order', 'name')
        
        self.fields["primary_type"].queryset = active_types
        self.fields["primary_type"].label_from_instance = lambda obj: obj.settings.name if obj.settings else obj.name
        self.fields["primary_type"].required = True
        self.fields["primary_type"].error_messages = {
            'required': 'يجب اختيار مجال التوريد',
            'invalid_choice': 'الرجاء اختيار مجال توريد صحيح من القائمة'
        }

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
            from financial.services.role_registry import AccountRoleRegistry
            suppliers_account = AccountRoleRegistry.get_account_by_role("SUPPLIER_PAYABLE_CONTROL")

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
            from financial.services.role_registry import AccountRoleRegistry
            suppliers_account = AccountRoleRegistry.get_account_by_role("SUPPLIER_PAYABLE_CONTROL")
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
