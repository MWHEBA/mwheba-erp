"""
خدمة إنشاء القيود المحاسبية للرسوم والمدفوعات
"""
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from decimal import Decimal
from typing import Optional
import logging

from ..models.chart_of_accounts import ChartOfAccounts
from ..models.journal_entry import JournalEntry, JournalEntryLine, AccountingPeriod

# Import AccountingGateway for unified journal entry creation
from governance.services import AccountingGateway, JournalEntryLineData

logger = logging.getLogger(__name__)
User = get_user_model()


class JournalEntryService:
    """
    خدمة إنشاء القيود المحاسبية للرسوم والمدفوعات
    """
    
    # أكواد الحسابات الأساسية للنظام (mapped to existing accounts in fixtures)
    SYSTEM_ACCOUNTS = {
        "tuition_revenue": "40100",      # إيرادات الرسوم الأساسية (pk 8)
        "other_revenue": "40400",        # إيرادات أخرى (pk 35)
        "parents_receivable": "10300",   # ذمم العملاء (pk 3)
        "cash": "10100",                 # الخزنة (pk 1)
        "bank": "10200",                 # البنك (pk 2)
    }
    
    def _get_system_accounts(self) -> dict:
        """الحصول على الحسابات الأساسية للنظام"""
        try:
            accounts = {}
            for account_key, code in self.SYSTEM_ACCOUNTS.items():
                account = ChartOfAccounts.objects.filter(
                    code=code, is_active=True
                ).first()
                if account:
                    accounts[account_key] = account
                else:
                    logger.warning(f"لا يمكن العثور على الحساب: {code}")
            
            return accounts if len(accounts) >= 4 else None
        except Exception as e:
            logger.error(f"خطأ في الحصول على حسابات النظام: {str(e)}")
            return None
    
    def _get_revenue_account_for_fee_type(self, fee_category: str, accounts: dict) -> ChartOfAccounts:
        """تحديد حساب الإيراد حسب نوع الرسوم"""
        revenue_mapping = {
            'tuition': 'tuition_revenue',
            'bus': 'bus_revenue',
            'summer': 'activity_revenue',
            'activity': 'activity_revenue',
            'application': 'application_revenue',
        }
        
        account_key = revenue_mapping.get(fee_category, 'other_revenue')
        return accounts.get(account_key, accounts.get('tuition_revenue'))
    
    def _get_receiving_account_for_payment_method(self, payment_method: str, accounts: dict) -> ChartOfAccounts:
        """تحديد حساب الاستلام حسب طريقة الدفع - النظام الجديد فقط"""
        # payment_method هو account code مباشرة (مثل 10100، 10200، 10500)
        try:
            account = ChartOfAccounts.objects.filter(
                code=payment_method,
                is_active=True
            ).first()
            
            if not account:
                raise ValueError(f"الحساب المحاسبي {payment_method} غير موجود أو غير نشط")
            
            return account
            
        except Exception as e:
            logger.error(f"فشل في الحصول على الحساب بالكود {payment_method}: {str(e)}")
            raise
    
    def _generate_journal_number(self, prefix: str, reference_id: int) -> str:
        """
        توليد رقم القيد مع دعم التسميات العربية الموحدة
        
        Args:
            prefix: بادئة القيد (مثل: تسليم-منتجات، رسوم-مكملة، رسوم-عميل)
            reference_id: معرف المرجع
            
        Returns:
            str: رقم القيد المُولد (مثل: تسليم-منتجات-0001)
        """
        # قاموس البادئات الإنجليزية (أرقام القيود يجب أن تكون بالإنجليزية فقط)
        prefix_mapping = {
            # البادئات العربية القديمة → البادئات الإنجليزية الجديدة
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
                    current_number = int(number_part)
                    if current_number > max_number:
                        max_number = current_number
            except (ValueError, IndexError):
                continue
        
        new_number = max_number + 1
        return f"{normalized_prefix}-{new_number:04d}"
    
    def _get_accounting_period(self, date) -> Optional[AccountingPeriod]:
        """الحصول على الفترة المحاسبية للتاريخ"""
        try:
            return AccountingPeriod.get_period_for_date(date)
        except Exception:
            return None
    
    @classmethod
    def create_simple_entry(
        cls,
        date,
        debit_account: str,
        credit_account: str,
        amount: Decimal,
        description: str = "",
        reference: str = "",
        user: Optional[User] = None,
        financial_category=None,
        financial_subcategory=None,
        entry_type: str = "manual"
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي بسيط (مدين واحد ودائن واحد)
        
        Args:
            date: تاريخ القيد
            debit_account: كود الحساب المدين
            credit_account: كود الحساب الدائن
            amount: المبلغ
            description: وصف القيد
            reference: مرجع القيد
            user: المستخدم المنشئ للقيد
            financial_category: التصنيف المالي الأساسي (اختياري)
            financial_subcategory: التصنيف الفرعي (اختياري)
            entry_type: نوع القيد (manual, cash_payment, cash_receipt, إلخ)
            
        Returns:
            JournalEntry: القيد المحاسبي المنشأ أو None في حالة الخطأ
        """
        try:
            with transaction.atomic():
                # الحصول على الحسابات
                debit_acc = ChartOfAccounts.objects.filter(
                    code=debit_account, is_active=True
                ).first()
                credit_acc = ChartOfAccounts.objects.filter(
                    code=credit_account, is_active=True
                ).first()
                
                if not debit_acc:
                    logger.error(f"لا يمكن العثور على الحساب المدين: {debit_account}")
                    return None
                    
                if not credit_acc:
                    logger.error(f"لا يمكن العثور على الحساب الدائن: {credit_account}")
                    return None
                
                # التعامل مع التصنيفات - لو تم تمرير FinancialSubcategory
                from financial.models import FinancialSubcategory
                if isinstance(financial_category, FinancialSubcategory):
                    # لو تم تمرير subcategory في مكان category، نصلحه
                    financial_subcategory = financial_category
                    financial_category = financial_subcategory.parent_category
                
                # Prepare journal entry lines
                lines = [
                    JournalEntryLineData(
                        account_code=debit_acc.code,
                        debit=amount,
                        credit=Decimal("0.00"),
                        description=description
                    ),
                    JournalEntryLineData(
                        account_code=credit_acc.code,
                        debit=Decimal("0.00"),
                        credit=amount,
                        description=description
                    )
                ]
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                
                # تحديد source_id و source_model الصحيح
                # لو في reference بيبدأ بـ ACT_EXP_ يبقى ده مصروف نشاط
                source_module_to_use = 'financial'
                source_model_to_use = 'ManualEntry'
                source_id_to_use = 0
                
                if reference and reference.startswith('ACT_EXP_'):
                    # استخراج الـ ID من الـ reference
                    try:
                        expense_id = int(reference.split('_')[-1])
                        source_module_to_use = 'activities'
                        source_model_to_use = 'ActivityExpense'
                        source_id_to_use = expense_id
                    except (ValueError, IndexError):
                        logger.warning(f"Could not parse expense_id from reference: {reference}")
                
                journal_entry = gateway.create_journal_entry(
                    source_module=source_module_to_use,
                    source_model=source_model_to_use,
                    source_id=source_id_to_use,
                    lines=lines,
                    idempotency_key=f"JE:{source_module_to_use}:{source_model_to_use}:{reference or timezone.now().timestamp()}:create",
                    user=user,
                    entry_type=entry_type,
                    description=description,
                    reference=reference,
                    date=date,
                    financial_category=financial_category,
                    financial_subcategory=financial_subcategory
                )
                
                if journal_entry:
                    pass
                else:
                    logger.error("فشل في إنشاء القيد المحاسبي")
                
                return journal_entry
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء القيد البسيط: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    @classmethod
    def create_compound_entry(
        cls,
        date,
        lines: list,
        description: str = "",
        reference: str = "",
        user: Optional[User] = None,
        financial_category=None
    ) -> Optional[JournalEntry]:
        """
        إنشاء قيد محاسبي مركب (متعدد الخطوط)
        
        Args:
            date: تاريخ القيد
            lines: قائمة بخطوط القيد [{'account': 'code', 'debit': amount, 'credit': amount, 'description': 'desc'}]
            description: وصف القيد
            reference: مرجع القيد
            user: المستخدم المنشئ للقيد
            financial_category: التصنيف المالي (اختياري)
            
        Returns:
            JournalEntry: القيد المحاسبي المنشأ أو None في حالة الخطأ
        """
        try:
            with transaction.atomic():
                # التحقق من توازن القيد
                total_debit = sum(Decimal(str(line.get('debit', 0))) for line in lines)
                total_credit = sum(Decimal(str(line.get('credit', 0))) for line in lines)
                
                if total_debit != total_credit:
                    logger.error(f"القيد غير متوازن: مدين {total_debit} != دائن {total_credit}")
                    return None
                
                # Prepare journal entry lines
                prepared_lines = []
                for line in lines:
                    account = ChartOfAccounts.objects.filter(
                        code=line['account'], is_active=True
                    ).first()
                    
                    if not account:
                        logger.error(f"لا يمكن العثور على الحساب: {line['account']}")
                        raise Exception(f"حساب غير موجود: {line['account']}")
                    
                    prepared_lines.append(
                        JournalEntryLineData(
                            account_code=account.code,
                            debit=Decimal(str(line.get('debit', 0))),
                            credit=Decimal(str(line.get('credit', 0))),
                            description=line.get('description', description)
                        )
                    )
                
                # Create journal entry via AccountingGateway
                gateway = AccountingGateway()
                journal_entry = gateway.create_journal_entry(
                    source_module='financial',
                    source_model='CompoundEntry',
                    source_id=0,
                    lines=prepared_lines,
                    idempotency_key=f"JE:financial:CompoundEntry:{reference or timezone.now().timestamp()}:create",
                    user=user,
                    entry_type='manual',
                    description=description,
                    reference=reference,
                    date=date,
                    financial_category=financial_category
                )
                
                return journal_entry
                
        except Exception as e:
            logger.error(f"خطأ في إنشاء القيد المركب: {str(e)}")
            return None
    
    @classmethod
    def post_entry(cls, journal_entry: JournalEntry) -> bool:
        """
        ترحيل القيد المحاسبي (تحديث أرصدة الحسابات)
        
        Args:
            journal_entry: القيد المراد ترحيله
            
        Returns:
            bool: True إذا تم الترحيل بنجاح، False في حالة الخطأ
        """
        try:
            with transaction.atomic():
                if journal_entry.status == 'posted':
                    return True
                
                # ترحيل خطوط القيد
                for line in journal_entry.lines.all():
                    account = line.account
                    
                    # تحديث رصيد الحساب
                    if line.debit > 0:
                        account.balance += line.debit
                    if line.credit > 0:
                        account.balance -= line.credit
                    
                    account.save()
                
                # تحديث حالة القيد
                journal_entry.status = 'posted'
                journal_entry.save()
                
                return True
                
        except Exception as e:
            logger.error(f"خطأ في ترحيل القيد: {str(e)}")
            return False
    
    @staticmethod
    def _generate_journal_number_static(prefix: str, reference_id: int) -> str:
        """نسخة ثابتة من توليد رقم القيد"""
        # البحث عن أعلى رقم للبادئة المحددة
        existing_entries = JournalEntry.objects.filter(
            number__startswith=f"{prefix}-"
        ).order_by('-id')
        
        max_number = 0
        for entry in existing_entries:
            try:
                # استخراج الرقم من نهاية اسم القيد
                parts = entry.number.split("-")
                if len(parts) >= 2:
                    number_part = parts[1]
                    current_number = int(number_part)
                    if current_number > max_number:
                        max_number = current_number
            except (ValueError, IndexError):
                continue
        
        new_number = max_number + 1
        return f"{prefix}-{new_number:04d}"
    
    @staticmethod
    def _get_accounting_period_static(date) -> Optional[AccountingPeriod]:
        """نسخة ثابتة من الحصول على الفترة المحاسبية"""
        try:
            return AccountingPeriod.get_period_for_date(date)
        except Exception:
            return None

    @classmethod
    def setup_system_accounts(cls) -> bool:
        """إعداد الحسابات الأساسية للنظام"""
        try:
            with transaction.atomic():
                accounts_created = 0
                
                # بيانات الحسابات المطلوبة
                system_accounts_data = {
                    "41020": {
                        "name": "إيرادات الرسوم الأساسية",
                        "name_en": "Core Fees Revenue",
                        "type": "revenue",
                        "description": "إيرادات من الرسوم الأساسية",
                    },
                    "41021": {
                        "name": "إيرادات رسوم النقل",
                        "name_en": "Transport Fees Revenue",
                        "type": "revenue",
                        "description": "إيرادات من رسوم النقل",
                    },
                    "41022": {
                        "name": "إيرادات الأنشطة",
                        "name_en": "Activities Revenue",
                        "type": "revenue",
                        "description": "إيرادات من الأنشطة والفعاليات",
                    },
                    "41023": {
                        "name": "إيرادات رسوم التقديم",
                        "name_en": "Application Fees Revenue",
                        "type": "revenue",
                        "description": "إيرادات من رسوم تقديم الطلبات",
                    },
                    "41029": {
                        "name": "إيرادات أخرى",
                        "name_en": "Other Revenue",
                        "type": "revenue",
                        "description": "إيرادات متنوعة أخرى",
                    },
                    "10301": {
                        "name": "ذمم العملاء",
                        "name_en": "Clients Receivable",
                        "type": "asset",
                        "description": "المبالغ المستحقة من العملاء",
                    },
                }
                
                for code, data in system_accounts_data.items():
                    if not ChartOfAccounts.objects.filter(code=code).exists():
                        # البحث عن الحساب الأب
                        parent_code = code[:3] + "0" if len(code) == 5 else code[:2] + "00"
                        parent_account = ChartOfAccounts.objects.filter(code=parent_code).first()
                        
                        ChartOfAccounts.objects.create(
                            code=code,
                            name=data["name"],
                            name_en=data.get("name_en"),
                            parent=parent_account,
                            account_type=data["type"],
                            is_leaf=True,
                            is_active=True,
                            description=data.get("description", ""),
                        )
                        accounts_created += 1
                
                return True
                
        except Exception as e:
            logger.error(f"خطأ في إعداد حسابات النظام: {str(e)}")
            return False
