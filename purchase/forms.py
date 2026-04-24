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
        queryset=Warehouse.objects.filter(is_active=True), 
        label="المخزن",
        required=False  # اختياري للفواتير الخدمية
    )

    # حقل التصنيف المالي (إجباري) - استخدام ChoiceField لعرض التصنيفات بشكل منظم
    financial_category = forms.ChoiceField(
        label="التصنيف المالي",
        help_text="اختر التصنيف المالي للمصروف",
        required=True,
        widget=forms.Select(
            attrs={"class": "form-control", "id": "id_financial_category"}
        ),
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

    class Meta:
        model = Purchase
        fields = [
            "supplier",
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
            from utils.helpers import get_system_today_string
            self.initial["date"] = get_system_today_string()

        # تعيين أول مخزن بشكل افتراضي (فقط للفواتير غير الخدمية)
        # سيتم التحكم في إظهار/إخفاء الحقل من JavaScript حسب نوع المورد
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
        
        # تعيين "نقدي" كافتراضي
        if not self.initial.get("payment_method"):
            self.initial["payment_method"] = "cash"
        
        # Handle old values when editing
        if self.instance and self.instance.pk and self.instance.payment_method:
            # إذا كانت القيمة القديمة cash أو credit، نبقيها كما هي
            # إذا كانت account code، نبقيها أيضاً
            self.initial['payment_method'] = self.instance.payment_method

        # تحديد التصنيفات المالية المتاحة - عرض الرئيسية والفرعية معاً
        try:
            from financial.models import FinancialCategory, FinancialSubcategory

            category_choices = [('', 'اختر التصنيف المالي')]
            
            # جلب التصنيفات الرئيسية (فقط اللي عندها حساب مصروفات)
            financial_categories = FinancialCategory.objects.filter(
                is_active=True,
                default_expense_account__isnull=False
            ).prefetch_related('subcategories').order_by('display_order', 'name')
            
            for cat in financial_categories:
                # إضافة التصنيف الرئيسي
                category_choices.append((f"cat_{cat.pk}", f"📁 {cat.name}"))
                
                # إضافة التصنيفات الفرعية تحته (كلها لأنها بتستخدم حساب الأب)
                subcategories = cat.subcategories.filter(is_active=True).order_by('display_order', 'name')
                for subcat in subcategories:
                    category_choices.append((f"sub_{subcat.pk}", f"   ↳ {subcat.name}"))
            
            self.fields['financial_category'].choices = category_choices
            
            # تحديد القيمة الحالية إذا كان هناك instance
            if self.instance and self.instance.pk and self.instance.financial_category:
                # تحديد نوع التصنيف (رئيسي أو فرعي)
                if isinstance(self.instance.financial_category, FinancialCategory):
                    self.initial['financial_category'] = f"cat_{self.instance.financial_category.pk}"
                elif isinstance(self.instance.financial_category, FinancialSubcategory):
                    self.initial['financial_category'] = f"sub_{self.instance.financial_category.pk}"
            
        except ImportError:
            self.fields["financial_category"].choices = [('', 'اختر التصنيف المالي')]
            self.fields["financial_category"].required = False

    def clean_financial_category(self):
        """معالجة التصنيف المالي - تحويل من ID إلى كائن"""
        financial_category_value = self.cleaned_data.get('financial_category')
        
        # التحقق من أن الحقل مطلوب فقط إذا كان required=True
        if not financial_category_value:
            if self.fields['financial_category'].required:
                raise ValidationError('التصنيف المالي مطلوب')
            return None
        
        try:
            from financial.models import FinancialCategory, FinancialSubcategory
            
            # التحقق من نوع القيمة
            if isinstance(financial_category_value, str):
                # القيمة جاية من الـ form بصيغة "cat_123" أو "sub_456"
                if financial_category_value.startswith('cat_'):
                    cat_id = int(financial_category_value.replace('cat_', ''))
                    try:
                        return FinancialCategory.objects.get(pk=cat_id, is_active=True)
                    except FinancialCategory.DoesNotExist:
                        raise ValidationError('التصنيف المالي المحدد غير موجود أو غير نشط')
                        
                elif financial_category_value.startswith('sub_'):
                    subcat_id = int(financial_category_value.replace('sub_', ''))
                    try:
                        subcat = FinancialSubcategory.objects.select_related('parent_category').get(
                            pk=subcat_id, is_active=True
                        )
                        # نرجع الـ parent category لأن Purchase بيقبل بس FinancialCategory
                        return subcat.parent_category
                    except FinancialSubcategory.DoesNotExist:
                        raise ValidationError('التصنيف الفرعي المحدد غير موجود أو غير نشط')
                else:
                    raise ValidationError('صيغة التصنيف المالي غير صحيحة')
            
            # إذا كان الكائن نفسه، نرجعه مباشرة
            return financial_category_value
            
        except (ImportError, ValueError) as e:
            raise ValidationError(f'خطأ في معالجة التصنيف المالي: {str(e)}')

    def clean(self):
        cleaned_data = super().clean()
        supplier = cleaned_data.get('supplier')
        warehouse = cleaned_data.get('warehouse')
        payment_method = cleaned_data.get('payment_method')
        
        # التحقق من المخزن للفواتير غير الخدمية
        if supplier:
            is_service = supplier.is_service_provider()
            
            if is_service:
                # فواتير خدمية لا تحتاج مخزن - نتأكد إنه فاضي
                cleaned_data['warehouse'] = None
            elif not warehouse:
                # فواتير منتجات تحتاج مخزن - بس نتحقق إن في منتجات فعلاً
                # لو المخزن مش موجود والمورد مش خدمي، نفترض إنه خدمي
                # (الـ JavaScript بيخفي المخزن للموردين الخدميين)
                pass
        
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

    def clean_number(self):
        number = self.cleaned_data.get("number")
        if not self.instance.pk and Purchase.objects.filter(number=number).exists():
            raise ValidationError("رقم الفاتورة موجود بالفعل")
        return number

    def clean_date(self):
        """التحقق من أن تاريخ الفاتورة ليس في المستقبل"""
        date = self.cleaned_data.get("date")
        if date:
            from utils.helpers import get_system_today
            today_system = get_system_today()
            if date > today_system:
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
            "date": forms.TextInput(attrs={
                "class": "form-control",
                "data-date-picker": True,
                "placeholder": "اختر تاريخ الفاتورة..."
            }),
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
        model = PurchasePayment
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
        self.purchase = kwargs.pop("purchase", None)
        super().__init__(*args, **kwargs)

        # إعداد خيارات طريقة الدفع
        payment_choices = [('', 'اختر حساب الدفع')]
        
        try:
            from financial.models import ChartOfAccounts
            payment_accounts = ChartOfAccounts.objects.filter(
                account_type__code__in=['cash', 'bank'],
                is_active=True
            ).order_by('code')
            
            for account in payment_accounts:
                payment_choices.append((account.code, f"{account.name} ({account.code})"))
            
            # تعيين الحساب النقدي الافتراضي
            default_cash = ChartOfAccounts.objects.filter(code='10100', is_active=True).first()
            if default_cash and not self.initial.get("payment_method"):
                self.initial["payment_method"] = default_cash.code
                
        except ImportError:
            payment_choices = [
                ('', 'اختر طريقة الدفع'),
                ('cash', 'نقداً'),
                ('bank_transfer', 'تحويل بنكي'),
            ]
            if not self.initial.get("payment_method"):
                self.initial["payment_method"] = "cash"
        
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
                self.initial['payment_method'] = old_value

        # تعيين التاريخ الحالي كافتراضي
        if not self.initial.get("payment_date"):
            from utils.helpers import get_system_today
            self.initial["payment_date"] = get_system_today()

        # إضافة CSS classes للحقول
        for field_name, field in self.fields.items():
            if "class" not in field.widget.attrs:
                field.widget.attrs["class"] = "form-control"

    def clean_payment_date(self):
        """التحقق من أن تاريخ الدفعة ليس في المستقبل"""
        payment_date = self.cleaned_data.get("payment_date")
        if payment_date:
            from utils.helpers import get_system_today
            today_system = get_system_today()
            if payment_date > today_system:
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


class PurchasePaymentEditForm(forms.ModelForm):
    """
    نموذج تعديل دفعة على فاتورة المشتريات
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
        model = PurchasePayment
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
        self.purchase = kwargs.pop("purchase", None)
        super().__init__(*args, **kwargs)

        # إعداد خيارات طريقة الدفع
        payment_choices = [('', 'اختر حساب الدفع')]
        
        try:
            from financial.models import ChartOfAccounts
            payment_accounts = ChartOfAccounts.objects.filter(
                account_type__code__in=['cash', 'bank'],
                is_active=True
            ).order_by('code')
            
            for account in payment_accounts:
                payment_choices.append((account.code, f"{account.name} ({account.code})"))
                
        except ImportError:
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
                self.initial['payment_method'] = old_value

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
        if payment_date:
            from utils.helpers import get_system_today
            today_system = get_system_today()
            if payment_date > today_system:
                raise ValidationError("تاريخ الدفعة لا يمكن أن يكون في المستقبل")
        return payment_date

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= 0:
            raise ValidationError("المبلغ يجب أن يكون أكبر من صفر")

        # لا نتحقق من المبلغ المتبقي في حالة التعديل
        # لأن المستخدم قد يريد تعديل مبلغ موجود

        return amount


class PurchaseReturnForm(forms.ModelForm):
    """
    نموذج مرتجع المشتريات
    """

    class Meta:
        model = PurchaseReturn
        fields = ["date", "warehouse", "notes"]
        widgets = {
            "date": forms.TextInput(attrs={
                "class": "form-control",
                "data-date-picker": True,
                "placeholder": "اختر تاريخ المرتجع..."
            }),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs["class"] = "form-control"

        # تعيين التاريخ الحالي كقيمة افتراضية بالتنسيق الصحيح
        if not self.initial.get("date"):
            from utils.helpers import get_system_today_string
            self.initial["date"] = get_system_today_string()

        # جعل حقل المخزن اختياري
        self.fields["warehouse"].required = False
        self.fields["notes"].required = False

    def clean_date(self):
        """التحقق من أن تاريخ المرتجع ليس في المستقبل"""
        date = self.cleaned_data.get("date")
        if date:
            from utils.helpers import get_system_today
            today_system = get_system_today()
            if date > today_system:
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
