"""
إشارات ربط المخزون بالمحاسبة - Governed Signals (Phase 3.2)
Stock-Accounting Integration Signals - Low-Risk Signal Processing

Migration Status: Phase 3.2 - Low-Risk Signal Processing ✅
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import transaction
from decimal import Decimal
from datetime import date
import logging

from governance.signal_integration import governed_signal_handler, side_effect_handler
from governance.services.audit_service import AuditService
from governance.models import GovernanceContext

from .models import StockMovement
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import (
    JournalEntry,
    JournalEntryLine,
    AccountingPeriod,
)
from financial.services.journal_service import JournalEntryService

logger = logging.getLogger(__name__)


class StockAccountingService:
    """خدمة ربط المخزون بالمحاسبة"""

    @staticmethod
    def get_inventory_account():
        """الحصول على حساب المخزون - 10400 (من fixtures) أو 11051"""
        try:
            # محاولة الحصول على الحساب من fixtures أولاً
            return ChartOfAccounts.objects.get(code="10400", is_active=True)
        except ChartOfAccounts.DoesNotExist:
            try:
                # محاولة الحساب القديم
                return ChartOfAccounts.objects.get(code="11051", is_active=True)
            except ChartOfAccounts.DoesNotExist:
                logger.error("حساب مخزون البضاعة (10400 أو 11051) غير موجود")
                return None

    @staticmethod
    def get_cogs_account():
        """الحصول على حساب تكلفة البضاعة المباعة - 50100"""
        try:
            return ChartOfAccounts.objects.get(code="50100", is_active=True)
        except ChartOfAccounts.DoesNotExist:
            logger.error("حساب تكلفة البضاعة المباعة (50100) غير موجود")
            return None

    @staticmethod
    def get_purchase_account():
        """الحصول على حساب المشتريات - 5101 (إذا كان موجود)"""
        try:
            return ChartOfAccounts.objects.get(code="5101", is_active=True)
        except ChartOfAccounts.DoesNotExist:
            logger.warning("حساب المشتريات (5101) غير موجود")
            return None

    @staticmethod
    def create_inventory_journal_entry(stock_movement):
        """إنشاء قيد محاسبي لحركة المخزون"""
        try:
            inventory_account = StockAccountingService.get_inventory_account()
            if not inventory_account:
                return None

            # حساب القيمة الإجمالية
            unit_cost = getattr(stock_movement.product, "cost_price", Decimal("0"))
            if unit_cost <= 0:
                unit_cost = getattr(
                    stock_movement.product, "sale_price", Decimal("0")
                ) * Decimal(
                    "0.7"
                )  # تقدير 70% من سعر البيع

            total_value = unit_cost * Decimal(str(stock_movement.quantity))

            if total_value <= 0:
                logger.warning(f"قيمة حركة المخزون صفر أو سالبة: {stock_movement}")
                return None

            # إنشاء القيد المحاسبي
            journal_service = JournalEntryService()

            # تحديد نوع القيد والحسابات حسب نوع الحركة
            if stock_movement.movement_type == "in":
                # حركة وارد - زيادة المخزون
                if stock_movement.document_type == "purchase":
                    # مشتريات: مدين المخزون، دائن المشتريات
                    purchase_account = StockAccountingService.get_purchase_account()
                    if not purchase_account:
                        return None

                    entry_data = {
                        "date": stock_movement.timestamp.date(),
                        "description": f"مشتريات - {stock_movement.product.name} - {stock_movement.reference_number}",
                        "reference": stock_movement.reference_number,
                        "lines": [
                            {
                                "account": inventory_account,
                                "debit": total_value,
                                "credit": Decimal("0"),
                                "description": f"زيادة مخزون - {stock_movement.product.name}",
                            },
                            {
                                "account": purchase_account,
                                "debit": Decimal("0"),
                                "credit": total_value,
                                "description": f"مشتريات - {stock_movement.product.name}",
                            },
                        ],
                    }
                else:
                    # حركة وارد أخرى (تسوية، إرجاع، إلخ)
                    entry_data = {
                        "date": stock_movement.timestamp.date(),
                        "description": f"زيادة مخزون - {stock_movement.product.name} - {stock_movement.reference_number}",
                        "reference": stock_movement.reference_number,
                        "lines": [
                            {
                                "account": inventory_account,
                                "debit": total_value,
                                "credit": Decimal("0"),
                                "description": f"زيادة مخزون - {stock_movement.product.name}",
                            }
                        ],
                    }

            elif stock_movement.movement_type == "out":
                # حركة صادر - نقص المخزون
                if stock_movement.document_type == "sale":
                    # مبيعات: دائن المخزون، مدين تكلفة البضاعة المباعة
                    cogs_account = StockAccountingService.get_cogs_account()
                    if not cogs_account:
                        return None

                    entry_data = {
                        "date": stock_movement.timestamp.date(),
                        "description": f"مبيعات - {stock_movement.product.name} - {stock_movement.reference_number}",
                        "reference": stock_movement.reference_number,
                        "lines": [
                            {
                                "account": cogs_account,
                                "debit": total_value,
                                "credit": Decimal("0"),
                                "description": f"تكلفة البضاعة المباعة - {stock_movement.product.name}",
                            },
                            {
                                "account": inventory_account,
                                "debit": Decimal("0"),
                                "credit": total_value,
                                "description": f"نقص مخزون - {stock_movement.product.name}",
                            },
                        ],
                    }
                else:
                    # حركة صادر أخرى
                    entry_data = {
                        "date": stock_movement.timestamp.date(),
                        "description": f"نقص مخزون - {stock_movement.product.name} - {stock_movement.reference_number}",
                        "reference": stock_movement.reference_number,
                        "lines": [
                            {
                                "account": inventory_account,
                                "debit": Decimal("0"),
                                "credit": total_value,
                                "description": f"نقص مخزون - {stock_movement.product.name}",
                            }
                        ],
                    }

            elif stock_movement.movement_type == "adjustment":
                # تسوية المخزون
                entry_data = {
                    "date": stock_movement.timestamp.date(),
                    "description": f"تسوية مخزون - {stock_movement.product.name} - {stock_movement.reference_number}",
                    "reference": stock_movement.reference_number,
                    "lines": [
                        {
                            "account": inventory_account,
                            "debit": total_value if total_value > 0 else Decimal("0"),
                            "credit": abs(total_value)
                            if total_value < 0
                            else Decimal("0"),
                            "description": f"تسوية مخزون - {stock_movement.product.name}",
                        }
                    ],
                }

            else:
                # حركات أخرى (تحويل، إلخ) - لا تحتاج قيود محاسبية
                return None

            # إنشاء القيد
            journal_entry = journal_service.create_entry_with_lines_data(entry_data)

            # ربط القيد بحركة المخزون
            stock_movement.journal_entry = journal_entry
            stock_movement.save(update_fields=["journal_entry"])

            return journal_entry

        except Exception as e:
            logger.error(f"خطأ في إنشاء قيد محاسبي لحركة المخزون: {str(e)}")
            return None


@side_effect_handler(
    "stock_accounting_entry_creation",
    "Create accounting journal entry for stock movements"
)
@receiver(post_save, sender=StockMovement)
def create_accounting_entry_for_stock_movement(sender, instance, created, **kwargs):
    """
    إنشاء قيد محاسبي عند إنشاء حركة مخزون
    Governed side effect handler: Creates accounting journal entry for stock movements
    
    ⚠️ ملاحظة: تم تعطيل القيود المحاسبية للمشتريات - يتم إنشاؤها عبر AccountingIntegrationService
    """
    if not created or getattr(instance, "_skip_accounting", False):
        return
    
    # ✅ تخطي المشتريات - يتم إنشاء القيود عبر AccountingIntegrationService
    if instance.document_type == "purchase":
        logger.debug(f"Skipping accounting entry for purchase stock movement {instance.reference_number} - handled by AccountingIntegrationService")
        return
        
    # تجنب إنشاء قيود محاسبية متكررة
    if hasattr(instance, "journal_entry") and instance.journal_entry:
        logger.debug(f"Journal entry already exists for stock movement {instance.id}")
        return

    try:
        with transaction.atomic():
            journal_entry = StockAccountingService.create_inventory_journal_entry(
                instance
            )
            if journal_entry:
                # Audit journal entry creation
                AuditService.create_audit_record(
                    model_name='StockMovement',
                    object_id=instance.id,
                    operation='ACCOUNTING_JOURNAL_ENTRY_CREATED',
                    user=GovernanceContext.get_current_user(),
                    source_service='StockAccountingSignals',
                    additional_context={
                        'journal_entry_id': journal_entry.id,
                        'reference_number': instance.reference_number,
                        'movement_type': instance.movement_type,
                        'product_name': instance.product.name,
                        'amount': str(instance.quantity * instance.product.cost_price) if hasattr(instance.product, 'cost_price') else 'N/A'
                    }
                )
                
            else:
                logger.warning(f"Failed to create journal entry for stock movement {instance.reference_number}")

    except Exception as e:
        logger.error(f"Error creating accounting journal entry for stock movement {instance.reference_number}: {e}")
        
        # Audit error
        AuditService.create_audit_record(
            model_name='StockMovement',
            object_id=instance.id,
            operation='ACCOUNTING_JOURNAL_ENTRY_ERROR',
            user=GovernanceContext.get_current_user(),
            source_service='StockAccountingSignals',
            additional_context={
                'error': str(e),
                'reference_number': instance.reference_number,
                'movement_type': instance.movement_type
            }
        )


@side_effect_handler(
    "stock_accounting_entry_deletion",
    "Delete accounting journal entry when stock movement is deleted"
)
@receiver(post_delete, sender=StockMovement)
def delete_accounting_entry_for_stock_movement(sender, instance, **kwargs):
    """
    حذف القيد المحاسبي عند حذف حركة المخزون
    Governed side effect handler: Deletes accounting journal entry when stock movement is deleted
    """
    try:
        if hasattr(instance, "journal_entry") and instance.journal_entry:
            journal_entry = instance.journal_entry
            journal_entry_id = journal_entry.id
            journal_entry.delete()
            
            # Audit journal entry deletion
            AuditService.create_audit_record(
                model_name='StockMovement',
                object_id=instance.id,
                operation='ACCOUNTING_JOURNAL_ENTRY_DELETED',
                user=GovernanceContext.get_current_user(),
                source_service='StockAccountingSignals',
                additional_context={
                    'deleted_journal_entry_id': journal_entry_id,
                    'reference_number': instance.reference_number,
                    'movement_type': instance.movement_type,
                    'product_name': instance.product.name
                }
            )
            

    except Exception as e:
        logger.error(f"Error deleting accounting journal entry for stock movement {instance.reference_number}: {e}")
        
        # Audit error
        AuditService.create_audit_record(
            model_name='StockMovement',
            object_id=instance.id,
            operation='ACCOUNTING_JOURNAL_DELETION_ERROR',
            user=GovernanceContext.get_current_user(),
            source_service='StockAccountingSignals',
            additional_context={
                'error': str(e),
                'reference_number': instance.reference_number
            }
        )
