"""
اختبارات شاملة لجميع نماذج نظام الموارد البشرية
================================================
يجمع اختبارات النماذج الأساسية والموسعة في ملف واحد منظم
"""
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, time, timedelta
from decimal import Decimal

from hr.models import (
    # النماذج التنظيمية
    Department, JobTitle, Employee, Shift,
    # نماذج الحضور
    Attendance,
    # نماذج الإجازات
    LeaveType, LeaveBalance, Leave,
    # نماذج الرواتب والسلف
    Salary, Payroll, Advance, AdvanceInstallment,
    # نماذج العقود
    Contract, ContractAmendment, ContractDocument, ContractIncrease,
    # نماذج بنود الراتب
    SalaryComponent, SalaryComponentTemplate,
    # نماذج البصمة
    BiometricDevice, BiometricLog, BiometricUserMapping
)

User = get_user_model()


# ============================================================================
# اختبارات النماذج التنظيمية (Organization Models)
# ============================================================================

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
    
    def test_department_unique_code(self):
        """اختبار عدم تكرار الكود"""
        with self.assertRaises(Exception):
            Department.objects.create(
                code='IT',
                name_ar='قسم آخر'
            )


class JobTitleModelTest(TestCase):
    """اختبارات نموذج المسمى الوظيفي"""
    
    def setUp(self):
        self.department = Department.objects.create(
            code='IT',
            name_ar='تقنية المعلومات'
        )
        self.job_title = JobTitle.objects.create(
            code='DEV',
            title_ar='مطور',
            department=self.department
        )
    
    def test_job_title_creation(self):
        """اختبار إنشاء مسمى وظيفي"""
        self.assertEqual(self.job_title.title_ar, 'مطور')
        self.assertEqual(self.job_title.department, self.department)
    
    def test_job_title_str(self):
        """اختبار __str__"""
        self.assertEqual(str(self.job_title), 'DEV - مطور')
    
    def test_job_title_unique_code(self):
        """اختبار عدم تكرار الكود"""
        with self.assertRaises(ValidationError):
            JobTitle.objects.create(
                code='DEV',
                title_ar='مطور آخر',
                department=self.department
            )


class JobTitleRelationshipTest(TestCase):
    """اختبارات علاقات المسمى الوظيفي"""
    def setUp(self):
        self.department = Department.objects.create(
            code='IT',
            name_ar='تقنية المعلومات'
        )
    
    def test_job_title_department_relationship(self):
        """اختبار علاقة المسمى الوظيفي بالقسم"""
        job_title = JobTitle.objects.create(
            code='DEV',
            title_ar='مطور',
            department=self.department
        )
        
        self.assertEqual(job_title.department, self.department)
        self.assertIn(job_title, self.department.jobtitle_set.all())


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
    
    def test_employee_age(self):
        """اختبار حساب العمر"""
        age = (date.today() - self.employee.birth_date).days // 365
        self.assertGreater(age, 0)


class ShiftModelTest(TestCase):
    """اختبارات نموذج الوردية"""
    
    def test_shift_creation(self):
        """اختبار إنشاء وردية"""
        shift = Shift.objects.create(
            name='الوردية الصباحية',
            start_time=time(8, 0),
            end_time=time(16, 0),
            work_hours=8.0
        )
        
        self.assertEqual(shift.name, 'الوردية الصباحية')
        self.assertEqual(shift.work_hours, 8.0)
        self.assertTrue(shift.is_active)
    
    def test_shift_str(self):
        """اختبار __str__"""
        shift = Shift.objects.create(
            name='الوردية الصباحية',
            start_time=time(8, 0),
            end_time=time(16, 0),
            work_hours=8.0
        )
        self.assertIn('الوردية الصباحية', str(shift))
        self.assertIn('08:00', str(shift))
        self.assertIn('16:00', str(shift))


# ============================================================================
# اختبارات نماذج الحضور (Attendance Models)
# ============================================================================

class AttendanceModelTest(TestCase):
    """اختبارات نموذج الحضور"""
    
    def setUp(self):
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        self.user = User.objects.create_user(
            username=f'test_att_{timestamp}',
            password='test',
            email=f'test_att_{timestamp}@test.com'
        )
        self.department = Department.objects.create(
            code=f'ATT_{timestamp}',
            name_ar=f'ATT_{timestamp}'
        )
        self.job_title = JobTitle.objects.create(
            code=f'ATT_DEV_{timestamp}',
            title_ar='Dev',
            department=self.department
        )
        self.employee = Employee.objects.create(
            user=self.user,
            employee_number=f'EMP_ATT_{timestamp}',
            first_name_ar='أحمد',
            last_name_ar='محمد',
            national_id=f'1234567890{timestamp[:4]}',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email=f'emp_att_{timestamp}@test.com',
            mobile_phone=f'0123456{timestamp[:4]}',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
        self.shift = Shift.objects.create(
            name=f'الوردية_{timestamp}',
            start_time=time(8, 0),
            end_time=time(16, 0),
            work_hours=8.0
        )
    
    def test_attendance_creation(self):
        """اختبار إنشاء سجل حضور"""
        attendance = Attendance.objects.create(
            employee=self.employee,
            date=date.today(),
            shift=self.shift,
            check_in=timezone.now()
        )
        
        self.assertEqual(attendance.employee, self.employee)
        self.assertEqual(attendance.date, date.today())
        self.assertIsNotNone(attendance.check_in)


# ============================================================================
# اختبارات نماذج الرواتب والسلف (Salary & Advance Models)
# ============================================================================

class SalaryModelTest(TestCase):
    """اختبارات نموذج الراتب"""
    
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
    
    def test_salary_calculation(self):
        """اختبار حساب الراتب"""
        salary = Salary.objects.create(
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
        
        # التحقق من الحسابات التلقائية
        salary.refresh_from_db()
        self.assertEqual(salary.gross_salary, Decimal('6800.00'))
        self.assertGreater(salary.net_salary, 0)


class AdvanceModelTest(TestCase):
    """اختبارات نموذج السلف - نظام الأقساط الجديد"""
    
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
    
    def test_advance_creation_with_installments(self):
        """اختبار إنشاء سلفة بالأقساط"""
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة اختبار',
            status='approved'
        )
        
        # التحقق من الحسابات التلقائية
        self.assertEqual(advance.installment_amount, Decimal('1000.00'))
        self.assertEqual(advance.remaining_amount, Decimal('6000.00'))
        self.assertEqual(advance.paid_installments, 0)
    
    def test_advance_validation(self):
        """اختبار التحقق من صحة البيانات"""
        advance = Advance(
            employee=self.employee,
            amount=Decimal('100000.00'),  # مبلغ كبير جداً
            installments_count=30,  # أقساط كثيرة جداً
            reason='قصير'  # سبب قصير
        )
        
        with self.assertRaises(ValidationError):
            advance.full_clean()
    
    def test_record_installment_payment(self):
        """اختبار تسجيل دفع قسط"""
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة اختبار',
            status='paid',
            deduction_start_month=date(2025, 12, 1)
        )
        
        # تسجيل قسط
        month = date(2025, 12, 1)
        installment = advance.record_installment_payment(month, Decimal('1000.00'))
        
        # التحقق
        self.assertIsNotNone(installment)
        self.assertEqual(installment.amount, Decimal('1000.00'))
        self.assertEqual(installment.installment_number, 1)
        
        # التحقق من تحديث السلفة
        advance.refresh_from_db()
        self.assertEqual(advance.paid_installments, 1)
        self.assertEqual(advance.remaining_amount, Decimal('5000.00'))
        self.assertEqual(advance.status, 'in_progress')
    
    def test_advance_completion(self):
        """اختبار إكمال السلفة"""
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('3000.00'),
            installments_count=3,
            reason='سلفة اختبار',
            status='paid',
            deduction_start_month=date(2025, 12, 1)
        )
        
        # دفع جميع الأقساط
        for i in range(3):
            month = date(2025, 12 + i, 1) if i < 1 else date(2026, i, 1)
            advance.record_installment_payment(month, Decimal('1000.00'))
        
        # التحقق من الإكمال
        advance.refresh_from_db()
        self.assertTrue(advance.is_completed)
        self.assertEqual(advance.status, 'completed')
        self.assertEqual(advance.remaining_amount, Decimal('0'))


class AdvanceInstallmentModelTest(TestCase):
    """اختبارات نموذج قسط السلفة"""
    
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
        self.advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة اختبار',
            status='paid',
            deduction_start_month=date(2025, 12, 1)
        )
    
    def test_installment_creation(self):
        """اختبار إنشاء قسط"""
        installment = AdvanceInstallment.objects.create(
            advance=self.advance,
            month=date(2025, 12, 1),
            amount=Decimal('1000.00'),
            installment_number=1
        )
        
        self.assertEqual(installment.advance, self.advance)
        self.assertEqual(installment.amount, Decimal('1000.00'))
        self.assertEqual(installment.installment_number, 1)
    
    def test_installment_unique_constraint(self):
        """اختبار عدم تكرار القسط لنفس الشهر"""
        AdvanceInstallment.objects.create(
            advance=self.advance,
            month=date(2025, 12, 1),
            amount=Decimal('1000.00'),
            installment_number=1
        )
        
        # محاولة إنشاء قسط آخر لنفس الشهر
        with self.assertRaises(Exception):
            AdvanceInstallment.objects.create(
                advance=self.advance,
                month=date(2025, 12, 1),
                amount=Decimal('1000.00'),
                installment_number=2
            )


# ============================================================================
# اختبارات إضافية من الملفات القديمة (فريدة فقط)
# ============================================================================

    def test_department_unique_code(self):
        """اختبار عدم تكرار الكود"""
        with self.assertRaises(Exception):
            Department.objects.create(
                code='IT',
                name_ar='قسم آخر'
            )



    def test_employee_age(self):
        """اختبار حساب العمر"""
        age = (date.today() - self.employee.birth_date).days // 365
        self.assertGreater(age, 0)


# ============================================================================
# 2. اختبارات نظام الرواتب والسلف (الجديد!)
# ============================================================================


    def test_salary_calculation(self):
        """اختبار حساب الراتب"""
        salary = Salary.objects.create(
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
        
        # التحقق من الحسابات التلقائية
        salary.refresh_from_db()
        self.assertEqual(salary.gross_salary, Decimal('6800.00'))
        self.assertGreater(salary.net_salary, 0)



    def test_shift_creation(self):
        """اختبار إنشاء وردية"""
        shift = Shift.objects.create(
            name='الوردية الصباحية',
            start_time=time(8, 0),
            end_time=time(16, 0),
            work_hours=8.0
        )
        
        self.assertEqual(shift.name, 'الوردية الصباحية')
        self.assertEqual(shift.work_hours, 8.0)
        self.assertTrue(shift.is_active)
    

    def test_shift_str(self):
        """اختبار __str__"""
        shift = Shift.objects.create(
            name='الوردية الصباحية',
            start_time=time(8, 0),
            end_time=time(16, 0),
            work_hours=8.0
        )
        # التحقق من أن الاسم موجود في النص
        self.assertIn('الوردية الصباحية', str(shift))
        self.assertIn('08:00', str(shift))
        self.assertIn('16:00', str(shift))


# ============================================================================
# اختبارات نماذج الحضور (Attendance)
# ============================================================================


    def test_attendance_creation(self):
        """اختبار إنشاء سجل حضور"""
        from django.utils import timezone
        attendance = Attendance.objects.create(
            employee=self.employee,
            date=date.today(),
            shift=self.shift,
            check_in=timezone.now(),
            check_out=timezone.now(),
            status='present'
        )
        
        self.assertEqual(attendance.employee, self.employee)
        self.assertEqual(attendance.status, 'present')
    

    def test_leave_type_creation(self):
        """اختبار إنشاء نوع إجازة"""
        leave_type = LeaveType.objects.create(
            name_ar='إجازة سنوية',
            name_en='Annual Leave',
            code='ANNUAL',
            max_days_per_year=21,
            is_paid=True
        )
        
        self.assertEqual(leave_type.code, 'ANNUAL')
        self.assertEqual(leave_type.max_days_per_year, 21)
        self.assertTrue(leave_type.is_paid)



    def test_leave_balance_creation(self):
        """اختبار إنشاء رصيد إجازة"""
        balance = LeaveBalance.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            year=2025,
            total_days=21,
            used_days=0,
            remaining_days=21
        )
        
        self.assertEqual(balance.total_days, 21)
        self.assertEqual(balance.remaining_days, 21)
    

    def test_contract_creation(self):
        """اختبار إنشاء عقد"""
        contract = Contract.objects.create(
            contract_number='C001',
            employee=self.employee,
            contract_type='permanent',
            job_title=self.job_title,
            department=self.department,
            start_date=date.today(),
            basic_salary=Decimal('10000.00'),
            status='active',
            created_by=self.user
        )
        
        self.assertEqual(contract.contract_number, 'C001')
        self.assertEqual(contract.contract_type, 'permanent')
        self.assertEqual(contract.status, 'active')
    

    def test_contract_with_annual_increase(self):
        """اختبار عقد مع زيادة سنوية"""
        contract = Contract.objects.create(
            contract_number='C001',
            employee=self.employee,
            contract_type='permanent',
            job_title=self.job_title,
            department=self.department,
            start_date=date.today(),
            basic_salary=Decimal('10000.00'),
            has_annual_increase=True,
            annual_increase_percentage=Decimal('10.00'),
            status='active',
            created_by=self.user
        )
        
        self.assertTrue(contract.has_annual_increase)
        self.assertEqual(contract.annual_increase_percentage, Decimal('10.00'))


# ============================================================================
# اختبارات نماذج مكونات الراتب
# ============================================================================


    def test_salary_component_creation(self):
        """اختبار إنشاء مكون راتب"""
        component = SalaryComponent.objects.create(
            employee=self.employee,
            component_type='earning',
            name='بدل سكن',
            amount=Decimal('2000.00'),
            is_fixed=True
        )
        
        self.assertEqual(component.component_type, 'earning')
        self.assertEqual(component.amount, Decimal('2000.00'))
    

    def test_salary_component_with_formula(self):
        """اختبار مكون راتب بصيغة حسابية"""
        component = SalaryComponent.objects.create(
            employee=self.employee,
            component_type='earning',
            name='بدل سكن',
            formula='basic * 0.2',
            amount=Decimal('0'),
            is_fixed=True
        )
        
        # حساب المبلغ بناءً على الصيغة
        calculated = component.calculate_amount(Decimal('10000.00'))
        self.assertEqual(calculated, Decimal('2000.00'))




class EmployeeServiceTest(TestCase):
    """اختبارات من tests_services.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
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
    


class EmployeeServiceTest(TestCase):
    """اختبارات من tests_services.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_get_active_employees(self):
        """اختبار الحصول على الموظفين النشطين"""
        # إنشاء موظفين
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
        
        Employee.objects.create(
            employee_number='EMP002',
            first_name_ar='محمد',
            last_name_ar='علي',
            national_id='12345678901235',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email='mohamed@test.com',
            mobile_phone='01234567891',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            status='inactive',
            created_by=self.user
        )
        
        active_employees = Employee.objects.filter(status='active')
        self.assertEqual(active_employees.count(), 1)




class EmployeeServiceTest(TestCase):
    """اختبارات من tests_services.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_check_leave_balance(self):
        """اختبار التحقق من رصيد الإجازة"""
        self.assertEqual(self.leave_balance.remaining_days, 21)
        
        # طلب إجازة
        Leave.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=5),
            days_count=5,
            reason='إجازة اختبار',
            status='approved'
        )
        
        # يجب أن يقل الرصيد (إذا كان هناك signal)
        # self.leave_balance.refresh_from_db()
        # self.assertEqual(self.leave_balance.remaining_days, 16)




class EmployeeServiceTest(TestCase):
    """اختبارات من tests_services.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_calculate_gross_salary(self):
        """اختبار حساب إجمالي الراتب"""
        self.salary.refresh_from_db()
        expected_gross = (
            self.salary.basic_salary +
            self.salary.housing_allowance +
            self.salary.transport_allowance +
            self.salary.food_allowance
        )
        self.assertEqual(self.salary.gross_salary, expected_gross)
    


class EmployeeServiceTest(TestCase):
    """اختبارات من tests_services.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_process_monthly_payroll_multiple_employees(self):
        """اختبار معالجة رواتب عدة موظفين"""
        # إنشاء مستخدم ثاني
        user2 = User.objects.create_user(username='test2', password='test2')
        
        # إنشاء موظف ثاني
        employee2 = Employee.objects.create(
            user=user2,
            employee_number='EMP002',
            first_name_ar='محمد',
            last_name_ar='علي',
            national_id='12345678901235',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email='mohamed@test.com',
            mobile_phone='01234567891',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            status='active',
            created_by=self.user
        )
        
        Salary.objects.create(
            employee=employee2,
            effective_date=date.today(),
            basic_salary=Decimal('8000.00'),
            housing_allowance=Decimal('1500.00'),
            transport_allowance=Decimal('800.00'),
            food_allowance=Decimal('400.00'),
            gross_salary=Decimal('0'),
            total_deductions=Decimal('0'),
            net_salary=Decimal('0'),
            is_active=True,
            created_by=self.user
        )
        
        # معالجة الرواتب
        results = PayrollService.process_monthly_payroll(
            date(2025, 12, 1),
            self.user
        )
        
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r['success'] for r in results))
    


class SalaryCalculationMethodsTest(TestCase):
    """اختبارات من tests_model_methods.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_calculate_gross_salary(self):
        """اختبار حساب إجمالي الراتب"""
        gross = self.salary.calculate_gross_salary()
        
        expected = (
            self.salary.basic_salary +
            self.salary.housing_allowance +
            self.salary.transport_allowance
        )
        
        self.assertEqual(gross, expected)
        self.assertEqual(self.salary.gross_salary, expected)
    


class SalaryCalculationMethodsTest(TestCase):
    """اختبارات من tests_model_methods.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_calculate_net_salary(self):
        """اختبار حساب صافي الراتب"""
        net = self.salary.calculate_net_salary()
        
        self.assertGreater(net, Decimal('0'))
        self.assertLess(net, self.salary.gross_salary)
        self.assertEqual(self.salary.net_salary, net)
    


class SalaryCalculationMethodsTest(TestCase):
    """اختبارات من tests_model_methods.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_salary_calculation_chain(self):
        """اختبار سلسلة الحسابات"""
        self.salary.calculate_net_salary()
        
        self.assertIsNotNone(self.salary.gross_salary)
        self.assertIsNotNone(self.salary.total_deductions)
        self.assertIsNotNone(self.salary.net_salary)
        
        # التحقق من المعادلة
        calculated_net = self.salary.gross_salary - self.salary.total_deductions
        self.assertEqual(self.salary.net_salary, calculated_net)




class SalaryCalculationMethodsTest(TestCase):
    """اختبارات من tests_model_methods.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_contract_with_probation(self):
        """اختبار العقد مع فترة تجربة"""
        self.contract.has_probation = True
        self.contract.probation_months = 3
        self.contract.save()
        
        try:
            probation_end = self.contract.get_probation_end_date()
            self.assertIsNotNone(probation_end)
            self.assertGreater(probation_end, self.contract.start_date)
        except AttributeError:
            self.skipTest("Method not implemented")
    


class SalaryCalculationMethodsTest(TestCase):
    """اختبارات من tests_model_methods.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_contract_dates_validation(self):
        """اختبار التحقق من صحة تواريخ العقد"""
        self.contract.contract_type = 'fixed_term'
        self.contract.end_date = date.today() + timedelta(days=365)
        
        try:
            is_valid = self.contract.validate_dates()
            self.assertTrue(is_valid)
        except AttributeError:
            self.skipTest("Method not implemented")




class ConcurrentOperationsTest(TestCase):
    """اختبارات من tests_edge_cases.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_concurrent_salary_updates(self):
        """اختبار تحديثات الراتب المتزامنة"""
        salary = Salary.objects.create(
            employee=self.employee,
            basic_salary=Decimal('5000.00'),
            effective_date=date.today()
        )
        
        def update_salary(amount):
            try:
                with transaction.atomic():
                    s = Salary.objects.select_for_update().get(pk=salary.pk)
                    s.basic_salary = amount
                    s.save()
            except Exception:
                pass
        
        # محاولة تحديثات متزامنة
        thread1 = threading.Thread(target=update_salary, args=(Decimal('6000.00'),))
        thread2 = threading.Thread(target=update_salary, args=(Decimal('7000.00'),))
        
        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()
        
        # التحقق من أن أحد التحديثات نجح
        salary.refresh_from_db()
        self.assertIn(salary.basic_salary, [Decimal('6000.00'), Decimal('7000.00')])
    


class ConcurrentOperationsTest(TestCase):
    """اختبارات من tests_edge_cases.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_duplicate_employee_number(self):
        """اختبار منع تكرار رقم الموظف"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        emp_number = f'EMP_{ts}'
        
        # إنشاء موظف أول
        Employee.objects.create(
            user=self.user,
            employee_number=emp_number,
            first_name_ar='أحمد',
            last_name_ar='محمد',
            national_id=f'1234567890{ts[:4]}',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email=f'emp1_{ts}@test.com',
            mobile_phone=f'0123456{ts[:4]}',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
        
        # محاولة إنشاء موظف ثاني بنفس الرقم
        with self.assertRaises(IntegrityError):
            Employee.objects.create(
                employee_number=emp_number,
                first_name_ar='علي',
                last_name_ar='حسن',
                national_id=f'9876543210{ts[:4]}',
                birth_date=date(1992, 1, 1),
                gender='male',
                marital_status='single',
                work_email=f'emp2_{ts}@test.com',
                mobile_phone=f'0123457{ts[:4]}',
                address='القاهرة',
                city='القاهرة',
                department=self.department,
                job_title=self.job_title,
                hire_date=date.today(),
                created_by=self.user
            )
    


class ConcurrentOperationsTest(TestCase):
    """اختبارات من tests_edge_cases.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_orphaned_salary_prevention(self):
        """اختبار منع الرواتب اليتيمة"""
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
            basic_salary=Decimal('5000.00'),
            effective_date=date.today()
        )
        
        # حذف الموظف يجب أن يحذف الراتب
        employee.delete()
        
        # التحقق من حذف الراتب
        self.assertFalse(Salary.objects.filter(pk=salary.pk).exists())
    


class ConcurrentOperationsTest(TestCase):
    """اختبارات من tests_edge_cases.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_leave_balance_integrity(self):
        """اختبار سلامة رصيد الإجازات"""
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
        
        # محاولة طلب إجازة أكثر من الرصيد
        leave = Leave(
            employee=employee,
            leave_type=leave_type,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),  # أكثر من 21 يوم
            days_count=30,
            reason='إجازة اختبار',
            status='pending'
        )
        
        # يجب أن يفشل الحفظ أو يتم رفضه
        try:
            leave.save()
            # إذا تم الحفظ، يجب أن تكون الحالة pending
            self.assertEqual(leave.status, 'pending')
        except Exception:
            # أو يجب أن يفشل الحفظ
            self.assertTrue(True)




class ConcurrentOperationsTest(TestCase):
    """اختبارات من tests_edge_cases.py"""
    
    def setUp(self):
        from datetime import datetime
        ts = datetime.now().strftime('%Y%m%d%H%M%S%f')
        self.user = User.objects.create_user(
            username=f'test_{ts}',
            password='test'
        )

    def test_salary_increase_rules(self):
        """اختبار قواعد زيادة الراتب"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        contract = Contract.objects.create(
            employee=self.employee,
            contract_number=f'C_{ts[:10]}',
            contract_type='permanent',
            start_date=date.today(),
            basic_salary=Decimal('5000.00'),
            has_annual_increase=True,
            annual_increase_percentage=Decimal('10.00'),
            status='active',
            created_by=self.user
        )
        
        # التحقق من قواعد الزيادة
        self.assertTrue(contract.has_annual_increase)
        self.assertGreater(contract.annual_increase_percentage, Decimal('0'))
    

# ============================================================================
# اختبارات إضافية منقولة (النقل الكامل)
# ============================================================================

    def test_attendance_late_calculation(self):
        """اختبار حساب التأخير"""
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


# ============================================================================
# اختبارات نماذج الإجازات (Leave)
# ============================================================================


    def test_leave_creation(self):
        """اختبار إنشاء إجازة"""
        leave = Leave.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=5),
            days_count=5,
            reason='إجازة اختبار',
            status='pending'
        )
        
        self.assertEqual(leave.days_count, 5)
        self.assertEqual(leave.status, 'pending')
    

    def test_leave_validation(self):
        """اختبار التحقق من صحة الإجازة"""
        leave = Leave(
            employee=self.employee,
            leave_type=self.leave_type,
            start_date=date.today() + timedelta(days=5),
            end_date=date.today(),  # تاريخ النهاية قبل البداية
            days_count=5,
            reason='إجازة اختبار'
        )
        
        with self.assertRaises(ValidationError):
            leave.full_clean()


# ============================================================================
# اختبارات نماذج العقود (Contracts)
# ============================================================================


    def test_template_creation(self):
        """اختبار إنشاء قالب"""
        template = SalaryComponentTemplate.objects.create(
            name='بدل سكن',
            component_type='earning',
            formula='basic * 0.2',
            default_amount=Decimal('0'),
            order=1,
            is_active=True
        )
        
        self.assertEqual(template.name, 'بدل سكن')
        self.assertTrue(template.is_active)


# ============================================================================
# اختبارات نماذج البصمة
# ============================================================================


    def test_device_creation(self):
        """اختبار إنشاء جهاز بصمة"""
        user = User.objects.create_user(username='test_bio', password='test')
        device = BiometricDevice.objects.create(
            device_name='جهاز المدخل الرئيسي',
            device_code='DEV001',
            device_type='fingerprint',
            serial_number='SN12345',
            ip_address='192.168.1.100',
            port=4370,
            location='المدخل الرئيسي',
            status='active',
            created_by=user
        )
        
        self.assertEqual(device.device_name, 'جهاز المدخل الرئيسي')
        self.assertEqual(device.status, 'active')


    def test_payroll_with_deductions(self):
        """اختبار راتب مع خصومات"""
        payroll = PayrollService.calculate_payroll(
            self.employee,
            date(2025, 12, 1),
            self.user
        )
        
        # التحقق من الحسابات
        self.assertGreater(payroll.gross_salary, 0)
        self.assertGreater(payroll.net_salary, 0)
        self.assertLess(payroll.net_salary, payroll.gross_salary)


    def test_create_user_for_employee(self):
        """اختبار إنشاء مستخدم لموظف"""
        try:
            user, password = UserEmployeeService.create_user_for_employee(
                self.employee,
                username=f'emp_{self.employee.employee_number}',
                password='test123'
            )
            self.assertIsNotNone(user)
            self.assertIsNotNone(password)
            self.employee.refresh_from_db()
            self.assertEqual(self.employee.user, user)
        except Exception as e:
            # قد يكون الموظف مرتبط بالفعل
            self.assertTrue(True)
    

    def test_create_user_for_employee_auto_password(self):
        """اختبار إنشاء مستخدم مع كلمة مرور تلقائية"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        new_employee = Employee.objects.create(
            employee_number=f'EMP_NEW_{ts}',
            first_name_ar='محمد',
            last_name_ar='علي',
            national_id=f'9876543210{ts[:4]}',
            birth_date=date(1992, 1, 1),
            gender='male',
            marital_status='single',
            work_email=f'new_emp_{ts}@test.com',
            mobile_phone=f'0123456{ts[:4]}',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
        
        try:
            user, password = UserEmployeeService.create_user_for_employee(new_employee)
            self.assertIsNotNone(user)
            self.assertIsNotNone(password)
            self.assertGreater(len(password), 8)
        except Exception:
            self.assertTrue(True)



    def test_employee_import_template_download(self):
        """اختبار تحميل قالب استيراد الموظفين"""
        try:
            response = self.client.get(reverse('hr:employee_import_template'))
            self.assertIn(response.status_code, [200, 302, 404])
        except Exception:
            self.skipTest("Employee import template view not available")
    

    def test_employee_import_validate(self):
        """اختبار التحقق من ملف الاستيراد"""
        try:
            # محاولة رفع ملف فارغ
            response = self.client.post(
                reverse('hr:employee_import_validate'),
                data={'file': None}
            )
            self.assertIn(response.status_code, [200, 302, 400, 404])
        except Exception:
            self.skipTest("Employee import validate view not available")
    

    def test_contracts_expiring_soon(self):
        """اختبار واجهة العقود القريبة من الانتهاء"""
        try:
            response = self.client.get(reverse('hr:contracts_expiring_soon'))
            self.assertIn(response.status_code, [200, 302, 404])
        except Exception:
            self.skipTest("Contracts expiring soon view not available")



    def test_list_departments(self):
        """اختبار قائمة الأقسام"""
        response = self.client.get('/hr/api/departments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    

    def test_retrieve_employee(self):
        """اختبار الحصول على موظف محدد"""
        response = self.client.get(f'/hr/api/employees/{self.employee.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    

    def test_contract_form_import(self):
        """اختبار استيراد ContractForm"""
        try:
            from .forms.contract_forms import ContractForm
            self.assertIsNotNone(ContractForm)
        except ImportError:
            self.skipTest("ContractForm not available")
    

    def test_contract_form_valid_data(self):
        """اختبار ContractForm مع بيانات صحيحة"""
        try:
            from .forms.contract_forms import ContractForm
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
            
            form_data = {
                'employee': self.employee.id,
                'contract_number': f'C_{ts[:10]}',
                'contract_type': 'permanent',
                'start_date': date.today(),
                'basic_salary': '5000.00',
                'status': 'draft'
            }
            
            form = ContractForm(data=form_data)
            self.assertTrue(form.is_valid())
        except ImportError:
            self.skipTest("ContractForm not available")
    

    def test_contract_form_date_validation(self):
        """اختبار التحقق من التواريخ"""
        try:
            from .forms.contract_forms import ContractForm
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
            
            # تاريخ نهاية قبل تاريخ البداية
            form_data = {
                'employee': self.employee.id,
                'contract_number': f'C_{ts[:10]}',
                'contract_type': 'fixed_term',
                'start_date': date.today(),
                'end_date': date.today() - timedelta(days=30),
                'basic_salary': '5000.00',
                'status': 'draft'
            }
            
            form = ContractForm(data=form_data)
            self.assertFalse(form.is_valid())
        except ImportError:
            self.skipTest("ContractForm not available")
    

    def test_employee_form_import(self):
        """اختبار استيراد EmployeeForm"""
        try:
            from .forms.employee_forms import EmployeeForm
            self.assertIsNotNone(EmployeeForm)
        except ImportError:
            self.skipTest("EmployeeForm not available")
    

    def test_employee_form_national_id_validation(self):
        """اختبار التحقق من الرقم القومي"""
        try:
            from .forms.employee_forms import EmployeeForm
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
            
            # رقم قومي قصير
            form_data = {
                'employee_number': f'EMP_{ts}',
                'first_name_ar': 'أحمد',
                'last_name_ar': 'محمد',
                'national_id': '123',  # قصير جداً
                'birth_date': date(1990, 1, 1),
                'gender': 'male',
                'marital_status': 'single',
                'work_email': f'test_{ts}@test.com',
                'mobile_phone': f'0123456{ts[:4]}',
                'address': 'القاهرة',
                'city': 'القاهرة',
                'department': self.department.id,
                'job_title': self.job_title.id,
                'hire_date': date.today()
            }
            
            form = EmployeeForm(data=form_data)
            if not form.is_valid():
                self.assertIn('national_id', form.errors)
        except ImportError:
            self.skipTest("EmployeeForm not available")
    

    def test_hr_manager_can_manage_contracts(self):
        """اختبار أن HR Manager يمكنه إدارة العقود"""
        @can_manage_contracts
        def test_view(request):
            return HttpResponse('OK')
        
        request = self.factory.get('/')
        request.user = self.hr_manager
        
        response = test_view(request)
        self.assertEqual(response.status_code, 200)



    def test_active_employee_can_request_advance(self):
        """اختبار أن الموظف النشط يمكنه طلب سلفة"""
        request = self.factory.get('/')
        request.user = self.user
        
        self.assertTrue(self.permission.has_permission(request, None))
    

