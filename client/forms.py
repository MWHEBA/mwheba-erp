from decimal import Decimal
from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.db import transaction

from .models import Customer, CustomerCreditProfile, PaymentTerm, CustomerCreditStatusHistory, CreditAuditLog
from client.services.credit_exposure_service import CreditExposureService
from utils.validators import validate_national_id

try:
    from financial.models import ChartOfAccounts, Currency
except ImportError:
    ChartOfAccounts = None
    Currency = None


class CustomerForm(forms.ModelForm):
    """
    نموذج إضافة وتعديل العميل الشامل والمتكامل مع حوكمة الائتمان والضرائب ودليل الحسابات
    """
    # حقول ملف حوكمة الائتمان وسقوف المخاطر (CustomerCreditProfile)
    default_payment_term = forms.ModelChoiceField(
        queryset=PaymentTerm.objects.filter(is_active=True),
        required=False,
        label=_("شروط الدفع المعيارية"),
        empty_label=_("-- اختر شرط الدفع --"),
        widget=forms.Select(attrs={"class": "form-select select2 select2-filter", "dir": "rtl"})
    )
    grace_period_days = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label=_("أيام السماح الإضافية"),
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "0"})
    )
    credit_status = forms.ChoiceField(
        choices=CustomerCreditProfile.STATUS_CHOICES,
        required=False,
        initial="ACTIVE",
        label=_("حالة الائتمان"),
        widget=forms.Select(attrs={"class": "form-select select2 select2-filter", "dir": "rtl"})
    )
    risk_category = forms.ChoiceField(
        choices=CustomerCreditProfile.RISK_CHOICES,
        required=False,
        initial="LOW",
        label=_("تصنيف المخاطر"),
        widget=forms.Select(attrs={"class": "form-select select2 select2-filter", "dir": "rtl"})
    )
    next_review_date = forms.DateField(
        required=False,
        label=_("تاريخ المراجعة الائتمانية القادمة"),
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"})
    )
    credit_change_reason = forms.CharField(
        required=False,
        label=_("مبرر تعديل الائتمان / ملاحظات الاعتماد"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": _("أدخل سبب التعديل لتوثيق سجل تدقيق الائتمان...")
        })
    )

    class Meta:
        model = Customer
        fields = [
            "name",
            "code",
            "client_type",
            "is_vip",
            "contact_person",
            "company_name",
            "national_id",
            "commercial_registry",
            "tax_number",
            "is_active",
            "phone_primary",
            "phone_secondary",
            "phone",
            "email",
            "country",
            "city",
            "address",
            "default_currency",
            "default_price_list",
            "credit_limit",
            "contact_frequency",
            "last_contact_date",
            "notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": _("اسم العميل أو الكيان التجاري")}),
            "code": forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}),
            "client_type": forms.Select(attrs={"class": "form-select select2 select2-filter", "dir": "rtl"}),
            "is_vip": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "contact_person": forms.TextInput(attrs={"class": "form-control", "placeholder": _("اسم الشخص المسؤول أو مندوب التواصل")}),
            "company_name": forms.HiddenInput(),
            "national_id": forms.TextInput(attrs={"class": "form-control", "maxlength": "14", "dir": "ltr", "placeholder": "29901011234567"}),
            "commercial_registry": forms.TextInput(attrs={"class": "form-control", "placeholder": _("رقم السجل التجاري")}),
            "tax_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "123-456-789"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "phone_primary": forms.TextInput(attrs={"class": "form-control", "dir": "ltr", "placeholder": "+201234567890"}),
            "phone_secondary": forms.TextInput(attrs={"class": "form-control", "dir": "ltr", "placeholder": "+201234567890"}),
            "phone": forms.HiddenInput(),
            "email": forms.EmailInput(attrs={"class": "form-control", "dir": "ltr", "placeholder": "client@example.com"}),
            "country": forms.TextInput(attrs={"class": "form-control", "placeholder": _("الدولة (افتراضياً: مصر)")}),
            "city": forms.TextInput(attrs={"class": "form-control", "placeholder": _("المدينة أو المحافظة")}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": _("العنوان التفصيلي وموقع التوصيل")}),
            "default_currency": forms.Select(attrs={"class": "form-select select2 select2-filter", "dir": "rtl"}),
            "default_price_list": forms.Select(attrs={"class": "form-select select2 select2-filter", "dir": "rtl"}),
            "credit_limit": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "contact_frequency": forms.Select(attrs={"class": "form-select select2 select2-filter", "dir": "rtl"}),
            "last_contact_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": _("أي ملاحظات خاصة بالعميل أو شروط التعامل")}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        # الحقول الاختيارية وضبطها
        if "client_type" in self.fields:
            self.fields["client_type"].required = False
        if "credit_limit" in self.fields:
            self.fields["credit_limit"].required = False
        if "phone" in self.fields:
            self.fields["phone"].required = False
        if "phone_primary" in self.fields:
            self.fields["phone_primary"].required = False
        if "credit_status" in self.fields:
            self.fields["credit_status"].required = False
        if "risk_category" in self.fields:
            self.fields["risk_category"].required = False

        # تخصيص العملة الافتراضية
        if not self.instance.pk and not self.initial.get("default_currency"):
            try:
                from financial.services.exchange_rate_service import ExchangeRateService
                func_curr = ExchangeRateService.get_functional_currency()
                if func_curr:
                    self.initial["default_currency"] = func_curr.id
            except Exception:
                pass

        # توليد كود تلقائي للعميل الجديد
        if not self.instance.pk and not self.initial.get("code"):
            last_customer = Customer.objects.filter(code__startswith="CUST").order_by("-id").first()
            if last_customer and last_customer.code:
                try:
                    digits = "".join(filter(str.isdigit, last_customer.code))
                    new_number = int(digits) + 1 if digits else 1
                except Exception:
                    new_number = 1
            else:
                new_number = 1
            self.initial["code"] = f"CUST{new_number:04d}"

        # تحميل بيانات ملف الائتمان للعميل الحالي
        if self.instance.pk:
            profile = CustomerCreditProfile.objects.filter(customer=self.instance).first()
            if profile:
                self.initial["default_payment_term"] = profile.default_payment_term_id
                self.initial["grace_period_days"] = profile.grace_period_days
                self.initial["credit_status"] = profile.credit_status
                self.initial["risk_category"] = profile.risk_category
                self.initial["next_review_date"] = profile.next_review_date
                self._original_credit_status = profile.credit_status
                self._original_credit_limit = profile.credit_limit
            else:
                self._original_credit_status = "ACTIVE"
                self._original_credit_limit = self.instance.credit_limit or Decimal("0.00")
        else:
            self._original_credit_status = "ACTIVE"
            self._original_credit_limit = Decimal("0.00")

    def clean_credit_limit(self):
        limit = self.cleaned_data.get("credit_limit")
        if limit is not None and limit < 0:
            raise forms.ValidationError(_("الحد الائتماني لا يمكن أن يكون قيمة سالبة"))
        return limit if limit is not None else Decimal("0.00")

    def clean_national_id(self):
        """التحقق من صحة الرقم القومي المصري عند إدخاله"""
        national_id = self.cleaned_data.get("national_id")
        if national_id:
            national_id = str(national_id).strip()
            # استدعاء أداة التحقق المعيارية
            try:
                result = validate_national_id(national_id, raise_exception=False)
                if isinstance(result, dict) and not result.get("valid", True):
                    raise forms.ValidationError(result.get("error", _("الرقم القومي غير صحيح")))
                elif isinstance(result, bool) and not result:
                    raise forms.ValidationError(_("الرقم القومي المدخل غير مطابق للمعايير المصرية"))
            except Exception as val_err:
                if isinstance(val_err, forms.ValidationError):
                    raise val_err
                # إذا حدث استثناء في الفاحص
                if len(national_id) != 14 or not national_id.isdigit():
                    raise forms.ValidationError(_("الرقم القومي يجب أن يتكون من 14 رقماً"))
        return national_id

    def clean_code(self):
        """التحقق من فرادة كود العميل وقفله عند وجود حركات"""
        code = self.cleaned_data.get("code")
        instance = getattr(self, "instance", None)
        if instance and instance.pk:
            # التحقق مما إذا كان العميل يمتلك حركات سابقة
            has_transactions = (
                instance.subledger_transactions.exists()
                or instance.payments.exists()
                or instance.sales.exists()
                if hasattr(instance, "sales") else False
            )
            if has_transactions and instance.code != code:
                raise forms.ValidationError(
                    _("لا يمكن تعديل كود العميل لوجود معاملات وفواتير مالية مسجلة مرتبطة به.")
                )
            if Customer.objects.exclude(pk=instance.pk).filter(code=code).exists():
                raise forms.ValidationError(_("هذا الكود مستخدم من قبل، الرجاء استخدام كود آخر"))
        else:
            if Customer.objects.filter(code=code).exists():
                raise forms.ValidationError(_("هذا الكود مستخدم من قبل، الرجاء استخدام كود آخر"))
        return code

    def clean(self):
        cleaned_data = super().clean()
        phone_primary = cleaned_data.get("phone_primary")
        phone_secondary = cleaned_data.get("phone_secondary")
        phone = cleaned_data.get("phone")

        if not cleaned_data.get("client_type"):
            cleaned_data["client_type"] = "individual"
        if cleaned_data.get("credit_limit") is None:
            cleaned_data["credit_limit"] = Decimal("0.00")

        # مزامنة رقم الهاتف الأساسي مع حقل phone
        if phone_primary:
            cleaned_data["phone"] = phone_primary
        elif phone:
            cleaned_data["phone_primary"] = phone

        # فحص مبرر تعديل الائتمان
        new_status = cleaned_data.get("credit_status") or "ACTIVE"
        credit_limit = cleaned_data.get("credit_limit") or Decimal("0.00")
        reason = cleaned_data.get("credit_change_reason")

        if self.instance.pk and (new_status != self._original_credit_status or credit_limit != self._original_credit_limit):
            if new_status in ["WARNING", "ON_HOLD", "BLOCKED"] and not reason:
                self.add_error(
                    "credit_change_reason",
                    _("يجب إدخال مبرر وسبب تعديل حالة الائتمان لتوثيق سجل التدقيق الحوكمي.")
                )

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True, user=None):
        customer = super().save(commit=False)
        effective_user = user or self.user or getattr(customer, "created_by", None)

        if not customer.pk and effective_user:
            customer.created_by = effective_user

        if not customer.client_type:
            customer.client_type = "individual"

        if commit:
            customer.save()
            self.save_m2m()

            # مزامنة ملف حوكمة الائتمان CustomerCreditProfile
            payment_term = self.cleaned_data.get("default_payment_term")
            grace_period = self.cleaned_data.get("grace_period_days") or 0
            new_status = self.cleaned_data.get("credit_status") or "ACTIVE"
            risk_cat = self.cleaned_data.get("risk_category") or "LOW"
            next_review = self.cleaned_data.get("next_review_date")
            reason = self.cleaned_data.get("credit_change_reason") or str(_("تحديث بيانات العميل العامة"))
            currency_code = customer.default_currency.code if customer.default_currency else "EGP"

            profile, created = CustomerCreditProfile.objects.select_for_update().get_or_create(
                customer=customer,
                defaults={
                    "credit_limit": customer.credit_limit or Decimal("0.00"),
                    "currency": currency_code,
                    "default_payment_term": payment_term,
                    "grace_period_days": grace_period,
                    "credit_status": new_status,
                    "risk_category": risk_cat,
                    "next_review_date": next_review,
                    "approved_by": effective_user,
                    "approval_date": timezone.now().date(),
                }
            )

            # تحديث حقول الملف إذا كان موجوداً مسبقاً
            profile.credit_limit = customer.credit_limit or Decimal("0.00")
            profile.currency = currency_code
            profile.default_payment_term = payment_term
            profile.grace_period_days = grace_period
            profile.risk_category = risk_cat
            profile.next_review_date = next_review

            if profile.credit_status != new_status:
                CreditExposureService.update_credit_status(
                    customer_id=customer.id,
                    new_status=new_status,
                    reason=reason,
                    user=effective_user,
                    related_document=f"CustomerMasterForm#{customer.code}"
                )
            else:
                profile.save()

        return customer




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
            from financial.services.role_registry import AccountRoleRegistry

            # الحسابات المؤهلة للعملاء - فقط الحسابات الفرعية من حساب العملاء
            customers_account = AccountRoleRegistry.get_account_by_role("CUSTOMER_RECEIVABLE_CONTROL")
            if not customers_account:
                customers_account = ChartOfAccounts.objects.filter(code="11210", is_active=True).first()

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
            from financial.services.role_registry import AccountRoleRegistry
            customers_account = AccountRoleRegistry.get_account_by_role("CUSTOMER_RECEIVABLE_CONTROL")
            if not customers_account:
                customers_account = ChartOfAccounts.objects.filter(code="11210", is_active=True).first()

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
