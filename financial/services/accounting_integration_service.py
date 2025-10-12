"""
خدمة التكامل المحاسبي الشاملة
ربط المبيعات والمشتريات بالنظام المحاسبي الجديد
"""
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
import logging

from ..models.chart_of_accounts import ChartOfAccounts, AccountType
from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from ..services.account_helper import AccountHelperService

logger = logging.getLogger(__name__)
User = get_user_model()


class AccountingIntegrationService:
    """
    خدمة التكامل المحاسبي الشاملة
    """

    # أكواد الحسابات الأساسية المطلوبة (حسب دليل الحسابات المعتمد)
    DEFAULT_ACCOUNTS = {
        "sales_revenue": "41010",  # إيرادات المبيعات
        "cost_of_goods_sold": "51010",  # تكلفة البضاعة المباعة
        "inventory": "11051",  # مخزون بضاعة جاهزة
        "accounts_receivable": "11030",  # العملاء
        "accounts_payable": "21010",  # الموردون
        "cash": "11011",  # الصندوق الرئيسي
        "bank": "11021",  # البنك الأهلي
        "purchase_expense": "51010",  # تكلفة البضاعة المباعة
    }

    @classmethod
    def create_sale_journal_entry(
        cls, sale, user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي لفاتورة مبيعات
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = cls._get_required_accounts_for_sale()
                if not accounts:
                    logger.error(
                        "لا يمكن العثور على الحسابات المحاسبية المطلوبة للمبيعات"
                    )
                    return None

                # إنشاء القيد الرئيسي
                journal_entry = JournalEntry.objects.create(
                    number=cls._generate_journal_number("SALE", sale.number),
                    date=sale.date,
                    entry_type="automatic",
                    status="posted",  # ترحيل تلقائي
                    reference=f"فاتورة مبيعات رقم {sale.number}",
                    description=f"مبيعات للعميل {sale.customer.name}",
                    created_by=user or sale.created_by,
                    accounting_period=cls._get_accounting_period(sale.date),
                )

                # قيد العميل (مدين) - دائماً نسجل في حساب العملاء
                # القيد النقدي سيتم في قيد الدفعة المنفصل
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts["accounts_receivable"],
                    debit=sale.total,
                    credit=Decimal("0.00"),
                    description=f"مبيعات - العميل {sale.customer.name} - فاتورة {sale.number}",
                )

                # قيد الإيرادات (دائن)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts["sales_revenue"],
                    debit=Decimal("0.00"),
                    credit=sale.total,
                    description=f"إيرادات مبيعات - فاتورة {sale.number}",
                )

                # قيد تكلفة البضاعة المباعة (إذا كانت متاحة)
                total_cost = cls._calculate_sale_cost(sale)
                if total_cost > 0:
                    # مدين تكلفة البضاعة المباعة
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=accounts["cost_of_goods_sold"],
                        debit=total_cost,
                        credit=Decimal("0.00"),
                        description=f"تكلفة البضاعة المباعة - فاتورة {sale.number}",
                    )

                    # دائن المخزون
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=accounts["inventory"],
                        debit=Decimal("0.00"),
                        credit=total_cost,
                        description=f"تخفيض المخزون - فاتورة {sale.number}",
                    )

                # ربط القيد بالفاتورة
                sale.journal_entry = journal_entry
                sale.save(update_fields=["journal_entry"])

                logger.info(f"تم إنشاء قيد محاسبي للمبيعات: {journal_entry.number}")
                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد المبيعات: {str(e)}")
            return None

    @classmethod
    def create_purchase_journal_entry(
        cls, purchase, user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي لفاتورة مشتريات
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = cls._get_required_accounts_for_purchase()
                if not accounts:
                    logger.error(
                        "لا يمكن العثور على الحسابات المحاسبية المطلوبة للمشتريات"
                    )
                    return None

                # إنشاء القيد الرئيسي
                journal_entry = JournalEntry.objects.create(
                    number=cls._generate_journal_number("PURCHASE", purchase.number),
                    date=purchase.date,
                    entry_type="automatic",
                    status="posted",  # ترحيل تلقائي
                    reference=f"فاتورة مشتريات رقم {purchase.number}",
                    description=f"مشتريات من المورد {purchase.supplier.name}",
                    created_by=user or purchase.created_by,
                    accounting_period=cls._get_accounting_period(purchase.date),
                )

                # قيد المخزون أو المصروفات (مدين)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts["inventory"],
                    debit=purchase.total,
                    credit=Decimal("0.00"),
                    description=f"مشتريات مخزون - فاتورة {purchase.number}",
                )

                # قيد المورد (دائن) - دائماً نسجل في حساب الموردين
                # القيد النقدي سيتم في قيد الدفعة المنفصل
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts["accounts_payable"],
                    debit=Decimal("0.00"),
                    credit=purchase.total,
                    description=f"مشتريات - المورد {purchase.supplier.name} - فاتورة {purchase.number}",
                )

                # ربط القيد بالفاتورة
                purchase.journal_entry = journal_entry
                purchase.save(update_fields=["journal_entry"])

                logger.info(f"تم إنشاء قيد محاسبي للمشتريات: {journal_entry.number}")
                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد المشتريات: {str(e)}")
            return None

    @classmethod
    def create_payment_journal_entry(
        cls,
        payment,
        payment_type: str,  # 'sale_payment' or 'purchase_payment'
        user: Optional[User] = None,
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي للمدفوعات
        """
        try:
            with transaction.atomic():
                accounts = cls._get_required_accounts_for_payment()
                if not accounts:
                    return None

                # تحديد نوع القيد
                if payment_type == "sale_payment":
                    # دفعة من عميل
                    reference = f"دفعة من العميل - فاتورة {payment.sale.number}"
                    description = f"استلام دفعة من {payment.sale.customer.name}"

                    # مدين الصندوق/البنك
                    account_debit = (
                        accounts["cash"]
                        if payment.payment_method == "cash"
                        else accounts["bank"]
                    )
                    # دائن العملاء
                    account_credit = accounts["accounts_receivable"]

                elif payment_type == "purchase_payment":
                    # دفعة لمورد
                    reference = f"دفعة للمورد - فاتورة {payment.purchase.number}"
                    description = f"دفع للمورد {payment.purchase.supplier.name}"

                    # مدين الموردين
                    account_debit = accounts["accounts_payable"]
                    # دائن الصندوق/البنك
                    account_credit = (
                        accounts["cash"]
                        if payment.payment_method == "cash"
                        else accounts["bank"]
                    )

                else:
                    logger.error(f"نوع دفعة غير معروف: {payment_type}")
                    return None

                # إنشاء القيد
                journal_entry = JournalEntry.objects.create(
                    number=cls._generate_journal_number("PAYMENT", payment.id),
                    date=payment.payment_date,
                    entry_type="automatic",
                    status="posted",  # ترحيل تلقائي
                    reference=reference,
                    description=description,
                    created_by=user or payment.created_by,
                    accounting_period=cls._get_accounting_period(payment.payment_date),
                )

                # بنود القيد
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=account_debit,
                    debit=payment.amount,
                    credit=Decimal("0.00"),
                    description=description,
                )

                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=account_credit,
                    debit=Decimal("0.00"),
                    credit=payment.amount,
                    description=description,
                )

                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد الدفعة: {str(e)}")
            return None

    @classmethod
    def _get_required_accounts_for_sale(cls) -> Dict[str, ChartOfAccounts]:
        """الحصول على الحسابات المطلوبة للمبيعات"""
        try:
            accounts = {}
            required_codes = [
                "sales_revenue",
                "cost_of_goods_sold",
                "inventory",
                "accounts_receivable",
                "cash",
                "bank",
            ]

            for account_key in required_codes:
                code = cls.DEFAULT_ACCOUNTS[account_key]
                account = ChartOfAccounts.objects.filter(
                    code=code, is_active=True
                ).first()
                if account:
                    accounts[account_key] = account
                else:
                    logger.warning(f"لا يمكن العثور على الحساب: {code}")

            return accounts if len(accounts) >= 4 else None  # على الأقل 4 حسابات أساسية
        except Exception as e:
            logger.error(f"خطأ في الحصول على حسابات المبيعات: {str(e)}")
            return None

    @classmethod
    def _get_required_accounts_for_purchase(cls) -> Dict[str, ChartOfAccounts]:
        """الحصول على الحسابات المطلوبة للمشتريات"""
        try:
            accounts = {}
            required_codes = [
                "inventory",
                "accounts_payable",
                "cash",
                "bank",
                "purchase_expense",
            ]

            for account_key in required_codes:
                code = cls.DEFAULT_ACCOUNTS[account_key]
                account = ChartOfAccounts.objects.filter(
                    code=code, is_active=True
                ).first()
                if account:
                    accounts[account_key] = account
                else:
                    logger.warning(f"لا يمكن العثور على الحساب: {code}")

            return accounts if len(accounts) >= 4 else None
        except Exception as e:
            logger.error(f"خطأ في الحصول على حسابات المشتريات: {str(e)}")
            return None

    @classmethod
    def _get_required_accounts_for_payment(cls) -> Dict[str, ChartOfAccounts]:
        """الحصول على الحسابات المطلوبة للمدفوعات"""
        try:
            accounts = {}
            required_codes = ["accounts_receivable", "accounts_payable", "cash", "bank"]

            for account_key in required_codes:
                code = cls.DEFAULT_ACCOUNTS[account_key]
                account = ChartOfAccounts.objects.filter(
                    code=code, is_active=True
                ).first()
                if account:
                    accounts[account_key] = account
                else:
                    logger.warning(f"لا يمكن العثور على الحساب: {code}")

            return accounts if len(accounts) >= 3 else None
        except Exception as e:
            logger.error(f"خطأ في الحصول على حسابات المدفوعات: {str(e)}")
            return None

    @classmethod
    def _calculate_sale_cost(cls, sale) -> Decimal:
        """حساب تكلفة البضاعة المباعة"""
        try:
            total_cost = Decimal("0.00")
            for item in sale.items.all():
                if hasattr(item.product, "cost_price") and item.product.cost_price:
                    total_cost += item.product.cost_price * item.quantity

            # تسجيل للتشخيص
            if total_cost == 0:
                logger.warning(f"تكلفة البضاعة المباعة = 0 للفاتورة {sale.number}")
                for item in sale.items.all():
                    logger.warning(
                        f"  - المنتج: {item.product.name}, التكلفة: {item.product.cost_price}, الكمية: {item.quantity}"
                    )

            return total_cost
        except Exception as e:
            logger.error(f"خطأ في حساب تكلفة البضاعة: {str(e)}")
            return Decimal("0.00")

    @classmethod
    def _generate_journal_number(cls, prefix: str, reference: Any) -> str:
        """توليد رقم القيد"""
        timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
        return f"{prefix}-{reference}-{timestamp}"

    @classmethod
    def _get_accounting_period(cls, date) -> Optional[AccountingPeriod]:
        """الحصول على الفترة المحاسبية للتاريخ"""
        try:
            return AccountingPeriod.get_period_for_date(date)
        except Exception:
            return None

    @classmethod
    def setup_default_accounts(cls) -> bool:
        """إعداد الحسابات الأساسية المطلوبة"""
        try:
            with transaction.atomic():
                # إنشاء أنواع الحسابات إذا لم تكن موجودة
                account_types = cls._create_default_account_types()

                # إنشاء الحسابات الأساسية
                accounts_created = 0
                for account_key, code in cls.DEFAULT_ACCOUNTS.items():
                    if not ChartOfAccounts.objects.filter(code=code).exists():
                        account_data = cls._get_account_data(account_key, code)
                        if account_data:
                            account_type = account_types.get(account_data["type"])
                            if account_type:
                                ChartOfAccounts.objects.create(
                                    code=code,
                                    name=account_data["name"],
                                    name_en=account_data.get("name_en"),
                                    account_type=account_type,
                                    is_leaf=True,
                                    is_active=True,
                                    is_cash_account=account_data.get("is_cash", False),
                                    is_bank_account=account_data.get("is_bank", False),
                                    description=account_data.get("description", ""),
                                )
                                accounts_created += 1

                logger.info(f"تم إنشاء {accounts_created} حساب محاسبي أساسي")
                return True

        except Exception as e:
            logger.error(f"خطأ في إعداد الحسابات الأساسية: {str(e)}")
            return False

    @classmethod
    def _create_default_account_types(cls) -> Dict[str, AccountType]:
        """إنشاء أنواع الحسابات الأساسية"""
        account_types = {}

        types_data = [
            {"code": "ASSET", "name": "أصول", "category": "asset", "nature": "debit"},
            {
                "code": "LIABILITY",
                "name": "خصوم",
                "category": "liability",
                "nature": "credit",
            },
            {
                "code": "REVENUE",
                "name": "إيرادات",
                "category": "revenue",
                "nature": "credit",
            },
            {
                "code": "EXPENSE",
                "name": "مصروفات",
                "category": "expense",
                "nature": "debit",
            },
        ]

        for type_data in types_data:
            account_type, created = AccountType.objects.get_or_create(
                code=type_data["code"],
                defaults={
                    "name": type_data["name"],
                    "category": type_data["category"],
                    "nature": type_data["nature"],
                    "is_active": True,
                },
            )
            account_types[type_data["category"]] = account_type

        return account_types

    @classmethod
    def _get_account_data(cls, account_key: str, code: str) -> Optional[Dict]:
        """الحصول على بيانات الحساب"""
        accounts_data = {
            "sales_revenue": {
                "name": "إيرادات المبيعات",
                "name_en": "Sales Revenue",
                "type": "revenue",
                "description": "إيرادات من بيع البضائع والخدمات",
            },
            "cost_of_goods_sold": {
                "name": "تكلفة البضاعة المباعة",
                "name_en": "Cost of Goods Sold",
                "type": "expense",
                "description": "تكلفة البضائع التي تم بيعها",
            },
            "inventory": {
                "name": "المخزون",
                "name_en": "Inventory",
                "type": "asset",
                "description": "قيمة البضائع المخزنة",
            },
            "accounts_receivable": {
                "name": "العملاء",
                "name_en": "Accounts Receivable",
                "type": "asset",
                "description": "المبالغ المستحقة من العملاء",
            },
            "accounts_payable": {
                "name": "الموردين",
                "name_en": "Accounts Payable",
                "type": "liability",
                "description": "المبالغ المستحقة للموردين",
            },
            "cash": {
                "name": "الصندوق",
                "name_en": "Cash",
                "type": "asset",
                "is_cash": True,
                "description": "النقدية في الصندوق",
            },
            "bank": {
                "name": "البنك",
                "name_en": "Bank",
                "type": "asset",
                "is_bank": True,
                "description": "الأرصدة البنكية",
            },
            "purchase_expense": {
                "name": "مصروفات المشتريات",
                "name_en": "Purchase Expenses",
                "type": "expense",
                "description": "مصروفات متعلقة بالمشتريات",
            },
        }

        return accounts_data.get(account_key)
