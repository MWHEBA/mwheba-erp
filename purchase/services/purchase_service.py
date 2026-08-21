"""
Purchase Service - خدمة موحدة لإدارة المشتريات

هذه الخدمة تستخدم:
- AccountingIntegrationService للقيود المحاسبية (Single Source of Truth)
- MovementService لحركات المخزون (مع الحوكمة الكاملة)

الهدف: ضمان الالتزام الكامل بمعايير الحوكمة والتدقيق
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
import logging

from purchase.models import Purchase, PurchaseItem, PurchasePayment, PurchaseReturn, PurchaseReturnItem
from governance.services.movement_service import MovementService
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData

User = get_user_model()
logger = logging.getLogger(__name__)


class PurchaseService:
    """
    خدمة موحدة لإدارة المشتريات مع الالتزام الكامل بالحوكمة
    """

    @staticmethod
    @transaction.atomic
    def create_purchase(data, user):
        """
        إنشاء فاتورة مشتريات جديدة مع القيود المحاسبية وحركات المخزون
        
        Args:
            data: dict يحتوي على بيانات الفاتورة والبنود
            user: المستخدم الذي ينشئ الفاتورة
            
        Returns:
            Purchase: الفاتورة المنشأة
            
        Raises:
            Exception: في حالة فشل أي عملية
        """
        try:
            # 1. إنشاء الفاتورة
            purchase = Purchase.objects.create(
                date=data.get('date', timezone.now().date()),
                supplier_id=data['supplier_id'],
                warehouse_id=data.get('warehouse_id'),
                payment_method=data.get('payment_method', 'credit'),
                subtotal=Decimal('0'),
                discount=Decimal(data.get('discount', 0)),
                tax=Decimal(data.get('tax', 0)),
                total=Decimal('0'),
                wht_active=data.get('wht_active', False),
                wht_rate=Decimal(str(data.get('wht_rate', 1.00))),
                wht_amount=Decimal(str(data.get('wht_amount', 0))),
                notes=data.get('notes', ''),
                status='confirmed',
                is_service=data.get('is_service', False),
                service_type=data.get('service_type'),
                financial_category_id=data.get('financial_category_id'),
                created_by=user
            )
            
            logger.info(f"✅ تم إنشاء فاتورة المشتريات: {purchase.number}")
            
            # 2. إضافة البنود
            items_data = data.get('items', [])
            for item_data in items_data:
                PurchaseService._add_purchase_item(purchase, item_data, user)
            
            # 3. حساب الإجماليات
            purchase.refresh_from_db()
            PurchaseService._calculate_totals(purchase)
            
            # 4. إنشاء القيد المحاسبي عبر AccountingGateway
            journal_entry = PurchaseService._create_purchase_journal_entry(purchase, user)
            if journal_entry:
                purchase.journal_entry = journal_entry
                purchase.save(update_fields=['journal_entry'])
                logger.info(f"✅ تم ربط القيد المحاسبي: {journal_entry.number} بالفاتورة: {purchase.number}")
            
            # 5. إنشاء حركات المخزون عبر MovementService (للمنتجات فقط)
            if not purchase.is_service:
                PurchaseService._create_stock_movements(purchase, user)

            # 6. تحديث رصيد المورد دفترياً والأستاذ المساعد
            if purchase.supplier:
                from financial.services.partner_subledger_service import PartnerSubledgerService
                from financial.services.partner_balance_service import PartnerBalanceService
                PartnerSubledgerService.record_purchase_bill(purchase, user)
                func_tot = getattr(purchase, "total_functional", None) or (purchase.total * (getattr(purchase, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000"))).quantize(Decimal("0.01"))
                PartnerBalanceService.apply_document_delta("supplier", purchase.supplier.id, func_tot, is_addition=True)

            # 7. توثيق التدقيق والحدث الضريبي (FIN-TAX-001)
            try:
                from financial.services.tax_service import TaxDeterminationService
                tax_lines = [{"line_id": item.id, "amount": item.total, "product_id": item.product_id} for item in purchase.items.all()]
                TaxDeterminationService.apply_tax_posting(
                    document_type="PurchaseInvoice",
                    document_id=purchase.id,
                    document_number=purchase.number,
                    supplier=purchase.supplier,
                    lines=tax_lines,
                    currency=getattr(purchase, "currency", "EGP") or "EGP",
                    exchange_rate=getattr(purchase, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000"),
                    user=user,
                    journal_entry=journal_entry
                )
            except Exception as tax_err:
                logger.warning(f"Could not apply tax posting for purchase invoice {purchase.number}: {tax_err}")
            
            logger.info(f"✅ تم إنشاء فاتورة المشتريات بنجاح: {purchase.number}")
            return purchase
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء فاتورة المشتريات: {str(e)}")
            raise

    @staticmethod
    def _add_purchase_item(purchase, item_data, user):
        """
        إضافة بند لفاتورة المشتريات
        """
        item = PurchaseItem.objects.create(
            purchase=purchase,
            product_id=item_data['product_id'],
            quantity=Decimal(item_data['quantity']),
            unit_price=Decimal(item_data['unit_price']),
            discount=Decimal(item_data.get('discount', 0)),
            total=Decimal(item_data['quantity']) * Decimal(item_data['unit_price']) - Decimal(item_data.get('discount', 0))
        )
        logger.info(f"✅ تم إضافة بند: {item.product.name} للفاتورة: {purchase.number}")
        return item

    @staticmethod
    def _calculate_totals(purchase):
        """
        حساب إجماليات الفاتورة
        """
        items = purchase.items.all()
        subtotal = sum(item.total for item in items)
        
        purchase.subtotal = subtotal
        purchase.total = subtotal - purchase.discount + purchase.tax
        purchase.save(update_fields=['subtotal', 'total'])
        
        logger.info(f"✅ تم حساب إجماليات الفاتورة: {purchase.number} - الإجمالي: {purchase.total}")

    @staticmethod
    def _create_purchase_journal_entry(purchase, user):
        """
        إنشاء القيد المحاسبي للفاتورة
        
        ملاحظة: هذه الدالة تستدعي AccountingIntegrationService (Single Source of Truth)
        """
        try:
            from financial.services.accounting_integration_service import AccountingIntegrationService
            
            journal_entry = AccountingIntegrationService.create_purchase_journal_entry(
                purchase=purchase,
                user=user
            )
            
            if journal_entry:
                logger.info(f"✅ تم إنشاء القيد المحاسبي: {journal_entry.number} للفاتورة: {purchase.number}")
            
            return journal_entry
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للفاتورة {purchase.number}: {str(e)}")
            raise

    @staticmethod
    def _create_stock_movements(purchase, user):
        """
        إنشاء حركات المخزون للفاتورة عبر MovementService
        """
        try:
            movement_service = MovementService()
            
            for item in purchase.items.all():
                # إنشاء الحركة عبر MovementService (مع الحوكمة الكاملة)
                movement = movement_service.process_movement(
                    product_id=item.product.id,
                    quantity_change=item.quantity,  # Positive for inbound
                    movement_type='in',
                    source_reference=f"PURCHASE-{purchase.number}-ITEM-{item.id}",
                    idempotency_key=f'purchase_{purchase.id}_item_{item.id}_movement',
                    user=user,
                    unit_cost=item.unit_price if (item.unit_price and item.unit_price > 0) else (item.product.cost_price if (item.product and item.product.cost_price and item.product.cost_price > 0) else Decimal('0.01')),
                    document_number=purchase.number,
                    notes=f'مشتريات - فاتورة رقم {purchase.number}',
                    movement_date=purchase.date,
                    warehouse_id=purchase.warehouse_id if purchase.warehouse_id else None
                )
                
                logger.info(f"✅ تم إنشاء حركة مخزون: {movement.id} للبند: {item.product.name}")
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء حركات المخزون للفاتورة {purchase.number}: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def process_payment(purchase, payment_data, user, auto_post=True):
        """
        معالجة دفعة على فاتورة مشتريات
        
        Args:
            purchase: الفاتورة
            payment_data: بيانات الدفعة
            user: المستخدم
            auto_post: هل يتم ترحيل الدفعة تلقائياً (default: True)
            
        Returns:
            PurchasePayment: الدفعة المنشأة
        """
        try:
            amount = Decimal(payment_data['amount'])
            pm = payment_data.get('payment_method', 'cash')

            # معالجة خاصة للخصم المباشر من الرصيد المسبق للمورد
            if pm == 'PREPAID_BALANCE':
                from supplier.services.supplier_allocation_service import SupplierAllocationService
                audit = SupplierAllocationService.allocate_advance_to_purchase_bill(
                    purchase=purchase,
                    amount_to_allocate=amount,
                    user=user
                )
                purchase.update_payment_status()
                prepaid_payment = purchase.payments.filter(source_type='PREPAID_BALANCE').order_by('-created_at').first()
                if prepaid_payment:
                    return prepaid_payment

            idem_key = payment_data.get('idempotency_key')
            if idem_key:
                existing = PurchasePayment.objects.filter(idempotency_key=idem_key).first()
                if existing:
                    logger.warning(f"⚠️ تم رصد طلب دفع مكرر بنفس المفتاح {idem_key} - إعادة الدفعة القائمة #{existing.id}")
                    return existing

            # 1. إنشاء الدفعة
            payment = PurchasePayment.objects.create(
                purchase=purchase,
                amount=amount,
                payment_method=pm,
                idempotency_key=idem_key,
                payment_date=payment_data.get('payment_date', timezone.now().date()),
                notes=payment_data.get('notes', ''),
                status='draft',
                created_by=user
            )
            
            logger.info(f"✅ تم إنشاء دفعة: {payment.id} للفاتورة: {purchase.number}")
            
            # 2. إنشاء القيد المحاسبي وترحيل الدفعة (إذا كان auto_post=True)
            if auto_post:
                journal_entry = PurchaseService._create_payment_journal_entry(payment, user)
                if journal_entry:
                    payment.financial_transaction = journal_entry
                    payment.status = 'posted'
                    payment.posted_at = timezone.now()
                    payment.posted_by = user
                    payment.save(update_fields=['financial_transaction', 'status', 'posted_at', 'posted_by'])
                    logger.info(f"✅ تم ترحيل الدفعة: {payment.id}")

                    # 3. تسجيل في الأستاذ المساعد
                    from financial.services.partner_subledger_service import PartnerSubledgerService
                    PartnerSubledgerService.record_payment_settlement(payment, "supplier", user)

                    # 4. تطبيق التعديل التفاضلي لرصيد المورد
                    if purchase.supplier:
                        from financial.services.partner_balance_service import PartnerBalanceService
                        PartnerBalanceService.apply_settlement_delta(
                            partner_type="supplier",
                            partner_id=purchase.supplier.id,
                            settled_invoice_amount=getattr(payment, "amount_settled_invoice_currency", payment.amount) or payment.amount,
                            invoice_rate=getattr(purchase, "exchange_rate", Decimal("1.000000")) or Decimal("1.000000"),
                            is_addition=False
                        )
                
                # 5. تحديث حالة الدفع للفاتورة
                purchase.update_payment_status()
            else:
                logger.info(f"ℹ️ الدفعة {payment.id} في حالة مسودة - تحتاج للترحيل اليدوي")
            
            return payment
            
        except Exception as e:
            logger.error(f"❌ خطأ في معالجة الدفعة للفاتورة {purchase.number}: {str(e)}")
            raise

    @staticmethod
    def _create_payment_journal_entry(payment, user):
        """
        إنشاء القيد المحاسبي للدفعة
        
        ملاحظة: هذه الدالة تستدعي AccountingIntegrationService (Single Source of Truth)
        """
        try:
            from financial.services.accounting_integration_service import AccountingIntegrationService
            
            journal_entry = AccountingIntegrationService.create_payment_journal_entry(
                payment=payment,
                payment_type='purchase_payment',
                user=user
            )
            
            if journal_entry:
                logger.info(f"✅ تم إنشاء القيد المحاسبي: {journal_entry.number} للدفعة: {payment.id}")
            else:
                logger.error(f"❌ Failed to create journal entry for payment {payment.id}")
            
            return journal_entry
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للدفعة {payment.id}: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def create_return(purchase, return_data, user):
        """
        مرتجع مشتريات
        
        Args:
            purchase: الفاتورة الأصلية
            return_data: بيانات المرتجع
            user: المستخدم
            
        Returns:
            PurchaseReturn: المرتجع المنشأ
        """
        try:
            # 1. إنشاء المرتجع
            # Support both 'date' and 'return_date' for backward compatibility
            return_date = return_data.get('date') or return_data.get('return_date', timezone.now().date())
            
            purchase_return = PurchaseReturn.objects.create(
                purchase=purchase,
                date=return_date,
                warehouse=purchase.warehouse,
                subtotal=Decimal('0'),
                discount=Decimal('0'),
                tax=Decimal('0'),
                total=Decimal('0'),
                status='confirmed',
                notes=return_data.get('notes', ''),
                created_by=user
            )
            
            logger.info(f"✅ تم إنشاء مرتجع: {purchase_return.number} للفاتورة: {purchase.number}")
            
            # 2. إضافة بنود المرتجع
            items_data = return_data.get('items', [])
            for item_data in items_data:
                PurchaseService._add_return_item(purchase_return, item_data, user)
            
            # 3. حساب الإجمالي
            purchase_return.refresh_from_db()
            total = sum(item.total for item in purchase_return.items.all())
            purchase_return.total = total
            purchase_return.subtotal = total
            purchase_return.save(update_fields=['total', 'subtotal'])
            
            # 4. إنشاء القيد المحاسبي للمرتجع
            journal_entry = PurchaseService._create_return_journal_entry(purchase_return, user)
            if journal_entry:
                # ملاحظة: PurchaseReturn model لا يحتوي على حقل journal_entry
                # يمكن إضافته لاحقاً إذا لزم الأمر
                logger.info(f"✅ تم إنشاء القيد المحاسبي: {journal_entry.number} للمرتجع: {purchase_return.number}")
            
            # 5. إنشاء حركات المخزون (إرجاع من المخزن) - للمنتجات فقط
            if not purchase.is_service:
                PurchaseService._create_return_stock_movements(purchase_return, user)
            
            # 6. تحديث حالة الدفع للفاتورة
            purchase.update_payment_status()
            
            logger.info(f"✅ تم إنشاء المرتجع بنجاح: {purchase_return.number}")
            return purchase_return
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء المرتجع للفاتورة {purchase.number}: {str(e)}")
            raise

    @staticmethod
    def _add_return_item(purchase_return, item_data, user):
        """
        إضافة بند للمرتجع
        """
        purchase_item = PurchaseItem.objects.get(id=item_data['purchase_item_id'])
        
        item = PurchaseReturnItem.objects.create(
            purchase_return=purchase_return,
            purchase_item=purchase_item,
            product=purchase_item.product,
            quantity=Decimal(item_data['quantity']),
            unit_price=Decimal(item_data['unit_price']),
            discount=Decimal(item_data.get('discount', 0)),
            total=Decimal(item_data['quantity']) * Decimal(item_data['unit_price']) - Decimal(item_data.get('discount', 0)),
            reason=item_data.get('reason', 'مرتجع')
        )
        logger.info(f"✅ تم إضافة بند مرتجع: {item.product.name}")
        return item

    @staticmethod
    def _create_return_journal_entry(purchase_return, user):
        """
        إنشاء القيد المحاسبي للمرتجع (عكس قيد المشتريات)
        """
        try:
            purchase = purchase_return.purchase
            
            # تحديد حساب المدين حسب طريقة الدفع الأصلية
            payment_method = purchase.payment_method
            
            if payment_method == 'cash' or payment_method == '10100':
                debit_account_code = '10100'
            elif payment_method == 'bank_transfer' or payment_method == '10200':
                debit_account_code = '10200'
            elif payment_method and payment_method.isdigit():
                debit_account_code = payment_method
            else:
                # حساب المورد
                if not purchase.supplier.financial_account:
                    try:
                        from supplier.services.supplier_service import SupplierService
                        supplier_service = SupplierService()
                        supplier_service.create_financial_account_for_supplier(purchase.supplier, user)
                        purchase.supplier.refresh_from_db()
                    except Exception as e:
                        logger.warning(f"فشل إنشاء حساب مالي للمورد {purchase.supplier.name}: {str(e)}")
                
                if purchase.supplier.financial_account:
                    debit_account_code = purchase.supplier.financial_account.code
                else:
                    debit_account_code = '20100'  # حساب الموردين الرئيسي
                    logger.warning(f"استخدام حساب الموردين الرئيسي للمورد {purchase.supplier.name}")
            
            # تحديد حساب الدائن حسب نوع الفاتورة
            if purchase.is_service:
                # للخدمات: استخدام حساب المصروفات
                if purchase.financial_category and purchase.financial_category.expense_account:
                    credit_account_code = purchase.financial_category.expense_account.code
                else:
                    credit_account_code = '50200'  # مصروفات عامة
            else:
                # للمنتجات: حساب المخزون
                credit_account_code = '10400'
            
            raw_rate = getattr(purchase, 'exchange_rate', Decimal('1.000000')) or Decimal('1.000000')
            inv_rate = Decimal(str(raw_rate))
            curr_code = purchase.currency.code if (purchase.currency and purchase.currency.code) else "EGP"
            func_total = (purchase_return.total * inv_rate).quantize(Decimal('0.01'))

            # إعداد بيانات القيد باستخدام JournalEntryLineData
            lines = [
                # مدين: الموردين/الخزينة/البنك (عكس)
                JournalEntryLineData(
                    account_code=debit_account_code,
                    debit=func_total,
                    credit=Decimal('0'),
                    description=f'مرتجع - فاتورة {purchase.number}',
                    currency=curr_code,
                    exchange_rate=inv_rate,
                    foreign_debit=purchase_return.total if curr_code != 'EGP' else Decimal('0.00'),
                    foreign_credit=Decimal('0.00')
                ),
                # دائن: المخزون/المصروفات (عكس)
                JournalEntryLineData(
                    account_code=credit_account_code,
                    debit=Decimal('0'),
                    credit=func_total,
                    description=f'مرتجع - فاتورة {purchase.number}',
                    currency=curr_code,
                    exchange_rate=inv_rate,
                    foreign_debit=Decimal('0.00'),
                    foreign_credit=purchase_return.total if curr_code != 'EGP' else Decimal('0.00')
                )
            ]
            
            # إنشاء القيد عبر AccountingGateway
            gateway = AccountingGateway()
            journal_entry = gateway.create_journal_entry(
                source_module='purchase',
                source_model='PurchaseReturn',
                source_id=purchase_return.id,
                lines=lines,
                idempotency_key=f'purchase_return_{purchase_return.id}_journal_entry',
                user=user,
                entry_type='purchase_return',
                description=f'مرتجع مشتريات رقم {purchase_return.number} - فاتورة {purchase.number}',
                reference=purchase_return.number,
                date=purchase_return.date
            )
            
            logger.info(f"✅ تم إنشاء القيد المحاسبي: {journal_entry.number} للمرتجع: {purchase_return.number}")
            return journal_entry
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء القيد المحاسبي للمرتجع {purchase_return.number}: {str(e)}")
            raise

    @staticmethod
    def _create_return_stock_movements(purchase_return, user):
        """
        إنشاء حركات المخزون للمرتجع (إخراج من المخزن)
        """
        try:
            movement_service = MovementService()
            
            for item in purchase_return.items.all():
                # إنشاء الحركة عبر MovementService (مع الحوكمة الكاملة)
                movement = movement_service.process_movement(
                    product_id=item.product.id,
                    quantity_change=-item.quantity,  # Negative for outbound
                    movement_type='out',
                    source_reference=f"RETURN-{purchase_return.number}-ITEM-{item.id}",
                    idempotency_key=f'purchase_return_{purchase_return.id}_item_{item.id}_movement',
                    user=user,
                    unit_cost=item.unit_price,
                    document_number=purchase_return.number,
                    notes=f'مرتجع مشتريات - فاتورة {purchase_return.purchase.number}',
                    movement_date=purchase_return.date,
                    warehouse_id=purchase_return.purchase.warehouse_id if purchase_return.purchase.warehouse_id else None
                )
                
                logger.info(f"✅ تم إنشاء حركة مخزون (إرجاع): {movement.id}")
                
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء حركات المخزون للمرتجع {purchase_return.number}: {str(e)}")
            raise

    @staticmethod
    @transaction.atomic
    def delete_purchase(purchase, user):
        """
        حذف فاتورة مشتريات مع التراجع عن جميع العمليات
        
        Args:
            purchase: الفاتورة المراد حذفها
            user: المستخدم
        """
        try:
            # 1. حذف القيد المحاسبي
            if purchase.journal_entry:
                try:
                    # فك قفل القيد وتغيير الحالة قبل الحذف
                    journal_entry = purchase.journal_entry
                    journal_entry._allow_lock_operation = True
                    from financial.models import JournalEntry, FinancialPostingReference
                    FinancialPostingReference.objects.filter(journal_entry_id=journal_entry.pk).delete()
                    JournalEntry.objects.filter(pk=journal_entry.pk).update(status='draft', is_locked=False)
                    journal_entry.status = 'draft'
                    journal_entry.delete()
                    logger.info(f"✅ تم حذف القيد المحاسبي للفاتورة: {purchase.number}")
                except Exception as e:
                    logger.warning(f"فشل حذف القيد المحاسبي: {str(e)}")
            
            # 2. حذف حركات المخزون (للمنتجات فقط)
            if not purchase.is_service:
                from product.models import StockMovement
                movements = StockMovement.objects.filter(
                    reference_number__contains=f'PURCHASE-{purchase.number}'
                )
                movements_count = movements.count()
                movements.delete()
                
                if movements_count > 0:
                    logger.info(f"✅ تم حذف {movements_count} حركة مخزون للفاتورة: {purchase.number}")
            
            # 3. تحديث رصيد المورد
            if purchase.payment_method == 'credit':
                supplier = purchase.supplier
                supplier.balance -= purchase.total
                supplier.save(update_fields=['balance'])
                logger.info(f"✅ تم تحديث رصيد المورد: {supplier.name}")
            
            # 4. حذف الفاتورة
            purchase_number = purchase.number
            purchase.delete()
            
            logger.info(f"✅ تم حذف الفاتورة بنجاح: {purchase_number}")
            
        except Exception as e:
            logger.error(f"❌ خطأ في حذف الفاتورة {purchase.number}: {str(e)}")
            raise

    @staticmethod
    def get_purchase_statistics(purchase):
        """
        الحصول على إحصائيات الفاتورة
        """
        return {
            'total': purchase.total,
            'amount_paid': purchase.amount_paid,
            'amount_due': purchase.amount_due,
            'is_fully_paid': purchase.is_fully_paid,
            'payment_status': purchase.get_payment_status_display(),
            'items_count': purchase.items.count(),
            'returns_count': purchase.returns.filter(status='confirmed').count(),
            'is_returned': purchase.is_returned,
            'return_status': purchase.return_status,
            'is_service': purchase.is_service,
            'service_type_display': purchase.service_type_display if purchase.is_service else None,
        }
