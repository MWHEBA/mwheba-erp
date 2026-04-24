"""
نماذج الحضور
"""
from django import forms
from datetime import datetime, timedelta
from ..models import Attendance, Shift, RamadanSettings, AttendancePenalty


class SmartFloatNumberInput(forms.NumberInput):
    """NumberInput يعرض الأرقام بدون أصفار زيادة (8 بدل 8.00، 7.5 بدل 7.50)"""

    def format_value(self, value):
        if value is None or value == '':
            return value
        try:
            from decimal import Decimal
            val = Decimal(str(value))
            return str(int(val)) if val == int(val) else str(val.normalize())
        except Exception:
            return value


class AttendanceForm(forms.ModelForm):
    """نموذج تسجيل الحضور"""
    
    class Meta:
        model = Attendance
        fields = ['employee', 'date', 'shift', 'check_in', 'check_out', 'notes']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.TextInput(attrs={
                'class': 'form-control',
                'data-date-picker': True,
                'placeholder': 'اختر تاريخ الحضور...'
            }),
            'shift': forms.Select(attrs={'class': 'form-select'}),
            'check_in': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'check_out': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class ShiftForm(forms.ModelForm):
    """نموذج الورديات"""
    
    class Meta:
        model = Shift
        fields = [
            'name', 'shift_type', 'start_time', 'end_time',
            'ramadan_start_time', 'ramadan_end_time',
            'grace_period_in', 'grace_period_out', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: الوردية الصباحية'}),
            'shift_type': forms.Select(attrs={'class': 'form-select'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'ramadan_start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'ramadan_end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'grace_period_in': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'grace_period_out': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'اسم الوردية',
            'shift_type': 'نوع الوردية',
            'start_time': 'وقت البداية',
            'end_time': 'وقت النهاية',
            'ramadan_start_time': 'وقت بداية رمضان',
            'ramadan_end_time': 'وقت نهاية رمضان',
            'grace_period_in': 'فترة السماح للحضور (دقائق)',
            'grace_period_out': 'فترة السماح للانصراف (دقائق)',
            'is_active': 'نشط',
        }
        help_texts = {
            'grace_period_in': 'عدد الدقائق المسموح بها للتأخير في الحضور',
            'grace_period_out': 'عدد الدقائق المسموح بها للتأخير في الانصراف',
            'ramadan_start_time': 'اتركه فارغاً لاستخدام وقت البداية العادي في رمضان',
            'ramadan_end_time': 'اتركه فارغاً لاستخدام وقت النهاية العادي في رمضان',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        """التحقق من صحة البيانات"""
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if start_time and end_time:
            start = datetime.combine(datetime.today(), start_time)
            end = datetime.combine(datetime.today(), end_time)
            if end <= start:
                end += timedelta(days=1)

        return cleaned_data


class RamadanSettingsForm(forms.ModelForm):
    """نموذج إعدادات رمضان"""

    class Meta:
        model = RamadanSettings
        fields = ['hijri_year', 'start_date', 'end_date', 'permission_max_count', 'permission_max_hours']
        widgets = {
            'hijri_year': forms.NumberInput(attrs={'class': 'form-control', 'min': '1400', 'placeholder': 'مثال: 1446'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'permission_max_count': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'permission_max_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.5'}),
        }
        labels = {
            'hijri_year': 'السنة الهجرية',
            'start_date': 'تاريخ بداية رمضان',
            'end_date': 'تاريخ نهاية رمضان',
            'permission_max_count': 'الحد الأقصى لعدد الأذونات',
            'permission_max_hours': 'الحد الأقصى لساعات الأذونات',
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date <= start_date:
            raise forms.ValidationError('تاريخ النهاية يجب أن يكون بعد تاريخ البداية')

        return cleaned_data


class AttendancePenaltyForm(forms.ModelForm):
    """نموذج جزاءات الحضور"""

    class Meta:
        model = AttendancePenalty
        fields = ['name', 'max_minutes', 'penalty_days', 'is_active', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مثال: تأخير خفيف'}),
            'max_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'penalty_days': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
        labels = {
            'name': 'اسم الجزاء',
            'max_minutes': 'الحد الأقصى للدقائق',
            'penalty_days': 'قيمة الجزاء (أيام)',
            'is_active': 'نشط',
            'order': 'الترتيب',
        }
        help_texts = {
            'max_minutes': 'أدخل 0 للنطاق المفتوح (يطبق على ما يتجاوز كل النطاقات)',
            'penalty_days': 'يمكن إدخال أرقام عشرية مثل 0.5 أو 1.5',
        }


class AttendanceSummaryApprovalForm(forms.ModelForm):
    """فورم اعتماد ملخص الحضور مع إمكانية تعديل معامل الغياب"""
    
    absence_multiplier = forms.ChoiceField(
        choices=[
            ('1.0', 'عادي (×1)'),
            ('2.0', 'مضاعف (×2)'),
            ('3.0', 'ثلاثي (×3)'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='معامل الغياب'
    )
    
    class Meta:
        from ..models import AttendanceSummary
        model = AttendanceSummary
        fields = ['absence_multiplier', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
