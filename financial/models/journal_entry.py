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
        ('open', _('مفتوحة')),
        ('closed', _('مغلقة')),
    )
    
    name = models.CharField(_('اسم الفترة'), max_length=100)
    start_date = models.DateField(_('تاريخ البداية'))
    end_date = models.DateField(_('تاريخ النهاية'))
    status = models.CharField(_('الحالة'), max_length=10, choices=STATUS_CHOICES, default='open')
    
    # معلومات الإغلاق
    closed_at = models.DateTimeField(_('تاريخ الإغلاق'), null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                verbose_name=_('أغلق بواسطة'), related_name='periods_closed')
    
    # معلومات التتبع
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                 verbose_name=_('أنشئ بواسطة'), related_name='periods_created')
    
    class Meta:
        verbose_name = _('فترة محاسبية')
        verbose_name_plural = _('الفترات المحاسبية')
        ordering = ['-start_date']
        unique_together = ['start_date', 'end_date']
    
    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"
    
    def clean(self):
        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError(_('تاريخ البداية يجب أن يكون قبل تاريخ النهاية'))
    
    def is_date_in_period(self, date):
        """التحقق من وجود التاريخ ضمن الفترة"""
        return self.start_date <= date <= self.end_date
    
    def can_post_entries(self):
        """التحقق من إمكانية إدراج قيود في الفترة"""
        return self.status == 'open'
    
    @property
    def is_active(self):
        """هل الفترة نشطة"""
        return self.status == 'open'
    
    @property
    def is_closed(self):
        """هل الفترة مغلقة"""
        return self.status == 'closed'
    
    @classmethod
    def get_period_for_date(cls, date):
        """الحصول على الفترة المحاسبية لتاريخ معين"""
        return cls.objects.filter(
            start_date__lte=date,
            end_date__gte=date
        ).first()


class JournalEntry(models.Model):
    """
    القيود اليومية (Journal Entries)
    """
    ENTRY_TYPES = (
        ('manual', _('يدوي')),
        ('automatic', _('تلقائي')),
        ('adjustment', _('تسوية')),
        ('closing', _('إقفال')),
        ('opening', _('افتتاحي')),
    )
    
    def __init__(self, *args, **kwargs):
        # تصحيح تلقائي للـ arguments الشائعة (للتوافق مع الأنظمة القديمة)
        if 'reference_number' in kwargs:
            kwargs['reference'] = kwargs.pop('reference_number')
        if 'entry_date' in kwargs:
            kwargs['date'] = kwargs.pop('entry_date')
                
        super().__init__(*args, **kwargs)
    
    STATUS_CHOICES = (
        ('draft', _('مسودة')),
        ('posted', _('مرحل')),
        ('cancelled', _('ملغي')),
    )
    
    # معلومات القيد الأساسية
    number = models.CharField(_('رقم القيد'), max_length=20, unique=True)
    date = models.DateField(_('التاريخ'), default=timezone.now)
    entry_type = models.CharField(_('نوع القيد'), max_length=20, choices=ENTRY_TYPES, default='manual')
    status = models.CharField(_('الحالة'), max_length=10, choices=STATUS_CHOICES, default='draft')
    
    # الوصف والمرجع
    description = models.TextField(_('البيان'))
    reference = models.CharField(_('المرجع'), max_length=100, blank=True, null=True)
    reference_type = models.CharField(_('نوع المرجع'), max_length=50, blank=True, null=True)
    reference_id = models.PositiveIntegerField(_('معرف المرجع'), blank=True, null=True)
    notes = models.TextField(_('ملاحظات'), blank=True, null=True, help_text=_('ملاحظات إضافية على القيد'))
    
    # الفترة المحاسبية
    accounting_period = models.ForeignKey(AccountingPeriod, on_delete=models.PROTECT,
                                        verbose_name=_('الفترة المحاسبية'), related_name='journal_entries')
    
    # معلومات الترحيل
    posted_at = models.DateTimeField(_('تاريخ الترحيل'), null=True, blank=True)
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                verbose_name=_('رحل بواسطة'), related_name='entries_posted')
    
    # معلومات التتبع
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                 verbose_name=_('أنشئ بواسطة'), related_name='entries_created')
    
    
    class Meta:
        verbose_name = _('قيد يومي')
        verbose_name_plural = _('القيود اليومية')
        ordering = ['-date', '-number']
        indexes = [
            models.Index(fields=['date', 'status']),
            models.Index(fields=['number']),
            models.Index(fields=['reference_type', 'reference_id']),
        ]
    
    def __str__(self):
        return f"{self.number} - {self.date} - {self.description[:50]}"
    
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
                    raise ValidationError(_('لا توجد فترة محاسبية مفتوحة لهذا التاريخ'))
                self.accounting_period = period
        except AccountingPeriod.DoesNotExist:
            # إذا لم تكن الفترة موجودة، ابحث عن واحدة
            period = AccountingPeriod.get_period_for_date(self.date)
            if not period:
                raise ValidationError(_('لا توجد فترة محاسبية مفتوحة لهذا التاريخ'))
            self.accounting_period = period
        
        super().save(*args, **kwargs)
    
    def generate_entry_number(self):
        """
        توليد رقم القيد تلقائياً
        التنسيق: JE-25-0001 (سنتين + رقم تسلسلي)
        """
        year = self.date.year if self.date else timezone.now().year
        year_short = str(year)[-2:]  # آخر رقمين من السنة
        
        # البحث عن أعلى رقم في السنة الحالية
        entries = JournalEntry.objects.filter(
            date__year=year,
            number__startswith=f'JE-{year_short}-'
        ).exclude(pk=self.pk if self.pk else None)
        
        max_number = 0
        for entry in entries:
            try:
                # استخراج الرقم من نهاية اسم القيد
                number_part = entry.number.split('-')[-1]
                current_number = int(number_part)
                if current_number > max_number:
                    max_number = current_number
            except (ValueError, IndexError):
                continue
        
        new_number = max_number + 1
        
        # التأكد من عدم تكرار الرقم
        while True:
            candidate_number = f"JE-{year_short}-{new_number:04d}"
            if not JournalEntry.objects.filter(number=candidate_number).exclude(pk=self.pk if self.pk else None).exists():
                return candidate_number
            new_number += 1
    
    @property
    def total_debit(self):
        """إجمالي المدين"""
        return self.lines.aggregate(models.Sum('debit'))['debit__sum'] or Decimal('0')
    
    @property
    def total_credit(self):
        """إجمالي الدائن"""
        return self.lines.aggregate(models.Sum('credit'))['credit__sum'] or Decimal('0')
    
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
        return self.status == 'posted'
    
    
    def validate_entry(self):
        """التحقق من صحة القيد"""
        errors = []
        
        # التحقق من وجود بنود
        if not self.lines.exists():
            errors.append(_('القيد يجب أن يحتوي على بنود'))
        
        # التحقق من التوازن
        if not self.is_balanced:
            errors.append(_('القيد غير متوازن: الفرق = {}'.format(self.difference)))
        
        # التحقق من الفترة المحاسبية
        try:
            if self.accounting_period_id and self.accounting_period and not self.accounting_period.can_post_entries():
                errors.append(_('لا يمكن إدراج قيود في فترة مغلقة'))
        except AccountingPeriod.DoesNotExist:
            errors.append(_('الفترة المحاسبية غير موجودة'))
        
        # التحقق من صحة البنود
        for line in self.lines.all():
            try:
                line.validate_line()
            except ValidationError as e:
                errors.extend(e.messages)
        
        if errors:
            raise ValidationError(errors)
        
        return True
    
    def post(self, user=None):
        """ترحيل القيد"""
        if self.status == 'posted':
            raise ValidationError(_('القيد مرحل بالفعل'))
        
        if self.status == 'cancelled':
            raise ValidationError(_('لا يمكن ترحيل قيد ملغي'))
        
        # التحقق من صحة القيد
        self.validate_entry()
        
        # ترحيل القيد
        self.status = 'posted'
        self.posted_at = timezone.now()
        self.posted_by = user
        self.save()
        
        return True
    
    def cancel(self, user=None):
        """إلغاء القيد"""
        if self.status == 'posted':
            raise ValidationError(_('لا يمكن إلغاء قيد مرحل'))
        
        self.status = 'cancelled'
        self.save()
        
        return True
    
    
    def delete(self, *args, **kwargs):
        """حماية من الحذف المباشر"""
        # السماح بالحذف للمسودات فقط
        if self.status == 'draft':
            return super().delete(*args, **kwargs)
        
        # منع حذف القيود المرحلة
        if self.status == 'posted':
            raise ValidationError(
                _('لا يمكن حذف قيد مرحل.')
            )
        
        # منع حذف القيود الملغاة (للاحتفاظ بسجل)
        if self.status == 'cancelled':
            raise ValidationError(
                _('لا يمكن حذف قيد ملغي. يتم الاحتفاظ به للسجلات.')
            )
        
        return super().delete(*args, **kwargs)
    
    def can_be_deleted(self):
        """التحقق من إمكانية الحذف"""
        return self.status == 'draft'


class JournalEntryLine(models.Model):
    """
    بنود القيود اليومية
    """
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE,
                                    verbose_name=_('القيد اليومي'), related_name='lines')
    
    account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT,
                              verbose_name=_('الحساب'), related_name='journal_lines')
    
    debit = models.DecimalField(_('مدين'), max_digits=15, decimal_places=2, 
                              default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])
    credit = models.DecimalField(_('دائن'), max_digits=15, decimal_places=2,
                               default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])
    
    description = models.TextField(_('البيان'), blank=True, null=True)
    
    # معلومات إضافية
    cost_center = models.CharField(_('مركز التكلفة'), max_length=50, blank=True, null=True)
    project = models.CharField(_('المشروع'), max_length=50, blank=True, null=True)
    
    # معلومات التتبع
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('بند قيد')
        verbose_name_plural = _('بنود القيود')
        indexes = [
            models.Index(fields=['account', 'journal_entry']),
            models.Index(fields=['journal_entry']),
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
            raise ValidationError(_('لا يمكن إدراج قيود على هذا الحساب'))
        
        # التحقق من صحة المبالغ
        if self.debit < 0 or self.credit < 0:
            raise ValidationError(_('المبالغ يجب أن تكون موجبة'))
        
        if self.debit > 0 and self.credit > 0:
            raise ValidationError(_('لا يمكن أن يكون البند مدين ودائن في نفس الوقت'))
        
        if self.debit == 0 and self.credit == 0:
            raise ValidationError(_('يجب أن يكون للبند مبلغ مدين أو دائن'))
        
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
    name = models.CharField(_('اسم القالب'), max_length=100)
    description = models.TextField(_('الوصف'), blank=True, null=True)
    entry_type = models.CharField(_('نوع القيد'), max_length=20, 
                                choices=JournalEntry.ENTRY_TYPES, default='manual')
    
    is_active = models.BooleanField(_('نشط'), default=True)
    
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                 verbose_name=_('أنشئ بواسطة'), related_name='entry_templates_created')
    
    class Meta:
        verbose_name = _('قالب قيد')
        verbose_name_plural = _('قوالب القيود')
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def create_entry(self, date=None, description=None, reference=None, user=None):
        """إنشاء قيد من القالب"""
        entry = JournalEntry.objects.create(
            date=date or timezone.now().date(),
            entry_type=self.entry_type,
            description=description or self.description,
            reference=reference,
            created_by=user
        )
        
        # نسخ بنود القالب
        for template_line in self.lines.all():
            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=template_line.account,
                debit=template_line.debit,
                credit=template_line.credit,
                description=template_line.description
            )
        
        return entry


class JournalEntryTemplateLine(models.Model):
    """
    بنود قوالب القيود
    """
    template = models.ForeignKey(JournalEntryTemplate, on_delete=models.CASCADE,
                               verbose_name=_('القالب'), related_name='lines')
    
    account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT,
                              verbose_name=_('الحساب'), related_name='template_lines')
    
    debit = models.DecimalField(_('مدين'), max_digits=15, decimal_places=2,
                              default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])
    credit = models.DecimalField(_('دائن'), max_digits=15, decimal_places=2,
                               default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))])
    
    description = models.TextField(_('البيان'), blank=True, null=True)
    
    class Meta:
        verbose_name = _('بند قالب قيد')
        verbose_name_plural = _('بنود قوالب القيود')
    
    def __str__(self):
        amount = self.debit if self.debit > 0 else self.credit
        return f"{self.account.code} - {amount}"
