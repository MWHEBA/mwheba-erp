from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
import datetime
import pytz
import re
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


class OperationsSettingsForm(forms.Form):
    """
    نموذج سياسات التشغيل والفواتير والطباعة والشروط والأحكام
    """
    # 1. سياسات بنود الفواتير
    sale_invoice_item_types = forms.ChoiceField(
        label=_('أنواع بنود فواتير المبيعات المسموحة'),
        choices=[
            ('both', _('المنتجات والخدمات معاً')),
            ('products', _('المنتجات فقط')),
            ('services', _('الخدمات فقط')),
        ],
        initial='both',
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )
    purchase_invoice_item_types = forms.ChoiceField(
        label=_('أنواع بنود فواتير الشراء المسموحة'),
        choices=[
            ('both', _('المنتجات والخدمات معاً')),
            ('products', _('المنتجات فقط')),
            ('services', _('الخدمات فقط')),
        ],
        initial='both',
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )
    invoice_product_code_display = forms.ChoiceField(
        label=_('طريقة عرض كود/موديل الصنف في الفواتير والطباعة'),
        choices=[
            ('sku', _('كود الصنف فقط (SKU)')),
            ('barcode', _('الباركود فقط')),
            ('both', _('الكود والباركود معاً')),
            ('none', _('إخفاء كود الصنف والباركود')),
        ],
        initial='sku',
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )
    enable_custom_fields = forms.BooleanField(
        label=_('تفعيل الحقول الإضافية المخصصة بالفواتير وعروض الأسعار'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    custom_fields_display_mode = forms.ChoiceField(
        label=_('نمط عرض الحقول الإضافية في واجهة تحرير الفاتورة'),
        choices=[
            ('expanded', _('مفتوحة افتراضياً (Expanded)')),
            ('collapsed', _('مطوية افتراضياً (Collapsed)')),
            ('hidden', _('مخفية (Hidden)')),
        ],
        initial='expanded',
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )

    # 2. عروض الأسعار وأوامر الشراء
    enable_quotations = forms.BooleanField(
        label=_('تفعيل موديول عروض الأسعار'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    default_quotation_validity_days = forms.IntegerField(
        label=_('فترة صلاحية عرض السعر الافتراضية (بالأيام)'),
        initial=15,
        min_value=1,
        max_value=365,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '15'})
    )
    enable_sales_orders = forms.BooleanField(
        label=_('تفعيل موديول أوامر البيع (Sales Orders)'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    enable_purchase_orders = forms.BooleanField(
        label=_('تفعيل موديول أوامر الشراء (Purchase Orders)'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    # 3. الشروط والأحكام الافتراضية
    default_sale_invoice_notes = forms.CharField(
        label=_('الشروط والأحكام الافتراضية لفواتير المبيعات (عربي)'),
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'dir': 'rtl'})
    )
    default_sale_invoice_notes_en = forms.CharField(
        label=_('Default Sales Invoice Terms & Conditions (English)'),
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'dir': 'ltr'})
    )
    default_quotation_notes = forms.CharField(
        label=_('الشروط والأحكام الافتراضية لعروض الأسعار (عربي)'),
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'dir': 'rtl'})
    )
    default_quotation_notes_en = forms.CharField(
        label=_('Default Quotation Terms & Conditions (English)'),
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'dir': 'ltr'})
    )

    # 4. نماذج الطباعة والحراري
    default_print_language = forms.ChoiceField(
        label=_('لغة الطباعة الافتراضية للمستندات والفواتير'),
        choices=[
            ('ar', _('العربية (Arabic)')),
            ('en', _('الإنجليزية (English)')),
        ],
        initial='ar',
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )
    invoice_title_sale_en = forms.CharField(
        label=_('عنوان فاتورة المبيعات بالإنجليزية (English Sale Title)'),
        required=False,
        initial='TAX INVOICE',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'TAX INVOICE', 'dir': 'ltr'})
    )
    invoice_title_quotation_en = forms.CharField(
        label=_('عنوان عرض السعر بالإنجليزية (English Quotation Title)'),
        required=False,
        initial='QUOTATION',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'QUOTATION', 'dir': 'ltr'})
    )
    enable_thermal_printing = forms.BooleanField(
        label=_('تفعيل الطباعة الحرارية المباشرة للفواتير (POS Thermal Printing)'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    receipt_paper_width = forms.ChoiceField(
        label=_('عرض ورق الفاتورة الحرارية (Paper Width)'),
        choices=[
            ('80', _('80 مم (قياسي / Standard)')),
            ('58', _('58 مم (صغير / Compact)')),
        ],
        initial='80',
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )

    def clean_default_sale_invoice_notes(self):
        val = self.cleaned_data.get('default_sale_invoice_notes', '')
        return re.sub(r'<script.*?>.*?</script>', '', val, flags=re.IGNORECASE | re.DOTALL) if val else ''

    def clean_default_sale_invoice_notes_en(self):
        val = self.cleaned_data.get('default_sale_invoice_notes_en', '')
        return re.sub(r'<script.*?>.*?</script>', '', val, flags=re.IGNORECASE | re.DOTALL) if val else ''

    def clean_default_quotation_notes(self):
        val = self.cleaned_data.get('default_quotation_notes', '')
        return re.sub(r'<script.*?>.*?</script>', '', val, flags=re.IGNORECASE | re.DOTALL) if val else ''

    def clean_default_quotation_notes_en(self):
        val = self.cleaned_data.get('default_quotation_notes_en', '')
        return re.sub(r'<script.*?>.*?</script>', '', val, flags=re.IGNORECASE | re.DOTALL) if val else ''


class SystemSettingsForm(forms.Form):
    """
    نموذج إعدادات النظام والبنية التحتية والأمان والربط الخارجي
    """
    # 1. الإعدادات العامة والإقليمية
    site_name = forms.CharField(
        label=_('اسم النظام / الموقع'),
        max_length=100,
        initial='موهبة ERP',
        widget=forms.TextInput(attrs={'class': 'form-control', 'dir': 'rtl'})
    )
    language = forms.ChoiceField(
        label=_('اللغة الافتراضية للواجهة'),
        choices=[('ar', _('العربية')), ('en', _('English'))],
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )
    timezone = forms.ChoiceField(
        label=_('المنطقة الزمنية للسيرفر'),
        choices=[
            ('Africa/Cairo', _('القاهرة (GMT+2 / GMT+3)')),
            ('Asia/Riyadh', _('الرياض (GMT+3)')),
            ('UTC', _('التوقيت العالمي الموحد (UTC)')),
        ],
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )
    date_format = forms.ChoiceField(
        label=_('صيغة عرض التاريخ'),
        choices=[
            ('d/m/Y', 'DD/MM/YYYY'),
            ('Y-m-d', 'YYYY-MM-DD'),
            ('m/d/Y', 'MM/DD/YYYY'),
        ],
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )
    time_format = forms.ChoiceField(
        label=_('صيغة عرض الوقت'),
        choices=[
            ('12', _('نظام 12 ساعة (ص/م)')),
            ('24', _('نظام 24 ساعة')),
        ],
        initial='12',
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )
    maintenance_mode = forms.BooleanField(
        label=_('تفعيل وضع الصيانة العام (إيقاف النظام لغير المشرفين)'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    maintenance_message = forms.CharField(
        label=_('رسالة وضع الصيانة المعروضة للمستخدمين'),
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'النظام في وضع الصيانة المجدولة، يرجى المحاولة لاحقاً...'})
    )

    # 2. المالية والعملة الأساسية (IAS 21)
    default_currency = forms.ModelChoiceField(
        queryset=None,
        label=_('العملة الوظيفية الأساسية للنظام (Functional Currency)'),
        required=True,
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )

    # 3. الأمان وإدارة الجلسات
    enable_two_factor = forms.BooleanField(
        label=_('تفعيل المصادقة الثنائية (2FA) للمشرفين'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    password_policy = forms.ChoiceField(
        label=_('سياسة قوة كلمات المرور'),
        choices=[
            ('simple', _('بسيط (6 أحرف على الأقل)')),
            ('medium', _('متوسط (8 أحرف وأرقام)')),
            ('strong', _('قوي (8 أحرف وأرقام ورموز خاصة)')),
        ],
        initial='medium',
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )
    session_timeout = forms.IntegerField(
        label=_('مهلة خمول الجلسة (بالدقائق)'),
        min_value=5,
        max_value=10080,
        initial=60,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    failed_login_attempts = forms.IntegerField(
        label=_('الحد الأقصى لمحاولات الدخول الفاشلة قبل القفل'),
        min_value=3,
        max_value=10,
        initial=5,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    account_lockout_time = forms.IntegerField(
        label=_('مدة قفل الحساب بعد المحاولات الفاشلة (بالدقائق)'),
        min_value=5,
        max_value=1440,
        initial=30,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    # 4. خادم البريد (SMTP)
    email_host = forms.CharField(
        label='SMTP Host',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'smtp.gmail.com', 'dir': 'ltr'})
    )
    email_port = forms.IntegerField(
        label='SMTP Port',
        required=False,
        min_value=1,
        max_value=65535,
        initial=587,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '587', 'dir': 'ltr'})
    )
    email_username = forms.CharField(
        label='Email Username',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'user@example.com', 'dir': 'ltr', 'autocomplete': 'off'})
    )
    email_password = forms.CharField(
        label='Email Password',
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={'class': 'form-control', 'placeholder': '••••••••', 'dir': 'ltr', 'autocomplete': 'new-password'})
    )
    email_encryption = forms.ChoiceField(
        label=_('نوع التشفير'),
        choices=[
            ('tls', 'TLS (Port 587)'),
            ('ssl', 'SSL (Port 465)'),
            ('none', _('بدون تشفير (Port 25)')),
        ],
        initial='tls',
        widget=forms.Select(attrs={'class': 'form-select select2-filter', 'dir': 'rtl'})
    )
    email_from = forms.EmailField(
        label=_('عنوان البريد الافتراضي للإرسال (From Email)'),
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'noreply@mwheba.com', 'dir': 'ltr', 'autocomplete': 'off'})
    )

    # 5. مزامنة نظام دفترة (Daftra)
    daftra_enabled = forms.BooleanField(
        label=_('تفعيل مزامنة البيانات مع نظام دفترة'),
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    daftra_domain = forms.CharField(
        label=_('نطاق حساب دفترة (Subdomain)'),
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'your-company', 'dir': 'ltr', 'autocomplete': 'off'})
    )
    daftra_api_key = forms.CharField(
        label=_('مفتاح الربط (API Key)'),
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={'class': 'form-control', 'placeholder': '••••••••', 'dir': 'ltr', 'autocomplete': 'new-password'})
    )

    def __init__(self, *args, **kwargs):
        is_locked = kwargs.pop('is_locked', False)
        super().__init__(*args, **kwargs)
        try:
            from financial.models import Currency
            self.fields['default_currency'].queryset = Currency.objects.filter(is_active=True)
        except Exception:
            pass
        if is_locked:
            self.fields['default_currency'].widget.attrs['disabled'] = 'disabled'
            self.fields['default_currency'].required = False


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
