"""
نماذج إدارة الإعدادات والإعدادات المتقدمة الموحدة
Unified settings and advanced settings forms
"""

from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from ..models import (
    PaperType, PaperSize, PaperWeight, PaperOrigin,
    PrintDirection, PrintSide, CoatingType, FinishingType,
    PieceSize, PlateSize, ProductType, ProductSize, VATSetting,
    OffsetMachineType, DigitalMachineType, OffsetSheetSize, DigitalSheetSize
)
from users.models import User


# ==================== نماذج أنواع الورق ====================

class PaperTypeForm(forms.ModelForm):
    """نموذج أنواع الورق"""

    class Meta:
        model = PaperType
        fields = ['name', 'description', 'is_active', 'is_default']
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
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
                'max': '500',
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


# ==================== نماذج اتجاهات الطباعة ====================

class PrintDirectionForm(forms.ModelForm):
    """نموذج اتجاهات الطباعة"""

    class Meta:
        model = PrintDirection
        fields = ['name', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: طولي'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لاتجاه الطباعة'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم الاتجاه'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            PrintDirection.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


# ==================== نماذج جوانب الطباعة ====================

class PrintSideForm(forms.ModelForm):
    """نموذج جوانب الطباعة"""

    class Meta:
        model = PrintSide
        fields = ['name', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: وجه واحد'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لجانب الطباعة'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم الجانب'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            PrintSide.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
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


class PieceSizeForm(forms.ModelForm):
    """نموذج مقاسات القطع"""

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
            'paper_type': forms.Select(attrs={'class': 'form-control'}),
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
            'paper_type': _('نوع الورق'),
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

    class Meta:
        model = PlateSize
        fields = ['name', 'width', 'height', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: زنك صغير'
            }),
            'width': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 30.0',
                'step': '0.1',
                'min': '0.1',
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 40.0',
                'step': '0.1',
                'min': '0.1',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم مقاس الزنك'),
            'width': _('العرض (سم)'),
            'height': _('الطول (سم)'),
            'is_active': _('نشط'),
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


class ProductTypeForm(forms.ModelForm):
    """نموذج أنواع المنتجات"""

    class Meta:
        model = ProductType
        fields = ['name', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: كتيب'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع المنتج'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
                raise ValidationError(_('هذا الاسم موجود مسبقاً'))
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
                'min': '0.1',
            }),
            'height': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 29.7',
                'step': '0.1',
                'min': '0.1',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'وصف اختياري لمقاس المنتج'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم مقاس المنتج'),
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
            ProductSize.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


class VATSettingForm(forms.ModelForm):
    """نموذج إعدادات ضريبة القيمة المضافة"""

    class Meta:
        model = VATSetting
        fields = ['is_enabled', 'percentage', 'description']
        widgets = {
            'is_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'placeholder': 'مثال: 14.00'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لإعداد الضريبة'
            }),
        }
        labels = {
            'is_enabled': _('مفعل'),
            'percentage': _('النسبة المئوية'),
            'description': _('الوصف'),
        }

    def clean_percentage(self):
        """التحقق من صحة النسبة المئوية"""
        percentage = self.cleaned_data.get('percentage')
        if percentage is not None:
            if percentage < 0 or percentage > 100:
                raise ValidationError(_('النسبة المئوية يجب أن تكون بين 0 و 100'))
        return percentage

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # جعل الوصف اختياري
        self.fields['description'].required = False
        
        # تعيين المستخدم المنشئ إذا كان النموذج جديد
        if user and not self.instance.pk:
            self.instance.created_by = user


# ==================== نماذج ماكينات الطباعة ====================

class OffsetMachineTypeForm(forms.ModelForm):
    """نموذج أنواع ماكينات الأوفست"""

    class Meta:
        model = OffsetMachineType
        fields = ['name', 'code', 'manufacturer', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ماكينة أوفست 4 ألوان'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: OFF4C',
                'maxlength': '20',
            }),
            'manufacturer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: هايدلبرج'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع الماكينة'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم نوع الماكينة'),
            'code': _('رمز الماكينة'),
            'manufacturer': _('الشركة المصنعة'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            OffsetMachineType.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


class DigitalMachineTypeForm(forms.ModelForm):
    """نموذج أنواع ماكينات الديجيتال"""

    class Meta:
        model = DigitalMachineType
        fields = ['name', 'code', 'manufacturer', 'description', 'is_active', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: ماكينة ديجيتال ملونة'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: DIG4C',
                'maxlength': '20',
            }),
            'manufacturer': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: زيروكس'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لنوع الماكينة'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم نوع الماكينة'),
            'code': _('رمز الماكينة'),
            'manufacturer': _('الشركة المصنعة'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
        }

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            DigitalMachineType.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


# ==================== نماذج مقاسات الفرخ ====================

class OffsetSheetSizeForm(forms.ModelForm):
    """نموذج مقاسات فرخ الأوفست"""

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
                'placeholder': 'مثال: FULL',
                'maxlength': '20',
            }),
            'width_cm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 70.0',
                'step': '0.1',
                'min': '0.1',
            }),
            'height_cm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 100.0',
                'step': '0.1',
                'min': '0.1',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لمقاس الفرخ'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_custom_size': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم مقاس الفرخ'),
            'code': _('رمز المقاس'),
            'width_cm': _('العرض (سم)'),
            'height_cm': _('الطول (سم)'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
            'is_custom_size': _('مقاس مخصص'),
        }

    def save(self, commit=True):
        """حفظ النموذج مع إدارة الافتراضي تلقائياً"""
        instance = super().save(commit=False)
        
        # إذا تم تعيين هذا العنصر كافتراضي، إلغاء الافتراضي من العناصر الأخرى
        if instance.is_default:
            OffsetSheetSize.objects.filter(is_default=True).exclude(pk=instance.pk).update(is_default=False)
        
        if commit:
            instance.save()
        return instance


class DigitalSheetSizeForm(forms.ModelForm):
    """نموذج مقاسات فرخ الديجيتال"""

    class Meta:
        model = DigitalSheetSize
        fields = ['name', 'code', 'width_cm', 'height_cm', 'description', 'is_active', 'is_default', 'is_custom_size']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: A3+'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: A3P',
                'maxlength': '20',
            }),
            'width_cm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 32.9',
                'step': '0.1',
                'min': '0.1',
            }),
            'height_cm': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'مثال: 48.3',
                'step': '0.1',
                'min': '0.1',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'وصف اختياري لمقاس الفرخ'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_custom_size': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': _('اسم مقاس الفرخ'),
            'code': _('رمز المقاس'),
            'width_cm': _('العرض (سم)'),
            'height_cm': _('الطول (سم)'),
            'description': _('الوصف'),
            'is_active': _('نشط'),
            'is_default': _('افتراضي'),
            'is_custom_size': _('مقاس مخصص'),
        }
