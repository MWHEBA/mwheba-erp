"""
خدمة إدارة المعاملات المالية المحسنة
"""
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple

from ..models.chart_of_accounts import ChartOfAccounts
from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from ..models.transactions import (
    FinancialTransaction,
    ExpenseTransaction,
    IncomeTransaction,
)
from ..models.categories import FinancialCategory
from .journal_service import JournalEntryService

logger = logging.getLogger(__name__)


class TransactionService:
    """
    خدمة شاملة لإدارة المعاملات المالية
    """

    @staticmethod
    def create_income_transaction(
        title: str,
        amount: Decimal,
        account_code: str,
        category_id: Optional[int] = None,
        description: str = "",
        date: Optional[timezone.datetime] = None,
        customer_name: str = "",
        invoice_number: str = "",
        user=None,
    ) -> IncomeTransaction:
        """
        إنشاء معاملة إيراد جديدة
        """
        try:
            with transaction.atomic():
                # التحقق من وجود الحساب
                account = ChartOfAccounts.objects.get(code=account_code, is_active=True)

                # التحقق من التصنيف إذا تم تحديدها
                category = None
                if category_id:
                    category = FinancialCategory.objects.get(
                        id=category_id, type__in=["income", "both"], is_active=True
                    )

                # إنشاء معاملة الإيراد
                income = IncomeTransaction.objects.create(
                    title=title,
                    description=description,
                    account=account,
                    amount=amount,
                    date=date or timezone.now().date(),
                    category=category,
                    vendor_name=customer_name,  # استخدام vendor_name للعميل
                    invoice_number=invoice_number,
                    status="draft",
                    created_by=user,
                )

                # تحديد ما إذا كانت تحتاج موافقة
                if amount >= Decimal("1000.00") or (
                    category and category.requires_approval
                ):
                    income.requires_approval = True
                    income.status = "pending"
                else:
                    income.status = "approved"

                income.save()

                # إنشاء القيد المحاسبي إذا كانت معتمدة
                if income.status == "approved":
                    income.process()

                logger.info(f"تم إنشاء معاملة إيراد: {income.title} - {income.amount}")
                return income

        except Exception as e:
            logger.error(f"خطأ في إنشاء معاملة الإيراد: {str(e)}")
            raise ValidationError(f"فشل في إنشاء معاملة الإيراد: {str(e)}")

    @staticmethod
    def create_expense_transaction(
        title: str,
        amount: Decimal,
        account_code: str,
        category_id: Optional[int] = None,
        description: str = "",
        date: Optional[timezone.datetime] = None,
        vendor_name: str = "",
        invoice_number: str = "",
        tax_amount: Decimal = Decimal("0"),
        user=None,
    ) -> ExpenseTransaction:
        """
        إنشاء معاملة مصروف جديدة
        """
        try:
            with transaction.atomic():
                # التحقق من وجود الحساب
                account = ChartOfAccounts.objects.get(code=account_code, is_active=True)

                # التحقق من التصنيف إذا تم تحديدها
                category = None
                if category_id:
                    category = FinancialCategory.objects.get(
                        id=category_id, type__in=["expense", "both"], is_active=True
                    )

                # إنشاء معاملة المصروف
                expense = ExpenseTransaction.objects.create(
                    title=title,
                    description=description,
                    account=account,
                    amount=amount,
                    date=date or timezone.now().date(),
                    category=category,
                    vendor_name=vendor_name,
                    invoice_number=invoice_number,
                    tax_amount=tax_amount,
                    status="draft",
                    created_by=user,
                )

                # تحديد ما إذا كانت تحتاج موافقة
                if amount >= Decimal("1000.00") or (
                    category and category.requires_approval
                ):
                    expense.requires_approval = True
                    expense.status = "pending"
                else:
                    expense.status = "approved"

                expense.save()

                # إنشاء القيد المحاسبي إذا كانت معتمدة
                if expense.status == "approved":
                    expense.process()

                logger.info(
                    f"تم إنشاء معاملة مصروف: {expense.title} - {expense.amount}"
                )
                return expense

        except Exception as e:
            logger.error(f"خطأ في إنشاء معاملة المصروف: {str(e)}")
            raise ValidationError(f"فشل في إنشاء معاملة المصروف: {str(e)}")

    @staticmethod
    def create_transfer_transaction(
        title: str,
        amount: Decimal,
        from_account_code: str,
        to_account_code: str,
        description: str = "",
        date: Optional[timezone.datetime] = None,
        user=None,
    ) -> FinancialTransaction:
        """
        إنشاء معاملة تحويل بين الحسابات
        """
        try:
            with transaction.atomic():
                # التحقق من وجود الحسابات
                from_account = ChartOfAccounts.objects.get(
                    code=from_account_code, is_active=True
                )
                to_account = ChartOfAccounts.objects.get(
                    code=to_account_code, is_active=True
                )

                # التحقق من كفاية الرصيد
                from_balance = from_account.get_balance()
                if from_balance < amount:
                    raise ValidationError(
                        f"رصيد الحساب {from_account.name} غير كافي للتحويل"
                    )

                # إنشاء معاملة التحويل
                transfer = FinancialTransaction.objects.create(
                    transaction_type="transfer",
                    title=title,
                    description=description,
                    account=from_account,
                    to_account=to_account,
                    amount=amount,
                    date=date or timezone.now().date(),
                    status="approved",  # التحويلات لا تحتاج موافقة عادة
                    created_by=user,
                )

                # إنشاء القيد المحاسبي
                transfer.process()

                logger.info(
                    f"تم إنشاء معاملة تحويل: {transfer.title} - {transfer.amount}"
                )
                return transfer

        except Exception as e:
            logger.error(f"خطأ في إنشاء معاملة التحويل: {str(e)}")
            raise ValidationError(f"فشل في إنشاء معاملة التحويل: {str(e)}")

    @staticmethod
    def approve_transaction(transaction_id: int, approved_by_user) -> bool:
        """
        اعتماد معاملة مالية
        """
        try:
            with transaction.atomic():
                trans = FinancialTransaction.objects.get(id=transaction_id)

                if trans.status != "pending":
                    raise ValidationError("يمكن اعتماد المعاملات المعلقة فقط")

                # اعتماد المعاملة
                trans.approve(approved_by_user)

                # إنشاء القيد المحاسبي
                trans.process()

                logger.info(f"تم اعتماد المعاملة: {trans.title}")
                return True

        except Exception as e:
            logger.error(f"خطأ في اعتماد المعاملة: {str(e)}")
            return False

    @staticmethod
    def reject_transaction(transaction_id: int, reason: str = "") -> bool:
        """
        رفض معاملة مالية
        """
        try:
            trans = FinancialTransaction.objects.get(id=transaction_id)

            if trans.status not in ["pending", "draft"]:
                raise ValidationError("يمكن رفض المعاملات المعلقة أو المسودات فقط")

            trans.reject()

            if reason:
                trans.description = f"{trans.description}\nسبب الرفض: {reason}"
                trans.save(update_fields=["description"])

            logger.info(f"تم رفض المعاملة: {trans.title}")
            return True

        except Exception as e:
            logger.error(f"خطأ في رفض المعاملة: {str(e)}")
            return False

    @staticmethod
    def get_pending_transactions(user=None) -> List[FinancialTransaction]:
        """
        الحصول على المعاملات المعلقة التي تحتاج موافقة
        """
        transactions = FinancialTransaction.objects.filter(
            status="pending", requires_approval=True
        ).order_by("-created_at")

        return list(transactions)

    @staticmethod
    def get_overdue_transactions() -> List[FinancialTransaction]:
        """
        الحصول على المعاملات المتأخرة
        """
        today = timezone.now().date()

        transactions = FinancialTransaction.objects.filter(
            due_date__lt=today, status__in=["approved", "pending"]
        ).order_by("due_date")

        return list(transactions)

    @staticmethod
    def get_transaction_summary(
        date_from: Optional[timezone.datetime] = None,
        date_to: Optional[timezone.datetime] = None,
        transaction_type: Optional[str] = None,
    ) -> Dict:
        """
        الحصول على ملخص المعاملات
        """
        transactions = FinancialTransaction.objects.filter(status="processed")

        if date_from:
            transactions = transactions.filter(date__gte=date_from)
        if date_to:
            transactions = transactions.filter(date__lte=date_to)
        if transaction_type:
            transactions = transactions.filter(transaction_type=transaction_type)

        # حساب الإحصائيات
        total_count = transactions.count()
        total_income = transactions.filter(transaction_type="income").aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0")

        total_expense = transactions.filter(transaction_type="expense").aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0")

        total_transfer = transactions.filter(transaction_type="transfer").aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0")

        return {
            "total_count": total_count,
            "total_income": total_income,
            "total_expense": total_expense,
            "total_transfer": total_transfer,
            "net_income": total_income - total_expense,
            "period_from": date_from,
            "period_to": date_to,
        }

    @staticmethod
    def create_opening_balances(balances_data: List[Dict]) -> int:
        """
        إنشاء الأرصدة الافتتاحية

        Args:
            balances_data: قائمة بالأرصدة في شكل:
            [
                {
                    'account_code': '1001',
                    'balance': Decimal('1000.00'),
                    'description': 'رصيد افتتاحي'
                }
            ]
        """
        created_count = 0

        try:
            with transaction.atomic():
                # الحصول على حساب الأرباح المحتجزة أو رأس المال
                equity_account = ChartOfAccounts.objects.filter(
                    account_type__category="equity", is_active=True, is_leaf=True
                ).first()

                if not equity_account:
                    raise ValidationError(
                        "لا يوجد حساب حقوق ملكية لإنشاء الأرصدة الافتتاحية"
                    )

                for balance_data in balances_data:
                    account_code = balance_data["account_code"]
                    balance = Decimal(str(balance_data["balance"]))
                    description = balance_data.get(
                        "description", f"رصيد افتتاحي - {account_code}"
                    )

                    if balance == 0:
                        continue

                    try:
                        account = ChartOfAccounts.objects.get(
                            code=account_code, is_active=True
                        )

                        # تحديد اتجاه القيد بناءً على طبيعة الحساب
                        if account.account_type.nature == "debit":
                            if balance > 0:
                                debit_account = account
                                credit_account = equity_account
                            else:
                                debit_account = equity_account
                                credit_account = account
                                balance = abs(balance)
                        else:  # credit nature
                            if balance > 0:
                                debit_account = equity_account
                                credit_account = account
                            else:
                                debit_account = account
                                credit_account = equity_account
                                balance = abs(balance)

                        # إنشاء القيد
                        entry = JournalEntryService.create_simple_entry(
                            debit_account=debit_account.code,
                            credit_account=credit_account.code,
                            amount=balance,
                            description=description,
                            reference=f"OPENING-{account_code}",
                            auto_post=True,
                        )

                        entry.entry_type = "opening"
                        entry.save()

                        created_count += 1

                    except ChartOfAccounts.DoesNotExist:
                        logger.warning(f"الحساب {account_code} غير موجود")
                        continue

                logger.info(f"تم إنشاء {created_count} رصيد افتتاحي")
                return created_count

        except Exception as e:
            logger.error(f"خطأ في إنشاء الأرصدة الافتتاحية: {str(e)}")
            raise ValidationError(f"فشل في إنشاء الأرصدة الافتتاحية: {str(e)}")

    @staticmethod
    def validate_account_balances() -> Tuple[bool, List[Dict]]:
        """
        التحقق من صحة أرصدة الحسابات
        """
        try:
            from ..services.balance_service import BalanceService

            issues = []
            accounts = ChartOfAccounts.objects.filter(is_active=True, is_leaf=True)

            for account in accounts:
                # فحص التنبيهات
                if account.check_low_balance_alert():
                    issues.append(
                        {
                            "account": account.name,
                            "code": account.code,
                            "issue": "رصيد منخفض",
                            "current_balance": account.get_balance(),
                            "threshold": account.low_balance_threshold,
                        }
                    )

                # فحص تجاوز حد الائتمان
                balance_status = account.get_balance_status()
                if balance_status["is_over_limit"]:
                    issues.append(
                        {
                            "account": account.name,
                            "code": account.code,
                            "issue": "تجاوز حد الائتمان",
                            "current_balance": balance_status["balance"],
                            "credit_limit": account.credit_limit,
                        }
                    )

            return len(issues) == 0, issues

        except Exception as e:
            logger.error(f"خطأ في التحقق من الأرصدة: {str(e)}")
            return False, [{"error": str(e)}]
