"""
استثناءات مخصصة لنظام التحقق من المعاملات المالية

هذا الملف يحتوي على جميع الاستثناءات المخصصة المستخدمة في نظام التحقق من المعاملات المالية.
يوفر استثناءات محددة لأنواع مختلفة من أخطاء التحقق مع معلومات إضافية للتشخيص والتسجيل.
"""

from django.core.exceptions import ValidationError


class FinancialValidationError(ValidationError):
    """
    استثناء أساسي لأخطاء التحقق من المعاملات المالية
    
    هذا الاستثناء هو الفئة الأساسية لجميع أخطاء التحقق المالي في النظام.
    يوفر معلومات إضافية عن الكيان المالي ونوع التحقق الذي فشل.
    
    Attributes:
        message (str): رسالة الخطأ الوصفية
        code (str): رمز الخطأ للتعريف البرمجي
        entity: الكيان المالي المرتبط بالخطأ (عميل، مورد، موظف، إلخ)
        validation_type (str): نوع التحقق الذي فشل (chart_of_accounts, accounting_period)
    
    Example:
        raise FinancialValidationError(
            message="لا يوجد حساب محاسبي مرتبط بالعميل",
            code="missing_account",
            entity=customer,
            validation_type="chart_of_accounts"
        )
    """
    
    def __init__(self, message, code=None, entity=None, validation_type=None):
        """
        تهيئة استثناء التحقق المالي
        
        Args:
            message (str): رسالة الخطأ الوصفية بالعربية
            code (str, optional): رمز الخطأ للتعريف البرمجي
            entity (Model, optional): الكيان المالي المرتبط بالخطأ
            validation_type (str, optional): نوع التحقق (chart_of_accounts, accounting_period)
        """
        self.entity = entity
        self.validation_type = validation_type
        self.code = code
        super().__init__(message, code=code)
    
    def __str__(self):
        """تمثيل نصي للاستثناء"""
        return str(self.message)


class ChartOfAccountsValidationError(FinancialValidationError):
    """
    استثناء خاص بأخطاء التحقق من الحساب المحاسبي
    
    يُستخدم هذا الاستثناء عندما يفشل التحقق من الحساب المحاسبي المرتبط بكيان مالي.
    يغطي الحالات التالية:
    - عدم وجود حساب محاسبي مرتبط بالكيان
    - الحساب المحاسبي غير مفعّل (is_active=False)
    - الحساب المحاسبي ليس حساباً نهائياً (is_leaf=False)
    
    Attributes:
        account: الحساب المحاسبي المرتبط بالخطأ (إن وجد)
    
    Example:
        raise ChartOfAccountsValidationError(
            message="الحساب المحاسبي غير مفعّل",
            code="inactive_account",
            entity=customer,
            account=chart_of_accounts
        )
    """
    
    def __init__(self, message, code=None, entity=None, account=None):
        """
        تهيئة استثناء التحقق من الحساب المحاسبي
        
        Args:
            message (str): رسالة الخطأ الوصفية بالعربية
            code (str, optional): رمز الخطأ (missing_account, inactive_account, not_leaf_account)
            entity (Model, optional): الكيان المالي المرتبط بالخطأ
            account (ChartOfAccounts, optional): الحساب المحاسبي المرتبط بالخطأ
        """
        self.account = account
        super().__init__(
            message=message,
            code=code,
            entity=entity,
            validation_type='chart_of_accounts'
        )


class AccountingPeriodValidationError(FinancialValidationError):
    """
    استثناء خاص بأخطاء التحقق من الفترة المحاسبية
    
    يُستخدم هذا الاستثناء عندما يفشل التحقق من الفترة المحاسبية للمعاملة المالية.
    يغطي الحالات التالية:
    - عدم وجود فترة محاسبية للتاريخ المحدد
    - الفترة المحاسبية مغلقة (status='closed')
    - التاريخ خارج نطاق جميع الفترات المحاسبية
    
    Attributes:
        period: الفترة المحاسبية المرتبطة بالخطأ (إن وجدت)
        transaction_date: تاريخ المعاملة المالية
    
    Example:
        raise AccountingPeriodValidationError(
            message="الفترة المحاسبية مغلقة",
            code="closed_period",
            entity=customer,
            period=accounting_period,
            transaction_date=date(2024, 1, 15)
        )
    """
    
    def __init__(self, message, code=None, entity=None, period=None, transaction_date=None):
        """
        تهيئة استثناء التحقق من الفترة المحاسبية
        
        Args:
            message (str): رسالة الخطأ الوصفية بالعربية
            code (str, optional): رمز الخطأ (missing_period, closed_period, out_of_range)
            entity (Model, optional): الكيان المالي المرتبط بالخطأ
            period (AccountingPeriod, optional): الفترة المحاسبية المرتبطة بالخطأ
            transaction_date (date, optional): تاريخ المعاملة المالية
        """
        self.period = period
        self.transaction_date = transaction_date
        super().__init__(
            message=message,
            code=code,
            entity=entity,
            validation_type='accounting_period'
        )
