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

                # قيد العميل (مدين) - استخدام حساب العميل المحدد
                customer_account = cls._get_customer_account(sale.customer)
                if not customer_account:
                    # استخدام الحساب العام كحل أخير
                    customer_account = accounts["accounts_receivable"]
                    logger.warning(f"استخدام حساب العملاء العام للعميل {sale.customer.name}")
                
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=customer_account,
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

                # قيد المورد (دائن) - استخدام حساب المورد المحدد
                supplier_account = cls._get_supplier_account(purchase.supplier)
                if not supplier_account:
                    # استخدام الحساب العام كحل أخير
                    supplier_account = accounts["accounts_payable"]
                    logger.warning(f"استخدام حساب الموردين العام للمورد {purchase.supplier.name}")
                
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=supplier_account,
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
    def create_return_journal_entry(
        cls, sale_return, user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي لمرتجع مبيعات
        
        القيد المطلوب:
        من حـ/ إيرادات المبيعات (مدين)
            إلى حـ/ العملاء (دائن)
        
        من حـ/ المخزون (مدين)
            إلى حـ/ تكلفة البضاعة المباعة (دائن)
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات المطلوبة
                accounts = cls._get_required_accounts_for_sale()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة للمرتجعات")
                    return None

                # حساب إجمالي المرتجع والتكلفة
                total_return = Decimal("0.00")
                total_cost = Decimal("0.00")
                
                for item in sale_return.items.all():
                    total_return += item.total
                    if hasattr(item.sale_item.product, "cost_price") and item.sale_item.product.cost_price:
                        total_cost += item.sale_item.product.cost_price * item.quantity

                # إنشاء القيد الرئيسي
                journal_entry = JournalEntry.objects.create(
                    number=cls._generate_journal_number("RETURN", sale_return.number),
                    date=sale_return.date,
                    entry_type="automatic",
                    status="posted",
                    reference=f"مرتجع مبيعات رقم {sale_return.number} - فاتورة {sale_return.sale.number}",
                    description=f"مرتجع من العميل {sale_return.sale.customer.name}",
                    created_by=user or sale_return.created_by,
                    accounting_period=cls._get_accounting_period(sale_return.date),
                )

                # قيد عكس الإيراد (مدين إيرادات، دائن عملاء)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts["sales_revenue"],
                    debit=total_return,
                    credit=Decimal("0.00"),
                    description=f"عكس إيرادات - مرتجع {sale_return.number}",
                )

                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=accounts["accounts_receivable"],
                    debit=Decimal("0.00"),
                    credit=total_return,
                    description=f"تخفيض ذمم العميل {sale_return.sale.customer.name} - مرتجع {sale_return.number}",
                )

                # قيد إرجاع المخزون (مدين مخزون، دائن تكلفة)
                if total_cost > 0:
                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=accounts["inventory"],
                        debit=total_cost,
                        credit=Decimal("0.00"),
                        description=f"إرجاع مخزون - مرتجع {sale_return.number}",
                    )

                    JournalEntryLine.objects.create(
                        journal_entry=journal_entry,
                        account=accounts["cost_of_goods_sold"],
                        debit=Decimal("0.00"),
                        credit=total_cost,
                        description=f"عكس تكلفة البضاعة - مرتجع {sale_return.number}",
                    )

                # ربط القيد بالمرتجع
                sale_return.journal_entry = journal_entry
                sale_return.save(update_fields=["journal_entry"])

                logger.info(f"✅ تم إنشاء قيد محاسبي للمرتجع: {journal_entry.number}")
                return journal_entry

        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء قيد المرتجع: {str(e)}")
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

                    # مدين حساب المورد المحدد
                    supplier_account = cls._get_supplier_account(payment.purchase.supplier)
                    account_debit = supplier_account if supplier_account else accounts["accounts_payable"]
                    
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
            items_without_cost = []
            
            for item in sale.items.all():
                # التحقق من وجود حقل cost_price
                if not hasattr(item.product, "cost_price"):
                    logger.warning(f"المنتج {item.product.name} لا يحتوي على حقل cost_price")
                    items_without_cost.append(item.product.name)
                    continue
                
                # التحقق من أن التكلفة ليست None
                if item.product.cost_price is None:
                    logger.warning(f"المنتج {item.product.name} ليس له تكلفة محددة (None)")
                    items_without_cost.append(item.product.name)
                    continue
                
                # حساب تكلفة البند (حتى لو كانت صفر)
                item_cost = item.product.cost_price * item.quantity
                total_cost += item_cost
                
                logger.debug(
                    f"  البند: {item.product.name}, الكمية: {item.quantity}, "
                    f"التكلفة: {item.product.cost_price}, الإجمالي: {item_cost}"
                )

            # تسجيل تحذير إذا كانت هناك منتجات بدون تكلفة
            if items_without_cost:
                logger.warning(
                    f"⚠️ الفاتورة {sale.number} تحتوي على منتجات بدون تكلفة محددة: "
                    f"{', '.join(items_without_cost)}"
                )
            
            # تسجيل إجمالي التكلفة
            logger.info(f"إجمالي تكلفة البضاعة المباعة للفاتورة {sale.number}: {total_cost}")

            return total_cost
        except Exception as e:
            logger.error(f"خطأ في حساب تكلفة البضاعة: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
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

    @classmethod
    def _get_supplier_account(cls, supplier) -> Optional[ChartOfAccounts]:
        """الحصول على حساب المورد المحدد أو إنشاؤه"""
        try:
            # أولاً: محاولة استخدام الحساب المالي المحدد للمورد
            if supplier.financial_account and supplier.financial_account.is_active:
                logger.info(f"✅ استخدام حساب المورد المحدد: {supplier.financial_account.code} - {supplier.financial_account.name}")
                return supplier.financial_account
            
            # ثانياً: البحث عن حساب فرعي للمورد في شجرة الحسابات
            supplier_sub_accounts = ChartOfAccounts.objects.filter(
                name__icontains=supplier.name,
                is_active=True,
                is_leaf=True,  # حساب نهائي
                parent__code__startswith="201"  # تحت مجموعة الموردين
            )
            
            if supplier_sub_accounts.exists():
                account = supplier_sub_accounts.first()
                logger.info(f"✅ وُجد حساب فرعي للمورد: {account.code} - {account.name}")
                return account
            
            # ثالثاً: محاولة إنشاء حساب جديد للمورد
            try:
                # البحث عن الحساب الأب للموردين
                parent_account = ChartOfAccounts.objects.get(code="2010", is_active=True)
                
                # إنشاء رقم حساب جديد للمورد
                last_supplier_account = ChartOfAccounts.objects.filter(
                    code__startswith="20101"
                ).order_by("-code").first()
                
                if last_supplier_account:
                    try:
                        last_number = int(last_supplier_account.code[5:])  # آخر 3 أرقام
                        new_number = last_number + 1
                    except (ValueError, IndexError):
                        new_number = 1
                else:
                    new_number = 1
                
                new_code = f"20101{new_number:03d}"  # مثال: 20101001
                
                # إنشاء الحساب الجديد
                new_account = ChartOfAccounts.objects.create(
                    code=new_code,
                    name=f"المورد - {supplier.name}",
                    parent=parent_account,
                    account_type="liability",
                    is_active=True,
                    is_leaf=True,
                    created_by_id=1  # استخدام المستخدم الافتراضي
                )
                
                # ربط الحساب الجديد بالمورد
                supplier.financial_account = new_account
                supplier.save(update_fields=['financial_account'])
                
                logger.info(f"✅ تم إنشاء حساب جديد للمورد: {new_account.code} - {new_account.name}")
                return new_account
                
            except Exception as e:
                logger.warning(f"⚠️ فشل في إنشاء حساب جديد للمورد: {e}")
            
            # رابعاً: إرجاع None للاستخدام الحساب العام
            logger.warning(f"⚠️ لم يتم العثور على حساب محدد للمورد {supplier.name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على حساب المورد: {e}")
            return None

    @classmethod
    def _get_customer_account(cls, customer) -> Optional[ChartOfAccounts]:
        """الحصول على حساب العميل المحدد أو إنشاؤه"""
        try:
            # أولاً: محاولة استخدام الحساب المالي المحدد للعميل
            if customer.financial_account and customer.financial_account.is_active:
                logger.info(f"✅ استخدام حساب العميل المحدد: {customer.financial_account.code} - {customer.financial_account.name}")
                return customer.financial_account
            
            # ثانياً: البحث عن حساب فرعي للعميل في شجرة الحسابات
            customer_sub_accounts = ChartOfAccounts.objects.filter(
                name__icontains=customer.name,
                is_active=True,
                is_leaf=True,  # حساب نهائي
                parent__code__startswith="110"  # تحت مجموعة العملاء
            )
            
            if customer_sub_accounts.exists():
                account = customer_sub_accounts.first()
                logger.info(f"✅ وُجد حساب فرعي للعميل: {account.code} - {account.name}")
                return account
            
            # ثالثاً: محاولة إنشاء حساب جديد للعميل
            try:
                # البحث عن الحساب الأب للعملاء
                parent_account = ChartOfAccounts.objects.get(code="1103", is_active=True)
                
                # إنشاء رقم حساب جديد للعميل
                last_customer_account = ChartOfAccounts.objects.filter(
                    code__startswith="11030"
                ).order_by("-code").first()
                
                if last_customer_account:
                    try:
                        last_number = int(last_customer_account.code[5:])  # آخر 3 أرقام
                        new_number = last_number + 1
                    except (ValueError, IndexError):
                        new_number = 1
                else:
                    new_number = 1
                
                new_code = f"11030{new_number:03d}"  # مثال: 11030001
                
                # إنشاء الحساب الجديد
                new_account = ChartOfAccounts.objects.create(
                    code=new_code,
                    name=f"العميل - {customer.name}",
                    parent=parent_account,
                    account_type="asset",
                    is_active=True,
                    is_leaf=True,
                    created_by_id=1  # استخدام المستخدم الافتراضي
                )
                
                # ربط الحساب الجديد بالعميل
                customer.financial_account = new_account
                customer.save(update_fields=['financial_account'])
                
                logger.info(f"✅ تم إنشاء حساب جديد للعميل: {new_account.code} - {new_account.name}")
                return new_account
                
            except Exception as e:
                logger.warning(f"⚠️ فشل في إنشاء حساب جديد للعميل: {e}")
            
            # رابعاً: إرجاع None للاستخدام الحساب العام
            logger.warning(f"⚠️ لم يتم العثور على حساب محدد للعميل {customer.name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على حساب العميل: {e}")
            return None

    @classmethod
    def create_sale_adjustment_entry(
        cls,
        sale,
        old_total: Decimal,
        old_cost: Decimal,
        user: Optional[User] = None,
        reason: str = ""
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد تصحيحي لتعديل فاتورة مبيعات مرحّلة
        
        يتم إنشاء قيد تصحيحي يُسجل الفرق بين القيم القديمة والجديدة
        مع الحفاظ على القيد الأصلي للأثر التدقيقي
        
        يتضمن:
        - التحقق من إغلاق الفترة المحاسبية
        - إنشاء سجل تدقيق مفصل
        - ربط القيد التصحيحي بالفاتورة
        """
        try:
            with transaction.atomic():
                # حساب الفروقات
                new_total = sale.total
                new_cost = cls._calculate_sale_cost(sale)
                
                total_difference = new_total - old_total
                cost_difference = new_cost - old_cost
                
                # إذا لم يكن هناك فرق، لا حاجة لقيد تصحيحي
                if total_difference == 0 and cost_difference == 0:
                    logger.info(f"لا توجد فروقات تتطلب قيد تصحيحي للفاتورة {sale.number}")
                    return None
                
                # التحقق من إغلاق الفترة المحاسبية
                current_date = timezone.now().date()
                accounting_period = cls._get_accounting_period(current_date)
                
                if accounting_period and accounting_period.status == 'closed':
                    error_msg = f"لا يمكن إنشاء قيد تصحيحي - الفترة المحاسبية {accounting_period.name} مغلقة"
                    logger.error(error_msg)
                    raise ValidationError(error_msg)
                
                # الحصول على الحسابات المطلوبة
                accounts = cls._get_required_accounts_for_sale()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة")
                    return None
                
                # إنشاء القيد التصحيحي
                adjustment_entry = JournalEntry.objects.create(
                    number=cls._generate_journal_number("ADJ-SALE", sale.number),
                    date=current_date,
                    entry_type="adjustment",
                    status="posted",
                    reference=f"تصحيح فاتورة مبيعات {sale.number}",
                    description=f"تصحيح بسبب تعديل الفاتورة - الفرق: {total_difference} ج.م",
                    created_by=user,
                    accounting_period=accounting_period,
                )
                
                # معالجة فرق الإجمالي (الإيرادات والعملاء)
                if total_difference != 0:
                    customer_account = cls._get_customer_account(sale.customer)
                    if not customer_account:
                        customer_account = accounts["accounts_receivable"]
                    
                    if total_difference > 0:  # زيادة في الفاتورة
                        # مدين العميل (زيادة الذمة)
                        JournalEntryLine.objects.create(
                            journal_entry=adjustment_entry,
                            account=customer_account,
                            debit=total_difference,
                            credit=Decimal("0.00"),
                            description=f"زيادة ذمة العميل {sale.customer.name} - تصحيح فاتورة {sale.number}",
                        )
                        # دائن الإيرادات (زيادة الإيرادات)
                        JournalEntryLine.objects.create(
                            journal_entry=adjustment_entry,
                            account=accounts["sales_revenue"],
                            debit=Decimal("0.00"),
                            credit=total_difference,
                            description=f"زيادة إيرادات - تصحيح فاتورة {sale.number}",
                        )
                    else:  # نقص في الفاتورة
                        abs_diff = abs(total_difference)
                        # دائن العميل (تخفيض الذمة)
                        JournalEntryLine.objects.create(
                            journal_entry=adjustment_entry,
                            account=customer_account,
                            debit=Decimal("0.00"),
                            credit=abs_diff,
                            description=f"تخفيض ذمة العميل {sale.customer.name} - تصحيح فاتورة {sale.number}",
                        )
                        # مدين الإيرادات (تخفيض الإيرادات)
                        JournalEntryLine.objects.create(
                            journal_entry=adjustment_entry,
                            account=accounts["sales_revenue"],
                            debit=abs_diff,
                            credit=Decimal("0.00"),
                            description=f"تخفيض إيرادات - تصحيح فاتورة {sale.number}",
                        )
                
                # معالجة فرق التكلفة (تكلفة البضاعة والمخزون)
                if cost_difference != 0:
                    if cost_difference > 0:  # زيادة في التكلفة
                        # مدين تكلفة البضاعة المباعة
                        JournalEntryLine.objects.create(
                            journal_entry=adjustment_entry,
                            account=accounts["cost_of_goods_sold"],
                            debit=cost_difference,
                            credit=Decimal("0.00"),
                            description=f"زيادة تكلفة البضاعة - تصحيح فاتورة {sale.number}",
                        )
                        # دائن المخزون
                        JournalEntryLine.objects.create(
                            journal_entry=adjustment_entry,
                            account=accounts["inventory"],
                            debit=Decimal("0.00"),
                            credit=cost_difference,
                            description=f"تخفيض المخزون - تصحيح فاتورة {sale.number}",
                        )
                    else:  # نقص في التكلفة
                        abs_cost_diff = abs(cost_difference)
                        # دائن تكلفة البضاعة المباعة
                        JournalEntryLine.objects.create(
                            journal_entry=adjustment_entry,
                            account=accounts["cost_of_goods_sold"],
                            debit=Decimal("0.00"),
                            credit=abs_cost_diff,
                            description=f"تخفيض تكلفة البضاعة - تصحيح فاتورة {sale.number}",
                        )
                        # مدين المخزون
                        JournalEntryLine.objects.create(
                            journal_entry=adjustment_entry,
                            account=accounts["inventory"],
                            debit=abs_cost_diff,
                            credit=Decimal("0.00"),
                            description=f"زيادة المخزون - تصحيح فاتورة {sale.number}",
                        )
                
                # إنشاء سجل تدقيق مفصل
                from financial.models import InvoiceAuditLog
                
                audit_log = InvoiceAuditLog.objects.create(
                    invoice_type="sale",
                    invoice_id=sale.id,
                    invoice_number=sale.number,
                    action_type="adjustment",
                    old_total=old_total,
                    old_cost=old_cost,
                    new_total=new_total,
                    new_cost=new_cost,
                    total_difference=total_difference,
                    cost_difference=cost_difference,
                    adjustment_entry=adjustment_entry,
                    reason=reason,
                    notes=f"تم إنشاء قيد تصحيحي {adjustment_entry.number}",
                    created_by=user,
                )
                
                logger.info(
                    f"✅ تم إنشاء قيد تصحيحي للمبيعات: {adjustment_entry.number} - "
                    f"فاتورة {sale.number} (فرق الإجمالي: {total_difference}, فرق التكلفة: {cost_difference}) - "
                    f"سجل تدقيق: {audit_log.id}"
                )
                return adjustment_entry
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء قيد تصحيحي للمبيعات: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def create_purchase_adjustment_entry(
        cls,
        purchase,
        old_total: Decimal,
        user: Optional[User] = None,
        reason: str = ""
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد تصحيحي لتعديل فاتورة مشتريات مرحّلة
        
        يتم إنشاء قيد تصحيحي يُسجل الفرق بين القيم القديمة والجديدة
        
        يتضمن:
        - التحقق من إغلاق الفترة المحاسبية
        - إنشاء سجل تدقيق مفصل
        - ربط القيد التصحيحي بالفاتورة
        """
        try:
            with transaction.atomic():
                # حساب الفرق
                new_total = purchase.total
                total_difference = new_total - old_total
                
                # إذا لم يكن هناك فرق، لا حاجة لقيد تصحيحي
                if total_difference == 0:
                    logger.info(f"لا توجد فروقات تتطلب قيد تصحيحي للفاتورة {purchase.number}")
                    return None
                
                # التحقق من إغلاق الفترة المحاسبية
                current_date = timezone.now().date()
                accounting_period = cls._get_accounting_period(current_date)
                
                if accounting_period and accounting_period.status == 'closed':
                    error_msg = f"لا يمكن إنشاء قيد تصحيحي - الفترة المحاسبية {accounting_period.name} مغلقة"
                    logger.error(error_msg)
                    raise ValidationError(error_msg)
                
                # الحصول على الحسابات المطلوبة
                accounts = cls._get_required_accounts_for_purchase()
                if not accounts:
                    logger.error("لا يمكن العثور على الحسابات المحاسبية المطلوبة")
                    return None
                
                # إنشاء القيد التصحيحي
                adjustment_entry = JournalEntry.objects.create(
                    number=cls._generate_journal_number("ADJ-PURCHASE", purchase.number),
                    date=current_date,
                    entry_type="adjustment",
                    status="posted",
                    reference=f"تصحيح فاتورة مشتريات {purchase.number}",
                    description=f"تصحيح بسبب تعديل الفاتورة - الفرق: {total_difference} ج.م",
                    created_by=user,
                    accounting_period=accounting_period,
                )
                
                # معالجة الفرق
                supplier_account = cls._get_supplier_account(purchase.supplier)
                if not supplier_account:
                    supplier_account = accounts["accounts_payable"]
                
                if total_difference > 0:  # زيادة في الفاتورة
                    # مدين المخزون (زيادة المخزون)
                    JournalEntryLine.objects.create(
                        journal_entry=adjustment_entry,
                        account=accounts["inventory"],
                        debit=total_difference,
                        credit=Decimal("0.00"),
                        description=f"زيادة مخزون - تصحيح فاتورة {purchase.number}",
                    )
                    # دائن المورد (زيادة المديونية)
                    JournalEntryLine.objects.create(
                        journal_entry=adjustment_entry,
                        account=supplier_account,
                        debit=Decimal("0.00"),
                        credit=total_difference,
                        description=f"زيادة مديونية المورد {purchase.supplier.name} - تصحيح فاتورة {purchase.number}",
                    )
                else:  # نقص في الفاتورة
                    abs_diff = abs(total_difference)
                    # دائن المخزون (تخفيض المخزون)
                    JournalEntryLine.objects.create(
                        journal_entry=adjustment_entry,
                        account=accounts["inventory"],
                        debit=Decimal("0.00"),
                        credit=abs_diff,
                        description=f"تخفيض مخزون - تصحيح فاتورة {purchase.number}",
                    )
                    # مدين المورد (تخفيض المديونية)
                    JournalEntryLine.objects.create(
                        journal_entry=adjustment_entry,
                        account=supplier_account,
                        debit=abs_diff,
                        credit=Decimal("0.00"),
                        description=f"تخفيض مديونية المورد {purchase.supplier.name} - تصحيح فاتورة {purchase.number}",
                    )
                
                # إنشاء سجل تدقيق مفصل
                from financial.models import InvoiceAuditLog
                
                audit_log = InvoiceAuditLog.objects.create(
                    invoice_type="purchase",
                    invoice_id=purchase.id,
                    invoice_number=purchase.number,
                    action_type="adjustment",
                    old_total=old_total,
                    old_cost=None,  # المشتريات لا تحتاج تتبع التكلفة
                    new_total=new_total,
                    new_cost=None,
                    total_difference=total_difference,
                    cost_difference=None,
                    adjustment_entry=adjustment_entry,
                    reason=reason,
                    notes=f"تم إنشاء قيد تصحيحي {adjustment_entry.number}",
                    created_by=user,
                )
                
                logger.info(
                    f"✅ تم إنشاء قيد تصحيحي للمشتريات: {adjustment_entry.number} - "
                    f"فاتورة {purchase.number} (الفرق: {total_difference}) - "
                    f"سجل تدقيق: {audit_log.id}"
                )
                return adjustment_entry
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء قيد تصحيحي للمشتريات: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def get_invoice_audit_logs(cls, invoice_type: str, invoice_id: int):
        """
        الحصول على سجلات التدقيق لفاتورة معينة
        
        Args:
            invoice_type: نوع الفاتورة ('sale' أو 'purchase')
            invoice_id: رقم الفاتورة في قاعدة البيانات
            
        Returns:
            QuerySet من سجلات التدقيق
        """
        try:
            from financial.models import InvoiceAuditLog
            
            return InvoiceAuditLog.objects.filter(
                invoice_type=invoice_type,
                invoice_id=invoice_id
            ).select_related('adjustment_entry', 'created_by').order_by('-created_at')
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على سجلات التدقيق: {str(e)}")
            return None

    @classmethod
    def get_adjustment_entries_for_invoice(cls, invoice_type: str, invoice_number: str):
        """
        الحصول على جميع القيود التصحيحية لفاتورة معينة
        
        Args:
            invoice_type: نوع الفاتورة ('sale' أو 'purchase')
            invoice_number: رقم الفاتورة
            
        Returns:
            QuerySet من القيود التصحيحية
        """
        try:
            from financial.models import JournalEntry
            
            reference_pattern = f"تصحيح فاتورة {'مبيعات' if invoice_type == 'sale' else 'مشتريات'} {invoice_number}"
            
            return JournalEntry.objects.filter(
                entry_type='adjustment',
                reference=reference_pattern
            ).prefetch_related('lines').order_by('-date')
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على القيود التصحيحية: {str(e)}")
            return None
