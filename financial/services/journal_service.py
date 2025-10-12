"""
خدمات إدارة القيود المحاسبية
"""
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
from typing import List, Dict, Optional, Union
import logging

from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod
from ..models.chart_of_accounts import ChartOfAccounts

logger = logging.getLogger(__name__)


class JournalEntryService:
    """
    خدمة إدارة القيود المحاسبية
    """
    
    @staticmethod
    def create_entry(
        date = None,
        description: str = "",
        reference: str = None,
        reference_type: str = None,
        reference_id: int = None,
        entry_type: str = 'manual',
        lines_data: List[Dict] = None,
        user = None,
        auto_post: bool = False
    ) -> JournalEntry:
        """
        إنشاء قيد محاسبي جديد
        
        Args:
            date: تاريخ القيد
            description: وصف القيد
            reference: المرجع
            reference_type: نوع المرجع
            reference_id: معرف المرجع
            entry_type: نوع القيد
            lines_data: بيانات بنود القيد
            user: المستخدم
            auto_post: ترحيل تلقائي
            
        Returns:
            JournalEntry: القيد المنشأ
            
        Example:
            lines_data = [
                {
                    'account_code': '11011',
                    'debit': 1000,
                    'credit': 0,
                    'description': 'نقدية'
                },
                {
                    'account_code': '3001',
                    'debit': 0,
                    'credit': 1000,
                    'description': 'رأس المال'
                }
            ]
        """
        try:
            with transaction.atomic():
                # إنشاء القيد
                entry = JournalEntry.objects.create(
                    date=date or timezone.now().date(),
                    description=description,
                    reference=reference,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    entry_type=entry_type,
                    created_by=user
                )
                
                # إضافة البنود
                if lines_data:
                    for line_data in lines_data:
                        JournalEntryService._create_entry_line(entry, line_data)
                
                # التحقق من صحة القيد
                entry.validate_entry()
                
                # ترحيل تلقائي إذا طُلب
                if auto_post:
                    entry.post(user)
                
                logger.info(f"تم إنشاء القيد {entry.number} بنجاح")
                return entry
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء القيد: {str(e)}")
            raise ValidationError(f"فشل في إنشاء القيد: {str(e)}")
    
    @staticmethod
    def _create_entry_line(entry: JournalEntry, line_data: Dict) -> JournalEntryLine:
        """
        إنشاء بند قيد
        """
        # الحصول على الحساب
        account_code = line_data.get('account_code')
        account_id = line_data.get('account_id')
        
        if account_code:
            try:
                account = ChartOfAccounts.objects.get(code=account_code, is_active=True)
            except ChartOfAccounts.DoesNotExist:
                raise ValidationError(f"الحساب {account_code} غير موجود أو غير نشط")
        elif account_id:
            try:
                account = ChartOfAccounts.objects.get(id=account_id, is_active=True)
            except ChartOfAccounts.DoesNotExist:
                raise ValidationError(f"الحساب {account_id} غير موجود أو غير نشط")
        else:
            raise ValidationError("يجب تحديد كود الحساب أو معرف الحساب")
        
        # إنشاء البند
        line = JournalEntryLine.objects.create(
            journal_entry=entry,
            account=account,
            debit=Decimal(str(line_data.get('debit', 0))),
            credit=Decimal(str(line_data.get('credit', 0))),
            description=line_data.get('description', ''),
            cost_center=line_data.get('cost_center'),
            project=line_data.get('project')
        )
        
        return line
    
    @staticmethod
    def create_simple_entry(
        debit_account: Union[str, int, ChartOfAccounts],
        credit_account: Union[str, int, ChartOfAccounts],
        amount: Decimal,
        description: str,
        date = None,
        reference: str = None,
        user = None,
        auto_post: bool = True
    ) -> JournalEntry:
        """
        إنشاء قيد بسيط (مدين ودائن فقط)
        """
        # تحضير بيانات البنود
        lines_data = [
            {
                'account_code': debit_account if isinstance(debit_account, str) else None,
                'account_id': debit_account.id if isinstance(debit_account, ChartOfAccounts) else (debit_account if isinstance(debit_account, int) else None),
                'debit': amount,
                'credit': 0,
                'description': description
            },
            {
                'account_code': credit_account if isinstance(credit_account, str) else None,
                'account_id': credit_account.id if isinstance(credit_account, ChartOfAccounts) else (credit_account if isinstance(credit_account, int) else None),
                'debit': 0,
                'credit': amount,
                'description': description
            }
        ]
        
        return JournalEntryService.create_entry(
            date=date,
            description=description,
            reference=reference,
            lines_data=lines_data,
            user=user,
            auto_post=auto_post
        )
    
    @staticmethod
    def post_entry(entry_id: int, user = None) -> bool:
        """
        ترحيل قيد محاسبي
        """
        try:
            entry = JournalEntry.objects.get(id=entry_id)
            entry.post(user)
            logger.info(f"تم ترحيل القيد {entry.number} بنجاح")
            return True
        except JournalEntry.DoesNotExist:
            raise ValidationError("القيد غير موجود")
        except Exception as e:
            logger.error(f"خطأ في ترحيل القيد: {str(e)}")
            raise ValidationError(f"فشل في ترحيل القيد: {str(e)}")
    
    @staticmethod
    def reverse_entry(entry_id: int, user = None, description: str = None) -> JournalEntry:
        """
        عكس قيد محاسبي
        """
        try:
            entry = JournalEntry.objects.get(id=entry_id)
            reverse_entry = entry.reverse(user, description)
            logger.info(f"تم عكس القيد {entry.number} بالقيد {reverse_entry.number}")
            return reverse_entry
        except JournalEntry.DoesNotExist:
            raise ValidationError("القيد غير موجود")
        except Exception as e:
            logger.error(f"خطأ في عكس القيد: {str(e)}")
            raise ValidationError(f"فشل في عكس القيد: {str(e)}")
    
    @staticmethod
    def get_account_balance(
        account: Union[str, int, ChartOfAccounts],
        date_from: str = None,
        date_to: str = None
    ) -> Decimal:
        """
        حساب رصيد حساب معين
        """
        if isinstance(account, str):
            account_obj = ChartOfAccounts.objects.get(code=account)
        elif isinstance(account, int):
            account_obj = ChartOfAccounts.objects.get(id=account)
        else:
            account_obj = account
        
        return account_obj.get_balance(date_from, date_to)
    
    @staticmethod
    def validate_period_open(date: str) -> bool:
        """
        التحقق من أن الفترة المحاسبية مفتوحة للتاريخ المحدد
        """
        period = AccountingPeriod.get_period_for_date(date)
        if not period:
            raise ValidationError(f"لا توجد فترة محاسبية للتاريخ {date}")
        
        if not period.can_post_entries():
            raise ValidationError(f"الفترة المحاسبية {period.name} مغلقة")
        
        return True


class AutoJournalService:
    """
    خدمة إنشاء القيود التلقائية للمعاملات المالية
    """
    
    @staticmethod
    def create_sale_entry(sale_obj, user=None) -> JournalEntry:
        """
        إنشاء قيد لفاتورة مبيعات
        """
        # حسابات المبيعات الافتراضية
        cash_account = ChartOfAccounts.objects.filter(
            code__startswith='11011', is_active=True
        ).first()
        
        sales_account = ChartOfAccounts.objects.filter(
            code__startswith='4001', is_active=True
        ).first()
        
        if not cash_account or not sales_account:
            raise ValidationError("حسابات المبيعات الافتراضية غير موجودة")
        
        # إنشاء القيد
        return JournalEntryService.create_simple_entry(
            debit_account=cash_account,
            credit_account=sales_account,
            amount=sale_obj.total,
            description=f"فاتورة مبيعات رقم {sale_obj.number}",
            date=sale_obj.date,
            reference=f"SALE-{sale_obj.number}",
            user=user
        )
    
    @staticmethod
    def create_purchase_entry(purchase_obj, user=None) -> JournalEntry:
        """
        إنشاء قيد لفاتورة مشتريات
        """
        # حسابات المشتريات الافتراضية
        purchases_account = ChartOfAccounts.objects.filter(
            code__startswith='5001', is_active=True
        ).first()
        
        cash_account = ChartOfAccounts.objects.filter(
            code__startswith='11011', is_active=True
        ).first()
        
        if not purchases_account or not cash_account:
            raise ValidationError("حسابات المشتريات الافتراضية غير موجودة")
        
        # إنشاء القيد
        return JournalEntryService.create_simple_entry(
            debit_account=purchases_account,
            credit_account=cash_account,
            amount=purchase_obj.total,
            description=f"فاتورة مشتريات رقم {purchase_obj.number}",
            date=purchase_obj.date,
            reference=f"PURCHASE-{purchase_obj.number}",
            user=user
        )
    
    @staticmethod
    def create_payment_entry(payment_obj, payment_type='customer', user=None) -> JournalEntry:
        """
        إنشاء قيد لمدفوعات العملاء أو الموردين
        """
        cash_account = ChartOfAccounts.objects.filter(
            code__startswith='11011', is_active=True
        ).first()
        
        if payment_type == 'customer':
            # دفعة من عميل
            receivables_account = ChartOfAccounts.objects.filter(
                code__startswith='11030', is_active=True
            ).first()
            
            if not receivables_account:
                raise ValidationError("حساب العملاء غير موجود")
            
            return JournalEntryService.create_simple_entry(
                debit_account=cash_account,
                credit_account=receivables_account,
                amount=payment_obj.amount,
                description=f"دفعة من العميل {payment_obj.customer.name}",
                date=payment_obj.payment_date,
                reference=f"CUST-PAY-{payment_obj.id}",
                user=user
            )
        
        elif payment_type == 'supplier':
            # دفعة لمورد
            payables_account = ChartOfAccounts.objects.filter(
                code__startswith='21010', is_active=True
            ).first()
            
            if not payables_account:
                raise ValidationError("حساب الموردين غير موجود")
            
            return JournalEntryService.create_simple_entry(
                debit_account=payables_account,
                credit_account=cash_account,
                amount=payment_obj.amount,
                description=f"دفعة للمورد {payment_obj.supplier.name}",
                date=payment_obj.payment_date,
                reference=f"SUPP-PAY-{payment_obj.id}",
                user=user
            )
