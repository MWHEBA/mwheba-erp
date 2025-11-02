from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import (
    Purchase,
    PurchaseItem,
    PurchasePayment,
    PurchaseReturn,
    PurchaseReturnItem,
)
from supplier.models import Supplier
from product.models import Product, Warehouse
from django.utils import timezone




class PurchaseForm(forms.ModelForm):
    """
    نموذج إنشاء فاتورة مشتريات جديدة
    """

    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.filter(is_active=True), label="المورد"
    )

    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True), label="المخزن"
    )


    # حقل الخزينة للفواتير النقدية
    financial_account = forms.ModelChoiceField(
        queryset=None,  # سيتم تحديده في __init__
        label="الخزينة/البنك",
        help_text="اختر الخزينة التي سيتم الدفع منها (للفواتير النقدية فقط)",
        required=False,
        empty_label="اختر الخزينة...",
        widget=forms.Select(
            attrs={"class": "form-control", "id": "id_financial_account"}
        ),
    )

    class Meta:
        model = Purchase
        fields = [
            "supplier",
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
        if not self.instance.pk and Purchase.objects.filter(number=number).exists():
            raise ValidationError("رقم الفاتورة موجود بالفعل")
        return number

    def clean_date(self):
        """التحقق من أن تاريخ الفاتورة ليس في المستقبل"""
        date = self.cleaned_data.get("date")
        if date and date > timezone.now().date():
            raise ValidationError("تاريخ الفاتورة لا يمكن أن يكون في المستقبل")
        return date

    def clean_discount(self):
        discount = self.cleaned_data.get("discount", 0)
        if discount < 0:
            raise ValidationError("لا يمكن أن يكون الخصم قيمة سالبة")
        return discount


class PurchaseUpdateForm(forms.ModelForm):
    """
    نموذج تعديل فاتورة المشتريات (فقط للبيانات الأساسية بدون البنود)
    """

    # إضافة حقول للعرض فقط
    supplier_display = forms.CharField(
        label="المورد",
        required=False,
        widget=forms.TextInput(attrs={"readonly": "readonly"}),
    )
    warehouse_display = forms.CharField(
        label="المخزن",
        required=False,
        widget=forms.TextInput(attrs={"readonly": "readonly"}),
    )
    tax = forms.DecimalField(
        label="الضريبة",
        required=False,
        min_value=0,
        initial=0,
        widget=forms.NumberInput(
            attrs={"class": "form-control", "min": 0, "step": 0.01}
        ),
    )

    class Meta:
        model = Purchase
        fields = ["date", "payment_method", "discount", "notes", "number"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "payment_method": forms.Select(attrs={"class": "form-control"}),
            "discount": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "step": 0.01}
            ),
            "number": forms.TextInput(
                attrs={"readonly": "readonly", "class": "form-control"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # لا نسمح بتعديل المورد أو المخزن بعد إنشاء الفاتورة
        for field in self.fields:
            self.fields[field].widget.attrs["class"] = "form-control"

        # إذا كان هناك كائن موجود، نقوم بتعبئة حقول العرض فقط
        if self.instance and self.instance.pk:
            self.initial["supplier_display"] = (
                self.instance.supplier.name if self.instance.supplier else ""
            )
            self.initial["warehouse_display"] = (
                self.instance.warehouse.name if self.instance.warehouse else ""
            )

            # التأكد من توفير قيم افتراضية لحقلي discount و tax
            if "discount" in self.fields and not self.initial.get("discount"):
                self.initial["discount"] = 0
            if "tax" in self.fields and not self.initial.get("tax"):
                self.initial["tax"] = 0

    def clean_discount(self):
        discount = self.cleaned_data.get("discount", 0)
        if discount < 0:
            raise ValidationError("لا يمكن أن يكون الخصم قيمة سالبة")
        return discount

    def clean_tax(self):
        tax = self.cleaned_data.get("tax", 0)
        if tax is None:
            tax = 0
        elif tax < 0:
            raise ValidationError("لا يمكن أن تكون الضريبة قيمة سالبة")
        return tax


class PurchaseItemForm(forms.ModelForm):
    """
    نموذج إضافة عنصر لفاتورة المشتريات
    """

    product = forms.ModelChoiceField(
        queryset=Product.objects.filter(is_active=True), label="المنتج"
    )

    class Meta:
        model = PurchaseItem
        fields = ["product", "quantity", "unit_price"]

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        if quantity <= 0:
            raise ValidationError("الكمية يجب أن تكون أكبر من صفر")
        return quantity


class PurchasePaymentForm(forms.ModelForm):
    """
    نموذج تسجيل دفعة على فاتورة المشتريات
    """

    # إضافة حقل اختيار الحساب المالي
    financial_account = forms.ModelChoiceField(
        queryset=None,  # سيتم تحديده في __init__
        label="الحساب المالي",
        help_text="اختر الخزينة أو البنك المستخدم للدفع",
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
        model = PurchasePayment
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
        self.purchase = kwargs.pop("purchase", None)
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

    def clean_payment_date(self):
        """التحقق من أن تاريخ الدفعة ليس في المستقبل"""
        payment_date = self.cleaned_data.get("payment_date")
        if payment_date and payment_date > timezone.now().date():
            raise ValidationError("تاريخ الدفعة لا يمكن أن يكون في المستقبل")
        return payment_date

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر")

        if self.purchase:
            # التحقق من أن المبلغ لا يتجاوز المبلغ المتبقي
            remaining = self.purchase.amount_due
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


class PurchasePaymentEditForm(forms.ModelForm):
    """
    نموذج تعديل دفعة على فاتورة المشتريات
    """

    # إضافة حقل اختيار الحساب المالي
    financial_account = forms.ModelChoiceField(
        queryset=None,  # سيتم تحديده في __init__
        label="الحساب المالي",
        help_text="اختر الخزينة أو البنك المستخدم للدفع",
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
        model = PurchasePayment
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
        self.purchase = kwargs.pop("purchase", None)
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

    def clean_payment_date(self):
        """التحقق من أن تاريخ الدفعة ليس في المستقبل"""
        payment_date = self.cleaned_data.get("payment_date")
        if payment_date and payment_date > timezone.now().date():
            raise ValidationError("تاريخ الدفعة لا يمكن أن يكون في المستقبل")
        return payment_date

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


class PurchaseReturnForm(forms.ModelForm):
    """
    نموذج مرتجع المشتريات
    """

    class Meta:
        model = PurchaseReturn
        fields = ["date", "warehouse", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs["class"] = "form-control"

        # تعيين التاريخ الحالي كقيمة افتراضية بالتنسيق الصحيح
        if not self.initial.get("date"):
            self.initial["date"] = timezone.now().date().strftime("%Y-%m-%d")

        # جعل حقل المخزن اختياري
        self.fields["warehouse"].required = False
        self.fields["notes"].required = False

    def clean_date(self):
        """التحقق من أن تاريخ المرتجع ليس في المستقبل"""
        date = self.cleaned_data.get("date")
        if date and date > timezone.now().date():
            raise ValidationError("تاريخ المرتجع لا يمكن أن يكون في المستقبل")
        return date


class PurchaseReturnItemForm(forms.ModelForm):
    """
    نموذج بند مرتجع المشتريات
    """

    class Meta:
        model = PurchaseReturnItem
        fields = ["purchase_item", "quantity", "unit_price", "discount", "reason"]
        widgets = {
            "reason": forms.TextInput(attrs={"placeholder": "سبب الإرجاع"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["purchase_item"].queryset = PurchaseItem.objects.none()

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        purchase_item = self.cleaned_data.get("purchase_item")

        if quantity and purchase_item:
            if quantity > purchase_item.quantity:
                raise forms.ValidationError(
                    "الكمية المرتجعة لا يمكن أن تتجاوز الكمية المشتراة"
                )

        return quantity
