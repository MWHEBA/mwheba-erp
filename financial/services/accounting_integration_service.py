"""
خدمة التكامل المحاسبي الشاملة
ربط المبيعات والمشتريات بالنظام المحاسبي الجديد
"""
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from datetime import date
import logging

from ..models.chart_of_accounts import ChartOfAccounts, AccountType
from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from ..services.account_helper import AccountHelperService

# Import AccountingGateway for unified journal entry creation
from governance.services import AccountingGateway, JournalEntryLineData

logger = logging.getLogger(__name__)
User = get_user_model()


class AccountingIntegrationService:
    """
    خدمة التكامل المحاسبي الشاملة
    """

    # أكواد الحسابات الأساسية المطلوبة (حسب دليل الحسابات المعتمد)
    DEFAULT_ACCOUNTS = {
        "sales_revenue": "40100",  # إيرادات الرسوم الأساسية
        "cost_of_goods_sold": "50100",  # تكلفة الخدمات المقدمة
        "inventory": "10400",  # المخزون
        "accounts_receivable": "10300",  # ذمم العملاء
        "accounts_payable": "20100",  # الموردون
        "cash": "10100",  # الخزنة
        "bank": "10200",  # البنك
        "purchase_expense": "50100",  # تكلفة الخدمات المقدمة
    }

    @classmethod
    def create_sale_journal_entry(
        cls, sale, user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيود محاسبية منفصلة لفاتورة مبيعات حسب تصنيف المنتجات
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

                # تجميع بنود الفاتورة حسب التصنيف
                items_by_category = cls._group_sale_items_by_category(sale)
                
                if not items_by_category:
                    logger.warning(f"لا توجد بنود في الفاتورة {sale.number}")
                    return None

                # الحصول على معلومات العميل/ولي الأمر
                client_account, client_name = cls._get_client_info(sale, user)
                if not client_account:
                    return None

                created_entries = []
                
                # إنشاء قيد منفصل لكل تصنيف
                for category_name, category_items in items_by_category.items():
                    category_total = sum(item.total for item in category_items)
                    category_cost = sum(cls._get_item_cost(item) for item in category_items)
                    
                    # Prepare journal entry lines
                    lines = [
                        JournalEntryLineData(
                            account_code=client_account.code,
                            debit=category_total,
                            credit=Decimal("0.00"),
                            description=f"مبيعات {category_name} - {client_name} - فاتورة {sale.number}"
                        )
                    ]
                    
                    # قيد الإيرادات (دائن)
                    revenue_account = cls._get_category_revenue_account(category_name) or accounts["sales_revenue"]
                    lines.append(
                        JournalEntryLineData(
                            account_code=revenue_account.code,
                            debit=Decimal("0.00"),
                            credit=category_total,
                            description=f"إيرادات {category_name} - فاتورة {sale.number}"
                        )
                    )
                    
                    # قيد تكلفة البضاعة المباعة (إذا كانت متاحة)
                    if category_cost > 0:
                        lines.append(
                            JournalEntryLineData(
                                account_code=accounts["cost_of_goods_sold"].code,
                                debit=category_cost,
                                credit=Decimal("0.00"),
                                description=f"تكلفة {category_name} المباعة - فاتورة {sale.number}"
                            )
                        )
                        lines.append(
                            JournalEntryLineData(
                                account_code=accounts["inventory"].code,
                                debit=Decimal("0.00"),
                                credit=category_cost,
                                description=f"تخفيض مخزون {category_name} - فاتورة {sale.number}"
                            )
                        )
                    
                    # Create journal entry via AccountingGateway
                    gateway = AccountingGateway()
                    journal_entry = gateway.create_journal_entry(
                        source_module='sales',
                        source_model='Sale',
                        source_id=sale.id,
                        lines=lines,
                        idempotency_key=f"JE:sales:Sale:{sale.id}:{category_name[:3].upper()}:create",
                        user=user or sale.created_by,
                        entry_type='automatic',
                        description=f"مبيعات {category_name} لـ {client_name}",
                        reference=f"فاتورة مبيعات رقم {sale.number} - {category_name}",
                        date=sale.date
                    )

                    created_entries.append(journal_entry)

                # ربط أول قيد بالفاتورة (للمرجعية)
                if created_entries:
                    sale.journal_entry = created_entries[0]
                    sale.save(update_fields=["journal_entry"])

                return created_entries[0] if created_entries else None

        except Exception as e:
            logger.error(f"خطأ في إنشاء قيود المبيعات: {str(e)}")
            return None

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

                # بناء وصف تفصيلي يتضمن المنتجات/الخدمات
                purchase_items = purchase.items.all()
                if purchase_items.exists():
                    # جمع أسماء المنتجات/الخدمات (أول 3 عناصر)
                    items_list = []
                    for item in purchase_items[:3]:
                        items_list.append(f"{item.product.name}")
                    
                    items_text = "، ".join(items_list)
                    if purchase_items.count() > 3:
                        items_text += f" وعناصر أخرى ({purchase_items.count() - 3})"
                    
                    description = f"مشتريات من \"{purchase.supplier.name}\" - {items_text}"
                else:
                    description = f"مشتريات من المورد {purchase.supplier.name}"
                
                # Prepare journal entry lines
                lines = []
                
                # قيد المخزون أو المصروفات (مدين)
                if purchase.is_service:
                    # للخدمات: استخدام حساب المصروفات من التصنيف المالي
                    if not purchase.financial_category:
                        logger.error(f"فاتورة الخدمات {purchase.number} ليس لها تصنيف مالي")
                        return None
                    
                    expense_account = purchase.financial_category.default_expense_account
                    if not expense_account:
                        logger.error(
                            f"التصنيف المالي {purchase.financial_category.name} "
                            f"ليس له حساب مصروفات افتراضي"
                        )
                        return None
                    
                    lines.append(
                        JournalEntryLineData(
                            account_code=expense_account.code,
                            debit=purchase.total,
                            credit=Decimal("0.00"),
                            description=f"مصروفات {purchase.service_type_display} - فاتورة {purchase.number}"
                        )
                    )
                else:
                    # للمنتجات: استخدام حساب المصروفات من التصنيف المالي (إذا كان موجود)
                    # أو حساب المخزون الافتراضي
                    if purchase.financial_category and purchase.financial_category.default_expense_account:
                        # استخدام حساب المصروفات من التصنيف
                        lines.append(
                            JournalEntryLineData(
                                account_code=purchase.financial_category.default_expense_account.code,
                                debit=purchase.total,
                                credit=Decimal("0.00"),
                                description=f"مشتريات - {purchase.financial_category.name} - فاتورة {purchase.number}"
                            )
                        )
                    else:
                        # Fallback: استخدام حساب المخزون الافتراضي
                        lines.append(
                            JournalEntryLineData(
                                account_code=accounts["inventory"].code,
                                debit=purchase.total,
                                credit=Decimal("0.00"),
                                description=f"مشتريات مخزون - فاتورة {purchase.number}"
                            )
                        )

                # قيد المورد (دائن)
                supplier_account = cls._get_supplier_account(purchase.supplier)
                if not supplier_account:
                    logger.warning(f"⚠️ المورد {purchase.supplier.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                    supplier_account = cls._create_supplier_account(purchase.supplier, user or purchase.created_by)
                    
                    if not supplier_account:
                        error_msg = f"❌ فشل إنشاء حساب محاسبي للمورد {purchase.supplier.name}. يجب إنشاء حساب محاسبي للمورد أولاً."
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                
                # بناء وصف تفصيلي لبند القيد
                if purchase_items.exists():
                    items_list = []
                    for item in purchase_items[:3]:
                        items_list.append(f"{item.product.name}")
                    
                    items_text = "، ".join(items_list)
                    if purchase_items.count() > 3:
                        items_text += f" وعناصر أخرى ({purchase_items.count() - 3})"
                    
                    line_description = f"مشتريات من \"{purchase.supplier.name}\" - {items_text}"
                else:
                    line_description = f"مشتريات - المورد {purchase.supplier.name} - فاتورة {purchase.number}"
                
                lines.append(
                    JournalEntryLineData(
                        account_code=supplier_account.code,
                        debit=Decimal("0.00"),
                        credit=purchase.total,
                        description=line_description
                    )
                )
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='purchase',
                    source_model='Purchase',
                    source_id=purchase.id,
                    lines=lines,
                    idempotency_key=f"JE:purchase:Purchase:{purchase.id}:create",
                    user=user or purchase.created_by,
                    entry_type='automatic',
                    description=description,
                    reference=f"فاتورة مشتريات رقم {purchase.number}",
                    date=purchase.date
                )

                # ربط القيد بالفاتورة
                purchase.journal_entry = journal_entry
                purchase.save(update_fields=["journal_entry"])

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

                # Prepare journal entry lines
                lines = []
                
                # قيد عكس الإيراد (مدين إيرادات)
                lines.append(
                    JournalEntryLineData(
                        account_code=accounts["sales_revenue"].code,
                        debit=total_return,
                        credit=Decimal("0.00"),
                        description=f"عكس إيرادات - مرتجع {sale_return.number}"
                    )
                )

                # استخدام حساب العميل المحدد
                client_account = None
                client_name = sale_return.sale.client_name
                
                if sale_return.sale.customer:
                    client_account = cls._get_customer_account(sale_return.sale.customer)
                    if not client_account:
                        logger.warning(f"⚠️ العميل {sale_return.sale.customer.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                        client_account = cls._create_customer_account(sale_return.sale.customer, user or sale_return.created_by)
                        if not client_account:
                            error_msg = f"❌ فشل إنشاء حساب محاسبي للعميل {sale_return.sale.customer.name}. يجب إنشاء حساب محاسبي للعميل أولاً."
                            logger.error(error_msg)
                            raise ValueError(error_msg)
                else:
                    error_msg = "❌ الفاتورة لا تحتوي على عميل"
                    logger.error(error_msg)
                    raise ValueError(error_msg)

                lines.append(
                    JournalEntryLineData(
                        account_code=client_account.code,
                        debit=Decimal("0.00"),
                        credit=total_return,
                        description=f"تخفيض ذمم {client_name} - مرتجع {sale_return.number}"
                    )
                )

                # قيد إرجاع المخزون (مدين مخزون، دائن تكلفة)
                if total_cost > 0:
                    lines.append(
                        JournalEntryLineData(
                            account_code=accounts["inventory"].code,
                            debit=total_cost,
                            credit=Decimal("0.00"),
                            description=f"إرجاع مخزون - مرتجع {sale_return.number}"
                        )
                    )
                    lines.append(
                        JournalEntryLineData(
                            account_code=accounts["cost_of_goods_sold"].code,
                            debit=Decimal("0.00"),
                            credit=total_cost,
                            description=f"عكس تكلفة البضاعة - مرتجع {sale_return.number}"
                        )
                    )
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='sales',
                    source_model='SaleReturn',
                    source_id=sale_return.id,
                    lines=lines,
                    idempotency_key=f"JE:sales:SaleReturn:{sale_return.id}:create",
                    user=user or sale_return.created_by,
                    entry_type='automatic',
                    description=f"مرتجع من {sale_return.sale.client_name}",
                    reference=f"مرتجع مبيعات رقم {sale_return.number} - فاتورة {sale_return.sale.number}",
                    date=sale_return.date
                )

                # ربط القيد بالمرتجع
                sale_return.journal_entry = journal_entry
                sale_return.save(update_fields=["journal_entry"])

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
                    # دفعة من عميل/ولي أمر
                    client_name = payment.sale.client_name
                    reference = f"دفعة من العميل - فاتورة {payment.sale.number}"
                    description = f"استلام دفعة من {client_name}"

                    # النظام الجديد: payment_method هو account code مباشرة
                    payment_method = payment.payment_method
                    try:
                        from financial.models import ChartOfAccounts
                        account_debit = ChartOfAccounts.objects.filter(
                            code=payment_method,
                            is_active=True
                        ).first()
                        
                        if not account_debit:
                            raise ValueError(f"الحساب المحاسبي {payment_method} غير موجود أو غير نشط")
                            
                    except Exception as e:
                        logger.error(f"فشل في الحصول على حساب الدفع {payment_method}: {str(e)}")
                        raise
                    
                    # دائن حساب العميل المحدد
                    client_account = None
                    
                    if payment.sale.customer:
                        client_account = cls._get_customer_account(payment.sale.customer)
                        
                        if not client_account:
                            logger.warning(f"⚠️ العميل {payment.sale.customer.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                            client_account = cls._create_customer_account(payment.sale.customer, user or payment.created_by)
                            
                            if not client_account:
                                error_msg = f"❌ فشل إنشاء حساب محاسبي للعميل {payment.sale.customer.name}. يجب إنشاء حساب محاسبي للعميل أولاً."
                                logger.error(error_msg)
                                raise ValueError(error_msg)
                    else:
                        error_msg = "❌ الفاتورة لا تحتوي على عميل"
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                    
                    account_credit = client_account

                elif payment_type == "fee_payment":
                    # دفعة رسوم خدمات
                    reference = f"دفعة رسوم - {payment.reference or ''}"
                    description = f"استلام دفعة رسوم"

                    payment_method = payment.payment_method
                    try:
                        from financial.models import ChartOfAccounts
                        account_debit = ChartOfAccounts.objects.filter(
                            code=payment_method,
                            is_active=True
                        ).first()
                        
                        if not account_debit:
                            raise ValueError(f"الحساب المحاسبي {payment_method} غير موجود أو غير نشط")
                            
                    except Exception as e:
                        logger.error(f"فشل في الحصول على حساب الدفع {payment_method}: {str(e)}")
                        raise
                    
                    account_credit = None

                elif payment_type == "purchase_payment":
                    # دفعة لمورد
                    # المرجع يبقى بسيط مع رقم الفاتورة
                    reference = f"دفعة للمورد - فاتورة {payment.purchase.number}"
                    
                    # الوصف يكون تفصيلي مع المنتجات/الخدمات
                    purchase_items = payment.purchase.items.all()
                    if purchase_items.exists():
                        # جمع أسماء المنتجات/الخدمات (أول 3 عناصر)
                        items_list = []
                        for item in purchase_items[:3]:
                            items_list.append(f"{item.product.name}")
                        
                        items_text = "، ".join(items_list)
                        if purchase_items.count() > 3:
                            items_text += f" وعناصر أخرى ({purchase_items.count() - 3})"
                        
                        description = f"دفع لـ \"{payment.purchase.supplier.name}\" مقابل {items_text}"
                    else:
                        description = f"دفع للمورد {payment.purchase.supplier.name}"

                    # مدين حساب المورد المحدد
                    supplier_account = cls._get_supplier_account(payment.purchase.supplier)
                    if not supplier_account:
                        # إنشاء حساب جديد للمورد تلقائياً
                        logger.warning(f"⚠️ المورد {payment.purchase.supplier.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                        supplier_account = cls._create_supplier_account(payment.purchase.supplier, user or payment.created_by)
                        
                        if not supplier_account:
                            # فشل إنشاء الحساب - إيقاف العملية
                            error_msg = f"❌ فشل إنشاء حساب محاسبي للمورد {payment.purchase.supplier.name}. يجب إنشاء حساب محاسبي للمورد أولاً."
                            logger.error(error_msg)
                            raise ValueError(error_msg)
                    
                    account_debit = supplier_account
                    
                    # النظام الجديد: payment_method هو account code مباشرة
                    payment_method = payment.payment_method
                    try:
                        from financial.models import ChartOfAccounts
                        account_credit = ChartOfAccounts.objects.filter(
                            code=payment_method,
                            is_active=True
                        ).first()
                        
                        if not account_credit:
                            raise ValueError(f"الحساب المحاسبي {payment_method} غير موجود أو غير نشط")
                            
                    except Exception as e:
                        logger.error(f"فشل في الحصول على حساب الدفع {payment_method}: {str(e)}")
                        raise

                else:
                    logger.error(f"نوع دفعة غير معروف: {payment_type}")
                    return None

                # تحديد نوع القيد الصحيح
                entry_type = "automatic"  # افتراضي
                financial_category = None
                financial_subcategory = None
                
                if payment_type == "sale_payment":
                    # دفعة من عميل
                    entry_type = "client_payment"
                    client_name = payment.sale.client_name
                    reference = f"دفعة من العميل - فاتورة {payment.sale.number}"
                    description = f"استلام دفعة من {client_name}"

                elif payment_type == "fee_payment":
                    # دفعة رسوم خدمات
                    entry_type = "service_payment"
                    reference = f"دفعة رسوم - {payment.reference or ''}"
                    description = f"استلام دفعة رسوم"

                elif payment_type == "purchase_payment":
                    # دفعة لمورد
                    entry_type = "supplier_payment"
                    
                    # المرجع يبقى بسيط مع رقم الفاتورة
                    reference = f"دفعة للمورد - فاتورة {payment.purchase.number}"
                    
                    # الوصف يكون تفصيلي مع المنتجات/الخدمات
                    purchase_items = payment.purchase.items.all()
                    if purchase_items.exists():
                        # جمع أسماء المنتجات/الخدمات (أول 3 عناصر)
                        items_list = []
                        for item in purchase_items[:3]:
                            items_list.append(f"{item.product.name}")
                        
                        items_text = "، ".join(items_list)
                        if purchase_items.count() > 3:
                            items_text += f" وعناصر أخرى ({purchase_items.count() - 3})"
                        
                        description = f"دفع لـ \"{payment.purchase.supplier.name}\" مقابل {items_text}"
                    else:
                        description = f"دفع للمورد {payment.purchase.supplier.name}"

                # Prepare journal entry lines
                lines = [
                    JournalEntryLineData(
                        account_code=account_debit.code,
                        debit=payment.amount,
                        credit=Decimal("0.00"),
                        description=description
                    ),
                    JournalEntryLineData(
                        account_code=account_credit.code,
                        debit=Decimal("0.00"),
                        credit=payment.amount,
                        description=description
                    )
                ]
                
                # Determine correct source module and model based on payment type
                if payment_type == "purchase_payment":
                    source_module = 'purchase'
                    source_model = 'PurchasePayment'
                elif payment_type == "customer_payment":
                    source_module = 'client'
                    source_model = 'CustomerPayment'
                elif payment_type == "sale_payment":
                    source_module = 'sale'
                    source_model = 'SalePayment'
                else:
                    # Fallback to generic payments
                    source_module = 'payments'
                    source_model = 'Payment'
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module=source_module,
                    source_model=source_model,
                    source_id=payment.id,
                    lines=lines,
                    idempotency_key=f"JE:{source_module}:{source_model}:{payment.id}:create",
                    user=user or payment.created_by,
                    entry_type=entry_type,
                    description=description,
                    reference=reference,
                    date=payment.payment_date,  # use actual payment date, not today
                    financial_category=financial_category,
                    financial_subcategory=financial_subcategory
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

            return total_cost
        except Exception as e:
            logger.error(f"خطأ في حساب تكلفة البضاعة: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return Decimal("0.00")

    @classmethod
    def _generate_journal_number(cls, prefix: str, reference: Any) -> str:
        """توليد رقم القيد مع دعم التسميات العربية الموحدة"""
        # قاموس البادئات الإنجليزية (أرقام القيود يجب أن تكون بالإنجليزية فقط)
        prefix_mapping = {
            # البادئات العربية القديمة → البادئات الإنجليزية الجديدة
            "رسوم": "FEE",               # Fee (البادئة العامة للرسوم)
            "رسوم-طالب": "TF",           # Tuition Fee (legacy - kept for DB compatibility)
            "دفع-رسوم": "PP",             # Parent Payment
            "استرداد-رسوم": "RF",         # Refund
            "عكس-رسوم": "RV",             # Reversal
            "تعديل-رسوم": "ADJ",          # Adjustment
            "رسوم-تقديم": "APP",          # Application Fee
            "تسليم-منتجات": "PD",         # Product Delivery
            "رسوم-مكملة": "CF",           # Complementary Fee
            "رسوم-تسليم": "DF",           # Delivery Fee
            # البادئات الإنجليزية (تبقى كما هي)
            "SALE": "SALE",
            "PURCHASE": "PURCH", 
            "RETURN": "RET",
            "PAYMENT": "PAY",
            "ADJ-SALE": "ADJ-SALE",
            "ADJ-PURCHASE": "ADJ-PURCH",
            "REV": "REV",
            "JE": "JE"
        }
        
        # استخدام البادئة المترجمة إذا كانت متوفرة
        normalized_prefix = prefix_mapping.get(prefix, prefix)
        
        # البحث عن أعلى رقم للبادئة المحددة
        existing_entries = JournalEntry.objects.filter(
            number__startswith=f"{normalized_prefix}-"
        ).order_by('-id')
        
        max_number = 0
        for entry in existing_entries:
            try:
                # استخراج الرقم من نهاية اسم القيد
                parts = entry.number.split("-")
                if len(parts) >= 2:
                    # أخذ آخر جزء كرقم
                    number_part = parts[-1]
                    # التحقق من أن الجزء الأخير رقم
                    if number_part.isdigit():
                        current_number = int(number_part)
                        if current_number > max_number:
                            max_number = current_number
            except (ValueError, IndexError):
                continue
        
        new_number = max_number + 1
        return f"{normalized_prefix}-{new_number:04d}"

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
                liability_type, _ = AccountType.objects.get_or_create(
                    category="liability",
                    defaults={
                        'code': 'LIABILITY',
                        'name': 'خصوم',
                        'nature': 'credit',
                        'is_active': True
                    }
                )
                new_account = ChartOfAccounts.objects.create(
                    code=new_code,
                    name=f"المورد - {supplier.name}",
                    parent=parent_account,
                    account_type=liability_type,
                    is_active=True,
                    is_leaf=True,
                    created_by_id=1  # استخدام المستخدم الافتراضي
                )
                
                # ربط الحساب الجديد بالمورد
                supplier.financial_account = new_account
                supplier.save(update_fields=['financial_account'])
                
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
                return account
            
            # ثالثاً: محاولة إنشاء حساب جديد للعميل
            try:
                # البحث عن الحساب الأب للعملاء
                parent_account = ChartOfAccounts.objects.get(code="1103", is_active=True)
                
                # إنشاء رقم حساب جديد للعميل
                last_customer_account = ChartOfAccounts.objects.filter(
                    code__startswith="10300"
                ).order_by("-code").first()
                
                if last_customer_account:
                    try:
                        last_number = int(last_customer_account.code[5:])  # آخر 3 أرقام
                        new_number = last_number + 1
                    except (ValueError, IndexError):
                        new_number = 1
                else:
                    new_number = 1
                
                new_code = f"10300{new_number:03d}"  # مثال: 10300001
                
                # إنشاء الحساب الجديد
                asset_type, _ = AccountType.objects.get_or_create(
                    category="asset",
                    defaults={
                        'code': 'ASSET',
                        'name': 'أصول',
                        'nature': 'debit',
                        'is_active': True
                    }
                )
                new_account = ChartOfAccounts.objects.create(
                    code=new_code,
                    name=f"العميل - {customer.name}",
                    parent=parent_account,
                    account_type=asset_type,
                    is_active=True,
                    is_leaf=True,
                    created_by_id=1  # استخدام المستخدم الافتراضي
                )
                
                # ربط الحساب الجديد بالعميل
                customer.financial_account = new_account
                customer.save(update_fields=['financial_account'])
                
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
    def _create_customer_account(cls, customer, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """
        إنشاء حساب محاسبي جديد للعميل تلقائياً
        يستخدم نفس المنطق الموجود في client/views.py:customer_create_account
        """
        try:
            # التحقق من أن العميل لا يملك حساب بالفعل
            if customer.financial_account:
                logger.warning(f"⚠️ العميل {customer.name} مربوط بالفعل بحساب محاسبي {customer.financial_account.code}")
                return customer.financial_account
            
            # البحث عن حساب العملاء الرئيسي (10300)
            customers_account = ChartOfAccounts.objects.filter(code="10300").first()
            
            if not customers_account:
                logger.error("❌ لا يمكن العثور على حساب أولياء الأمور الرئيسي (10300) في النظام")
                return None
            
            # إنشاء كود فريد للحساب الجديد
            # البحث عن آخر حساب فرعي تحت حساب العملاء
            # النمط المتوقع: 1030001, 1030002, 1030003...
            last_customer_account = ChartOfAccounts.objects.filter(
                parent=customers_account,
                code__startswith='1030'
            ).exclude(code='10300').order_by('-code').first()
            
            if last_customer_account:
                last_number = int(last_customer_account.code[-4:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            new_code = f"1030{new_number:04d}"
            
            # إنشاء اسم مناسب للحساب
            account_name = f"عميل - {customer.name}"
            
            # إنشاء الحساب الجديد
            new_account = ChartOfAccounts.objects.create(
                code=new_code,
                name=account_name,
                parent=customers_account,
                account_type=customers_account.account_type,
                is_active=True,
                is_leaf=True,
                description=f"حساب محاسبي للعميل: {customer.name} (كود العميل: {customer.code})",
                created_by=user if user else None
            )
            
            # ربط العميل بالحساب الجديد
            customer.financial_account = new_account
            customer.save(update_fields=['financial_account'])
            
            return new_account
            
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء حساب جديد للعميل {customer.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def _create_supplier_account(cls, supplier, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """
        إنشاء حساب محاسبي جديد للمورد تلقائياً
        يستخدم نفس المنطق الموجود في supplier/views.py:supplier_create_account
        """
        try:
            # التحقق من أن المورد لا يملك حساب بالفعل
            if supplier.financial_account:
                logger.warning(f"⚠️ المورد {supplier.name} مربوط بالفعل بحساب محاسبي {supplier.financial_account.code}")
                return supplier.financial_account
            
            # البحث عن حساب الموردين الرئيسي (20100)
            suppliers_account = ChartOfAccounts.objects.filter(code="20100").first()
            
            if not suppliers_account:
                logger.error("❌ لا يمكن العثور على حساب الموردين الرئيسي (20100) في النظام")
                return None
            
            # إنشاء كود فريد للحساب الجديد
            # البحث عن آخر حساب فرعي تحت حساب الموردين
            # النمط المتوقع: 2010001, 2010002, 2010003...
            last_supplier_account = ChartOfAccounts.objects.filter(
                parent=suppliers_account,
                code__startswith='2010'
            ).exclude(code='20100').order_by('-code').first()
            
            if last_supplier_account:
                last_number = int(last_supplier_account.code[-4:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            new_code = f"2010{new_number:04d}"
            
            # إنشاء اسم مناسب للحساب
            account_name = f"مورد - {supplier.name}"
            
            # إنشاء الحساب الجديد
            new_account = ChartOfAccounts.objects.create(
                code=new_code,
                name=account_name,
                parent=suppliers_account,
                account_type=suppliers_account.account_type,
                is_active=True,
                is_leaf=True,
                description=f"حساب محاسبي للمورد: {supplier.name} (كود المورد: {supplier.code})",
                created_by=user if user else None
            )
            
            # ربط المورد بالحساب الجديد
            supplier.financial_account = new_account
            supplier.save(update_fields=['financial_account'])
            
            return new_account
            
        except Exception as e:
            logger.error(f"❌ فشل في إنشاء حساب جديد للمورد {supplier.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

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
                
                # Prepare journal entry lines
                lines = []
                
                # معالجة فرق الإجمالي (الإيرادات والعملاء/أولياء الأمور)
                if total_difference != 0:
                    client_account = None
                    client_name = sale.client_name
                    
                    if sale.parent:
                        client_account = cls._get_parent_account(sale.parent)
                        if not client_account:
                            logger.warning(f"⚠️ ولي الأمر {sale.parent.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                            client_account = cls._create_parent_account(sale.parent, user)
                            if not client_account:
                                error_msg = f"❌ فشل إنشاء حساب محاسبي لولي الأمر {sale.parent.name}. يجب إنشاء حساب محاسبي لولي الأمر أولاً."
                                logger.error(error_msg)
                                raise ValueError(error_msg)
                    elif sale.customer:
                        client_account = cls._get_customer_account(sale.customer)
                        if not client_account:
                            logger.warning(f"⚠️ العميل {sale.customer.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                            client_account = cls._create_customer_account(sale.customer, user)
                            if not client_account:
                                error_msg = f"❌ فشل إنشاء حساب محاسبي للعميل {sale.customer.name}. يجب إنشاء حساب محاسبي للعميل أولاً."
                                logger.error(error_msg)
                                raise ValueError(error_msg)
                    else:
                        error_msg = "❌ الفاتورة لا تحتوي على ولي أمر أو عميل"
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                    
                    if total_difference > 0:  # زيادة في الفاتورة
                        lines.append(JournalEntryLineData(
                            account_code=client_account.code,
                            debit=total_difference,
                            credit=Decimal("0.00"),
                            description=f"زيادة ذمة {client_name} - تصحيح فاتورة {sale.number}"
                        ))
                        lines.append(JournalEntryLineData(
                            account_code=accounts["sales_revenue"].code,
                            debit=Decimal("0.00"),
                            credit=total_difference,
                            description=f"زيادة إيرادات - تصحيح فاتورة {sale.number}"
                        ))
                    else:  # نقص في الفاتورة
                        abs_diff = abs(total_difference)
                        lines.append(JournalEntryLineData(
                            account_code=client_account.code,
                            debit=Decimal("0.00"),
                            credit=abs_diff,
                            description=f"تخفيض ذمة {client_name} - تصحيح فاتورة {sale.number}"
                        ))
                        lines.append(JournalEntryLineData(
                            account_code=accounts["sales_revenue"].code,
                            debit=abs_diff,
                            credit=Decimal("0.00"),
                            description=f"تخفيض إيرادات - تصحيح فاتورة {sale.number}"
                        ))
                
                # معالجة فرق التكلفة (تكلفة البضاعة والمخزون)
                if cost_difference != 0:
                    if cost_difference > 0:  # زيادة في التكلفة
                        lines.append(JournalEntryLineData(
                            account_code=accounts["cost_of_goods_sold"].code,
                            debit=cost_difference,
                            credit=Decimal("0.00"),
                            description=f"زيادة تكلفة البضاعة - تصحيح فاتورة {sale.number}"
                        ))
                        lines.append(JournalEntryLineData(
                            account_code=accounts["inventory"].code,
                            debit=Decimal("0.00"),
                            credit=cost_difference,
                            description=f"تخفيض المخزون - تصحيح فاتورة {sale.number}"
                        ))
                    else:  # نقص في التكلفة
                        abs_cost_diff = abs(cost_difference)
                        lines.append(JournalEntryLineData(
                            account_code=accounts["cost_of_goods_sold"].code,
                            debit=Decimal("0.00"),
                            credit=abs_cost_diff,
                            description=f"تخفيض تكلفة البضاعة - تصحيح فاتورة {sale.number}"
                        ))
                        lines.append(JournalEntryLineData(
                            account_code=accounts["inventory"].code,
                            debit=abs_cost_diff,
                            credit=Decimal("0.00"),
                            description=f"زيادة المخزون - تصحيح فاتورة {sale.number}"
                        ))
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                adjustment_entry = gateway.create_journal_entry(
                    source_module='sales',
                    source_model='Sale',
                    source_id=sale.id,
                    lines=lines,
                    idempotency_key=f"JE:sales:Sale:{sale.id}:adjustment:{current_date.strftime('%Y%m%d')}",
                    user=user,
                    entry_type='adjustment',
                    description=f"تصحيح بسبب تعديل الفاتورة - الفرق: {total_difference} ج.م",
                    reference=f"تصحيح فاتورة مبيعات {sale.number}",
                    date=current_date
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
                
                # Prepare journal entry lines
                lines = []
                
                # معالجة الفرق
                supplier_account = cls._get_supplier_account(purchase.supplier)
                if not supplier_account:
                    logger.warning(f"⚠️ المورد {purchase.supplier.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                    supplier_account = cls._create_supplier_account(purchase.supplier, user)
                    if not supplier_account:
                        error_msg = f"❌ فشل إنشاء حساب محاسبي للمورد {purchase.supplier.name}. يجب إنشاء حساب محاسبي للمورد أولاً."
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                
                if total_difference > 0:  # زيادة في الفاتورة
                    lines.append(JournalEntryLineData(
                        account_code=accounts["inventory"].code,
                        debit=total_difference,
                        credit=Decimal("0.00"),
                        description=f"زيادة مخزون - تصحيح فاتورة {purchase.number}"
                    ))
                    lines.append(JournalEntryLineData(
                        account_code=supplier_account.code,
                        debit=Decimal("0.00"),
                        credit=total_difference,
                        description=f"زيادة مديونية المورد {purchase.supplier.name} - تصحيح فاتورة {purchase.number}"
                    ))
                else:  # نقص في الفاتورة
                    abs_diff = abs(total_difference)
                    lines.append(JournalEntryLineData(
                        account_code=accounts["inventory"].code,
                        debit=Decimal("0.00"),
                        credit=abs_diff,
                        description=f"تخفيض مخزون - تصحيح فاتورة {purchase.number}"
                    ))
                    lines.append(JournalEntryLineData(
                        account_code=supplier_account.code,
                        debit=abs_diff,
                        credit=Decimal("0.00"),
                        description=f"تخفيض مديونية المورد {purchase.supplier.name} - تصحيح فاتورة {purchase.number}"
                    ))
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                adjustment_entry = gateway.create_journal_entry(
                    source_module='purchases',
                    source_model='Purchase',
                    source_id=purchase.id,
                    lines=lines,
                    idempotency_key=f"JE:purchases:Purchase:{purchase.id}:adjustment:{current_date.strftime('%Y%m%d')}",
                    user=user,
                    entry_type='adjustment',
                    description=f"تصحيح بسبب تعديل الفاتورة - الفرق: {total_difference} ج.م",
                    reference=f"تصحيح فاتورة مشتريات {purchase.number}",
                    date=current_date
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
    @classmethod
    def _group_sale_items_by_category(cls, sale) -> dict:
        """تجميع بنود الفاتورة حسب تصنيف المنتجات"""
        try:
            items_by_category = {}
            
            for item in sale.items.select_related('product', 'product__category').all():
                category_name = item.product.category.name if item.product.category else "غير مصنف"
                
                if category_name not in items_by_category:
                    items_by_category[category_name] = []
                
                items_by_category[category_name].append(item)
            
            return items_by_category
            
        except Exception as e:
            logger.error(f"خطأ في تجميع بنود الفاتورة حسب التصنيف: {str(e)}")
            return {}

    @classmethod
    def _get_client_info(cls, sale, user=None) -> tuple:
        """الحصول على معلومات العميل/ولي الأمر وحسابه المحاسبي"""
        try:
            client_account = None
            client_name = ""
            
            if sale.parent:
                # استخدام ولي الأمر (النظام الجديد)
                client_account = cls._get_parent_account(sale.parent)
                client_name = sale.parent.name
                
                if not client_account:
                    # إنشاء حساب جديد لولي الأمر تلقائياً
                    logger.warning(f"⚠️ ولي الأمر {sale.parent.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                    client_account = cls._create_parent_account(sale.parent, user or sale.created_by)
                    
                    if not client_account:
                        # فشل إنشاء الحساب - إيقاف العملية
                        error_msg = f"❌ فشل إنشاء حساب محاسبي لولي الأمر {sale.parent.name}. يجب إنشاء حساب محاسبي لولي الأمر أولاً."
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                        
            elif hasattr(sale, 'customer') and sale.customer:
                # استخدام العميل (النظام القديم - للتوافق المؤقت)
                client_account = cls._get_customer_account(sale.customer)
                client_name = sale.customer.name
                
                if not client_account:
                    # إنشاء حساب جديد للعميل تلقائياً
                    logger.warning(f"⚠️ العميل {sale.customer.name} ليس له حساب محاسبي - سيتم إنشاء حساب جديد")
                    client_account = cls._create_customer_account(sale.customer, user or sale.created_by)
                    
                    if not client_account:
                        # فشل إنشاء الحساب - إيقاف العملية
                        error_msg = f"❌ فشل إنشاء حساب محاسبي للعميل {sale.customer.name}. يجب إنشاء حساب محاسبي للعميل أولاً."
                        logger.error(error_msg)
                        raise ValueError(error_msg)
            else:
                error_msg = "❌ الفاتورة لا تحتوي على ولي أمر أو عميل"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            return client_account, client_name
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على معلومات العميل: {str(e)}")
            return None, ""

    @classmethod
    def _get_item_cost(cls, item) -> Decimal:
        """حساب تكلفة بند واحد"""
        try:
            if not hasattr(item.product, "cost_price") or item.product.cost_price is None:
                return Decimal("0.00")
            
            return item.product.cost_price * item.quantity
            
        except Exception as e:
            logger.error(f"خطأ في حساب تكلفة البند: {str(e)}")
            return Decimal("0.00")

    @classmethod
    def _get_fee_revenue_account(cls, fee_category: str) -> Optional['ChartOfAccounts']:
        """الحصول على حساب الإيرادات المناسب حسب نوع الرسوم"""
        try:
            from financial.models.chart_of_accounts import ChartOfAccounts
            
            # خريطة أنواع الرسوم إلى حسابات الإيرادات
            fee_category_accounts = {
                'academic': '40100',    # إيرادات الرسوم الأساسية
                'tuition': '40100',     # إيرادات الرسوم الأساسية
                'transport': '40300',   # إيرادات النقل
                'bus': '40300',         # إيرادات النقل
                'services': '40300',    # إيرادات خدمات النقل
                'activities': '40400',  # إيرادات أخرى
                'sports': '40400',      # إيرادات أخرى
                'events': '40400',      # إيرادات أخرى
                'products': '41100',    # إيرادات المنتجات
                'materials': '41100',   # إيرادات المنتجات
                'books': '41100',       # إيرادات المنتجات
                'uniform': '41100',     # إيرادات المنتجات
                'stationery': '41100',  # إيرادات المنتجات
            }
            
            # البحث عن حساب مناسب للفئة
            account_code = fee_category_accounts.get(fee_category.lower())
            
            if account_code:
                account = ChartOfAccounts.objects.filter(
                    code=account_code, 
                    is_active=True
                ).first()
                
                if account:
                    return account
                else:
                    logger.warning(f"⚠️ الحساب {account_code} غير موجود أو غير نشط لفئة الرسوم {fee_category}")
            else:
                logger.warning(f"⚠️ لا يوجد حساب مخصص لفئة الرسوم {fee_category}")
            
            # إذا لم يوجد حساب مخصص، إرجاع None لاستخدام الحساب الافتراضي
            return None
            
        except Exception as e:
            logger.error(f"❌ خطأ في الحصول على حساب الإيرادات لفئة الرسوم {fee_category}: {str(e)}")
            return None

    @classmethod
    @classmethod
    def create_reversal_entry(
        cls, 
        original_entry: JournalEntry, 
        refund_amount: Decimal, 
        reason: str,
        user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد عكسي للتسوية المالية - تم تصحيح الخطأ المحاسبي
        
        المبدأ المحاسبي الصحيح:
        - إذا كان البند الأصلي: من حـ/أ (مدين 100) إلى حـ/ب (دائن 100)
        - فالقيد العكسي يكون: من حـ/ب (مدين 100) إلى حـ/أ (دائن 100)
        
        مثال عملي:
        القيد الأصلي: من حـ/ولي الأمر (مدين 150) إلى حـ/الإيرادات (دائن 150)
        القيد العكسي: من حـ/الإيرادات (مدين 150) إلى حـ/ولي الأمر (دائن 150)
        
        الوسائط:
            original_entry: القيد الأصلي المراد عكسه
            refund_amount: مبلغ الاسترداد
            reason: سبب القيد العكسي
            user: المستخدم الذي ينشئ القيد
            
        العائد:
            JournalEntry: القيد العكسي المنشأ أو None في حالة الفشل
        """
        try:
            with transaction.atomic():
                # التحقق من صحة القيد الأصلي
                if not original_entry or not original_entry.is_posted:
                    logger.error("القيد الأصلي غير موجود أو غير مرحل")
                    return None
                
                # التحقق من صحة مبلغ الاسترداد
                if refund_amount <= 0:
                    logger.error("مبلغ الاسترداد يجب أن يكون أكبر من صفر")
                    return None
                
                # حساب المبلغ الإجمالي للقيد الأصلي (أكبر قيمة بين المدين والدائن)
                original_total = max(original_entry.total_debit, original_entry.total_credit)
                
                if refund_amount > original_total:
                    logger.error(f"مبلغ الاسترداد ({refund_amount}) لا يمكن أن يكون أكبر من مبلغ القيد الأصلي ({original_total})")
                    return None
                
                # إنشاء رقم القيد العكسي
                try:
                    reversal_number = cls._generate_journal_number("REV", original_entry.number)
                except Exception as e:
                    logger.error(f"فشل في توليد رقم القيد العكسي: {e}")
                    return None
                
                # الحصول على الفترة المحاسبية
                try:
                    accounting_period = cls._get_accounting_period(timezone.now().date())
                    if not accounting_period:
                        logger.error("لا توجد فترة محاسبية مفتوحة للتاريخ الحالي")
                        return None
                except Exception as e:
                    logger.error(f"فشل في الحصول على الفترة المحاسبية: {e}")
                    return None
                
                # حساب نسبة الاسترداد
                refund_ratio = refund_amount / original_total
                
                # Prepare journal entry lines (reverse of original)
                lines = []
                for original_line in original_entry.lines.all():
                    # حساب المبلغ المتناسب للبند
                    line_debit = original_line.debit * refund_ratio
                    line_credit = original_line.credit * refund_ratio
                    
                    # تجاهل البنود التي مبلغها صفر
                    if line_debit == 0 and line_credit == 0:
                        continue
                    
                    # إنشاء البند العكسي - عكس الجهات تماماً
                    lines.append(JournalEntryLineData(
                        account_code=original_line.account.code,
                        debit=line_credit,   # الدائن الأصلي يصبح مدين في العكسي
                        credit=line_debit,   # المدين الأصلي يصبح دائن في العكسي
                        description=f"عكس: {original_line.description}",
                        cost_center=original_line.cost_center.code if original_line.cost_center else None,
                        project=original_line.project.code if original_line.project else None
                    ))
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                reversal_entry = gateway.create_journal_entry(
                    source_module='financial',
                    source_model='JournalEntry',
                    source_id=original_entry.id,
                    lines=lines,
                    idempotency_key=f"JE:financial:JournalEntry:{original_entry.id}:reversal:{timezone.now().timestamp()}",
                    user=user,
                    entry_type='reversal',
                    description=f"قيد عكسي - {reason}",
                    reference=f"قيد عكسي للقيد {original_entry.number}",
                    date=timezone.now().date()
                )
                
                
                # إضافة سجل تدقيق للقيد العكسي
                try:
                    cls._log_reversal_entry(original_entry, reversal_entry, refund_amount, reason, user)
                except Exception as e:
                    logger.warning(f"⚠️ فشل في تسجيل القيد العكسي في سجل التدقيق: {e}")
                
                return reversal_entry
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد العكسي: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    @classmethod
    def _log_reversal_entry(cls, original_entry, reversal_entry, amount, reason, user):
        """تسجيل عملية القيد العكسي في سجل التدقيق"""
        try:
            logger.info(
                f"قيد عكسي {reversal_entry.number} للقيد الأصلي {original_entry.number} - "
                f"المبلغ: {amount} - السبب: {reason}"
            )
        except Exception as e:
            logger.warning(f"⚠️ فشل في تسجيل القيد العكسي في سجل التدقيق: {e}")
    
    @classmethod
    def validate_reversal_entry(cls, original_entry: JournalEntry, reversal_entry: JournalEntry) -> bool:
        """
        التحقق من صحة القيد العكسي محاسبياً
        
        يتحقق من:
        1. أن مجموع المدين في العكسي = مجموع الدائن في الأصلي
        2. أن مجموع الدائن في العكسي = مجموع المدين في الأصلي
        3. أن كل حساب في العكسي له نفس المبلغ بالجهة المعاكسة
        
        مثال:
        القيد الأصلي: حـ/أ (مدين 100) + حـ/ب (دائن 100)
        القيد العكسي: حـ/أ (دائن 100) + حـ/ب (مدين 100)
        """
        try:
            original_lines = {line.account_id: line for line in original_entry.lines.all()}
            reversal_lines = {line.account_id: line for line in reversal_entry.lines.all()}
            
            # التحقق من أن نفس الحسابات موجودة
            if set(original_lines.keys()) != set(reversal_lines.keys()):
                logger.error("الحسابات في القيد العكسي لا تطابق الحسابات في القيد الأصلي")
                return False
            
            # التحقق من عكس المبالغ لكل حساب
            for account_id in original_lines.keys():
                orig_line = original_lines[account_id]
                rev_line = reversal_lines[account_id]
                
                # المدين الأصلي يجب أن يساوي الدائن العكسي
                if orig_line.debit != rev_line.credit:
                    logger.error(f"خطأ في الحساب {account_id}: المدين الأصلي ({orig_line.debit}) لا يساوي الدائن العكسي ({rev_line.credit})")
                    return False
                
                # الدائن الأصلي يجب أن يساوي المدين العكسي
                if orig_line.credit != rev_line.debit:
                    logger.error(f"خطأ في الحساب {account_id}: الدائن الأصلي ({orig_line.credit}) لا يساوي المدين العكسي ({rev_line.debit})")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في التحقق من صحة القيد العكسي: {e}")
            return False
