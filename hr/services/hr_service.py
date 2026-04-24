"""
خدمة إدارة الموارد البشرية
"""
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class HRService:
    """خدمة إدارة الموارد البشرية"""
    
    @staticmethod
    def initialize_organization_structure():
        """
        تهيئة الهيكل التنظيمي للشركة
        """
        try:
            from hr.models import Department, JobTitle
            
            # إنشاء الأقسام والمسميات الوظيفية
            departments_created = Department.create_default_departments()
            job_titles_created = JobTitle.create_default_job_titles()
            
            if departments_created and job_titles_created:
                logger.info("تم تهيئة الهيكل التنظيمي للشركة بنجاح")
                return True
            else:
                logger.warning("فشل في تهيئة بعض أجزاء الهيكل التنظيمي")
                return False
                
        except Exception as e:
            logger.error(f"فشل في تهيئة الهيكل التنظيمي للشركة: {e}")
            return False
    
    @staticmethod
    def create_employee(employee_data, created_by=None):
        """
        إنشاء موظف جديد
        """
        from hr.models import Employee
        
        try:
            with transaction.atomic():
                # التأكد من وجود البيانات المطلوبة
                required_fields = ['name', 'national_id', 'birth_date', 'gender']
                for field in required_fields:
                    if not employee_data.get(field):
                        raise ValueError(f"الحقل {field} مطلوب")
                
                # توليد رقم الموظف إذا لم يكن موجوداً
                if not employee_data.get('employee_number'):
                    employee_data['employee_number'] = HRService._generate_employee_number()
                
                # إنشاء الموظف
                employee = Employee.objects.create(
                    **employee_data,
                    created_by=created_by
                )
                
                logger.info(f"تم إنشاء موظف جديد: {employee.get_full_name_ar()}")
                return employee
                
        except Exception as e:
            logger.error(f"فشل في إنشاء الموظف: {e}")
            raise
    
    @staticmethod
    def _generate_employee_number():
        """توليد رقم موظف فريد"""
        from hr.models import Employee
        
        current_year = timezone.now().year
        year_suffix = str(current_year)[-2:]
        
        # البحث عن آخر رقم موظف
        prefix = f"EMP{year_suffix}"
        last_employee = Employee.objects.filter(
            employee_number__startswith=prefix
        ).order_by('employee_number').last()
        
        if last_employee:
            try:
                last_number = int(last_employee.employee_number[len(prefix):])
                next_number = last_number + 1
            except (ValueError, IndexError):
                next_number = 1
        else:
            next_number = 1
        
        return f"{prefix}{next_number:04d}"
    
    @staticmethod
    def get_employees_by_department(department_code=None):
        """
        الحصول على الموظفين حسب القسم
        """
        from hr.models import Employee, Department
        
        try:
            queryset = Employee.objects.filter(status='active').select_related('department', 'job_title')
            
            if department_code:
                queryset = queryset.filter(department__code=department_code)
            
            employees_data = []
            
            for employee in queryset:
                employee_info = {
                    'id': employee.id,
                    'employee_number': employee.employee_number,
                    'name': employee.get_full_name_ar(),
                    'department': employee.department.name_ar,
                    'job_title': employee.job_title.title_ar,
                    'gender': employee.get_gender_display(),
                    'hire_date': employee.hire_date,
                    'mobile_phone': employee.mobile_phone,
                    'work_email': employee.work_email,
                    'employment_type': employee.get_employment_type_display(),
                    'biometric_id': employee.biometric_user_id,
                    'has_biometric': bool(employee.biometric_user_id)
                }
                
                employees_data.append(employee_info)
            
            return employees_data
            
        except Exception as e:
            logger.error(f"فشل في الحصول على الموظفين: {e}")
            return []
    
    @staticmethod
    def get_employees_by_job_category(job_category=None):
        """
        الحصول على الموظفين حسب فئة الوظيفة
        """
        from hr.models import Employee
        
        try:
            # الموظفين النشطين
            employees = Employee.objects.filter(
                status='active'
            ).select_related('department', 'job_title')
            
            if job_category:
                # تصفية حسب فئة الوظيفة (مثل: مبيعات، إنتاج، إدارة)
                employees = employees.filter(department__code__startswith=job_category.upper())
            
            employees_data = []
            
            for employee in employees:
                employee_info = {
                    'id': employee.id,
                    'name': employee.get_full_name_ar(),
                    'employee_number': employee.employee_number,
                    'job_title': employee.job_title.title_ar,
                    'department': employee.department.name_ar,
                    'mobile_phone': employee.mobile_phone,
                    'work_email': employee.work_email,
                    'hire_date': employee.hire_date,
                    'experience_years': (timezone.now().date() - employee.hire_date).days // 365,
                }
                
                employees_data.append(employee_info)
            
            return employees_data
            
        except Exception as e:
            logger.error(f"فشل في الحصول على الموظفين: {e}")
            return []
    
    @staticmethod
    def get_attendance_summary(date_from=None, date_to=None):
        """
        ملخص حضور الموظفين
        """
        from hr.models import Employee, Attendance
        
        try:
            # تحديد الفترة الافتراضية (آخر 30 يوم)
            if not date_to:
                date_to = timezone.now().date()
            if not date_from:
                date_from = date_to - timedelta(days=30)
            
            active_employees = Employee.objects.filter(status='active')
            
            attendance_data = []
            
            for employee in active_employees:
                # حساب إحصائيات الحضور
                attendance_records = Attendance.objects.filter(
                    employee=employee,
                    date__gte=date_from,
                    date__lte=date_to
                )
                
                total_days = (date_to - date_from).days + 1
                present_days = attendance_records.filter(status='present').count()
                absent_days = attendance_records.filter(status='absent').count()
                late_days = attendance_records.filter(is_late=True).count()
                
                employee_summary = {
                    'employee_id': employee.id,
                    'name': employee.get_full_name_ar(),
                    'employee_number': employee.employee_number,
                    'department': employee.department.name_ar,
                    'job_title': employee.job_title.title_ar,
                    'total_days': total_days,
                    'present_days': present_days,
                    'absent_days': absent_days,
                    'late_days': late_days,
                    'attendance_rate': (present_days / total_days * 100) if total_days > 0 else 0,
                    'punctuality_rate': ((present_days - late_days) / present_days * 100) if present_days > 0 else 0
                }
                
                attendance_data.append(employee_summary)
            
            return {
                'period': {'from': date_from, 'to': date_to},
                'employees': attendance_data,
                'summary': {
                    'total_employees': len(attendance_data),
                    'average_attendance_rate': sum(e['attendance_rate'] for e in attendance_data) / len(attendance_data) if attendance_data else 0,
                    'average_punctuality_rate': sum(e['punctuality_rate'] for e in attendance_data) / len(attendance_data) if attendance_data else 0
                },
                'generated_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"فشل في إنشاء ملخص الحضور: {e}")
            return None
    
    @staticmethod
    def verify_biometric_integration():
        """
        التحقق من تكامل نظام البصمة
        """
        from hr.models import Employee, BiometricDevice
        
        try:
            # التحقق من وجود أجهزة البصمة
            devices = BiometricDevice.objects.filter(is_active=True)
            
            # التحقق من الموظفين المربوطين بالبصمة
            employees_with_biometric = Employee.objects.filter(
                status='active',
                biometric_user_id__isnull=False
            ).exclude(biometric_user_id='')
            
            employees_without_biometric = Employee.objects.filter(
                status='active'
            ).filter(
                models.Q(biometric_user_id__isnull=True) | models.Q(biometric_user_id='')
            )
            
            return {
                'devices_count': devices.count(),
                'active_devices': list(devices.values('name', 'ip_address', 'status')),
                'employees_with_biometric': employees_with_biometric.count(),
                'employees_without_biometric': employees_without_biometric.count(),
                'integration_rate': (employees_with_biometric.count() / Employee.objects.filter(status='active').count() * 100) if Employee.objects.filter(status='active').exists() else 0,
                'missing_biometric_employees': list(employees_without_biometric.values('employee_number', 'name', 'job_title__title_ar')),
                'verified_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"فشل في التحقق من تكامل البصمة: {e}")
            return None
    
    @staticmethod
    def generate_employee_directory():
        """
        إنشاء دليل الموظفين
        """
        from hr.models import Employee, Department
        
        try:
            departments = Department.objects.filter(
                is_active=True,
                employees__status='active'
            ).distinct().prefetch_related('employees')
            
            directory_data = []
            
            for department in departments:
                dept_employees = department.employees.filter(status='active').order_by('job_title__code')
                
                employees_list = []
                for employee in dept_employees:
                    employee_info = {
                        'name': employee.get_full_name_ar(),
                        'job_title': employee.job_title.title_ar,
                        'mobile_phone': employee.mobile_phone,
                        'work_email': employee.work_email,
                        'extension': getattr(employee, 'extension', ''),
                        'hire_date': employee.hire_date,
                        'photo_url': employee.photo.url if employee.photo else None
                    }
                    employees_list.append(employee_info)
                
                dept_info = {
                    'department_name': department.name_ar,
                    'department_code': department.code,
                    'manager': department.manager.get_full_name_ar() if department.manager else None,
                    'employees_count': len(employees_list),
                    'employees': employees_list
                }
                
                directory_data.append(dept_info)
            
            return {
                'departments': directory_data,
                'total_employees': sum(d['employees_count'] for d in directory_data),
                'generated_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"فشل في إنشاء دليل الموظفين: {e}")
            return None
    
    @staticmethod
    def get_payroll_summary(month=None, year=None):
        """
        ملخص الرواتب الشهرية
        """
        from hr.models import Employee, Payroll
        
        try:
            if not month:
                month = timezone.now().month
            if not year:
                year = timezone.now().year
            
            # البحث عن كشف الراتب للشهر المحدد
            payroll = Payroll.objects.filter(
                month=month,
                year=year,
                status='approved'
            ).first()
            
            if not payroll:
                return {
                    'month': month,
                    'year': year,
                    'status': 'not_generated',
                    'message': 'لم يتم إنشاء كشف راتب لهذا الشهر'
                }
            
            # حساب الإحصائيات
            payroll_lines = payroll.payroll_lines.all()
            
            total_employees = payroll_lines.count()
            total_gross_salary = sum(line.gross_salary for line in payroll_lines)
            total_deductions = sum(line.total_deductions for line in payroll_lines)
            total_net_salary = sum(line.net_salary for line in payroll_lines)
            
            # تجميع حسب القسم
            department_summary = {}
            for line in payroll_lines:
                dept_name = line.employee.department.name_ar
                if dept_name not in department_summary:
                    department_summary[dept_name] = {
                        'employees_count': 0,
                        'total_gross': Decimal('0.00'),
                        'total_net': Decimal('0.00')
                    }
                
                department_summary[dept_name]['employees_count'] += 1
                department_summary[dept_name]['total_gross'] += line.gross_salary
                department_summary[dept_name]['total_net'] += line.net_salary
            
            return {
                'month': month,
                'year': year,
                'payroll_id': payroll.id,
                'status': payroll.status,
                'summary': {
                    'total_employees': total_employees,
                    'total_gross_salary': total_gross_salary,
                    'total_deductions': total_deductions,
                    'total_net_salary': total_net_salary,
                    'average_gross_salary': total_gross_salary / total_employees if total_employees > 0 else Decimal('0.00'),
                    'average_net_salary': total_net_salary / total_employees if total_employees > 0 else Decimal('0.00')
                },
                'by_department': department_summary,
                'generated_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"فشل في إنشاء ملخص الرواتب: {e}")
            return None