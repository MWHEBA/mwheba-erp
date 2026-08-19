from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import RegexValidator
from django.conf import settings
from datetime import date

User = settings.AUTH_USER_MODEL


class AccountType(models.Model):
    """
    أنواع الحسابات المحاسبية الرئيسية
    """

    ACCOUNT_CATEGORIES = (
        ("asset", _("أصول")),
        ("liability", _("خصوم")),
        ("equity", _("حقوق الملكية")),
        ("revenue", _("إيرادات")),
        ("expense", _("مصروفات")),
    )

    NATURE_CHOICES = (
        ("debit", _("مدين")),
        ("credit", _("دائن")),
    )

    code = models.CharField(_("كود النوع"), max_length=20, unique=True)
    name = models.CharField(_("اسم النوع"), max_length=100)
    # إضافة الحقول المحسنة الجديدة
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=100, blank=True)
    is_system_type = models.BooleanField(_("نوع نظام"), default=False, 
                                       help_text=_("أنواع النظام لا يمكن حذفها أو تعديلها"))
    
    category = models.CharField(_("التصنيف"), max_length=20, choices=ACCOUNT_CATEGORIES)
    nature = models.CharField(_("الطبيعة"), max_length=10, choices=NATURE_CHOICES)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("النوع الأب"),
        related_name="children",
    )
    level = models.PositiveIntegerField(_("المستوى"), default=1)
    is_active = models.BooleanField(_("نشط"), default=True)

    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="account_types_created",
    )

    class Meta:
        verbose_name = _("نوع الحساب")
        verbose_name_plural = _("أنواع الحسابات")
        ordering = ["category", "code"]
        # إضافة الفهارس المحسنة
        indexes = [
            models.Index(fields=["category", "is_active"]),
            models.Index(fields=["parent", "level"]),
            models.Index(fields=["code"]),
            models.Index(fields=["is_system_type"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        # حساب المستوى تلقائياً
        if self.parent:
            self.level = self.parent.level + 1
        else:
            self.level = 1
        super().save(*args, **kwargs)


class ChartOfAccounts(models.Model):
    """
    دليل الحسابات المحاسبي الشامل
    """

    code_validator = RegexValidator(
        regex=r"^\d{4,20}$", message=_("كود الحساب يجب أن يكون من 4 إلى 20 رقم")
    )

    code = models.CharField(
        _("كود الحساب"), max_length=50, unique=True, validators=[code_validator]
    )
    name = models.CharField(_("اسم الحساب"), max_length=200)
    name_en = models.CharField(
        _("الاسم بالإنجليزية"), max_length=200, blank=True, null=True
    )

    account_type = models.ForeignKey(
        AccountType,
        on_delete=models.PROTECT,
        verbose_name=_("نوع الحساب"),
        related_name="accounts",
    )

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("الحساب الأب"),
        related_name="children",
    )

    level = models.PositiveIntegerField(_("المستوى"), default=1)
    is_leaf = models.BooleanField(
        _("حساب نهائي"),
        default=True,
        help_text=_("الحسابات النهائية فقط يمكن إدراج قيود عليها"),
    )

    # خصائص الحساب
    is_bank_account = models.BooleanField(_("حساب بنكي"), default=False)
    is_cash_account = models.BooleanField(_("حساب نقدي"), default=False)
    is_reconcilable = models.BooleanField(_("يخضع للتسوية"), default=False)
    is_control_account = models.BooleanField(_("حساب رقابي"), default=False)
    currency = models.ForeignKey(
        'financial.Currency',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("عملة الحساب"),
        related_name="accounts",
        help_text=_("العملة الخاصة بالخزنة أو الحساب البنكي (إذا تُركت فارغة تعتمد العملة الأساسية للنظام)")
    )

    # الرصيد الافتتاحي
    opening_balance = models.DecimalField(
        _("الرصيد الافتتاحي"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("الرصيد الافتتاحي للحساب بالعملة الوظيفية (EGP)"),
    )
    opening_balance_foreign = models.DecimalField(
        _("الرصيد الافتتاحي بالعملة الأجنبية"),
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("الرصيد الافتتاحي بالعملة الأجنبية للحساب عند إنشائه"),
    )
    opening_balance_rate = models.DecimalField(
        _("سعر صرف الرصيد الافتتاحي"),
        max_digits=12,
        decimal_places=6,
        default=Decimal("1.000000"),
        help_text=_("سعر الصرف المعتمد للرصيد الافتتاحي الأجنبي"),
    )
    opening_balance_date = models.DateField(
        _("تاريخ الرصيد الافتتاحي"),
        null=True,
        blank=True,
        help_text=_("تاريخ الرصيد الافتتاحي"),
    )

    # معلومات إضافية
    description = models.TextField(_("الوصف"), blank=True, null=True)
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    # حالة الحساب
    is_active = models.BooleanField(_("نشط"), default=True)
    is_system_account = models.BooleanField(
        _("حساب نظام"), default=False, help_text=_("الحسابات النظامية لا يمكن حذفها")
    )

    # معلومات بنكية إضافية (للحسابات البنكية)
    bank_name = models.CharField(_("اسم البنك"), max_length=100, blank=True, null=True)
    account_number = models.CharField(
        _("رقم الحساب"), max_length=50, blank=True, null=True
    )
    iban = models.CharField(_("رقم الآيبان"), max_length=34, blank=True, null=True)
    swift_code = models.CharField(
        _("رمز السويفت"), max_length=11, blank=True, null=True
    )

    # حدود الحساب
    credit_limit = models.DecimalField(
        _("حد الائتمان"),
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("الحد الأقصى للسحب على المكشوف"),
    )
    minimum_balance = models.DecimalField(
        _("الحد الأدنى للرصيد"),
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("الحد الأدنى المطلوب للرصيد"),
    )

    # إعدادات التنبيهات
    low_balance_alert = models.BooleanField(_("تنبيه الرصيد المنخفض"), default=False)
    low_balance_threshold = models.DecimalField(
        _("عتبة الرصيد المنخفض"), max_digits=15, decimal_places=2, null=True, blank=True
    )

    # معلومات التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="chart_accounts_created",
    )

    class Meta:
        verbose_name = _("حساب")
        verbose_name_plural = _("دليل الحسابات")
        ordering = ["code"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["account_type", "is_active"]),
            models.Index(fields=["parent", "level"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        # حساب الرصيد الافتتاحي بالعملة المحلية تلقائياً عند إدخال رصيد أجنبي
        if self.opening_balance_foreign and self.opening_balance_foreign != Decimal("0.00"):
            rate = self.opening_balance_rate or Decimal("1.000000")
            self.opening_balance = (self.opening_balance_foreign * rate).quantize(Decimal("0.01"))

        # حساب المستوى تلقائياً
        if self.parent:
            self.level = self.parent.level + 1
            # إذا كان للحساب أب، فالأب ليس حساباً نهائياً
            self.parent.is_leaf = False
            self.parent.save(update_fields=["is_leaf"])
        else:
            self.level = 1

        super().save(*args, **kwargs)

        # مسح كاش الخزن والبنوك لضمان الظهور الفوري عند التعديل
        try:
            from django.core.cache import cache
            cache.delete('payment_accounts_data_v2')
        except Exception:
            pass

    @property
    def full_code(self):
        """الكود الكامل مع الأب"""
        if self.parent:
            return f"{self.parent.full_code}.{self.code}"
        return self.code

    @property
    def full_name(self):
        """الاسم الكامل مع التسلسل الهرمي"""
        if self.parent:
            return f"{self.parent.full_name} > {self.name}"
        return self.name

    @property
    def nature(self):
        """طبيعة الحساب (مدين/دائن) من نوع الحساب"""
        return self.account_type.nature

    @property
    def category(self):
        """فئة الحساب من نوع الحساب"""
        return self.account_type.category

    @property
    def account_currency(self):
        """كائن العملة التابع للحساب أو العملة الوظيفية الأساسية"""
        if self.currency:
            return self.currency
        from financial.services.exchange_rate_service import ExchangeRateService
        return ExchangeRateService.get_functional_currency()

    @property
    def currency_code(self):
        """رمز عملة الحساب"""
        if self.currency and self.currency.code:
            return self.currency.code
        from financial.services.exchange_rate_service import ExchangeRateService
        func = ExchangeRateService.get_functional_currency()
        return func.code if func else "EGP"

    @property
    def currency_symbol(self):
        """رمز العملة الجرافيكي أو كود العملة"""
        if self.currency:
            return self.currency.symbol or self.currency.code
        from financial.services.exchange_rate_service import ExchangeRateService
        func = ExchangeRateService.get_functional_currency()
        return (func.symbol or func.code) if func else "ج.م"

    @property
    def is_foreign_currency(self):
        """هل الحساب بالعملة الأجنبية"""
        if not self.currency:
            return False
        return not self.currency.is_functional

    @property
    def current_balance(self):
        """الرصيد الحالي من القيود المرحلة (مع الرصيد الافتتاحي)"""
        return self.get_balance(include_opening=True)

    def get_balance(self, date_from=None, date_to=None, include_opening=True):
        """
        حساب رصيد الحساب في فترة معينة - محسن ومحدث
        """
        from .journal_entry import JournalEntryLine
        from django.db.models import Sum, Q
        from django.utils import timezone
        from decimal import Decimal
        from datetime import date

        # إذا لم يتم تحديد تاريخ نهاية، استخدم تاريخ مستقبلي لضمان شمول جميع القيود
        if not date_to:
            date_to = date(2030, 12, 31)  # تاريخ مستقبلي بعيد

        # الحصول على جميع بنود القيود المرحلة للحساب
        query = Q(account=self, journal_entry__status="posted")
        if date_from:
            query &= Q(journal_entry__date__gte=date_from)
        if date_to:
            query &= Q(journal_entry__date__lte=date_to)

        lines = JournalEntryLine.objects.filter(query)

        total_debit = lines.aggregate(Sum("debit"))["debit__sum"] or Decimal("0")
        total_credit = lines.aggregate(Sum("credit"))["credit__sum"] or Decimal("0")

        # إضافة الرصيد الافتتاحي أولاً إذا كان مطلوباً
        opening_balance = Decimal("0")
        if include_opening and self.opening_balance:
            # التحقق من أن تاريخ الرصيد الافتتاحي يقع في النطاق المطلوب
            opening_date = self.opening_balance_date or date(
                2020, 1, 1
            )  # تاريخ افتراضي
            if (not date_from or opening_date >= date_from) and (
                not date_to or opening_date <= date_to
            ):
                opening_balance = self.opening_balance

        # حساب الرصيد حسب طبيعة الحساب
        if self.nature == "debit":
            # للحسابات المدينة: الرصيد = الافتتاحي + المدين - الدائن
            balance = opening_balance + total_debit - total_credit
        else:
            # للحسابات الدائنة: الرصيد = الافتتاحي + الدائن - المدين
            balance = opening_balance + total_credit - total_debit

        return balance

    @classmethod
    def get_balances_bulk(cls, date_from=None, date_to=None, include_opening=True, account_ids=None):
        """
        حساب أرصدة الحسابات دفعة واحدة باستعلام SQL موحد يمنع مشاكل N+1 Queries
        مع إجراء التجميع الشجري الصاعد في الذاكرة (Memory Roll-up Aggregation) للحسابات الأمهات.
        """
        from .journal_entry import JournalEntryLine
        from django.db.models import Sum, Q
        from decimal import Decimal
        from datetime import date

        # 1. فلترة الحركات الحسابية
        query = Q(journal_entry__status="posted")
        if date_from:
            query &= Q(journal_entry__date__gte=date_from)
        if date_to:
            query &= Q(journal_entry__date__lte=date_to)
        if account_ids:
            query &= Q(account_id__in=account_ids)

        # 2. تجميع الحركات دفعة واحدة بـ SQL Group By
        totals_qs = (
            JournalEntryLine.objects.filter(query)
            .values("account_id")
            .annotate(
                sum_debit=Sum("debit"),
                sum_credit=Sum("credit")
            )
        )
        totals_map = {row["account_id"]: row for row in totals_qs}

        # 3. جلب كافة الحسابات المحددة أو النشطة
        acc_qs = cls.objects.all().select_related("account_type", "parent")
        if account_ids:
            acc_qs = acc_qs.filter(id__in=account_ids)

        accounts = list(acc_qs)

        # 4. حساب أرصدة الحسابات الفرعية أولاً
        balances = {}
        for acc in accounts:
            row = totals_map.get(acc.id, {})
            period_debit = row.get("sum_debit") or Decimal("0")
            period_credit = row.get("sum_credit") or Decimal("0")

            opening_balance = Decimal("0")
            if include_opening and acc.opening_balance:
                opening_date = acc.opening_balance_date or date(2020, 1, 1)
                if (not date_from or opening_date >= date_from) and (not date_to or opening_date <= date_to):
                    opening_balance = acc.opening_balance

            nature = acc.nature
            if nature == "debit":
                balance = opening_balance + period_debit - period_credit
            else:
                balance = opening_balance + period_credit - period_debit

            balances[acc.id] = {
                "account": acc,
                "opening_balance": opening_balance,
                "period_debit": period_debit,
                "period_credit": period_credit,
                "balance": balance,
            }

        # 5. التجميع الشجري الصاعد في الذاكرة للحسابات الأمهات (Roll-up Aggregation)
        # نرتب الحسابات حسب عمق الشجرة (من الأسفل للأعلى)
        for acc in sorted(accounts, key=lambda a: getattr(a, 'code', ''), reverse=True):
            if acc.parent_id and acc.parent_id in balances:
                parent_data = balances[acc.parent_id]
                child_data = balances[acc.id]
                parent_data["period_debit"] += child_data["period_debit"]
                parent_data["period_credit"] += child_data["period_credit"]
                parent_data["balance"] += child_data["balance"]

        return balances

    def get_descendants(self, include_self=False):
        """
        جلب جميع الأحفاد (الحسابات الفرعية) بشكل تكراري
        """
        descendants = []

        if include_self:
            descendants.append(self)

        for child in self.children.all():
            descendants.append(child)
            descendants.extend(child.get_descendants())

        return descendants

    def get_leaf_descendants(self, include_self=False):
        """
        جلب الأحفاد النهائيين فقط (التي يمكن أن تحتوي على قيود)
        """
        descendants = self.get_descendants(include_self=include_self)
        return [acc for acc in descendants if acc.is_leaf]

    def get_transactions_summary(self, date_from=None, date_to=None):
        """
        ملخص المعاملات للحساب وأحفاده
        """
        from .journal_entry import JournalEntryLine
        from django.db.models import Sum, Count
        from decimal import Decimal

        # جلب الحسابات النهائية (الحساب نفسه أو أحفاده)
        if self.is_leaf:
            accounts = [self]
        else:
            accounts = self.get_leaf_descendants(include_self=True)

        # بناء الاستعلام
        query_filter = {"account__in": accounts, "journal_entry__status": "posted"}

        if date_from:
            query_filter["journal_entry__date__gte"] = date_from
        if date_to:
            query_filter["journal_entry__date__lte"] = date_to

        # جلب الإحصائيات
        lines = JournalEntryLine.objects.filter(**query_filter)

        summary = lines.aggregate(
            total_debit=Sum("debit"),
            total_credit=Sum("credit"),
            transaction_count=Count("id"),
        )

        return {
            "total_debit": summary["total_debit"] or Decimal("0"),
            "total_credit": summary["total_credit"] or Decimal("0"),
            "transaction_count": summary["transaction_count"] or 0,
            "net_movement": (summary["total_debit"] or Decimal("0"))
            - (summary["total_credit"] or Decimal("0")),
            "accounts_included": len(accounts),
        }

    def update_balance(self, amount, operation="add"):
        """
        [DEPRECATED / PROTECTED]
        تم تحييد هذه الدالة لمنع أي تعديل عشوائي على الرصيد الافتتاحي (opening_balance).
        أرصدة الحسابات تُدار حصراً عبر قيود اليومية (Journal Entries).
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"ChartOfAccounts.update_balance called for account {self.id} ({self.code}). "
            f"Direct balance manipulation is prohibited; ledger entries are used instead."
        )
        return True

    def reconcile(self, bank_statement_balance, reconciliation_date=None):
        """
        إجراء التسوية البنكية

        الوسائط:
            bank_statement_balance: رصيد كشف الحساب البنكي
            reconciliation_date: تاريخ التسوية (افتراضيًا التاريخ الحالي)

        العائد:
            tuple: (نجاح/فشل، رسالة، الفرق)
        """
        from django.utils import timezone

        if not self.is_bank_account and not self.is_reconcilable:
            return (False, "هذا الحساب لا يخضع للتسوية البنكية", 0)

        if reconciliation_date is None:
            reconciliation_date = timezone.now().date()

        current_balance = self.get_balance()
        difference = bank_statement_balance - current_balance

        # تسجيل تفاصيل التسوية (يمكن إنشاء نموذج BankReconciliation لاحقاً)
        try:
            # إنشاء قيد تسوية إذا كان هناك فرق
            if difference != 0:
                from .journal_entry import JournalEntry, JournalEntryLine

                # إنشاء قيد التسوية عبر Service
                from financial.services.account_reconciliation_service import AccountReconciliationService
                
                reconciliation_entry = AccountReconciliationService.create_reconciliation_entry(
                    account=self,
                    difference=difference,
                    reconciliation_date=reconciliation_date,
                    user=None
                )

                return (
                    True,
                    f"تمت التسوية مع إنشاء قيد بقيمة {difference}",
                    difference,
                )
            else:
                return (True, "تمت التسوية بدون فروقات", 0)

        except Exception as e:
            return (False, f"خطأ في التسوية: {str(e)}", difference)

    def get_children_recursive(self):
        """الحصول على جميع الحسابات الفرعية بشكل تكراري"""
        children = list(self.children.all())
        for child in list(children):
            children.extend(child.get_children_recursive())
        return children

    def can_post_entries(self):
        """التحقق من إمكانية إدراج قيود على الحساب"""
        if not self.is_active:
            return False
        if self.is_leaf:
            return True
        return self.children.count() == 0

    def validate_entry_amount(self, debit=0, credit=0):
        """التحقق من صحة مبلغ القيد"""
        if debit < 0 or credit < 0:
            raise ValueError(_("المبالغ يجب أن تكون موجبة"))

        if debit > 0 and credit > 0:
            raise ValueError(_("لا يمكن أن يكون القيد مدين ودائن في نفس الوقت"))

        if debit == 0 and credit == 0:
            raise ValueError(_("يجب أن يكون للقيد مبلغ مدين أو دائن"))

        return True

    def check_low_balance_alert(self):
        """التحقق من تنبيه الرصيد المنخفض"""
        if not self.low_balance_alert or not self.low_balance_threshold:
            return False

        current_balance = self.get_balance()
        return current_balance <= self.low_balance_threshold

    def get_balance_status(self):
        """الحصول على حالة الرصيد"""
        current_balance = self.get_balance()

        status = {
            "balance": current_balance,
            "is_negative": current_balance < 0,
            "is_low": False,
            "is_over_limit": False,
            "warnings": [],
        }

        # فحص الرصيد المنخفض
        if self.low_balance_alert and self.low_balance_threshold:
            if current_balance <= self.low_balance_threshold:
                status["is_low"] = True
                status["warnings"].append("الرصيد أقل من الحد المسموح")

        # فحص تجاوز حد الائتمان
        if self.credit_limit and current_balance < -self.credit_limit:
            status["is_over_limit"] = True
            status["warnings"].append("تم تجاوز حد الائتمان المسموح")

        # فحص الحد الأدنى للرصيد
        if self.minimum_balance and current_balance < self.minimum_balance:
            status["warnings"].append("الرصيد أقل من الحد الأدنى المطلوب")

        return status

    def get_transaction_summary(self, date_from=None, date_to=None):
        """الحصول على ملخص المعاملات للحساب"""
        from .journal_entry import JournalEntryLine
        from django.db.models import Sum, Count

        lines = JournalEntryLine.objects.filter(account=self)

        if date_from:
            lines = lines.filter(journal_entry__date__gte=date_from)
        if date_to:
            lines = lines.filter(journal_entry__date__lte=date_to)

        summary = lines.aggregate(
            total_debit=Sum("debit"), total_credit=Sum("credit"), count=Count("id")
        )

        return {
            "total_debit": summary["total_debit"] or 0,
            "total_credit": summary["total_credit"] or 0,
            "transaction_count": summary["count"] or 0,
            "net_movement": (summary["total_debit"] or 0)
            - (summary["total_credit"] or 0),
        }

    # الطرق المحسنة الجديدة
    def get_balance_optimized(self, date_from=None, date_to=None, use_cache=True):
        """
        حساب الرصيد مع استخدام التخزين المؤقت المحسن
        
        الوسائط:
            date_from: تاريخ البداية
            date_to: تاريخ النهاية
            use_cache: استخدام التخزين المؤقت
            
        العائد:
            decimal: الرصيد المحسوب
        """
        from django.core.cache import cache
        from django.db.models import Sum, Q
        from decimal import Decimal
        from datetime import date
        import hashlib
        
        # إنشاء مفتاح التخزين المؤقت
        cache_key_data = f"{self.id}_{date_from}_{date_to}_{self.updated_at}"
        cache_key = f"balance_optimized_{hashlib.md5(cache_key_data.encode()).hexdigest()}"
        
        # محاولة الحصول على الرصيد من التخزين المؤقت
        if use_cache:
            cached_balance = cache.get(cache_key)
            if cached_balance is not None:
                return Decimal(str(cached_balance))
        
        # حساب الرصيد إذا لم يكن موجوداً في التخزين المؤقت
        from .journal_entry import JournalEntryLine
        
        # إذا لم يتم تحديد تاريخ نهاية، استخدم تاريخ مستقبلي
        if not date_to:
            date_to = date(2030, 12, 31)
            
        # بناء الاستعلام المحسن
        query = Q(account=self, journal_entry__status="posted")
        if date_from:
            query &= Q(journal_entry__date__gte=date_from)
        if date_to:
            query &= Q(journal_entry__date__lte=date_to)
            
        # استخدام select_related لتحسين الأداء
        lines = JournalEntryLine.objects.select_related('journal_entry').filter(query)
        
        # حساب المجاميع بشكل محسن
        totals = lines.aggregate(
            total_debit=Sum("debit"),
            total_credit=Sum("credit")
        )
        
        total_debit = totals["total_debit"] or Decimal("0")
        total_credit = totals["total_credit"] or Decimal("0")
        
        # إضافة الرصيد الافتتاحي
        opening_balance = Decimal("0")
        if self.opening_balance:
            opening_date = self.opening_balance_date or date(2020, 1, 1)
            if (not date_from or opening_date >= date_from) and (
                not date_to or opening_date <= date_to
            ):
                opening_balance = self.opening_balance
                
        # حساب الرصيد حسب طبيعة الحساب
        if self.nature == "debit":
            balance = opening_balance + total_debit - total_credit
        else:
            balance = opening_balance + total_credit - total_debit
            
        # حفظ النتيجة في التخزين المؤقت لمدة 15 دقيقة
        if use_cache:
            cache.set(cache_key, float(balance), 900)  # 15 minutes
            
        return balance

    def update_balance_atomic(self, amount, operation="add"):
        """
        [DEPRECATED / PROTECTED]
        تم تحييد هذه الدالة لمنع أي تعديل عشوائي على الرصيد الافتتاحي (opening_balance).
        أرصدة الحسابات تُدار حصراً عبر قيود اليومية (Journal Entries).
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"ChartOfAccounts.update_balance_atomic called for account {self.id} ({self.code}). "
            f"Direct balance manipulation is prohibited; ledger entries are used instead."
        )
        return (True, "تم تسجيل العملية في دفتر الأستاذ", self.current_balance)

    def check_low_balance_alert_enhanced(self):
        """
        فحص محسن لتنبيه الرصيد المنخفض مع تفاصيل إضافية
        
        العائد:
            dict: معلومات مفصلة عن حالة الرصيد
        """
        from decimal import Decimal
        
        result = {
            'has_alert': False,
            'current_balance': Decimal('0'),
            'threshold': None,
            'difference': None,
            'percentage': None,
            'severity': 'normal',  # normal, warning, critical
            'message': '',
            'recommendations': []
        }
        
        # حساب الرصيد الحالي بالطريقة المحسنة
        current_balance = self.get_balance_optimized()
        result['current_balance'] = current_balance
        
        # التحقق من تفعيل التنبيه
        if not self.low_balance_alert or not self.low_balance_threshold:
            result['message'] = 'تنبيه الرصيد المنخفض غير مفعل'
            return result
            
        threshold = self.low_balance_threshold
        result['threshold'] = threshold
        
        # حساب الفرق والنسبة
        difference = current_balance - threshold
        result['difference'] = difference
        
        if threshold != 0:
            result['percentage'] = (current_balance / threshold) * 100
        
        # تحديد مستوى الخطورة
        if current_balance <= 0:
            result['severity'] = 'critical'
            result['has_alert'] = True
            result['message'] = 'تحذير: الرصيد سالب أو صفر'
            result['recommendations'].extend([
                'إيداع مبلغ فوري',
                'مراجعة المعاملات الأخيرة',
                'التواصل مع الإدارة المالية'
            ])
        elif current_balance <= threshold * Decimal('0.5'):
            result['severity'] = 'critical'
            result['has_alert'] = True
            result['message'] = f'تحذير حرج: الرصيد أقل من 50% من الحد المسموح'
            result['recommendations'].extend([
                'إيداع مبلغ عاجل',
                'مراجعة خطة التدفق النقدي'
            ])
        elif current_balance <= threshold:
            result['severity'] = 'warning'
            result['has_alert'] = True
            result['message'] = f'تنبيه: الرصيد أقل من الحد المسموح'
            result['recommendations'].extend([
                'التخطيط لإيداع مبلغ قريباً',
                'مراقبة المعاملات القادمة'
            ])
        else:
            result['message'] = 'الرصيد ضمن الحد المسموح'
            
        # إضافة توصيات عامة للحسابات البنكية
        if self.is_bank_account and result['has_alert']:
            result['recommendations'].extend([
                'التحقق من كشف الحساب البنكي',
                'مراجعة المدفوعات المعلقة'
            ])
            
        return result


class AccountGroup(models.Model):
    """
    مجموعات الحسابات لتسهيل التصنيف والتقارير
    """

    name = models.CharField(_("اسم المجموعة"), max_length=100)
    description = models.TextField(_("الوصف"), blank=True, null=True)
    accounts = models.ManyToManyField(
        "ChartOfAccounts", verbose_name=_("الحسابات"), related_name="groups", blank=True
    )

    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="account_groups_created",
    )

    class Meta:
        verbose_name = _("مجموعة حسابات")
        verbose_name_plural = _("مجموعات الحسابات")
        ordering = ["name"]

    def __str__(self):
        return self.name
