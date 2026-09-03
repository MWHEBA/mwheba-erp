"""
نماذج إدارة الإعدادات والإعدادات المتقدمة الموحدة
Unified settings and advanced settings forms
"""

from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from ..models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin,
    CoatingType, FinishingType,
    PieceSize, PlateSize, ProductType, ProductSize,
    OffsetMachineType, DigitalMachineType, OffsetSheetSize, DigitalSheetSize
)
from users.models import User


# ==================== نماذج أنواع الورق ====================

class PaperTypeForm(forms.ModelForm):
    """نموذج أنواع الورق"""

    class Meta:
        model = PaperType
        fields = ['name', 'description', 'override_sheets_per_pack', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ورق أبيض'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع الورق'
            }),
            'override_sheets_per_pack': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'اتركه فارغاً للاعتماد على الجراماج، أو اكتب مثلاً: 100 للدوبلكس',
                'min': '1',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم نوع الورق'),
            'description': _('الوصف'),
            'override_sheets_per_pack': _('سعة رزمة خاصة بالخامة (فرخ)'),
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
                raise ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            PaperType.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


# ==================== نماذج مقاسات الورق ====================

class PaperSizeForm(forms.ModelForm):
    """نموذج مقاسات الورق"""

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
                'min': '0.1',
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 29.7',
                'step': '0.1',
                'min': '0.1',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
                raise ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name

    def clean_width(self):
        """التحقق من صحة العرض"""
        width = self.cleaned_data.get('width')
        if width and width <= 0:
            raise ValidationError(_('العرض يجب أن يكون أكبر من صفر'))
        return width

    def clean_height(self):
        """التحقق من صحة الطول"""
        height = self.cleaned_data.get('height')
        if height and height <= 0:
            raise ValidationError(_('الطول يجب أن يكون أكبر من صفر'))
        return height

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            PaperSize.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


# ==================== نماذج أوزان الورق ====================

class PaperWeightForm(forms.ModelForm):
    """نموذج أوزان الورق"""

    class Meta:
        model = PaperWeight
        fields = ['name', 'gsm', 'sheets_per_pack', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ورق عادي'
            }),
            'gsm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 80',
                'min': '50',
                'max': '500',
            }),
            'sheets_per_pack': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 500 أو 250 أو 125',
                'min': '1',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لوزن الورق'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم الوزن'),
            'gsm': _('الوزن (جرام)'),
            'sheets_per_pack': _('سعة الرزمة القياسية (فرخ)'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }

    def clean_gsm(self):
        """التحقق من صحة الوزن"""
        gsm = self.cleaned_data.get('gsm')
        if gsm and (gsm < 50 or gsm > 500):
            raise ValidationError(_('الوزن يجب أن يكون بين 50 و 500 جرام'))

        # التحقق من عدم تكرار الوزن
        if gsm:
            existing = PaperWeight.objects.filter(gsm=gsm)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError(_('هذا الوزن موجود مسبقاً'))

        return gsm

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            PaperWeight.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


# ==================== نماذج مناشئ الورق ====================

class PaperOriginForm(forms.ModelForm):
    """نموذج مناشئ الورق"""

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
                'maxlength': '10',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لمنشأ الورق'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
                raise ValidationError(_('هذا الاسم موجود مسبقاً'))
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
                raise ValidationError(_('هذا الرمز موجود مسبقاً'))
        return code

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            PaperOrigin.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance





# ==================== النماذج المتقدمة المدموجة ====================

class CoatingTypeForm(forms.ModelForm):
    """نموذج أنواع التغطية"""

    class Meta:
        model = CoatingType
        fields = ['name', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ورنيش'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع التغطية'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
                raise ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            CoatingType.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


class FinishingTypeForm(forms.ModelForm):
    """نموذج أنواع خدمات الطباعة"""

    class Meta:
        model = FinishingType
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: تقفيل'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع خدمات الطباعة'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم نوع خدمات الطباعة'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
        }

    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = FinishingType.objects.filter(name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError(_('هذا الاسم موجود مسبقاً'))
        return name


class PaperSizeSelectWidget(forms.Select):
    """Widget مخصص لمقاسات الورق يمرر أبعاد العرض والطول كـ data-width و data-height"""
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value:
            try:
                val_id = int(value.value if hasattr(value, 'value') else value)
                psize = PaperSize.objects.filter(pk=val_id).only('width', 'height').first()
                if psize:
                    option['attrs']['data-width'] = str(psize.width)
                    option['attrs']['data-height'] = str(psize.height)
            except (ValueError, TypeError):
                pass
        return option


class PieceSizeForm(forms.ModelForm):
    """نموذج مقاسات القطع"""

    paper_type = forms.ModelChoiceField(
        queryset=PaperSize.objects.filter(is_active=True).order_by('sort_order', 'name'),
        required=False,
        label=_('مقاس الفرخ الخام الأساسي'),
        widget=PaperSizeSelectWidget(attrs={'class': 'form-select select2-modal'})
    )

    class Meta:
        model = PieceSize
        fields = ['name', 'width', 'height', 'paper_type', 'pieces_per_sheet', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: A4'
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 21.0',
                'step': '0.1',
                'min': '0.1',
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 29.7',
                'step': '0.1',
                'min': '0.1',
            }),
            'pieces_per_sheet': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم مقاس القطع'),
            'width': _('العرض (سم)'),
            'height': _('الطول (سم)'),
            'paper_type': _('مقاس الفرخ الخام الأساسي'),
            'pieces_per_sheet': _('عدد القطع في الفرخ'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }

    def clean_width(self):
        """التحقق من صحة العرض"""
        width = self.cleaned_data.get('width')
        if width and width <= 0:
            raise ValidationError(_('العرض يجب أن يكون أكبر من صفر'))
        return width

    def clean_height(self):
        """التحقق من صحة الطول"""
        height = self.cleaned_data.get('height')
        if height and height <= 0:
            raise ValidationError(_('الطول يجب أن يكون أكبر من صفر'))
        return height

    def clean_pieces_per_sheet(self):
        """التحقق من صحة عدد القطع"""
        pieces = self.cleaned_data.get('pieces_per_sheet')
        if pieces and pieces <= 0:
            raise ValidationError(_('عدد القطع يجب أن يكون أكبر من صفر'))
        return pieces

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            PieceSize.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


class PlateSizeForm(forms.ModelForm):
    """نموذج مقاسات الزنكات"""

    machine = forms.ModelChoiceField(
        queryset=OffsetMachineType.objects.filter(is_active=True).order_by('sort_order', 'name'),
        required=False,
        label=_('الماكينة المرتبطة (اختياري)'),
        widget=forms.Select(attrs={'class': 'form-select select2-modal'}),
        help_text=_('ربط مقاس الزنكة بماكينة أوفست معينة، أو اتركه فارغاً إذا كان مقاس زنك عاماً')
    )

    class Meta:
        model = PlateSize
        fields = ['name', 'code', 'machine', 'width', 'height', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: زنك هايدلبرج ربع فرخ'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: PLT-52',
                'maxlength': '20',
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 45.9',
                'step': '0.1',
                'min': '0.1',
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 52.5',
                'step': '0.1',
                'min': '0.1',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'وصف اختياري لمقاس الزنكة'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم مقاس الزنك'),
            'code': _('رمز المقاس'),
            'machine': _('الماكينة المرتبطة'),
            'width': _('العرض (سم)'),
            'height': _('الطول (سم)'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }

    def clean_width(self):
        """التحقق من صحة العرض"""
        width = self.cleaned_data.get('width')
        if width and width <= 0:
            raise ValidationError(_('العرض يجب أن يكون أكبر من صفر'))
        return width

    def clean_height(self):
        """التحقق من صحة الطول"""
        height = self.cleaned_data.get('height')
        if height and height <= 0:
            raise ValidationError(_('الطول يجب أن يكون أكبر من صفر'))
        return height

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.dimension_type = 'plate'
        if instance.is_default:
            PlateSize.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        if commit:
            instance.save()
        return instance


class ProductTypeForm(forms.ModelForm):
    """نموذج أنواع المنتجات"""

    class Meta:
        model = ProductType
        fields = ['name', 'base_archetype', 'sort_order', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: بروشور 3 بوابة'
            }),
            'base_archetype': forms.Select(attrs={
                'class': 'form-select select2-modal',
            }),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'وصف توضيحي اختياري لنوع المطبوع ومسار تشغيله'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم نوع المطبوع'),
            'base_archetype': _('التصنيف التشغيلي للمحرك'),
            'sort_order': _('رقم الترتيب'),
            'description': _('الوصف'),
            'is_active': _('نشط ومتاح في شاشة التسعير'),
            'is_default': _('صنف افتراضي'),
        }

    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = ProductType.objects.filter(name__iexact=name.strip())
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError(_('هذا الاسم موجود مسبقاً، يرجى اختيار اسم مميز.'))
        return name
        return name

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            ProductType.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


class ProductSizeForm(forms.ModelForm):
    """نموذج مقاسات المطبوعات"""

    class Meta:
        model = ProductSize
        fields = ['name', 'width', 'height', 'sort_order', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: A4 معياري أو كارت شخصي'
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '21.0',
                'step': '0.1',
                'min': '0.1',
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '29.7',
                'step': '0.1',
                'min': '0.1',
            }),
            'sort_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '10'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'وصف توضيحي اختياري للمقاس واستخداماته'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم المقاس'),
            'width': _('العرض (سم)'),
            'height': _('الارتفاع (سم)'),
            'sort_order': _('رقم الترتيب'),
            'description': _('الوصف'),
            'is_active': _('نشط ومتاح في شاشة التسعير'),
            'is_default': _('مقاس افتراضي'),
        }

    def clean_name(self):
        """التحقق من عدم تكرار الاسم"""
        name = self.cleaned_data.get('name')
        if name:
            existing = ProductSize.objects.filter(name__iexact=name.strip())
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError(_('هذا الاسم موجود مسبقاً، يرجى اختيار اسم مميز.'))
        return name

    def clean_width(self):
        """التحقق من صحة العرض"""
        width = self.cleaned_data.get('width')
        if width and width <= 0:
            raise ValidationError(_('العرض يجب أن يكون أكبر من الصفر'))
        return width

    def clean_height(self):
        """التحقق من صحة الارتفاع"""
        height = self.cleaned_data.get('height')
        if height and height <= 0:
            raise ValidationError(_('الارتفاع يجب أن يكون أكبر من الصفر'))
        return height

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        if instance.is_default:
            ProductSize.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        if commit:
            instance.save()
        return instance


# ==================== نماذج ماكينات الطباعة ====================

# ==================== نماذج ماكينات الطباعة ====================

class OffsetMachineTypeForm(forms.ModelForm):
    """نموذج أنواع ماكينات الأوفست"""

    class Meta:
        model = OffsetMachineType
        fields = ['name', 'code', 'manufacturer', 'max_sheet_size', 'colors_capacity', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: هايدلبرج سبيد ماستر 4 ألوان'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: HD-SM52',
                'maxlength': '50',
            }),
            'manufacturer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: هايدلبرج (Heidelberg)'
            }),
            'max_sheet_size': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 37×52 سم'
            }),
            'colors_capacity': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'max': '12',
                'placeholder': '4'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'ملاحظات ومواصفات فنية إضافية لماكينة الأوفست'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم ماكينة الأوفست'),
            'code': _('رمز الماكينة الكودي'),
            'manufacturer': _('الشركة المصنعة'),
            'max_sheet_size': _('أقصى مقاس فرخ (سم)'),
            'colors_capacity': _('عدد أبراج الألوان'),
            'description': _('الوصف والملاحظات'),
            'is_active': _('نشط ومتاح للتشغيل'),
            'is_default': _('الماكينة الافتراضية'),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.machine_category = 'offset'
        if instance.is_default:
            OffsetMachineType.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        if commit:
            instance.save()
        return instance


class DigitalMachineTypeForm(forms.ModelForm):
    """نموذج أنواع ماكينات الديجيتال"""

    class Meta:
        model = DigitalMachineType
        fields = ['name', 'code', 'manufacturer', 'max_sheet_size', 'print_quality', 'is_color', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: زيروكس فيرسانت 280'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: XER-V280',
                'maxlength': '50',
            }),
            'manufacturer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: زيروكس (Xerox)'
            }),
            'max_sheet_size': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 33×66 سم (Banner)'
            }),
            'print_quality': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 2400×2400 DPI'
            }),
            'is_color': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'مواصفات دقة الطباعة وسرعة الماكينة الديجيتال'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم ماكينة الديجيتال'),
            'code': _('رمز الماكينة الكودي'),
            'manufacturer': _('الشركة المصنعة'),
            'max_sheet_size': _('أقصى مقاس شيت (سم)'),
            'print_quality': _('دقة وجودة الطباعة'),
            'is_color': _('تدعم الألوان (ألوان + أسود)'),
            'description': _('الوصف والملاحظات'),
            'is_active': _('نشط ومتاح للتشغيل'),
            'is_default': _('الماكينة الافتراضية'),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.machine_category = 'digital'
        if instance.is_default:
            DigitalMachineType.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        if commit:
            instance.save()
        return instance


# ==================== نماذج مقاسات الفرخ ====================

class OffsetSheetSizeForm(forms.ModelForm):
    """نموذج مقاسات فرخ الأوفست"""

    machine = forms.ModelChoiceField(
        queryset=OffsetMachineType.objects.filter(is_active=True).order_by('sort_order', 'name'),
        required=False,
        label=_('الماكينة المرتبطة (اختياري)'),
        widget=forms.Select(attrs={'class': 'form-select select2-modal'}),
        help_text=_('ربط مقاس الشيت بماكينة أوفست معينة، أو اتركه فارغاً إذا كان مقاس تشغيل عاماً')
    )

    class Meta:
        model = OffsetSheetSize
        fields = ['name', 'code', 'machine', 'width', 'height', 'description', 'is_active', 'is_default', 'is_custom_size']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ربع فرخ 35×50'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: Q-35x50',
                'maxlength': '20',
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 35.0',
                'step': '0.1',
                'min': '0.1',
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 50.0',
                'step': '0.1',
                'min': '0.1',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'وصف اختياري لمقاس الشيت واستخداماته'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_custom_size': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم مقاس الشيت'),
            'code': _('رمز المقاس'),
            'machine': _('ماكينة الأوفست المرتبطة'),
            'width': _('العرض (سم)'),
            'height': _('الطول (سم)'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
            'is_custom_size': _('مقاس تشغيل مخصص'),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.dimension_type = 'offset_sheet'
        if instance.is_default:
            OffsetSheetSize.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        if commit:
            instance.save()
        return instance


class DigitalSheetSizeForm(forms.ModelForm):
    """نموذج مقاسات فرخ الديجيتال"""

    machine = forms.ModelChoiceField(
        queryset=DigitalMachineType.objects.filter(is_active=True).order_by('sort_order', 'name'),
        required=False,
        label=_('الماكينة المرتبطة (اختياري)'),
        widget=forms.Select(attrs={'class': 'form-select select2-modal'}),
        help_text=_('ربط مقاس الشيت بماكينة ديجيتال معينة، أو اتركه فارغاً إذا كان مقاساً عاماً')
    )

    class Meta:
        model = DigitalSheetSize
        fields = ['name', 'code', 'machine', 'width', 'height', 'description', 'is_active', 'is_default', 'is_custom_size']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: A3+ قياسي'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: A3P-33x48',
                'maxlength': '20',
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 32.9',
                'step': '0.1',
                'min': '0.1',
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 48.3',
                'step': '0.1',
                'min': '0.1',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'وصف اختياري لمقاس الشيت واستخداماته'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_custom_size': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم مقاس الشيت'),
            'code': _('رمز المقاس'),
            'machine': _('ماكينة الديجيتال المرتبطة'),
            'width': _('العرض (سم)'),
            'height': _('الطول (سم)'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
            'is_custom_size': _('مقاس تشغيل مخصص'),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.dimension_type = 'digital_sheet'
        if instance.is_default:
            DigitalSheetSize.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        if commit:
            instance.save()
        return instance
