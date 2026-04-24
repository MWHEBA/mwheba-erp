from django import forms
from django.utils.translation import gettext_lazy as _
from .models import (
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Unit,
    Warehouse,
    StockMovement,
    BundleComponent,
)
from .models.batch_voucher import BatchVoucher, BatchVoucherItem
from .models.inventory_movement import InventoryMovement


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "code", "parent", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "مثل: SUP للمواد والمستلزمات",
                "maxlength": "10",
                "style": "text-transform: uppercase;"
            }),
            "parent": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['code'].help_text = "رمز مختصر للتصنيف (حروف إنجليزية فقط، حد أقصى 10 أحرف)"
        
    def clean_code(self):
        """التحقق من صحة كود التصنيف"""
        code = self.cleaned_data.get('code')
        if code:
            # تحويل إلى أحرف كبيرة
            code = code.upper().strip()
            
            # التحقق من أن الكود يحتوي على أحرف إنجليزية فقط
            if not code.isalpha():
                raise forms.ValidationError("الكود يجب أن يحتوي على أحرف إنجليزية فقط")
            
            # التحقق من طول الكود
            if len(code) > 10:
                raise forms.ValidationError("الكود يجب ألا يزيد عن 10 أحرف")
                
        return code





class UnitForm(forms.ModelForm):
    class Meta:
        model = Unit
        fields = ["name", "symbol", "is_active"]


class ProductForm(forms.ModelForm):
    # تعريف الحقول غير الإجبارية
    min_stock = forms.IntegerField(
        required=False, min_value=0, label=_("الحد الأدنى للمخزون")
    )

    class Meta:
        model = Product
        fields = [
            "name",
            "category",
            "description",
            "sku",
            "barcode",
            "unit",
            "cost_price",
            "selling_price",
            "min_stock",
            "is_service",
            "is_active",
            "is_featured",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "cost_price": forms.NumberInput(attrs={"step": "0.01"}),
            "selling_price": forms.NumberInput(attrs={"step": "0.01"}),
            "sku": forms.TextInput(attrs={
                "placeholder": "سيتم توليده تلقائياً إذا ترك فارغاً",
                "readonly": False
            }),
        }
        
    def __init__(self, *args, **kwargs):
        # استخراج is_service من kwargs إذا كان موجود
        is_service = kwargs.pop('is_service', None)
        
        super().__init__(*args, **kwargs)
        
        # تحديد إذا كان العنصر خدمة
        if is_service is not None:
            self.fields['is_service'].initial = is_service
        
        # تحديد نوع العنصر (خدمة أو منتج)
        is_service_value = self.instance.is_service if self.instance.pk else (is_service or False)
        item_type = "الخدمة" if is_service_value else "المنتج"
        
        # تحديث labels ديناميكياً
        self.fields['name'].label = f"اسم {item_type}"
        self.fields['sku'].label = f"كود {item_type}"
        self.fields['description'].label = f"وصف {item_type}"
        self.fields['barcode'].label = "الباركود"
        self.fields['cost_price'].label = "سعر التكلفة"
        self.fields['selling_price'].label = "سعر البيع"
        
        # تحديث help texts
        self.fields['sku'].help_text = f"سيتم توليد كود {item_type} تلقائياً بناءً على التصنيف إذا ترك فارغاً"
        self.fields['name'].help_text = f"أدخل اسم {item_type} بوضوح"
        
        # جعل حقل SKU اختياري
        self.fields['sku'].required = False
        
        # جعل وحدة القياس وسعر التكلفة اختيارية للخدمات
        if is_service_value:
            self.fields['unit'].required = False
            self.fields['unit'].help_text = "وحدة القياس اختيارية للخدمات"
            
            self.fields['cost_price'].required = False
            self.fields['cost_price'].help_text = "سعر التكلفة اختياري للخدمات"
        
        # تحديث label حقل is_service
        self.fields['is_service'].label = "خدمة (وليس منتج)"
        self.fields['is_service'].help_text = "الخدمات لا تحتاج مخزون (مثل: كورسات، مواصلات، رسوم)"
    
    def clean_unit(self):
        """التحقق من وحدة القياس وإنشاء واحدة افتراضية للخدمات إذا لزم الأمر"""
        unit = self.cleaned_data.get('unit')
        is_service = self.cleaned_data.get('is_service') or self.data.get('is_service')
        
        # تحويل is_service من string إلى boolean إذا لزم الأمر
        if isinstance(is_service, str):
            is_service = is_service.lower() in ('true', '1', 'on')
        
        # إذا كانت خدمة ولم يتم اختيار وحدة، نستخدم وحدة افتراضية
        if is_service and not unit:
            from product.models import Unit
            default_unit, created = Unit.objects.get_or_create(
                name="خدمة",
                defaults={
                    "symbol": "خدمة",
                    "is_active": True
                }
            )
            return default_unit
        
        return unit
    
    def clean_cost_price(self):
        """التحقق من سعر التكلفة وتعيين قيمة افتراضية للخدمات"""
        cost_price = self.cleaned_data.get('cost_price')
        is_service = self.cleaned_data.get('is_service') or self.data.get('is_service')
        
        # تحويل is_service من string إلى boolean إذا لزم الأمر
        if isinstance(is_service, str):
            is_service = is_service.lower() in ('true', '1', 'on')
        
        # إذا كانت خدمة ولم يتم إدخال سعر تكلفة، نضع 0
        if is_service and not cost_price:
            return 0
        
        return cost_price

    def clean_min_stock(self):
        min_stock = self.cleaned_data.get("min_stock")
        is_service = self.cleaned_data.get("is_service")
        
        # إذا كانت خدمة، المخزون دائماً 0
        if is_service:
            return 0
            
        return min_stock if min_stock is not None else 0

    def clean(self):
        """التحقق من صحة البيانات المترابطة"""
        cleaned_data = super().clean()
        cost_price = cleaned_data.get("cost_price")
        selling_price = cleaned_data.get("selling_price")
        
        # التحقق من أن سعر البيع أكبر من سعر التكلفة
        if cost_price and selling_price and selling_price <= cost_price:
            self.add_error("selling_price", _("سعر البيع يجب أن يكون أكبر من سعر التكلفة"))
        
        return cleaned_data


class ProductImageForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = ["image", "is_primary", "alt_text"]
        widgets = {
            "alt_text": forms.TextInput(attrs={"placeholder": _("وصف الصورة")}),
        }


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model = ProductVariant
        fields = [
            "product",
            "name",
            "sku",
            "barcode",
            "cost_price",
            "selling_price",
            "stock",
            "is_active",
        ]
        widgets = {
            "cost_price": forms.NumberInput(attrs={"step": "0.01"}),
            "selling_price": forms.NumberInput(attrs={"step": "0.01"}),
        }


class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ["name", "code", "location", "manager", "description", "is_active"]
        widgets = {
            "code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "اتركه فارغاً للتوليد التلقائي (WH0001, WH0002, ...)"
                }
            ),
            "description": forms.Textarea(attrs={"rows": 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make code field optional
        self.fields['code'].required = False


class StockMovementForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = [
            "product",
            "warehouse",
            "movement_type",
            "quantity",
            "reference_number",
            "document_type",
            "notes",
            "destination_warehouse",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # تعيين القيمة الافتراضية لنوع المستند إلى 'other' للحركات اليدوية
        self.initial["document_type"] = "other"

    def clean(self):
        cleaned_data = super().clean()
        movement_type = cleaned_data.get("movement_type")
        destination_warehouse = cleaned_data.get("destination_warehouse")

        if movement_type == "transfer" and not destination_warehouse:
            self.add_error(
                "destination_warehouse", _("يجب تحديد المخزن المستلم في حالة التحويل")
            )

        if movement_type == "transfer" and destination_warehouse:
            if cleaned_data.get("warehouse") == destination_warehouse:
                self.add_error(
                    "destination_warehouse", _("لا يمكن التحويل إلى نفس المخزن")
                )

        return cleaned_data


class ProductSearchForm(forms.Form):
    name = forms.CharField(
        required=False, 
        label=_("اسم المنتج"),
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'البحث في أسماء المنتجات...'
        })
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.filter(is_active=True).order_by('name'), 
        required=False, 
        label=_("التصنيف"),
        empty_label="جميع التصنيفات",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    product_type = forms.ChoiceField(
        required=False,
        label=_("نوع المنتج"),
        choices=[
            ('', 'جميع الأنواع'),
            ('regular', 'منتج عادي'),
            ('bundle', 'منتج مجمع'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    min_price = forms.DecimalField(
        required=False, 
        label=_("السعر الأدنى"),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': '0.00'
        })
    )
    max_price = forms.DecimalField(
        required=False, 
        label=_("السعر الأقصى"),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': '0.00'
        })
    )
    is_active = forms.BooleanField(
        required=False, 
        label=_("نشط فقط"),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    in_stock = forms.BooleanField(
        required=False, 
        label=_("متوفر فقط"),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class BundleForm(forms.ModelForm):
    """
    نموذج إنشاء وتعديل المنتجات المجمعة
    Requirements: 1.1, 1.2, 1.3
    """
    
    class Meta:
        model = Product
        fields = [
            'name', 'category', 'description', 'sku', 'barcode', 'unit',
            'cost_price', 'selling_price', 'min_stock', 'is_active', 'is_featured'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'cost_price': forms.NumberInput(attrs={'step': '0.01'}),
            'selling_price': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تعيين is_bundle = True تلقائياً للمنتجات الجديدة
        if not self.instance.pk:
            self.instance.is_bundle = True
        
        # تخصيص الحقول
        self.fields['name'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'أدخل اسم المنتج المجمع'
        })
        
        self.fields['sku'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'كود المنتج المجمع'
        })
        
        self.fields['description'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'وصف المنتج المجمع ومكوناته'
        })
        
        # تصفية التصنيفات النشطة فقط
        self.fields['category'].queryset = Category.objects.filter(is_active=True)
        self.fields['unit'].queryset = Unit.objects.filter(is_active=True)
    
    def save(self, commit=True):
        """
        حفظ المنتج المجمع مع تعيين is_bundle = True
        """
        instance = super().save(commit=False)
        instance.is_bundle = True
        
        if commit:
            instance.save()
        
        return instance


class BundleComponentForm(forms.ModelForm):
    """
    نموذج إضافة مكون للمنتج المجمع
    Requirements: 1.2, 1.4
    """
    
    class Meta:
        model = BundleComponent
        fields = ['component_product', 'required_quantity']
        widgets = {
            'required_quantity': forms.NumberInput(attrs={
                'min': '1',
                'class': 'form-control',
                'placeholder': 'الكمية المطلوبة'
            })
        }
    
    def __init__(self, *args, **kwargs):
        bundle_product = kwargs.pop('bundle_product', None)
        super().__init__(*args, **kwargs)
        
        # تصفية المنتجات المتاحة (استبعاد المنتجات المجمعة والمنتج نفسه)
        available_products = Product.objects.filter(
            is_active=True,
            is_bundle=False
        )
        
        if bundle_product:
            available_products = available_products.exclude(pk=bundle_product.pk)
            # استبعاد المكونات المضافة مسبقاً
            existing_components = BundleComponent.objects.filter(
                bundle_product=bundle_product
            ).values_list('component_product_id', flat=True)
            available_products = available_products.exclude(pk__in=existing_components)
        
        self.fields['component_product'].queryset = available_products
        self.fields['component_product'].widget.attrs.update({
            'class': 'form-control component-select',
            'data-placeholder': 'اختر المنتج المكون'
        })
        
        self.fields['required_quantity'].widget.attrs.update({
            'class': 'form-control quantity-input'
        })
        
        # جعل الحقول غير مطلوبة للنماذج الفارغة
        self.fields['component_product'].required = False
        self.fields['required_quantity'].required = False
    
    def clean(self):
        """
        التحقق من صحة البيانات
        """
        cleaned_data = super().clean()
        component_product = cleaned_data.get('component_product')
        required_quantity = cleaned_data.get('required_quantity')
        
        # إذا كان أحد الحقول فارغ والآخر مملوء، أظهر خطأ
        if component_product and not required_quantity:
            raise forms.ValidationError(_("يجب تحديد الكمية المطلوبة"))
        
        if required_quantity and not component_product:
            raise forms.ValidationError(_("يجب اختيار المنتج المكون"))
        
        # إذا كان كلا الحقلين فارغين، هذا مقبول (نموذج فارغ)
        if not component_product and not required_quantity:
            return cleaned_data
        
        # التحقق من أن المنتج المكون ليس منتج مجمع
        if component_product and component_product.is_bundle:
            raise forms.ValidationError(_("لا يمكن إضافة منتج مجمع كمكون لمنتج مجمع آخر"))
        
        # التحقق من أن الكمية أكبر من صفر
        if required_quantity and required_quantity < 1:
            raise forms.ValidationError(_("الكمية المطلوبة يجب أن تكون أكبر من صفر"))
        
        return cleaned_data


# نموذج مبسط لإضافة مكونات متعددة في نفس الوقت
BundleComponentFormSet = forms.inlineformset_factory(
    Product,
    BundleComponent,
    form=BundleComponentForm,
    fk_name='bundle_product',  # تحديد المفتاح الخارجي المطلوب
    extra=1,
    min_num=0,  # تغيير من 1 إلى 0 لتجنب مشاكل التحقق
    validate_min=False,  # تعطيل التحقق التلقائي
    can_delete=True,
    fields=['component_product', 'required_quantity']
)



class ReceiptVoucherForm(forms.ModelForm):
    """نموذج إذن استلام"""
    
    class Meta:
        model = InventoryMovement
        fields = ['product', 'warehouse', 'quantity', 'unit_cost', 'purpose_type', 
                  'received_by_name', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'warehouse': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'required': True}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01', 'required': True}),
            'purpose_type': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'received_by_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم المستلم'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 1, 'placeholder': 'ملاحظات إضافية'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from product.models.inventory_movement import InventoryMovement
        
        # تحديد الأغراض المتاحة لأذون الاستلام فقط
        self.fields['purpose_type'].choices = [('', '--- اختر الغرض ---')] + list(InventoryMovement.RECEIPT_PURPOSE_TYPES)
        
        # تحسين labels
        self.fields['product'].label = 'المنتج'
        self.fields['warehouse'].label = 'المخزن'
        self.fields['quantity'].label = 'الكمية'
        self.fields['unit_cost'].label = 'تكلفة الوحدة'
        self.fields['purpose_type'].label = 'غرض الاستلام'
        self.fields['received_by_name'].label = 'المستلم'
        self.fields['notes'].label = 'ملاحظات'


class IssueVoucherForm(forms.ModelForm):
    """نموذج إذن صرف"""
    
    class Meta:
        model = InventoryMovement
        fields = ['product', 'warehouse', 'quantity', 'purpose_type', 
                  'issued_by_name', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select', 'required': True, 'id': 'id_product'}),
            'warehouse': forms.Select(attrs={'class': 'form-select', 'required': True, 'id': 'id_warehouse'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'required': True}),
            'purpose_type': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'issued_by_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم الموظف'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 1, 'placeholder': 'ملاحظات إضافية'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from product.models.inventory_movement import InventoryMovement
        from product.models.stock_management import Stock
        
        # تحديد الأغراض المتاحة لأذون الصرف فقط
        self.fields['purpose_type'].choices = [('', '--- اختر الغرض ---')] + list(InventoryMovement.ISSUE_PURPOSE_TYPES)
        
        # عرض المنتجات التي لها stock متاح فقط
        products_with_stock = Stock.objects.filter(
            quantity__gt=0
        ).values_list('product_id', flat=True).distinct()
        
        self.fields['product'].queryset = Product.objects.filter(
            id__in=products_with_stock,
            is_active=True
        ).order_by('name')
        
        # إضافة خيار فارغ للمنتجات
        self.fields['product'].empty_label = 'اختر المنتج'
        
        # المخازن ستُحدّث ديناميكياً عبر JavaScript حسب المنتج المختار
        self.fields['warehouse'].choices = [('', 'اختر المنتج أولاً')]
        self.fields['warehouse'].widget.attrs['disabled'] = True
        
        # تحسين labels
        self.fields['product'].label = 'المنتج'
        self.fields['warehouse'].label = 'المخزن'
        self.fields['warehouse'].help_text = 'سيتم عرض المخازن المتاحة بعد اختيار المنتج'
        self.fields['quantity'].label = 'الكمية'
        self.fields['purpose_type'].label = 'غرض الصرف'
        self.fields['issued_by_name'].label = 'اسم الموظف'
        self.fields['notes'].label = 'ملاحظات'


class TransferVoucherForm(forms.Form):
    """نموذج إذن تحويل مخزني"""

    product = forms.ModelChoiceField(
        queryset=None,
        label='المنتج',
        widget=forms.Select(attrs={'class': 'form-select', 'required': True}),
    )
    from_warehouse = forms.ModelChoiceField(
        queryset=None,
        label='من مخزن',
        widget=forms.Select(attrs={'class': 'form-select', 'required': True}),
    )
    to_warehouse = forms.ModelChoiceField(
        queryset=None,
        label='إلى مخزن',
        widget=forms.Select(attrs={'class': 'form-select', 'required': True}),
    )
    quantity = forms.IntegerField(
        label='الكمية',
        min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'required': True}),
    )
    reference_document = forms.CharField(
        label='المستند المرجعي',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'رقم أو اسم المستند'}),
    )
    transferred_by_name = forms.CharField(
        label='اسم المحوِّل',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم الموظف المسؤول'}),
    )
    notes = forms.CharField(
        label='ملاحظات',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 1, 'placeholder': 'ملاحظات إضافية'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from product.models import Product, Warehouse
        from product.models.stock_management import Stock

        products_with_stock = Stock.objects.filter(
            quantity__gt=0
        ).values_list('product_id', flat=True).distinct()

        self.fields['product'].queryset = Product.objects.filter(
            id__in=products_with_stock,
            is_active=True
        ).order_by('name')
        self.fields['product'].empty_label = 'اختر المنتج'

        warehouses = Warehouse.objects.filter(is_active=True).order_by('name')
        self.fields['from_warehouse'].queryset = warehouses
        self.fields['from_warehouse'].empty_label = 'اختر المخزن المصدر'
        self.fields['to_warehouse'].queryset = warehouses
        self.fields['to_warehouse'].empty_label = 'اختر المخزن الهدف'

    def clean(self):
        cleaned_data = super().clean()
        from_warehouse = cleaned_data.get('from_warehouse')
        to_warehouse = cleaned_data.get('to_warehouse')
        if from_warehouse and to_warehouse and from_warehouse == to_warehouse:
            raise forms.ValidationError('لا يمكن التحويل من وإلى نفس المخزن')
        return cleaned_data


class BatchVoucherForm(forms.ModelForm):
    """نموذج الإذن الجماعي"""

    class Meta:
        model = BatchVoucher
        fields = ['voucher_type', 'warehouse', 'target_warehouse',
                  'purpose_type', 'party_name', 'notes']
        widgets = {
            'voucher_type': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'warehouse': forms.Select(attrs={'class': 'form-select', 'required': True}),
            'target_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'purpose_type': forms.Select(attrs={'class': 'form-select'}),
            'party_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم الشخص'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from product.models import Warehouse
        warehouses = Warehouse.objects.filter(is_active=True).order_by('name')
        self.fields['warehouse'].queryset = warehouses
        self.fields['warehouse'].empty_label = 'اختر المخزن'
        self.fields['target_warehouse'].queryset = warehouses
        self.fields['target_warehouse'].empty_label = 'اختر المخزن الهدف'
        self.fields['target_warehouse'].required = False

        self.fields['voucher_type'].label = 'نوع الإذن'
        self.fields['warehouse'].label = 'المخزن'
        self.fields['target_warehouse'].label = 'المخزن الهدف'
        self.fields['purpose_type'].label = 'الغرض'
        self.fields['party_name'].label = 'اسم الشخص'
        self.fields['notes'].label = 'ملاحظات'

    def clean(self):
        cleaned_data = super().clean()
        voucher_type = cleaned_data.get('voucher_type')
        target_warehouse = cleaned_data.get('target_warehouse')
        warehouse = cleaned_data.get('warehouse')
        if voucher_type == 'transfer' and not target_warehouse:
            self.add_error('target_warehouse', 'المخزن الهدف مطلوب لأذون التحويل')
        if voucher_type == 'transfer' and warehouse and target_warehouse and warehouse == target_warehouse:
            self.add_error('target_warehouse', 'لا يمكن التحويل من وإلى نفس المخزن')
        return cleaned_data


class BatchVoucherItemForm(forms.ModelForm):
    """نموذج بند الإذن الجماعي"""

    class Meta:
        model = BatchVoucherItem
        fields = ['product', 'quantity', 'unit_cost', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ملاحظة'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].empty_label = 'اختر المنتج'
        self.fields['product'].label = 'المنتج'
        self.fields['quantity'].label = 'الكمية'
        self.fields['unit_cost'].label = 'تكلفة الوحدة'
        self.fields['notes'].label = 'ملاحظات'
        self.fields['notes'].required = False


BatchVoucherItemFormSet = forms.inlineformset_factory(
    BatchVoucher,
    BatchVoucherItem,
    form=BatchVoucherItemForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
