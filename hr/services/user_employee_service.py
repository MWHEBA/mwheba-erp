"""
خدمة الربط بين المستخدمين والموظفين
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from ..models import Employee

User = get_user_model()


class UserEmployeeService:
    """
    خدمة إدارة الربط بين المستخدمين والموظفين
    
    الاستراتيجيات المتاحة:
    1. OneToOne: مستخدم واحد لكل موظف (الأفضل)
    2. Employee Number Matching: الربط عبر رقم الموظف
    3. Email Matching: الربط عبر البريد الإلكتروني
    4. Biometric User ID: الربط عبر معرف البصمة
    """
    
    @staticmethod
    def create_user_for_employee(employee, username=None, password=None, send_email=False):
        """
        إنشاء مستخدم لموظف موجود
        
        Args:
            employee: كائن الموظف
            username: اسم المستخدم (اختياري، سيستخدم employee_number)
            password: كلمة المرور (اختياري، سيتم توليدها)
            send_email: إرسال بيانات الدخول بالبريد
        
        Returns:
            User object
        """
        if hasattr(employee, 'user') and employee.user:
            raise ValueError(f"الموظف {employee.employee_number} مرتبط بمستخدم بالفعل")
        
        # تحديد اسم المستخدم
        if not username:
            username = employee.employee_number
        
        # توليد كلمة مرور
        if not password:
            import secrets
            password = secrets.token_urlsafe(12)
        
        # إنشاء المستخدم
        user = User.objects.create_user(
            username=username,
            email=employee.work_email,
            password=password,
            first_name=employee.first_name_ar,
            last_name=employee.last_name_ar
        )
        
        # ربط الموظف بالمستخدم
        employee.user = user
        employee.save()
        
        # إرسال بيانات الدخول بالبريد
        if send_email:
            UserEmployeeService.send_credentials_email(employee, username, password)
        
        return user, password
    
    @staticmethod
    def create_employee_for_user(user, employee_data):
        """
        إنشاء موظف لمستخدم موجود
        
        Args:
            user: كائن المستخدم
            employee_data: بيانات الموظف (dict)
        
        Returns:
            Employee object
        """
        if hasattr(user, 'employee_profile'):
            raise ValueError(f"المستخدم {user.username} مرتبط بموظف بالفعل")
        
        # إنشاء الموظف
        employee = Employee.objects.create(
            user=user,
            **employee_data
        )
        
        return employee
    
    @staticmethod
    def link_existing_user_to_employee(employee, user):
        """
        ربط مستخدم موجود بموظف موجود
        
        Args:
            employee: كائن الموظف
            user: كائن المستخدم
        """
        if hasattr(employee, 'user') and employee.user:
            raise ValueError(f"الموظف {employee.employee_number} مرتبط بمستخدم بالفعل")
        
        if hasattr(user, 'employee_profile'):
            raise ValueError(f"المستخدم {user.username} مرتبط بموظف بالفعل")
        
        employee.user = user
        employee.save()
        
        return employee
    
    @staticmethod
    def find_user_by_employee_number(employee_number):
        """البحث عن مستخدم عبر رقم الموظف"""
        try:
            employee = Employee.objects.get(employee_number=employee_number)
            return employee.user if hasattr(employee, 'user') else None
        except Employee.DoesNotExist:
            return None
    
    @staticmethod
    def find_employee_by_username(username):
        """البحث عن موظف عبر اسم المستخدم"""
        try:
            user = User.objects.get(username=username)
            return user.employee_profile if hasattr(user, 'employee_profile') else None
        except User.DoesNotExist:
            return None
    
    @staticmethod
    def find_employee_by_biometric_id(user_id):
        """
        البحث عن موظف عبر معرف البصمة
        
        الاستراتيجيات:
        1. employee_number = user_id
        2. البحث في جدول mapping منفصل
        """
        # الاستراتيجية 1: رقم الموظف = معرف البصمة
        try:
            return Employee.objects.get(employee_number=user_id)
        except Employee.DoesNotExist:
            pass
        
        # الاستراتيجية 2: البحث في جدول mapping
        from ..models import BiometricUserMapping
        try:
            mapping = BiometricUserMapping.objects.get(biometric_user_id=user_id)
            return mapping.employee
        except:
            return None
    
    @staticmethod
    def sync_user_data_to_employee(user):
        """مزامنة بيانات المستخدم مع الموظف"""
        if not hasattr(user, 'employee_profile'):
            return False
        
        employee = user.employee_profile
        
        # تحديث البيانات
        if user.first_name and not employee.first_name_ar:
            employee.first_name_ar = user.first_name
        
        if user.last_name and not employee.last_name_ar:
            employee.last_name_ar = user.last_name
        
        if user.email and not employee.work_email:
            employee.work_email = user.email
        
        employee.save()
        return True
    
    @staticmethod
    def sync_employee_data_to_user(employee):
        """مزامنة بيانات الموظف مع المستخدم"""
        if not hasattr(employee, 'user'):
            return False
        
        user = employee.user
        
        # تحديث البيانات
        user.first_name = employee.first_name_ar
        user.last_name = employee.last_name_ar
        user.email = employee.work_email
        
        user.save()
        return True
    
    @staticmethod
    def bulk_create_users_for_employees(employees, send_email=False):
        """
        إنشاء مستخدمين لعدة موظفين دفعة واحدة
        
        Returns:
            list of (employee, user, password) tuples
        """
        results = []
        
        with transaction.atomic():
            for employee in employees:
                try:
                    if not hasattr(employee, 'user') or not employee.user:
                        user, password = UserEmployeeService.create_user_for_employee(
                            employee,
                            send_email=send_email
                        )
                        results.append((employee, user, password))
                except Exception as e:
                    results.append((employee, None, str(e)))
        
        return results
    
    @staticmethod
    def send_credentials_email(employee, username, password):
        """إرسال بيانات الدخول بالبريد الإلكتروني"""
        from django.core.mail import send_mail
        from django.conf import settings
        
        subject = 'بيانات الدخول لنظام الموارد البشرية'
        
        message = f"""
مرحباً {employee.get_full_name_ar()},

تم إنشاء حساب لك في نظام الموارد البشرية.

بيانات الدخول:
اسم المستخدم: {username}
كلمة المرور: {password}

رابط الدخول: {settings.SITE_URL}/login/

يرجى تغيير كلمة المرور عند أول تسجيل دخول.

تحياتنا،
قسم الموارد البشرية
        """
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [employee.work_email],
            fail_silently=False,
        )
    
    @staticmethod
    def get_unlinked_employees():
        """الحصول على الموظفين غير المرتبطين بمستخدمين"""
        return Employee.objects.filter(user__isnull=True)
    
    @staticmethod
    def get_unlinked_users():
        """الحصول على المستخدمين غير المرتبطين بموظفين"""
        return User.objects.filter(employee_profile__isnull=True)
    
    @staticmethod
    def auto_link_by_email():
        """
        ربط تلقائي بين المستخدمين والموظفين عبر البريد الإلكتروني
        
        Returns:
            عدد الروابط المنشأة
        """
        linked_count = 0
        
        unlinked_employees = UserEmployeeService.get_unlinked_employees()
        
        for employee in unlinked_employees:
            try:
                # البحث عن مستخدم بنفس البريد
                user = User.objects.get(email=employee.work_email)
                
                # التحقق من أن المستخدم غير مرتبط
                if not hasattr(user, 'employee_profile'):
                    employee.user = user
                    employee.save()
                    linked_count += 1
            except User.DoesNotExist:
                continue
            except User.MultipleObjectsReturned:
                continue
        
        return linked_count
    
    @staticmethod
    def generate_username_suggestions(employee):
        """توليد اقتراحات لأسماء المستخدمين"""
        suggestions = []
        
        # 1. رقم الموظف
        suggestions.append(employee.employee_number)
        
        # 2. الاسم الأول + رقم الموظف
        if employee.first_name_en:
            suggestions.append(f"{employee.first_name_en.lower()}{employee.employee_number}")
        
        # 3. الاسم الأول.اسم العائلة
        if employee.first_name_en and employee.last_name_en:
            suggestions.append(f"{employee.first_name_en.lower()}.{employee.last_name_en.lower()}")
        
        # 4. البريد الإلكتروني (الجزء قبل @)
        if employee.work_email:
            email_username = employee.work_email.split('@')[0]
            suggestions.append(email_username)
        
        # التحقق من التوفر
        available_suggestions = []
        for suggestion in suggestions:
            if not User.objects.filter(username=suggestion).exists():
                available_suggestions.append(suggestion)
        
        return available_suggestions
