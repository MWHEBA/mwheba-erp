"""
مراقب أمان نظام الرواتب - يسجل ويمنع المحاولات المشبوهة
"""
import logging
from datetime import datetime
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class PayrollSecurityMonitor:
    """مراقب أمان نظام الرواتب"""
    
    # عتبات التحذير
    MAX_FAILED_ATTEMPTS = 5
    MONITORING_WINDOW = 3600  # ساعة واحدة
    
    @staticmethod
    def log_security_event(event_type, details, user=None, severity='INFO'):
        """
        تسجيل حدث أمني
        
        Args:
            event_type: نوع الحدث
            details: تفاصيل الحدث
            user: المستخدم (إن وجد)
            severity: مستوى الخطورة
        """
        user_info = f"User: {user.username}" if user else "System"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        log_message = f"[PAYROLL_SECURITY] {timestamp} - {event_type} - {details} - {user_info}"
        
        if severity == 'ERROR':
            logger.error(log_message)
        elif severity == 'WARNING':
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        # حفظ في الكاش للمراقبة
        cache_key = f"security_event_{event_type}_{datetime.now().timestamp()}"
        cache.set(cache_key, {
            'event_type': event_type,
            'details': details,
            'user': user.username if user else None,
            'severity': severity,
            'timestamp': timestamp
        }, timeout=86400)  # يوم واحد
    
    @staticmethod
    def check_unauthorized_account_access(account_code, user=None):
        """
        فحص محاولة الوصول لحساب غير مصرح
        
        Args:
            account_code: كود الحساب
            user: المستخدم
            
        Returns:
            bool: True إذا كان مسموح، False إذا كان ممنوع
        """
        from .secure_payroll_service import SecurePayrollService
        
        if account_code not in SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS:
            PayrollSecurityMonitor.log_security_event(
                'UNAUTHORIZED_ACCOUNT_ACCESS',
                f'Attempted access to unauthorized account: {account_code}',
                user,
                'ERROR'
            )
            
            # زيادة عداد المحاولات المشبوهة
            PayrollSecurityMonitor._increment_failed_attempts(user)
            
            return False
        
        return True
    
    @staticmethod
    def check_account_creation_attempt(account_code, account_name, user=None):
        """
        فحص محاولة إنشاء حساب جديد
        
        Args:
            account_code: كود الحساب
            account_name: اسم الحساب
            user: المستخدم
        """
        PayrollSecurityMonitor.log_security_event(
            'ACCOUNT_CREATION_BLOCKED',
            f'Blocked attempt to create account: {account_code} - {account_name}',
            user,
            'WARNING'
        )
        
        PayrollSecurityMonitor._increment_failed_attempts(user)
    
    @staticmethod
    def check_template_modification(template, old_account, new_account, user=None):
        """
        فحص تعديل قالب مكون راتب
        
        Args:
            template: القالب
            old_account: الحساب القديم
            new_account: الحساب الجديد
            user: المستخدم
        """
        from .secure_payroll_service import SecurePayrollService
        
        if new_account not in SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS:
            PayrollSecurityMonitor.log_security_event(
                'UNSAFE_TEMPLATE_MODIFICATION',
                f'Template {template.name} changed from {old_account} to unsafe account {new_account}',
                user,
                'ERROR'
            )
            return False
        
        PayrollSecurityMonitor.log_security_event(
            'TEMPLATE_MODIFICATION',
            f'Template {template.name} changed from {old_account} to {new_account}',
            user,
            'INFO'
        )
        return True
    
    @staticmethod
    def _increment_failed_attempts(user):
        """زيادة عداد المحاولات الفاشلة"""
        if not user:
            return
        
        cache_key = f"failed_attempts_{user.username}"
        attempts = cache.get(cache_key, 0)
        attempts += 1
        
        cache.set(cache_key, attempts, timeout=PayrollSecurityMonitor.MONITORING_WINDOW)
        
        if attempts >= PayrollSecurityMonitor.MAX_FAILED_ATTEMPTS:
            PayrollSecurityMonitor.log_security_event(
                'SUSPICIOUS_ACTIVITY',
                f'User {user.username} exceeded maximum failed attempts ({attempts})',
                user,
                'ERROR'
            )
    
    @staticmethod
    def get_security_summary():
        """الحصول على ملخص الأمان"""
        # جمع الأحداث الأمنية من الكاش
        cache_keys = cache.keys("security_event_*")
        events = []
        
        for key in cache_keys:
            event = cache.get(key)
            if event:
                events.append(event)
        
        # تصنيف الأحداث
        summary = {
            'total_events': len(events),
            'error_events': len([e for e in events if e['severity'] == 'ERROR']),
            'warning_events': len([e for e in events if e['severity'] == 'WARNING']),
            'info_events': len([e for e in events if e['severity'] == 'INFO']),
            'recent_events': sorted(events, key=lambda x: x['timestamp'], reverse=True)[:10]
        }
        
        return summary
    
    @staticmethod
    def is_payroll_operation_safe(operation_type, details, user=None):
        """
        فحص ما إذا كانت عملية الراتب آمنة
        
        Args:
            operation_type: نوع العملية
            details: تفاصيل العملية
            user: المستخدم
            
        Returns:
            bool: True إذا كانت آمنة
        """
        # فحص المستخدم
        if user:
            cache_key = f"failed_attempts_{user.username}"
            failed_attempts = cache.get(cache_key, 0)
            
            if failed_attempts >= PayrollSecurityMonitor.MAX_FAILED_ATTEMPTS:
                PayrollSecurityMonitor.log_security_event(
                    'OPERATION_BLOCKED',
                    f'Operation {operation_type} blocked due to suspicious activity',
                    user,
                    'ERROR'
                )
                return False
        
        # تسجيل العملية
        PayrollSecurityMonitor.log_security_event(
            'PAYROLL_OPERATION',
            f'{operation_type}: {details}',
            user,
            'INFO'
        )
        
        return True
    
    @staticmethod
    def validate_journal_entry_accounts(journal_entry):
        """
        التحقق من صحة حسابات القيد المحاسبي
        
        Args:
            journal_entry: القيد المحاسبي
            
        Returns:
            dict: نتيجة التحقق
        """
        from .secure_payroll_service import SecurePayrollService
        
        result = {
            'is_safe': True,
            'unsafe_accounts': [],
            'warnings': []
        }
        
        allowed_accounts = SecurePayrollService.ALLOWED_PAYROLL_ACCOUNTS
        
        for line in journal_entry.lines.all():
            if line.account.code not in allowed_accounts:
                result['is_safe'] = False
                result['unsafe_accounts'].append({
                    'code': line.account.code,
                    'name': line.account.name,
                    'amount': float(line.debit + line.credit)
                })
        
        if not result['is_safe']:
            PayrollSecurityMonitor.log_security_event(
                'UNSAFE_JOURNAL_ENTRY',
                f'Journal entry {journal_entry.id} contains unsafe accounts',
                None,
                'ERROR'
            )
        
        return result
