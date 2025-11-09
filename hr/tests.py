"""
Tests لوحدة الموارد البشرية
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from datetime import date, timedelta, time
from decimal import Decimal

from .models import (
    Department, JobTitle, Employee, Shift, Attendance,
    LeaveType, LeaveBalance, Leave, Salary, Payroll, Advance
)
from .services.employee_service import EmployeeService
from .services.attendance_service import AttendanceService
from .services.leave_service import LeaveService
from .services.payroll_service import PayrollService

User = get_user_model()


class DepartmentModelTest(TestCase):
    """اختبارات نموذج القسم"""
    
    def setUp(self):
        self.department = Department.objects.create(
            code='IT',
            name_ar='تقنية المعلومات',
            name_en='Information Technology'
        )
    
    def test_department_creation(self):
        """اختبار إنشاء قسم"""
        self.assertEqual(self.department.code, 'IT')
        self.assertEqual(self.department.name_ar, 'تقنية المعلومات')
        self.assertTrue(self.department.is_active)
    
    def test_department_str(self):
        """اختبار __str__"""
        self.assertEqual(str(self.department), 'IT - تقنية المعلومات')


class EmployeeModelTest(TestCase):
    """اختبارات نموذج الموظف"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.department = Department.objects.create(
            code='IT',
            name_ar='تقنية المعلومات'
        )
        self.job_title = JobTitle.objects.create(
            code='DEV',
            title_ar='مطور',
            department=self.department
        )
        self.employee = Employee.objects.create(
            user=self.user,
            employee_number='EMP001',
            first_name_ar='أحمد',
            last_name_ar='محمد',
            national_id='12345678901234',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email='ahmed@test.com',
            mobile_phone='01234567890',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
    
    def test_employee_creation(self):
        """اختبار إنشاء موظف"""
        self.assertEqual(self.employee.employee_number, 'EMP001')
        self.assertEqual(self.employee.status, 'active')
    
    def test_get_full_name_ar(self):
        """اختبار الاسم الكامل"""
        self.assertEqual(self.employee.get_full_name_ar(), 'أحمد محمد')


class AttendanceServiceTest(TestCase):
    """اختبارات خدمة الحضور"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='test', password='test')
        self.department = Department.objects.create(code='IT', name_ar='IT')
        self.job_title = JobTitle.objects.create(code='DEV', title_ar='Dev', department=self.department)
        self.employee = Employee.objects.create(
            user=self.user,
            employee_number='EMP001',
            first_name_ar='أحمد',
            last_name_ar='محمد',
            national_id='12345678901234',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email='test@test.com',
            mobile_phone='01234567890',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
        self.shift = Shift.objects.create(
            name='صباحي',
            shift_type='morning',
            start_time=time(8, 0),
            end_time=time(16, 0)
        )
    
    def test_check_in(self):
        """اختبار تسجيل الحضور"""
        attendance = AttendanceService.record_check_in(self.employee, shift=self.shift)
        self.assertIsNotNone(attendance)
        self.assertEqual(attendance.employee, self.employee)
        self.assertEqual(attendance.date, date.today())
    
    def test_check_out(self):
        """اختبار تسجيل الانصراف"""
        attendance = AttendanceService.record_check_in(self.employee, shift=self.shift)
        updated = AttendanceService.record_check_out(self.employee)
        self.assertIsNotNone(updated.check_out)


class LeaveServiceTest(TestCase):
    """اختبارات خدمة الإجازات"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='test', password='test')
        self.department = Department.objects.create(code='IT', name_ar='IT')
        self.job_title = JobTitle.objects.create(code='DEV', title_ar='Dev', department=self.department)
        self.employee = Employee.objects.create(
            user=self.user,
            employee_number='EMP001',
            first_name_ar='أحمد',
            last_name_ar='محمد',
            national_id='12345678901234',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email='test@test.com',
            mobile_phone='01234567890',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
        self.leave_type = LeaveType.objects.create(
            code='ANNUAL',
            name_ar='إجازة سنوية',
            max_days_per_year=21
        )
        self.leave_balance = LeaveBalance.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            year=date.today().year,
            total_days=21,
            remaining_days=21
        )
    
    def test_request_leave(self):
        """اختبار طلب إجازة"""
        leave_data = {
            'leave_type': self.leave_type,
            'start_date': date.today(),
            'end_date': date.today() + timedelta(days=2),
            'reason': 'إجازة'
        }
        leave = LeaveService.request_leave(self.employee, leave_data)
        self.assertIsNotNone(leave)
        self.assertEqual(leave.status, 'pending')
    
    def test_approve_leave(self):
        """اختبار اعتماد إجازة"""
        leave = Leave.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=2),
            days_count=3,
            reason='test'
        )
        LeaveService.approve_leave(leave, self.user)
        leave.refresh_from_db()
        self.assertEqual(leave.status, 'approved')


class PayrollServiceTest(TestCase):
    """اختبارات خدمة الرواتب"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='test', password='test')
        self.department = Department.objects.create(code='IT', name_ar='IT')
        self.job_title = JobTitle.objects.create(code='DEV', title_ar='Dev', department=self.department)
        self.employee = Employee.objects.create(
            user=self.user,
            employee_number='EMP001',
            first_name_ar='أحمد',
            last_name_ar='محمد',
            national_id='12345678901234',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email='test@test.com',
            mobile_phone='01234567890',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
        self.salary = Salary.objects.create(
            employee=self.employee,
            effective_date=date.today(),
            basic_salary=Decimal('5000.00'),
            housing_allowance=Decimal('1000.00'),
            transport_allowance=Decimal('500.00'),
            food_allowance=Decimal('300.00'),
            gross_salary=Decimal('0'),
            total_deductions=Decimal('0'),
            net_salary=Decimal('0'),
            is_active=True,
            created_by=self.user
        )
    
    def test_calculate_payroll_basic(self):
        """اختبار حساب راتب أساسي"""
        payroll = PayrollService.calculate_payroll(
            self.employee,
            date(2025, 1, 1),
            self.user
        )
        
        self.assertIsNotNone(payroll)
        self.assertEqual(payroll.employee, self.employee)
        self.assertEqual(payroll.status, 'calculated')
        self.assertEqual(payroll.basic_salary, Decimal('5000.00'))
        self.assertGreater(payroll.net_salary, 0)
    
    def test_calculate_payroll_with_advance(self):
        """اختبار حساب راتب مع سلفة"""
        # إنشاء سلفة
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('1000.00'),
            reason='سلفة اختبار',
            status='paid'
        )
        
        payroll = PayrollService.calculate_payroll(
            self.employee,
            date(2025, 1, 1),
            self.user
        )
        
        # التحقق من خصم السلفة
        self.assertEqual(payroll.advance_deduction, Decimal('1000.00'))
        self.assertLess(payroll.net_salary, payroll.gross_salary)
        
        # التحقق من تحديث حالة السلفة
        advance.refresh_from_db()
        self.assertTrue(advance.deducted)
        self.assertEqual(advance.status, 'deducted')
    
    def test_calculate_payroll_no_active_salary(self):
        """اختبار حساب راتب بدون راتب نشط"""
        # تعطيل الراتب
        self.salary.is_active = False
        self.salary.save()
        
        with self.assertRaises(ValueError) as context:
            PayrollService.calculate_payroll(
                self.employee,
                date(2025, 1, 1),
                self.user
            )
        
        self.assertIn('لا يوجد راتب نشط', str(context.exception))
    
    def test_process_monthly_payroll(self):
        """اختبار معالجة رواتب شهرية"""
        results = PayrollService.process_monthly_payroll(
            date(2025, 1, 1),
            self.user
        )
        
        self.assertIsNotNone(results)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['success'])
        self.assertEqual(results[0]['employee'], self.employee)


class ViewsTest(TestCase):
    """اختبارات الواجهات"""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        
        self.department = Department.objects.create(code='IT', name_ar='IT')
        self.job_title = JobTitle.objects.create(code='DEV', title_ar='Dev', department=self.department)
    
    def test_dashboard_view(self):
        """اختبار Dashboard"""
        response = self.client.get(reverse('hr:dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_employee_list_view(self):
        """اختبار قائمة الموظفين"""
        response = self.client.get(reverse('hr:employee_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_department_list_view(self):
        """اختبار قائمة الأقسام"""
        response = self.client.get(reverse('hr:department_list'))
        self.assertEqual(response.status_code, 200)
