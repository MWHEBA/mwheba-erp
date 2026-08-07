from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class CostCenter(models.Model):
    """
    موديل مراكز التكلفة الهيكلي (CostCenter Model with Indexed Tree Path & Policy Enforcement)
    يدعم العلاقات الشجرية، المسار الشجري المفهرس، وسياسات الفرض الموحدة.
    """
    POLICY_CHOICES = (
        ('REQUIRED', _('إلزامي')),
        ('OPTIONAL', _('اختياري')),
        ('FORBIDDEN', _('محظور')),
    )

    code = models.CharField(_("كود مركز التكلفة"), max_length=50, unique=True, db_index=True)
    name = models.CharField(_("اسم مركز التكلفة"), max_length=150)

    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_("المركز الأب (في الشجرة)")
    )
    tree_path = models.CharField(
        _("المسار الشجري المفهرس"),
        max_length=255,
        db_index=True,
        blank=True,
        help_text=_("المسار الشجري الفريد بالصيغة /root_id/parent_id/node_id/ لسرعة الاستعلامات الختامية")
    )

    cost_center_policy = models.CharField(
        _("سياسة مركز التكلفة"),
        max_length=20,
        choices=POLICY_CHOICES,
        default='OPTIONAL',
        help_text=_("السياسة المطبقة على المعاملات والحسابات المتعلقة به")
    )

    is_active = models.BooleanField(_("نشط"), default=True)
    is_system = models.BooleanField(
        _("كائن نظام محمي"),
        default=False,
        help_text=_("حماية كائنات النظام التاريخية مثل CC-LEGACY من الحذف أو التعديل")
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("مركز تكلفة")
        verbose_name_plural = _("مراكز التكلفة")
        ordering = ['code']
        indexes = [
            models.Index(fields=['tree_path']),
            models.Index(fields=['is_active', 'is_system']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        super().clean()
        # 1. حظر جعل المركز أباً لنفسه
        if self.pk and self.parent_id == self.pk:
            raise ValidationError(_("لا يمكن جعل مركز التكلفة أباً لنفسه."))

        # 2. حماية كائنات النظام من تعديل الأب أو الكود
        if self.pk and self.is_system:
            old = CostCenter.objects.get(pk=self.pk)
            if old.code != self.code:
                raise ValidationError(_("حماية النظام: لا يمكن تغيير كود مركز تكلفة تابع للنظام."))

        # 3. حظر النقل الهيكلي للمراكز التي تملك قيوداً مرحّلة (Tree Structural Mutation Guard)
        if self.pk:
            old = CostCenter.objects.get(pk=self.pk)
            if old.parent_id != self.parent_id:
                # التحقق هل هذا المركز أو أي من أبنائه له بنود قيود مرحلة
                descendant_ids = self.get_descendant_ids()
                from financial.models.journal_entry import JournalEntryLine
                has_posted = JournalEntryLine.objects.filter(
                    journal_entry__status='posted'
                ).filter(
                    models.Q(cost_center_id__in=descendant_ids) | models.Q(cost_allocations__cost_center_id__in=descendant_ids)
                ).exists()

                if has_posted:
                    raise ValidationError(
                        _("حظر الحوكمة: لا يمكن تغيير موقع مركز التكلفة في الشجرة لوجود معاملات مالية مرحّلة مرتبطة به أو بأبنائه.")
                    )

    def get_descendant_ids(self):
        """جلب جميع معرفات الأبناء والأحفاد الممتدين تحت هذا المركز"""
        if not self.pk or not self.tree_path:
            return [self.pk] if self.pk else []
        return list(CostCenter.objects.filter(tree_path__startswith=self.tree_path).values_list('id', flat=True))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        # تحديث المسار الشجري تلقائياً بعد الحفظ الحصول على الـ Primary Key
        new_path = f"{self.parent.tree_path}{self.id}/" if self.parent and self.parent.tree_path else f"/{self.id}/"
        if self.tree_path != new_path:
            self.tree_path = new_path
            super().save(update_fields=['tree_path'])
            # تحديث مسارات الأبناء تلقائياً لو تغير مسار الأب
            for child in self.children.all():
                child.save()
