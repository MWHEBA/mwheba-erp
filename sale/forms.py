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

    # حقل طريقة الدفع - ديناميكي يدعم account codes
    payment_method = forms.ChoiceField(
        label="طريقة الدفع",
        help_text="اختر طريقة الدفع (نقدي/آجل) أو حساب محدد",
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

    class Meta:
        model = Sale
        fields = [
            "customer",
            "warehouse",
            "date",
            "number",
            "discount",
            "payment_method",
            "financial_category",
            "notes",
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
        super().__init__(*args, **kwargs)

        # تعيين تاريخ اليوم كافتراضي بالتنسيق الصحيح
        if not self.initial.get("date"):
            self.initial["date"] = timezone.now().date().strftime("%Y-%m-%d")

        # تعيين أول مخزن بشكل افتراضي
        warehouses = Warehouse.objects.filter(is_active=True)
        if warehouses.exists() and not self.initial.get("warehouse"):
            self.initial["warehouse"] = warehouses.first().pk

        # إعداد خيارات طريقة الدفع
        payment_choices = [
            ('', 'اختر طريقة الدفع'),
            ('cash', 'نقدي'),
            ('credit', 'آجل'),
        ]
        
        # إضافة حسابات الدفع من النظام المالي (للفواتير النقدية فقط)
        try:
            from financial.models import ChartOfAccounts
            payment_accounts = ChartOfAccounts.objects.filter(
                account_type__code__in=['cash', 'bank'],
                is_active=True
            ).order_by('code')
            
            for account in payment_accounts:
                payment_choices.append((account.code, f"{account.name} ({account.code})"))
        except ImportError:
            pass
        
        self.fields['payment_method'].choices = payment_choices
        
        # تعيين "آجل" كافتراضي
        if not self.initial.get("payment_method"):
            self.initial["payment_method"] = "credit"
        
        # Handle old values when editing
        if self.instance and self.instance.pk and self.instance.payment_method:
            self.initial['payment_method'] = self.instance.payment_method

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
        except ImportError:
            self.fields['financial_category'].choices = [('', 'اختر التصنيف المالي')]

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get('payment_method')
        
        # التحقق من payment_method: مطلوب فقط للفواتير النقدية
        # الـ view بيبعت invoice_type في الـ POST data
        # لكن في الـ form validation مش موجود، فهنعتمد على القيمة نفسها
        if payment_method and payment_method not in ['', 'credit']:
            # فاتورة نقدية - payment_method لازم يكون موجود
            pass
        elif not payment_method or payment_method == '':
            # لو فاضي، نفترض إنه آجل ونحط 'credit'
            cleaned_data['payment_method'] = 'credit'
        
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
        if not self.instance.pk and Sale.objects.filter(number=number).exists():
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

        # تحميل حسابات الدفع ديناميكياً (حسب unified-components-guide.md)
        try:
            from financial.models import ChartOfAccounts
            from django.db.models import Q
            
            payment_accounts = ChartOfAccounts.objects.filter(
                Q(is_cash_account=True) | Q(is_bank_account=True),
                is_active=True
            ).order_by('code')
            
            if payment_accounts.exists():
                choices = [('', 'اختر حساب الدفع')]
                for account in payment_accounts:
                    choices.append((account.code, f"{account.name} ({account.code})"))
                
                self.fields['payment_method'].choices = choices
                
                # Handle old values when editing
                if self.instance and self.instance.pk and self.instance.payment_method:
                    old_value = self.instance.payment_method
                    if old_value == 'cash':
                        default_cash = ChartOfAccounts.objects.filter(code='10100').first()
                        if default_cash:
                            self.initial['payment_method'] = default_cash.code
                    elif old_value == 'bank_transfer':
                        default_bank = ChartOfAccounts.objects.filter(code='10200').first()
                        if default_bank:
                            self.initial['payment_method'] = default_bank.code
                    else:
                        # Already an account code - verify it exists
                        if payment_accounts.filter(code=old_value).exists():
                            self.initial['payment_method'] = old_value
            else:
                # No payment accounts found - use fallback
                self.fields['payment_method'].choices = [
                    ('', 'اختر طريقة الدفع'),
                    ('cash', 'نقداً'),
                    ('bank_transfer', 'تحويل بنكي'),
                ]
        except Exception:
            # Fallback to default choices on any error
            self.fields['payment_method'].choices = [
                ('', 'اختر طريقة الدفع'),
                ('cash', 'نقداً'),
                ('bank_transfer', 'تحويل بنكي'),
            ]
        
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
            from financial.models import ChartOfAccounts
            from django.db.models import Q
            
            payment_accounts = ChartOfAccounts.objects.filter(
                Q(is_cash_account=True) | Q(is_bank_account=True),
                is_active=True
            ).order_by('code')
            
            if payment_accounts.exists():
                for account in payment_accounts:
                    payment_choices.append((account.code, f"{account.name} ({account.code})"))
            else:
                # No payment accounts found - use fallback
                payment_choices = [
                    ('', 'اختر طريقة الدفع'),
                    ('cash', 'نقداً'),
                    ('bank_transfer', 'تحويل بنكي'),
                ]
                
        except Exception:
            payment_choices = [
                ('', 'اختر طريقة الدفع'),
                ('cash', 'نقداً'),
                ('bank_transfer', 'تحويل بنكي'),
            ]
        
        self.fields['payment_method'].choices = payment_choices
        
        # Handle old values when editing
        if self.instance and self.instance.pk and self.instance.payment_method:
            old_value = self.instance.payment_method
            # تحويل القيم القديمة
            if old_value == 'cash':
                try:
                    from financial.models import ChartOfAccounts
                    default_cash = ChartOfAccounts.objects.filter(code='10100').first()
                    if default_cash:
                        self.initial['payment_method'] = default_cash.code
                except:
                    self.initial['payment_method'] = 'cash'
            elif old_value == 'bank_transfer':
                try:
                    from financial.models import ChartOfAccounts
                    default_bank = ChartOfAccounts.objects.filter(code='10200').first()
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

        # لا نتحقق من المبلغ المتبقي في حالة التعديل
        # لأن المستخدم قد يريد تعديل مبلغ موجود

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
