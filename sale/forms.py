from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem
from client.models import Customer
from product.models import Product, Stock, Warehouse
from django.db import models
from django.utils import timezone


class SaleForm(forms.ModelForm):
    """
    نموذج إنشاء فاتورة مبيعات جديدة
    """

    customer = forms.ModelChoiceField(
        queryset=Customer.objects.filter(is_active=True), label="العميل"
    )

    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True), label="المخزن"
    )

    # حقل الخزينة للفواتير النقدية
    financial_account = forms.ModelChoiceField(
        queryset=None,  # سيتم تحديده في __init__
        label="الخزينة/البنك",
        help_text="اختر الخزينة التي سيتم استلام المبلغ فيها (للفواتير النقدية فقط)",
        required=False,
        empty_label="اختر الخزينة...",
        widget=forms.Select(
            attrs={"class": "form-control", "id": "id_financial_account"}
        ),
    )

    class Meta:
        model = Sale
        fields = [
            "customer",
            "warehouse",
            "date",
            "number",
            "discount",
            "payment_method",
            "financial_account",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # تعيين تاريخ اليوم كافتراضي بالتنسيق الصحيح
        if not self.initial.get("date"):
            self.initial["date"] = timezone.now().date().strftime("%Y-%m-%d")

        # تعيين أول مخزن بشكل افتراضي
        warehouses = Warehouse.objects.filter(is_active=True)
        if warehouses.exists() and not self.initial.get("warehouse"):
            self.initial["warehouse"] = warehouses.first().pk

        # تعيين طريقة الدفع "نقدي" بشكل افتراضي
        if not self.initial.get("payment_method"):
            self.initial["payment_method"] = "cash"

        # تحديد الحسابات المالية المتاحة (نقدية وبنكية فقط)
        try:
            from financial.models.chart_of_accounts import ChartOfAccounts

            self.fields["financial_account"].queryset = ChartOfAccounts.objects.filter(
                Q(is_cash_account=True) | Q(is_bank_account=True), is_active=True
            ).order_by("code")

            # تعيين الحساب النقدي الافتراضي إذا وجد
            default_cash_account = ChartOfAccounts.objects.filter(
                is_cash_account=True, is_active=True
            ).first()
            if default_cash_account and not self.initial.get("financial_account"):
                self.initial["financial_account"] = default_cash_account.pk

        except ImportError:
            # في حالة عدم وجود النموذج المالي
            self.fields["financial_account"].queryset = self.fields[
                "financial_account"
            ].queryset.none()
            self.fields["financial_account"].required = False

    def clean_number(self):
        number = self.cleaned_data.get("number")
        if not self.instance.pk and Sale.objects.filter(number=number).exists():
            raise ValidationError("رقم الفاتورة موجود بالفعل")
        return number

    def clean_discount(self):
        discount = self.cleaned_data.get("discount", 0)
        if discount < 0:
            raise ValidationError("لا يمكن أن يكون الخصم قيمة سالبة")
        return discount


class SaleItemForm(forms.ModelForm):
    """
    نموذج إضافة عنصر لفاتورة المبيعات
    """

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True), label="المنتج"
    )

    class Meta:
        model = SaleItem
        fields = ["product", "quantity", "unit_price"]

    def __init__(self, *args, **kwargs):
        self.warehouse = kwargs.pop("warehouse", None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get("product")
        quantity = cleaned_data.get("quantity")

        if not product or not quantity or not self.warehouse:
            return cleaned_data

        # التحقق من وجود سعر تكلفة للمنتج
        if not product.cost_price or product.cost_price == 0:
            raise ValidationError(
                f"⚠️ المنتج '{product.name}' ليس له سعر تكلفة محدد. "
                f"يرجى تحديد سعر التكلفة قبل البيع لضمان دقة الحسابات المحاسبية."
            )

        # التحقق من توفر المخزون الكافي
        available_stock = (
            Stock.objects.filter(product=product, warehouse=self.warehouse)
            .aggregate(total=models.Sum("quantity"))
            .get("total")
            or 0
        )

        if quantity > available_stock:
            raise ValidationError(
                f"الكمية المتوفرة من {product.name} في المخزن هي {available_stock} فقط"
            )

        return cleaned_data


class SalePaymentForm(forms.ModelForm):
    """
    نموذج تسجيل دفعة على فاتورة المبيعات
    """

    # إضافة حقل اختيار الحساب المالي
    financial_account = forms.ModelChoiceField(
        queryset=None,  # سيتم تحديده في __init__
        label="الحساب المالي",
        help_text="اختر الخزينة أو البنك المستخدم لاستقبال الدفعة",
        required=True,
        empty_label="اختر الحساب المالي...",  # تخصيص النص الافتراضي
        widget=forms.Select(
            attrs={
                "class": "form-control select2",
                "data-placeholder": "اختر الحساب المالي...",
            }
        ),
    )

    class Meta:
        model = SalePayment
        fields = [
            "financial_account",
            "amount",
            "payment_date",
            "payment_method",
            "reference_number",
            "notes",
        ]
        widgets = {
            "payment_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "payment_method": forms.Select(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "any", "min": "0"}
            ),
            "reference_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "رقم المرجع (اختياري)"}
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "form-control",
                    "placeholder": "ملاحظات (اختياري)",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        self.sale = kwargs.pop("sale", None)
        super().__init__(*args, **kwargs)

        # تحديد الحسابات المالية المتاحة (نقدية وبنكية فقط)
        try:
            from financial.models.chart_of_accounts import ChartOfAccounts

            self.fields["financial_account"].queryset = ChartOfAccounts.objects.filter(
                Q(is_cash_account=True) | Q(is_bank_account=True), is_active=True
            ).order_by("code")

            # تعيين الحساب النقدي الافتراضي إذا وجد
            default_cash_account = ChartOfAccounts.objects.filter(
                is_cash_account=True, is_active=True
            ).first()
            if default_cash_account and not self.initial.get("financial_account"):
                self.initial["financial_account"] = default_cash_account.pk

        except ImportError:
            # في حالة عدم وجود النموذج المالي
            self.fields["financial_account"].queryset = self.fields[
                "financial_account"
            ].queryset.none()
            self.fields["financial_account"].required = False
            self.fields["financial_account"].help_text = "النظام المالي غير متاح حالياً"

        # تعيين التاريخ الحالي كافتراضي
        if not self.initial.get("payment_date"):
            self.initial["payment_date"] = timezone.now().date()

        # إضافة CSS classes للحقول
        for field_name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "form-control"

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر")

        if self.sale:
            # التحقق من أن المبلغ لا يتجاوز المبلغ المتبقي
            remaining = self.sale.amount_due
            if amount > remaining:
                raise ValidationError(f"المبلغ يتجاوز المبلغ المتبقي ({remaining:.2f})")

        return amount

    def clean_financial_account(self):
        financial_account = self.cleaned_data.get("financial_account")

        if financial_account:
            # التحقق من أن الحساب نقدي أو بنكي
            if not (
                financial_account.is_cash_account or financial_account.is_bank_account
            ):
                raise ValidationError("يجب اختيار حساب نقدي أو بنكي فقط")

            # التحقق من أن الحساب نشط
            if not financial_account.is_active:
                raise ValidationError("الحساب المحدد غير نشط")

        return financial_account

    def clean(self):
        cleaned_data = super().clean()

        # التحقق من تطابق طريقة الدفع مع نوع الحساب
        payment_method = cleaned_data.get("payment_method")
        financial_account = cleaned_data.get("financial_account")

        if payment_method and financial_account:
            if payment_method == "cash" and not financial_account.is_cash_account:
                raise ValidationError(
                    {
                        "financial_account": "يجب اختيار حساب نقدي عند اختيار الدفع النقدي"
                    }
                )
            elif (
                payment_method in ["bank_transfer", "check"]
                and not financial_account.is_bank_account
            ):
                raise ValidationError(
                    {
                        "financial_account": "يجب اختيار حساب بنكي عند اختيار التحويل البنكي أو الشيك"
                    }
                )

        return cleaned_data


class SalePaymentEditForm(forms.ModelForm):
    """
    نموذج تعديل دفعة على فاتورة المبيعات
    """

    # إضافة حقل اختيار الحساب المالي
    financial_account = forms.ModelChoiceField(
        queryset=None,  # سيتم تحديده في __init__
        label="الحساب المالي",
        help_text="اختر الخزينة أو البنك المستخدم لاستقبال الدفعة",
        required=True,
        empty_label="اختر الحساب المالي...",
        widget=forms.Select(
            attrs={
                "class": "form-control select2",
                "data-placeholder": "اختر الحساب المالي...",
            }
        ),
    )

    class Meta:
        model = SalePayment
        fields = [
            "financial_account",
            "amount",
            "payment_date",
            "payment_method",
            "reference_number",
            "notes",
        ]
        widgets = {
            "payment_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "payment_method": forms.Select(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(
                attrs={"class": "form-control", "step": "any", "min": "0"}
            ),
            "reference_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "رقم المرجع (اختياري)"}
            ),
            "notes": forms.Textarea(
                attrs={
                    "rows": 2,
                    "class": "form-control",
                    "placeholder": "ملاحظات (اختياري)",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        self.sale = kwargs.pop("sale", None)
        super().__init__(*args, **kwargs)

        # تحديد الحسابات المالية المتاحة (نقدية وبنكية فقط)
        try:
            from financial.models.chart_of_accounts import ChartOfAccounts

            self.fields["financial_account"].queryset = ChartOfAccounts.objects.filter(
                Q(is_cash_account=True) | Q(is_bank_account=True), is_active=True
            ).order_by("code")

        except ImportError:
            # في حالة عدم وجود النموذج المالي
            self.fields["financial_account"].queryset = self.fields[
                "financial_account"
            ].queryset.none()
            self.fields["financial_account"].required = False
            self.fields["financial_account"].help_text = "النظام المالي غير متاح حالياً"

        # إضافة CSS classes للحقول
        for field_name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "form-control"

        # إضافة تحذير للدفعات المرحّلة
        if self.instance and self.instance.pk and self.instance.is_posted:
            for field in self.fields.values():
                field.help_text = "تحذير: تعديل هذه الدفعة سيؤثر على الأرصدة المحاسبية"

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر")

        # لا نتحقق من المبلغ المتبقي في حالة التعديل
        # لأن المستخدم قد يريد تعديل مبلغ موجود

        return amount

    def clean_financial_account(self):
        financial_account = self.cleaned_data.get("financial_account")

        if financial_account:
            # التحقق من أن الحساب نقدي أو بنكي
            if not (
                financial_account.is_cash_account or financial_account.is_bank_account
            ):
                raise ValidationError("يجب اختيار حساب نقدي أو بنكي فقط")

            # التحقق من أن الحساب نشط
            if not financial_account.is_active:
                raise ValidationError("الحساب المحدد غير نشط")

        return financial_account

    def clean(self):
        cleaned_data = super().clean()

        # التحقق من تطابق طريقة الدفع مع نوع الحساب
        payment_method = cleaned_data.get("payment_method")
        financial_account = cleaned_data.get("financial_account")

        if payment_method and financial_account:
            if payment_method == "cash" and not financial_account.is_cash_account:
                raise ValidationError(
                    {
                        "financial_account": "يجب اختيار حساب نقدي عند اختيار الدفع النقدي"
                    }
                )
            elif (
                payment_method in ["bank_transfer", "check"]
                and not financial_account.is_bank_account
            ):
                raise ValidationError(
                    {
                        "financial_account": "يجب اختيار حساب بنكي عند اختيار التحويل البنكي أو الشيك"
                    }
                )

        return cleaned_data


class SaleReturnForm(forms.ModelForm):
    """
    نموذج مرتجع المبيعات
    """

    class Meta:
        model = SaleReturn
        fields = ["date", "warehouse", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # تعيين تاريخ اليوم كافتراضي بالتنسيق الصحيح
        if not self.initial.get("date"):
            self.initial["date"] = timezone.now().date().strftime("%Y-%m-%d")


class SaleReturnItemForm(forms.ModelForm):
    """
    نموذج بند مرتجع المبيعات
    """

    class Meta:
        model = SaleReturnItem
        fields = ["sale_item", "quantity", "unit_price", "discount", "reason"]
        widgets = {
            "reason": forms.TextInput(attrs={"placeholder": "سبب الإرجاع"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sale_item"].queryset = SaleItem.objects.none()

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        sale_item = self.cleaned_data.get("sale_item")

        if quantity and sale_item:
            if quantity > sale_item.quantity:
                raise forms.ValidationError(
                    "الكمية المرتجعة لا يمكن أن تتجاوز الكمية المباعة"
                )

        return quantity
