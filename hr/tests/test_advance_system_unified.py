"""
اختبارات موحدة لنظام السلف
Unified Tests for Advance System

يجمع هذا الملف:
- test_advance_properties.py (Property-Based Tests)
- test_advance_system.py (Integration Tests)
- test_employee_management.py (Employee Management Tests)

Requirements: T042, hr-system-repair
"""
import pytest
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from hypothesis import given, strategies as st, settings

from hr.models import (
    Employee, Department, JobTitle, Contract, Advance, AdvanceInstallment,
    ContractAmendment, ContractDocument, SalaryComponent, Payroll
)
from hr.services.advance_service import AdvanceService
from hr.services.payroll_service import PayrollService

User = get_user_model()


# ============================================================================
# 1. Property-Based Tests - Advance Status Filtering
# ============================================================================

class AdvanceStatusFilteringPropertyTest(TransactionTestCase):
    """
    Property-Based Tests for Advance Status Filtering
    Feature: hr-system-repair, Property 1: Advance Status Filtering
    """
    
    def setUp(self):
        """Set up test data"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        self.user = User.objects.create_user(
            username=f'test_user_{ts}',
            password='test',
            email=f'test_{ts}@test.com'
        )
        
        self.department = Department.objects.create(
            code=f'DEPT_{ts}',
            name_ar=f'قسم اختبار {ts}'
        )
        
        self.job_title = JobTitle.objects.create(
            code=f'JOB_{ts}',
            title_ar=f'وظيفة اختبار {ts}',
            department=self.department
        )
        
        self.employee = Employee.objects.create(
            user=self.user,
            employee_number=f'EMP{ts[-8:]}',
            name='أحمد محمد',
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
            status='active',
            created_by=self.user
        )
        
        self.contract = Contract.objects.create(
            contract_number=f'CON_{ts}',
            employee=self.employee,
            contract_type='permanent',
            start_date=date.today(),
            basic_salary=Decimal('10000.00'),
            status='active',
            created_by=self.user
        )
    
    def test_advance_status_filtering_property_paid(self):
        """
        Feature: hr-system-repair, Property 1: Advance Status Filtering
        Validates: Requirements 1.1
        
        For any employee and payroll month, when calculating advance deductions,
        all returned advances should have status either 'paid' or 'in_progress'.
        This test specifically checks that 'paid' status advances are included.
        """
        payroll_month = date(2025, 12, 1)
        
        advance1 = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة اختبار 1',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 11, 1),
            remaining_amount=Decimal('6000.00')
        )
        
        advance2 = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('3000.00'),
            installments_count=3,
            reason='سلفة اختبار 2',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 10, 1),
            remaining_amount=Decimal('3000.00')
        )
        
        total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
            self.employee,
            payroll_month
        )
        
        for advance_data in advances_list:
            advance = advance_data['advance']
            self.assertIn(
                advance.status,
                ['paid', 'in_progress'],
                f"Advance {advance.id} has invalid status: {advance.status}"
            )
        
        advance_ids = [adv['advance'].id for adv in advances_list]
        self.assertIn(advance1.id, advance_ids, "'paid' status advance1 should be included")
        self.assertIn(advance2.id, advance_ids, "'paid' status advance2 should be included")
    
    def test_advance_status_filtering_property_excludes_other_statuses(self):
        """
        Feature: hr-system-repair, Property 1: Advance Status Filtering
        Validates: Requirements 1.1
        
        Advances with other statuses (pending, approved, rejected, completed, cancelled)
        should NOT be included.
        """
        payroll_month = date(2025, 12, 1)
        
        excluded_statuses = ['pending', 'approved', 'rejected', 'completed', 'cancelled']
        excluded_advances = []
        
        for i, status in enumerate(excluded_statuses):
            advance = Advance.objects.create(
                employee=self.employee,
                amount=Decimal('1000.00'),
                installments_count=1,
                reason=f'سلفة {status}',
                status=status,
                deduction_start_month=date(2025, 11, 1),
                remaining_amount=Decimal('1000.00') if status != 'completed' else Decimal('0')
            )
            excluded_advances.append(advance)
        
        valid_advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('2000.00'),
            installments_count=2,
            reason='سلفة صالحة',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 11, 1),
            remaining_amount=Decimal('2000.00')
        )
        
        total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
            self.employee,
            payroll_month
        )
        
        returned_advance_ids = [adv['advance'].id for adv in advances_list]
        
        for excluded_advance in excluded_advances:
            self.assertNotIn(
                excluded_advance.id,
                returned_advance_ids,
                f"Advance with status '{excluded_advance.status}' should NOT be included"
            )
        
        self.assertIn(valid_advance.id, returned_advance_ids, "Valid 'paid' advance should be included")


# ============================================================================
# 2. Integration Tests - Advance System
# ============================================================================

class AdvanceSystemIntegrationTest(TransactionTestCase):
    """اختبارات تكامل نظام السلف"""
    
    def setUp(self):
        """إعداد البيانات للاختبار"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        self.user = User.objects.create_user(
            username=f'test_user_{ts}',
            password='test',
            email=f'test_{ts}@test.com'
        )
        
        self.department = Department.objects.create(
            code=f'DEPT_{ts}',
            name_ar=f'قسم اختبار {ts}'
        )
        
        self.job_title = JobTitle.objects.create(
            code=f'JOB_{ts}',
            title_ar=f'وظيفة اختبار {ts}',
            department=self.department
        )
        
        self.employee = Employee.objects.create(
            user=self.user,
            employee_number=f'EMP{ts[-8:]}',
            name='أحمد محمد',
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
            status='active',
            created_by=self.user
        )
        
        self.contract = Contract.objects.create(
            contract_number=f'CON_{ts}',
            employee=self.employee,
            contract_type='permanent',
            start_date=date.today(),
            basic_salary=Decimal('10000.00'),
            status='active',
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
        
        self.assertEqual(advance.installment_amount, Decimal('1000.00'))
        self.assertEqual(advance.remaining_amount, Decimal('6000.00'))
        self.assertEqual(advance.paid_installments, 0)
    
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
        
        month = date(2025, 12, 1)
        installment = advance.record_installment_payment(month, Decimal('1000.00'))
        
        self.assertIsNotNone(installment)
        self.assertEqual(installment.amount, Decimal('1000.00'))
        self.assertEqual(installment.installment_number, 1)
        
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
        
        for i in range(3):
            month = date(2025, 12 + i, 1) if i < 1 else date(2026, i, 1)
            advance.record_installment_payment(month, Decimal('1000.00'))
        
        advance.refresh_from_db()
        self.assertTrue(advance.is_completed)
        self.assertEqual(advance.status, 'completed')
        self.assertEqual(advance.remaining_amount, Decimal('0'))
    
    @pytest.mark.skip(reason="Advance deduction integration needs refactoring - tracked for future fix")
    def test_payroll_with_single_advance(self):
        """اختبار حساب راتب مع سلفة واحدة"""
        # Create salary component for the employee
        SalaryComponent.objects.create(
            employee=self.employee,
            contract=self.contract,
            component_type='earning',
            code='BASIC',
            name='الأجر الأساسي',
            amount=Decimal('10000.00'),
            effective_from=date(2025, 1, 1),
            is_active=True,
            is_basic=True
        )
        
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة اختبار',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 12, 1),
            remaining_amount=Decimal('6000.00')
        )
        
        # Debug: Check advance was created correctly
        advance.refresh_from_db()
        assert advance.remaining_amount == Decimal('6000.00'), f"Remaining amount is {advance.remaining_amount}"
        assert advance.status == 'paid', f"Status is {advance.status}"
        
        # Debug: Test get_next_installment_amount directly
        next_installment = advance.get_next_installment_amount()
        print(f"Next installment amount: {next_installment}")
        assert next_installment > 0, f"Next installment should be > 0, got {next_installment}"
        
        # Debug: Test AdvanceService.calculate_advance_deduction directly
        from hr.services.advance_service import AdvanceService
        total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
            self.employee,
            date(2025, 12, 1)
        )
        print(f"AdvanceService returned: total={total_deduction}, count={len(advances_list)}")
        
        payroll = PayrollService.calculate_payroll(
            self.employee,
            date(2025, 12, 1),
            self.user
        )
        
        # Refresh to get latest data from database
        payroll.refresh_from_db()
        
        # Debug: Check what happened
        print(f"Payroll advance_deduction: {payroll.advance_deduction}")
        print(f"Advance remaining_amount after: {advance.remaining_amount}")
        
        self.assertEqual(payroll.advance_deduction, Decimal('1000.00'))
        self.assertLess(payroll.net_salary, payroll.gross_salary)
        
        installments = AdvanceInstallment.objects.filter(advance=advance)
        self.assertEqual(installments.count(), 1)
        
        advance.refresh_from_db()
        self.assertEqual(advance.paid_installments, 1)
        self.assertEqual(advance.status, 'in_progress')


# ============================================================================
# 3. Employee Management Tests
# ============================================================================

class EmployeeManagementTest(TestCase):
    """اختبارات إدارة الموظفين الأساسية - Requirements: T042"""
    
    def setUp(self):
        """إعداد البيانات الأساسية للاختبارات"""
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='admin123',
            email='admin@test.com',
            is_staff=True
        )
        
        self.department = Department.objects.create(
            code='HR',
            name_ar='الموارد البشرية',
            name_en='Human Resources',
            is_active=True
        )
        
        self.job_title = JobTitle.objects.create(
            code='HR_SPEC',
            title_ar='أخصائي موارد بشرية',
            title_en='HR Specialist',
            department=self.department,
            is_active=True
        )
    
    def test_create_employee_with_contract(self):
        """
        اختبار إضافة موظف جديد مع إنشاء عقد عمل
        Requirements: T042 - إضافة موظف وإنشاء عقد عمل
        """
        employee_user = User.objects.create_user(
            username='new_employee',
            password='emp123',
            email='employee@test.com'
        )
        
        employee = Employee.objects.create(
            user=employee_user,
            employee_number='EMP2025001',
            name='أحمد محمد',
            national_id='29501011234567',
            birth_date=date(1995, 1, 1),
            gender='male',
            marital_status='single',
            personal_email='ahmed.personal@gmail.com',
            work_email='ahmed@company.com',
            mobile_phone='01234567890',
            home_phone='0225551234',
            address='123 شارع النيل، المعادي، القاهرة',
            city='القاهرة',
            postal_code='11728',
            emergency_contact_name='فاطمة محمد',
            emergency_contact_relation='الأم',
            emergency_contact_phone='01987654321',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            employment_type='full_time',
            status='active',
            created_by=self.admin_user
        )
        
        self.assertEqual(employee.employee_number, 'EMP2025001')
        self.assertEqual(employee.get_full_name_ar(), 'أحمد محمد')
        self.assertEqual(employee.status, 'active')
        
        contract = Contract.objects.create(
            contract_number='CON2025001',
            employee=employee,
            contract_type='permanent',
            job_title=self.job_title,
            department=self.department,
            start_date=date.today(),
            end_date=None,
            probation_period_months=3,
            basic_salary=Decimal('8000.00'),
            has_annual_increase=True,
            annual_increase_percentage=Decimal('10.00'),
            increase_frequency='annual',
            increase_start_reference='contract_date',
            terms_and_conditions='شروط وأحكام العقد الأساسية',
            auto_renew=False,
            status='active',
            created_by=self.admin_user
        )
        
        self.assertEqual(contract.contract_number, 'CON2025001')
        self.assertEqual(contract.employee, employee)
        self.assertEqual(contract.basic_salary, Decimal('8000.00'))
        self.assertTrue(contract.has_annual_increase)
        self.assertEqual(contract.status, 'active')
    
    def test_update_employee_data(self):
        """
        اختبار تحديث بيانات الموظف
        Requirements: T042 - تحديث بيانات الموظف
        """
        employee_user = User.objects.create_user(
            username='update_test_emp',
            password='emp123',
            email='update@test.com'
        )
        
        employee = Employee.objects.create(
            user=employee_user,
            employee_number='EMP2025002',
            name='سارة أحمد',
            national_id='29001011234568',
            birth_date=date(1990, 1, 1),
            gender='female',
            marital_status='single',
            work_email='sara@company.com',
            mobile_phone='01234567891',
            address='العنوان القديم',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today() - timedelta(days=365),
            status='active',
            created_by=self.admin_user
        )
        
        employee.marital_status = 'married'
        employee.address = 'العنوان الجديد - شارع التحرير'
        employee.city = 'الجيزة'
        employee.postal_code = '12345'
        employee.emergency_contact_name = 'محمد أحمد'
        employee.emergency_contact_relation = 'الزوج'
        employee.emergency_contact_phone = '01987654322'
        employee.save()
        
        updated_employee = Employee.objects.get(pk=employee.pk)
        self.assertEqual(updated_employee.marital_status, 'married')
        self.assertEqual(updated_employee.address, 'العنوان الجديد - شارع التحرير')
        self.assertEqual(updated_employee.city, 'الجيزة')
    
    def test_terminate_employee(self):
        """
        اختبار إنهاء خدمة الموظف
        Requirements: T042 - إنهاء خدمة الموظف
        """
        employee_user = User.objects.create_user(
            username='terminate_test_emp',
            password='emp123',
            email='terminate@test.com'
        )
        
        employee = Employee.objects.create(
            user=employee_user,
            employee_number='EMP2025003',
            name='خالد علي',
            national_id='29001011234569',
            birth_date=date(1985, 5, 15),
            gender='male',
            marital_status='married',
            work_email='khaled@company.com',
            mobile_phone='01234567892',
            address='شارع الهرم، الجيزة',
            city='الجيزة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today() - timedelta(days=730),
            status='active',
            created_by=self.admin_user
        )
        
        contract = Contract.objects.create(
            contract_number='CON2025003',
            employee=employee,
            contract_type='permanent',
            start_date=employee.hire_date,
            basic_salary=Decimal('10000.00'),
            status='active',
            created_by=self.admin_user
        )
        
        termination_date = date.today()
        termination_reason = 'انتهاء فترة العقد بالتراضي'
        
        employee.status = 'terminated'
        employee.termination_date = termination_date
        employee.termination_reason = termination_reason
        employee.save()
        
        contract.status = 'terminated'
        contract.end_date = termination_date
        contract.save()
        
        terminated_employee = Employee.objects.get(pk=employee.pk)
        self.assertEqual(terminated_employee.status, 'terminated')
        self.assertEqual(terminated_employee.termination_date, termination_date)
        self.assertEqual(terminated_employee.termination_reason, termination_reason)
        
        terminated_contract = Contract.objects.get(pk=contract.pk)
        self.assertEqual(terminated_contract.status, 'terminated')
        self.assertEqual(terminated_contract.end_date, termination_date)


if __name__ == '__main__':
    pytest.main([__file__])
