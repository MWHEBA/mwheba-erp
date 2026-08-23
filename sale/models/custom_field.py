from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify


class CustomFieldDefinition(models.Model):
    """
    نموذج تعريف الحقول الإضافية المخصصة في النظام
    """
    MODULE_CHOICES = (
        ('quotation', _('عروض الأسعار')),
        ('sales_order', _('أوامر البيع')),
        ('sale', _('فواتير المبيعات')),
        ('both', _('عروض الأسعار وفواتير المبيعات')),
        ('all', _('الكل (عروض الأسعار، أوامر البيع، والفواتير)')),
    )

    FIELD_TYPES = (
        ('text', _('نص قصير')),
        ('number', _('رقم')),
        ('date', _('تاريخ')),
        ('select', _('قائمة منسدلة')),
        ('checkbox', _('مربع اختيار (نعم/لا)')),
        ('textarea', _('نص طويل')),
    )

    key = models.SlugField(_("المفتاح الفريد"), max_length=100, unique=True, help_text=_("مفتاح فريد كود إنجليزي يولد آلياً"))
    name = models.CharField(_("اسم الحقل بالعربي"), max_length=100)
    name_en = models.CharField(_("اسم الحقل بالإنجليزية"), max_length=100, blank=True, null=True)
    module = models.CharField(_("الموديول المستهدف"), max_length=20, choices=MODULE_CHOICES, default='both')
    field_type = models.CharField(_("نوع البيانات"), max_length=20, choices=FIELD_TYPES, default='text')
    select_options = models.TextField(
        _("خيارات القائمة المنسدلة"), 
        blank=True, 
        null=True, 
        help_text=_("مفصولة بفاصلة (,) في حال اختيار قائمة منسدلة")
    )
    
    is_required = models.BooleanField(_("إجباري في النموذج"), default=False)
    show_in_header = models.BooleanField(_("إظهار في قسم معلومات الفاتورة (أعلى الصفحة)"), default=False, help_text=_("إذا تم تفعيله، سيظهر الحقل في قسم بيانات الفاتورة الرئيسي العلوي بدلاً من قسم الحقول المخصصة"))
    show_on_print = models.BooleanField(_("إظهار في طباعة A4 و PDF"), default=True)
    show_on_thermal = models.BooleanField(_("إظهار في الطباعة الحرارية 80mm"), default=False)
    is_active = models.BooleanField(_("نشط"), default=True)
    sort_order = models.PositiveIntegerField(_("ترتيب الظهور"), default=0)

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("تعريف حقل إضافي")
        verbose_name_plural = _("تعاريف الحقول الإضافية")
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.name} ({self.get_field_type_display()})"

    def get_name(self, lang="ar"):
        if lang == "en" and self.name_en:
            return self.name_en
        return self.name

    def save(self, *args, **kwargs):
        if not self.key:
            # توليد مفتاح فريد تلقائياً من الاسم أو ID
            base_slug = slugify(self.name, allow_unicode=False)
            if not base_slug or base_slug.replace('-', '').isdigit():
                import time
                base_slug = f"cf_{int(time.time())}"
            
            slug = base_slug
            num = 1
            while CustomFieldDefinition.objects.filter(key=slug).exists():
                slug = f"{base_slug}_{num}"
                num += 1
            self.key = slug
        super().save(*args, **kwargs)

    def get_options_list(self):
        """
        إرجاع خيارات القائمة المنسدلة كمصفوفة نصوص
        """
        if not self.select_options:
            return []
        return [opt.strip() for opt in self.select_options.split(',') if opt.strip()]
