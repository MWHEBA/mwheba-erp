from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from django.db import models
from ..models import ChartOfAccounts, AccountType, JournalEntry, JournalEntryLine

try:
    from client.models import Customer
    from supplier.models import Supplier
except ImportError:
    Customer = None
    Supplier = None


class IncomeForm(forms.Form):
    """نموذج إنشاء إيراد جديد"""

    # معلومات أساسية
    description = forms.CharField(
        label="وصف الإيراد",
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "أدخل وصف الإيراد"}
        ),
    )

    amount = forms.DecimalField(
        label="المبلغ",
        max_digits=15,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "0", "step": "any"}
        ),
    )

    income_date = forms.DateField(
        label="تاريخ الإيراد",
        initial=timezone.now().date(),
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    # الحسابات المحاسبية
    income_account = forms.ModelChoiceField(
        label="حساب الإيراد",
        queryset=None,
        empty_label="اختر حساب الإيراد",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    receipt_account = forms.ModelChoiceField(
        label="حساب الاستلام",
        queryset=None,
        empty_label="اختر حساب الاستلام",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    # معلومات إضافية
    reference = forms.CharField(
        label="المرجع",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "رقم الفاتورة أو المرجع"}
        ),
    )

    notes = forms.CharField(
        label="ملاحظات",
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 3, "placeholder": "ملاحظات إضافية"}
        ),
    )

    # ربط بالعملاء
    customer = forms.ModelChoiceField(
        label="العميل",
        queryset=None,
        required=False,
        empty_label="اختر العميل (اختياري)",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    # حالة الترحيل
    auto_post = forms.BooleanField(
        label="ترحيل تلقائي",
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # حسابات الإيرادات
        try:
            income_accounts = ChartOfAccounts.objects.filter(
                is_active=True, is_leaf=True, account_type__name__icontains="إيراد"
            ).order_by("code")
            self.fields["income_account"].queryset = income_accounts
        except Exception:
            self.fields["income_account"].queryset = ChartOfAccounts.objects.none()

        # الحسابات النقدية والبنكية
        try:
            receipt_accounts = (
                ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)
                .filter(
                    models.Q(is_cash_account=True)
                    | models.Q(is_bank_account=True)
                    | models.Q(account_type__name__icontains="نقدي")
                    | models.Q(account_type__name__icontains="بنك")
                    | models.Q(account_type__name__icontains="صندوق")
                )
                .order_by("code")
            )
            self.fields["receipt_account"].queryset = receipt_accounts
        except Exception:
            self.fields["receipt_account"].queryset = ChartOfAccounts.objects.none()

        # العملاء
        if Customer:
            try:
                customers = Customer.objects.filter(is_active=True).order_by("name")
                self.fields["customer"].queryset = customers
            except Exception:
                self.fields["customer"].queryset = Customer.objects.none()
        else:
            # إخفاء حقل العميل إذا لم يكن متوفراً
            del self.fields["customer"]

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount and amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر")
        return amount

    def clean_income_date(self):
        income_date = self.cleaned_data.get("income_date")
        if income_date and income_date > timezone.now().date():
            raise ValidationError("تاريخ الإيراد لا يمكن أن يكون في المستقبل")
        return income_date

    def clean(self):
        cleaned_data = super().clean()
        income_account = cleaned_data.get("income_account")
        receipt_account = cleaned_data.get("receipt_account")

        # التأكد من عدم تطابق الحسابات
        if income_account and receipt_account and income_account == receipt_account:
            raise ValidationError("حساب الإيراد وحساب الاستلام يجب أن يكونا مختلفين")

        return cleaned_data


class IncomeEditForm(IncomeForm):
    """نموذج تعديل إيراد موجود"""

    def __init__(self, *args, **kwargs):
        self.journal_entry = kwargs.pop("journal_entry", None)
        super().__init__(*args, **kwargs)

        if self.journal_entry:
            # ملء البيانات من القيد المحاسبي
            self.initial["description"] = self.journal_entry.description
            self.initial["income_date"] = self.journal_entry.date
            self.initial["reference"] = self.journal_entry.reference
            self.initial["notes"] = self.journal_entry.notes

            # استخراج المبلغ والحسابات من بنود القيد
            lines = self.journal_entry.lines.all()
            for line in lines:
                if line.debit_amount > 0:
                    # حساب الاستلام (مدين)
                    self.initial["receipt_account"] = line.account
                    self.initial["amount"] = line.debit_amount
                elif line.credit_amount > 0:
                    # حساب الإيراد (دائن)
                    self.initial["income_account"] = line.account


class IncomeFilterForm(forms.Form):
    """نموذج تصفية الإيرادات"""

    date_from = forms.DateField(
        label="من تاريخ",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    date_to = forms.DateField(
        label="إلى تاريخ",
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    income_account = forms.ModelChoiceField(
        label="حساب الإيراد",
        queryset=None,
        required=False,
        empty_label="جميع الحسابات",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    customer = forms.ModelChoiceField(
        label="العميل",
        queryset=None,
        required=False,
        empty_label="جميع العملاء",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    status = forms.ChoiceField(
        label="الحالة",
        choices=[
            ("", "جميع الحالات"),
            ("draft", "مسودة"),
            ("posted", "مرحل"),
        ],
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    min_amount = forms.DecimalField(
        label="الحد الأدنى للمبلغ",
        required=False,
        min_value=Decimal("0"),
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "0", "step": "any"}
        ),
    )

    max_amount = forms.DecimalField(
        label="الحد الأقصى للمبلغ",
        required=False,
        min_value=Decimal("0"),
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "0", "step": "any"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # حسابات الإيرادات
        try:
            income_accounts = ChartOfAccounts.objects.filter(
                is_active=True, is_leaf=True, account_type__name__icontains="إيراد"
            ).order_by("code")
            self.fields["income_account"].queryset = income_accounts
        except Exception:
            self.fields["income_account"].queryset = ChartOfAccounts.objects.none()

        # العملاء
        if Customer:
            try:
                customers = Customer.objects.filter(is_active=True).order_by("name")
                self.fields["customer"].queryset = customers
            except Exception:
                self.fields["customer"].queryset = Customer.objects.none()
        else:
            del self.fields["customer"]
