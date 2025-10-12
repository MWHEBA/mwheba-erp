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

    code = models.CharField(_("كود النوع"), max_length=10, unique=True)
    name = models.CharField(_("اسم النوع"), max_length=100)
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
        ordering = ["code"]

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
        regex=r"^\d{4,8}$", message=_("كود الحساب يجب أن يكون من 4 إلى 8 أرقام")
    )

    code = models.CharField(
        _("كود الحساب"), max_length=8, unique=True, validators=[code_validator]
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

    # الرصيد الافتتاحي
    opening_balance = models.DecimalField(
        _("الرصيد الافتتاحي"),
        max_digits=15,
        decimal_places=2,
        default=0.00,
        help_text=_("الرصيد الافتتاحي للحساب"),
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
        # حساب المستوى تلقائياً
        if self.parent:
            self.level = self.parent.level + 1
            # إذا كان للحساب أب، فالأب ليس حساباً نهائياً
            self.parent.is_leaf = False
            self.parent.save(update_fields=["is_leaf"])
        else:
            self.level = 1

        super().save(*args, **kwargs)

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

        if not date_to:
            date_to = timezone.now().date()

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
        تحديث رصيد الحساب مع ضمان سلامة البيانات

        الوسائط:
            amount: المبلغ للإضافة أو الخصم
            operation: العملية ('add' للإضافة، 'subtract' للخصم)

        العائد:
            boolean: نجاح أو فشل العملية
        """
        from django.db import IntegrityError, transaction

        print(
            f"Updating balance for account {self.id} - {self.name}: Current={self.opening_balance}, Amount={amount}, Operation={operation}"
        )

        # حساب الرصيد الجديد
        current_balance = self.get_balance()

        if operation == "add":
            new_balance = current_balance + amount
        elif operation == "subtract":
            if current_balance >= amount:
                new_balance = current_balance - amount
            else:
                print(
                    f"Warning: Attempted to subtract {amount} from {current_balance} for account {self.id} - {self.name}"
                )
                new_balance = 0
        else:
            raise ValueError(
                f"Invalid operation: {operation}. Use 'add' or 'subtract'."
            )

        try:
            from django.utils import timezone

            # تحديث الرصيد الافتتاحي كبديل لحفظ الرصيد الحالي
            with transaction.atomic():
                ChartOfAccounts.objects.filter(id=self.id).update(
                    opening_balance=new_balance, updated_at=timezone.now()
                )
                # تحديث الكائن المحلي ليعكس التغييرات المخزنة
                self.refresh_from_db(fields=["opening_balance", "updated_at"])
                print(
                    f"Successfully updated balance for account {self.id} - {self.name}: New balance={new_balance}"
                )
                return True
        except IntegrityError as e:
            print(f"Database error updating balance: {str(e)}")
            return False
        except Exception as e:
            print(f"Error updating balance: {str(e)}")
            return False

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

                # إنشاء قيد التسوية
                reconciliation_entry = JournalEntry.objects.create(
                    reference=f"تسوية بنكية - {self.name}",
                    description=f"تسوية بنكية بتاريخ {reconciliation_date} - فرق {difference}",
                    date=reconciliation_date,
                )

                # إضافة بند القيد
                if difference > 0:
                    # رصيد البنك أكبر - مدين الحساب البنكي
                    JournalEntryLine.objects.create(
                        journal_entry=reconciliation_entry,
                        account=self,
                        debit=difference,
                        credit=0,
                        description=f"تسوية بنكية - زيادة في الرصيد",
                    )
                else:
                    # رصيد البنك أقل - دائن الحساب البنكي
                    JournalEntryLine.objects.create(
                        journal_entry=reconciliation_entry,
                        account=self,
                        debit=0,
                        credit=abs(difference),
                        description=f"تسوية بنكية - نقص في الرصيد",
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
        return self.is_leaf and self.is_active

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
