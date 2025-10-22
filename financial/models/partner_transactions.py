from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from decimal import Decimal

from .chart_of_accounts import ChartOfAccounts
from .journal_entry import JournalEntry

User = settings.AUTH_USER_MODEL


class PartnerTransaction(models.Model):
    """
    نموذج أساسي لمعاملات الشريك (مساهمات وسحوبات)
    """
    
    TRANSACTION_TYPES = (
        ("contribution", _("مساهمة")),
        ("withdrawal", _("سحب")),
    )
    
    CONTRIBUTION_TYPES = (
        ("loan", _("قرض للشركة")),
        ("capital_increase", _("زيادة رأس المال")),
        ("temporary", _("مساهمة مؤقتة")),
    )
    
    WITHDRAWAL_TYPES = (
        ("loan_repayment", _("سداد قرض سابق")),
        ("capital_withdrawal", _("سحب من رأس المال")),
        ("profit_distribution", _("توزيع أرباح")),
        ("personal_expense", _("مصروف شخصي")),
    )
    
    STATUS_CHOICES = (
        ("pending", _("في الانتظار")),
        ("approved", _("موافق عليه")),
        ("completed", _("مكتمل")),
        ("cancelled", _("ملغي")),
    )

    # المعلومات الأساسية
    transaction_type = models.CharField(
        _("نوع المعاملة"), 
        max_length=20, 
        choices=TRANSACTION_TYPES
    )
    
    # الشريك (حاليا محمد يوسف فقط)
    partner_account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        related_name="partner_transactions",
        verbose_name=_("حساب الشريك"),
        help_text=_("حساب جاري الشريك")
    )
    
    # الخزينة (صندوق أو بنك)
    cash_account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        related_name="partner_cash_transactions",
        verbose_name=_("حساب الخزينة"),
        help_text=_("الحساب النقدي أو البنكي")
    )
    
    # المبلغ والتفاصيل
    amount = models.DecimalField(
        _("المبلغ"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    
    # نوع فرعي للمعاملة
    contribution_type = models.CharField(
        _("نوع المساهمة"),
        max_length=20,
        choices=CONTRIBUTION_TYPES,
        blank=True,
        null=True
    )
    
    withdrawal_type = models.CharField(
        _("نوع السحب"),
        max_length=20,
        choices=WITHDRAWAL_TYPES,
        blank=True,
        null=True
    )
    
    # التواريخ
    transaction_date = models.DateField(
        _("تاريخ المعاملة"),
        default=timezone.now
    )
    
    # الوصف والملاحظات
    description = models.TextField(
        _("الوصف"),
        help_text=_("سبب المساهمة أو السحب")
    )
    
    notes = models.TextField(
        _("ملاحظات إضافية"),
        blank=True,
        null=True
    )
    
    # الحالة والموافقات
    status = models.CharField(
        _("الحالة"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )
    
    # القيد المحاسبي المرتبط
    journal_entry = models.OneToOneField(
        JournalEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partner_transaction",
        verbose_name=_("القيد المحاسبي")
    )
    
    # معلومات التدقيق
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_partner_transactions",
        verbose_name=_("أنشأ بواسطة")
    )
    
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_partner_transactions",
        verbose_name=_("وافق عليه")
    )
    
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    approved_at = models.DateTimeField(_("تاريخ الموافقة"), null=True, blank=True)
    
    class Meta:
        verbose_name = _("معاملة الشريك")
        verbose_name_plural = _("معاملات الشريك")
        ordering = ["-transaction_date", "-created_at"]
        indexes = [
            models.Index(fields=["transaction_type", "transaction_date"]),
            models.Index(fields=["partner_account", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]
    
    def __str__(self):
        type_display = self.get_transaction_type_display()
        return f"{type_display} - {self.amount} ج.م - {self.transaction_date}"
    
    @property
    def partner_name(self):
        """اسم الشريك من اسم الحساب"""
        return self.partner_account.name if self.partner_account else ""
    
    @property
    def cash_account_name(self):
        """اسم حساب الخزينة"""
        return self.cash_account.name if self.cash_account else ""
    
    def get_sub_type_display(self):
        """عرض النوع الفرعي للمعاملة"""
        if self.transaction_type == "contribution" and self.contribution_type:
            return dict(self.CONTRIBUTION_TYPES).get(self.contribution_type, "")
        elif self.transaction_type == "withdrawal" and self.withdrawal_type:
            return dict(self.WITHDRAWAL_TYPES).get(self.withdrawal_type, "")
        return ""
    
    def can_be_approved(self):
        """هل يمكن الموافقة على المعاملة"""
        return self.status == "pending"
    
    def can_be_cancelled(self):
        """هل يمكن إلغاء المعاملة"""
        return self.status in ["pending", "approved"]
    
    def approve(self, approved_by_user):
        """الموافقة على المعاملة"""
        if self.can_be_approved():
            self.status = "approved"
            self.approved_by = approved_by_user
            self.approved_at = timezone.now()
            self.save()
            return True
        return False
    
    def complete(self):
        """إكمال المعاملة وإنشاء القيد المحاسبي"""
        if self.status == "approved" and not self.journal_entry:
            # إنشاء القيد المحاسبي
            journal_entry = self._create_journal_entry()
            if journal_entry:
                self.journal_entry = journal_entry
                self.status = "completed"
                self.save()
                
                # تحديث رصيد الشريك تلقائياً
                partner_balance, created = PartnerBalance.objects.get_or_create(
                    partner_account=self.partner_account
                )
                partner_balance.update_balance()
                
                return True
        return False
    
    def _create_journal_entry(self):
        """إنشاء القيد المحاسبي للمعاملة"""
        try:
            # تحديد وصف القيد
            if self.transaction_type == "contribution":
                description = f"مساهمة الشريك - {self.description}"
            else:
                description = f"سحب الشريك - {self.description}"
            
            # إنشاء القيد
            journal_entry = JournalEntry.objects.create(
                date=self.transaction_date,
                description=description,
                reference=f"PARTNER-{self.id}",
                created_by=self.created_by
            )
            
            # إنشاء بنود القيد
            if self.transaction_type == "contribution":
                # مدين: الخزينة (زيادة النقدية)
                journal_entry.lines.create(
                    account=self.cash_account,
                    debit=self.amount,
                    credit=Decimal('0'),
                    description=description
                )
                # دائن: جاري الشريك (زيادة التزام الشركة)
                journal_entry.lines.create(
                    account=self.partner_account,
                    debit=Decimal('0'),
                    credit=self.amount,
                    description=description
                )
            else:  # withdrawal
                # مدين: جاري الشريك (تقليل التزام الشركة)
                journal_entry.lines.create(
                    account=self.partner_account,
                    debit=self.amount,
                    credit=Decimal('0'),
                    description=description
                )
                # دائن: الخزينة (نقص النقدية)
                journal_entry.lines.create(
                    account=self.cash_account,
                    debit=Decimal('0'),
                    credit=self.amount,
                    description=description
                )
            
            return journal_entry
            
        except Exception as e:
            # في حالة الخطأ، يمكن تسجيل الخطأ
            return None
    
    def cancel(self):
        """إلغاء المعاملة"""
        if self.can_be_cancelled():
            self.status = "cancelled"
            self.save()
            return True
        return False


class PartnerBalance(models.Model):
    """
    نموذج لتتبع رصيد الشريك
    """
    
    partner_account = models.OneToOneField(
        ChartOfAccounts,
        on_delete=models.CASCADE,
        related_name="partner_balance",
        verbose_name=_("حساب الشريك")
    )
    
    # الأرصدة
    total_contributions = models.DecimalField(
        _("إجمالي المساهمات"),
        max_digits=15,
        decimal_places=2,
        default=Decimal('0')
    )
    
    total_withdrawals = models.DecimalField(
        _("إجمالي السحوبات"),
        max_digits=15,
        decimal_places=2,
        default=Decimal('0')
    )
    
    current_balance = models.DecimalField(
        _("الرصيد الحالي"),
        max_digits=15,
        decimal_places=2,
        default=Decimal('0')
    )
    
    # آخر معاملة
    last_transaction_date = models.DateField(
        _("تاريخ آخر معاملة"),
        null=True,
        blank=True
    )
    
    # تواريخ التحديث
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    
    class Meta:
        verbose_name = _("رصيد الشريك")
        verbose_name_plural = _("أرصدة الشركاء")
    
    def __str__(self):
        partner_name = self.partner_account.name if self.partner_account else "شريك"
        return f"رصيد {partner_name}: {self.current_balance} ج.م"
    
    def update_balance(self):
        """تحديث الرصيد من المعاملات المكتملة"""
        completed_transactions = PartnerTransaction.objects.filter(
            partner_account=self.partner_account,
            status="completed"
        )
        
        # حساب المساهمات
        contributions = completed_transactions.filter(
            transaction_type="contribution"
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')
        
        # حساب السحوبات
        withdrawals = completed_transactions.filter(
            transaction_type="withdrawal"
        ).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0')
        
        # تحديث الأرصدة
        self.total_contributions = contributions
        self.total_withdrawals = withdrawals
        self.current_balance = contributions - withdrawals
        
        # آخر معاملة
        last_transaction = completed_transactions.order_by('-transaction_date').first()
        if last_transaction:
            self.last_transaction_date = last_transaction.transaction_date
        
        self.save()
        
        return self.current_balance
    
    @property
    def net_balance(self):
        """صافي الرصيد (مساهمات - سحوبات)"""
        return self.total_contributions - self.total_withdrawals
    
    def can_withdraw(self, amount):
        """هل يمكن سحب المبلغ المحدد"""
        return self.current_balance >= amount
