"""
إشارات ربط المخزون بالمحاسبة
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal
from datetime import date

from .models import StockMovement
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from financial.services.journal_service import JournalEntryService

import logging
logger = logging.getLogger(__name__)


class StockAccountingService:
    """خدمة ربط المخزون بالمحاسبة"""
    
    @staticmethod
    def get_inventory_account():
        """الحصول على حساب المخزون"""
        try:
            return ChartOfAccounts.objects.get(code='1301', is_active=True)
        except ChartOfAccounts.DoesNotExist:
            logger.error("حساب المخزون (1301) غير موجود")
            return None
    
    @staticmethod
    def get_cogs_account():
        """الحصول على حساب تكلفة البضاعة المباعة"""
        try:
            return ChartOfAccounts.objects.get(code='5001', is_active=True)
        except ChartOfAccounts.DoesNotExist:
            logger.error("حساب تكلفة البضاعة المباعة (5001) غير موجود")
            return None
    
    @staticmethod
    def get_purchase_account():
        """الحصول على حساب المشتريات"""
        try:
            return ChartOfAccounts.objects.get(code='5101', is_active=True)
        except ChartOfAccounts.DoesNotExist:
            # إنشاء الحساب إذا لم يكن موجود
            try:
                from financial.models.chart_of_accounts import AccountType
                expense_type = AccountType.objects.get(code='5')
                account = ChartOfAccounts.objects.create(
                    code='5101',
                    name='المشتريات',
                    account_type=expense_type,
                    is_active=True,
                    is_system_account=True
                )
                logger.info(f"تم إنشاء حساب المشتريات: {account}")
                return account
            except Exception as e:
                logger.error(f"فشل في إنشاء حساب المشتريات: {str(e)}")
                return None
    
    @staticmethod
    def create_inventory_journal_entry(stock_movement):
        """إنشاء قيد محاسبي لحركة المخزون"""
        try:
            inventory_account = StockAccountingService.get_inventory_account()
            if not inventory_account:
                return None
            
            # حساب القيمة الإجمالية
            unit_cost = getattr(stock_movement.product, 'cost_price', Decimal('0'))
            if unit_cost <= 0:
                unit_cost = getattr(stock_movement.product, 'sale_price', Decimal('0')) * Decimal('0.7')  # تقدير 70% من سعر البيع
            
            total_value = unit_cost * Decimal(str(stock_movement.quantity))
            
            if total_value <= 0:
                logger.warning(f"قيمة حركة المخزون صفر أو سالبة: {stock_movement}")
                return None
            
            # إنشاء القيد المحاسبي
            journal_service = JournalEntryService()
            
            # تحديد نوع القيد والحسابات حسب نوع الحركة
            if stock_movement.movement_type == 'in':
                # حركة وارد - زيادة المخزون
                if stock_movement.document_type == 'purchase':
                    # مشتريات: مدين المخزون، دائن المشتريات
                    purchase_account = StockAccountingService.get_purchase_account()
                    if not purchase_account:
                        return None
                    
                    entry_data = {
                        'date': stock_movement.created_at.date(),
                        'description': f'مشتريات - {stock_movement.product.name} - {stock_movement.reference_number}',
                        'reference': stock_movement.reference_number,
                        'lines': [
                            {
                                'account': inventory_account,
                                'debit': total_value,
                                'credit': Decimal('0'),
                                'description': f'زيادة مخزون - {stock_movement.product.name}'
                            },
                            {
                                'account': purchase_account,
                                'debit': Decimal('0'),
                                'credit': total_value,
                                'description': f'مشتريات - {stock_movement.product.name}'
                            }
                        ]
                    }
                else:
                    # حركة وارد أخرى (تسوية، إرجاع، إلخ)
                    entry_data = {
                        'date': stock_movement.created_at.date(),
                        'description': f'زيادة مخزون - {stock_movement.product.name} - {stock_movement.reference_number}',
                        'reference': stock_movement.reference_number,
                        'lines': [
                            {
                                'account': inventory_account,
                                'debit': total_value,
                                'credit': Decimal('0'),
                                'description': f'زيادة مخزون - {stock_movement.product.name}'
                            }
                        ]
                    }
            
            elif stock_movement.movement_type == 'out':
                # حركة صادر - نقص المخزون
                if stock_movement.document_type == 'sale':
                    # مبيعات: دائن المخزون، مدين تكلفة البضاعة المباعة
                    cogs_account = StockAccountingService.get_cogs_account()
                    if not cogs_account:
                        return None
                    
                    entry_data = {
                        'date': stock_movement.created_at.date(),
                        'description': f'مبيعات - {stock_movement.product.name} - {stock_movement.reference_number}',
                        'reference': stock_movement.reference_number,
                        'lines': [
                            {
                                'account': cogs_account,
                                'debit': total_value,
                                'credit': Decimal('0'),
                                'description': f'تكلفة البضاعة المباعة - {stock_movement.product.name}'
                            },
                            {
                                'account': inventory_account,
                                'debit': Decimal('0'),
                                'credit': total_value,
                                'description': f'نقص مخزون - {stock_movement.product.name}'
                            }
                        ]
                    }
                else:
                    # حركة صادر أخرى
                    entry_data = {
                        'date': stock_movement.created_at.date(),
                        'description': f'نقص مخزون - {stock_movement.product.name} - {stock_movement.reference_number}',
                        'reference': stock_movement.reference_number,
                        'lines': [
                            {
                                'account': inventory_account,
                                'debit': Decimal('0'),
                                'credit': total_value,
                                'description': f'نقص مخزون - {stock_movement.product.name}'
                            }
                        ]
                    }
            
            elif stock_movement.movement_type == 'adjustment':
                # تسوية المخزون
                entry_data = {
                    'date': stock_movement.created_at.date(),
                    'description': f'تسوية مخزون - {stock_movement.product.name} - {stock_movement.reference_number}',
                    'reference': stock_movement.reference_number,
                    'lines': [
                        {
                            'account': inventory_account,
                            'debit': total_value if total_value > 0 else Decimal('0'),
                            'credit': abs(total_value) if total_value < 0 else Decimal('0'),
                            'description': f'تسوية مخزون - {stock_movement.product.name}'
                        }
                    ]
                }
            
            else:
                # حركات أخرى (تحويل، إلخ) - لا تحتاج قيود محاسبية
                return None
            
            # إنشاء القيد
            journal_entry = journal_service.create_entry_with_lines_data(entry_data)
            
            # ربط القيد بحركة المخزون
            stock_movement.journal_entry = journal_entry
            stock_movement.save(update_fields=['journal_entry'])
            
            logger.info(f"تم إنشاء قيد محاسبي لحركة المخزون: {journal_entry.reference}")
            return journal_entry
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد محاسبي لحركة المخزون: {str(e)}")
            return None


@receiver(post_save, sender=StockMovement)
def create_accounting_entry_for_stock_movement(sender, instance, created, **kwargs):
    """إنشاء قيد محاسبي عند إنشاء حركة مخزون"""
    if created and not getattr(instance, '_skip_accounting', False):
        # تجنب إنشاء قيود محاسبية متكررة
        if hasattr(instance, 'journal_entry') and instance.journal_entry:
            return
        
        try:
            with transaction.atomic():
                journal_entry = StockAccountingService.create_inventory_journal_entry(instance)
                if journal_entry:
                    logger.info(f"تم إنشاء قيد محاسبي لحركة المخزون: {instance.reference_number}")
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد محاسبي لحركة المخزون {instance.reference_number}: {str(e)}")


@receiver(post_delete, sender=StockMovement)
def delete_accounting_entry_for_stock_movement(sender, instance, **kwargs):
    """حذف القيد المحاسبي عند حذف حركة المخزون"""
    try:
        if hasattr(instance, 'journal_entry') and instance.journal_entry:
            journal_entry = instance.journal_entry
            journal_entry.delete()
            logger.info(f"تم حذف القيد المحاسبي لحركة المخزون: {instance.reference_number}")
    
    except Exception as e:
        logger.error(f"خطأ في حذف القيد المحاسبي لحركة المخزون {instance.reference_number}: {str(e)}")
