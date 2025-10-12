from django import forms
from django.utils.translation import gettext_lazy as _
from .models import (
    PricingOrder, InternalContent, OrderFinishing, ExtraExpense, 
    OrderComment, CtpPlates, PaperType, PaperSize, OrderSupplier, PricingQuotation,
    PricingApprovalWorkflow, PricingApproval, PricingReport, PricingKPI,
    OffsetMachineType, OffsetSheetSize, DigitalMachineType, DigitalSheetSize,
    PaperWeight, PaperOrigin, ProductType, ProductSize, CoatingType, FinishingType
)
from supplier.models import Supplier, PaperServiceDetails
from client.models import Customer as Client
from users.models import User


class PricingOrderForm(forms.ModelForm):
    """نموذج طلب التسعير"""
    
    # تم نقل PRODUCT_TYPES إلى __init__ للربط بالإعدادات
    
    BINDING_TYPES = [
        ('staple', _('تدبيس')),
        ('wire', _('سلك')),
        ('sewing', _('خياطة')),
        ('glue', _('تغرية')),
        ('spiral', _('سبيرال')),
        ('none', _('بدون')),
    ]
    
    product_type = forms.ModelChoiceField(
        label=_('نوع المنتج'),
        queryset=ProductType.objects.none(),  # سيتم تحديثه في __init__
        widget=forms.Select(attrs={'class': 'form-control'}),
        empty_label=_('اختر نوع المنتج')
    )
    
    custom_size_width = forms.DecimalField(
        label=_('العرض (سم)'),
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    custom_size_height = forms.DecimalField(
        label=_('الطول (سم)'),
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    open_size_width = forms.DecimalField(
        label=_('عرض المقاس المفتوح (سم)'),
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    open_size_height = forms.DecimalField(
        label=_('طول المقاس المفتوح (سم)'),
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'})
    )
    
    binding_type = forms.ChoiceField(
        label=_('نوع التقفيل'),
        choices=BINDING_TYPES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    binding_side = forms.ChoiceField(
        label=_('جهة التقفيل'),
        choices=[
            ('arabic', _('عربي')),
            ('english', _('انجليزي')),
            ('top', _('أعلى')),
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    paper_supplier = forms.ModelChoiceField(
        label=_('مورد الورق'),
        queryset=Supplier.objects.filter(
            is_active=True,
            id__in=PaperServiceDetails.objects.filter(
                service__is_active=True
            ).values_list('service__supplier_id', flat=True).distinct()
        ).distinct(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    paper_sheet_type = forms.ChoiceField(
        label=_('مقاس الفرخ'),
        choices=[],  # مؤقت - قائمة فارغة
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    paper_origin = forms.ChoiceField(
        label=_('بلد المنشأ'),
        required=False,
        choices=[('', '---------')],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    paper_weight = forms.ChoiceField(
        label=_('جرام الورق'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    paper_price = forms.DecimalField(
        label=_('سعر الورق'),
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    zinc_plates_count = forms.IntegerField(
        label=_('عدد الزنكات'),
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    internal_page_count = forms.IntegerField(
        label=_('عدد صفحات الداخل'),
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    design_price = forms.DecimalField(
        label=_('سعر التصميم'),
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    class Meta:
        model = PricingOrder
        fields = [
            'client', 'order_type', 'title', 'description', 'quantity',
            'has_internal_content', 'product_type', 'paper_type', 'paper_size', 'print_direction',
            'print_sides', 'colors_front', 'colors_back', 'coating_type', 'coating_service',
            'supplier', 'press', 'material_cost', 'printing_cost',
            'finishing_cost', 'extra_cost', 'profit_margin', 'sale_price',
            'status'
        ]
        widgets = {
            'client': forms.Select(attrs={'class': 'form-control select2', 'data-placeholder': 'اختر العميل...'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'material_cost': forms.NumberInput(attrs={'step': '0.01'}),
            'printing_cost': forms.NumberInput(attrs={'step': '0.01'}),
            'finishing_cost': forms.NumberInput(attrs={'step': '0.01'}),
            'extra_cost': forms.NumberInput(attrs={'step': '0.01'}),
            'profit_margin': forms.NumberInput(attrs={'step': '0.01'}),
            'sale_price': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # إضافة الفئات لحقول النموذج
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
        
        # ربط نوع المنتج بالإعدادات
        try:
            self.fields['product_type'].queryset = ProductType.objects.filter(is_active=True).order_by('name')
        except:
            # fallback في حالة عدم وجود النموذج
            pass
        
        # ربط مقاس المنتج بالإعدادات
        try:
            # تحديث حقل paper_size ليكون مربوط بـ ProductSize
            from .models import ProductSize
            self.fields['paper_size'].queryset = ProductSize.objects.filter(is_active=True).order_by('name')
        except:
            # fallback في حالة عدم وجود النموذج
            pass
        
        # جعل بعض الحقول اختيارية
        self.fields['product_type'].required = False
        self.fields['press'].required = False
        self.fields['coating_type'].required = False
        self.fields['coating_service'].required = False
        self.fields['supplier'].required = False
        self.fields['description'].required = False
        
        # تصفية خدمات التغطية معطلة مؤقتاً
        
        # ربط نوع الورق بالإعدادات
        try:
            self.fields['paper_type'].queryset = PaperType.objects.filter(is_active=True).order_by('name')
        except:
            # fallback في حالة عدم وجود النموذج
            pass
        
        # إعداد اختيارات جرام الورق من قاعدة البيانات
        try:
            paper_weights = PaperWeight.objects.filter(is_active=True).order_by('gsm')
            weight_choices = [('', '---------')]
            for weight in paper_weights:
                weight_choices.append((weight.id, f"{weight.name} ({weight.gsm} جم)"))
            self.fields['paper_weight'].choices = weight_choices
        except:
            # fallback للقائمة الثابتة في حالة عدم وجود البيانات
            paper_weights = [
                (80, '80 جم'),
                (90, '90 جم'),
                (100, '100 جم'),
                (120, '120 جم'),
                (150, '150 جم'),
                (170, '170 جم'),
                (200, '200 جم'),
                (250, '250 جم'),
                (300, '300 جم'),
                (350, '350 جم'),
            ]
            self.fields['paper_weight'].choices = [('', '---------')] + paper_weights
        
        # تعيين المندوب المسؤول تلقائيًا إذا كان النموذج جديدًا
        if user and not self.instance.pk:
            self.initial['created_by'] = user

    def clean(self):
        """التحقق من صحة البيانات المدخلة والعلاقة بين الحقول"""
        cleaned_data = super().clean()
        print_sides = cleaned_data.get('print_sides')
        colors_front = cleaned_data.get('colors_front')
        colors_back = cleaned_data.get('colors_back')
        
        # التحقق من أن جوانب الطباعة محددة
        if not print_sides:
            self.add_error('print_sides', _('يجب تحديد جوانب الطباعة'))
            return cleaned_data
        
        # التحقق من عدد الألوان حسب جوانب الطباعة
        try:
            # التحقق من وجود وجهي الطباعة
            sides_count = getattr(print_sides, 'sides_count', None)
            
            if sides_count == 2:  # الطباعة على وجهين
                if colors_front is None:
                    self.add_error('colors_front', _('يجب تحديد عدد ألوان الوجه الأمامي'))
                if colors_back is None:
                    self.add_error('colors_back', _('يجب تحديد عدد ألوان الوجه الخلفي'))
            elif sides_count == 1:  # الطباعة على وجه واحد
                if colors_front is None:
                    self.add_error('colors_front', _('يجب تحديد عدد ألوان الوجه الأمامي'))
                # إعادة تعيين عدد ألوان الوجه الخلفي إلى 0
                cleaned_data['colors_back'] = 0
            else:
                # للاحتياط في حالة كان sides_count غير محدد
                self.add_error('print_sides', _('قيمة غير صالحة لجوانب الطباعة'))
                
        except Exception as e:
            print(f"خطأ في التحقق من جوانب الطباعة: {e}")
            self.add_error('print_sides', _('حدث خطأ في التحقق من جوانب الطباعة'))
            
        # التأكد من أن قيم الألوان موجبة
        if colors_front is not None and colors_front < 0:
            self.add_error('colors_front', _('عدد الألوان يجب أن يكون موجباً'))
            
        if colors_back is not None and colors_back < 0:
            self.add_error('colors_back', _('عدد الألوان يجب أن يكون موجباً'))
        
        return cleaned_data


class InternalContentForm(forms.ModelForm):
    """نموذج المحتوى الداخلي للطلب"""
    
    class Meta:
        model = InternalContent
        fields = [
            'paper_type', 'paper_size', 'page_count', 'print_sides',
            'colors_front', 'colors_back', 'material_cost', 'printing_cost',
        ]
        widgets = {
            'material_cost': forms.NumberInput(attrs={'step': '0.01'}),
            'printing_cost': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # إضافة الفئات لحقول النموذج
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


class OrderFinishingForm(forms.ModelForm):
    """نموذج خدمات الطباعة للطلب"""
    
    class Meta:
        model = OrderFinishing
        fields = [
            'finishing_type', 'supplier_service', 'quantity', 'unit_price', 'notes',
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # إضافة الفئات لحقول النموذج
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
        
        # تصفية خدمات الموردين معطلة مؤقتاً
        
        # جعل finishing_type اختياري للسماح باستخدام خدمات الموردين بدلاً من ذلك
        self.fields['finishing_type'].required = False
        # جعل supplier_service اختياري للسماح بالانتقال التدريجي
        self.fields['supplier_service'].required = False
        # جعل الملاحظات اختيارية
        self.fields['notes'].required = False


class ExtraExpenseForm(forms.ModelForm):
    """نموذج المصاريف الإضافية للطلب"""
    
    class Meta:
        model = ExtraExpense
        fields = ['name', 'description', 'amount']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'amount': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # إضافة الفئات لحقول النموذج
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
        
        # جعل الوصف اختياري
        self.fields['description'].required = False


class OrderCommentForm(forms.ModelForm):
    """نموذج تعليقات الطلب"""
    
    class Meta:
        model = OrderComment
        fields = ['comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 2, 'placeholder': _('أضف تعليقك هنا...')}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # إضافة الفئات لحقول النموذج
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


class CtpPlatesForm(forms.ModelForm):
    """نموذج الزنكات (CTP)"""
    
    class Meta:
        model = CtpPlates
        fields = [
            'supplier', 'plate_size', 'plates_count', 'plate_price', 
            'transportation_cost', 'notes'
        ]
        widgets = {
            'plate_price': forms.NumberInput(attrs={'step': '0.01'}),
            'transportation_cost': forms.NumberInput(attrs={'step': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # إضافة الفئات لحقول النموذج
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'
        
        # تصفية الموردين ليظهر فقط موردي الزنكات
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)  # مؤقت - جميع الموردين
        
        # جعل الملاحظات اختيارية
        self.fields['notes'].required = False


class PricingOrderApproveForm(forms.ModelForm):
    """نموذج اعتماد طلب التسعير"""
    
    class Meta:
        model = PricingOrder
        fields = ['sale_price']
        widgets = {
            'sale_price': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # إضافة الفئات لحقول النموذج
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control'


# ==================== النماذج الجديدة للنظام المستقل ====================

class OrderSupplierForm(forms.ModelForm):
    """نموذج ربط الموردين المتعددين بطلب التسعير"""
    
    class Meta:
        model = OrderSupplier
        fields = [
            'supplier', 'role', 'service_type', 'description',
            'estimated_cost', 'quoted_price', 'contact_person',
            'phone', 'email', 'is_confirmed', 'notes'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'estimated_cost': forms.NumberInput(attrs={'step': '0.01'}),
            'quoted_price': forms.NumberInput(attrs={'step': '0.01'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'service_type': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ['role', 'service_type']:
                field.widget.attrs['class'] = 'form-control'
        
        # تصفية الموردين النشطين
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        
        # جعل بعض الحقول اختيارية
        optional_fields = ['description', 'contact_person', 'phone', 'email', 'notes']
        for field in optional_fields:
            self.fields[field].required = False


class PricingQuotationForm(forms.ModelForm):
    """نموذج عروض الأسعار المستقلة"""
    
    class Meta:
        model = PricingQuotation
        fields = [
            'valid_until', 'follow_up_date', 'status', 'payment_terms',
            'delivery_terms', 'warranty_terms', 'special_conditions',
            'sent_to_person', 'sent_via', 'discount_percentage',
            'client_feedback', 'internal_notes'
        ]
        widgets = {
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
            'follow_up_date': forms.DateInput(attrs={'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'sent_via': forms.Select(attrs={'class': 'form-select'}),
            'payment_terms': forms.Textarea(attrs={'rows': 3}),
            'delivery_terms': forms.Textarea(attrs={'rows': 3}),
            'warranty_terms': forms.Textarea(attrs={'rows': 2}),
            'special_conditions': forms.Textarea(attrs={'rows': 2}),
            'client_feedback': forms.Textarea(attrs={'rows': 3}),
            'internal_notes': forms.Textarea(attrs={'rows': 3}),
            'discount_percentage': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'max': '100'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ['status', 'sent_via']:
                field.widget.attrs['class'] = 'form-control'
        
        # جعل بعض الحقول اختيارية
        optional_fields = [
            'follow_up_date', 'warranty_terms', 'special_conditions',
            'sent_to_person', 'client_feedback', 'internal_notes'
        ]
        for field in optional_fields:
            self.fields[field].required = False


class PricingApprovalWorkflowForm(forms.ModelForm):
    """نموذج تدفق موافقات التسعير المبسط"""
    
    class Meta:
        model = PricingApprovalWorkflow
        fields = [
            'name', 'description', 'is_active', 'min_amount', 'max_amount',
            'primary_approver', 'secondary_approver', 'email_notifications',
            'whatsapp_notifications', 'auto_approve_below_limit', 'require_both_approvers'
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'min_amount': forms.NumberInput(attrs={'step': '0.01'}),
            'max_amount': forms.NumberInput(attrs={'step': '0.01'}),
            'primary_approver': forms.Select(attrs={'class': 'form-select'}),
            'secondary_approver': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ['primary_approver', 'secondary_approver']:
                if isinstance(field.widget, forms.CheckboxInput):
                    field.widget.attrs['class'] = 'form-check-input'
                else:
                    field.widget.attrs['class'] = 'form-control'
        
        # تصفية المستخدمين النشطين
        self.fields['primary_approver'].queryset = User.objects.filter(is_active=True)
        self.fields['secondary_approver'].queryset = User.objects.filter(is_active=True)
        
        # جعل بعض الحقول اختيارية
        optional_fields = ['description', 'max_amount', 'secondary_approver']
        for field in optional_fields:
            self.fields[field].required = False


class PricingApprovalForm(forms.ModelForm):
    """نموذج موافقات طلبات التسعير"""
    
    class Meta:
        model = PricingApproval
        fields = ['status', 'comments', 'priority']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'comments': forms.Textarea(attrs={'rows': 4}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name not in ['status', 'priority']:
                field.widget.attrs['class'] = 'form-control'
        
        # جعل التعليقات اختيارية
        self.fields['comments'].required = False


class QuotationSearchForm(forms.Form):
    """نموذج البحث في العروض"""
    
    search = forms.CharField(
        label=_('البحث'),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': _('البحث في رقم العرض أو العميل...')
        })
    )
    
    status = forms.ChoiceField(
        label=_('الحالة'),
        required=False,
        choices=[('', _('جميع الحالات'))] + list(PricingQuotation.STATUS_CHOICES),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    date_from = forms.DateField(
        label=_('من تاريخ'),
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    
    date_to = forms.DateField(
        label=_('إلى تاريخ'),
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )


# ==================== نموذج أوزان الورق ====================

class PaperWeightForm(forms.ModelForm):
    """نموذج أوزان الورق"""
    
    class Meta:
        model = PaperWeight
        fields = ['name', 'gsm', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ورق عادي'
            }),
            'gsm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 80',
                'min': '50',
                'max': '500'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لوزن الورق'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم الوزن'),
            'gsm': _('الوزن (جرام)'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }
    
    def clean_gsm(self):
        """التحقق من صحة الوزن"""
        gsm = self.cleaned_data.get('gsm')
        if gsm and (gsm < 50 or gsm > 500):
            raise forms.ValidationError(_('الوزن يجب أن يكون بين 50 و 500 جرام'))
        
        # التحقق من عدم تكرار الوزن
        if gsm:
            existing = PaperWeight.objects.filter(gsm=gsm)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الوزن موجود مسبقاً'))
        
        return gsm
    
    def clean(self):
        """التحقق من وجود افتراضي واحد فقط"""
        cleaned_data = super().clean()
        is_default = cleaned_data.get('is_default')
        
        if is_default:
            # التحقق من عدم وجود افتراضي آخر
            existing_default = PaperWeight.objects.filter(is_default=True)
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            if existing_default.exists():
                raise forms.ValidationError(_('يمكن أن يكون هناك وزن افتراضي واحد فقط'))
        
        return cleaned_data


# ==================== نماذج أنواع وأحجام الورق ====================

class PaperTypeForm(forms.ModelForm):
    """نموذج أنواع الورق"""
    
    class Meta:
        model = PaperType
        fields = ['name', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ورق مطبوع'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع الورق'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم نوع الورق'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }
    
    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = PaperType.objects.filter(name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name
    
    def clean(self):
        """التحقق من وجود افتراضي واحد فقط"""
        cleaned_data = super().clean()
        is_default = cleaned_data.get('is_default')
        
        if is_default:
            existing_default = PaperType.objects.filter(is_default=True)
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            if existing_default.exists():
                raise forms.ValidationError(_('يمكن أن يكون هناك نوع افتراضي واحد فقط'))
        
        return cleaned_data


class PaperSizeForm(forms.ModelForm):
    """نموذج أحجام الورق"""
    
    class Meta:
        model = PaperSize
        fields = ['name', 'width', 'height', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: A4'
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 21.0',
                'step': '0.1',
                'min': '0.1'
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 29.7',
                'step': '0.1',
                'min': '0.1'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم المقاس'),
            'width': _('العرض (سم)'),
            'height': _('الطول (سم)'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }
    
    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = PaperSize.objects.filter(name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name
    
    def clean_width(self):
        """التحقق من صحة العرض"""
        width = self.cleaned_data.get('width')
        if width and width <= 0:
            raise forms.ValidationError(_('العرض يجب أن يكون أكبر من صفر'))
        return width
    
    def clean_height(self):
        """التحقق من صحة الطول"""
        height = self.cleaned_data.get('height')
        if height and height <= 0:
            raise forms.ValidationError(_('الطول يجب أن يكون أكبر من صفر'))
        return height
    
    def clean(self):
        """التحقق من وجود افتراضي واحد فقط"""
        cleaned_data = super().clean()
        is_default = cleaned_data.get('is_default')
        
        if is_default:
            existing_default = PaperSize.objects.filter(is_default=True)
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            if existing_default.exists():
                raise forms.ValidationError(_('يمكن أن يكون هناك مقاس افتراضي واحد فقط'))
        
        return cleaned_data


class PaperOriginForm(forms.ModelForm):
    """نموذج منشأ الورق"""
    
    class Meta:
        model = PaperOrigin
        fields = ['name', 'code', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: مصر'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: EG',
                'maxlength': '10'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لمنشأ الورق'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم المنشأ'),
            'code': _('رمز المنشأ'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }
    
    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = PaperOrigin.objects.filter(name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name
    
    def clean_code(self):
        """التحقق من عدم تكرار الرمز"""
        code = self.cleaned_data.get('code')
        if code:
            code = code.upper()  # تحويل لأحرف كبيرة
            existing = PaperOrigin.objects.filter(code=code)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الرمز موجود مسبقاً'))
        return code
    
    def clean(self):
        """التحقق من وجود افتراضي واحد فقط"""
        cleaned_data = super().clean()
        is_default = cleaned_data.get('is_default')
        
        if is_default:
            existing_default = PaperOrigin.objects.filter(is_default=True)
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            if existing_default.exists():
                raise forms.ValidationError(_('يمكن أن يكون هناك منشأ افتراضي واحد فقط'))
        
        return cleaned_data


# ==================== نماذج أنواع الماكينات ====================

class OffsetMachineTypeForm(forms.ModelForm):
    """نموذج أنواع ماكينات الأوفست"""
    
    class Meta:
        model = OffsetMachineType
        fields = ['name', 'code', 'manufacturer', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ماكينة أوفست نصف فرخ'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: OFF-HALF'
            }),
            'manufacturer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: هايدلبرغ'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع الماكينة'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم نوع الماكينة'),
            'code': _('كود النوع'),
            'manufacturer': _('الشركة المصنعة'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }
    
    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = OffsetMachineType.objects.filter(name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name
    
    def clean_code(self):
        """التحقق من عدم تكرار الكود"""
        code = self.cleaned_data.get('code')
        if code:
            code = code.strip().upper()  # تحويل إلى أحرف كبيرة
            existing = OffsetMachineType.objects.filter(code=code)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الكود موجود مسبقاً'))
        return code
    
    def clean(self):
        """التحقق من وجود افتراضي واحد فقط"""
        cleaned_data = super().clean()
        is_default = cleaned_data.get('is_default')
        
        if is_default:
            existing_default = OffsetMachineType.objects.filter(is_default=True)
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            if existing_default.exists():
                raise forms.ValidationError(_('يمكن أن يكون هناك نوع افتراضي واحد فقط'))
        
        return cleaned_data


class CoatingTypeForm(forms.ModelForm):
    """نموذج أنواع التغطية"""
    
    class Meta:
        model = CoatingType
        fields = ['name', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: تغطية لامعة'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع التغطية'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم نوع التغطية'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }
    
    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = CoatingType.objects.filter(name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name
    
    def clean(self):
        """التحقق من وجود افتراضي واحد فقط"""
        cleaned_data = super().clean()
        is_default = cleaned_data.get('is_default')
        
        if is_default:
            existing_default = CoatingType.objects.filter(is_default=True)
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            if existing_default.exists():
                raise forms.ValidationError(_('يمكن أن يكون هناك نوع افتراضي واحد فقط'))
        
        return cleaned_data


class DigitalMachineTypeForm(forms.ModelForm):
    """نموذج أنواع ماكينات الديجيتال"""
    
    class Meta:
        model = DigitalMachineType
        fields = ['name', 'code', 'manufacturer', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ماكينة ديجيتال A3'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: DIG-A3'
            }),
            'manufacturer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: كانون'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع الماكينة'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم نوع الماكينة'),
            'code': _('كود النوع'),
            'manufacturer': _('الشركة المصنعة'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }
    
    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = DigitalMachineType.objects.filter(name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name
    
    def clean(self):
        """التحقق من وجود افتراضي واحد فقط"""
        cleaned_data = super().clean()
        is_default = cleaned_data.get('is_default')
        
        if is_default:
            existing_default = DigitalMachineType.objects.filter(is_default=True)
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            if existing_default.exists():
                raise forms.ValidationError(_('يمكن أن يكون هناك نوع افتراضي واحد فقط'))
        
        return cleaned_data


# ==================== نماذج أنواع ومقاسات المنتجات ====================

class ProductTypeForm(forms.ModelForm):
    """نموذج أنواع المنتجات"""
    
    class Meta:
        model = ProductType
        fields = ['name', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: كتالوج'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع المنتج'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم نوع المنتج'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }
    
    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = ProductType.objects.filter(name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name
    
    def clean(self):
        """التحقق من وجود افتراضي واحد فقط"""
        cleaned_data = super().clean()
        is_default = cleaned_data.get('is_default')
        
        if is_default:
            existing_default = ProductType.objects.filter(is_default=True)
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            if existing_default.exists():
                raise forms.ValidationError(_('يمكن أن يكون هناك نوع منتج افتراضي واحد فقط'))
        
        return cleaned_data


class ProductSizeForm(forms.ModelForm):
    """نموذج مقاسات المنتجات"""
    
    class Meta:
        model = ProductSize
        fields = ['name', 'width', 'height', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: A4'
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 21.0',
                'step': '0.1',
                'min': '0.1'
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 29.7',
                'step': '0.1',
                'min': '0.1'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري للمقاس'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم المقاس'),
            'width': _('العرض (سم)'),
            'height': _('الطول (سم)'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }
    
    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = ProductSize.objects.filter(name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name
    
    def clean_width(self):
        """التحقق من صحة العرض"""
        width = self.cleaned_data.get('width')
        if width and width <= 0:
            raise forms.ValidationError(_('العرض يجب أن يكون أكبر من صفر'))
        return width
    
    def clean_height(self):
        """التحقق من صحة الطول"""
        height = self.cleaned_data.get('height')
        if height and height <= 0:
            raise forms.ValidationError(_('الطول يجب أن يكون أكبر من صفر'))
        return height
    
    def clean(self):
        """التحقق من وجود افتراضي واحد فقط"""
        cleaned_data = super().clean()
        is_default = cleaned_data.get('is_default')
        
        if is_default:
            existing_default = ProductSize.objects.filter(is_default=True)
            if self.instance.pk:
                existing_default = existing_default.exclude(pk=self.instance.pk)
            if existing_default.exists():
                raise forms.ValidationError(_('يمكن أن يكون هناك مقاس افتراضي واحد فقط'))
        
        return cleaned_data


class FinishingTypeForm(forms.ModelForm):
    """نموذج أنواع التشطيب"""
    
    class Meta:
        model = FinishingType
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('اسم نوع التشطيب')
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('وصف نوع التشطيب (اختياري)')
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم نوع التشطيب'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
        }
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            name = name.strip()
            # التحقق من عدم وجود نوع تشطيب بنفس الاسم
            existing = FinishingType.objects.filter(name__iexact=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(_('يوجد نوع تشطيب بهذا الاسم بالفعل'))
        return name


# ==================== نماذج مقاسات الماكينات ====================

class OffsetSheetSizeForm(forms.ModelForm):
    """نموذج مقاسات ماكينات الأوفست"""
    
    class Meta:
        model = OffsetSheetSize
        fields = ['name', 'code', 'width_cm', 'height_cm', 'description', 'is_active', 'is_default', 'is_custom_size']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: فرخ كامل'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: FULL-SHEET'
            }),
            'width_cm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 70.0',
                'step': '0.1',
                'min': '0.1'
            }),
            'height_cm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 100.0',
                'step': '0.1',
                'min': '0.1'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري للمقاس'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_custom_size': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم المقاس'),
            'code': _('كود المقاس'),
            'width_cm': _('العرض (سم)'),
            'height_cm': _('الطول (سم)'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
            'is_custom_size': _('مقاس مخصص'),
        }


class DigitalSheetSizeForm(forms.ModelForm):
    """نموذج مقاسات ماكينات الديجيتال"""
    
    class Meta:
        model = DigitalSheetSize
        fields = ['name', 'code', 'width_cm', 'height_cm', 'description', 'is_active', 'is_default', 'is_custom_size']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: A3'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: A3-SIZE'
            }),
            'width_cm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 29.7',
                'step': '0.1',
                'min': '0.1'
            }),
            'height_cm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 42.0',
                'step': '0.1',
                'min': '0.1'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري للمقاس'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_default': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'is_custom_size': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }
        labels = {
            'name': _('اسم المقاس'),
            'code': _('كود المقاس'),
            'width_cm': _('العرض (سم)'),
            'height_cm': _('الطول (سم)'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
            'is_custom_size': _('مقاس مخصص'),
        }
