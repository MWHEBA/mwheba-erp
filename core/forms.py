from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
import datetime
import pytz


class SearchForm(forms.Form):
    """
    نموذج البحث العام
    """
    query = forms.CharField(required=False, label=_('بحث'), widget=forms.TextInput(attrs={'placeholder': _('أدخل كلمة البحث...')}))
    category = forms.CharField(required=False, label=_('التصنيف'))
    date_from = forms.DateField(required=False, label=_('من تاريخ'), widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False, label=_('إلى تاريخ'), widget=forms.DateInput(attrs={'type': 'date'}))
    sort_by = forms.ChoiceField(required=False, label=_('ترتيب حسب'), choices=[
        ('name', _('الاسم')),
        ('date', _('التاريخ')),
        ('price', _('السعر')),
    ])
    
    def clean(self):
        """
        التحقق من صحة نطاق التاريخ
        """
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        # التحقق من صحة نطاق التاريخ إذا تم تحديد كلا التاريخين
        if date_from and date_to and date_from > date_to:
            self.add_error('date_to', _('تاريخ النهاية يجب أن يكون بعد تاريخ البداية'))
        
        return cleaned_data


class DateRangeForm(forms.Form):
    """
    نموذج نطاق التاريخ
    """
    # صفة لتحديد ما إذا كان النموذج يسمح بالتواريخ المستقبلية
    allows_future_dates = True
    
    start_date = forms.DateField(required=False, label=_('تاريخ البداية'), widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(required=False, label=_('تاريخ النهاية'), widget=forms.DateInput(attrs={'type': 'date'}))
    preset = forms.ChoiceField(required=False, label=_('فترة محددة مسبقًا'), choices=[
        ('', _('اختر الفترة')),
        ('today', _('اليوم')),
        ('yesterday', _('أمس')),
        ('this_week', _('هذا الأسبوع')),
        ('this_month', _('هذا الشهر')),
        ('last_month', _('الشهر الماضي')),
        ('this_year', _('هذا العام')),
    ])
    
    def clean(self):
        """
        التحقق من صحة نطاق التاريخ والتعامل مع الفترات المحددة مسبقًا
        """
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        preset = cleaned_data.get('preset')
        
        # التعامل مع الفترات المحددة مسبقًا
        if preset:
            today = timezone.now().date()
            
            if preset == 'today':
                # اليوم
                start_date = today
                end_date = today
            elif preset == 'yesterday':
                # أمس
                yesterday = today - datetime.timedelta(days=1)
                start_date = yesterday
                end_date = yesterday
            elif preset == 'this_week':
                # هذا الأسبوع (من الأحد إلى السبت)
                start_date = today - datetime.timedelta(days=today.weekday())
                end_date = start_date + datetime.timedelta(days=6)
            elif preset == 'this_month':
                # هذا الشهر
                start_date = today.replace(day=1)
                # آخر يوم في الشهر
                next_month = today.replace(day=28) + datetime.timedelta(days=4)
                end_date = next_month - datetime.timedelta(days=next_month.day)
            elif preset == 'last_month':
                # الشهر الماضي
                first_day_this_month = today.replace(day=1)
                last_day_last_month = first_day_this_month - datetime.timedelta(days=1)
                start_date = last_day_last_month.replace(day=1)
                end_date = last_day_last_month
            elif preset == 'this_year':
                # هذا العام
                start_date = today.replace(month=1, day=1)
                end_date = today.replace(month=12, day=31)
            
            # تحديث البيانات النظيفة
            cleaned_data['start_date'] = start_date
            cleaned_data['end_date'] = end_date
        
        # التحقق من صحة نطاق التاريخ
        if start_date and end_date and start_date > end_date:
            self.add_error('end_date', _('تاريخ النهاية يجب أن يكون بعد تاريخ البداية'))
        
        # التحقق من عدم وجود تواريخ مستقبلية إذا كان غير مسموح بها
        if not self.allows_future_dates:
            today = timezone.now().date()
            if start_date and start_date > today:
                self.add_error('start_date', _('لا يمكن تحديد تاريخ في المستقبل'))
            if end_date and end_date > today:
                self.add_error('end_date', _('لا يمكن تحديد تاريخ في المستقبل'))
        
        return cleaned_data


class ImportForm(forms.Form):
    """
    نموذج استيراد البيانات
    """
    file = forms.FileField(label=_('ملف للاستيراد'), help_text=_('اختر ملف Excel أو CSV للاستيراد'))
    file_type = forms.ChoiceField(label=_('نوع الملف'), choices=[
        ('excel', _('Excel')),
        ('csv', _('CSV')),
    ])
    model_type = forms.ChoiceField(label=_('نوع البيانات'), choices=[
        ('product', _('المنتجات')),
        ('customer', _('العملاء')),
        ('supplier', _('الموردين')),
        ('sale', _('المبيعات')),
        ('purchase', _('المشتريات')),
    ])
    
    def clean_file(self):
        """
        التحقق من نوع الملف
        """
        file = self.cleaned_data.get('file')
        file_type = self.cleaned_data.get('file_type')
        
        if file:
            # التحقق من امتداد الملف
            if file_type == 'excel' and not file.name.endswith(('.xlsx', '.xls')):
                raise ValidationError(_('يرجى تحميل ملف Excel صالح بامتداد .xlsx أو .xls'))
            elif file_type == 'csv' and not file.name.endswith('.csv'):
                raise ValidationError(_('يرجى تحميل ملف CSV صالح بامتداد .csv'))
        
        return file


class ExportForm(forms.Form):
    """
    نموذج تصدير البيانات
    """
    file_type = forms.ChoiceField(label=_('نوع الملف'), choices=[
        ('excel', _('Excel')),
        ('pdf', _('PDF')),
        ('csv', _('CSV')),
    ])
    model_type = forms.ChoiceField(label=_('نوع البيانات'), choices=[
        ('product', _('المنتجات')),
        ('customer', _('العملاء')),
        ('supplier', _('الموردين')),
        ('sale', _('المبيعات')),
        ('purchase', _('المشتريات')),
    ])
    date_from = forms.DateField(required=False, label=_('من تاريخ'), widget=forms.DateInput(attrs={'type': 'date'}))
    date_to = forms.DateField(required=False, label=_('إلى تاريخ'), widget=forms.DateInput(attrs={'type': 'date'}))
    
    def clean(self):
        """
        التحقق من صحة نطاق التاريخ
        """
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        # التحقق من صحة نطاق التاريخ إذا تم تحديد كلا التاريخين
        if date_from and date_to and date_from > date_to:
            self.add_error('date_to', _('تاريخ النهاية يجب أن يكون بعد تاريخ البداية'))
        
        # التحقق من صحة نوع الملف
        file_type = cleaned_data.get('file_type')
        if file_type not in ['excel', 'pdf', 'csv']:
            self.add_error('file_type', _('نوع ملف غير صالح'))
        
        return cleaned_data


class SettingsForm(forms.Form):
    """
    نموذج إعدادات النظام
    """
    site_name = forms.CharField(label=_('اسم الموقع'), max_length=100)
    site_logo = forms.ImageField(label=_('شعار الموقع'), required=False)
    currency = forms.ChoiceField(label=_('العملة'), choices=[
        ('EGP', _('جنيه مصري')),
        ('USD', _('دولار أمريكي')),
        ('SAR', _('ريال سعودي')),
        ('AED', _('درهم إماراتي')),
        ('KWD', _('دينار كويتي')),
    ])
    decimal_places = forms.IntegerField(label=_('عدد المنازل العشرية'), min_value=0, max_value=4)
    tax_rate = forms.DecimalField(label=_('نسبة الضريبة (%)'), min_value=0, max_value=100, decimal_places=2)
    enable_dark_mode = forms.BooleanField(label=_('تفعيل الوضع الداكن'), required=False)
    timezone = forms.ChoiceField(label=_('المنطقة الزمنية'), choices=[])
    language = forms.ChoiceField(label=_('اللغة'), choices=[
        ('ar', _('العربية')),
        ('en', _('الإنجليزية')),
    ])
    items_per_page = forms.IntegerField(label=_('عدد العناصر في الصفحة'), min_value=5, max_value=100)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # تعبئة قائمة المناطق الزمنية
        timezone_choices = [(tz, tz) for tz in pytz.common_timezones]
        self.fields['timezone'].choices = timezone_choices
    
    def clean_tax_rate(self):
        """
        التحقق من صحة نسبة الضريبة
        """
        tax_rate = self.cleaned_data.get('tax_rate')
        if tax_rate is not None and (tax_rate < 0 or tax_rate > 100):
            raise ValidationError(_('نسبة الضريبة يجب أن تكون بين 0 و 100'))
        return tax_rate
    
    def clean_decimal_places(self):
        """
        التحقق من صحة عدد المنازل العشرية
        """
        decimal_places = self.cleaned_data.get('decimal_places')
        if decimal_places is not None and (decimal_places < 0 or decimal_places > 4):
            raise ValidationError(_('عدد المنازل العشرية يجب أن يكون بين 0 و 4'))
        return decimal_places
    
    def clean_timezone(self):
        """
        التحقق من صحة المنطقة الزمنية
        """
        timezone_str = self.cleaned_data.get('timezone')
        if timezone_str:
            try:
                pytz.timezone(timezone_str)
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValidationError(_('منطقة زمنية غير صالحة'))
        return timezone_str 