"""
نموذج التسوية البنكية
مستعاد من النظام القديم مع تحسينات للنظام الجديد
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from .chart_of_accounts import ChartOfAccounts

User = settings.AUTH_USER_MODEL


class BankReconciliation(models.Model):
    """
    نموذج التسوية البنكية
    يسجل عمليات التسوية بين رصيد النظام ورصيد البنك
    """
    account = models.ForeignKey(
        ChartOfAccounts, 
        on_delete=models.CASCADE, 
        verbose_name=_('الحساب'), 
        related_name='bank_reconciliations'
    )
    reconciliation_date = models.DateField(
        _('تاريخ التسوية'), 
        default=timezone.now
    )
    system_balance = models.DecimalField(
        _('رصيد النظام'), 
        max_digits=15, 
        decimal_places=2
    )
    bank_balance = models.DecimalField(
        _('رصيد البنك'), 
        max_digits=15, 
        decimal_places=2
    )
    difference = models.DecimalField(
        _('الفرق'), 
        max_digits=15, 
        decimal_places=2
    )
    
    # تفاصيل إضافية
    bank_statement_reference = models.CharField(
        _('مرجع كشف الحساب'), 
        max_length=100, 
        blank=True, 
        null=True
    )
    notes = models.TextField(
        _('ملاحظات'), 
        blank=True, 
        null=True
    )
    
    # حالة التسوية
    STATUS_CHOICES = (
        ('pending', _('قيد المراجعة')),
        ('approved', _('معتمدة')),
        ('rejected', _('مرفوضة')),
    )
    status = models.CharField(
        _('الحالة'), 
        max_length=20, 
        choices=STATUS_CHOICES, 
        default='pending'
    )
    
    # القيد المحاسبي المرتبط
    journal_entry = models.ForeignKey(
        'JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('القيد المحاسبي'),
        related_name='bank_reconciliations'
    )
    
    # معلومات التتبع
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    updated_at = models.DateTimeField(_('تاريخ التحديث'), auto_now=True)
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        verbose_name=_('أنشئ بواسطة'), 
        related_name='bank_reconciliations'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('اعتمد بواسطة'),
        related_name='approved_reconciliations'
    )
    approved_at = models.DateTimeField(
        _('تاريخ الاعتماد'),
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _('تسوية بنكية')
        verbose_name_plural = _('التسويات البنكية')
        ordering = ['-reconciliation_date', '-created_at']
        indexes = [
            models.Index(fields=['account', 'reconciliation_date']),
            models.Index(fields=['status', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.account.name} - {self.reconciliation_date} - {self.difference}"
    
    def save(self, *args, **kwargs):
        # حساب الفرق تلقائياً
        if self.system_balance is not None and self.bank_balance is not None:
            self.difference = self.bank_balance - self.system_balance
        
        super().save(*args, **kwargs)
    
    @property
    def is_balanced(self):
        """التحقق من توازن التسوية"""
        return self.difference == 0
    
    @property
    def difference_type(self):
        """نوع الفرق (زيادة/نقص)"""
        if self.difference > 0:
            return 'زيادة'
        elif self.difference < 0:
            return 'نقص'
        return 'متوازن'
    
    @property
    def difference_abs(self):
        """القيمة المطلقة للفرق"""
        return abs(self.difference)
    
    def approve(self, approved_by_user):
        """اعتماد التسوية"""
        self.status = 'approved'
        self.approved_by = approved_by_user
        self.approved_at = timezone.now()
        self.save(update_fields=['status', 'approved_by', 'approved_at'])
    
    def reject(self):
        """رفض التسوية"""
        self.status = 'rejected'
        self.save(update_fields=['status'])
    
    def create_journal_entry(self):
        """إنشاء قيد محاسبي للتسوية"""
        if self.difference == 0 or self.journal_entry:
            return None
        
        from .journal_entry import JournalEntry, JournalEntryLine
        
        try:
            # إنشاء قيد التسوية
            reconciliation_entry = JournalEntry.objects.create(
                reference=f"تسوية بنكية - {self.account.name}",
                description=f"تسوية بنكية بتاريخ {self.reconciliation_date} - فرق {self.difference}",
                date=self.reconciliation_date
            )
            
            # إضافة بند القيد
            if self.difference > 0:
                # رصيد البنك أكبر - مدين الحساب البنكي
                JournalEntryLine.objects.create(
                    journal_entry=reconciliation_entry,
                    account=self.account,
                    debit=self.difference,
                    credit=0,
                    description="تسوية بنكية - زيادة في الرصيد"
                )
                
                # نحتاج حساب مقابل (يمكن إنشاء حساب "فروقات تسوية بنكية")
                # هنا يمكن إضافة منطق لاختيار الحساب المقابل
                
            else:
                # رصيد البنك أقل - دائن الحساب البنكي
                JournalEntryLine.objects.create(
                    journal_entry=reconciliation_entry,
                    account=self.account,
                    debit=0,
                    credit=abs(self.difference),
                    description="تسوية بنكية - نقص في الرصيد"
                )
            
            # ربط القيد بالتسوية
            self.journal_entry = reconciliation_entry
            self.save(update_fields=['journal_entry'])
            
            return reconciliation_entry
            
        except Exception as e:
            print(f"خطأ في إنشاء قيد التسوية: {str(e)}")
            return None


class BankReconciliationItem(models.Model):
    """
    بنود التسوية البنكية
    للتفاصيل الدقيقة لكل تسوية
    """
    reconciliation = models.ForeignKey(
        BankReconciliation,
        on_delete=models.CASCADE,
        verbose_name=_('التسوية'),
        related_name='items'
    )
    
    ITEM_TYPES = (
        ('deposit_in_transit', _('إيداعات في الطريق')),
        ('outstanding_check', _('شيكات معلقة')),
        ('bank_charge', _('رسوم بنكية')),
        ('bank_interest', _('فوائد بنكية')),
        ('error_correction', _('تصحيح خطأ')),
        ('other', _('أخرى')),
    )
    
    item_type = models.CharField(
        _('نوع البند'),
        max_length=30,
        choices=ITEM_TYPES
    )
    description = models.CharField(
        _('الوصف'),
        max_length=200
    )
    amount = models.DecimalField(
        _('المبلغ'),
        max_digits=15,
        decimal_places=2
    )
    reference = models.CharField(
        _('المرجع'),
        max_length=100,
        blank=True,
        null=True
    )
    
    # تأثير البند على الرصيد
    EFFECT_CHOICES = (
        ('add_to_book', _('إضافة لرصيد الدفاتر')),
        ('subtract_from_book', _('خصم من رصيد الدفاتر')),
        ('add_to_bank', _('إضافة لرصيد البنك')),
        ('subtract_from_bank', _('خصم من رصيد البنك')),
    )
    
    effect = models.CharField(
        _('التأثير'),
        max_length=30,
        choices=EFFECT_CHOICES
    )
    
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    
    class Meta:
        verbose_name = _('بند تسوية بنكية')
        verbose_name_plural = _('بنود التسوية البنكية')
        ordering = ['item_type', 'description']
    
    def __str__(self):
        return f"{self.get_item_type_display()} - {self.amount}"
