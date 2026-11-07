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
            from financial.models import ChartOfAccounts, AccountType
            
            # حساب قيمة الحركة بناءً على التكلفة الفعلية للحركة (أو سعر التكلفة كبديل)
            if stock_movement.unit_cost and stock_movement.unit_cost > Decimal("0"):
                cost = stock_movement.unit_cost
            else:
                cost = stock_movement.product.cost_price or Decimal("0")
            amount = (cost * Decimal(str(stock_movement.quantity))).quantize(Decimal("0.01"))
            
            if amount == 0:
                return None  # لا نُنشئ قيد لحركات بدون قيمة

            # تحديد المستخدم أولاً لاستخدامه في إنشاء الحسابات إن لزم
            if user is None:
                user = stock_movement.created_by
            
            # فحص طبيعة الحركة: هل تخص أعمال تشطيبات ومقاولات أم مخزون تجاري عام
            is_finishing = (
                (stock_movement.reference_number and any(stock_movement.reference_number.startswith(p) for p in ['REQ-MAT-', 'RET-MAT-', 'FIN-']))
                or (stock_movement.document_number and 'FIN' in str(stock_movement.document_number))
                or (stock_movement.notes and 'تشطيب' in str(stock_movement.notes))
            )

            # 1. حساب المخزون (أصل متداول ASSET)
            inventory_account = (
                ChartOfAccounts.objects.filter(code="1030").first()
                or ChartOfAccounts.objects.filter(code="11410").first()
            )
            if not inventory_account:
                asset_type, _ = AccountType.objects.get_or_create(
                    code="ASSET", defaults={'name': 'ASSET', 'name_en': 'ASSET', 'is_active': True}
                )
                inventory_account, _ = ChartOfAccounts.objects.get_or_create(
                    code="11410" if is_finishing else "1030",
                    defaults={
                        'name': 'مخزون خامات ومواد تشطيب' if is_finishing else 'مخزون البضاعة',
                        'account_type': asset_type,
                        'is_active': True,
                        'created_by': user
                    }
                )

            # 2. حساب الطرف المقابل (أعمال تشطيبات تحت التنفيذ 12105 كأصل ASSET، أو تكلفة البضاعة 5010 كمصروف EXPENSE)
            if is_finishing:
                cogs_account = ChartOfAccounts.objects.filter(code="12105").first()
                if not cogs_account:
                    asset_type, _ = AccountType.objects.get_or_create(
                        code="ASSET", defaults={'name': 'ASSET', 'name_en': 'ASSET', 'is_active': True}
                    )
                    cogs_account, _ = ChartOfAccounts.objects.get_or_create(
                        code="12105",
                        defaults={
                            'name': 'أعمال تشطيبات تحت التنفيذ',
                            'account_type': asset_type,
                            'is_active': True,
                            'created_by': user
                        }
                    )
            else:
                cogs_account = (
                    ChartOfAccounts.objects.filter(code="5010").first()
                    or ChartOfAccounts.objects.filter(code="12105").first()
                )
                if not cogs_account:
                    expense_type, _ = AccountType.objects.get_or_create(
                        code="EXPENSE", defaults={'name': 'EXPENSE', 'name_en': 'EXPENSE', 'is_active': True}
                    )
                    cogs_account, _ = ChartOfAccounts.objects.get_or_create(
                        code="5010",
                        defaults={
                            'name': 'تكلفة البضاعة المباعة',
                            'account_type': expense_type,
                            'is_active': True,
                            'created_by': user
                        }
                    )
            
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
            elif stock_movement.movement_type == "return_in":
                # مرتجع وارد: مدين المخزون / دائن تكلفة البضاعة (عكس الصادر تماماً بنفس الحسابات)
                lines = [
                    JournalEntryLineData(
                        account_code=inventory_account.code,
                        debit=amount,
                        credit=Decimal("0"),
                        description=f"مرتجع مخزون - {stock_movement.product.name}"
                    ),
                    JournalEntryLineData(
                        account_code=cogs_account.code,
                        debit=Decimal("0"),
                        credit=amount,
                        description=f"عكس تكلفة صرف مخزون - {stock_movement.product.name}"
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
