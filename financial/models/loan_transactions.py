from django.db import models
from django.db.models import F
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from datetime import timedelta

from .chart_of_accounts import ChartOfAccounts
from .journal_entry import JournalEntry

User = settings.AUTH_USER_MODEL


class Loan(models.Model):
    """
    نموذج القروض - يمثل قرض واحد للشركة
    """
    
    LOAN_TYPES = (
        ("short_term", _("قصير الأجل (أقل من سنة)")),
        ("long_term", _("طويل الأجل (أكثر من سنة)")),
    )
    
    LENDER_TYPES = (
        ("bank", _("بنك")),
        ("supplier", _("مورد")),
        ("partner", _("شريك")),
        ("individual", _("فرد")),
        ("other", _("أخرى")),
    )
    
    STATUS_CHOICES = (
        ("active", _("نشط")),
        ("completed", _("مكتمل السداد")),
        ("cancelled", _("ملغي")),
    )
    
    PAYMENT_FREQUENCY = (
        ("monthly", _("شهري")),
        ("quarterly", _("ربع سنوي")),
        ("semi_annual", _("نصف سنوي")),
        ("annual", _("سنوي")),
    )

    # المعلومات الأساسية
    loan_number = models.CharField(
        _("رقم القرض"),
        max_length=50,
        unique=True,
        blank=True,
        help_text=_("رقم مرجعي للقرض - يتم توليده تلقائياً")
    )
    
    loan_type = models.CharField(
        _("نوع القرض"),
        max_length=20,
        choices=LOAN_TYPES,
        default="long_term"
    )
    
    lender_type = models.CharField(
        _("نوع الجهة المقرضة"),
        max_length=20,
        choices=LENDER_TYPES,
        default="bank"
    )
    
    lender_name = models.CharField(
        _("اسم الجهة المقرضة"),
        max_length=200,
    )
    
    # المبالغ
    principal_amount = models.DecimalField(
        _("مبلغ القرض الأصلي"),
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    
    interest_rate = models.DecimalField(
        _("معدل الفائدة السنوي (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        help_text=_("مثال: 10.5 تعني 10.5%")
    )
    
    # التواريخ والمدة
    start_date = models.DateField(
        _("تاريخ استلام القرض"),
        default=timezone.now
    )
    
    duration_months = models.PositiveIntegerField(
        _("مدة القرض (بالأشهر)"),
        validators=[MinValueValidator(1)],
    )
    
    payment_frequency = models.CharField(
        _("دورية السداد"),
        max_length=20,
        choices=PAYMENT_FREQUENCY,
        default="monthly"
    )
    
    # الحسابات المحاسبية
    loan_account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        related_name="loans_as_liability",
        verbose_name=_("حساب القرض (خصوم)"),
        help_text=_("مثال: 22010 - القروض طويلة الأجل")
    )
    
    bank_account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        related_name="loans_received",
        verbose_name=_("الحساب البنكي المستلم"),
        help_text=_("الحساب الذي استلم مبلغ القرض")
    )
    
    interest_expense_account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        related_name="loan_interest_expenses",
        verbose_name=_("حساب مصروف الفوائد"),
        help_text=_("مثال: 5300 - فوائد القروض"),
        null=True,
        blank=True
    )
    
    # القيد المحاسبي الأصلي (استلام القرض)
    initial_journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loan_initial_entry",
        verbose_name=_("القيد المحاسبي الأصلي")
    )
    
    # الوصف والملاحظات
    description = models.TextField(
        _("وصف القرض"),
        help_text=_("تفاصيل عن القرض والغرض منه")
    )
    
    notes = models.TextField(
        _("ملاحظات"),
        blank=True,
        help_text=_("أي ملاحظات إضافية")
    )
    
    # الحالة
    status = models.CharField(
        _("الحالة"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )
    
    # التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_loans",
        verbose_name=_("أنشأ بواسطة")
    )

    class Meta:
        verbose_name = _("قرض")
        verbose_name_plural = _("القروض")
        ordering = ["-start_date", "-created_at"]
        indexes = [
            models.Index(fields=['loan_number']),
            models.Index(fields=['status', 'start_date']),
            models.Index(fields=['lender_type', 'status']),
        ]

    def __str__(self):
        return f"{self.loan_number} - {self.lender_name} ({self.principal_amount})"
    
    def save(self, *args, **kwargs):
        # توليد رقم القرض تلقائياً إذا لم يكن موجوداً
        if not self.loan_number:
            self.loan_number = self.generate_loan_number()
        super().save(*args, **kwargs)
    
    def generate_loan_number(self):
        """
        توليد رقم القرض تلقائياً
        التنسيق: LOAN-25-0001 (سنتين + رقم تسلسلي)
        """
        year = self.start_date.year if self.start_date else timezone.now().year
        year_short = str(year)[-2:]  # آخر رقمين من السنة
        
        # البحث عن أعلى رقم في السنة الحالية
        loans = Loan.objects.filter(
            start_date__year=year,
            loan_number__startswith=f"LOAN-{year_short}-"
        ).exclude(pk=self.pk if self.pk else None)
        
        max_number = 0
        for loan in loans:
            try:
                # استخراج الرقم من نهاية رقم القرض
                number_part = loan.loan_number.split("-")[-1]
                current_number = int(number_part)
                if current_number > max_number:
                    max_number = current_number
            except (ValueError, IndexError):
                continue
        
        new_number = max_number + 1
        
        # التأكد من عدم تكرار الرقم
        while True:
            candidate_number = f"LOAN-{year_short}-{new_number:04d}"
            if not Loan.objects.filter(loan_number=candidate_number).exclude(pk=self.pk if self.pk else None).exists():
                return candidate_number
            new_number += 1

    @property
    def end_date(self):
        """تاريخ انتهاء القرض المتوقع"""
        return self.start_date + timedelta(days=self.duration_months * 30)

    @property
    def total_amount_with_interest(self):
        """إجمالي المبلغ مع الفوائد"""
        interest_amount = (self.principal_amount * self.interest_rate * self.duration_months) / (Decimal('100') * Decimal('12'))
        return self.principal_amount + interest_amount

    @property
    def total_paid(self):
        """إجمالي المبلغ المدفوع"""
        result = self.payments.filter(status="completed").aggregate(
            principal=models.Sum('principal_amount'),
            interest=models.Sum('interest_amount')
        )
        principal = result['principal'] or Decimal('0.00')
        interest = result['interest'] or Decimal('0.00')
        return principal + interest

    @property
    def remaining_balance(self):
        """الرصيد المتبقي"""
        return self.principal_amount - self.total_paid

    @property
    def is_overdue(self):
        """هل القرض متأخر في السداد"""
        if self.status != "active":
            return False
        return timezone.now().date() > self.end_date

    def calculate_monthly_payment(self):
        """حساب القسط الشهري"""
        if self.interest_rate == 0:
            # بدون فوائد
            return self.principal_amount / self.duration_months
        
        # مع الفوائد - استخدام معادلة القسط الثابت
        monthly_rate = self.interest_rate / (Decimal('100') * Decimal('12'))
        numerator = self.principal_amount * monthly_rate * ((1 + monthly_rate) ** self.duration_months)
        denominator = ((1 + monthly_rate) ** self.duration_months) - 1
        return numerator / denominator


class LoanPayment(models.Model):
    """
    نموذج دفعات القرض - يمثل قسط واحد من أقساط القرض
    """
    
    STATUS_CHOICES = (
        ("scheduled", _("مجدول")),
        ("completed", _("مكتمل")),
        ("overdue", _("متأخر")),
        ("cancelled", _("ملغي")),
    )

    # ربط بالقرض
    loan = models.ForeignKey(
        Loan,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("القرض")
    )
    
    # معلومات الدفعة
    payment_number = models.PositiveIntegerField(
        _("رقم القسط"),
        help_text=_("رقم القسط من إجمالي الأقساط")
    )
    
    scheduled_date = models.DateField(
        _("تاريخ الاستحقاق"),
        help_text=_("التاريخ المجدول للدفع")
    )
    
    actual_payment_date = models.DateField(
        _("تاريخ الدفع الفعلي"),
        null=True,
        blank=True
    )
    
    # المبالغ
    principal_amount = models.DecimalField(
        _("أصل القسط"),
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    interest_amount = models.DecimalField(
        _("الفوائد"),
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))]
    )
    
    @property
    def amount(self):
        """إجمالي القسط (أصل + فائدة)"""
        return self.principal_amount + self.interest_amount
    
    # الحساب البنكي المسدد منه
    payment_account = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        related_name="loan_payments",
        verbose_name=_("حساب الدفع"),
        null=True,
        blank=True
    )
    
    # القيد المحاسبي
    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loan_payment_entry",
        verbose_name=_("القيد المحاسبي")
    )
    
    # الحالة
    status = models.CharField(
        _("الحالة"),
        max_length=20,
        choices=STATUS_CHOICES,
        default="scheduled"
    )
    
    notes = models.TextField(
        _("ملاحظات"),
        blank=True
    )
    
    # التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    paid_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="loan_payments_made",
        verbose_name=_("دفع بواسطة"),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("دفعة قرض")
        verbose_name_plural = _("دفعات القروض")
        ordering = ["loan", "payment_number"]
        unique_together = [['loan', 'payment_number']]
        indexes = [
            models.Index(fields=['loan', 'payment_number']),
            models.Index(fields=['status', 'scheduled_date']),
        ]

    def __str__(self):
        return f"{self.loan.loan_number} - قسط {self.payment_number} ({self.amount})"

    @property
    def is_overdue(self):
        """هل القسط متأخر"""
        if self.status == "completed":
            return False
        return timezone.now().date() > self.scheduled_date

    def mark_as_paid(self, payment_date=None, payment_account=None, paid_by=None):
        """تحديد القسط كمدفوع"""
        self.status = "completed"
        self.actual_payment_date = payment_date or timezone.now().date()
        if payment_account:
            self.payment_account = payment_account
        if paid_by:
            self.paid_by = paid_by
        self.save()
