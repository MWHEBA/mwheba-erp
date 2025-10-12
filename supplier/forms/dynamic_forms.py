from django import forms
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

from ..models import (
    SpecializedService, SupplierType, ServicePriceTier,
    PaperServiceDetails, DigitalPrintingDetails, FinishingServiceDetails,
    OffsetPrintingDetails, PlateServiceDetails, OutdoorPrintingDetails,
    LaserServiceDetails, VIPGiftDetails
)


class ServiceFormFactory:
    """مصنع النماذج الديناميكية حسب نوع الخدمة"""
    
    @staticmethod
    def get_form_for_category(category_code, *args, **kwargs):
        """إرجاع النموذج المناسب حسب نوع الخدمة"""
        form_mapping = {
            'paper': PaperServiceForm,
            'offset_printing': OffsetPrintingForm,
            'digital_printing': DigitalPrintingForm,
            'finishing': FinishingServiceForm,
            'plates': PlateServiceForm,
            'outdoor': OutdoorPrintingForm,
            'laser': LaserServiceForm,
            'vip_gifts': VIPGiftForm,
            'packaging': GenericServiceForm,
            'other': GenericServiceForm
        }
        
        form_class = form_mapping.get(category_code, GenericServiceForm)
        return form_class(*args, **kwargs)
    
    @staticmethod
    def get_form_choices_for_category(category_code):
        """إرجاع الخيارات المناسبة لكل تصنيف"""
        
        # للطباعة الأوفست، استخدم البيانات من الإعدادات
        if category_code == 'offset_printing':
            try:
                from pricing.models import OffsetMachineType, OffsetSheetSize
                
                # أنواع الماكينات من الإعدادات
                machine_types = OffsetMachineType.objects.filter(is_active=True).order_by('manufacturer', 'name')
                machine_choices = [
                    (machine.code, str(machine))  # استخدام __str__ method من النموذج
                    for machine in machine_types
                ]
                
                # مقاسات الماكينات من الإعدادات
                sheet_sizes = OffsetSheetSize.objects.filter(is_active=True).order_by('width_cm', 'height_cm')
                size_choices = [
                    (size.code, f"{size.name} ({int(size.width_cm)}×{int(size.height_cm)})")
                    for size in sheet_sizes
                ]
                
                return {
                    'machine_types': machine_choices,
                    'sheet_sizes': size_choices,
                }
            except ImportError:
                # في حالة عدم وجود النماذج، استخدم الخيارات الافتراضية
                pass
        
        # للطباعة الديجيتال، استخدم البيانات من الإعدادات
        if category_code == 'digital_printing':
            try:
                from pricing.models import DigitalMachineType, DigitalSheetSize
                
                # أنواع الماكينات من الإعدادات
                machine_types = DigitalMachineType.objects.filter(is_active=True).order_by('manufacturer', 'name')
                machine_choices = [
                    (machine.code, str(machine))  # استخدام __str__ method من النموذج
                    for machine in machine_types
                ]
                
                # مقاسات الماكينات من الإعدادات
                sheet_sizes = DigitalSheetSize.objects.filter(is_active=True).order_by('width_cm', 'height_cm')
                size_choices = [
                    (size.code, f"{size.name} ({int(size.width_cm)}×{int(size.height_cm)})")
                    for size in sheet_sizes
                ]
                
                return {
                    'machine_types': machine_choices,
                    'paper_sizes': size_choices,  # تغيير الاسم ليطابق template
                }
            except ImportError:
                # في حالة عدم وجود النماذج، استخدم الخيارات الافتراضية
                pass
        
        # للورق، استخدم البيانات من الإعدادات
        if category_code == 'paper':
            try:
                from pricing.models import PaperType, PaperWeight, PaperOrigin
                
                # أنواع الورق من الإعدادات
                paper_types = PaperType.objects.filter(is_active=True).order_by('name')
                type_choices = [
                    (paper_type.name.lower(), paper_type.name)
                    for paper_type in paper_types
                ]
                
                # أوزان الورق من الإعدادات
                paper_weights = PaperWeight.objects.filter(is_active=True).order_by('gsm')
                weight_choices = [
                    (weight.gsm, f"{weight.name} ({weight.gsm} جم)")
                    for weight in paper_weights
                ]
                
                # منشأ الورق من الإعدادات
                paper_origins = PaperOrigin.objects.filter(is_active=True).order_by('name')
                origin_choices = [
                    (origin.code, f"{origin.name} ({origin.code})")
                    for origin in paper_origins
                ]
                
                return {
                    'paper_types': type_choices,
                    'sheet_sizes': PaperServiceDetails.SHEET_SIZE_CHOICES,
                    'paper_weights': weight_choices,
                    'paper_origins': origin_choices,
                }
            except ImportError:
                # في حالة عدم وجود النماذج، استخدم الخيارات الافتراضية
                return {
                    'paper_types': PaperServiceDetails.PAPER_TYPE_CHOICES,
                    'sheet_sizes': PaperServiceDetails.SHEET_SIZE_CHOICES,
                    'paper_weights': [
                        (80, '80 جم'),
                        (90, '90 جم'),
                        (120, '120 جم'),
                        (160, '160 جم'),
                        (200, '200 جم'),
                        (250, '250 جم'),
                        (300, '300 جم'),
                    ],
                    'paper_origins': [
                        ('eg', 'مصر (EG)'),
                        ('cn', 'الصين (CN)'),
                        ('de', 'ألمانيا (DE)'),
                        ('fi', 'فنلندا (FI)'),
                    ],
                }
        
        # الخيارات الافتراضية للتصنيفات الأخرى
        choices_mapping = {
            'paper': {
                'paper_types': PaperServiceDetails.PAPER_TYPE_CHOICES,
                'sheet_sizes': PaperServiceDetails.SHEET_SIZE_CHOICES,
            },
            'offset_printing': {
                'machine_types': OffsetPrintingDetails.MACHINE_TYPE_CHOICES,
                'sheet_sizes': OffsetPrintingDetails.SHEET_SIZE_CHOICES,
            },
            'digital_printing': {
                'machine_types': DigitalPrintingDetails.MACHINE_TYPE_CHOICES,
                'paper_sizes': DigitalPrintingDetails.PAPER_SIZE_CHOICES,
            },
            'finishing': {
                'finishing_types': FinishingServiceDetails.FINISHING_TYPE_CHOICES,
                'calculation_methods': FinishingServiceDetails.CALCULATION_METHOD_CHOICES,
            },
            'plates': {
                'plate_sizes': PlateServiceDetails.PLATE_SIZE_CHOICES,
            },
            'outdoor': {
                'material_types': OutdoorPrintingDetails.MATERIAL_TYPE_CHOICES,
                'printing_types': OutdoorPrintingDetails.PRINTING_TYPE_CHOICES,
            },
            'laser': {
                'laser_types': LaserServiceDetails.LASER_TYPE_CHOICES,
                'service_types': LaserServiceDetails.SERVICE_TYPE_CHOICES,
                'material_types': LaserServiceDetails.MATERIAL_TYPE_CHOICES,
            },
            'vip_gifts': {
                'gift_categories': VIPGiftDetails.GIFT_CATEGORY_CHOICES,
                'customization_types': VIPGiftDetails.CUSTOMIZATION_TYPE_CHOICES,
            }
        }
        
        return choices_mapping.get(category_code, {})


class BaseServiceForm(forms.Form):
    """النموذج الأساسي لجميع الخدمات"""
    
    # الحقول الأساسية المشتركة
    name = forms.CharField(
        label=_('اسم الخدمة'),
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'أدخل اسم الخدمة'})
    )
    
    description = forms.CharField(
        label=_('وصف الخدمة'),
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'وصف تفصيلي للخدمة'})
    )
    
    is_active = forms.BooleanField(
        label=_('نشط'),
        initial=True,
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class PaperServiceForm(BaseServiceForm):
    """نموذج خدمات الورق"""
    
    paper_type = forms.ChoiceField(
        label=_('نوع الورق'),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    gsm = forms.ChoiceField(
        label=_('وزن الورق (جرام)'),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    sheet_size = forms.ChoiceField(
        label=_('مقاس الفرخ'),
        choices=PaperServiceDetails.SHEET_SIZE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'onchange': 'toggleCustomSize(this)'})
    )
    
    custom_width = forms.DecimalField(
        label=_('العرض المخصص (سم)'),
        max_digits=8,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    custom_height = forms.DecimalField(
        label=_('الارتفاع المخصص (سم)'),
        max_digits=8,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    country_of_origin = forms.ChoiceField(
        label=_('بلد المنشأ'),
        choices=[],  # سيتم تحديثها ديناميكياً
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    brand = forms.CharField(
        label=_('الماركة'),
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: UPM'})
    )
    
    price_per_sheet = forms.DecimalField(
        label=_('سعر الفرخ'),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تحديث خيارات أنواع الورق من الإعدادات
        try:
            from pricing.models import PaperType
            paper_types = PaperType.objects.filter(is_active=True).order_by('name')
            self.fields['paper_type'].choices = [('', '-- اختر نوع الورق --')] + [
                (paper_type.name.lower(), paper_type.name)
                for paper_type in paper_types
            ]
        except ImportError:
            # في حالة عدم وجود النموذج، استخدم خيارات افتراضية
            self.fields['paper_type'].choices = PaperServiceDetails.PAPER_TYPE_CHOICES
        
        # تحديث خيارات أوزان الورق من الإعدادات
        try:
            from pricing.models import PaperWeight
            paper_weights = PaperWeight.objects.filter(is_active=True).order_by('gsm')
            self.fields['gsm'].choices = [('', '-- اختر وزن الورق --')] + [
                (weight.gsm, f"{weight.name} ({weight.gsm} جم)")
                for weight in paper_weights
            ]
        except ImportError:
            # في حالة عدم وجود النموذج، استخدم خيارات افتراضية
            self.fields['gsm'].choices = [('', '-- اختر وزن الورق --')] + [
                (80, '80 جم'),
                (90, '90 جم'),
                (120, '120 جم'),
                (160, '160 جم'),
                (200, '200 جم'),
                (250, '250 جم'),
                (300, '300 جم'),
            ]
        
        # تحديث خيارات منشأ الورق من الإعدادات
        try:
            from pricing.models import PaperOrigin
            paper_origins = PaperOrigin.objects.filter(is_active=True).order_by('name')
            origin_choices = [('', '-- اختر المنشأ --')]
            origin_choices.extend([
                (origin.code, f"{origin.name} ({origin.code})")
                for origin in paper_origins
            ])
            self.fields['country_of_origin'].choices = origin_choices
        except ImportError:
            # في حالة عدم وجود النموذج، استخدم خيارات افتراضية
            self.fields['country_of_origin'].choices = [
                ('', '-- اختر المنشأ --'),
                ('EG', 'مصر (EG)'),
                ('CN', 'الصين (CN)'),
                ('DE', 'ألمانيا (DE)'),
                ('FI', 'فنلندا (FI)'),
                ('SE', 'السويد (SE)'),
            ]


class OffsetPrintingForm(BaseServiceForm):
    """نموذج خدمات الطباعة الأوفست"""
    
    machine_type = forms.ChoiceField(
        label=_('نوع الماكينة'),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    sheet_size = forms.ChoiceField(
        label=_('مقاس الماكينة'),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تحديث خيارات أنواع الماكينات من الإعدادات
        try:
            from pricing.models import OffsetMachineType
            machine_types = OffsetMachineType.objects.filter(is_active=True).order_by('manufacturer', 'name')
            self.fields['machine_type'].choices = [
                (machine.code, str(machine))  # استخدام __str__ method من النموذج
                for machine in machine_types
            ]
        except ImportError:
            # في حالة عدم وجود النموذج، استخدم الخيارات الافتراضية
            self.fields['machine_type'].choices = OffsetPrintingDetails.MACHINE_TYPE_CHOICES
        
        # تحديث خيارات مقاسات الماكينات من الإعدادات
        try:
            from pricing.models import OffsetSheetSize
            sheet_sizes = OffsetSheetSize.objects.filter(is_active=True).order_by('width_cm', 'height_cm')
            self.fields['sheet_size'].choices = [
                (size.code, f"{size.name} ({int(size.width_cm)}×{int(size.height_cm)})")
                for size in sheet_sizes
            ]
        except ImportError:
            # في حالة عدم وجود النموذج، استخدم الخيارات الافتراضية
            self.fields['sheet_size'].choices = OffsetPrintingDetails.SHEET_SIZE_CHOICES
    
    max_colors = forms.IntegerField(
        label=_('عدد الألوان'),
        initial=4,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '8'})
    )
    
    impression_cost_per_1000 = forms.DecimalField(
        label=_('سعر التراج (لكل 1000)'),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    special_impression_cost = forms.DecimalField(
        label=_('سعر التراج مخصوص'),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    break_impression_cost = forms.DecimalField(
        label=_('سعر كسر التراج'),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )


class DigitalPrintingForm(BaseServiceForm):
    """نموذج خدمات الطباعة الديجيتال مبسط"""
    
    machine_type = forms.ChoiceField(
        label=_('نوع الماكينة'),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    paper_size = forms.ChoiceField(
        label=_('مقاس الماكينة'),
        choices=[],  # سيتم تحديثها ديناميكياً
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تحديث خيارات أنواع الماكينات من الإعدادات
        try:
            from pricing.models import DigitalMachineType
            machine_types = DigitalMachineType.objects.filter(is_active=True).order_by('manufacturer', 'name')
            self.fields['machine_type'].choices = [
                (machine.code, str(machine))  # استخدام __str__ method من النموذج
                for machine in machine_types
            ]
        except ImportError:
            # في حالة عدم وجود النموذج، استخدم الخيارات الافتراضية
            self.fields['machine_type'].choices = DigitalPrintingDetails.MACHINE_TYPE_CHOICES
        
        # تحديث خيارات مقاسات الماكينات من الإعدادات
        try:
            from pricing.models import DigitalSheetSize
            sheet_sizes = DigitalSheetSize.objects.filter(is_active=True).order_by('width_cm', 'height_cm')
            self.fields['paper_size'].choices = [
                (size.code, f"{size.name} ({int(size.width_cm)}×{int(size.height_cm)})")
                for size in sheet_sizes
            ]
        except ImportError:
            # في حالة عدم وجود النموذج، استخدم الخيارات الافتراضية
            self.fields['paper_size'].choices = DigitalPrintingDetails.PAPER_SIZE_CHOICES
    
    # الشرائح السعرية إجبارية للطباعة الديجيتال
    has_price_tiers = forms.BooleanField(
        label=_('استخدام شرائح سعرية'),
        initial=True,
        required=True,
        widget=forms.HiddenInput()  # مخفي لأنه إجباري
    )


class FinishingServiceForm(BaseServiceForm):
    """نموذج خدمات الطباعة (التشطيب)"""
    
    finishing_type = forms.ChoiceField(
        label=_('نوع الخدمة'),
        choices=FinishingServiceDetails.FINISHING_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    calculation_method = forms.ChoiceField(
        label=_('طريقة الحساب'),
        choices=FinishingServiceDetails.CALCULATION_METHOD_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    price_per_unit = forms.DecimalField(
        label=_('سعر الوحدة'),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    setup_time_minutes = forms.IntegerField(
        label=_('وقت التجهيز (دقائق)'),
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0'})
    )
    
    turnaround_time_hours = forms.IntegerField(
        label=_('وقت التسليم (ساعات)'),
        initial=24,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
    )


class PlateServiceForm(BaseServiceForm):
    """نموذج خدمات الزنكات"""
    
    plate_size = forms.ChoiceField(
        label=_('مقاس الزنك'),
        choices=PlateServiceDetails.PLATE_SIZE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    price_per_plate = forms.DecimalField(
        label=_('سعر الزنك الواحد'),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    set_price = forms.DecimalField(
        label=_('سعر الطقم (4 زنكات)'),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )


class OutdoorPrintingForm(BaseServiceForm):
    """نموذج خدمات الأوت دور"""
    
    material_type = forms.ChoiceField(
        label=_('نوع المادة'),
        choices=OutdoorPrintingDetails.MATERIAL_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    printing_type = forms.ChoiceField(
        label=_('نوع الطباعة'),
        choices=OutdoorPrintingDetails.PRINTING_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    max_width_cm = forms.DecimalField(
        label=_('أقصى عرض (سم)'),
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    price_per_sqm = forms.DecimalField(
        label=_('سعر المتر المربع'),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    min_order_sqm = forms.DecimalField(
        label=_('الحد الأدنى (متر مربع)'),
        max_digits=8,
        decimal_places=2,
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )


class LaserServiceForm(BaseServiceForm):
    """نموذج خدمات الليزر"""
    
    laser_type = forms.ChoiceField(
        label=_('نوع الليزر'),
        choices=LaserServiceDetails.LASER_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    service_type = forms.ChoiceField(
        label=_('نوع الخدمة'),
        choices=LaserServiceDetails.SERVICE_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    material_type = forms.ChoiceField(
        label=_('نوع المادة'),
        choices=LaserServiceDetails.MATERIAL_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    max_width_cm = forms.DecimalField(
        label=_('أقصى عرض (سم)'),
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    max_height_cm = forms.DecimalField(
        label=_('أقصى ارتفاع (سم)'),
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    price_per_minute = forms.DecimalField(
        label=_('سعر الدقيقة'),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    price_per_piece = forms.DecimalField(
        label=_('سعر القطعة'),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )


class VIPGiftForm(BaseServiceForm):
    """نموذج خدمات الهدايا المميزة"""
    
    gift_category = forms.ChoiceField(
        label=_('فئة الهدية'),
        choices=VIPGiftDetails.GIFT_CATEGORY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    customization_type = forms.ChoiceField(
        label=_('نوع التخصيص'),
        choices=VIPGiftDetails.CUSTOMIZATION_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    product_name = forms.CharField(
        label=_('اسم المنتج'),
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: قلم ذهبي محفور'})
    )
    
    brand = forms.CharField(
        label=_('الماركة'),
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: Parker'})
    )
    
    customization_cost = forms.DecimalField(
        label=_('تكلفة التخصيص'),
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    packaging_cost = forms.DecimalField(
        label=_('تكلفة التغطية'),
        max_digits=10,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )


class GenericServiceForm(BaseServiceForm):
    """نموذج عام للخدمات الأخرى"""
    
    service_details = forms.CharField(
        label=_('تفاصيل الخدمة'),
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'أدخل تفاصيل الخدمة'})
    )
    
    price_per_unit = forms.DecimalField(
        label=_('سعر الوحدة'),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    unit_type = forms.CharField(
        label=_('نوع الوحدة'),
        max_length=50,
        initial='قطعة',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: قطعة، متر، ساعة'})
    )


# نموذج الشرائح السعرية
class PriceTierForm(forms.ModelForm):
    """نموذج الشريحة السعرية"""
    
    class Meta:
        model = ServicePriceTier
        fields = ['tier_name', 'min_quantity', 'max_quantity', 'price_per_unit', 'discount_percentage']
        widgets = {
            'tier_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: 1-100'}),
            'min_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'max_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'price_per_unit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'discount_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'max': '100'}),
        }
