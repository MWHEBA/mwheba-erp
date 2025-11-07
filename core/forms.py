from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
import datetime
import pytz
from .models import NotificationPreference


class SearchForm(forms.Form):
    """
    نموذج البحث العام
    """

    query = forms.CharField(
        required=False,
        label=_("بحث"),
        widget=forms.TextInput(attrs={"placeholder": _("أدخل كلمة البحث...")}),
    )
    category = forms.CharField(required=False, label=_("التصنيف"))
    date_from = forms.DateField(
        required=False,
        label=_("من تاريخ"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "من تاريخ..."
        }),
    )
    date_to = forms.DateField(
        required=False,
        label=_("إلى تاريخ"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "إلى تاريخ..."
        }),
    )
    sort_by = forms.ChoiceField(
        required=False,
        label=_("ترتيب حسب"),
        choices=[
            ("name", _("الاسم")),
            ("date", _("التاريخ")),
            ("price", _("السعر")),
        ],
    )

    def clean(self):
        """
        التحقق من صحة نطاق التاريخ
        """
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")

        # التحقق من صحة نطاق التاريخ إذا تم تحديد كلا التاريخين
        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", _("تاريخ النهاية يجب أن يكون بعد تاريخ البداية"))

        return cleaned_data


class DateRangeForm(forms.Form):
    """
    نموذج نطاق التاريخ
    """

    # صفة لتحديد ما إذا كان النموذج يسمح بالتواريخ المستقبلية
    allows_future_dates = True

    start_date = forms.DateField(
        required=False,
        label=_("تاريخ البداية"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "تاريخ البداية..."
        }),
    )
    end_date = forms.DateField(
        required=False,
        label=_("تاريخ النهاية"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "تاريخ النهاية..."
        }),
    )
    preset = forms.ChoiceField(
        required=False,
        label=_("فترة محددة مسبقًا"),
        choices=[
            ("", _("اختر الفترة")),
            ("today", _("اليوم")),
            ("yesterday", _("أمس")),
            ("this_week", _("هذا الأسبوع")),
            ("this_month", _("هذا الشهر")),
            ("last_month", _("الشهر الماضي")),
            ("this_year", _("هذا العام")),
        ],
    )

    def clean(self):
        """
        التحقق من صحة نطاق التاريخ والتعامل مع الفترات المحددة مسبقًا
        """
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        preset = cleaned_data.get("preset")

        # التعامل مع الفترات المحددة مسبقًا
        if preset:
            today = timezone.now().date()

            if preset == "today":
                # اليوم
                start_date = today
                end_date = today
            elif preset == "yesterday":
                # أمس
                yesterday = today - datetime.timedelta(days=1)
                start_date = yesterday
                end_date = yesterday
            elif preset == "this_week":
                # هذا الأسبوع (من الأحد إلى السبت)
                start_date = today - datetime.timedelta(days=today.weekday())
                end_date = start_date + datetime.timedelta(days=6)
            elif preset == "this_month":
                # هذا الشهر
                start_date = today.replace(day=1)
                # آخر يوم في الشهر
                next_month = today.replace(day=28) + datetime.timedelta(days=4)
                end_date = next_month - datetime.timedelta(days=next_month.day)
            elif preset == "last_month":
                # الشهر الماضي
                first_day_this_month = today.replace(day=1)
                last_day_last_month = first_day_this_month - datetime.timedelta(days=1)
                start_date = last_day_last_month.replace(day=1)
                end_date = last_day_last_month
            elif preset == "this_year":
                # هذا العام
                start_date = today.replace(month=1, day=1)
                end_date = today.replace(month=12, day=31)

            # تحديث البيانات النظيفة
            cleaned_data["start_date"] = start_date
            cleaned_data["end_date"] = end_date

        # التحقق من صحة نطاق التاريخ
        if start_date and end_date and start_date > end_date:
            self.add_error("end_date", _("تاريخ النهاية يجب أن يكون بعد تاريخ البداية"))

        # التحقق من عدم وجود تواريخ مستقبلية إذا كان غير مسموح بها
        if not self.allows_future_dates:
            today = timezone.now().date()
            if start_date and start_date > today:
                self.add_error("start_date", _("لا يمكن تحديد تاريخ في المستقبل"))
            if end_date and end_date > today:
                self.add_error("end_date", _("لا يمكن تحديد تاريخ في المستقبل"))

        return cleaned_data


class ImportForm(forms.Form):
    """
    نموذج استيراد البيانات
    """

    file = forms.FileField(
        label=_("ملف للاستيراد"), help_text=_("اختر ملف Excel أو CSV للاستيراد")
    )
    file_type = forms.ChoiceField(
        label=_("نوع الملف"),
        choices=[
            ("excel", _("Excel")),
            ("csv", _("CSV")),
        ],
    )
    model_type = forms.ChoiceField(
        label=_("نوع البيانات"),
        choices=[
            ("product", _("المنتجات")),
            ("customer", _("العملاء")),
            ("supplier", _("الموردين")),
            ("sale", _("المبيعات")),
            ("purchase", _("المشتريات")),
        ],
    )

    def clean_file(self):
        """
        التحقق من نوع الملف
        """
        file = self.cleaned_data.get("file")
        file_type = self.cleaned_data.get("file_type")

        if file:
            # التحقق من امتداد الملف
            if file_type == "excel" and not file.name.endswith((".xlsx", ".xls")):
                raise ValidationError(
                    _("يرجى تحميل ملف Excel صالح بامتداد .xlsx أو .xls")
                )
            elif file_type == "csv" and not file.name.endswith(".csv"):
                raise ValidationError(_("يرجى تحميل ملف CSV صالح بامتداد .csv"))

        return file


class ExportForm(forms.Form):
    """
    نموذج تصدير البيانات
    """

    file_type = forms.ChoiceField(
        label=_("نوع الملف"),
        choices=[
            ("excel", _("Excel")),
            ("pdf", _("PDF")),
            ("csv", _("CSV")),
        ],
    )
    model_type = forms.ChoiceField(
        label=_("نوع البيانات"),
        choices=[
            ("product", _("المنتجات")),
            ("customer", _("العملاء")),
            ("supplier", _("الموردين")),
            ("sale", _("المبيعات")),
            ("purchase", _("المشتريات")),
        ],
    )
    date_from = forms.DateField(
        required=False,
        label=_("من تاريخ"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "من تاريخ..."
        }),
    )
    date_to = forms.DateField(
        required=False,
        label=_("إلى تاريخ"),
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "data-date-picker": True,
            "placeholder": "إلى تاريخ..."
        }),
    )

    def clean(self):
        """
        التحقق من صحة نطاق التاريخ
        """
        cleaned_data = super().clean()
        date_from = cleaned_data.get("date_from")
        date_to = cleaned_data.get("date_to")

        # التحقق من صحة نطاق التاريخ إذا تم تحديد كلا التاريخين
        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", _("تاريخ النهاية يجب أن يكون بعد تاريخ البداية"))

        # التحقق من صحة نوع الملف
        file_type = cleaned_data.get("file_type")
        if file_type not in ["excel", "pdf", "csv"]:
            self.add_error("file_type", _("نوع ملف غير صالح"))

        return cleaned_data


class SettingsForm(forms.Form):
    """
    نموذج إعدادات النظام
    """

    site_name = forms.CharField(label=_("اسم الموقع"), max_length=100)
    site_logo = forms.ImageField(label=_("شعار الموقع"), required=False)
    currency = forms.ChoiceField(
        label=_("العملة"),
        choices=[
            ("EGP", _("جنيه مصري")),
            ("USD", _("دولار أمريكي")),
            ("SAR", _("ريال سعودي")),
            ("AED", _("درهم إماراتي")),
            ("KWD", _("دينار كويتي")),
        ],
    )
    decimal_places = forms.IntegerField(
        label=_("عدد المنازل العشرية"), min_value=0, max_value=4
    )
    tax_rate = forms.DecimalField(
        label=_("نسبة الضريبة (%)"), min_value=0, max_value=100, decimal_places=2
    )
    enable_dark_mode = forms.BooleanField(label=_("تفعيل الوضع الداكن"), required=False)
    timezone = forms.ChoiceField(label=_("المنطقة الزمنية"), choices=[])
    language = forms.ChoiceField(
        label=_("اللغة"),
        choices=[
            ("ar", _("العربية")),
            ("en", _("الإنجليزية")),
        ],
    )
    items_per_page = forms.IntegerField(
        label=_("عدد العناصر في الصفحة"), min_value=5, max_value=100
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # تعبئة قائمة المناطق الزمنية
        timezone_choices = [(tz, tz) for tz in pytz.common_timezones]
        self.fields["timezone"].choices = timezone_choices

    def clean_tax_rate(self):
        """
        التحقق من صحة نسبة الضريبة
        """
        tax_rate = self.cleaned_data.get("tax_rate")
        if tax_rate is not None and (tax_rate < 0 or tax_rate > 100):
            raise ValidationError(_("نسبة الضريبة يجب أن تكون بين 0 و 100"))
        return tax_rate

    def clean_decimal_places(self):
        """
        التحقق من صحة عدد المنازل العشرية
        """
        decimal_places = self.cleaned_data.get("decimal_places")
        if decimal_places is not None and (decimal_places < 0 or decimal_places > 4):
            raise ValidationError(_("عدد المنازل العشرية يجب أن يكون بين 0 و 4"))
        return decimal_places

    def clean_timezone(self):
        """
        التحقق من صحة المنطقة الزمنية
        """
        timezone_str = self.cleaned_data.get("timezone")
        if timezone_str:
            try:
                pytz.timezone(timezone_str)
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValidationError(_("منطقة زمنية غير صالحة"))
        return timezone_str


class SystemSettingsForm(forms.Form):
    """
    نموذج إعدادات النظام الشامل
    """
    # إعدادات عامة
    language = forms.ChoiceField(
        label='اللغة الافتراضية',
        choices=[('ar', 'العربية'), ('en', 'English')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    timezone = forms.ChoiceField(
        label='المنطقة الزمنية',
        choices=[
            ('Africa/Cairo', 'القاهرة (GMT+2)'),
            ('Asia/Riyadh', 'الرياض (GMT+3)'),
            ('UTC', 'التوقيت العالمي (UTC)')
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date_format = forms.ChoiceField(
        label='صيغة التاريخ',
        choices=[
            ('d/m/Y', 'DD/MM/YYYY'),
            ('Y-m-d', 'YYYY-MM-DD'),
            ('m/d/Y', 'MM/DD/YYYY')
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # إعدادات الفواتير والمالية (منقولة من company_settings)
    invoice_prefix = forms.CharField(
        label='بادئة الفواتير',
        max_length=10,
        initial='INV-',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'INV-'})
    )
    default_currency = forms.CharField(
        label='العملة الافتراضية',
        max_length=10,
        initial='ج.م',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ج.م'})
    )
    default_tax_rate = forms.DecimalField(
        label='نسبة الضريبة الافتراضية (%)',
        min_value=0,
        max_value=100,
        initial=14,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    invoice_notes = forms.CharField(
        label='ملاحظات الفاتورة الافتراضية',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )
    
    # إعدادات النظام
    maintenance_mode = forms.BooleanField(
        label='وضع الصيانة',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    session_timeout = forms.IntegerField(
        label='مدة الجلسة (بالدقائق)',
        min_value=5,
        max_value=10080,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    backup_frequency = forms.ChoiceField(
        label='تكرار النسخ الاحتياطي',
        choices=[
            ('daily', 'يومي'),
            ('weekly', 'أسبوعي'),
            ('monthly', 'شهري'),
            ('manual', 'يدوي')
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    # إعدادات الأمان
    enable_two_factor = forms.BooleanField(
        label='تفعيل المصادقة الثنائية',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    password_policy = forms.ChoiceField(
        label='سياسة كلمة المرور',
        choices=[
            ('simple', 'بسيط'),
            ('medium', 'متوسط'),
            ('strong', 'قوي')
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    failed_login_attempts = forms.IntegerField(
        label='الحد الأقصى لمحاولات تسجيل الدخول الفاشلة',
        min_value=3,
        max_value=10,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    account_lockout_time = forms.IntegerField(
        label='مدة قفل الحساب بعد محاولات فاشلة (بالدقائق)',
        min_value=5,
        max_value=1440,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    
    # إعدادات الإيميل
    email_host = forms.CharField(
        label='SMTP Host',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'mail.example.com'})
    )
    email_port = forms.IntegerField(
        label='SMTP Port',
        required=False,
        min_value=1,
        max_value=65535,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '587'})
    )
    email_username = forms.CharField(
        label='Email Username',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'user@example.com'})
    )
    email_password = forms.CharField(
        label='Email Password',
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '••••••••'})
    )
    email_encryption = forms.ChoiceField(
        label='نوع التشفير',
        choices=[
            ('none', 'بدون تشفير'),
            ('tls', 'TLS (Port 587)'),
            ('ssl', 'SSL (Port 465)')
        ],
        initial='tls',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    email_from = forms.EmailField(
        label='البريد الافتراضي للإرسال',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'noreply@example.com'})
    )


class NotificationSettingsForm(forms.ModelForm):
    """
    نموذج إعدادات الإشعارات
    """
    
    class Meta:
        model = NotificationPreference
        exclude = ['user', 'created_at', 'updated_at']
        widgets = {
            'daily_summary_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'do_not_disturb_start': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'do_not_disturb_end': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'email_for_notifications': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'example@email.com'}),
            'phone_for_notifications': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+20 xxx xxx xxxx'}),
            'inventory_check_frequency': forms.Select(attrs={'class': 'form-select'}),
            'invoice_check_frequency': forms.Select(attrs={'class': 'form-select'}),
            'auto_delete_after_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '365'}),
            'auto_archive_after_months': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '24'}),
            'invoice_due_days_before': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '30'}),
            'invoice_overdue_days_after': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '30'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # تخصيص الـ labels والـ help_text
        for field_name, field in self.fields.items():
            # إضافة class للـ checkboxes
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})
    
    def clean(self):
        """
        التحقق من صحة البيانات
        """
        cleaned_data = super().clean()
        
        # التحقق من البريد الإلكتروني إذا تم تفعيل إشعارات البريد
        notify_email = cleaned_data.get('notify_email')
        email_for_notifications = cleaned_data.get('email_for_notifications')
        
        if notify_email and not email_for_notifications:
            self.add_error('email_for_notifications', _('يجب إدخال البريد الإلكتروني لتفعيل إشعارات البريد'))
        
        # التحقق من رقم الهاتف إذا تم تفعيل إشعارات SMS
        notify_sms = cleaned_data.get('notify_sms')
        phone_for_notifications = cleaned_data.get('phone_for_notifications')
        
        if notify_sms and not phone_for_notifications:
            self.add_error('phone_for_notifications', _('يجب إدخال رقم الهاتف لتفعيل إشعارات SMS'))
        
        # التحقق من أوقات عدم الإزعاج
        enable_do_not_disturb = cleaned_data.get('enable_do_not_disturb')
        do_not_disturb_start = cleaned_data.get('do_not_disturb_start')
        do_not_disturb_end = cleaned_data.get('do_not_disturb_end')
        
        if enable_do_not_disturb:
            if not do_not_disturb_start:
                self.add_error('do_not_disturb_start', _('يجب تحديد وقت بداية عدم الإزعاج'))
            if not do_not_disturb_end:
                self.add_error('do_not_disturb_end', _('يجب تحديد وقت نهاية عدم الإزعاج'))
        
        # التحقق من تفعيل طريقة إشعار واحدة على الأقل
        notify_in_app = cleaned_data.get('notify_in_app')
        
        if not notify_in_app and not notify_email and not notify_sms:
            raise ValidationError(_('يجب تفعيل طريقة إشعار واحدة على الأقل'))
        
        return cleaned_data
