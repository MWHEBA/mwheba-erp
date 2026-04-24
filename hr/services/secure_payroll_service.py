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
        '50200': 'الرواتب والأجور',
        '50210': 'الأجر الأساسي', 
        '50220': 'البدلات',
        '50230': 'المكافآت',
        '50240': 'التأمينات الاجتماعية',
        
        # حسابات الخصوم
        '20200': 'مستحقات الرواتب',
        '10350': 'سلف الموظفين',
        '20210': 'التأمينات الاجتماعية',
        '20220': 'ضرائب الدخل',
        '21033': 'اشتراكات النقابة',
        '21034': 'التأمين الطبي',
        
        # حسابات النقدية
        '10100': 'الخزنة',
        '10200': 'البنك',
    }
    
    # خريطة البنود للحسابات (لا يمكن تغييرها)
    COMPONENT_ACCOUNT_MAPPING = {
        # المستحقات
        'TRANSPORT_ALLOWANCE': '50220',
        'MEAL_ALLOWANCE': '50220', 
        'PHONE_ALLOWANCE': '50220',
        'EDUCATION_ALLOWANCE': '50220',
        'OVERTIME_PAY': '50230',
        'PERFORMANCE_BONUS': '50230',
        'ANNUAL_BONUS': '50230',
        'HOUSING_ALLOWANCE': '50220',
        
        # الخصومات
        'UNION_FEE': '21033',
        'MEDICAL_INS': '21034',
        'SOCIAL_INS': '20210',
        'INCOME_TAX': '20220',
        'ADVANCE_DEDUCTION': '10350',
        'ABSENCE_PENALTY': '20200',
        'LATE_PENALTY': '20200',
    }
    
    # الحساب الافتراضي للبنود غير المعروفة
    DEFAULT_FALLBACK_ACCOUNTS = {
        'earning': '50220',  # البدلات
        'deduction': '20200'  # مستحقات الرواتب
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
        
        DEPRECATED: Use PayrollAccountingService.create_payroll_journal_entry() instead.
        This method is kept for backward compatibility.
        
        Args:
            payroll: قسيمة الراتب
            payment_account: حساب الدفع
            paid_by: المستخدم الذي دفع
            
        Returns:
            JournalEntry: القيد المحاسبي
        """
        import warnings
        warnings.warn(
            "SecurePayrollService.create_secure_journal_entry() is deprecated. "
            "Use PayrollAccountingService.create_payroll_journal_entry() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        from hr.services.payroll_accounting_service import PayrollAccountingService
        
        # التحقق من صحة الحسابات أولاً
        validation = SecurePayrollService.validate_payroll_accounts(payroll)
        
        if not validation['is_valid']:
            raise ValueError(f"فشل التحقق من الحسابات: {validation['errors']}")
        
        # طباعة التحذيرات
        for warning in validation['warnings']:
            logger.warning(warning)
        
        # استخدام PayrollAccountingService
        service = PayrollAccountingService()
        return service.create_payroll_journal_entry(payroll, paid_by)
    
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
