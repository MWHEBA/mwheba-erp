from django import forms
from django.utils.translation import gettext_lazy as _
from .models import (
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Brand,
    Unit,
    Warehouse,
    StockMovement,
)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "parent", "description", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ["name", "description", "logo", "website", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }


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
            "brand",
            "description",
            "sku",
            "barcode",
            "unit",
            "cost_price",
            "selling_price",
            "min_stock",
            "is_active",
            "is_featured",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "cost_price": forms.NumberInput(attrs={"step": "0.01"}),
            "selling_price": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def clean_min_stock(self):
        min_stock = self.cleaned_data.get("min_stock")
        return min_stock if min_stock is not None else 0


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
            "description": forms.Textarea(attrs={"rows": 3}),
        }


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
    name = forms.CharField(required=False, label=_("اسم المنتج"))
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(), required=False, label=_("التصنيف")
    )
    brand = forms.ModelChoiceField(
        queryset=Brand.objects.all(), required=False, label=_("النوع")
    )
    min_price = forms.DecimalField(required=False, label=_("السعر الأدنى"))
    max_price = forms.DecimalField(required=False, label=_("السعر الأقصى"))
    is_active = forms.BooleanField(required=False, label=_("نشط"))
    in_stock = forms.BooleanField(required=False, label=_("متوفر"))
