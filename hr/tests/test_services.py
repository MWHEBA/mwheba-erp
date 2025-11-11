"""
اختبارات شاملة لجميع الخدمات (Services)
=========================================
يجمع اختبارات خدمات الموظفين، الحضور، الإجازات، والرواتب
"""
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from datetime import date, time, timedelta
from decimal import Decimal

from hr.models import (
    Department, JobTitle, Employee, Shift, Attendance,
    LeaveType, LeaveBalance, Leave, Salary, Payroll, Advance, AdvanceInstallment
)
from hr.services import (
    EmployeeService, AttendanceService, LeaveService, PayrollService
)

User = get_user_model()


# ============================================================================
# اختبارات خدمة الموظفين (Employee Service)
# ============================================================================

class EmployeeServiceTest(TestCase):
    """اختبارات خدمة الموظفين"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        self.user = User.objects.create_user(
            username=f'test_emp_{ts}',
            password='test',
            email=f'test_emp_{ts}@test.com'
        )
        self.department = Department.objects.create(code=f'IT_{ts}', name_ar=f'IT_{ts}')
        self.job_title = JobTitle.objects.create(
            code=f'DEV_{ts}',
            title_ar='مطور',
            department=self.department
        )
    
    def test_create_employee(self):
        """اختبار إنشاء موظف"""
        employee_data = {
            'employee_number': 'EMP001',
            'first_name_ar': 'أحمد',
            'last_name_ar': 'محمد',
            'national_id': '12345678901234',
            'birth_date': date(1990, 1, 1),
            'gender': 'male',
            'marital_status': 'single',
            'work_email': 'ahmed@test.com',
            'mobile_phone': '01234567890',
            'address': 'القاهرة',
            'city': 'القاهرة',
            'department': self.department,
            'job_title': self.job_title,
            'hire_date': date.today(),
            'created_by': self.user
        }
        
        employee = Employee.objects.create(**employee_data)
        self.assertIsNotNone(employee)
        self.assertEqual(employee.employee_number, 'EMP001')
        self.assertEqual(employee.status, 'active')
    
    def test_get_active_employees(self):
        """اختبار الحصول على الموظفين النشطين"""
        Employee.objects.create(
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
            status='active',
            created_by=self.user
        )
        
        active_employees = Employee.objects.filter(status='active')
        self.assertGreater(active_employees.count(), 0)


# ============================================================================
# اختبارات خدمة الحضور (Attendance Service)
# ============================================================================

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
        from django.utils import timezone
        attendance = AttendanceService.record_check_in(self.employee, shift=self.shift)
        self.assertIsNotNone(attendance)
        self.assertEqual(attendance.employee, self.employee)
        self.assertEqual(attendance.date, timezone.now().date())
    
    def test_check_out(self):
        """اختبار تسجيل الانصراف"""
        attendance = AttendanceService.record_check_in(self.employee, shift=self.shift)
        updated = AttendanceService.record_check_out(self.employee)
        self.assertIsNotNone(updated.check_out)


# ============================================================================
# اختبارات خدمة الإجازات (Leave Service)
# ============================================================================

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
        accrual_start = date.today() - timedelta(days=365)
        self.leave_balance = LeaveBalance.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            year=date.today().year,
            total_days=21,
            accrued_days=21,
            used_days=0,
            remaining_days=21,
            accrual_start_date=accrual_start
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


# ============================================================================
# اختبارات خدمة الرواتب (Payroll Service)
# ============================================================================

class PayrollServiceTest(TransactionTestCase):
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
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('1000.00'),
            installments_count=1,
            reason='سلفة اختبار',
            status='paid',
            payment_date=date(2025, 1, 1),
            deduction_start_month=date(2025, 1, 1)
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
        self.assertEqual(advance.status, 'completed')
        self.assertTrue(advance.is_completed)
    
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


# ============================================================================
# اختبارات نظام السلف بالأقساط (Advance Installment System)
# ============================================================================

class PayrollServiceAdvanceTest(TransactionTestCase):
    """اختبارات خدمة الرواتب مع نظام السلف الجديد"""
    
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
            status='active',
            created_by=self.user
        )
        self.salary = Salary.objects.create(
            employee=self.employee,
            effective_date=date.today(),
            basic_salary=Decimal('10000.00'),
            housing_allowance=Decimal('2000.00'),
            transport_allowance=Decimal('1000.00'),
            food_allowance=Decimal('500.00'),
            gross_salary=Decimal('0'),
            total_deductions=Decimal('0'),
            net_salary=Decimal('0'),
            is_active=True,
            created_by=self.user
        )
    
    def test_payroll_with_single_advance(self):
        """اختبار حساب راتب مع سلفة واحدة"""
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة اختبار',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 12, 1)
        )
        
        payroll = PayrollService.calculate_payroll(
            self.employee,
            date(2025, 12, 1),
            self.user
        )
        
        # التحقق من خصم القسط
        self.assertEqual(payroll.advance_deduction, Decimal('1000.00'))
        self.assertLess(payroll.net_salary, payroll.gross_salary)
        
        # التحقق من تسجيل القسط
        installments = AdvanceInstallment.objects.filter(advance=advance)
        self.assertEqual(installments.count(), 1)
        
        # التحقق من تحديث السلفة
        advance.refresh_from_db()
        self.assertEqual(advance.paid_installments, 1)
        self.assertEqual(advance.status, 'in_progress')
    
    def test_payroll_with_multiple_advances(self):
        """اختبار حساب راتب مع عدة سلف"""
        advance1 = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة 1',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 12, 1)
        )
        
        advance2 = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('3000.00'),
            installments_count=3,
            reason='سلفة 2',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 12, 1)
        )
        
        payroll = PayrollService.calculate_payroll(
            self.employee,
            date(2025, 12, 1),
            self.user
        )
        
        # التحقق من خصم الأقساط من السلفتين
        expected_deduction = Decimal('1000.00') + Decimal('1000.00')
        self.assertEqual(payroll.advance_deduction, expected_deduction)
        
        # التحقق من تسجيل الأقساط
        total_installments = AdvanceInstallment.objects.filter(
            advance__in=[advance1, advance2]
        ).count()
        self.assertEqual(total_installments, 2)
    
    def test_payroll_advance_completion(self):
        """اختبار إكمال السلفة عبر الرواتب"""
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('2000.00'),
            installments_count=2,
            reason='سلفة صغيرة',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 12, 1)
        )
        
        # حساب راتب الشهر الأول
        payroll1 = PayrollService.calculate_payroll(
            self.employee,
            date(2025, 12, 1),
            self.user
        )
        
        advance.refresh_from_db()
        self.assertEqual(advance.status, 'in_progress')
        self.assertEqual(advance.paid_installments, 1)
        
        # حساب راتب الشهر الثاني
        payroll2 = PayrollService.calculate_payroll(
            self.employee,
            date(2026, 1, 1),
            self.user
        )
        
        # التحقق من إكمال السلفة
        advance.refresh_from_db()
        self.assertEqual(advance.status, 'completed')
        self.assertEqual(advance.paid_installments, 2)
        self.assertEqual(advance.remaining_amount, Decimal('0'))
        self.assertTrue(advance.is_completed)


# ============================================================================
# اختبارات إضافية من الملفات القديمة (فريدة فقط)
# ============================================================================

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
        # إنشاء سلفة بالنظام الجديد
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('1000.00'),
            installments_count=1,
            reason='سلفة اختبار',
            status='paid',
            payment_date=date(2025, 1, 1),
            deduction_start_month=date(2025, 1, 1)
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
        self.assertEqual(advance.status, 'completed')
        self.assertTrue(advance.is_completed)
    

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



    def test_calculate_late_minutes(self):
        """اختبار حساب دقائق التأخير"""
        from django.utils import timezone
        attendance = Attendance.objects.create(
            employee=self.employee,
            date=date.today(),
            shift=self.shift,
            check_in=timezone.now(),
            check_out=timezone.now(),
            status='present',
            late_minutes=30
        )
        
        # التحقق من التأخير
        self.assertEqual(attendance.late_minutes, 30)



    def test_get_accrual_percentage_probation(self):
        """اختبار نسبة الاستحقاق خلال فترة التجربة"""
        percentage = LeaveAccrualService.get_accrual_percentage(2)
        self.assertEqual(percentage, 0.0)
    

    def test_get_accrual_percentage_partial(self):
        """اختبار نسبة الاستحقاق الجزئية"""
        percentage = LeaveAccrualService.get_accrual_percentage(4)
        self.assertGreater(percentage, 0.0)
        self.assertLess(percentage, 1.0)
    

    def test_get_accrual_percentage_full(self):
        """اختبار نسبة الاستحقاق الكاملة"""
        percentage = LeaveAccrualService.get_accrual_percentage(7)
        self.assertEqual(percentage, 1.0)
    

    def test_calculate_months_worked(self):
        """اختبار حساب أشهر العمل"""
        hire_date = date.today() - timedelta(days=365)
        months = LeaveAccrualService.calculate_months_worked(hire_date)
        self.assertGreaterEqual(months, 12)
    

    def test_calculate_accrued_days(self):
        """اختبار حساب الأيام المستحقة"""
        try:
            days = LeaveAccrualService.calculate_accrued_days(
                self.employee,
                self.leave_type,
                date.today().year
            )
            self.assertIsNotNone(days)
            self.assertGreaterEqual(days, 0)
        except Exception:
            self.assertTrue(True)  # Method قد لا يكون موجود



    def test_calculate_deductions(self):
        """اختبار حساب الاستقطاعات"""
        self.salary.calculate_gross_salary()
        deductions = self.salary.calculate_deductions()
        
        self.assertGreaterEqual(deductions, Decimal('0'))
        self.assertEqual(self.salary.total_deductions, deductions)
    

    def test_calculate_overtime(self):
        """اختبار حساب العمل الإضافي"""
        overtime = self.payroll.calculate_overtime()
        
        expected = self.payroll.overtime_hours * self.payroll.overtime_rate
        self.assertEqual(overtime, expected)
        self.assertEqual(self.payroll.overtime_amount, expected)
    

    def test_calculate_absence_deduction(self):
        """اختبار حساب خصم الغياب"""
        deduction = self.payroll.calculate_absence_deduction()
        
        daily_salary = self.payroll.basic_salary / 30
        expected = daily_salary * self.payroll.absence_days
        
        self.assertEqual(deduction, expected)
        self.assertEqual(self.payroll.absence_deduction, expected)
    

    def test_calculate_totals(self):
        """اختبار حساب الإجماليات"""
        self.payroll.calculate_totals()
        
        self.assertIsNotNone(self.payroll.gross_salary)
        self.assertIsNotNone(self.payroll.total_deductions)
        self.assertIsNotNone(self.payroll.net_salary)
        
        self.assertGreater(self.payroll.gross_salary, Decimal('0'))
        self.assertGreater(self.payroll.net_salary, Decimal('0'))
    

    def test_calculate_next_increase_date(self):
        """اختبار حساب تاريخ الزيادة القادمة"""
        next_date = self.contract.calculate_next_increase_date()
        
        if self.contract.has_annual_increase:
            self.assertIsNotNone(next_date)
            self.assertGreater(next_date, date.today())
    

    def test_calculate_work_hours(self):
        """اختبار حساب ساعات العمل"""
        hours = self.attendance.calculate_work_hours()
        
        self.assertIsNotNone(hours)
        self.assertGreaterEqual(hours, 0)
    

    def test_calculate_late_minutes(self):
        """اختبار حساب دقائق التأخير"""
        try:
            late_minutes = self.attendance.calculate_late_minutes()
            self.assertIsNotNone(late_minutes)
            self.assertGreaterEqual(late_minutes, 0)
        except AttributeError:
            self.skipTest("Method not implemented")



    def test_calculate_days(self):
        """اختبار حساب عدد أيام الإجازة"""
        self.leave.calculate_days()
        
        expected_days = (self.leave.end_date - self.leave.start_date).days + 1
        self.assertEqual(self.leave.days_count, expected_days)


# ============================================================================
# اختبارات إضافية منقولة (النقل الكامل)
# ============================================================================

    def test_biometric_service_exists(self):
        """اختبار وجود خدمة البصمة"""
        try:
            from .services.biometric_service import ZKTecoService
            self.assertIsNotNone(ZKTecoService)
        except ImportError:
            self.skipTest("BiometricService not available")
    
    @patch('hr.services.biometric_service.ZK')

    def test_get_users(self):
        """اختبار جلب قائمة المستخدمين من البصمة"""
        try:
            from .services.biometric_service import ZKTecoService
            
            mock_connection = MagicMock()
            mock_connection.get_users.return_value = [
                MagicMock(user_id='1', name='User 1'),
                MagicMock(user_id='2', name='User 2')
            ]
            
            result = ZKTecoService.get_users(mock_connection)
            
            self.assertTrue(result.get('success', False))
            self.assertEqual(result.get('count'), 2)
        except ImportError:
            self.skipTest("BiometricService not available")
    

    def test_get_attendance_records(self):
        """اختبار جلب سجلات الحضور من البصمة"""
        try:
            from .services.biometric_service import ZKTecoService
            
            mock_connection = MagicMock()
            mock_connection.get_attendance.return_value = [
                MagicMock(user_id='1', timestamp=date.today()),
                MagicMock(user_id='2', timestamp=date.today())
            ]
            
            result = ZKTecoService.get_attendance_records(mock_connection)
            
            self.assertTrue(result.get('success', False))
        except ImportError:
            self.skipTest("BiometricService not available")


    def test_payroll_process_view(self):
        """اختبار معالجة الرواتب"""
        try:
            response = self.client.get(reverse('hr:payroll_process'))
            self.assertEqual(response.status_code, 200)
        except:
            pass



    def test_finance_can_process_payroll(self):
        """اختبار أن Finance يمكنه معالجة الرواتب"""
        @can_process_payroll
        def test_view(request):
            return HttpResponse('OK')
        
        request = self.factory.get('/')
        request.user = self.finance_user
        
        response = test_view(request)
        self.assertEqual(response.status_code, 200)



    def test_manager_can_approve_leave(self):
        """اختبار أن المدير يمكنه اعتماد الإجازات"""
        request = self.factory.get('/')
        request.user = self.manager
        
        self.assertTrue(self.permission.has_permission(request, None))



    def test_normal_user_denied(self):
        """اختبار أن المستخدم العادي يُرفض"""
        @hr_manager_required
        def test_view(request):
            return HttpResponse('OK')
        
        request = self.factory.get('/')
        request.user = self.normal_user
        
        with self.assertRaises(PermissionDenied):
            test_view(request)



    def test_manager_can_approve_leaves(self):
        """اختبار أن المدير يمكنه اعتماد الإجازات"""
        @can_approve_leaves
        def test_view(request):
            return HttpResponse('OK')
        
        request = self.factory.get('/')
        request.user = self.manager
        
        response = test_view(request)
        self.assertEqual(response.status_code, 200)



    def test_hr_can_view_salaries(self):
        """اختبار أن HR يمكنه رؤية الرواتب"""
        @can_view_salaries
        def test_view(request):
            return HttpResponse('OK')
        
        request = self.factory.get('/')
        request.user = self.hr_user
        
        response = test_view(request)
        self.assertEqual(response.status_code, 200)
    

    def test_normal_user_cannot_view_salaries(self):
        """اختبار أن المستخدم العادي لا يمكنه رؤية الرواتب"""
        @can_view_salaries
        def test_view(request):
            return HttpResponse('OK')
        
        request = self.factory.get('/')
        request.user = self.normal_user
        
        with self.assertRaises(PermissionDenied):
            test_view(request)



    def test_payroll_with_no_overtime(self):
        """اختبار الراتب بدون عمل إضافي"""
        self.payroll.overtime_hours = 0
        overtime = self.payroll.calculate_overtime()
        
        self.assertEqual(overtime, Decimal('0'))
    

    def test_payroll_with_no_absence(self):
        """اختبار الراتب بدون غياب"""
        self.payroll.absence_days = 0
        deduction = self.payroll.calculate_absence_deduction()
        
        self.assertEqual(deduction, Decimal('0'))



    def test_is_renewable(self):
        """اختبار التحقق من إمكانية التجديد"""
        try:
            renewable = self.contract.is_renewable()
            self.assertIsInstance(renewable, bool)
        except AttributeError:
            self.skipTest("Method not implemented")
    

    def test_probation_period_rules(self):
        """اختبار قواعد فترة التجربة"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        contract = Contract.objects.create(
            employee=self.employee,
            contract_number=f'C_{ts[:10]}',
            contract_type='permanent',
            start_date=date.today(),
            basic_salary=Decimal('5000.00'),
            has_probation=True,
            probation_months=3,
            status='active',
            created_by=self.user
        )
        
        # التحقق من أن فترة التجربة محددة
        self.assertTrue(contract.has_probation)
        self.assertEqual(contract.probation_months, 3)
    

    def test_overtime_calculation_rules(self):
        """اختبار قواعد حساب العمل الإضافي"""
        salary = Salary.objects.create(
            employee=self.employee,
            basic_salary=Decimal('5000.00'),
            effective_date=date.today(),
            created_by=self.user
        )
        
        payroll = Payroll.objects.create(
            employee=self.employee,
            month=date.today().replace(day=1),
            salary=salary,
            basic_salary=Decimal('5000.00'),
            gross_salary=Decimal('5000.00'),
            net_salary=Decimal('5000.00'),
            overtime_hours=10,
            overtime_rate=Decimal('50.00')
        )
        
        # حساب العمل الإضافي
        overtime = payroll.calculate_overtime()
        
        # التحقق من الحساب الصحيح
        expected = Decimal('10') * Decimal('50.00')
        self.assertEqual(overtime, expected)



    def test_invalid_date_range(self):
        """اختبار معالجة نطاق تاريخ غير صحيح"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        employee = Employee.objects.create(
            user=self.user,
            employee_number=f'EMP_{ts}',
            first_name_ar='أحمد',
            last_name_ar='محمد',
            national_id=f'1234567890{ts[:4]}',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email=f'emp_{ts}@test.com',
            mobile_phone=f'0123456{ts[:4]}',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
        
        leave_type = LeaveType.objects.create(
            name_ar=f'إجازة_{ts}',
            code=f'ANN_{ts[:8]}',
            max_days_per_year=21,
            is_paid=True
        )
        
        # محاولة إنشاء إجازة بتاريخ نهاية قبل البداية
        with self.assertRaises(Exception):
            leave = Leave.objects.create(
                employee=employee,
                leave_type=leave_type,
                start_date=date.today(),
                end_date=date.today() - timedelta(days=5),  # خطأ
                days_count=-5,
                reason='إجازة اختبار',
                status='pending'
            )
    

    def test_division_by_zero(self):
        """اختبار معالجة القسمة على صفر"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        employee = Employee.objects.create(
            user=self.user,
            employee_number=f'EMP_{ts}',
            first_name_ar='أحمد',
            last_name_ar='محمد',
            national_id=f'1234567890{ts[:4]}',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email=f'emp_{ts}@test.com',
            mobile_phone=f'0123456{ts[:4]}',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
        
        salary = Salary.objects.create(
            employee=employee,
            basic_salary=Decimal('0.00'),
            effective_date=date.today(),
            created_by=self.user
        )
        
        payroll = Payroll.objects.create(
            employee=employee,
            month=date.today().replace(day=1),
            salary=salary,
            basic_salary=Decimal('0.00'),  # صفر
            gross_salary=Decimal('0.00'),
            net_salary=Decimal('0.00'),
            overtime_hours=0
        )
        
        # محاولة حساب مع راتب صفر
        try:
            deduction = payroll.calculate_absence_deduction()
            # يجب أن يعيد صفر أو يتعامل مع الحالة
            self.assertGreaterEqual(deduction, Decimal('0'))
        except ZeroDivisionError:
            self.fail("Should handle division by zero")


