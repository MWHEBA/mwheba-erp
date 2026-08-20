from decimal import Decimal
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem, Quotation, CustomFieldDefinition
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

    # نوع الفاتورة
    invoice_type = forms.ChoiceField(
        label="نوع الفاتورة",
        choices=[
            ("credit", "آجل"),
            ("cash", "نقدي"),
        ],
        initial="credit",
        widget=forms.Select(attrs={"class": "form-select select2", "id": "id_invoice_type"}),
    )

    # مبلغ الدفعة المقدمة
    down_payment_amount = forms.DecimalField(
        label="مبلغ الدفعة المقدمة",
        max_digits=12,
        decimal_places=2,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "id": "id_down_payment_amount", "min": "0"}),
    )

    # حقل طريقة الدفع - ديناميكي يدعم account codes
    payment_method = forms.ChoiceField(
        label="حساب الدفع",
        help_text="اختر حساب الخزينة أو البنك للمعاملة النقدية أو الدفعة المقدمة",
        required=False,  # سيتم التحقق منه في clean() حسب نوع الفاتورة
        widget=forms.Select(
            attrs={"class": "form-control", "id": "id_payment_method"}
        ),
    )

    # حقل التصنيف المالي
    financial_category = forms.ChoiceField(
        label="التصنيف المالي",
        help_text="اختر التصنيف المالي للإيراد",
        required=False,
        widget=forms.Select(
            attrs={"class": "form-control", "id": "id_financial_category"}
        ),
    )

    # نوع الخصم والتسوية
    discount_type = forms.ChoiceField(
        label="نوع الخصم",
        choices=[("fixed", "العملة"), ("percentage", "%")],
        initial="fixed",
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_discount_type"}),
    )

    adjustment_name = forms.CharField(
        label="اسم/بيان التسوية",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "id": "id_adjustment_name", "placeholder": "مثال: مصاريف شحن / تغليف / تسوية"}),
    )

    adjustment_type = forms.ChoiceField(
        label="نوع التسوية",
        choices=[("add", "إضافة (+)"), ("subtract", "خصم (-)")],
        initial="add",
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_adjustment_type"}),
    )

    adjustment_amount = forms.DecimalField(
        label="مبلغ التسوية",
        max_digits=12,
        decimal_places=2,
        required=False,
        initial=0,
        widget=forms.NumberInput(attrs={"class": "form-control", "id": "id_adjustment_amount", "min": "0", "placeholder": "0.00"}),
    )

    salesman = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(),
        label="مسؤول المبيعات",
        required=False,
        widget=forms.Select(attrs={"class": "form-control select2", "id": "id_salesman"}),
    )

    class Meta:
        model = Sale
        fields = [
            "customer",
            "warehouse",
            "salesman",
            "date",
            "number",
            "discount",
            "discount_type",
            "adjustment_name",
            "adjustment_amount",
            "tax_active",
            "vat_active",
            "vat_rate",
            "wht_active",
            "wht_rate",
            "wht_amount",
            "payment_method",
            "financial_category",
            "notes",
            "work_order",
        ]
        widgets = {
            "date": forms.TextInput(attrs={
                "class": "form-control",
                "data-date-picker": True,
                "placeholder": "اختر تاريخ الفاتورة..."
            }),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        self.user = user
        super().__init__(*args, **kwargs)

        can_change_salesman = False
        if user:
            can_change_salesman = (
                user.is_superuser or
                getattr(user, 'is_admin', False) or
                user.has_perm('sale.change_sale_salesman') or
                user.has_perm('users.تغيير_مسؤول_المبيعات')
            )
        self.can_change_salesman = can_change_salesman

        from django.contrib.auth import get_user_model
        User = get_user_model()
        salesman_qs = User.objects.filter(is_active=True).order_by('first_name', 'username')
        if self.instance and self.instance.pk and self.instance.salesman_id:
            salesman_qs = User.objects.filter(
                models.Q(is_active=True) | models.Q(pk=self.instance.salesman_id)
            ).order_by('first_name', 'username')
        self.fields['salesman'].queryset = salesman_qs

        if not self.instance.pk and user and not self.initial.get('salesman'):
            self.initial['salesman'] = user.pk

        from work_order.models import WorkOrder
        self.fields['work_order'] = forms.ModelChoiceField(
            queryset=WorkOrder.objects.all(),
            required=False,
            widget=forms.HiddenInput()
        )

        # تعيين تاريخ اليوم كافتراضي بالتنسيق الصحيح
        if not self.initial.get("date"):
            self.initial["date"] = timezone.now().date().strftime("%Y-%m-%d")

        # تعيين أول مخزن بشكل افتراضي
        warehouses = Warehouse.objects.filter(is_active=True)
        if warehouses.exists() and not self.initial.get("warehouse"):
            self.initial["warehouse"] = warehouses.first().pk

        # إعداد خيارات طريقة الدفع (حسابات الخزائن والبنوك والرصيد المسبق)
        payment_choices = [
            ('', 'اختر حساب الدفع'),
            ('PREPAID_BALANCE', '💳 رصيد مسبق / دفعة مقدمة'),
        ]
        
        # إضافة حسابات الدفع من النظام المالي المركزي
        try:
            from financial.services.account_helper import AccountHelperService
            payment_accounts = AccountHelperService.get_cash_and_bank_accounts()
            for account in payment_accounts:
                payment_choices.append((account.code, f"{account.name} ({account.code})"))
        except Exception:
            pass

        current_method = self.data.get('payment_method') or self.initial.get('payment_method') or (self.instance.payment_method if self.instance and self.instance.pk else None)
        if current_method and current_method not in [c[0] for c in payment_choices]:
            try:
                from financial.models import ChartOfAccounts
                acc = ChartOfAccounts.objects.filter(code=current_method).first()
                if acc:
                    payment_choices.append((acc.code, f"{acc.name} ({acc.code})"))
                else:
                    payment_choices.append((current_method, current_method))
            except Exception:
                payment_choices.append((current_method, current_method))

        self.fields['payment_method'].choices = payment_choices
        
        # تعيين نوع الفاتورة والقيم الافتراضية عند التعديل أو الإنشاء
        if self.instance and self.instance.pk:
            # حالة التعديل
            if self.instance.payment_method == 'credit':
                self.initial['invoice_type'] = 'credit'
                self.initial['payment_method'] = ''
                self.initial['down_payment_amount'] = Decimal('0')
            elif self.instance.payment_status == 'paid' and self.instance.payment_method not in ['credit', 'credit_with_downpayment']:
                self.initial['invoice_type'] = 'cash'
                self.initial['payment_method'] = self.instance.payment_method
                self.initial['down_payment_amount'] = Decimal('0')
            else:
                self.initial['invoice_type'] = 'credit'
                self.initial['payment_method'] = self.instance.payment_method if self.instance.payment_method != 'credit' else ''
                # استخراج مبلغ الدفعة الأولى المرتبطة بالفاتورة كدفعة مقدمة
                first_payment = self.instance.payments.filter(status='posted').first()
                if first_payment:
                    self.initial['down_payment_amount'] = first_payment.amount
                    if not self.initial['payment_method'] and first_payment.payment_method:
                        self.initial['payment_method'] = first_payment.payment_method
        else:
            # حالة الإنشاء الجديد
            self.initial['invoice_type'] = 'credit'
            self.initial['payment_method'] = ''
            self.initial['down_payment_amount'] = Decimal('0')

        # تفعيل الضريبة افتراضياً للفواتير الجديدة ديناميكياً حسب إعدادات النظام
        if not self.instance.pk:
            from core.models import SystemSetting
            enable_tax = SystemSetting.get_setting("enable_tax", True)
            if isinstance(enable_tax, str):
                enable_tax = enable_tax.lower() in ["true", "1", "yes", "نعم"]
            self.initial.setdefault("tax_active", bool(enable_tax))
            self.initial.setdefault("vat_active", bool(enable_tax))
            default_rate = SystemSetting.get_setting("default_tax_rate", 14)
            self.initial.setdefault("vat_rate", default_rate)

        # إعداد خيارات التصنيف المالي (إيرادات)
        try:
            from financial.models import FinancialCategory

            category_choices = [('', 'اختر التصنيف المالي')]
            financial_categories = FinancialCategory.objects.filter(
                is_active=True,
                default_revenue_account__isnull=False
            ).prefetch_related('subcategories').order_by('display_order', 'name')

            for cat in financial_categories:
                category_choices.append((f"cat_{cat.pk}", f"📁 {cat.name}"))
                for subcat in cat.subcategories.filter(is_active=True).order_by('display_order', 'name'):
                    category_choices.append((f"sub_{subcat.pk}", f"   ↳ {subcat.name}"))

            self.fields['financial_category'].choices = category_choices

            if self.instance and self.instance.pk and self.instance.financial_category:
                from financial.models import FinancialSubcategory
                if isinstance(self.instance.financial_category, FinancialCategory):
                    self.initial['financial_category'] = f"cat_{self.instance.financial_category.pk}"
        except Exception:
            self.fields['financial_category'].choices = [('', 'اختر التصنيف المالي')]

        # ضبط الحقول الاختيارية والافتراضية
        for field_name in [
            "number", "discount", "discount_type", "adjustment_name",
            "adjustment_amount", "tax_active", "vat_active", "vat_rate",
            "wht_active", "wht_rate", "wht_amount", "notes"
        ]:
            if field_name in self.fields:
                self.fields[field_name].required = False

    def clean_salesman(self):
        salesman = self.cleaned_data.get('salesman')
        user = getattr(self, 'user', None)
        can_change = (
            user and (
                user.is_superuser or
                getattr(user, 'is_admin', False) or
                user.has_perm('sale.change_sale_salesman') or
                user.has_perm('users.تغيير_مسؤول_المبيعات')
            )
        )
        if not can_change:
            if self.instance and self.instance.pk and self.instance.salesman:
                return self.instance.salesman
            return user

        return salesman or user

    def clean(self):
        cleaned_data = super().clean()
        invoice_type = cleaned_data.get('invoice_type')
        payment_method = cleaned_data.get('payment_method')
        down_payment_amount = cleaned_data.get('down_payment_amount') or Decimal('0')
        
        # التحقق من حساب الدفع حسب نوع الفاتورة
        if invoice_type == 'cash':
            if not payment_method or payment_method == '':
                raise ValidationError({'payment_method': 'يجب اختيار حساب دفع (خزينة/بنك) للفاتورة النقدية.'})
            cleaned_data['down_payment_amount'] = Decimal('0')
        
        elif invoice_type == 'credit':
            if down_payment_amount > Decimal('0'):
                if not payment_method or payment_method == '':
                    raise ValidationError({'payment_method': 'يجب اختيار حساب دفع (خزينة/بنك) للدفعة المقدمة.'})
            else:
                cleaned_data['payment_method'] = 'credit'
                cleaned_data['down_payment_amount'] = Decimal('0')
            
        return cleaned_data

    def clean_financial_category(self):
        """معالجة التصنيف المالي - تحويل من ID إلى كائن"""
        value = self.cleaned_data.get('financial_category')
        if not value:
            return None
        try:
            from financial.models import FinancialCategory, FinancialSubcategory
            if value.startswith('cat_'):
                cat_id = int(value.replace('cat_', ''))
                return FinancialCategory.objects.get(pk=cat_id, is_active=True)
            elif value.startswith('sub_'):
                subcat_id = int(value.replace('sub_', ''))
                subcat = FinancialSubcategory.objects.select_related('parent_category').get(pk=subcat_id, is_active=True)
                return subcat.parent_category
            else:
                raise ValidationError('صيغة التصنيف المالي غير صحيحة')
        except (ImportError, ValueError, Exception) as e:
            raise ValidationError(f'خطأ في معالجة التصنيف المالي: {str(e)}')

    def clean_number(self):
        number = self.cleaned_data.get("number")
        if number and not self.instance.pk and Sale.objects.filter(number=number).exists():
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
    
    # Override payment_method field لدعم account codes
    # حسب unified-components-guide.md
    payment_method = forms.ChoiceField(
        required=True,
        label='طريقة الدفع (الخزينة/البنك)',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = SalePayment
        fields = [
            "amount",
            "payment_date",
            "payment_method",
            "reference_number",
            "notes",
        ]
        widgets = {
            "payment_date": forms.TextInput(attrs={
                "class": "form-control",
                "data-date-picker": True,
                "placeholder": "اختر تاريخ الدفع..."
            }),
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

        # تحميل حسابات الدفع ديناميكياً
        try:
            from financial.services.account_helper import AccountHelperService
            payment_accounts = AccountHelperService.get_cash_and_bank_accounts()
            
            choices = [('', 'اختر حساب الدفع')]
            for account in payment_accounts:
                choices.append((account.code, f"{account.name} ({account.code})"))
            
            current_method = self.data.get('payment_method') or self.initial.get('payment_method') or (self.instance.payment_method if self.instance and self.instance.pk else None)
            if current_method and current_method not in [c[0] for c in choices]:
                try:
                    from financial.models import ChartOfAccounts
                    acc = ChartOfAccounts.objects.filter(code=current_method).first()
                    if acc:
                        choices.append((acc.code, f"{acc.name} ({acc.code})"))
                    else:
                        choices.append((current_method, current_method))
                except Exception:
                    choices.append((current_method, current_method))

            self.fields['payment_method'].choices = choices
            
            # Handle old values when editing
            if self.instance and self.instance.pk and self.instance.payment_method:
                old_value = self.instance.payment_method
                if old_value == 'cash':
                    from financial.services.role_registry import AccountRoleRegistry
                    default_cash = AccountRoleRegistry.get_account_by_role("CASH_CONTROL_ACCOUNT")
                    if default_cash:
                        self.initial['payment_method'] = default_cash.code
                elif old_value == 'bank_transfer':
                    from financial.services.role_registry import AccountRoleRegistry
                    default_bank = AccountRoleRegistry.get_account_role("BANK_CONTROL_ACCOUNT")
                    if default_bank:
                        self.initial['payment_method'] = default_bank.code
                else:
                    self.initial['payment_method'] = old_value
        except Exception:
            # Fallback to default choices on any error
            choices = [
                ('', 'اختر طريقة الدفع'),
                ('cash', 'نقداً'),
                ('bank_transfer', 'تحويل بنكي'),
            ]
            current_method = self.data.get('payment_method') or self.initial.get('payment_method') or (self.instance.payment_method if self.instance and self.instance.pk else None)
            if current_method and current_method not in [c[0] for c in choices]:
                choices.append((current_method, current_method))
            self.fields['payment_method'].choices = choices
        
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

        if self.sale:
            # التحقق من أن المبلغ لا يتجاوز المبلغ المتبقي
            remaining = self.sale.amount_due
            if amount > remaining:
                raise ValidationError(f"المبلغ يتجاوز المبلغ المتبقي ({remaining:.2f})")

        return amount


class SalePaymentEditForm(forms.ModelForm):
    """
    نموذج تعديل دفعة على فاتورة المبيعات
    """

    # حقل طريقة الدفع - ديناميكي يدعم account codes
    payment_method = forms.ChoiceField(
        label="طريقة الدفع (الخزينة/البنك)",
        help_text="اختر حساب الدفع",
        required=True,
        widget=forms.Select(
            attrs={"class": "form-control select2"}
        ),
    )

    class Meta:
        model = SalePayment
        fields = [
            "amount",
            "payment_date",
            "payment_method",
            "reference_number",
            "notes",
        ]
        widgets = {
            "payment_date": forms.TextInput(attrs={
                "class": "form-control",
                "data-date-picker": True,
                "placeholder": "اختر تاريخ الدفع..."
            }),
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

        # إعداد خيارات طريقة الدفع
        payment_choices = [('', 'اختر حساب الدفع')]
        
        try:
            from financial.services.account_helper import AccountHelperService
            payment_accounts = AccountHelperService.get_cash_and_bank_accounts()
            for account in payment_accounts:
                payment_choices.append((account.code, f"{account.name} ({account.code})"))
                
        except Exception:
            payment_choices = [
                ('', 'اختر طريقة الدفع'),
                ('cash', 'نقداً'),
                ('bank_transfer', 'تحويل بنكي'),
            ]
        
        current_method = self.data.get('payment_method') or self.initial.get('payment_method') or (self.instance.payment_method if self.instance and self.instance.pk else None)
        if current_method and current_method not in [c[0] for c in payment_choices]:
            try:
                from financial.models import ChartOfAccounts
                acc = ChartOfAccounts.objects.filter(code=current_method).first()
                if acc:
                    payment_choices.append((acc.code, f"{acc.name} ({acc.code})"))
                else:
                    payment_choices.append((current_method, current_method))
            except Exception:
                payment_choices.append((current_method, current_method))

        self.fields['payment_method'].choices = payment_choices
        
        # Handle old values when editing
        if self.instance and self.instance.pk and self.instance.payment_method:
            old_value = self.instance.payment_method
            # تحويل القيم القديمة
            if old_value == 'cash':
                try:
                    from financial.services.role_registry import AccountRoleRegistry
                    default_cash = AccountRoleRegistry.get_account_by_role("CASH_CONTROL_ACCOUNT")
                    if default_cash:
                        self.initial['payment_method'] = default_cash.code
                except:
                    self.initial['payment_method'] = 'cash'
            elif old_value == 'bank_transfer':
                try:
                    from financial.services.role_registry import AccountRoleRegistry
                    default_bank = AccountRoleRegistry.get_account_by_role("BANK_CONTROL_ACCOUNT")
                    if default_bank:
                        self.initial['payment_method'] = default_bank.code
                except:
                    self.initial['payment_method'] = 'bank_transfer'
            else:
                # Already an account code - verify it exists
                try:
                    from financial.models import ChartOfAccounts
                    if ChartOfAccounts.objects.filter(code=old_value, is_active=True).exists():
                        self.initial['payment_method'] = old_value
                except:
                    pass

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

        from decimal import Decimal

        sale = getattr(self, 'sale', None)
        if not sale and self.instance and hasattr(self.instance, 'sale') and self.instance.sale_id:
            sale = self.instance.sale

        if sale:
            if self.instance and self.instance.pk:
                remaining = sale.amount_due + (self.instance.amount or Decimal('0'))
            else:
                remaining = sale.amount_due

            if remaining < Decimal('0'):
                remaining = Decimal('0.00')

            if amount > remaining:
                raise ValidationError(
                    f"المبلغ المدخل ({amount}) يتجاوز المبلغ المتبقي على الفاتورة ({remaining:.2f} ج.م)"
                )

        return amount


class SaleReturnForm(forms.ModelForm):
    """
    نموذج مرتجع المبيعات
    """

    class Meta:
        model = SaleReturn
        fields = ["date", "warehouse", "notes"]
        widgets = {
            "date": forms.TextInput(attrs={
                "class": "form-control",
                "data-date-picker": True,
                "placeholder": "اختر تاريخ المرتجع..."
            }),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # تعيين تاريخ اليوم كافتراضي بالتنسيق الصحيح
        if not self.initial.get("date"):
            self.initial["date"] = timezone.now().date().strftime("%Y-%m-%d")

    def clean_date(self):
        """التحقق من أن تاريخ المرتجع ليس في المستقبل"""
        date = self.cleaned_data.get("date")
        if date and date > timezone.now().date():
            raise ValidationError("تاريخ المرتجع لا يمكن أن يكون في المستقبل")
        return date


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


class QuotationForm(forms.ModelForm):
    """
    نموذج إنشاء وتعديل عرض سعر
    """
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.filter(is_active=True), label="العميل",
        widget=forms.Select(attrs={"class": "form-control select2", "id": "id_customer"})
    )
    salesman = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(),
        label="مسؤول المبيعات",
        required=False,
        widget=forms.Select(attrs={"class": "form-control select2", "id": "id_salesman"}),
    )
    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.filter(is_active=True),
        label="المخزن",
        required=False,
        widget=forms.Select(attrs={"class": "form-control select2", "id": "id_warehouse"}),
    )

    class Meta:
        model = Quotation
        fields = [
            "customer",
            "salesman",
            "warehouse",
            "date",
            "valid_until",
            "discount",
            "adjustment_name",
            "adjustment_amount",
            "tax_active",
            "vat_active",
            "vat_rate",
            "wht_active",
            "wht_rate",
            "wht_amount",
            "currency",
            "exchange_rate",
            "total_foreign",
            "total_functional",
            "notes",
            "work_order",
        ]
        widgets = {
            "date": forms.TextInput(attrs={
                "class": "form-control",
                "data-date-picker": True,
                "placeholder": "اختر تاريخ عرض السعر..."
            }),
            "valid_until": forms.TextInput(attrs={
                "class": "form-control",
                "data-date-picker": True,
                "placeholder": "اختر تاريخ انتهاء الصلاحية..."
            }),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        self.user = user
        super().__init__(*args, **kwargs)
        
        can_change_salesman = False
        if user:
            can_change_salesman = (
                user.is_superuser or
                getattr(user, 'is_admin', False) or
                user.has_perm('sale.change_sale_salesman') or
                user.has_perm('users.تغيير_مسؤول_المبيعات')
            )
        self.can_change_salesman = can_change_salesman

        from django.contrib.auth import get_user_model
        User = get_user_model()
        salesman_qs = User.objects.filter(is_active=True).order_by('first_name', 'username')
        if self.instance and self.instance.pk and self.instance.salesman_id:
            salesman_qs = User.objects.filter(
                models.Q(is_active=True) | models.Q(pk=self.instance.salesman_id)
            ).order_by('first_name', 'username')
        self.fields['salesman'].queryset = salesman_qs

        if not self.instance.pk and user and not self.initial.get('salesman'):
            self.initial['salesman'] = user.pk

        from work_order.models import WorkOrder
        self.fields['work_order'] = forms.ModelChoiceField(
            queryset=WorkOrder.objects.all(),
            required=False,
            widget=forms.HiddenInput()
        )
        if not self.initial.get("date"):
            self.initial["date"] = timezone.now().date().strftime("%Y-%m-%d")
        if not self.initial.get("status"):
            self.initial["status"] = "draft"
        
        # تعيين أول مخزن بشكل افتراضي
        warehouses = Warehouse.objects.filter(is_active=True)
        if warehouses.exists() and not self.initial.get("warehouse"):
            self.initial["warehouse"] = warehouses.first().pk

        # تفعيل الضريبة افتراضياً لعروض الأسعار الجديدة ديناميكياً حسب إعدادات النظام
        if not self.instance.pk:
            from core.models import SystemSetting
            enable_tax = SystemSetting.get_setting("enable_tax", True)
            if isinstance(enable_tax, str):
                enable_tax = enable_tax.lower() in ["true", "1", "yes", "نعم"]
            self.initial.setdefault("tax_active", bool(enable_tax))
            self.initial.setdefault("vat_active", bool(enable_tax))
            default_rate = SystemSetting.get_setting("default_tax_rate", 14)
            self.initial.setdefault("vat_rate", default_rate)

        for field_name in ["discount", "tax_active", "vat_active", "vat_rate", "wht_active", "wht_rate", "wht_amount", "adjustment_name", "adjustment_amount", "currency", "exchange_rate", "total_foreign", "total_functional"]:
            if field_name in self.fields:
                self.fields[field_name].required = False

    def clean_salesman(self):
        salesman = self.cleaned_data.get('salesman')
        user = getattr(self, 'user', None)
        can_change = (
            user and (
                user.is_superuser or
                getattr(user, 'is_admin', False) or
                user.has_perm('sale.change_sale_salesman') or
                user.has_perm('users.تغيير_مسؤول_المبيعات')
            )
        )
        if not can_change:
            if self.instance and self.instance.pk and self.instance.salesman:
                return self.instance.salesman
            return user
        return salesman or user


class CustomFieldDefinitionForm(forms.ModelForm):
    """
    نموذج إنشاء وتعديل تعاريف الحقول الإضافية
    """
    class Meta:
        model = CustomFieldDefinition
        fields = [
            "name",
            "name_en",
            "key",
            "module",
            "field_type",
            "select_options",
            "is_required",
            "show_in_header",
            "show_on_print",
            "show_on_thermal",
            "is_active",
            "sort_order",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "مثال: رقم أمر الشراء"}),
            "name_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. PO Number"}),
            "key": forms.TextInput(attrs={"class": "form-control", "placeholder": "مثال: po_number (يترك فارغاً للتوليد التلقائي)"}),
            "module": forms.Select(attrs={"class": "form-select"}),
            "field_type": forms.Select(attrs={"class": "form-select", "id": "id_field_type"}),
            "select_options": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "خيار 1, خيار 2, خيار 3 (مفصولة بفاصلة)"}),
            "is_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_in_header": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_on_print": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_on_thermal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['key'].required = False
