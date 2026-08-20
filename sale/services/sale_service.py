"""
Sale Service - خدمة موحدة لإدارة المبيعات

هذه الخدمة تستخدم:
- AccountingGateway للقيود المحاسبية (مع الحوكمة الكاملة)
- MovementService لحركات المخزون (مع الحوكمة الكاملة)
- CustomerService للتعامل مع العملاء

الهدف: ضمان الالتزام الكامل بمعايير الحوكمة والتدقيق
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
import logging

from sale.models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem
from governance.services.accounting_gateway import AccountingGateway
from governance.services.movement_service import MovementService
from client.services.customer_service import CustomerService

User = get_user_model()
logger = logging.getLogger(__name__)


class SaleService:
    """
    خدمة موحدة لإدارة المبيعات مع الالتزام الكامل بالحوكمة
    """

    @staticmethod
    @transaction.atomic
    def create_sale(data, user):
        """
        إنشاء فاتورة مبيعات جديدة مع القيود المحاسبية وحركات المخزون
        
        Args:
            data: dict يحتوي على بيانات الفاتورة والبنود
            user: المستخدم الذي ينشئ الفاتورة
            
        Returns:
            Sale: الفاتورة المنشأة
            
        Raises:
            Exception: في حالة فشل أي عملية
        """
        try:
            # Validation: التحقق من صحة البيانات
            items_data = data.get('items', [])
            for item in items_data:
                if Decimal(str(item.get('quantity', 0))) <= Decimal('0'):
                    raise ValidationError('لا يمكن بيع البند بكمية صفر أو أقل (Negative/Zero quantity is rejected)')
                if Decimal(str(item.get('unit_price', 0))) <= Decimal('0'):
                    raise ValidationError('لا يمكن بيع البند بسعر صفر أو أقل (Zero price is rejected)')
            # 0. قفل المنتجات والمخزون والعميل بترتيب منظم لمنع الـ Deadlocks وسباق التزامن
            product_ids = sorted([int(item['product_id']) for item in items_data if item.get('product_id')])
            if product_ids:
                from product.models import Product, Stock
                list(Product.objects.filter(id__in=product_ids).order_by('id').select_for_update())
                if data.get('warehouse_id'):
                    list(Stock.objects.filter(product_id__in=product_ids, warehouse_id=data['warehouse_id']).order_by('id').select_for_update())
            
            if data.get('customer_id'):
                from client.models import Customer
                list(Customer.objects.filter(id=data['customer_id']).select_for_update())

            # 1. إنشاء الفاتورة
            currency_id = data.get('currency_id') or data.get('currency')
            currency_obj = None
            if currency_id:
                from financial.models import Currency
                currency_obj = Currency.objects.filter(id=currency_id).first() if str(currency_id).isdigit() else Currency.objects.filter(code=currency_id).first()

            sys_rate = Decimal("1.000000")
            if currency_obj and not currency_obj.is_functional:
                from financial.services.exchange_rate_service import ExchangeRateService
                sys_rate = Decimal(str(ExchangeRateService.get_exchange_rate(currency_obj) or 1.0))

            sale = Sale.objects.create(
                date=data.get('date', timezone.now().date()),
                customer_id=data['customer_id'],
                warehouse_id=data['warehouse_id'],
                currency=currency_obj,
                exchange_rate=sys_rate,
                payment_method=data.get('payment_method', 'credit'),
                subtotal=Decimal('0'),
                discount=Decimal(data.get('discount', 0)),
                discount_type=data.get('discount_type', 'fixed'),
                adjustment_name=data.get('adjustment_name'),
                adjustment_amount=Decimal(data.get('adjustment_amount', 0)),
                tax=Decimal(data.get('tax', 0)),
                tax_active=data.get('tax_active', True) if ('vat_active' in data or 'tax' not in data or Decimal(str(data.get('tax', 0) or 0)) > 0) else False,
                vat_active=data.get('vat_active', True) if ('vat_active' in data or 'tax' not in data or Decimal(str(data.get('tax', 0) or 0)) > 0) else False,
                vat_rate=Decimal(str(data.get('vat_rate', 14.00))),
                wht_active=data.get('wht_active', False),
                wht_rate=Decimal(str(data.get('wht_rate', 1.00))),
                wht_amount=Decimal(str(data.get('wht_amount', 0))),
                total=Decimal('0'),
                notes=data.get('notes', ''),
                status='confirmed',
                created_by=user,
                salesman=data.get('salesman') or user,
                financial_category_id=data.get('financial_category_id'),
                work_order_id=data.get('work_order_id'),
                custom_fields=SaleService.parse_custom_fields(data.get('custom_fields') or data.get('custom_fields_json')),
            )
            
            logger.info(f"✅ تم إنشاء فاتورة المبيعات: {sale.number}")
            
            # 2. إضافة البنود
            items_data = data.get('items', [])
            for item_data in items_data:
                SaleService._add_sale_item(sale, item_data, user)
            
            # إنشاء السعر الاسترشادي المبدئي للمنتجات بالعملة الأجنبية
            if sale.currency and not sale.currency.is_functional:
                from product.services.indicative_price_service import IndicativePriceService
                for item in sale.items.all():
                    if item.unit_price > Decimal("0"):
                        IndicativePriceService.create_if_missing(
                            product=item.product,
                            currency=sale.currency,
                            price=item.unit_price,
                            price_type='selling',
                            user=user
                        )
            
            # 3. حساب الإجماليات
            sale.refresh_from_db()
            SaleService._calculate_totals(sale)
            
            # 4. إنشاء القيد المحاسبي عبر AccountingGateway
            journal_entry = SaleService._create_sale_journal_entry(sale, user)
            if journal_entry:
                sale.journal_entry = journal_entry
                sale.save(update_fields=['journal_entry'])
                logger.info(f"✅ تم ربط القيد المحاسبي: {journal_entry.number} بالفاتورة: {sale.number}")
            
            # 5. إنشاء حركات المخزون عبر MovementService
            SaleService._create_stock_movements(sale, user)
            
            logger.info(f"✅ تم إنشاء فاتورة المبيعات بنجاح: {sale.number}")
            return sale
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء فاتورة المبيعات: {str(e)}")
            raise

    @staticmethod
    def _add_sale_item(sale, item_data, user):
        """
        إضافة بند لفاتورة المبيعات
        """
        item = SaleItem.objects.create(
            sale=sale,
            product_id=item_data['product_id'],
            quantity=Decimal(item_data['quantity']),
            unit_price=Decimal(item_data['unit_price']),
            discount=Decimal(item_data.get('discount', 0)),
            total=Decimal(item_data['quantity']) * Decimal(item_data['unit_price']) - Decimal(item_data.get('discount', 0))
        )
        logger.info(f"✅ تم إضافة بند: {item.product.name} للفاتورة: {sale.number}")
        return item

    @staticmethod
    def _calculate_totals(sale):
        """
        حساب إجماليات الفاتورة
        """
        items = sale.items.all()
        subtotal = sum(item.total for item in items)
        
        sale.subtotal = subtotal
        net_taxable_base = max(Decimal('0'), subtotal - sale.discount + sale.adjustment_amount)
        
        if getattr(sale, 'vat_active', True) and getattr(sale, 'tax_active', True):
            vat_rate = getattr(sale, 'vat_rate', Decimal("14.00")) or Decimal("14.00")
            sale.tax = (net_taxable_base * vat_rate / Decimal("100.00")).quantize(Decimal("0.01"))
        else:
            sale.tax = Decimal("0.00")
            
        if getattr(sale, 'wht_active', False):
            wht_rate = getattr(sale, 'wht_rate', Decimal("1.00")) or Decimal("1.00")
            sale.wht_amount = (net_taxable_base * wht_rate / Decimal("100.00")).quantize(Decimal("0.01"))
        else:
            sale.wht_amount = Decimal("0.00")

        gross_total = net_taxable_base + sale.tax
        sale.total = max(Decimal('0'), gross_total - sale.wht_amount)
        
        if sale.currency and not sale.currency.is_functional:
            sale.total_foreign = sale.total
            sale.total_functional = (sale.total * sale.exchange_rate).quantize(Decimal("0.01"))
        else:
            sale.total_foreign = Decimal("0.00")
            sale.total_functional = sale.total

        sale.save(update_fields=['subtotal', 'tax', 'wht_amount', 'total', 'total_foreign', 'total_functional'])
        
        logger.info(f"✅ تم حساب إجماليات الفاتورة: {sale.number} - الإجمالي: {sale.total}")

    @staticmethod
    @transaction.atomic
    def update_sale(sale, data, user):
        """
        تعديل فاتورة مبيعات مع إعادة تسوية حركات المخزن والقيد المحاسبي بالحوكمة
        """
        if sale.status == 'cancelled':
            raise ValidationError("لا يمكن تعديل فاتورة ملغية")
        
        if sale.is_fully_paid:
            raise ValidationError("لا يمكن تعديل فاتورة مدفوعة بالكامل")
            
        if sale.returns.filter(status='confirmed').exists():
            raise ValidationError("لا يمكن تعديل فاتورة تمت عليها عمليات مرتجع مؤكدة")

        items_data = data.get('items', [])
        if not items_data:
            raise ValidationError("يجب أن تحتوي الفاتورة على بند واحد على الأقل")

        # 1. إلغاء حركات المخزن القديمة للبنود الفيزيائية
        movement_service = MovementService()
        for item in sale.items.all():
            if not item.product.is_service:
                try:
                    movement_service.process_movement(
                        product_id=item.product.id,
                        quantity_change=item.quantity,  # موجب لاستعادة الكمية المصروفة
                        movement_type='in',
                        source_reference=f"SALE_EDIT_RESTORE_{item.id}",
                        idempotency_key=f'sale_{sale.id}_item_{item.id}_restore_{int(timezone.now().timestamp())}',
                        user=user,
                        unit_cost=item.product.cost_price,
                        notes=f'تعديل فاتورة رقم {sale.number} - استرجاع كمية سابقة',
                        movement_date=sale.date,
                        warehouse_id=sale.warehouse_id
                    )
                except Exception as e:
                    logger.warning(f"⚠️ يتعذر استرجاع حركات مخزن البند {item.id}: {e}")

        # 2. تحديث بيانات الفاتورة الأساسية
        sale.date = data.get('date', sale.date)
        if 'customer_id' in data:
            sale.customer_id = data['customer_id']
        if 'warehouse_id' in data:
            sale.warehouse_id = data['warehouse_id']
        if 'payment_method' in data:
            sale.payment_method = data['payment_method']
        if 'discount' in data:
            sale.discount = Decimal(str(data['discount']))
        if 'discount_type' in data:
            sale.discount_type = data['discount_type']
        if 'adjustment_name' in data:
            sale.adjustment_name = data['adjustment_name']
        if 'adjustment_amount' in data:
            sale.adjustment_amount = Decimal(str(data['adjustment_amount']))
        if 'tax' in data:
            sale.tax = Decimal(str(data['tax']))
        if 'notes' in data:
            sale.notes = data['notes']
        if 'financial_category_id' in data:
            sale.financial_category_id = data['financial_category_id']
        sale.save()

        # 3. إزالة البنود القديمة وإضافة البنود الجديدة
        sale.items.all().delete()
        for item_data in items_data:
            SaleService._add_sale_item(sale, item_data, user)

        # 4. إعادة حساب الإجماليات
        sale.refresh_from_db()
        SaleService._calculate_totals(sale)

        # 5. التحقق من ألا يقل الإجمالي الجديد عن الدفعات المرحّلة
        if sale.total < sale.amount_paid:
            raise ValidationError(f"إجمالي الفاتورة الجديد ({sale.total}) أقل من المبالغ المسددة سلفاً ({sale.amount_paid}). يرجى تسوية الدفعات أولاً.")

        # 6. تحديث حالة الدفع
        sale.update_payment_status()

        # 7. توليد قيد جديد بمفتاح تحديث فريد
        version_stamp = int(timezone.now().timestamp())
        try:
            update_key = AccountingGateway.generate_idempotency_key('sale', 'Sale', sale.id, f'update_v{version_stamp}')
            journal_entry = SaleService._create_sale_journal_entry(
                sale, user, idempotency_key=update_key
            )
            if journal_entry:
                sale.journal_entry = journal_entry
                sale.save(update_fields=['journal_entry'])
        except Exception as e:
            logger.error(f"❌ فشل إنشاء القيد المحاسبي المعدل للفاتورة {sale.number}: {e}")
            raise ValidationError(f"فشل إنشاء القيد المحاسبي التعديلي: {e}")

        # 8. إنشاء حركات المخزون الجديدة
        try:
            SaleService._create_stock_movements(sale, user, version_stamp=version_stamp)
        except Exception as e:
            logger.error(f"❌ فشل إنشاء حركات المخزون المعدلة للفاتورة {sale.number}: {e}")
            raise ValidationError(f"فشل تحديث حركات المخزون المعدلة: {e}")

        logger.info(f"✅ تم تعديل الفاتورة بنجاح: {sale.number}")
        return sale

    @staticmethod
    def _create_sale_journal_entry(sale, user, idempotency_key=None):
        """
        إنشاء القيد المحاسبي للفاتورة عبر AccountingGateway
        
        القيد:
        - مدين: العملاء (أو الخزينة/البنك إذا نقدي)
        - دائن: إيرادات المبيعات
        - مدين: تكلفة البضاعة المباعة
        - دائن: المخزون
        """
        try:
            from governance.services.accounting_gateway import JournalEntryLineData
            from financial.models import ChartOfAccounts
            from django.core.exceptions import ValidationError
            
            logger.info(f"🔍 بدء إنشاء القيد المحاسبي للفاتورة: {sale.number}")
            logger.info(f"   - العميل: {sale.customer.name} (ID: {sale.customer.id})")
            logger.info(f"   - طريقة الدفع: {sale.payment_method}")
            logger.info(f"   - الإجمالي: {sale.total}")
            
            # تحديد حساب المدين: يجب دائماً مدين حساب العميل في قيد الفاتورة
            # لضمان عدم حدوث تكرار لمديونية الخزينة (Double-Debit) وتكامل الحسابات
            if not sale.customer.financial_account:
                logger.info(
                    f"ℹ️ العميل '{sale.customer.name}' (ID: {sale.customer.id}) ليس لديه حساب محاسبي. "
                    f"سيتم إنشاؤه عبر CustomerService مباشرة."
                )
                try:
                    CustomerService.create_financial_account_for_customer(sale.customer)
                    sale.customer.refresh_from_db()
                except Exception as e:
                    logger.warning(f"⚠️ يتعذر إنشاء حساب العميل عبر الخدمة: {e}")
                    sale.customer.save()
                    sale.customer.refresh_from_db()
                
                # التحقق من نجاح الإنشاء
                if not sale.customer.financial_account:
                    from django.core.exceptions import ValidationError
                    error_msg = (
                        f"❌ فشل إنشاء حساب محاسبي للعميل '{sale.customer.name}' (ID: {sale.customer.id}). "
                        f"يرجى التأكد من:\n"
                        f"1. وجود حساب العملاء الرئيسي (10300)\n"
                        f"2. تفعيل AUTO_CREATE_CUSTOMER_ACCOUNTS في settings\n"
                        f"3. عدم وجود أخطاء في CustomerService.create_financial_account_for_customer()"
                    )
                    logger.error(error_msg)
                    raise ValidationError(error_msg)
            
            debit_account = sale.customer.financial_account
            logger.info(f"✅ استخدام حساب العميل للمديونية: {debit_account.code} - {debit_account.name}")

            
            # حساب تكلفة البضاعة المباعة (فقط للمنتجات المادية)
            cost_of_goods_sold = Decimal('0')
            for item in sale.items.all():
                if item.product.is_service:
                    continue
                if not item.product.cost_price or item.product.cost_price == 0:
                    logger.warning(f"⚠️ المنتج '{item.product.name}' ليس له سعر تكلفة - سيتم استخدام 0")
                cost_of_goods_sold += (item.product.cost_price or Decimal('0')) * item.quantity
            
            logger.info(f"   - تكلفة البضاعة المباعة: {cost_of_goods_sold}")
            
            from financial.services.role_registry import AccountRoleRegistry

            # الحصول على الحسابات المطلوبة عبر سجل الأدوار المركزي
            sales_revenue_account = None
            try:
                sales_revenue_account = AccountRoleRegistry.get_account("SALES_REVENUE")
            except Exception:
                sales_revenue_account = ChartOfAccounts.objects.filter(code__in=['41100', '40100'], is_active=True).first()
            if not sales_revenue_account:
                error_msg = "❌ حساب إيرادات المبيعات غير موجود في دليل الحسابات. يرجى إنشاؤه أولاً."
                logger.error(error_msg)
                raise ValidationError(error_msg)

            # محاولة جلب حساب إيرادات الخدمات (41200 / 40200) - والارتداد لحساب المبيعات لو مش موجود
            services_revenue_account = ChartOfAccounts.objects.filter(code__in=['41200', '40200'], is_active=True).first() or sales_revenue_account

            cogs_account = None
            try:
                cogs_account = AccountRoleRegistry.get_account("COGS_EXPENSE")
            except Exception:
                cogs_account = ChartOfAccounts.objects.filter(code__in=['51100', '50100'], is_active=True).first()
            if not cogs_account:
                error_msg = "❌ حساب تكلفة البضاعة المباعة غير موجود في دليل الحسابات. يرجى إنشاؤه أولاً."
                logger.error(error_msg)
                raise ValidationError(error_msg)

            inventory_account = None
            try:
                inventory_account = AccountRoleRegistry.get_account("INVENTORY_GENERAL")
            except Exception:
                inventory_account = ChartOfAccounts.objects.filter(code__in=['11310', '10400'], is_active=True).first()
            if not inventory_account:
                error_msg = "❌ حساب المخزون غير موجود في دليل الحسابات. يرجى إنشاؤه أولاً."
                logger.error(error_msg)
                raise ValidationError(error_msg)

            # تقسيم الإجمالي النهائي بين المنتجات والخدمات بالتناسب مع الـ subtotal لكل فئة
            physical_subtotal = Decimal('0')
            service_subtotal = Decimal('0')
            for item in sale.items.all():
                if item.product.is_service:
                    service_subtotal += item.total
                else:
                    physical_subtotal += item.total
                    
            total_items_subtotal = physical_subtotal + service_subtotal
            if total_items_subtotal > 0:
                physical_ratio = physical_subtotal / total_items_subtotal
                service_ratio = service_subtotal / total_items_subtotal
            else:
                physical_ratio = Decimal('1')
                service_ratio = Decimal('0')
                
            # حساب صافي الإيراد (المبلغ قبل الضريبة والخصم)
            net_revenue_total = max(Decimal('0'), sale.subtotal - sale.discount)
            
            # إذا كانت هناك ضرائب (VAT/WHT) نوزع صافي الإيراد على المنتجات والخدمات
            has_taxes = (getattr(sale, 'vat_active', False) and sale.tax and sale.tax > Decimal('0')) or (getattr(sale, 'wht_active', False) and sale.wht_amount and sale.wht_amount > Decimal('0'))
            
            revenue_base = net_revenue_total if has_taxes else sale.total
            physical_revenue_total = (revenue_base * physical_ratio).quantize(Decimal('0.01'))
            service_revenue_total = (revenue_base - physical_revenue_total).quantize(Decimal('0.01'))
            
            # إعداد بيانات القيد باستخدام JournalEntryLineData
            lines = []
            customer_name = getattr(sale.customer, 'name', '')
            cust_suffix = f" - {customer_name}" if customer_name else ""

            if sale.total > 0:
                lines.append(
                    # مدين: العملاء/الخزينة/البنك
                    JournalEntryLineData(
                        account_code=debit_account.code,
                        debit=sale.total,
                        credit=Decimal('0'),
                        description=f'مبيعات - فاتورة {sale.number}{cust_suffix}'
                    )
                )

            # مدين: ضريبة الخصم والإضافة (WHT محجوزة لدى العميل) إذا كانت مفعلة
            if getattr(sale, 'wht_active', False) and sale.wht_amount and sale.wht_amount > Decimal('0'):
                wht_account = None
                try:
                    wht_account = AccountRoleRegistry.get_account("CUSTOMER_WHT_RECEIVABLE")
                except Exception:
                    wht_account = ChartOfAccounts.objects.filter(code__in=['11520', '11500'], is_active=True).first()
                
                if wht_account:
                    lines.append(
                        JournalEntryLineData(
                            account_code=wht_account.code,
                            debit=sale.wht_amount,
                            credit=Decimal('0'),
                            description=f'ضريبة مخصومة ومحجوزة لدى الغير - فاتورة {sale.number}{cust_suffix}'
                        )
                    )

            # دائن: إيرادات المنتجات المادية
            if physical_revenue_total > 0:
                lines.append(
                    JournalEntryLineData(
                        account_code=sales_revenue_account.code,
                        debit=Decimal('0'),
                        credit=physical_revenue_total,
                        description=f'مبيعات منتجات - فاتورة {sale.number}{cust_suffix}'
                    )
                )

            # دائن: إيرادات الخدمات
            if service_revenue_total > 0:
                lines.append(
                    JournalEntryLineData(
                        account_code=services_revenue_account.code,
                        debit=Decimal('0'),
                        credit=service_revenue_total,
                        description=f'مبيعات خدمات - فاتورة {sale.number}{cust_suffix}'
                    )
                )

            # دائن: ضريبة القيمة المضافة (مخرجات) إذا كانت مفعلة
            if getattr(sale, 'vat_active', False) and sale.tax and sale.tax > Decimal('0'):
                vat_account = None
                try:
                    vat_account = AccountRoleRegistry.get_account("VAT_OUTPUT")
                except Exception:
                    vat_account = ChartOfAccounts.objects.filter(code__in=['21310', '21300'], is_active=True).first()

                if vat_account:
                    lines.append(
                        JournalEntryLineData(
                            account_code=vat_account.code,
                            debit=Decimal('0'),
                            credit=sale.tax,
                            description=f'ضريبة القيمة المضافة مخرجات - فاتورة {sale.number}{cust_suffix}'
                        )
                    )
                else:
                    # في حالة عدم وجود حساب ضريبة مخرجات (مثلاً في بيئة اختبار مبسطة) تضاف للإيراد
                    if physical_revenue_total > 0:
                        lines[1].credit += sale.tax
                    elif service_revenue_total > 0:
                        lines[2].credit += sale.tax

            # مدين ودائن قيد التكلفة (فقط للمنتجات المادية وعندما تكون التكلفة أكبر من صفر)
            if cost_of_goods_sold > 0:
                lines.append(
                    JournalEntryLineData(
                        account_code=cogs_account.code,
                        debit=cost_of_goods_sold,
                        credit=Decimal('0'),
                        description=f'تكلفة مبيعات - فاتورة {sale.number}{cust_suffix}'
                    )
                )
                lines.append(
                    JournalEntryLineData(
                        account_code=inventory_account.code,
                        debit=Decimal('0'),
                        credit=cost_of_goods_sold,
                        description=f'تكلفة مبيعات - فاتورة {sale.number}{cust_suffix}'
                    )
                )
            
            if not lines:
                logger.info(f"الفاتورة {sale.number} بقيمة صفري، لا يتطلب قيد محاسبي.")
                return None
            
            # إنشاء القيد عبر AccountingGateway (مع الحوكمة الكاملة)
            gateway = AccountingGateway()
            entry_idem_key = idempotency_key if idempotency_key else AccountingGateway.generate_idempotency_key('sale', 'Sale', sale.id, 'create')
            journal_entry = gateway.create_journal_entry(
                source_module='sale',
                source_model='Sale',
                source_id=sale.id,
                lines=lines,
                idempotency_key=entry_idem_key,
                user=user,
                entry_type='sales_invoice',
                description=f'فاتورة مبيعات رقم {sale.number} - {sale.customer.name}',
                reference=sale.number,
                date=sale.date
            )
            
            logger.info(f"✅ تم إنشاء القيد المحاسبي: {journal_entry.number} للفاتورة: {sale.number}")
            return journal_entry
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للفاتورة {sale.number}: {str(e)}")
            raise

    @staticmethod
    def _create_stock_movements(sale, user, version_stamp=None):
        """
        إنشاء حركات المخزون للفاتورة عبر MovementService
        
        ملاحظة: لا نستخدم document_number هنا لأن AccountingGateway يفترض أن أي
        حركة لها document_number هي فاتورة مشتريات ويحاول البحث عن المورد
        """
        try:
            movement_service = MovementService()
            
            for item in sale.items.all():
                # تخطي الخدمات - لا تولد حركات مخزنية
                if item.product.is_service:
                    logger.info(f"ℹ️ تخطي بند الخدمة: {item.product.name} من حركة المخزون")
                    continue
                # إنشاء الحركة عبر MovementService (مع الحوكمة الكاملة)
                item_idem_key = AccountingGateway.generate_idempotency_key('product', 'StockMovement', item.id, f'sale_{sale.id}_out' if not version_stamp else f'sale_{sale.id}_v{version_stamp}')
                movement = movement_service.process_movement(
                    product_id=item.product.id,
                    quantity_change=-item.quantity,  # Negative for outbound
                    movement_type='out',
                    source_reference=f"SALE_ITEM_{item.id}",
                    idempotency_key=item_idem_key,
                    user=user,
                    unit_cost=item.product.cost_price,
                    document_number=sale.number,
                    notes=f'مبيعات - فاتورة رقم {sale.number}',
                    movement_date=sale.date,
                    warehouse_id=sale.warehouse_id if sale.warehouse_id else None
                )
                
                logger.info(f"✅ تم إنشاء حركة مخزون: {movement.id} للبند: {item.product.name}")
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء حركات المخزون للفاتورة {sale.number}: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def process_payment(sale, payment_data, user):
        """
        معالجة دفعة على فاتورة مبيعات
        
        Args:
            sale: الفاتورة
            payment_data: بيانات الدفعة
            user: المستخدم
            
        Returns:
            SalePayment: الدفعة المنشأة
        """
        try:
            # 0. قفل صف الفاتورة في قاعدة البيانات والتحقق من المتبقي للتزامن
            locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
            amount = Decimal(payment_data['amount'])

            if amount <= Decimal('0'):
                raise ValidationError("مبلغ الدفعة يجب أن يكون أكبر من صفر")

            remaining = locked_sale.amount_due
            if remaining <= Decimal('0'):
                raise ValidationError(f"الفاتورة {locked_sale.number} مسددة بالكامل بالفعل ولا توجد مبالغ متبقية للدفع.")

            if amount > remaining:
                raise ValidationError(f"مبلغ الدفعة ({amount} ج.م) يتجاوز المبلغ المتبقي على الفاتورة ({remaining:.2f} ج.م).")

            sale = locked_sale
            pm = payment_data.get('payment_method', 'cash')

            # معالجة خاصة للخصم المباشر من الرصيد المسبق للعميل
            if pm == 'PREPAID_BALANCE':
                from client.services.customer_allocation_audit_service import CustomerAllocationAuditService
                audit = CustomerAllocationAuditService.allocate_customer_prepaid_balance_to_sale(
                    sale=sale,
                    amount_to_allocate=amount,
                    user=user
                )
                sale.update_payment_status()
                prepaid_payment = sale.payments.filter(source_type='PREPAID_BALANCE').order_by('-created_at').first()
                if prepaid_payment:
                    return prepaid_payment

            # البحث عن الحساب المالي كـ ForeignKey
            fin_acc = None
            if pm and str(pm).isdigit():
                from financial.models import ChartOfAccounts
                fin_acc = ChartOfAccounts.objects.filter(code=str(pm), is_active=True).first()

            if not fin_acc:
                from financial.services.account_helper import AccountHelperService
                fin_acc = AccountHelperService.get_default_cash_account()

            # العملات المتعددة
            from financial.models import Currency
            from financial.services.exchange_rate_service import ExchangeRateService

            pmt_curr = fin_acc.currency if (fin_acc and fin_acc.currency) else (sale.currency or None)
            if not pmt_curr:
                func_curr_obj = ExchangeRateService.get_functional_currency()
                if isinstance(func_curr_obj, Currency):
                    pmt_curr = func_curr_obj
                else:
                    curr_code = getattr(func_curr_obj, 'code', 'EGP')
                    pmt_curr = Currency.objects.filter(code=curr_code).first()
            elif not isinstance(pmt_curr, Currency):
                curr_code = getattr(pmt_curr, 'code', 'EGP')
                pmt_curr = Currency.objects.filter(code=curr_code).first()
            
            raw_rate = payment_data.get('payment_exchange_rate')
            if raw_rate:
                pmt_rate = Decimal(str(raw_rate))
            elif pmt_curr and not getattr(pmt_curr, 'is_functional', True):
                pmt_rate = Decimal(str(ExchangeRateService.get_rate(pmt_curr) or 1.0))
            else:
                pmt_rate = Decimal('1.000000')

            raw_paid_amt = payment_data.get('amount_paid_currency')
            paid_curr_amt = Decimal(str(raw_paid_amt)) if raw_paid_amt else amount
            
            treasury_code = fin_acc.currency_code if fin_acc else 'EGP'
            if treasury_code == 'EGP':
                func_amt = paid_curr_amt
            else:
                func_amt = (paid_curr_amt * pmt_rate).quantize(Decimal('0.01'))

            # 1. إنشاء الدفعة
            payment = SalePayment.objects.create(
                sale=sale,
                amount=amount,
                payment_method=pm if pm else (fin_acc.code if fin_acc else 'cash'),
                financial_account=fin_acc,
                payment_currency=pmt_curr,
                payment_exchange_rate=pmt_rate,
                amount_paid_currency=paid_curr_amt,
                amount_functional=func_amt,
                amount_settled_invoice_currency=amount,
                payment_date=payment_data.get('payment_date', timezone.now().date()),
                notes=payment_data.get('notes', ''),
                status='draft',
                created_by=user
            )
            
            logger.info(f"✅ تم إنشاء دفعة: {payment.id} للفاتورة: {sale.number}")
            
            # 2. إنشاء القيد المحاسبي للدفعة عبر AccountingIntegrationService
            journal_entry = SaleService._create_payment_journal_entry(payment, user)
            if journal_entry:
                payment.financial_transaction = journal_entry
                payment.status = 'posted'
                payment.posted_at = timezone.now()
                payment.posted_by = user
                payment.save(update_fields=['financial_transaction', 'status', 'posted_at', 'posted_by'])
                logger.info(f"✅ تم ترحيل الدفعة: {payment.id}")
            
            # 3. تحديث حالة الدفع للفاتورة
            sale.update_payment_status()
            
            return payment
            
        except Exception as e:
            logger.error(f"❌ خطأ في معالجة الدفعة للفاتورة {sale.number}: {str(e)}")
            raise

    @staticmethod
    def _create_payment_journal_entry(payment, user):
        """
        إنشاء القيد المحاسبي للدفعة عبر AccountingIntegrationService (Single Source of Truth)
        """
        try:
            # الدفعات المخصومة من الرصيد المسبق يتم ترحيل قيودها عبر خدمة التخصيص
            if payment.source_type == 'PREPAID_BALANCE' or payment.payment_method == 'PREPAID_BALANCE':
                return None

            from financial.services.accounting_integration_service import AccountingIntegrationService
            journal_entry = AccountingIntegrationService.create_payment_journal_entry(
                payment=payment,
                payment_type='sale_payment',
                user=user
            )
            return journal_entry
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد المحاسبي لدفعة المبيعات {payment.id}: {str(e)}")
            raise
            
            logger.info(f"✅ تم إنشاء القيد المحاسبي: {journal_entry.number} للدفعة: {payment.id}")
            return journal_entry
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للدفعة {payment.id}: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def create_return(sale, return_data, user):
        """
        إنشاء مرتجع مبيعات
        
        Args:
            sale: الفاتورة الأصلية
            return_data: بيانات المرتجع
            user: المستخدم
            
        Returns:
            SaleReturn: المرتجع المنشأ
        """
        try:
            # 1. إنشاء المرتجع
            # Support both 'date' and 'return_date' for backward compatibility
            return_date = return_data.get('date') or return_data.get('return_date', timezone.now().date())
            
            sale_return = SaleReturn.objects.create(
                sale=sale,
                date=return_date,
                warehouse=sale.warehouse,
                subtotal=Decimal('0'),
                discount=Decimal('0'),
                tax=Decimal('0'),
                total=Decimal('0'),
                status='confirmed',
                notes=return_data.get('notes', ''),
                created_by=user
            )
            
            logger.info(f"✅ تم إنشاء مرتجع: {sale_return.number} للفاتورة: {sale.number}")
            
            # 2. إضافة بنود المرتجع
            items_data = return_data.get('items', [])
            for item_data in items_data:
                SaleService._add_return_item(sale_return, item_data, user)
            
            # 3. حساب الإجمالي
            sale_return.refresh_from_db()
            total = sum(item.total for item in sale_return.items.all())
            sale_return.total = total
            sale_return.subtotal = total
            sale_return.save(update_fields=['total', 'subtotal'])
            
            # 4. إنشاء القيد المحاسبي للمرتجع
            journal_entry = SaleService._create_return_journal_entry(sale_return, user)
            if journal_entry:
                sale_return.journal_entry = journal_entry
                sale_return.save(update_fields=['journal_entry'])
            
            # 5. إنشاء حركات المخزون (إرجاع)
            SaleService._create_return_stock_movements(sale_return, user)
            
            # 6. تحديث حالة الدفع للفاتورة
            sale.update_payment_status()
            
            logger.info(f"✅ تم إنشاء المرتجع بنجاح: {sale_return.number}")
            return sale_return
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء المرتجع للفاتورة {sale.number}: {str(e)}")
            raise

    @staticmethod
    def _add_return_item(sale_return, item_data, user):
        """
        إضافة بند للمرتجع
        """
        from sale.models import SaleItem
        
        sale_item = SaleItem.objects.get(id=item_data['sale_item_id'])
        
        item = SaleReturnItem.objects.create(
            sale_return=sale_return,
            sale_item=sale_item,
            product=sale_item.product,
            quantity=Decimal(item_data['quantity']),
            unit_price=Decimal(item_data['unit_price']),
            discount=Decimal(item_data.get('discount', 0)),
            total=Decimal(item_data['quantity']) * Decimal(item_data['unit_price']) - Decimal(item_data.get('discount', 0)),
            reason=item_data.get('reason', 'مرتجع')
        )
        logger.info(f"✅ تم إضافة بند مرتجع: {item.product.name}")
        return item

    @staticmethod
    def _create_return_journal_entry(sale_return, user):
        """
        إنشاء القيد المحاسبي للمرتجع (عكس قيد المبيعات)
        """
        try:
            from governance.services.accounting_gateway import JournalEntryLineData
            from financial.models import ChartOfAccounts
            from financial.services.account_role_registry import AccountRoleRegistry
            
            sale = sale_return.sale
            
            # تحديد حساب الدائن حسب طريقة الدفع الأصلية
            if sale.payment_method == 'cash':
                credit_account_code = AccountRoleRegistry.get_account_code("CASH_CONTROL_ACCOUNT")
            elif sale.payment_method == 'bank_transfer':
                credit_account_code = AccountRoleRegistry.get_account_code("BANK_CONTROL_ACCOUNT")
            else:
                # حساب العميل - التأكد من وجود الحساب المحاسبي
                if not sale.customer.financial_account:
                    # استدعاء الـ signal لإنشاء الحساب (Single Source of Truth)
                    logger.warning(
                        f"العميل '{sale.customer.name}' ليس لديه حساب محاسبي. "
                        f"سيتم إنشاؤه تلقائياً عبر signal."
                    )
                    sale.customer.save()  # Trigger post_save signal
                    sale.customer.refresh_from_db()
                    
                    # التحقق من نجاح الإنشاء
                    if not sale.customer.financial_account:
                        raise ValidationError(
                            f"فشل إنشاء حساب محاسبي للعميل '{sale.customer.name}'. "
                            f"يرجى التواصل مع الدعم الفني."
                        )
                
                if sale.customer.financial_account:
                    credit_account_code = sale.customer.financial_account.code
                else:
                    credit_account_code = '10300'  # حساب العملاء الرئيسي
                    logger.warning(f"استخدام حساب العملاء الرئيسي للعميل {sale.customer.name}")
            
            # حساب تكلفة البضاعة المرتجعة (فقط للمنتجات المادية)
            cost_of_goods_returned = sum(
                item.product.cost_price * item.quantity
                for item in sale_return.items.all()
                if not item.product.is_service
            )
            
            # تقسيم الإرجاع بالتناسب بين المنتجات والخدمات
            physical_return = Decimal('0')
            service_return = Decimal('0')
            for item in sale_return.items.all():
                if item.product.is_service:
                    service_return += item.total
                else:
                    physical_return += item.total
                    
            total_items_return = physical_return + service_return
            if total_items_return > 0:
                physical_ratio = physical_return / total_items_return
                service_ratio = service_return / total_items_return
            else:
                physical_ratio = Decimal('1')
                service_ratio = Decimal('0')
                
            physical_return_total = (sale_return.total * physical_ratio).quantize(Decimal('0.01'))
            service_return_total = (sale_return.total - physical_return_total).quantize(Decimal('0.01'))
            
            # إعداد بيانات القيد باستخدام JournalEntryLineData
            lines = []

            sales_rev_code = AccountRoleRegistry.get_account_code("SALES_REVENUE_ACCOUNT")

            # مدين: إيرادات المبيعات (عكس) للرصيد المادي
            if physical_return_total > 0:
                lines.append(
                    JournalEntryLineData(
                        account_code=sales_rev_code,
                        debit=physical_return_total,
                        credit=Decimal('0'),
                        description=f'عكس مبيعات منتجات - مرتجع {sale_return.number}'
                    )
                )

            # مدين: إيرادات الخدمات (عكس) للرصيد الخدمي
            if service_return_total > 0:
                try:
                    services_revenue_account_code = ChartOfAccounts.objects.get(code='40200', is_active=True).code
                except ChartOfAccounts.DoesNotExist:
                    services_revenue_account_code = '40100'
                
                lines.append(
                    JournalEntryLineData(
                        account_code=services_revenue_account_code,
                        debit=service_return_total,
                        credit=Decimal('0'),
                        description=f'عكس مبيعات خدمات - مرتجع {sale_return.number}'
                    )
                )

            # دائن: العملاء/الخزينة/البنك (عكس)
            lines.append(
                JournalEntryLineData(
                    account_code=credit_account_code,
                    debit=Decimal('0'),
                    credit=sale_return.total,
                    description=f'مرتجع - فاتورة {sale.number}'
                )
            )

            # قيد تكلفة ومخزون للمرتجع (فقط للمنتجات المادية وعند وجود تكلفة بضاعة مرتجعة)
            if cost_of_goods_returned > 0:
                inv_code = AccountRoleRegistry.get_account_code("INVENTORY_CONTROL_ACCOUNT")
                cogs_code = AccountRoleRegistry.get_account_code("COGS_EXPENSE_ACCOUNT")
                lines.append(
                    JournalEntryLineData(
                        account_code=inv_code,
                        debit=cost_of_goods_returned,
                        credit=Decimal('0'),
                        description=f'إرجاع مخزون - مرتجع {sale_return.number}'
                    )
                )
                lines.append(
                    JournalEntryLineData(
                        account_code=cogs_code,
                        debit=Decimal('0'),
                        credit=cost_of_goods_returned,
                        description=f'عكس تكلفة البضاعة - مرتجع {sale_return.number}'
                    )
                )
            
            # إنشاء القيد عبر AccountingGateway
            gateway = AccountingGateway()
            journal_entry = gateway.create_journal_entry(
                source_module='sale',
                source_model='SaleReturn',
                source_id=sale_return.id,
                lines=lines,
                idempotency_key=f'sale_return_{sale_return.id}_journal_entry',
                user=user,
                entry_type='sales_return',
                description=f'مرتجع مبيعات رقم {sale_return.number} - فاتورة {sale.number}',
                reference=sale_return.number,
                date=sale_return.date
            )
            
            logger.info(f"✅ تم إنشاء القيد المحاسبي: {journal_entry.number} للمرتجع: {sale_return.number}")
            return journal_entry
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للمرتجع {sale_return.number}: {str(e)}")
            raise

    @staticmethod
    def _create_return_stock_movements(sale_return, user):
        """
        إنشاء حركات المخزون للمرتجع (إرجاع للمخزن)
        
        ملاحظة: لا نستخدم document_number هنا لأن AccountingGateway يفترض أن أي
        حركة لها document_number هي فاتورة مشتريات ويحاول البحث عن المورد
        """
        try:
            movement_service = MovementService()
            
            for item in sale_return.items.all():
                # تخطي الخدمات - لا تولد حركات إرجاع مخزنية
                if item.product.is_service:
                    logger.info(f"ℹ️ تخطي بند الخدمة: {item.product.name} من حركة إرجاع المخزون")
                    continue
                # إنشاء الحركة عبر MovementService (مع الحوكمة الكاملة)
                movement = movement_service.process_movement(
                    product_id=item.product.id,
                    quantity_change=item.quantity,  # Positive for inbound
                    movement_type='in',
                    source_reference=f"RETURN_ITEM_{item.id}",
                    idempotency_key=f'sale_return_{sale_return.id}_item_{item.id}_movement',
                    user=user,
                    unit_cost=item.product.cost_price,
                    document_number=None,
                    notes=f'مرتجع مبيعات - فاتورة {sale_return.sale.number}',
                    movement_date=sale_return.date,
                    warehouse_id=sale_return.sale.warehouse_id if sale_return.sale.warehouse_id else None
                )
                
                logger.info(f"✅ تم إنشاء حركة مخزون (إرجاع): {movement.id}")
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء حركات المخزون للمرتجع {sale_return.number}: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def delete_sale(sale, user):
        """
        حذف فاتورة مبيعات مع التراجع عن جميع العمليات
        
        Args:
            sale: الفاتورة المراد حذفها
            user: المستخدم
        """
        try:
            customer = sale.customer
            # 1. حذف القيد المحاسبي
            if sale.journal_entry:
                try:
                    # فك قفل القيد وتغيير الحالة قبل الحذف
                    from financial.models import JournalEntry, FinancialPostingReference
                    journal_entry = sale.journal_entry
                    journal_entry._allow_lock_operation = True
                    FinancialPostingReference.objects.filter(journal_entry_id=journal_entry.pk).delete()
                    JournalEntry.objects.filter(pk=journal_entry.pk).update(status='draft', is_locked=False)
                    journal_entry.status = 'draft'
                    journal_entry.delete()
                    logger.info(f"✅ تم حذف القيد المحاسبي للفاتورة: {sale.number}")
                except Exception as e:
                    logger.warning(f"فشل حذف القيد المحاسبي: {str(e)}")
            
            # 2. حذف حركات المخزون
            from product.models import StockMovement
            item_ids = list(sale.items.values_list('id', flat=True))
            movements = StockMovement.objects.filter(
                reference_number__in=[f"SALE_ITEM_{item_id}" for item_id in item_ids]
            )
            movements_count = movements.count()
            movements.delete()
            
            if movements_count > 0:
                logger.info(f"✅ تم حذف {movements_count} حركة مخزون للفاتورة: {sale.number}")
            
            # 3. حذف الفاتورة (سيقوم الـ cascade بحذف الدفعات التلقائية المربوطة بها)
            sale_number = sale.number
            sale.delete()
            logger.info(f"✅ تم حذف الفاتورة بنجاح: {sale_number}")

            # 4. إعادة حساب رصيد العميل بعد حذف الفاتورة والدفعات المرتبطة
            if customer:
                from sale.signals import recalculate_customer_balance
                recalculate_customer_balance(customer)
                logger.info(f"✅ تم إعادة حساب رصيد العميل: {customer.name}")
            
        except Exception as e:
            logger.error(f"❌ خطأ في حذف الفاتورة {sale.number}: {str(e)}")
            raise

    @staticmethod
    def get_sale_statistics(sale, items=None, returns=None):
        """
        الحصول على إحصائيات الفاتورة بأسلوب عالي الأداء يعتمد على القوائم المسحوبة بالذاكرة إن وُجدت
        """
        if items is not None:
            items_count = len(items)
        else:
            items_count = sale.items.count()

        if returns is not None:
            confirmed_returns = [r for r in returns if getattr(r, 'status', None) == 'confirmed']
            returns_count = len(confirmed_returns)
        else:
            returns_count = sale.returns.filter(status='confirmed').count()

        return {
            'total': sale.total,
            'amount_paid': sale.amount_paid,
            'amount_due': sale.amount_due,
            'is_fully_paid': sale.is_fully_paid,
            'payment_status': sale.get_payment_status_display(),
            'items_count': items_count,
            'returns_count': returns_count,
            'is_returned': sale.is_returned,
            'return_status': sale.return_status,
        }

    @staticmethod
    def parse_custom_fields(raw_data):
        """
        فك وتسطيح الحقول الإضافية بأمان تام (Defensive JSON Parsing)
        """
        import json
        if not raw_data:
            return []
        
        if isinstance(raw_data, list):
            data_list = raw_data
        elif isinstance(raw_data, str):
            try:
                data_list = json.loads(raw_data)
                if not isinstance(data_list, list):
                    data_list = []
            except (json.JSONDecodeError, TypeError):
                data_list = []
        else:
            data_list = []

        cleaned = []
        for item in data_list:
            if isinstance(item, dict):
                key = str(item.get('key', '')).strip()
                name = str(item.get('name', '')).strip()
                name_en = str(item.get('name_en', '') if item.get('name_en') else '').strip()
                val = str(item.get('value', '') if item.get('value') is not None else '').strip()
                if key and name:
                    cleaned.append({
                        'key': key,
                        'name': name,
                        'name_en': name_en,
                        'value': val,
                        'show_in_header': bool(item.get('show_in_header', False)),
                        'show_on_print': bool(item.get('show_on_print', True)),
                        'show_on_thermal': bool(item.get('show_on_thermal', False))
                    })
        return cleaned

    @staticmethod
    def smart_merge_custom_fields(module, existing_fields):
        """
        دمج الحقول المخزنة سابقاً مع التعاريف النشطة في الإعدادات باستخدام Caching عالي الأداء
        """
        from django.core.cache import cache
        from django.conf import settings

        client_name = getattr(settings, 'CLIENT_NAME', 'mwheba')
        cache_key = f"custom_field_defs_{module}_{client_name}"
        active_defs = cache.get(cache_key)

        if active_defs is None:
            from sale.models import CustomFieldDefinition
            active_defs = list(CustomFieldDefinition.objects.filter(
                is_active=True,
                module__in=[module, 'both']
            ).order_by('sort_order', 'id'))
            cache.set(cache_key, active_defs, timeout=300)

        existing_list = SaleService.parse_custom_fields(existing_fields)
        existing_keys = {f['key']: f for f in existing_list}

        merged = []
        for defn in active_defs:
            if defn.key in existing_keys:
                field_data = dict(existing_keys[defn.key])
                field_data['name'] = defn.name  # تحديث الاسم العربي المعروض إذا تغير في الإعدادات
                field_data['name_en'] = defn.name_en or ''
                field_data['field_type'] = defn.field_type
                field_data['select_options'] = defn.get_options_list()
                field_data['is_required'] = defn.is_required
                field_data['show_in_header'] = defn.show_in_header
                merged.append(field_data)
            else:
                merged.append({
                    'key': defn.key,
                    'name': defn.name,
                    'name_en': defn.name_en or '',
                    'value': '',
                    'field_type': defn.field_type,
                    'select_options': defn.get_options_list(),
                    'is_required': defn.is_required,
                    'show_in_header': defn.show_in_header,
                    'show_on_print': defn.show_on_print,
                    'show_on_thermal': defn.show_on_thermal
                })
        
        # إضافة أي حقول قديمة مخزنة لم تعد نشطة في التعاريف
        active_keys = {d.key for d in active_defs}
        for old_field in existing_list:
            if old_field['key'] not in active_keys:
                merged.append(old_field)
                
        return merged
