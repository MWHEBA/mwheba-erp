from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

User = settings.AUTH_USER_MODEL


class FinancialCategory(models.Model):
    """
    التصنيفات المالية (Financial Categories)
    تصنيف موحد للإيرادات والمصروفات لتحليل الربحية
    """
    
    # الحقول الأساسية
    code = models.CharField(
        _("الرمز"),
        max_length=50,
        unique=True,
        help_text=_("رمز فريد للتصنيف (مثال: tuition, transportation)")
    )
    
    name = models.CharField(
        _("الاسم"),
        max_length=200,
        help_text=_("اسم التصنيف")
    )
    
    description = models.TextField(
        _("الوصف"),
        blank=True,
        null=True,
        help_text=_("وصف تفصيلي للتصنيف")
    )
    
    # الحسابات المحاسبية الافتراضية
    default_revenue_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        related_name='revenue_categories',
        verbose_name=_("حساب الإيرادات الافتراضي"),
        blank=True,
        null=True,
        help_text=_("الحساب المحاسبي الافتراضي للإيرادات من هذا التصنيف")
    )
    
    default_expense_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        related_name='expense_categories',
        verbose_name=_("حساب المصروفات الافتراضي"),
        blank=True,
        null=True,
        help_text=_("الحساب المحاسبي الافتراضي للمصروفات من هذا التصنيف")
    )
    
    # حقول التحكم
    is_active = models.BooleanField(
        _("نشط"),
        default=True,
        help_text=_("هل التصنيف نشط ومتاح للاستخدام؟")
    )
    
    display_order = models.PositiveIntegerField(
        _("ترتيب العرض"),
        default=0,
        help_text=_("ترتيب ظهور التصنيف في القوائم (الأصغر أولاً)")
    )
    
    # حقول التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    
    class Meta:
        verbose_name = _("تصنيف مالي")
        verbose_name_plural = _("التصنيفات المالية")
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
            models.Index(fields=['display_order']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    def clean(self):
        """التحقق من صحة البيانات"""
        super().clean()
        
        # التحقق من وجود حساب واحد على الأقل
        if not self.default_revenue_account and not self.default_expense_account:
            raise ValidationError(
                _("يجب تحديد حساب الإيرادات أو حساب المصروفات على الأقل")
            )
    
    def save(self, *args, **kwargs):
        """حفظ النموذج مع التحقق"""
        self.full_clean()
        super().save(*args, **kwargs)
    
    def get_account_for_transaction_type(self, transaction_type):
        """
        الحصول على الحساب المحاسبي المناسب حسب نوع المعاملة
        
        Args:
            transaction_type (str): نوع المعاملة ('revenue' أو 'expense')
        
        Returns:
            ChartOfAccounts: الحساب المحاسبي المناسب أو None
        """
        if transaction_type == 'revenue':
            return self.default_revenue_account
        elif transaction_type == 'expense':
            return self.default_expense_account
        return None


class FinancialSubcategory(models.Model):
    """
    التصنيفات المالية الفرعية
    تصنيفات فرعية تحت التصنيف الرئيسي لتحليل ربحية أدق
    """
    
    parent_category = models.ForeignKey(
        FinancialCategory,
        on_delete=models.CASCADE,
        related_name='subcategories',
        verbose_name=_("التصنيف الرئيسي")
    )
    
    code = models.CharField(
        _("الرمز"),
        max_length=50,
        help_text=_("رمز فريد للتصنيف الفرعي")
    )
    
    name = models.CharField(
        _("الاسم"),
        max_length=200,
        help_text=_("اسم التصنيف الفرعي")
    )
    
    is_active = models.BooleanField(
        _("نشط"),
        default=True,
        help_text=_("هل التصنيف الفرعي نشط؟")
    )
    
    display_order = models.PositiveIntegerField(
        _("ترتيب العرض"),
        default=0,
        help_text=_("ترتيب ظهور التصنيف في القوائم")
    )
    
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    
    class Meta:
        verbose_name = _("تصنيف فرعي")
        verbose_name_plural = _("التصنيفات الفرعية")
        ordering = ['parent_category', 'display_order', 'name']
        unique_together = ['parent_category', 'code']
        indexes = [
            models.Index(fields=['parent_category', 'is_active']),
            models.Index(fields=['code']),
        ]
    
    def save(self, *args, **kwargs):
        """Override save to ensure code uniqueness among active subcategories"""
        if self.is_active:
            # Check for duplicate active codes (excluding self)
            duplicate = FinancialSubcategory.objects.filter(
                code=self.code,
                is_active=True
            ).exclude(pk=self.pk).first()
            
            if duplicate:
                raise ValueError(
                    f"التصنيف الفرعي بالكود '{self.code}' موجود بالفعل "
                    f"تحت '{duplicate.parent_category.name}'. "
                    f"يرجى استخدام كود مختلف."
                )
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.parent_category.name} - {self.name}"


class CategoryBudget(models.Model):
    """
    ميزانيات التصنيفات المالية
    """

    PERIOD_CHOICES = (
        ("monthly", _("شهرية")),
        ("quarterly", _("ربع سنوية")),
        ("yearly", _("سنوية")),
        ("custom", _("مخصصة")),
    )

    category = models.ForeignKey(
        FinancialCategory,
        on_delete=models.CASCADE,
        verbose_name=_("التصنيف"),
        related_name="budgets",
    )
    period_type = models.CharField(
        _("نوع الفترة"), max_length=20, choices=PERIOD_CHOICES
    )
    start_date = models.DateField(_("تاريخ البداية"))
    end_date = models.DateField(_("تاريخ النهاية"))

    budget_amount = models.DecimalField(
        _("مبلغ الميزانية"), max_digits=12, decimal_places=2
    )
    spent_amount = models.DecimalField(
        _("المبلغ المنفق"), max_digits=12, decimal_places=2, default=0
    )

    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    is_active = models.BooleanField(_("نشط"), default=True)

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="created_budgets",
    )

    class Meta:
        verbose_name = _("ميزانية فئة")
        verbose_name_plural = _("ميزانيات التصنيفات")
        ordering = ["-start_date"]
        unique_together = ["category", "start_date", "end_date"]

    def __str__(self):
        return f"{self.category.name} - {self.start_date} إلى {self.end_date}"

    @property
    def remaining_amount(self):
        """المبلغ المتبقي"""
        return self.budget_amount - self.spent_amount

    @property
    def usage_percentage(self):
        """نسبة الاستخدام"""
        if self.budget_amount > 0:
            return (self.spent_amount / self.budget_amount) * 100
        return 0

    @property
    def is_over_budget(self):
        """هل تجاوز الميزانية"""
        return self.spent_amount > self.budget_amount
