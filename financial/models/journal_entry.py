from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from django.core.exceptions import ValidationError
from .chart_of_accounts import ChartOfAccounts

# User = settings.AUTH_USER_MODEL


class AccountingPeriod(models.Model):
    """
    الفترات المحاسبية
    """

    STATUS_CHOICES = (
        ("open", _("مفتوحة")),
        ("closed", _("مغلقة")),
    )

    name = models.CharField(_("اسم الفترة"), max_length=100)
    start_date = models.DateField(_("تاريخ البداية"))
    end_date = models.DateField(_("تاريخ النهاية"))
    status = models.CharField(
        _("الحالة"), max_length=10, choices=STATUS_CHOICES, default="open"
    )

    # معلومات الإغلاق
    closed_at = models.DateTimeField(_("تاريخ الإغلاق"), null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أغلق بواسطة"),
        related_name="periods_closed",
    )

    # معلومات التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="periods_created",
    )

    class Meta:
        verbose_name = _("فترة محاسبية")
        verbose_name_plural = _("الفترات المحاسبية")
        ordering = ["-start_date"]
        unique_together = ["start_date", "end_date"]

    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"

    def clean(self):
        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError(_("تاريخ البداية يجب أن يكون قبل تاريخ النهاية"))

    def is_date_in_period(self, date):
        """التحقق من وجود التاريخ ضمن الفترة"""
        from datetime import date as date_type
        # تحويل التاريخ إلى date إذا كان datetime
        if hasattr(date, 'date'):
            date = date.date()
        # تحويل start_date و end_date إذا كانا strings
        start = self.start_date
        end = self.end_date
        if isinstance(start, str):
            start = date_type.fromisoformat(start)
        if isinstance(end, str):
            end = date_type.fromisoformat(end)
        return start <= date <= end

    def can_post_entries(self):
        """التحقق من إمكانية إدراج قيود في الفترة"""
        return self.status == "open"

    @property
    def is_active(self):
        """هل الفترة نشطة"""
        return self.status == "open"

    @property
    def is_closed(self):
        """هل الفترة مغلقة"""
        return self.status == "closed"

    @classmethod
    def get_period_for_date(cls, date):
        """الحصول على الفترة المحاسبية لتاريخ معين"""
        return cls.objects.filter(start_date__lte=date, end_date__gte=date).first()


class JournalEntry(models.Model):
    """
    القيود اليومية (Journal Entries)
    """

    ENTRY_TYPES = (
        ("manual", _("يدوي")),
        ("automatic", _("تلقائي")),
        ("adjustment", _("تسوية")),
        ("closing", _("إقفال")),
        ("opening", _("افتتاحي")),
        ("inventory", _("حركة مخزنية")),
        ("fee", _("رسوم")),  # للتوافق مع القيود القديمة
        ("application_fee", _("رسوم تقديم")),
        ("tuition_fee", _("رسوم أساسية")),
        ("bus_fee", _("رسوم نقل")),
        ("materials_fee", _("رسوم مواد ومستلزمات")),
        ("services_fee", _("رسوم خدمات")),
        ("activity_fee", _("رسوم أنشطة")),
        ("admin_fee", _("رسوم إدارية")),
        ("product_delivery", _("تسليم منتجات")),
        ("delivery_fee", _("رسوم تسليم")),
        ("complementary_fee", _("رسوم مكملة")),
        ("parent_payment", _("دفعة ولي أمر")),
        ("supplier_payment", _("دفعة مورد")),
        ("salary_payment", _("راتب موظف")),
        ("partner_contribution", _("مساهمة الشريك")),
        ("partner_withdrawal", _("سحب الشريك")),
        ("cash_receipt", _("إيراد نقدي")),
        ("cash_payment", _("مصروف نقدي")),
        ("bank_receipt", _("إيراد بنكي")),
        ("bank_payment", _("مصروف بنكي")),
        ("transfer", _("تحويل")),
        ("refund", _("استرداد")),
        ("settlement", _("تسوية مالية")),
        ("discount", _("خصم")),
        ("penalty", _("غرامة")),
        ("reversal", _("قيد عكسي")),
    )

    def __init__(self, *args, **kwargs):
        # تصحيح تلقائي للـ arguments الشائعة (للتوافق مع الأنظمة القديمة)
        if "reference_number" in kwargs:
            kwargs["reference"] = kwargs.pop("reference_number")
        if "entry_date" in kwargs:
            kwargs["date"] = kwargs.pop("entry_date")

        super().__init__(*args, **kwargs)

    STATUS_CHOICES = (
        ("draft", _("مسودة")),
        ("posted", _("مرحل")),
        ("cancelled", _("ملغي")),
    )

    # معلومات القيد الأساسية
    number = models.CharField(_("رقم القيد"), max_length=20, unique=True)
    date = models.DateField(_("التاريخ"), default=timezone.now)
    entry_type = models.CharField(
        _("نوع القيد"), max_length=20, choices=ENTRY_TYPES, default="manual"
    )
    status = models.CharField(
        _("الحالة"), max_length=10, choices=STATUS_CHOICES, default="draft"
    )

    # الوصف والمرجع
    description = models.TextField(_("البيان"))
    reference = models.CharField(_("المرجع"), max_length=100, blank=True, null=True)
    reference_type = models.CharField(
        _("نوع المرجع"), max_length=50, blank=True, null=True
    )
    reference_id = models.PositiveIntegerField(_("معرف المرجع"), blank=True, null=True)
    notes = models.TextField(
        _("ملاحظات"), blank=True, null=True, help_text=_("ملاحظات إضافية على القيد")
    )

    # حقول الربط المحسنة (للربط مع الوحدات الأخرى)
    source_module = models.CharField(
        _("الوحدة المصدر"), 
        max_length=50, 
        blank=True, 
        help_text=_("الوحدة التي أنشأت القيد (client, transportation, hr, etc.)")
    )
    source_model = models.CharField(
        _("النموذج المصدر"), 
        max_length=50, 
        blank=True, 
        help_text=_("النموذج الذي أنشأ القيد (CustomerPayment, SalaryPayment, etc.)")
    )
    source_id = models.PositiveIntegerField(
        _("معرف المصدر"), 
        blank=True, 
        null=True, 
        help_text=_("معرف السجل الذي أنشأ القيد")
    )

    # الفترة المحاسبية
    accounting_period = models.ForeignKey(
        AccountingPeriod,
        on_delete=models.PROTECT,
        verbose_name=_("الفترة المحاسبية"),
        related_name="journal_entries",
    )
    
    # التصنيف المالي
    financial_category = models.ForeignKey(
        'financial.FinancialCategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("التصنيف المالي"),
        related_name="journal_entries",
        help_text=_("التصنيف المالي للقيد (للتحليل والتقارير)")
    )
    
    # التصنيف الفرعي
    financial_subcategory = models.ForeignKey(
        'financial.FinancialSubcategory',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("التصنيف الفرعي"),
        related_name="journal_entries",
        help_text=_("التصنيف الفرعي للقيد (للتحليل التفصيلي)")
    )

    # معلومات الترحيل
    posted_at = models.DateTimeField(_("تاريخ الترحيل"), null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("رحل بواسطة"),
        related_name="entries_posted",
    )

    # حقول الحوكمة والحماية من التكرار
    idempotency_key = models.CharField(
        _("مفتاح منع التكرار"),
        max_length=255,
        unique=True,
        null=True,
        blank=True,
        help_text=_("مفتاح فريد لضمان عدم تكرار العملية")
    )
    created_by_service = models.CharField(
        _("الخدمة المنشئة"),
        max_length=100,
        default='AccountingGateway',
        help_text=_("الخدمة التي أنشأت هذا القيد")
    )
    
    # حقول العكس والتعديل (Period Lock Enforcement)
    original_entry = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("القيد الأصلي"),
        related_name="reversal_entries",
        help_text=_("القيد الأصلي الذي يتم عكسه (للقيود العكسية فقط)")
    )
    is_reversal = models.BooleanField(
        _("قيد عكسي"),
        default=False,
        help_text=_("هل هذا قيد عكسي لقيد آخر؟")
    )
    reversal_reason = models.TextField(
        _("سبب العكس"),
        blank=True,
        null=True,
        help_text=_("سبب إنشاء القيد العكسي")
    )
    is_locked = models.BooleanField(
        _("مقفل"),
        default=False,
        help_text=_("هل القيد مقفل ولا يمكن تعديله؟ (للقيود المرحلة في فترات مغلقة)")
    )
    locked_at = models.DateTimeField(
        _("تاريخ القفل"),
        null=True,
        blank=True,
        help_text=_("تاريخ قفل القيد")
    )
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("قُفل بواسطة"),
        related_name="entries_locked",
        help_text=_("المستخدم الذي قام بقفل القيد")
    )
    
    # معلومات التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="entries_created",
    )

    class Meta:
        verbose_name = _("قيد يومي")
        verbose_name_plural = _("القيود اليومية")
        ordering = ["-date", "-number"]
        indexes = [
            models.Index(fields=["date", "status"]),
            models.Index(fields=["number"]),
            models.Index(fields=["reference_type", "reference_id"]),
            models.Index(fields=["source_module", "source_model", "source_id"]),
            models.Index(fields=["entry_type", "date"]),
            models.Index(fields=["accounting_period", "status"]),
            models.Index(fields=["created_by", "date"]),
            models.Index(fields=["posted_at"]),
            models.Index(fields=["idempotency_key"]),
            models.Index(fields=["created_by_service"]),
            models.Index(fields=["original_entry", "is_reversal"]),
            models.Index(fields=["is_locked", "status"]),
            models.Index(fields=["locked_at"]),
        ]

    def __str__(self):
        return f"{self.number} - {self.date} - {self.description[:50]}"
    
    def get_absolute_url(self):
        """الحصول على رابط تفاصيل القيد"""
        from django.urls import reverse
        return reverse('financial:journal_entries_detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        # تعيين رقم القيد تلقائياً إذا لم يكن موجوداً
        if not self.number:
            self.number = self.generate_entry_number()

        # تعيين الفترة المحاسبية تلقائياً
        try:
            # التحقق من وجود الفترة المحاسبية
            if self.accounting_period_id is None:
                period = AccountingPeriod.get_period_for_date(self.date)
                if not period:
                    raise ValidationError(_("لا توجد فترة محاسبية مفتوحة لهذا التاريخ"))
                self.accounting_period = period
        except AccountingPeriod.DoesNotExist:
            # إذا لم تكن الفترة موجودة، ابحث عن واحدة
            period = AccountingPeriod.get_period_for_date(self.date)
            if not period:
                raise ValidationError(_("لا توجد فترة محاسبية مفتوحة لهذا التاريخ"))
            self.accounting_period = period

        # التحقق من قفل الفترة المحاسبية (للقيود غير العكسية)
        # السماح بعمليات القفل والعكس والترحيل
        update_fields = kwargs.get('update_fields', None)
        is_posting = update_fields and {'status', 'posted_at', 'posted_by'}.issubset(set(update_fields))
        
        if not self.is_reversal and self.pk and not getattr(self, '_allow_lock_operation', False) and not is_posting:  # تحديث قيد موجود
            try:
                self.validate_period_lock()
            except ValidationError as e:
                # السماح بالحفظ للقيود العكسية أو إذا كان هناك تجاوز صريح
                if not getattr(self, '_bypass_period_lock', False):
                    raise e

        # تحذير تطوير إذا لم يتم إنشاء القيد عبر البوابة المخولة
        if not getattr(self, '_gateway_approved', False):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"JournalEntry {self.number} created outside AccountingGateway - audit will flag this")

        super().save(*args, **kwargs)

    def generate_entry_number(self):
        """
        توليد رقم القيد تلقائياً - نظام مبسط
        التنسيق: JE-0001 (رقم تسلسلي بسيط)
        """
        # البحث عن أعلى رقم في النظام
        entries = JournalEntry.objects.filter(
            number__startswith="JE-"
        ).exclude(pk=self.pk if self.pk else None)

        max_number = 0
        for entry in entries:
            try:
                # استخراج الرقم من نهاية اسم القيد
                number_part = entry.number.split("-")[-1]
                current_number = int(number_part)
                if current_number > max_number:
                    max_number = current_number
            except (ValueError, IndexError):
                continue

        new_number = max_number + 1

        # التأكد من عدم تكرار الرقم
        while True:
            candidate_number = f"JE-{new_number:04d}"
            if (
                not JournalEntry.objects.filter(number=candidate_number)
                .exclude(pk=self.pk if self.pk else None)
                .exists()
            ):
                return candidate_number
            new_number += 1

    @property
    def total_debit(self):
        """إجمالي المدين"""
        return self.lines.aggregate(models.Sum("debit"))["debit__sum"] or Decimal("0")

    @property
    def total_credit(self):
        """إجمالي الدائن"""
        return self.lines.aggregate(models.Sum("credit"))["credit__sum"] or Decimal("0")

    @property
    def is_balanced(self):
        """التحقق من توازن القيد"""
        return self.total_debit == self.total_credit

    @property
    def difference(self):
        """الفرق بين المدين والدائن"""
        return self.total_debit - self.total_credit

    @property
    def total_amount(self):
        """إجمالي المبلغ (المدين أو الدائن)"""
        return self.total_debit

    @property
    def is_posted(self):
        """هل القيد مرحل"""
        return self.status == "posted"
    
    @property
    def reversed_entry(self):
        """القيد العكسي لهذا القيد (إذا كان موجوداً)"""
        return self.reversal_entries.filter(is_reversal=True).first()
    
    @property
    def can_be_reversed(self):
        """هل يمكن عكس هذا القيد؟"""
        if not self.is_posted:
            return False
        if self.is_reversal:
            return False  # لا يمكن عكس قيد عكسي
        if self.reversed_entry:
            return False  # تم عكسه بالفعل
        return True
    
    @property
    def can_be_modified(self):
        """هل يمكن تعديل هذا القيد؟"""
        if self.is_posted:
            return False  # القيود المرحلة لا يمكن تعديلها
        if self.is_locked:
            return False  # القيود المقفلة لا يمكن تعديلها
        if self.accounting_period and not self.accounting_period.can_post_entries():
            return False  # لا يمكن تعديل قيود في فترات مغلقة
        return True
    
    @property
    def can_be_deleted(self):
        """هل يمكن حذف هذا القيد؟"""
        if self.is_posted:
            return False  # القيود المرحلة لا يمكن حذفها
        if self.is_locked:
            return False  # القيود المقفلة لا يمكن حذفها
        return self.status == "draft"

    def validate_entry(self):
        """التحقق من صحة القيد"""
        errors = []

        # التحقق من وجود بنود
        if not self.lines.exists():
            errors.append(_("القيد يجب أن يحتوي على بنود"))

        # التحقق من التوازن
        if not self.is_balanced:
            errors.append(_("القيد غير متوازن: الفرق = {}".format(self.difference)))

        # التحقق من الفترة المحاسبية
        try:
            if (
                self.accounting_period_id
                and self.accounting_period
                and not self.accounting_period.can_post_entries()
            ):
                errors.append(_("لا يمكن إدراج قيود في فترة مغلقة"))
        except AccountingPeriod.DoesNotExist:
            errors.append(_("الفترة المحاسبية غير موجودة"))

        # التحقق من صحة البنود
        for line in self.lines.all():
            try:
                line.validate_line()
            except ValidationError as e:
                errors.extend(e.messages)

        if errors:
            raise ValidationError(errors)

        return True
    
    def lock_entry(self, user=None, reason="Period closed"):
        """
        قفل القيد لمنع التعديل
        
        Args:
            user: المستخدم الذي يقوم بالقفل
            reason: سبب القفل
        """
        if not self.is_posted:
            raise ValidationError(_("لا يمكن قفل قيد غير مرحل"))
        
        if self.is_locked:
            return  # مقفل بالفعل
        
        self.is_locked = True
        self.locked_at = timezone.now()
        self.locked_by = user
        
        # السماح بعملية القفل
        self._allow_lock_operation = True
        self.save(update_fields=['is_locked', 'locked_at', 'locked_by'])
        
        import logging
        logger = logging.getLogger(__name__)
    
    def validate_period_lock(self):
        """
        التحقق من قفل الفترة المحاسبية
        
        Raises:
            ValidationError: إذا كانت الفترة مغلقة أو القيد مقفل
        """
        if self.is_locked:
            raise ValidationError(_("القيد مقفل ولا يمكن تعديله"))
        
        if self.accounting_period and not self.accounting_period.can_post_entries():
            raise ValidationError(_("لا يمكن تعديل قيود في فترة مغلقة"))
        
        if self.is_posted:
            raise ValidationError(_("القيود المرحلة لا يمكن تعديلها - استخدم العكس بدلاً من ذلك"))
    
    def create_reversal_entry(self, user, reason="", partial_amount=None):
        """
        إنشاء قيد عكسي لهذا القيد
        
        Args:
            user: المستخدم الذي ينشئ القيد العكسي
            reason: سبب العكس
            partial_amount: مبلغ جزئي للعكس (اختياري)
            
        Returns:
            JournalEntry: القيد العكسي الجديد
        """
        if not self.can_be_reversed:
            raise ValidationError(_("لا يمكن عكس هذا القيد"))
        
        # تحديد المبلغ المراد عكسه
        reversal_amount = partial_amount or self.total_amount
        if reversal_amount > self.total_amount:
            raise ValidationError(_("مبلغ العكس أكبر من المبلغ الأصلي"))
        
        # إنشاء القيد العكسي
        reversal_entry = JournalEntry(
            date=timezone.now().date(),
            entry_type='reversal',
            status='posted',  # القيود العكسية ترحل تلقائياً
            description=f"عكس القيد {self.number} - {reason}",
            reference=f"REV-{self.number}",
            source_module=self.source_module,
            source_model=self.source_model,
            source_id=self.source_id,
            accounting_period=AccountingPeriod.get_period_for_date(timezone.now().date()),
            original_entry=self,
            is_reversal=True,
            reversal_reason=reason,
            created_by_service='AccountingGateway',
            created_by=user,
            posted_at=timezone.now(),
            posted_by=user
        )
        
        # تمييز القيد كمعتمد من البوابة
        reversal_entry.mark_as_gateway_approved()
        reversal_entry.save()
        
        # إنشاء بنود القيد العكسي (عكس المدين والدائن)
        for original_line in self.lines.all():
            if partial_amount and partial_amount < self.total_amount:
                # حساب النسبة للعكس الجزئي
                ratio = partial_amount / self.total_amount
                line_debit = original_line.credit * ratio  # عكس المدين والدائن
                line_credit = original_line.debit * ratio
            else:
                # عكس كامل
                line_debit = original_line.credit
                line_credit = original_line.debit
            
            JournalEntryLine.objects.create(
                journal_entry=reversal_entry,
                account=original_line.account,
                debit=line_debit,
                credit=line_credit,
                description=f"عكس: {original_line.description}",
                cost_center=original_line.cost_center,
                project=original_line.project
            )
        
        # التحقق من توازن القيد العكسي
        reversal_entry.validate_entry()
        
        import logging
        logger = logging.getLogger(__name__)
        return reversal_entry

    def post(self, user=None):
        """ترحيل القيد"""
        if self.status == "posted":
            raise ValidationError(_("القيد مرحل بالفعل"))

        if self.status == "cancelled":
            raise ValidationError(_("لا يمكن ترحيل قيد ملغي"))

        # التحقق من صحة القيد
        self.validate_entry()

        # ترحيل القيد
        self.status = "posted"
        self.posted_at = timezone.now()
        self.posted_by = user
        
        # استخدام update_fields لتجنب validation الكامل
        # نحدث الحقول المطلوبة فقط بدون المرور على validate_period_lock
        self.save(update_fields=['status', 'posted_at', 'posted_by'])

        return True

    def cancel(self, user=None):
        """إلغاء القيد"""
        if self.status == "posted":
            raise ValidationError(_("لا يمكن إلغاء قيد مرحل"))

        self.status = "cancelled"
        self.save()

        return True

    def delete(self, *args, **kwargs):
        """حماية من الحذف المباشر مع تطبيق قفل الفترة"""
        # التحقق من قفل الفترة المحاسبية
        try:
            self.validate_period_lock()
        except ValidationError as e:
            # السماح بالحذف إذا كان هناك تجاوز صريح
            if not getattr(self, '_bypass_period_lock', False):
                raise e

        # السماح بالحذف للمسودات فقط
        if self.status == "draft":
            return super().delete(*args, **kwargs)

        # منع حذف القيود المرحلة
        if self.status == "posted":
            raise ValidationError(_("لا يمكن حذف قيد مرحل. استخدم العكس بدلاً من ذلك."))

        # منع حذف القيود الملغاة (للاحتفاظ بسجل)
        if self.status == "cancelled":
            raise ValidationError(_("لا يمكن حذف قيد ملغي. يتم الاحتفاظ به للسجلات."))

        return super().delete(*args, **kwargs)

    # الطرق المحسنة الجديدة
    def post_optimized(self, user=None, validate_balance=True, update_balances=True):
        """
        ترحيل محسن للقيد مع خيارات متقدمة
        
        الوسائط:
            user: المستخدم الذي يقوم بالترحيل
            validate_balance: التحقق من توازن القيد
            update_balances: تحديث أرصدة الحسابات
            
        العائد:
            tuple: (نجاح/فشل، رسالة، تفاصيل)
        """
        from django.db import transaction
        from django.utils import timezone
        from decimal import Decimal
        
        if self.status == "posted":
            return (False, "القيد مرحل بالفعل", None)
            
        if self.status == "cancelled":
            return (False, "لا يمكن ترحيل قيد ملغي", None)
            
        try:
            with transaction.atomic():
                # التحقق من صحة القيد إذا كان مطلوباً
                if validate_balance:
                    try:
                        self.validate_entry()
                    except ValidationError as e:
                        return (False, f"خطأ في التحقق: {'; '.join(e.messages)}", None)
                
                # تحديث أرصدة الحسابات إذا كان مطلوباً
                updated_accounts = []
                if update_balances:
                    for line in self.lines.select_related('account'):
                        account = line.account
                        amount = line.debit if line.debit > 0 else line.credit
                        operation = "add" if line.debit > 0 else "subtract"
                        
                        # استخدام الطريقة المحسنة لتحديث الرصيد
                        success, message, new_balance = account.update_balance_atomic(amount, operation)
                        if not success:
                            return (False, f"خطأ في تحديث رصيد الحساب {account.name}: {message}", None)
                        
                        updated_accounts.append({
                            'account': account.name,
                            'amount': amount,
                            'operation': operation,
                            'new_balance': new_balance
                        })
                
                # ترحيل القيد
                self.status = "posted"
                self.posted_at = timezone.now()
                self.posted_by = user
                self.save(update_fields=['status', 'posted_at', 'posted_by'])
                
                return (True, "تم ترحيل القيد بنجاح", {
                    'entry_number': self.number,
                    'posted_at': self.posted_at,
                    'updated_accounts': updated_accounts
                })
                
        except Exception as e:
            return (False, f"خطأ غير متوقع: {str(e)}", None)

    def validate_balance_optimized(self, check_accounts=True, check_period=True):
        """
        التحقق المحسن من توازن القيد مع فحوصات إضافية
        
        الوسائط:
            check_accounts: فحص صحة الحسابات
            check_period: فحص الفترة المحاسبية
            
        العائد:
            dict: نتائج التحقق المفصلة
        """
        from decimal import Decimal
        
        result = {
            'is_valid': True,
            'is_balanced': False,
            'total_debit': Decimal('0'),
            'total_credit': Decimal('0'),
            'difference': Decimal('0'),
            'errors': [],
            'warnings': [],
            'line_count': 0,
            'account_details': []
        }
        
        # فحص وجود البنود
        lines = self.lines.select_related('account', 'account__account_type')
        result['line_count'] = lines.count()
        
        if result['line_count'] == 0:
            result['is_valid'] = False
            result['errors'].append("القيد يجب أن يحتوي على بنود")
            return result
        
        # حساب المجاميع وفحص البنود
        for line in lines:
            result['total_debit'] += line.debit
            result['total_credit'] += line.credit
            
            # فحص صحة الحساب إذا كان مطلوباً
            if check_accounts:
                if not line.account.can_post_entries():
                    result['errors'].append(f"لا يمكن إدراج قيود على الحساب: {line.account.name}")
                    result['is_valid'] = False
                
                if not line.account.is_active:
                    result['warnings'].append(f"الحساب غير نشط: {line.account.name}")
            
            # إضافة تفاصيل الحساب
            result['account_details'].append({
                'account_code': line.account.code,
                'account_name': line.account.name,
                'debit': line.debit,
                'credit': line.credit,
                'is_active': line.account.is_active,
                'can_post': line.account.can_post_entries()
            })
        
        # فحص التوازن
        result['difference'] = result['total_debit'] - result['total_credit']
        result['is_balanced'] = result['difference'] == 0
        
        if not result['is_balanced']:
            result['is_valid'] = False
            result['errors'].append(f"القيد غير متوازن: الفرق = {result['difference']}")
        
        # فحص الفترة المحاسبية إذا كان مطلوباً
        if check_period and self.accounting_period:
            if not self.accounting_period.can_post_entries():
                result['is_valid'] = False
                result['errors'].append("لا يمكن إدراج قيود في فترة مغلقة")
            
            if not self.accounting_period.is_date_in_period(self.date):
                result['warnings'].append("تاريخ القيد خارج نطاق الفترة المحاسبية")
        
        return result

    def set_source(self, module, model, object_id):
        """
        ربط القيد بمصدره (الوحدة والنموذج والكائن)
        
        الوسائط:
            module: اسم الوحدة (client, hr, transportation, etc.)
            model: اسم النموذج (CustomerPayment, SalaryPayment, etc.)
            object_id: معرف الكائن
        """
        self.source_module = module
        self.source_model = model
        self.source_id = object_id
        self.save(update_fields=['source_module', 'source_model', 'source_id'])

    def get_source_object(self):
        """
        الحصول على الكائن المصدر للقيد
        
        العائد:
            object أو None: الكائن المصدر إذا كان موجوداً
        """
        if not all([self.source_module, self.source_model, self.source_id]):
            return None
            
        try:
            from django.apps import apps
            model_class = apps.get_model(self.source_module, self.source_model)
            return model_class.objects.get(id=self.source_id)
        except Exception:
            return None

    def validate_source_linkage(self):
        """
        التحقق من صحة ربط المصدر باستخدام SourceLinkage contract
        
        العائد:
            bool: True إذا كان الربط صحيح، False إذا لم يكن
        """
        if not all([self.source_module, self.source_model, self.source_id]):
            return False
        
        # Skip validation for ManualJournalEntry (virtual model)
        if self.source_module == 'financial' and self.source_model == 'ManualJournalEntry':
            return True
            
        try:
            from governance.services import SourceLinkageService
            return SourceLinkageService.validate_linkage(
                self.source_module, 
                self.source_model, 
                self.source_id
            )
        except Exception:
            return False
    
    def is_orphaned(self):
        """
        التحقق من كون القيد يتيم (بدون ربط صحيح بالمصدر)
        
        العائد:
            bool: True إذا كان القيد يتيم
        """
        return not self.validate_source_linkage()
    
    def get_source_linkage_info(self):
        """
        الحصول على معلومات ربط المصدر
        
        العائد:
            dict: معلومات الربط أو None إذا لم يكن موجود
        """
        if not all([self.source_module, self.source_model, self.source_id]):
            return None
            
        try:
            from governance.services import SourceLinkageService
            return SourceLinkageService.get_source_model_info(
                self.source_module, 
                self.source_model
            )
        except Exception:
            return None

    def get_related_entries(self):
        """
        الحصول على القيود المرتبطة بنفس المصدر
        
        العائد:
            QuerySet: القيود المرتبطة
        """
        if not all([self.source_module, self.source_model, self.source_id]):
            return JournalEntry.objects.none()
            
        return JournalEntry.objects.filter(
            source_module=self.source_module,
            source_model=self.source_model,
            source_id=self.source_id
        ).exclude(id=self.id)
    
    # طرق الحوكمة والحماية من التكرار
    
    def set_idempotency_key(self, key):
        """
        تعيين مفتاح منع التكرار
        
        الوسائط:
            key: مفتاح منع التكرار
        """
        self.idempotency_key = key
        self.save(update_fields=['idempotency_key'])
    
    def mark_as_gateway_approved(self):
        """
        تمييز القيد كمعتمد من البوابة المخولة
        يستخدم لتجنب تحذيرات التطوير
        """
        self._gateway_approved = True
    
    def bypass_period_lock(self):
        """
        تجاوز قفل الفترة المحاسبية للعمليات النظامية
        يستخدم فقط للقيود العكسية أو العمليات الإدارية المخولة
        """
        self._bypass_period_lock = True
    
    def validate_governance_rules(self):
        """
        التحقق من قواعد الحوكمة
        
        العائد:
            dict: نتائج التحقق
        """
        result = {
            'is_valid': True,
            'warnings': [],
            'errors': []
        }
        
        # التحقق من وجود مفتاح منع التكرار للقيود الحساسة
        if self.entry_type in ['automatic', 'application_fee', 'tuition_fee', 'product_delivery']:
            if not self.idempotency_key:
                result['warnings'].append("القيد الحساس بدون مفتاح منع التكرار")
        
        # التحقق من صحة ربط المصدر
        if not self.validate_source_linkage():
            result['errors'].append("ربط المصدر غير صحيح")
            result['is_valid'] = False
        
        # التحقق من الخدمة المنشئة
        if not self.created_by_service:
            result['warnings'].append("الخدمة المنشئة غير محددة")
        
        return result


class JournalEntryLine(models.Model):
    """
    بنود القيود اليومية
    """

    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        verbose_name=_("القيد اليومي"),
        related_name="lines",
    )

    account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        verbose_name=_("الحساب"),
        related_name="journal_lines",
    )

    debit = models.DecimalField(
        _("مدين"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    credit = models.DecimalField(
        _("دائن"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    description = models.TextField(_("البيان"), blank=True, null=True)

    # معلومات إضافية
    cost_center = models.CharField(
        _("مركز التكلفة"), max_length=50, blank=True, null=True
    )
    project = models.CharField(_("المشروع"), max_length=50, blank=True, null=True)

    # معلومات التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("بند قيد")
        verbose_name_plural = _("بنود القيود")
        indexes = [
            models.Index(fields=["account", "journal_entry"]),
            models.Index(fields=["journal_entry"]),
        ]

    def __str__(self):
        amount = self.debit if self.debit > 0 else self.credit
        return f"{self.account.code} - {amount}"

    def clean(self):
        """التحقق من صحة البند"""
        self.validate_line()

    def validate_line(self):
        """التحقق من صحة بند القيد"""
        # التحقق من أن الحساب يمكن إدراج قيود عليه
        if not self.account.can_post_entries():
            raise ValidationError(_("لا يمكن إدراج قيود على هذا الحساب"))

        # التحقق من صحة المبالغ
        if self.debit < 0 or self.credit < 0:
            raise ValidationError(_("المبالغ يجب أن تكون موجبة"))

        if self.debit > 0 and self.credit > 0:
            raise ValidationError(_("لا يمكن أن يكون البند مدين ودائن في نفس الوقت"))

        if self.debit == 0 and self.credit == 0:
            raise ValidationError(_("يجب أن يكون للبند مبلغ مدين أو دائن"))

        return True

    @property
    def amount(self):
        """المبلغ (مدين أو دائن)"""
        return self.debit if self.debit > 0 else self.credit

    @property
    def is_debit(self):
        """هل البند مدين"""
        return self.debit > 0

    @property
    def is_credit(self):
        """هل البند دائن"""
        return self.credit > 0


class JournalEntryTemplate(models.Model):
    """
    قوالب القيود اليومية المتكررة
    """

    name = models.CharField(_("اسم القالب"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True, null=True)
    entry_type = models.CharField(
        _("نوع القيد"),
        max_length=20,
        choices=JournalEntry.ENTRY_TYPES,
        default="manual",
    )

    is_active = models.BooleanField(_("نشط"), default=True)

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="entry_templates_created",
    )

    class Meta:
        verbose_name = _("قالب قيد")
        verbose_name_plural = _("قوالب القيود")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def create_entry(self, date=None, description=None, reference=None, user=None):
        """إنشاء قيد من القالب"""
        entry = JournalEntry.objects.create(
            date=date or timezone.now().date(),
            entry_type=self.entry_type,
            description=description or self.description,
            reference=reference,
            created_by=user,
        )

        # نسخ بنود القالب
        for template_line in self.lines.all():
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=template_line.account,
                debit=template_line.debit,
                credit=template_line.credit,
                description=template_line.description,
            )

        return entry


class JournalEntryTemplateLine(models.Model):
    """
    بنود قوالب القيود
    """

    template = models.ForeignKey(
        JournalEntryTemplate,
        on_delete=models.CASCADE,
        verbose_name=_("القالب"),
        related_name="lines",
    )

    account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        verbose_name=_("الحساب"),
        related_name="template_lines",
    )

    debit = models.DecimalField(
        _("مدين"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    credit = models.DecimalField(
        _("دائن"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
    )

    description = models.TextField(_("البيان"), blank=True, null=True)

    class Meta:
        verbose_name = _("بند قالب قيد")
        verbose_name_plural = _("بنود قوالب القيود")

    def __str__(self):
        amount = self.debit if self.debit > 0 else self.credit
        return f"{self.account.code} - {amount}"
