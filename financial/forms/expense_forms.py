from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import models
from decimal import Decimal
from ..models import ChartOfAccounts, AccountType, JournalEntry, JournalEntryLine

try:
    from client.models import Customer
    from supplier.models import Supplier
except ImportError:
    Customer = None
    Supplier = None


class ExpenseForm(forms.Form):
    """نموذج إنشاء مصروف جديد"""

    # معلومات أساسية
    description = forms.CharField(
        label="وصف المصروف",
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "أدخل وصف المصروف"}
        ),
    )

    amount = forms.DecimalField(
        label="المبلغ",
        max_digits=15,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "placeholder": "0", "step": "any"}
        ),
    )

    expense_date = forms.DateField(
        label="تاريخ المصروف",
        initial=timezone.now().date(),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "اختر تاريخ المصروف..."
        }),
    )
    # الحسابات المحاسبية
    expense_account = forms.ModelChoiceField(
        label="حساب المصروف",
        queryset=None,
        empty_label="اختر حساب المصروف",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    payment_account = forms.ModelChoiceField(
        label="حساب الدفع",
        queryset=None,
        empty_label="اختر حساب الدفع",
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

    # ربط بالموردين
    supplier = forms.ModelChoiceField(
        label="المورد",
        queryset=None,
        required=False,
        empty_label="اختر المورد (اختياري)",
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

        # حسابات المصروفات
        try:
            expense_accounts = ChartOfAccounts.objects.filter(
                is_active=True, is_leaf=True, account_type__name__icontains="مصروف"
            ).order_by("code")
            self.fields["expense_account"].queryset = expense_accounts
        except Exception:
            self.fields["expense_account"].queryset = ChartOfAccounts.objects.none()

        # الحسابات النقدية والبنكية
        try:
            payment_accounts = (
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
            self.fields["payment_account"].queryset = payment_accounts
        except Exception:
            self.fields["payment_account"].queryset = ChartOfAccounts.objects.none()

        # الموردين
        if Supplier:
            try:
                suppliers = Supplier.objects.filter(is_active=True).order_by("name")
                self.fields["supplier"].queryset = suppliers
            except Exception:
                self.fields["supplier"].queryset = Supplier.objects.none()
        else:
            # إخفاء حقل المورد إذا لم يكن متوفراً
            del self.fields["supplier"]

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount and amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر")
        return amount

    def clean_expense_date(self):
        expense_date = self.cleaned_data.get("expense_date")
        if expense_date and expense_date > timezone.now().date():
            raise ValidationError("تاريخ المصروف لا يمكن أن يكون في المستقبل")
        return expense_date

    def clean(self):
        cleaned_data = super().clean()
        expense_account = cleaned_data.get("expense_account")
        payment_account = cleaned_data.get("payment_account")

        # التأكد من عدم تطابق الحسابات
        if expense_account and payment_account and expense_account == payment_account:
            raise ValidationError("حساب المصروف وحساب الدفع يجب أن يكونا مختلفين")

        return cleaned_data


class ExpenseEditForm(ExpenseForm):
    """نموذج تعديل مصروف موجود"""

    def __init__(self, *args, **kwargs):
        self.journal_entry = kwargs.pop("journal_entry", None)
        super().__init__(*args, **kwargs)

        if self.journal_entry:
            # ملء البيانات من القيد المحاسبي
            self.initial["description"] = self.journal_entry.description
            self.initial["expense_date"] = self.journal_entry.date
            self.initial["reference"] = self.journal_entry.reference
            self.initial["notes"] = self.journal_entry.notes

            # استخراج المبلغ والحسابات من بنود القيد
            lines = self.journal_entry.lines.all()
            for line in lines:
                if line.debit > 0:
                    # حساب المصروف (مدين)
                    self.initial["expense_account"] = line.account
                    self.initial["amount"] = line.debit
                elif line.credit > 0:
                    # حساب الدفع (دائن)
                    self.initial["payment_account"] = line.account


class ExpenseFilterForm(forms.Form):
    """نموذج تصفية المصروفات"""

    date_from = forms.DateField(
        label="من تاريخ",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "من تاريخ..."
        }),
    )

    date_to = forms.DateField(
        label="إلى تاريخ",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "إلى تاريخ..."
        }),
    )

    expense_account = forms.ModelChoiceField(
        label="حساب المصروف",
        queryset=None,
        required=False,
        empty_label="جميع الحسابات",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    supplier = forms.ModelChoiceField(
        label="المورد",
        queryset=None,
        required=False,
        empty_label="جميع الموردين",
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

        # حسابات المصروفات
        try:
            expense_accounts = ChartOfAccounts.objects.filter(
                is_active=True, is_leaf=True, account_type__name__icontains="مصروف"
            ).order_by("code")
            self.fields["expense_account"].queryset = expense_accounts
        except Exception:
            self.fields["expense_account"].queryset = ChartOfAccounts.objects.none()

        # الموردين
        if Supplier:
            try:
                suppliers = Supplier.objects.filter(is_active=True).order_by("name")
                self.fields["supplier"].queryset = suppliers
            except Exception:
                self.fields["supplier"].queryset = Supplier.objects.none()
        else:
            del self.fields["supplier"]
