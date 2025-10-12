from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal

from .chart_of_accounts import ChartOfAccounts
from .categories import FinancialCategory
from .journal_entry import JournalEntry

User = settings.AUTH_USER_MODEL


class FinancialTransaction(models.Model):
    """
    نموذج أساسي للمعاملات المالية المحسن
    """
    TRANSACTION_TYPES = (
        ('income', _('إيراد')),
        ('expense', _('مصروف')),
        ('transfer', _('تحويل')),
        ('adjustment', _('تسوية')),
    )
    
    PRIORITY_CHOICES = (
        ('high', _('عالية')),
        ('medium', _('متوسطة')),
        ('low', _('منخفضة')),
    )
    
    # المعلومات الأساسية
    transaction_type = models.CharField(_('نوع المعاملة'), max_length=20, choices=TRANSACTION_TYPES)
    title = models.CharField(_('العنوان'), max_length=200)
    description = models.TextField(_('الوصف'), blank=True, null=True)
    
    # الحسابات
    account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, 
                               related_name='financial_transactions', verbose_name=_('الحساب الرئيسي'))
    to_account = models.ForeignKey(ChartOfAccounts, on_delete=models.PROTECT, 
                                  related_name='incoming_financial_transactions', 
                                  null=True, blank=True, verbose_name=_('الحساب المستلم'))
    
    # المبلغ والتاريخ
    amount = models.DecimalField(_('المبلغ'), max_digits=15, decimal_places=2, 
                               validators=[MinValueValidator(Decimal('0.01'))])
    date = models.DateField(_('التاريخ'), default=timezone.now)
    due_date = models.DateField(_('تاريخ الاستحقاق'), null=True, blank=True)
    
    # التصنيف
    category = models.ForeignKey(FinancialCategory, on_delete=models.SET_NULL, 
                               null=True, blank=True, verbose_name=_('التصنيف'))
    priority = models.CharField(_('الأولوية'), max_length=10, choices=PRIORITY_CHOICES, default='medium')
    
    # المراجع
    reference_number = models.CharField(_('رقم المرجع'), max_length=100, blank=True, null=True)
    external_reference = models.CharField(_('المرجع الخارجي'), max_length=100, blank=True, null=True)
    invoice_number = models.CharField(_('رقم الفاتورة'), max_length=100, blank=True, null=True)
    
    # الحالة والموافقة
    STATUS_CHOICES = (
        ('draft', _('مسودة')),
        ('pending', _('قيد الانتظار')),
        ('approved', _('معتمد')),
        ('processed', _('منفذ')),
        ('cancelled', _('ملغي')),
        ('rejected', _('مرفوض')),
    )
    
    status = models.CharField(_('الحالة'), max_length=20, choices=STATUS_CHOICES, default='draft')
    requires_approval = models.BooleanField(_('يتطلب موافقة'), default=False)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   verbose_name=_('اعتمد بواسطة'), related_name='approved_transactions')
    approved_at = models.DateTimeField(_('تاريخ الاعتماد'), null=True, blank=True)
    
    # القيد المحاسبي المرتبط
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL, 
                                     null=True, blank=True, verbose_name=_('القيد المحاسبي'))
    
    # معلومات إضافية
    tags = models.CharField(_('العلامات'), max_length=200, blank=True, null=True,
                           help_text=_('علامات مفصولة بفواصل'))
    attachments_count = models.PositiveIntegerField(_('عدد المرفقات'), default=0)
    
    # معلومات خاصة بالمصروفات والإيرادات
    vendor_name = models.CharField(_('اسم المورد/العميل'), max_length=200, blank=True, null=True)
    vendor_contact = models.CharField(_('جهة الاتصال'), max_length=100, blank=True, null=True)
    payment_method = models.CharField(_('طريقة الدفع'), max_length=50, blank=True, null=True)
    payment_date = models.DateField(_('تاريخ الدفع/الاستلام'), null=True, blank=True)
    
    # الضرائب والخصومات
    tax_amount = models.DecimalField(_('مبلغ الضريبة'), max_digits=15, decimal_places=2, default=0)
    discount_amount = models.DecimalField(_('مبلغ الخصم'), max_digits=15, decimal_places=2, default=0)
    net_amount = models.DecimalField(_('المبلغ الصافي'), max_digits=15, decimal_places=2, default=0)
    
    # التتبع
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                  verbose_name=_('أنشئ بواسطة'), related_name='created_financial_transactions')
    
    class Meta:
        verbose_name = _('معاملة مالية')
        verbose_name_plural = _('المعاملات المالية')
        ordering = ['-date', '-created_at']
        db_table = 'financial_transaction'  # تحديد اسم الجدول صراحة
        # تم إزالة الـ indexes المشكلة مؤقتاً
        # indexes = [
        #     models.Index(fields=['transaction_type', 'date']),
        #     models.Index(fields=['status', 'created_at']),
        #     models.Index(fields=['account', 'date']),
        # ]
    
    def __str__(self):
        return f"{self.title} - {self.amount} ({self.get_transaction_type_display()})"
    
    def save(self, *args, **kwargs):
        # تحديد ما إذا كانت المعاملة تتطلب موافقة
        if not self.pk and self.amount >= Decimal('1000.00'):  # مبلغ افتراضي يتطلب موافقة
            self.requires_approval = True
        
        # حساب المبلغ الصافي
        self.net_amount = self.amount + self.tax_amount - self.discount_amount
            
        super().save(*args, **kwargs)
    
    def approve(self, approved_by_user):
        """اعتماد المعاملة"""
        if self.status != 'pending':
            raise ValueError(_('يمكن اعتماد المعاملات المعلقة فقط'))
            
        self.status = 'approved'
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.save(update_fields=['status', 'approved_by', 'approved_at'])
    
    def reject(self):
        """رفض المعاملة"""
        if self.status not in ['pending', 'draft']:
            raise ValueError(_('يمكن رفض المعاملات المعلقة أو المسودات فقط'))
            
        self.status = 'rejected'
        self.save(update_fields=['status'])
    
    def process(self):
        """تنفيذ المعاملة وإنشاء القيد المحاسبي"""
        if self.status != 'approved':
            raise ValueError(_('يجب اعتماد المعاملة قبل التنفيذ'))
        
        if self.journal_entry:
            raise ValueError(_('تم تنفيذ هذه المعاملة مسبقاً'))
        
        # إنشاء القيد المحاسبي
        journal_entry = self.create_journal_entry()
        if journal_entry:
            self.journal_entry = journal_entry
            self.status = 'processed'
            self.save(update_fields=['journal_entry', 'status'])
            return True
        
        return False
    
    def create_journal_entry(self):
        """إنشاء القيد المحاسبي للمعاملة"""
        from .journal_entry import JournalEntryLine
        
        try:
            # إنشاء القيد الرئيسي
            entry = JournalEntry.objects.create(
                reference=f"{self.get_transaction_type_display()} - {self.reference_number or self.id}",
                description=f"{self.title} - {self.description or ''}",
                date=self.date,
                created_by=self.created_by
            )
            
            if self.transaction_type == 'income':
                # مدين: الحساب المستلم (نقدي/بنكي)
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=self.account,
                    debit=self.amount,
                    credit=0,
                    description=self.title
                )
                
                # دائن: حساب الإيرادات
                revenue_account = self._get_revenue_account()
                if revenue_account:
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=revenue_account,
                        debit=0,
                        credit=self.amount,
                        description=self.title
                    )
            
            elif self.transaction_type == 'expense':
                # مدين: حساب المصروفات
                expense_account = self._get_expense_account()
                if expense_account:
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=expense_account,
                        debit=self.amount,
                        credit=0,
                        description=self.title
                    )
                
                # دائن: الحساب الدافع (نقدي/بنكي)
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=self.account,
                    debit=0,
                    credit=self.amount,
                    description=self.title
                )
            
            elif self.transaction_type == 'transfer':
                # مدين: الحساب المستلم
                if self.to_account:
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=self.to_account,
                        debit=self.amount,
                        credit=0,
                        description=self.title
                    )
                
                # دائن: الحساب المرسل
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=self.account,
                    debit=0,
                    credit=self.amount,
                    description=self.title
                )
            
            return entry
            
        except Exception as e:
            # في حالة حدوث خطأ، احذف القيد إذا تم إنشاؤه
            if 'entry' in locals():
                entry.delete()
            raise e
    
    def _get_revenue_account(self):
        """الحصول على حساب الإيرادات المناسب"""
        try:
            # البحث عن حساب إيرادات مناسب
            revenue_accounts = ChartOfAccounts.objects.filter(
                account_type__name__icontains='إيراد'
            ).first()
            return revenue_accounts
        except:
            return None
    
    def _get_expense_account(self):
        """الحصول على حساب المصروفات المناسب"""
        try:
            # البحث عن حساب مصروفات مناسب
            expense_accounts = ChartOfAccounts.objects.filter(
                account_type__name__icontains='مصروف'
            ).first()
            return expense_accounts
        except:
            return None
    
    def cancel(self):
        """إلغاء المعاملة"""
        if self.status == 'processed':
            raise ValueError(_('لا يمكن إلغاء معاملة منفذة'))
        
        self.status = 'cancelled'
        self.save(update_fields=['status'])
    
    @property
    def is_overdue(self):
        """هل المعاملة متأخرة"""
        if self.due_date and self.status not in ['processed', 'cancelled']:
            return timezone.now().date() > self.due_date
        return False
    
    @property
    def days_until_due(self):
        """عدد الأيام حتى الاستحقاق"""
        if self.due_date:
            delta = self.due_date - timezone.now().date()
            return delta.days
        return None


class ExpenseTransaction(FinancialTransaction):
    """
    نموذج متخصص للمصروفات
    """
    class Meta:
        proxy = True
        verbose_name = _('مصروف')
        verbose_name_plural = _('المصروفات')
    
    def save(self, *args, **kwargs):
        self.transaction_type = 'expense'
        super().save(*args, **kwargs)


class IncomeTransaction(FinancialTransaction):
    """
    نموذج متخصص للإيرادات
    """
    class Meta:
        proxy = True
        verbose_name = _('إيراد')
        verbose_name_plural = _('الإيرادات')
    
    def save(self, *args, **kwargs):
        self.transaction_type = 'income'
        super().save(*args, **kwargs)


class TransactionAttachment(models.Model):
    """
    مرفقات المعاملات المالية
    """
    transaction = models.ForeignKey(FinancialTransaction, on_delete=models.CASCADE,
                                  verbose_name=_('المعاملة'), related_name='attachments')
    
    file = models.FileField(_('الملف'), upload_to='financial/transactions/%Y/%m/')
    file_name = models.CharField(_('اسم الملف'), max_length=255)
    file_size = models.PositiveIntegerField(_('حجم الملف'), help_text=_('بالبايت'))
    file_type = models.CharField(_('نوع الملف'), max_length=50, blank=True, null=True)
    
    description = models.CharField(_('الوصف'), max_length=255, blank=True, null=True)
    
    uploaded_at = models.DateTimeField(_('تاريخ الرفع'), auto_now_add=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                  verbose_name=_('رفع بواسطة'))
    
    class Meta:
        verbose_name = _('مرفق معاملة')
        verbose_name_plural = _('مرفقات المعاملات')
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.transaction.title} - {self.file_name}"
    
    def save(self, *args, **kwargs):
        if self.file:
            self.file_size = self.file.size
            self.file_name = self.file.name
        super().save(*args, **kwargs)
        
        # تحديث عدد المرفقات في المعاملة
        self.transaction.attachments_count = self.transaction.attachments.count()
        self.transaction.save(update_fields=['attachments_count'])
