from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from financial.models.audit_trail import PaymentAuditMixin

class PurchasePayment(PaymentAuditMixin, models.Model):
    """
    نموذج مدفوعات فواتير المشتريات
    """
    PAYMENT_METHODS = (
        ('cash', _('نقدي')),
        ('bank_transfer', _('تحويل بنكي')),
        ('check', _('شيك')),
    )
    
    purchase = models.ForeignKey('purchase.Purchase', on_delete=models.CASCADE, verbose_name=_('الفاتورة'), related_name='payments')
    amount = models.DecimalField(_('المبلغ'), max_digits=12, decimal_places=2)
    payment_date = models.DateField(_('تاريخ الدفع'))
    payment_method = models.CharField(_('طريقة الدفع'), max_length=20, choices=PAYMENT_METHODS)
    reference_number = models.CharField(_('رقم المرجع'), max_length=50, blank=True, null=True)
    notes = models.TextField(_('ملاحظات'), blank=True, null=True)
    created_at = models.DateTimeField(_('تاريخ الإنشاء'), auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 verbose_name=_('أنشئ بواسطة'), related_name='purchase_payments_created')
    # الحساب المالي المستخدم للدفع (خزينة أو بنك)
    financial_account = models.ForeignKey(
        'financial.ChartOfAccounts',
        on_delete=models.PROTECT,
        verbose_name=_('الحساب المالي'),
        help_text=_('الخزينة أو البنك المستخدم للدفع'),
        null=True, blank=True
    )
    
    # حقل للإشارة إلى المعاملة المالية المرتبطة
    financial_transaction = models.ForeignKey('financial.JournalEntry', on_delete=models.SET_NULL, 
                                             null=True, blank=True, verbose_name=_('المعاملة المالية'))
    
    # حالة الربط المالي
    FINANCIAL_STATUS_CHOICES = (
        ('pending', _('معلق')),
        ('synced', _('مربوط')),
        ('failed', _('فشل')),
        ('manual', _('يدوي')),
    )
    financial_status = models.CharField(
        _('حالة الربط المالي'),
        max_length=20,
        choices=FINANCIAL_STATUS_CHOICES,
        default='pending'
    )
    
    # رسالة خطأ الربط المالي (إن وجدت)
    financial_error = models.TextField(_('خطأ الربط المالي'), blank=True, null=True)
    
    # حقول الترحيل
    STATUS_CHOICES = (
        ('draft', _('مسودة')),
        ('posted', _('مرحّلة')),
    )
    status = models.CharField(
        _('الحالة'),
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft',
        help_text=_('المسودات يمكن تعديلها، المرحّلة لا يمكن تعديلها')
    )
    posted_at = models.DateTimeField(_('تاريخ الترحيل'), null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_('رحّلها'),
        related_name='purchase_payments_posted',
        null=True,
        blank=True
    )
    
    class Meta:
        verbose_name = _('دفعة الفاتورة')
        verbose_name_plural = _('دفعات الفواتير')
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"{self.purchase} - {self.amount} - {self.payment_date}"
    
    def clean(self):
        """التحقق من صحة البيانات"""
        super().clean()
        
        # التحقق من أن الحساب المالي نقدي أو بنكي
        if self.financial_account:
            if not (self.financial_account.is_cash_account or self.financial_account.is_bank_account):
                raise ValidationError({
                    'financial_account': _('يجب اختيار حساب نقدي أو بنكي فقط')
                })
        
        # التحقق من أن المبلغ موجب
        if self.amount and self.amount <= 0:
            raise ValidationError({
                'amount': _('يجب أن يكون المبلغ أكبر من صفر')
            })
    
    @property
    def is_financially_synced(self):
        """هل الدفعة مربوطة مالياً"""
        return self.financial_status == 'synced' and self.financial_transaction
    
    @property
    def can_be_synced(self):
        """هل يمكن ربط الدفعة مالياً"""
        return (
            self.financial_account and 
            self.financial_status in ['pending', 'failed'] and
            self.amount > 0
        )
    
    def mark_financial_sync_success(self, transaction, movement=None):
        """تحديد الدفعة كمربوطة مالياً بنجاح"""
        self.financial_transaction = transaction
        # حقل cash_movement تم حذفه - نستخدم القيود المحاسبية فقط
        self.financial_status = 'synced'
        self.financial_error = None
        self.save(update_fields=['financial_transaction', 'financial_status', 'financial_error'])
    
    def mark_financial_sync_failed(self, error_message):
        """تحديد الدفعة كفاشلة في الربط المالي"""
        self.financial_status = 'failed'
        self.financial_error = error_message
        self.save(update_fields=['financial_status', 'financial_error'])
    
    @property
    def is_draft(self):
        """هل الدفعة مسودة"""
        return self.status == 'draft'
    
    @property
    def is_posted(self):
        """هل الدفعة مرحّلة"""
        return self.status == 'posted'
    
    @property
    def can_edit(self):
        """هل يمكن تعديل الدفعة"""
        return self.status == 'draft'
    
    @property
    def can_delete(self):
        """هل يمكن حذف الدفعة"""
        return self.status == 'draft'
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # تحديث حالة الدفع للفاتورة
        if self.purchase:
            self.purchase.update_payment_status()
    
    def unpost(self, user=None, reason=""):
        """إلغاء ترحيل الدفعة بحذف القيد المحاسبي"""
        if not self.is_posted:
            return {'success': False, 'message': 'الدفعة غير مرحّلة'}
        
        try:
            # تسجيل البيانات القديمة للتدقيق
            old_data = {
                'status': self.status,
                'financial_status': self.financial_status,
                'financial_transaction_id': self.financial_transaction.id if self.financial_transaction else None,
                'posted_at': self.posted_at.isoformat() if self.posted_at else None,
                'posted_by': self.posted_by.username if self.posted_by else None
            }
            
            # حذف القيد المحاسبي المرتبط
            journal_entry_number = None
            if self.financial_transaction:
                journal_entry = self.financial_transaction
                journal_entry_number = journal_entry.number
                # حذف بنود القيد
                journal_entry.lines.all().delete()
                # حذف القيد نفسه
                journal_entry.delete()
            
            # إعادة تعيين حالة الدفعة
            self.financial_transaction = None
            self.financial_status = 'pending'
            self.status = 'draft'
            self.posted_at = None
            self.posted_by = None
            self.save()
            
            # تسجيل البيانات الجديدة للتدقيق
            new_data = {
                'status': self.status,
                'financial_status': self.financial_status,
                'financial_transaction_id': None,
                'posted_at': None,
                'posted_by': None
            }
            
            # تسجيل العملية في سجل التدقيق
            self.log_payment_action(
                action='unpost',
                user=user,
                description=f'إلغاء ترحيل دفعة مشتريات - القيد المحذوف: {journal_entry_number}',
                reason=reason,
                old_values=old_data,
                new_values=new_data,
                journal_entry_number=journal_entry_number
            )
            
            # تحديث حالة الدفع للفاتورة
            if self.purchase:
                self.purchase.update_payment_status()
            
            return {'success': True, 'message': 'تم إلغاء الترحيل بنجاح'}
            
        except Exception as e:
            # تسجيل فشل العملية
            if user:
                self.log_payment_action(
                    action='unpost',
                    user=user,
                    description=f'فشل في إلغاء ترحيل دفعة مشتريات: {str(e)}',
                    reason=reason,
                    status='failed',
                    error_message=str(e)
                )
            return {'success': False, 'message': f'خطأ في إلغاء الترحيل: {str(e)}'}
    
    @property
    def can_unpost(self):
        """هل يمكن إلغاء ترحيل الدفعة"""
        return self.is_posted and self.financial_transaction
    
    def update_payment_data(self, data, user=None):
        """تحديث بيانات الدفعة مع معالجة الترحيل"""
        was_posted = self.is_posted
        
        # تسجيل البيانات القديمة للتدقيق
        old_data = {
            'amount': float(self.amount),
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'payment_method': self.payment_method,
            'financial_account_id': self.financial_account.id if self.financial_account else None,
            'reference_number': self.reference_number,
            'notes': self.notes,
            'status': self.status,
            'financial_status': self.financial_status
        }
        
        # إذا كانت مرحّلة، ألغِ الترحيل أولاً
        if was_posted:
            unpost_result = self.unpost(user, reason="تعديل بيانات الدفعة")
            if not unpost_result['success']:
                return unpost_result
        
        # تحديث البيانات
        for field, value in data.items():
            if hasattr(self, field):
                setattr(self, field, value)
        
        self.save()
        
        # تسجيل البيانات الجديدة للتدقيق
        new_data = {
            'amount': float(self.amount),
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'payment_method': self.payment_method,
            'financial_account_id': self.financial_account.id if self.financial_account else None,
            'reference_number': self.reference_number,
            'notes': self.notes,
            'status': self.status,
            'financial_status': self.financial_status
        }
        
        # تسجيل العملية في سجل التدقيق
        self.log_payment_action(
            action='update',
            user=user,
            description='تحديث بيانات دفعة مشتريات',
            reason="تعديل بيانات الدفعة",
            old_values=old_data,
            new_values=new_data,
            was_posted=was_posted
        )
        
        # إعادة الترحيل إذا كانت مرحّلة مسبقاً
        if was_posted:
            from financial.services.payment_integration_service import PaymentIntegrationService
            result = PaymentIntegrationService.process_payment(self, 'purchase', user)
            if result['success']:
                self.status = 'posted'
                self.posted_at = timezone.now()
                self.posted_by = user
                self.save()
                
                # تسجيل إعادة الترحيل
                self.log_payment_action(
                    action='post',
                    user=user,
                    description='إعادة ترحيل دفعة مشتريات بعد التعديل',
                    reason="إعادة ترحيل بعد التعديل",
                    journal_entry_id=self.financial_transaction.id if self.financial_transaction else None
                )
        
        return {'success': True, 'message': 'تم تحديث الدفعة بنجاح'}
    
    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        
        # تحديث حالة الدفع للفاتورة بعد الحذف
        if self.purchase:
            self.purchase.update_payment_status() 