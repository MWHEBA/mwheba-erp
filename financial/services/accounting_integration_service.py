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
        "sales_revenue": "41100",  # إيرادات المبيعات العامة
        "cost_of_goods_sold": "51100",  # تكلفة البضاعة المباعة
        "inventory": "11310",  # مخزون البضائع التامة
        "accounts_receivable": "11210",  # العملاء
        "accounts_payable": "21110",  # الموردون
        "cash": "11110",  # الخزينة الرئيسية
        "bank": "11160001",  # الحساب البنكي الرئيسي
        "purchase_expense": "51100",  # مصروفات المشتريات
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
                accounts = cls._get_required_accounts_for_sale()
                if not accounts:
                    error_msg = "لا يمكن العثور على الحسابات المحاسبية المطلوبة للمبيعات"
                    logger.error(error_msg)
                    raise ValidationError(error_msg)

                client_account, client_name = cls._get_client_info(sale, user)
                if not client_account:
                    error_msg = f"لا يوجد حساب محاسبي مرتبط بالعميل في الفاتورة {sale.number}"
                    logger.error(error_msg)
                    raise ValidationError(error_msg)

                total_sale_amount = sale.total
                total_cost_amount = sum(cls._get_item_cost(item) for item in sale.items.all() if not item.product.is_service)

                lines = [
                    JournalEntryLineData(
                        account_code=client_account.code,
                        debit=total_sale_amount,
                        credit=Decimal("0.00"),
                        description=f"مبيعات - {client_name} - فاتورة {sale.number}"
                    ),
                    JournalEntryLineData(
                        account_code=accounts["sales_revenue"].code,
                        debit=Decimal("0.00"),
                        credit=total_sale_amount,
                        description=f"إيرادات مبيعات - فاتورة {sale.number}"
                    )
                ]

                if total_cost_amount > 0:
                    lines.append(
                        JournalEntryLineData(
                            account_code=accounts["cost_of_goods_sold"].code,
                            debit=total_cost_amount,
                            credit=Decimal("0.00"),
                            description=f"تكلفة بضاعة مباعة - فاتورة {sale.number}"
                        )
                    )
                    lines.append(
                        JournalEntryLineData(
                            account_code=accounts["inventory"].code,
                            debit=Decimal("0.00"),
                            credit=total_cost_amount,
                            description=f"تخفيض مخزون - فاتورة {sale.number}"
                        )
                    )

                gateway = AccountingGateway()
                idem_key = AccountingGateway.generate_idempotency_key('sale', 'Sale', sale.id, 'create')
                journal_entry = gateway.create_journal_entry(
                    source_module='sale',
                    source_model='Sale',
                    source_id=sale.id,
                    lines=lines,
                    idempotency_key=idem_key,
                    user=user or sale.created_by,
                    entry_type='sales_invoice',
                    description=f"مبيعات لـ {client_name}",
                    reference=f"فاتورة مبيعات رقم {sale.number}",
                    date=sale.date
                )

                if journal_entry:
                    sale.journal_entry = journal_entry
                    sale.save(update_fields=["journal_entry"])

                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد المبيعات للفاتورة {sale.number}: {str(e)}")
            raise ValidationError(f"فشل إنشاء قيد المبيعات المحاسبي: {str(e)}")

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
                
                # حساب صافي البضاعة/المصروف (المبلغ قبل الضريبة والخصم)
                net_purchase_amount = max(Decimal("0.00"), purchase.subtotal - purchase.discount)
                
                # 1. قيد المخزون أو المصروفات (مدين)
                if purchase.is_service:
                    # للخدمات: استخدام حساب المصروفات من التصنيف المالي أو الافتراضي
                    expense_account = None
                    if purchase.financial_category and purchase.financial_category.default_expense_account:
                        expense_account = purchase.financial_category.default_expense_account
                    elif "purchase_expense" in accounts:
                        expense_account = accounts["purchase_expense"]
                    
                    if not expense_account:
                        logger.error(f"فاتورة الخدمات {purchase.number} ليس لها حساب مصروفات")
                        return None
                    
                    lines.append(
                        JournalEntryLineData(
                            account_code=expense_account.code,
                            debit=net_purchase_amount,
                            credit=Decimal("0.00"),
                            description=f"مصروفات {purchase.service_type_display or 'خدمات'} - فاتورة {purchase.number}"
                        )
                    )
                else:
                    # للمنتجات: استخدام حساب المصروفات من التصنيف المالي (إذا كان موجود)
                    # أو حساب المخزون الافتراضي
                    goods_account = None
                    if purchase.financial_category and purchase.financial_category.default_expense_account:
                        goods_account = purchase.financial_category.default_expense_account
                    elif "inventory" in accounts:
                        goods_account = accounts["inventory"]
                    elif "purchase_expense" in accounts:
                        goods_account = accounts["purchase_expense"]
                    
                    if not goods_account:
                        logger.error(f"لا يمكن العثور على حساب المخزون للفاتورة {purchase.number}")
                        return None
                    
                    lines.append(
                        JournalEntryLineData(
                            account_code=goods_account.code,
                            debit=net_purchase_amount,
                            credit=Decimal("0.00"),
                            description=f"مشتريات مخزون - فاتورة {purchase.number}"
                        )
                    )

                # 2. قيد ضريبة القيمة المضافة (مدخلات) - مدين
                if getattr(purchase, 'vat_active', False) and purchase.tax and purchase.tax > Decimal("0.00"):
                    from financial.services.role_registry import AccountRoleRegistry
                    vat_code = AccountRoleRegistry.resolve_role_code("VAT_INPUT") or "11510"
                    lines.append(
                        JournalEntryLineData(
                            account_code=vat_code,
                            debit=purchase.tax,
                            credit=Decimal("0.00"),
                            description=f"ضريبة القيمة المضافة مدخلات - فاتورة {purchase.number}"
                        )
                    )

                # 3. قيد ضريبة الخصم والإضافة (WHT) - دائن
                if getattr(purchase, 'wht_active', False) and purchase.wht_amount and purchase.wht_amount > Decimal("0.00"):
                    from financial.services.role_registry import AccountRoleRegistry
                    wht_code = AccountRoleRegistry.resolve_role_code("WITHHOLDING_TAX_PAYABLE") or AccountRoleRegistry.resolve_role_code("INCOME_TAX") or "21810"
                    lines.append(
                        JournalEntryLineData(
                            account_code=wht_code,
                            debit=Decimal("0.00"),
                            credit=purchase.wht_amount,
                            description=f"ضريبة خصم المنبع - فاتورة {purchase.number}"
                        )
                    )

                # 4. قيد المورد (دائن) - المبلغ الصافي المستحق للمورد
                supplier_account = cls._get_supplier_account(purchase.supplier)
                if not supplier_account:
                    logger.warning(f"⚠️ المورد {purchase.supplier.name} ليس له حساب محاسبي - سيتم إنشاؤه")
                    from financial.services.subledger_account_service import SubledgerAccountService
                    supplier_account = SubledgerAccountService.get_or_create_supplier_account(
                        purchase.supplier, user or purchase.created_by
                    )
                    
                    if not supplier_account:
                        error_msg = f"❌ فشل إنشاء حساب محاسبي للمورد {purchase.supplier.name}."
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                
                # بناء وصف تفصيلي لبند القيد
                if purchase_items.exists():
                    items_list = [item.product.name for item in purchase_items[:3]]
                    items_text = "، ".join(items_list)
                    if purchase_items.count() > 3:
                        items_text += f" وعناصر أخرى ({purchase_items.count() - 3})"
                    line_description = f"مشتريات من \"{purchase.supplier.name}\" - {items_text}"
                else:
                    line_description = f"مشتريات - المورد {purchase.supplier.name} - فاتورة {purchase.number}"
                
                # حساب صافي المستحق للمورد بعد خصم ضريبة المنبع
                net_supplier_payable = purchase.total
                if getattr(purchase, 'wht_active', False) and purchase.wht_amount and purchase.wht_amount > Decimal("0.00"):
                    net_supplier_payable = max(Decimal("0.00"), purchase.total - purchase.wht_amount)

                lines.append(
                    JournalEntryLineData(
                        account_code=supplier_account.code,
                        debit=Decimal("0.00"),
                        credit=net_supplier_payable,
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
                    entry_type='purchase_invoice',
                    description=description,
                    reference=f"فاتورة مشتريات رقم {purchase.number}",
                    date=purchase.date
                )

                # ربط القيد بالفاتورة
                if journal_entry:
                    purchase.journal_entry = journal_entry
                    purchase.save(update_fields=["journal_entry"])
                    logger.info(f"✅ تم ربط القيد المحاسبي {journal_entry.number} بالفاتورة {purchase.number}")

                return journal_entry

        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد المشتريات: {str(e)}")
            raise

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
                    entry_type='sales_return',
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
                # تحديد نوع القيد
                if payment_type == "sale_payment":
                    # دفعة من عميل/ولي أمر
                    client_name = payment.sale.customer.name if (payment.sale and payment.sale.customer) else getattr(payment.sale, 'client_name', 'عميل')
                    reference = f"دفعة من العميل - فاتورة {payment.sale.number}"
                    description = f"استلام دفعة من {client_name}"

                    # النظام الجديد: payment_method هو account code مباشرة أو legacy 'cash' / 'bank_transfer'
                    payment_method = payment.payment_method
                    account_debit = None
                    if getattr(payment, 'financial_account', None):
                        account_debit = payment.financial_account
                    elif payment_method:
                        from financial.models import ChartOfAccounts
                        account_debit = ChartOfAccounts.objects.filter(code=str(payment_method), is_active=True).first()
                    
                    if not account_debit:
                        from financial.services.account_helper import AccountHelperService
                        if payment_method == 'bank_transfer':
                            account_debit = AccountHelperService.get_default_bank_account()
                        else:
                            account_debit = AccountHelperService.get_default_cash_account()
                        
                    if not account_debit:
                        raise ValueError(f"الحساب المحاسبي {payment_method} غير موجود أو غير نشط")
                    
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
                    from financial.models import ChartOfAccounts
                    account_debit = ChartOfAccounts.objects.filter(code=payment_method, is_active=True).first() if payment_method else None
                    if not account_debit:
                        from financial.services.account_helper import AccountHelperService
                        account_debit = AccountHelperService.get_default_cash_account()
                    
                    if not account_debit:
                        raise ValueError(f"الحساب المحاسبي {payment_method} غير موجود أو غير نشط")
                    
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
                    account_credit = None
                    if getattr(payment, 'financial_account', None):
                        account_credit = payment.financial_account
                    elif payment_method:
                        from financial.models import ChartOfAccounts
                        account_credit = ChartOfAccounts.objects.filter(code=str(payment_method), is_active=True).first()
                    
                    if not account_credit:
                        from financial.services.account_helper import AccountHelperService
                        if payment_method == 'bank_transfer':
                            account_credit = AccountHelperService.get_default_bank_account()
                        else:
                            account_credit = AccountHelperService.get_default_cash_account()
                    
                    if not account_credit:
                        raise ValueError(f"الحساب المحاسبي {payment_method} غير موجود أو غير نشط")

                else:
                    logger.error(f"نوع دفعة غير معروف: {payment_type}")
                    return None

                # تحديد نوع القيد الصحيح
                entry_type = "automatic"  # افتراضي
                financial_category = None
                financial_subcategory = None
                
                if payment_type == "sale_payment":
                    # دفعة من عميل (سند قبض)
                    entry_type = "client_payment"
                    client_name = payment.sale.customer.name if (payment.sale and payment.sale.customer) else getattr(payment.sale, 'client_name', 'عميل')
                    rec_code = f"REC-{str(payment.id).zfill(4)}"
                    reference = payment.reference_number if getattr(payment, 'reference_number', None) else rec_code
                    description = f"تحصيل من العميل \"{client_name}\" - فاتورة مبيعات {payment.sale.number}"

                elif payment_type == "fee_payment":
                    # دفعة رسوم خدمات
                    entry_type = "service_payment"
                    reference = f"FEE-{str(payment.id).zfill(4)}" if not getattr(payment, 'reference', None) else payment.reference
                    description = f"استلام دفعة رسوم"

                elif payment_type == "purchase_payment":
                    # دفعة لمورد (سند صرف)
                    entry_type = "supplier_payment"
                    supplier_name = payment.purchase.supplier.name if (payment.purchase and payment.purchase.supplier) else "المورد"
                    pay_code = f"PAY-{str(payment.id).zfill(4)}"
                    reference = payment.reference_number if getattr(payment, 'reference_number', None) else pay_code
                    
                    purchase_items = payment.purchase.items.all()
                    if purchase_items.exists():
                        items_list = [f"{item.product.name}" for item in purchase_items[:3]]
                        items_text = "، ".join(items_list)
                        if purchase_items.count() > 3:
                            items_text += f" وعناصر أخرى ({purchase_items.count() - 3})"
                        description = f"سداد للمورد \"{supplier_name}\" مقابل {items_text} - فاتورة مشتريات {payment.purchase.number}"
                    else:
                        description = f"سداد للمورد \"{supplier_name}\" - فاتورة مشتريات {payment.purchase.number}"

                cost_center_code = None
                if hasattr(payment, 'cost_center') and payment.cost_center:
                    cost_center_code = payment.cost_center.code if hasattr(payment.cost_center, 'code') else str(payment.cost_center)
                elif payment_type == "purchase_payment" and hasattr(payment.purchase, 'cost_center') and payment.purchase.cost_center:
                    cost_center_code = payment.purchase.cost_center.code if hasattr(payment.purchase.cost_center, 'code') else str(payment.purchase.cost_center)
                elif payment_type == "sale_payment" and hasattr(payment.sale, 'cost_center') and payment.sale.cost_center:
                    cost_center_code = payment.sale.cost_center.code if hasattr(payment.sale.cost_center, 'code') else str(payment.sale.cost_center)

                # إعداد بنود القيد المحاسبي مع دعم تعدد العملات وحوكمة فروق الصرف (IAS 21)
                lines = []
                from financial.services.role_registry import AccountRoleRegistry, AccountRoleNames

                if payment_type == "purchase_payment":
                    invoice = payment.purchase
                    inv_currency_code = invoice.currency.code if (invoice.currency and invoice.currency.code) else "EGP"
                    inv_rate = Decimal(str(getattr(invoice, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')))
                    
                    # 1. المبلغ المخصوم من أصل الفاتورة بعملة الفاتورة
                    settled_invoice_amt = Decimal(str(getattr(payment, 'amount_settled_invoice_currency', Decimal('0.00')) or Decimal('0.00')))
                    if settled_invoice_amt <= Decimal('0.00'):
                        settled_invoice_amt = Decimal(str(payment.amount))
                    
                    # مدين حساب المورد بالمعادل الوظيفي الدفتري لأصل الفاتورة
                    supplier_functional_debit = (settled_invoice_amt * inv_rate).quantize(Decimal('0.01'))
                    
                    # 2. المبلغ الفعلي المسدد من الخزينة/البنك
                    treasury_currency_code = getattr(account_credit, 'currency_code', 'EGP') or 'EGP'
                    pmt_rate = Decimal(str(getattr(payment, 'payment_exchange_rate', Decimal('1.000000')) or Decimal('1.000000')))
                    
                    paid_treasury_amt = Decimal(str(getattr(payment, 'amount_paid_currency', Decimal('0.00')) or Decimal('0.00')))
                    treasury_functional_credit = Decimal(str(getattr(payment, 'amount_functional', Decimal('0.00')) or Decimal('0.00')))
                    
                    if treasury_functional_credit <= Decimal('0.00'):
                        if paid_treasury_amt > Decimal('0.00'):
                            treasury_functional_credit = (paid_treasury_amt * pmt_rate).quantize(Decimal('0.01'))
                        else:
                            if treasury_currency_code == inv_currency_code:
                                paid_treasury_amt = settled_invoice_amt
                                treasury_functional_credit = (paid_treasury_amt * pmt_rate).quantize(Decimal('0.01'))
                            elif treasury_currency_code == 'EGP':
                                paid_treasury_amt = (settled_invoice_amt * pmt_rate).quantize(Decimal('0.01'))
                                treasury_functional_credit = paid_treasury_amt
                            else:
                                paid_treasury_amt = settled_invoice_amt
                                treasury_functional_credit = (paid_treasury_amt * pmt_rate).quantize(Decimal('0.01'))

                    # سطر 1: مدين حساب المورد (إقفال أصل المديونية)
                    lines.append(
                        JournalEntryLineData(
                            account_code=account_debit.code,
                            debit=supplier_functional_debit,
                            credit=Decimal("0.00"),
                            description=description,
                            cost_center=cost_center_code,
                            currency=inv_currency_code,
                            exchange_rate=inv_rate,
                            foreign_debit=settled_invoice_amt if inv_currency_code != 'EGP' else Decimal('0.00'),
                            foreign_credit=Decimal('0.00')
                        )
                    )
                    
                    # سطر 2: دائن حساب الخزينة / البنك (خروج النقدية الفعلي)
                    lines.append(
                        JournalEntryLineData(
                            account_code=account_credit.code,
                            debit=Decimal("0.00"),
                            credit=treasury_functional_credit,
                            description=description,
                            cost_center=cost_center_code,
                            currency=treasury_currency_code,
                            exchange_rate=pmt_rate,
                            foreign_debit=Decimal('0.00'),
                            foreign_credit=paid_treasury_amt if treasury_currency_code != 'EGP' else Decimal('0.00')
                        )
                    )
                    
                    # سطر 3: أرباح أو خسائر فروق الصرف المحققة (Realized FX Gain/Loss)
                    fx_diff = (treasury_functional_credit - supplier_functional_debit).quantize(Decimal('0.01'))
                    payment.realized_fx_difference = fx_diff
                    payment.amount_paid_currency = paid_treasury_amt
                    payment.amount_functional = treasury_functional_credit
                    payment.amount_settled_invoice_currency = settled_invoice_amt
                    payment.save(update_fields=['realized_fx_difference', 'amount_paid_currency', 'amount_functional', 'amount_settled_invoice_currency'])
                    
                    if fx_diff > Decimal('0.00'):
                        # خروج نقدية أكبر من المعادل الدفتري -> خسائر فروق عملة محققة (مدين 54300)
                        fx_loss_account = AccountRoleRegistry.get_account_by_role(AccountRoleNames.FX_REALIZED_LOSS)
                        loss_code = fx_loss_account.code if fx_loss_account else '54300'
                        lines.append(
                            JournalEntryLineData(
                                account_code=loss_code,
                                debit=fx_diff,
                                credit=Decimal('0.00'),
                                description=f"خسائر فروق عملة محققة - سداد فاتورة مشتريات {invoice.number}",
                                cost_center=cost_center_code
                            )
                        )
                    elif fx_diff < Decimal('0.00'):
                        # خروج نقدية أقل من المعادل الدفتري -> أرباح فروق عملة محققة (دائن 43100)
                        fx_gain_account = AccountRoleRegistry.get_account_by_role(AccountRoleNames.FX_REALIZED_GAIN)
                        gain_code = fx_gain_account.code if fx_gain_account else '43100'
                        lines.append(
                            JournalEntryLineData(
                                account_code=gain_code,
                                debit=Decimal('0.00'),
                                credit=abs(fx_diff),
                                description=f"أرباح فروق عملة محققة - سداد فاتورة مشتريات {invoice.number}",
                                cost_center=cost_center_code
                            )
                        )

                elif payment_type == "sale_payment":
                    invoice = payment.sale
                    inv_currency_code = invoice.currency.code if (invoice.currency and invoice.currency.code) else "EGP"
                    inv_rate = Decimal(str(getattr(invoice, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')))
                    
                    # 1. المبلغ المخصوم من أصل الفاتورة بعملة الفاتورة
                    settled_invoice_amt = Decimal(str(getattr(payment, 'amount_settled_invoice_currency', Decimal('0.00')) or Decimal('0.00')))
                    if settled_invoice_amt <= Decimal('0.00'):
                        settled_invoice_amt = Decimal(str(payment.amount))
                    
                    # دائن حساب العميل بالمعادل الوظيفي الدفتري لأصل الفاتورة
                    customer_functional_credit = (settled_invoice_amt * inv_rate).quantize(Decimal('0.01'))
                    
                    # 2. المبلغ الفعلي المحصل في الخزينة/البنك
                    treasury_currency_code = getattr(account_debit, 'currency_code', 'EGP') or 'EGP'
                    pmt_rate = Decimal(str(getattr(payment, 'payment_exchange_rate', Decimal('1.000000')) or Decimal('1.000000')))
                    
                    paid_treasury_amt = Decimal(str(getattr(payment, 'amount_paid_currency', Decimal('0.00')) or Decimal('0.00')))
                    treasury_functional_debit = Decimal(str(getattr(payment, 'amount_functional', Decimal('0.00')) or Decimal('0.00')))
                    
                    if treasury_functional_debit <= Decimal('0.00'):
                        if paid_treasury_amt > Decimal('0.00'):
                            treasury_functional_debit = (paid_treasury_amt * pmt_rate).quantize(Decimal('0.01'))
                        else:
                            if treasury_currency_code == inv_currency_code:
                                paid_treasury_amt = settled_invoice_amt
                                treasury_functional_debit = (paid_treasury_amt * pmt_rate).quantize(Decimal('0.01'))
                            elif treasury_currency_code == 'EGP':
                                paid_treasury_amt = (settled_invoice_amt * pmt_rate).quantize(Decimal('0.01'))
                                treasury_functional_debit = paid_treasury_amt
                            else:
                                paid_treasury_amt = settled_invoice_amt
                                treasury_functional_debit = (paid_treasury_amt * pmt_rate).quantize(Decimal('0.01'))

                    # سطر 1: مدين حساب الخزينة / البنك (دخول النقدية الفعلي)
                    lines.append(
                        JournalEntryLineData(
                            account_code=account_debit.code,
                            debit=treasury_functional_debit,
                            credit=Decimal("0.00"),
                            description=description,
                            cost_center=cost_center_code,
                            currency=treasury_currency_code,
                            exchange_rate=pmt_rate,
                            foreign_debit=paid_treasury_amt if treasury_currency_code != 'EGP' else Decimal('0.00'),
                            foreign_credit=Decimal('0.00')
                        )
                    )
                    
                    # سطر 2: دائن حساب العميل (إقفال أصل المديونية)
                    lines.append(
                        JournalEntryLineData(
                            account_code=account_credit.code,
                            debit=Decimal("0.00"),
                            credit=customer_functional_credit,
                            description=description,
                            cost_center=cost_center_code,
                            currency=inv_currency_code,
                            exchange_rate=inv_rate,
                            foreign_debit=Decimal('0.00'),
                            foreign_credit=settled_invoice_amt if inv_currency_code != 'EGP' else Decimal('0.00')
                        )
                    )
                    
                    # سطر 3: أرباح أو خسائر فروق الصرف المحققة
                    fx_diff = (treasury_functional_debit - customer_functional_credit).quantize(Decimal('0.01'))
                    payment.realized_fx_difference = fx_diff
                    payment.amount_paid_currency = paid_treasury_amt
                    payment.amount_functional = treasury_functional_debit
                    payment.amount_settled_invoice_currency = settled_invoice_amt
                    payment.save(update_fields=['realized_fx_difference', 'amount_paid_currency', 'amount_functional', 'amount_settled_invoice_currency'])
                    
                    if fx_diff > Decimal('0.00'):
                        # دخول نقدية أكبر من المعادل الدفتري -> أرباح فروق عملة محققة (دائن 43100)
                        fx_gain_account = AccountRoleRegistry.get_account_by_role(AccountRoleNames.FX_REALIZED_GAIN)
                        gain_code = fx_gain_account.code if fx_gain_account else '43100'
                        lines.append(
                            JournalEntryLineData(
                                account_code=gain_code,
                                debit=Decimal('0.00'),
                                credit=fx_diff,
                                description=f"أرباح فروق عملة محققة - تحصيل فاتورة مبيعات {invoice.number}",
                                cost_center=cost_center_code
                            )
                        )
                    elif fx_diff < Decimal('0.00'):
                        # دخول نقدية أقل من المعادل الدفتري -> خسائر فروق عملة محققة (مدين 54300)
                        fx_loss_account = AccountRoleRegistry.get_account_by_role(AccountRoleNames.FX_REALIZED_LOSS)
                        loss_code = fx_loss_account.code if fx_loss_account else '54300'
                        lines.append(
                            JournalEntryLineData(
                                account_code=loss_code,
                                debit=abs(fx_diff),
                                credit=Decimal('0.00'),
                                description=f"خسائر فروق عملة محققة - تحصيل فاتورة مبيعات {invoice.number}",
                                cost_center=cost_center_code
                            )
                        )
                else:
                    # سداد الرسوم والمدفوعات العامة
                    lines = [
                        JournalEntryLineData(
                            account_code=account_debit.code,
                            debit=payment.amount,
                            credit=Decimal("0.00"),
                            description=description,
                            cost_center=cost_center_code
                        ),
                        JournalEntryLineData(
                            account_code=account_credit.code,
                            debit=Decimal("0.00"),
                            credit=payment.amount,
                            description=description,
                            cost_center=cost_center_code
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
            from financial.services.role_registry import AccountRoleRegistry
            from financial.models import ChartOfAccounts
            
            accounts = {}
            role_mappings = {
                "sales_revenue": ["SALES_REVENUE", "GENERAL_SALES_REVENUE"],
                "cost_of_goods_sold": ["COGS_EXPENSE"],
                "inventory": ["INVENTORY_CONTROL_ACCOUNT", "INVENTORY_GENERAL"],
                "accounts_receivable": ["CUSTOMER_RECEIVABLE_CONTROL", "AR_CONTROL_ACCOUNT"],
                "cash": ["DEFAULT_CASH_DRAWER", "CASH_CONTROL_ACCOUNT"],
                "bank": ["DEFAULT_BANK_ACCOUNT", "BANK_CONTROL_ACCOUNT"],
            }

            for key, role_names in role_mappings.items():
                account = None
                for role_name in role_names:
                    try:
                        code = AccountRoleRegistry.resolve_role_code(role_name)
                        if code:
                            account = ChartOfAccounts.objects.filter(code=code, is_active=True).first()
                            if account:
                                break
                    except Exception:
                        pass
                
                if not account and key in cls.DEFAULT_ACCOUNTS:
                    code = cls.DEFAULT_ACCOUNTS[key]
                    account = ChartOfAccounts.objects.filter(code=code, is_active=True).first()

                if account:
                    accounts[key] = account
                else:
                    logger.warning(f"لا يمكن العثور على حساب لدور: {key}")

            return accounts if len(accounts) >= 2 else None
        except Exception as e:
            logger.error(f"خطأ في الحصول على حسابات المبيعات: {str(e)}")
            return None

    @classmethod
    def _get_required_accounts_for_purchase(cls) -> Dict[str, ChartOfAccounts]:
        """الحصول على الحسابات المطلوبة للمشتريات"""
        try:
            from financial.services.role_registry import AccountRoleRegistry
            from financial.models import ChartOfAccounts
            from django.db import models
            
            accounts = {}
            role_mappings = {
                "inventory": ["INVENTORY_CONTROL_ACCOUNT", "INVENTORY_GENERAL"],
                "accounts_payable": ["SUPPLIER_PAYABLE_CONTROL", "AP_CONTROL_ACCOUNT"],
                "cash": ["DEFAULT_CASH_DRAWER", "CASH_CONTROL_ACCOUNT"],
                "bank": ["DEFAULT_BANK_ACCOUNT", "BANK_CONTROL_ACCOUNT"],
                "purchase_expense": ["COGS_EXPENSE"],
            }

            for key, role_names in role_mappings.items():
                account = None
                for role_name in role_names:
                    try:
                        code = AccountRoleRegistry.resolve_role_code(role_name)
                        if code:
                            account = ChartOfAccounts.objects.filter(code=code, is_active=True).first()
                            if account:
                                break
                    except Exception:
                        pass
                
                if not account and key in cls.DEFAULT_ACCOUNTS:
                    code = cls.DEFAULT_ACCOUNTS[key]
                    account = ChartOfAccounts.objects.filter(code=code, is_active=True).first()

                if not account:
                    if key == "cash":
                        from financial.services.account_helper import AccountHelperService
                        account = AccountHelperService.get_cash_accounts().first()
                    elif key == "bank":
                        from financial.services.account_helper import AccountHelperService
                        account = AccountHelperService.get_bank_accounts().first()
                    elif key == "inventory":
                        account = ChartOfAccounts.objects.filter(models.Q(code__startswith="104") | models.Q(code__startswith="113"), is_active=True, is_leaf=True).first()
                    elif key == "accounts_payable":
                        account = ChartOfAccounts.objects.filter(models.Q(code__startswith="201") | models.Q(code__startswith="211"), is_active=True, is_leaf=True).first()
                    elif key == "purchase_expense":
                        account = ChartOfAccounts.objects.filter(models.Q(code__startswith="501") | models.Q(code__startswith="511"), is_active=True, is_leaf=True).first()

                if account:
                    accounts[key] = account
                else:
                    logger.warning(f"لا يمكن العثور على حساب لدور: {key}")

            return accounts if len(accounts) >= 2 else None
        except Exception as e:
            logger.error(f"خطأ في الحصول على حسابات المشتريات: {str(e)}")
            return None

    @classmethod
    def _get_required_accounts_for_payment(cls) -> Dict[str, ChartOfAccounts]:
        """الحصول على الحسابات المطلوبة للمدفوعات"""
        try:
            from financial.services.role_registry import AccountRoleRegistry
            from financial.models import ChartOfAccounts
            
            accounts = {}
            role_mappings = {
                "accounts_receivable": ["CUSTOMER_RECEIVABLE_CONTROL", "AR_CONTROL_ACCOUNT"],
                "accounts_payable": ["SUPPLIER_PAYABLE_CONTROL", "AP_CONTROL_ACCOUNT"],
                "cash": ["DEFAULT_CASH_DRAWER", "CASH_CONTROL_ACCOUNT"],
                "bank": ["DEFAULT_BANK_ACCOUNT", "BANK_CONTROL_ACCOUNT"],
            }

            for key, role_names in role_mappings.items():
                account = None
                for role_name in role_names:
                    try:
                        code = AccountRoleRegistry.resolve_role_code(role_name)
                        if code:
                            account = ChartOfAccounts.objects.filter(code=code, is_active=True).first()
                            if account:
                                break
                    except Exception:
                        pass
                
                if not account and key in cls.DEFAULT_ACCOUNTS:
                    code = cls.DEFAULT_ACCOUNTS[key]
                    account = ChartOfAccounts.objects.filter(code=code, is_active=True).first()

                if account:
                    accounts[key] = account
                else:
                    logger.warning(f"لا يمكن العثور على حساب لدور: {key}")

            return accounts if len(accounts) >= 2 else None
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
    def _get_supplier_account(cls, supplier, user=None) -> Optional[ChartOfAccounts]:
        """الحصول على حساب المورد المحدد أو إنشاؤه عبر المحرك المركزي الموحد"""
        if not supplier:
            return None
        from financial.services.subledger_account_service import SubledgerAccountService
        return SubledgerAccountService.get_or_create_supplier_account(supplier, user=user)

    @classmethod
    def _get_customer_account(cls, customer, user=None) -> Optional[ChartOfAccounts]:
        """الحصول على حساب العميل المحدد أو إنشاؤه عبر المحرك المركزي الموحد"""
        if not customer:
            return None
        from financial.services.subledger_account_service import SubledgerAccountService
        return SubledgerAccountService.get_or_create_customer_account(customer, user=user)

    @classmethod
    def _create_customer_account(cls, customer, user: Optional[User] = None) -> Optional[ChartOfAccounts]:
        """إنشاء حساب محاسبي جديد للعميل عبر المحرك المركزي الموحد"""
        if not customer:
            return None
        from financial.services.subledger_account_service import SubledgerAccountService
        return SubledgerAccountService.create_customer_account(customer, user=user)

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
    def create_reversal_entry(
        cls, 
        original_entry: JournalEntry, 
        refund_amount: Decimal, 
        reason: str,
        user: Optional[User] = None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد عكسي للتسوية المالية
        
        المبدأ المحاسبي الصحيح:
        - إذا كان البند الأصلي: من حـ/أ (مدين 100) إلى حـ/ب (دائن 100)
        - فالقيد العكسي يكون: من حـ/ب (مدين 100) إلى حـ/أ (دائن 100)
        
        مثال عملي:
        القيد الأصلي: من حـ/العميل (مدين 150) إلى حـ/الإيرادات (دائن 150)
        القيد العكسي: من حـ/الإيرادات (مدين 150) إلى حـ/العميل (دائن 150)
        
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
