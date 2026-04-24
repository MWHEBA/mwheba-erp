"""
Bank Reconciliation Service
خدمة التسوية البنكية
"""
from decimal import Decimal
from django.db import transaction
from typing import Optional


class BankReconciliationService:
    """خدمة إنشاء القيود المحاسبية للتسوية البنكية"""
    
    @staticmethod
    @transaction.atomic
    def create_reconciliation_entry(reconciliation, user=None):
        """
        إنشاء قيد محاسبي للتسوية البنكية عبر AccountingGateway
        
        Args:
            reconciliation: BankReconciliation instance
            user: User creating the entry
            
        Returns:
            JournalEntry or None
        """
        try:
            from governance.services import AccountingGateway, JournalEntryLineData
            from financial.models import ChartOfAccounts
            
            if reconciliation.difference == 0:
                return None  # لا حاجة لقيد إذا لم يكن هناك فرق
            
            # الحصول على حساب الفروقات
            differences_account = ChartOfAccounts.objects.filter(
                code='59000',  # أرباح وخسائر متنوعة
                is_active=True
            ).first()
            
            if not differences_account:
                import logging
                logger = logging.getLogger(__name__)
                logger.error("Differences account (59000) not found")
                return None
            
            # إنشاء القيد
            gateway = AccountingGateway()
            
            if reconciliation.difference > 0:
                # رصيد البنك أكبر - مدين الحساب البنكي / دائن الفروقات
                lines = [
                    JournalEntryLineData(
                        account_code=reconciliation.account.code,
                        debit=reconciliation.difference,
                        credit=Decimal('0'),
                        description="تسوية بنكية - زيادة في الرصيد"
                    ),
                    JournalEntryLineData(
                        account_code=differences_account.code,
                        debit=Decimal('0'),
                        credit=reconciliation.difference,
                        description="فرق تسوية بنكية"
                    )
                ]
            else:
                # رصيد البنك أقل - دائن الحساب البنكي / مدين الفروقات
                diff_amount = abs(reconciliation.difference)
                lines = [
                    JournalEntryLineData(
                        account_code=differences_account.code,
                        debit=diff_amount,
                        credit=Decimal('0'),
                        description="فرق تسوية بنكية"
                    ),
                    JournalEntryLineData(
                        account_code=reconciliation.account.code,
                        debit=Decimal('0'),
                        credit=diff_amount,
                        description="تسوية بنكية - نقص في الرصيد"
                    )
                ]
            
            entry = gateway.create_journal_entry(
                source_module='financial',
                source_model='BankReconciliation',
                source_id=reconciliation.id,
                lines=lines,
                idempotency_key=f'JE:financial:BankReconciliation:{reconciliation.id}:create',
                user=user or reconciliation.created_by if hasattr(reconciliation, 'created_by') else None,
                date=reconciliation.reconciliation_date,
                description=f"تسوية بنكية - {reconciliation.account.name} - فرق {reconciliation.difference}",
                reference=f"RECON-{reconciliation.id}"
            )
            
            return entry
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"خطأ في إنشاء قيد التسوية البنكية: {e}")
            return None
