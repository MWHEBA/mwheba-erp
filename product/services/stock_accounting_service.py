"""
Stock Accounting Service
خدمة الربط المحاسبي لحركات المخزون
"""
from decimal import Decimal
from django.db import transaction
from django.contrib.auth.models import User
from typing import Optional


class StockAccountingService:
    """خدمة إنشاء القيود المحاسبية لحركات المخزون"""
    
    @staticmethod
    @transaction.atomic
    def create_stock_movement_entry(stock_movement, user: Optional[User] = None):
        """
        إنشاء قيد محاسبي لحركة المخزون عبر AccountingGateway
        
        Args:
            stock_movement: StockMovement instance
            user: User creating the entry (defaults to stock_movement.created_by)
            
        Returns:
            JournalEntry or None
        """
        try:
            from governance.services import AccountingGateway, JournalEntryLineData
            from financial.models import ChartOfAccounts
            
            # حساب قيمة الحركة
            cost = stock_movement.product.cost_price or Decimal("0")
            amount = cost * Decimal(str(stock_movement.quantity))
            
            if amount == 0:
                return None  # لا نُنشئ قيد لحركات بدون قيمة
            
            # الحصول على الحسابات
            try:
                inventory_account = ChartOfAccounts.objects.get(code="1030")  # مخزون البضاعة
                cogs_account = ChartOfAccounts.objects.get(code="5010")  # تكلفة البضاعة المباعة
            except ChartOfAccounts.DoesNotExist:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("حسابات المخزون غير موجودة - لم يتم إنشاء قيد")
                return None
            
            # تحديد المستخدم
            if user is None:
                user = stock_movement.created_by
            
            # إنشاء القيد حسب نوع الحركة
            gateway = AccountingGateway()
            lines = []
            
            if stock_movement.movement_type == "in":
                # وارد (شراء): مدين المخزون
                # ملاحظة: الطرف الدائن يجب أن يُنشأ من فاتورة الشراء
                lines = [
                    JournalEntryLineData(
                        account_code=inventory_account.code,
                        debit=amount,
                        credit=Decimal("0"),
                        description=f"وارد مخزون - {stock_movement.product.name}"
                    )
                ]
                # Skip creating entry with unbalanced lines
                return None
                
            elif stock_movement.movement_type == "out":
                # صادر (بيع): مدين تكلفة البضاعة / دائن المخزون
                lines = [
                    JournalEntryLineData(
                        account_code=cogs_account.code,
                        debit=amount,
                        credit=Decimal("0"),
                        description=f"تكلفة بيع - {stock_movement.product.name}"
                    ),
                    JournalEntryLineData(
                        account_code=inventory_account.code,
                        debit=Decimal("0"),
                        credit=amount,
                        description=f"صادر مخزون - {stock_movement.product.name}"
                    )
                ]
            else:
                # أنواع حركات أخرى - skip for now
                return None
            
            if not lines:
                return None
            
            # Get financial category from product if available
            financial_category = None
            financial_subcategory = None
            if hasattr(stock_movement.product, 'financial_category'):
                financial_category = stock_movement.product.financial_category
            if hasattr(stock_movement.product, 'financial_subcategory'):
                financial_subcategory = stock_movement.product.financial_subcategory
            
            # إنشاء القيد عبر Gateway
            entry = gateway.create_journal_entry(
                source_module='product',
                source_model='StockMovement',
                source_id=stock_movement.id,
                lines=lines,
                idempotency_key=f'JE:product:StockMovement:{stock_movement.id}:create',
                user=user,
                date=stock_movement.timestamp.date() if hasattr(stock_movement.timestamp, 'date') else stock_movement.timestamp,
                description=f"حركة مخزون - {stock_movement.product.name} - {stock_movement.get_movement_type_display()}",
                reference=stock_movement.number,
                financial_category=financial_category,
                financial_subcategory=financial_subcategory
            )
            
            return entry
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"خطأ في إنشاء القيد المحاسبي: {e}")
            return None
