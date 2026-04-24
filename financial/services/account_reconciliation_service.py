"""
Account Reconciliation Service
خدمة تسوية الحسابات
"""
from decimal import Decimal
from django.db import transaction
from typing import Optional


class AccountReconciliationService:
    """خدمة إنشاء القيود المحاسبية لتسوية الحسابات"""
    
    @staticmethod
    @transaction.atomic
    def create_reconciliation_entry(account, difference, reconciliation_date, user=None):
        """
        إنشاء قيد محاسبي لتسوية حساب عبر AccountingGateway
        
        Args:
            account: ChartOfAccounts instance
            difference: Decimal - الفرق في الرصيد
            reconciliation_date: date - تاريخ التسوية
            user: User creating the entry
            
        Returns:
            JournalEntry or None
        """
        try:
            from governance.services import AccountingGateway, JournalEntryLineData
            from financial.models import ChartOfAccounts
            
            if difference == 0:
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
            
            if difference > 0:
                # زيادة في الرصيد - مدين الحساب / دائن الفروقات
                lines = [
                    JournalEntryLineData(
                        account_code=account.code,
                        debit=difference,
                        credit=Decimal('0'),
                        description=f"تسوية حساب - زيادة في الرصيد"
                    ),
                    JournalEntryLineData(
                        account_code=differences_account.code,
                        debit=Decimal('0'),
                        credit=difference,
                        description=f"فرق تسوية - {account.name}"
                    )
                ]
            else:
                # نقص في الرصيد - دائن الحساب / مدين الفروقات
                diff_amount = abs(difference)
                lines = [
                    JournalEntryLineData(
                        account_code=differences_account.code,
                        debit=diff_amount,
                        credit=Decimal('0'),
                        description=f"فرق تسوية - {account.name}"
                    ),
                    JournalEntryLineData(
                        account_code=account.code,
                        debit=Decimal('0'),
                        credit=diff_amount,
                        description=f"تسوية حساب - نقص في الرصيد"
                    )
                ]
            
            entry = gateway.create_journal_entry(
                source_module='financial',
                source_model='ChartOfAccounts',
                source_id=account.id,
                lines=lines,
                idempotency_key=f'JE:financial:AccountReconciliation:{account.id}:{reconciliation_date}',
                user=user,
                date=reconciliation_date,
                description=f"تسوية حساب - {account.name} - فرق {difference}",
                reference=f"ACCT-RECON-{account.code}"
            )
            
            return entry
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"خطأ في إنشاء قيد تسوية الحساب: {e}")
            return None
