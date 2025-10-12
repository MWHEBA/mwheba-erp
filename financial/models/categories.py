from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

User = settings.AUTH_USER_MODEL


class FinancialCategory(models.Model):
    """
    تصنيفات المصروفات والإيرادات المحسنة
    """

    TYPE_CHOICES = (
        ("expense", _("مصروف")),
        ("income", _("إيراد")),
        ("both", _("مختلط")),
    )

    PRIORITY_CHOICES = (
        ("high", _("عالية")),
        ("medium", _("متوسطة")),
        ("low", _("منخفضة")),
    )

    name = models.CharField(_("الاسم"), max_length=100)
    name_en = models.CharField(
        _("الاسم بالإنجليزية"), max_length=100, blank=True, null=True
    )
    code = models.CharField(
        _("الكود"), max_length=20, unique=True, blank=True, null=True
    )
    type = models.CharField(_("النوع"), max_length=20, choices=TYPE_CHOICES)
    priority = models.CharField(
        _("الأولوية"), max_length=10, choices=PRIORITY_CHOICES, default="medium"
    )
    description = models.TextField(_("الوصف"), blank=True, null=True)

    # التسلسل الهرمي
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("التصنيف الأب"),
        related_name="children",
    )
    level = models.PositiveIntegerField(_("المستوى"), default=1)

    # الحدود المالية
    budget_limit = models.DecimalField(
        _("حد الميزانية"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("الحد الأقصى للإنفاق في هذا التصنيف"),
    )
    warning_threshold = models.DecimalField(
        _("عتبة التحذير"),
        max_digits=5,
        decimal_places=2,
        default=80.00,
        help_text=_("نسبة التحذير من حد الميزانية"),
    )

    # الإعدادات
    is_active = models.BooleanField(_("نشط"), default=True)
    is_system = models.BooleanField(
        _("فئة نظام"), default=False, help_text=_("فئة أساسية لا يمكن حذفها")
    )
    requires_approval = models.BooleanField(_("يتطلب موافقة"), default=False)

    # التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="created_categories",
    )

    class Meta:
        verbose_name = _("فئة مالية")
        verbose_name_plural = _("التصنيفات المالية")
        ordering = ["type", "level", "name"]
        unique_together = ["name", "type", "parent"]

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

    def save(self, *args, **kwargs):
        # تحديد المستوى تلقائياً
        if self.parent:
            self.level = self.parent.level + 1
        else:
            self.level = 1

        # إنشاء كود تلقائي إذا لم يكن موجوداً
        if not self.code:
            type_prefix = self.type.upper()[:3]
            count = FinancialCategory.objects.filter(type=self.type).count() + 1
            self.code = f"{type_prefix}{count:03d}"

        super().save(*args, **kwargs)

    def get_children_recursive(self):
        """الحصول على جميع التصنيفات الفرعية بشكل تكراري"""
        children = []
        for child in self.children.filter(is_active=True):
            children.append(child)
            children.extend(child.get_children_recursive())
        return children

    def get_budget_usage(self, start_date=None, end_date=None):
        """حساب استخدام الميزانية للفئة"""
        if not self.budget_limit:
            return None

        from django.utils import timezone
        from datetime import datetime, timedelta

        if not start_date:
            start_date = timezone.now().date().replace(day=1)  # بداية الشهر الحالي
        if not end_date:
            end_date = timezone.now().date()

        # حساب إجمالي المصروفات في هذا التصنيف
        total_spent = 0
        # هنا يمكن إضافة منطق حساب المصروفات من الجداول المرتبطة

        usage_percentage = (
            (total_spent / self.budget_limit) * 100 if self.budget_limit > 0 else 0
        )

        return {
            "total_spent": total_spent,
            "budget_limit": self.budget_limit,
            "remaining": self.budget_limit - total_spent,
            "usage_percentage": usage_percentage,
            "is_over_budget": total_spent > self.budget_limit,
            "is_warning": usage_percentage >= self.warning_threshold,
        }

    def is_ancestor_of(self, category):
        """التحقق من كون هذا التصنيف أب لفئة أخرى"""
        if not category.parent:
            return False
        if category.parent == self:
            return True
        return self.is_ancestor_of(category.parent)


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
