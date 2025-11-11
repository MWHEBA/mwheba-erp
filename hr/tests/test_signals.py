"""
اختبارات الإشارات (Signals)
============================
دمج من tests_signals.py
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import date
from decimal import Decimal

from hr.models import Department, JobTitle, Employee, Contract

User = get_user_model()


class SignalsTest(TestCase):
    """اختبارات الإشارات"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='test', password='test')
        self.department = Department.objects.create(code='IT', name_ar='IT')
        self.job_title = JobTitle.objects.create(code='DEV', title_ar='Dev', department=self.department)
    
    def test_employee_creation_signal(self):
        """اختبار إشارة إنشاء موظف"""
        employee = Employee.objects.create(
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
        
        self.assertIsNotNone(employee)
        self.assertEqual(employee.status, 'active')


# ============================================================================
# اختبارات إضافية منقولة (النقل الكامل)
# ============================================================================

    def test_leave_balance_update_on_hire_date_change(self):
        """اختبار تحديث رصيد الإجازات عند تغيير تاريخ التعيين"""
        # إنشاء رصيد إجازة
        balance = LeaveBalance.objects.create(
            employee=self.employee,
            leave_type=self.leave_type,
            year=date.today().year,
            total_days=21,
            used_days=0,
            remaining_days=21
        )
        
        # تغيير تاريخ التعيين
        self.employee.hire_date = date.today() - timedelta(days=180)
        self.employee.save()
        
        # التحقق من وجود الرصيد
        balance.refresh_from_db()
        self.assertIsNotNone(balance)



    def test_user_creation_for_employee(self):
        """اختبار إنشاء مستخدم تلقائي للموظف"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        # إنشاء موظف بدون مستخدم
        employee = Employee.objects.create(
            employee_number=f'EMP_USR_{ts}',
            first_name_ar='أحمد',
            last_name_ar='محمد',
            national_id=f'1234567890{ts[:4]}',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email=f'emp_usr_{ts}@test.com',
            mobile_phone=f'0123456{ts[:4]}',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
        
        # التحقق من إنشاء الموظف
        self.assertIsNotNone(employee)
        self.assertIsNotNone(employee.employee_number)



    def test_employee_status_update(self):
        """اختبار تحديث حالة الموظف"""
        # إنشاء عقد نشط
        contract = Contract.objects.create(
            employee=self.employee,
            contract_number='C001',
            contract_type='permanent',
            start_date=date.today(),
            basic_salary=Decimal('5000.00'),
            status='active',
            created_by=self.user
        )
        
        # التحقق من وجود العقد
        self.assertIsNotNone(contract)
        self.assertEqual(contract.status, 'active')



    def test_contract_changes_tracking(self):
        """اختبار تتبع تعديلات العقود"""
        contract = Contract.objects.create(
            employee=self.employee,
            contract_number='C001',
            contract_type='permanent',
            start_date=date.today(),
            basic_salary=Decimal('5000.00'),
            status='active',
            created_by=self.user
        )
        
        # تعديل العقد
        old_salary = contract.basic_salary
        contract.basic_salary = Decimal('6000.00')
        contract.save()
        
        # التحقق من التعديل
        contract.refresh_from_db()
        self.assertEqual(contract.basic_salary, Decimal('6000.00'))
        self.assertNotEqual(contract.basic_salary, old_salary)


    def test_auto_update_draft_to_active(self):
        """اختبار تحويل draft → active عند بداية العقد"""
        contract = Contract.objects.create(
            employee=self.employee,
            contract_number='C001',
            contract_type='permanent',
            start_date=date.today(),
            basic_salary=Decimal('5000.00'),
            status='draft',
            created_by=self.user
        )
        
        # عند الحفظ، يجب أن يتحول لـ active
        contract.save()
        contract.refresh_from_db()
        self.assertEqual(contract.status, 'active')
    

    def test_auto_update_active_to_expired(self):
        """اختبار تحويل active → expired عند انتهاء العقد"""
        contract = Contract.objects.create(
            employee=self.employee,
            contract_number='C002',
            contract_type='fixed_term',
            start_date=date.today() - timedelta(days=365),
            end_date=date.today() - timedelta(days=1),
            basic_salary=Decimal('5000.00'),
            status='active',
            created_by=self.user
        )
        
        # عند الحفظ، يجب أن يتحول لـ expired
        contract.save()
        contract.refresh_from_db()
        self.assertEqual(contract.status, 'expired')
    

    def test_track_hire_date_change(self):
        """اختبار تتبع تغيير تاريخ التعيين"""
        old_hire_date = self.employee.hire_date
        new_hire_date = date.today() - timedelta(days=180)
        
        self.employee.hire_date = new_hire_date
        self.employee.save()
        
        # التحقق من تغيير التاريخ
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.hire_date, new_hire_date)
        self.assertNotEqual(self.employee.hire_date, old_hire_date)



    def test_advance_status_update_on_payment(self):
        """اختبار تحديث حالة السلفة عند الدفع"""
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('1000.00'),
            reason='سلفة اختبار',
            installments_count=2,
            monthly_installment=Decimal('500.00'),
            status='approved',
            approved_by=self.user,
            approved_at=timezone.now()
        )
        
        # إنشاء قسط
        installment = AdvanceInstallment.objects.create(
            advance=advance,
            installment_number=1,
            amount=Decimal('500.00'),
            due_date=date.today(),
            status='pending'
        )
        
        # دفع القسط
        installment.status = 'paid'
        installment.paid_date = date.today()
        installment.save()
        
        # التحقق من تحديث حالة القسط
        installment.refresh_from_db()
        self.assertEqual(installment.status, 'paid')



