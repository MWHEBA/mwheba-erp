"""
خدمة الرواتب الآمنة - تمنع إنشاء حسابات جديدة وتلتزم بالقوالب المحددة
"""
from decimal import Decimal
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


class SecurePayrollService:
    """خدمة الرواتب الآمنة التي تلتزم بالحسابات والقوالب المحددة مسبقاً"""
    
    # الحسابات المسموحة للرواتب (لا يمكن إضافة غيرها)
    ALLOWED_PAYROLL_ACCOUNTS = {
        # حسابات المصروفات
        '52020': 'الرواتب والأجور',
        '52021': 'البدلات الثابتة', 
        '52022': 'المكافآت والحوافز',
        '52023': 'بدل السكن',
        
        # حسابات الخصوم
        '21020': 'مستحقات الرواتب',
        '21030': 'سلف الموظفين',
        '21031': 'التأمينات الاجتماعية',
        '21032': 'ضرائب الدخل',
        '21033': 'اشتراكات النقابة',
        '21034': 'التأمين الطبي',
        
        # حسابات النقدية
        '11011': 'الصندوق الرئيسي',
        '11021': 'البنك الأهلي',
    }
    
    # خريطة البنود للحسابات (لا يمكن تغييرها)
    COMPONENT_ACCOUNT_MAPPING = {
        # المستحقات
        'TRANSPORT_ALLOWANCE': '52021',
        'MEAL_ALLOWANCE': '52021', 
        'PHONE_ALLOWANCE': '52021',
        'EDUCATION_ALLOWANCE': '52021',
        'OVERTIME_PAY': '52022',
        'PERFORMANCE_BONUS': '52022',
        'ANNUAL_BONUS': '52022',
        'HOUSING_ALLOWANCE': '52023',
        
        # الخصومات
        'UNION_FEE': '21033',
        'MEDICAL_INS': '21034',
        'SOCIAL_INS': '21031',
        'INCOME_TAX': '21032',
        'ADVANCE_DEDUCTION': '21030',
        'ABSENCE_PENALTY': '21020',
        'LATE_PENALTY': '21020',
    }
    
    # الحساب الافتراضي للبنود غير المعروفة
    DEFAULT_FALLBACK_ACCOUNTS = {
        'earning': '52021',  # البدلات الثابتة
        'deduction': '21020'  # مستحقات الرواتب
    }
    
    @staticmethod
    def get_account_for_component(component_code, component_type):
        """
        الحصول على الحساب المحاسبي لمكون الراتب بطريقة آمنة
        
        Args:
            component_code: كود المكون
            component_type: نوع المكون (earning/deduction)
            
        Returns:
            ChartOfAccounts: الحساب المحاسبي أو None
        """
        from financial.models import ChartOfAccounts
        
        # 1. البحث في الخريطة المحددة مسبقاً
        account_code = SecurePayrollService.COMPONENT_ACCOUNT_MAPPING.get(component_code)
        
        # 2. إذا لم يوجد، استخدم الحساب الافتراضي
        if not account_code:
            account_code = SecurePayrollService.DEFAULT_FALLBACK_ACCOUNTS.get(component_type)
            logger.warning(f"استخدام الحساب الافتراضي للمكون غير المعروف: {component_code}")
        
        # 3. التحقق من أن الحساب مسموح
        if account_code not in SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS:
            logger.error(f"محاولة استخدام حساب غير مسموح: {account_code}")
            return None
        
        # 4. البحث عن الحساب في النظام
        account = ChartOfAccounts.objects.filter(code=account_code).first()
        
        if not account:
            logger.error(f"الحساب المطلوب غير موجود في النظام: {account_code}")
            return None
        
        return account
    
    @staticmethod
    def validate_payroll_accounts(payroll):
        """
        التحقق من صحة الحسابات المستخدمة في قسيمة الراتب
        
        Args:
            payroll: قسيمة الراتب
            
        Returns:
            dict: نتيجة التحقق
        """
        validation_result = {
            'is_valid': True,
            'errors': [],
            'warnings': []
        }
        
        # فحص جميع بنود الراتب
        for line in payroll.lines.all():
            component_code = line.code
            component_type = line.component_type
            
            # الحصول على الحساب المتوقع
            expected_account = SecurePayrollService.get_account_for_component(
                component_code, component_type
            )
            
            if not expected_account:
                validation_result['is_valid'] = False
                validation_result['errors'].append(
                    f"لا يمكن تحديد حساب آمن للمكون: {line.name} ({component_code})"
                )
                continue
            
            # التحقق من الحساب المستخدم في SalaryComponent
            if line.salary_component and line.salary_component.account_code:
                actual_account_code = line.salary_component.account_code
                
                if actual_account_code != expected_account.code:
                    validation_result['warnings'].append(
                        f"المكون {line.name} يستخدم حساب {actual_account_code} "
                        f"بدلاً من الحساب المتوقع {expected_account.code}"
                    )
        
        return validation_result
    
    @staticmethod
    def create_secure_journal_entry(payroll, payment_account, paid_by):
        """
        إنشاء قيد محاسبي آمن للراتب
        
        Args:
            payroll: قسيمة الراتب
            payment_account: حساب الدفع
            paid_by: المستخدم الذي دفع
            
        Returns:
            JournalEntry: القيد المحاسبي
        """
        from financial.models import JournalEntry, JournalEntryLine
        
        # التحقق من صحة الحسابات أولاً
        validation = SecurePayrollService.validate_payroll_accounts(payroll)
        
        if not validation['is_valid']:
            raise ValueError(f"فشل التحقق من الحسابات: {validation['errors']}")
        
        # طباعة التحذيرات
        for warning in validation['warnings']:
            logger.warning(warning)
        
        with transaction.atomic():
            # إنشاء القيد
            entry = JournalEntry.objects.create(
                date=payroll.month,
                description=f'راتب {payroll.employee.get_full_name_ar()} - {payroll.month.strftime("%Y-%m")}',
                reference=f'PAY-{payroll.id}',
                created_by=paid_by
            )
            
            # 1. الراتب الأساسي
            basic_account = SecurePayrollService._get_safe_account('52020')
            if basic_account:
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=basic_account,
                    debit=payroll.basic_salary,
                    credit=Decimal('0'),
                    description=f'راتب أساسي - {payroll.employee.get_full_name_ar()}'
                )
            
            # 2. المستحقات (من PayrollLines)
            SecurePayrollService._add_earnings_lines(entry, payroll)
            
            # 3. الخصومات (من PayrollLines) 
            SecurePayrollService._add_deductions_lines(entry, payroll)
            
            # 4. صافي الراتب
            if payment_account.code in SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS:
                JournalEntryLine.objects.create(
                    journal_entry=entry,
                    account=payment_account,
                    debit=Decimal('0'),
                    credit=payroll.net_salary,
                    description=f'صافي راتب {payroll.employee.get_full_name_ar()}'
                )
            else:
                raise ValueError(f"حساب الدفع غير مسموح: {payment_account.code}")
            
            return entry
    
    @staticmethod
    def _get_safe_account(account_code):
        """الحصول على حساب آمن (موجود في القائمة المسموحة)"""
        from financial.models import ChartOfAccounts
        
        if account_code not in SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS:
            logger.error(f"محاولة استخدام حساب غير مسموح: {account_code}")
            return None
        
        account = ChartOfAccounts.objects.filter(code=account_code).first()
        if not account:
            logger.error(f"الحساب المطلوب غير موجود: {account_code}")
            return None
        
        return account
    
    @staticmethod
    def _add_earnings_lines(entry, payroll):
        """إضافة بنود المستحقات للقيد"""
        from financial.models import JournalEntryLine
        
        earning_lines = payroll.lines.filter(component_type='earning')
        
        for line in earning_lines:
            if line.amount and line.amount > 0:
                account = SecurePayrollService.get_account_for_component(
                    line.code, 'earning'
                )
                
                if account:
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=account,
                        debit=line.amount,
                        credit=Decimal('0'),
                        description=f"{line.name} - {payroll.employee.get_full_name_ar()}"
                    )
                    logger.info(f"تم إضافة مستحق آمن: {line.name} - {line.amount}")
                else:
                    logger.error(f"فشل إضافة المستحق: {line.name}")
    
    @staticmethod
    def _add_deductions_lines(entry, payroll):
        """إضافة بنود الخصومات للقيد"""
        from financial.models import JournalEntryLine
        
        deduction_lines = payroll.lines.filter(component_type='deduction')
        
        for line in deduction_lines:
            if line.amount and line.amount > 0:
                account = SecurePayrollService.get_account_for_component(
                    line.code, 'deduction'
                )
                
                if account:
                    JournalEntryLine.objects.create(
                        journal_entry=entry,
                        account=account,
                        debit=Decimal('0'),
                        credit=line.amount,
                        description=f"{line.name} - {payroll.employee.get_full_name_ar()}"
                    )
                    logger.info(f"تم إضافة خصم آمن: {line.name} - {line.amount}")
                else:
                    logger.error(f"فشل إضافة الخصم: {line.name}")
    
    @staticmethod
    def get_allowed_accounts_summary():
        """عرض ملخص الحسابات المسموحة"""
        return {
            'total_allowed': len(SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS),
            'accounts': SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS,
            'component_mapping': SecurePayrollService.COMPONENT_ACCOUNT_MAPPING,
            'fallback_accounts': SecurePayrollService.DEFAULT_FALLBACK_ACCOUNTS
        }
