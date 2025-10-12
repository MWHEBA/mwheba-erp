"""
خدمة شاملة لإدارة المصروفات والإيرادات مع ربط كامل بالنظام المالي
"""

from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal
import logging

from ..models import (
    ChartOfAccounts,
    JournalEntry,
    JournalEntryLine,
    AccountingPeriod,
    AccountType,
)

try:
    from client.models import Customer
    from supplier.models import Supplier
except ImportError:
    Customer = None
    Supplier = None

logger = logging.getLogger(__name__)


class ExpenseIncomeService:
    """خدمة موحدة لإدارة المصروفات والإيرادات"""

    @staticmethod
    def create_expense(data, user):
        """
        إنشاء مصروف جديد مع قيد محاسبي
        """
        try:
            with transaction.atomic():
                # إنشاء القيد المحاسبي
                journal_entry = JournalEntry.objects.create(
                    reference=f"EXP-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    description=data["description"],
                    date=data["expense_date"],
                    notes=data.get("notes", ""),
                    created_by=user,
                    status="draft",
                )

                # إضافة بنود القيد
                # 1. المصروف (مدين)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=data["expense_account"],
                    description=f"مصروف: {data['description']}",
                    debit_amount=data["amount"],
                    credit_amount=Decimal("0.00"),
                )

                # 2. حساب الدفع (دائن)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=data["payment_account"],
                    description=f"دفع مصروف: {data['description']}",
                    debit_amount=Decimal("0.00"),
                    credit_amount=data["amount"],
                )

                # ربط بالمورد إذا تم تحديده
                if data.get("supplier") and Supplier:
                    journal_entry.notes += f"\nالمورد: {data['supplier'].name}"
                    journal_entry.save()

                # ترحيل تلقائي إذا تم طلبه
                if data.get("auto_post", False):
                    ExpenseIncomeService.post_journal_entry(journal_entry, user)

                logger.info(f"تم إنشاء مصروف جديد: {journal_entry.reference}")
                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في إنشاء المصروف: {str(e)}")
            raise

    @staticmethod
    def create_income(data, user):
        """
        إنشاء إيراد جديد مع قيد محاسبي
        """
        try:
            with transaction.atomic():
                # إنشاء القيد المحاسبي
                journal_entry = JournalEntry.objects.create(
                    reference=f"INC-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    description=data["description"],
                    date=data["income_date"],
                    notes=data.get("notes", ""),
                    created_by=user,
                    status="draft",
                )

                # إضافة بنود القيد
                # 1. حساب الاستلام (مدين)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=data["receipt_account"],
                    description=f"استلام إيراد: {data['description']}",
                    debit_amount=data["amount"],
                    credit_amount=Decimal("0.00"),
                )

                # 2. الإيراد (دائن)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=data["income_account"],
                    description=f"إيراد: {data['description']}",
                    debit_amount=Decimal("0.00"),
                    credit_amount=data["amount"],
                )

                # ربط بالعميل إذا تم تحديده
                if data.get("customer") and Customer:
                    journal_entry.notes += f"\nالعميل: {data['customer'].name}"
                    journal_entry.save()

                # ترحيل تلقائي إذا تم طلبه
                if data.get("auto_post", False):
                    ExpenseIncomeService.post_journal_entry(journal_entry, user)

                logger.info(f"تم إنشاء إيراد جديد: {journal_entry.reference}")
                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في إنشاء الإيراد: {str(e)}")
            raise

    @staticmethod
    def update_expense(journal_entry, data, user):
        """
        تحديث مصروف موجود
        """
        try:
            with transaction.atomic():
                # التحقق من حالة القيد
                if journal_entry.status == "posted":
                    raise ValueError("لا يمكن تعديل قيد مرحل. يجب إلغاء الترحيل أولاً")

                # تحديث معلومات القيد
                journal_entry.description = data["description"]
                journal_entry.date = data["expense_date"]
                journal_entry.notes = data.get("notes", "")
                journal_entry.updated_by = user
                journal_entry.updated_at = timezone.now()

                # حذف البنود القديمة
                journal_entry.lines.all().delete()

                # إضافة البنود الجديدة
                # 1. المصروف (مدين)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=data["expense_account"],
                    description=f"مصروف: {data['description']}",
                    debit_amount=data["amount"],
                    credit_amount=Decimal("0.00"),
                )

                # 2. حساب الدفع (دائن)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=data["payment_account"],
                    description=f"دفع مصروف: {data['description']}",
                    debit_amount=Decimal("0.00"),
                    credit_amount=data["amount"],
                )

                # ربط بالمورد
                if data.get("supplier") and Supplier:
                    journal_entry.notes += f"\nالمورد: {data['supplier'].name}"

                journal_entry.save()

                logger.info(f"تم تحديث المصروف: {journal_entry.reference}")
                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في تحديث المصروف: {str(e)}")
            raise

    @staticmethod
    def update_income(journal_entry, data, user):
        """
        تحديث إيراد موجود
        """
        try:
            with transaction.atomic():
                # التحقق من حالة القيد
                if journal_entry.status == "posted":
                    raise ValueError("لا يمكن تعديل قيد مرحل. يجب إلغاء الترحيل أولاً")

                # تحديث معلومات القيد
                journal_entry.description = data["description"]
                journal_entry.date = data["income_date"]
                journal_entry.notes = data.get("notes", "")
                journal_entry.updated_by = user
                journal_entry.updated_at = timezone.now()

                # حذف البنود القديمة
                journal_entry.lines.all().delete()

                # إضافة البنود الجديدة
                # 1. حساب الاستلام (مدين)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=data["receipt_account"],
                    description=f"استلام إيراد: {data['description']}",
                    debit_amount=data["amount"],
                    credit_amount=Decimal("0.00"),
                )

                # 2. الإيراد (دائن)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=data["income_account"],
                    description=f"إيراد: {data['description']}",
                    debit_amount=Decimal("0.00"),
                    credit_amount=data["amount"],
                )

                # ربط بالعميل
                if data.get("customer") and Customer:
                    journal_entry.notes += f"\nالعميل: {data['customer'].name}"

                journal_entry.save()

                logger.info(f"تم تحديث الإيراد: {journal_entry.reference}")
                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في تحديث الإيراد: {str(e)}")
            raise

    @staticmethod
    def post_journal_entry(journal_entry, user):
        """
        ترحيل القيد المحاسبي
        """
        try:
            with transaction.atomic():
                if journal_entry.status == "posted":
                    raise ValueError("القيد مرحل مسبقاً")

                # التحقق من توازن القيد
                total_debit = sum(
                    line.debit_amount for line in journal_entry.lines.all()
                )
                total_credit = sum(
                    line.credit_amount for line in journal_entry.lines.all()
                )

                if total_debit != total_credit:
                    raise ValueError(
                        f"القيد غير متوازن: مدين {total_debit} ≠ دائن {total_credit}"
                    )

                # إنشاء أو الحصول على الفترة المحاسبية
                period = ExpenseIncomeService.get_or_create_accounting_period(
                    journal_entry.date
                )

                # ترحيل القيد
                journal_entry.status = "posted"
                journal_entry.posted_by = user
                journal_entry.posted_at = timezone.now()
                journal_entry.accounting_period = period
                journal_entry.save()

                # تحديث أرصدة الحسابات
                ExpenseIncomeService.update_account_balances(journal_entry)

                logger.info(f"تم ترحيل القيد: {journal_entry.reference}")
                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في ترحيل القيد: {str(e)}")
            raise

    @staticmethod
    def unpost_journal_entry(journal_entry, user):
        """
        إلغاء ترحيل القيد المحاسبي
        """
        try:
            with transaction.atomic():
                if journal_entry.status != "posted":
                    raise ValueError("القيد غير مرحل")

                # إلغاء الترحيل
                journal_entry.status = "draft"
                journal_entry.posted_by = None
                journal_entry.posted_at = None
                journal_entry.accounting_period = None
                journal_entry.updated_by = user
                journal_entry.updated_at = timezone.now()
                journal_entry.save()

                # تحديث أرصدة الحسابات (عكس)
                ExpenseIncomeService.reverse_account_balances(journal_entry)

                logger.info(f"تم إلغاء ترحيل القيد: {journal_entry.reference}")
                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في إلغاء ترحيل القيد: {str(e)}")
            raise

    @staticmethod
    def delete_journal_entry(journal_entry, user):
        """
        حذف القيد المحاسبي
        """
        try:
            with transaction.atomic():
                if journal_entry.status == "posted":
                    raise ValueError("لا يمكن حذف قيد مرحل. يجب إلغاء الترحيل أولاً")

                reference = journal_entry.reference
                journal_entry.delete()

                logger.info(f"تم حذف القيد: {reference}")
                return True

        except Exception as e:
            logger.error(f"خطأ في حذف القيد: {str(e)}")
            raise

    @staticmethod
    def get_or_create_accounting_period(date):
        """
        الحصول على الفترة المحاسبية أو إنشاؤها
        """
        try:
            # البحث عن فترة محاسبية تحتوي على التاريخ
            period = AccountingPeriod.objects.filter(
                start_date__lte=date, end_date__gte=date, is_closed=False
            ).first()

            if not period:
                # إنشاء فترة محاسبية جديدة (شهرية)
                start_date = date.replace(day=1)
                if date.month == 12:
                    end_date = date.replace(
                        year=date.year + 1, month=1, day=1
                    ) - timezone.timedelta(days=1)
                else:
                    end_date = date.replace(
                        month=date.month + 1, day=1
                    ) - timezone.timedelta(days=1)

                period = AccountingPeriod.objects.create(
                    name=f"فترة {date.strftime('%Y-%m')}",
                    start_date=start_date,
                    end_date=end_date,
                    is_closed=False,
                )

                logger.info(f"تم إنشاء فترة محاسبية جديدة: {period.name}")

            return period

        except Exception as e:
            logger.error(f"خطأ في إنشاء الفترة المحاسبية: {str(e)}")
            raise

    @staticmethod
    def update_account_balances(journal_entry):
        """
        تحديث أرصدة الحسابات بعد الترحيل
        """
        try:
            for line in journal_entry.lines.all():
                account = line.account

                # تحديث الرصيد الحالي
                if line.debit_amount > 0:
                    account.current_balance += line.debit_amount
                elif line.credit_amount > 0:
                    account.current_balance -= line.credit_amount

                account.save()

                logger.debug(
                    f"تم تحديث رصيد الحساب {account.code}: {account.current_balance}"
                )

        except Exception as e:
            logger.error(f"خطأ في تحديث أرصدة الحسابات: {str(e)}")
            raise

    @staticmethod
    def reverse_account_balances(journal_entry):
        """
        عكس تحديث أرصدة الحسابات عند إلغاء الترحيل
        """
        try:
            for line in journal_entry.lines.all():
                account = line.account

                # عكس تحديث الرصيد
                if line.debit_amount > 0:
                    account.current_balance -= line.debit_amount
                elif line.credit_amount > 0:
                    account.current_balance += line.credit_amount

                account.save()

                logger.debug(
                    f"تم عكس تحديث رصيد الحساب {account.code}: {account.current_balance}"
                )

        except Exception as e:
            logger.error(f"خطأ في عكس تحديث أرصدة الحسابات: {str(e)}")
            raise

    @staticmethod
    def get_expense_statistics(date_from=None, date_to=None):
        """
        الحصول على إحصائيات المصروفات
        """
        try:
            # فلترة القيود حسب التاريخ
            queryset = JournalEntry.objects.filter(reference__startswith="EXP-")

            if date_from:
                queryset = queryset.filter(date__gte=date_from)
            if date_to:
                queryset = queryset.filter(date__lte=date_to)

            # حساب الإحصائيات
            total_expenses = Decimal("0.00")
            posted_expenses = Decimal("0.00")
            draft_expenses = Decimal("0.00")

            for entry in queryset:
                amount = sum(
                    line.debit_amount
                    for line in entry.lines.all()
                    if line.debit_amount > 0
                )
                total_expenses += amount

                if entry.status == "posted":
                    posted_expenses += amount
                else:
                    draft_expenses += amount

            return {
                "total_expenses": total_expenses,
                "posted_expenses": posted_expenses,
                "draft_expenses": draft_expenses,
                "count": queryset.count(),
            }

        except Exception as e:
            logger.error(f"خطأ في حساب إحصائيات المصروفات: {str(e)}")
            return {
                "total_expenses": Decimal("0.00"),
                "posted_expenses": Decimal("0.00"),
                "draft_expenses": Decimal("0.00"),
                "count": 0,
            }

    @staticmethod
    def get_income_statistics(date_from=None, date_to=None):
        """
        الحصول على إحصائيات الإيرادات
        """
        try:
            # فلترة القيود حسب التاريخ
            queryset = JournalEntry.objects.filter(reference__startswith="INC-")

            if date_from:
                queryset = queryset.filter(date__gte=date_from)
            if date_to:
                queryset = queryset.filter(date__lte=date_to)

            # حساب الإحصائيات
            total_incomes = Decimal("0.00")
            posted_incomes = Decimal("0.00")
            draft_incomes = Decimal("0.00")

            for entry in queryset:
                amount = sum(
                    line.credit_amount
                    for line in entry.lines.all()
                    if line.credit_amount > 0
                )
                total_incomes += amount

                if entry.status == "posted":
                    posted_incomes += amount
                else:
                    draft_incomes += amount

            return {
                "total_incomes": total_incomes,
                "posted_incomes": posted_incomes,
                "draft_incomes": draft_incomes,
                "count": queryset.count(),
            }

        except Exception as e:
            logger.error(f"خطأ في حساب إحصائيات الإيرادات: {str(e)}")
            return {
                "total_incomes": Decimal("0.00"),
                "posted_incomes": Decimal("0.00"),
                "draft_incomes": Decimal("0.00"),
                "count": 0,
            }
