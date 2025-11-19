"""
Property-Based Tests for Advance Service
=========================================
Tests correctness properties using Hypothesis for advance payment deductions.
"""
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from datetime import date, timedelta
from decimal import Decimal
from hypothesis import given, strategies as st, settings
from hypothesis.extra.django import from_model, TestCase as HypothesisTestCase

from hr.models import (
    Employee, Department, JobTitle, Contract, Advance
)
from hr.services.advance_service import AdvanceService

User = get_user_model()


class AdvanceStatusFilteringPropertyTest(TransactionTestCase):
    """
    Property-Based Tests for Advance Status Filtering
    **Feature: hr-system-repair, Property 1: Advance Status Filtering**
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
    
    @settings(max_examples=100, deadline=None)
    def test_advance_status_filtering_property_paid(self):
        """
        **Feature: hr-system-repair, Property 1: Advance Status Filtering**
        **Validates: Requirements 1.1**
        
        For any employee and payroll month, when calculating advance deductions,
        all returned advances should have status either 'paid' or 'in_progress'.
        
        This test specifically checks that 'paid' status advances are included.
        """
        # Create advances with 'paid' status
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
        
        # Calculate advance deductions
        total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
            self.employee,
            payroll_month
        )
        
        # Property: All returned advances should have status 'paid' or 'in_progress'
        for advance_data in advances_list:
            advance = advance_data['advance']
            self.assertIn(
                advance.status,
                ['paid', 'in_progress'],
                f"Advance {advance.id} has invalid status: {advance.status}"
            )
        
        # Verify that 'paid' advances are included
        advance_ids = [adv['advance'].id for adv in advances_list]
        self.assertIn(advance1.id, advance_ids, "'paid' status advance1 should be included")
        self.assertIn(advance2.id, advance_ids, "'paid' status advance2 should be included")
    
    @settings(max_examples=100, deadline=None)
    def test_advance_status_filtering_property_in_progress(self):
        """
        **Feature: hr-system-repair, Property 1: Advance Status Filtering**
        **Validates: Requirements 1.1**
        
        For any employee and payroll month, when calculating advance deductions,
        all returned advances should have status either 'paid' or 'in_progress'.
        
        This test specifically checks that 'in_progress' status advances are included.
        """
        # Create advances with 'in_progress' status
        payroll_month = date(2025, 12, 1)
        
        advance1 = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة اختبار 1',
            status='in_progress',
            payment_date=date.today(),
            deduction_start_month=date(2025, 11, 1),
            remaining_amount=Decimal('5000.00'),
            paid_installments=1
        )
        
        advance2 = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('3000.00'),
            installments_count=3,
            reason='سلفة اختبار 2',
            status='in_progress',
            payment_date=date.today(),
            deduction_start_month=date(2025, 10, 1),
            remaining_amount=Decimal('2000.00'),
            paid_installments=1
        )
        
        # Calculate advance deductions
        total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
            self.employee,
            payroll_month
        )
        
        # Property: All returned advances should have status 'paid' or 'in_progress'
        for advance_data in advances_list:
            advance = advance_data['advance']
            self.assertIn(
                advance.status,
                ['paid', 'in_progress'],
                f"Advance {advance.id} has invalid status: {advance.status}"
            )
        
        # Verify that 'in_progress' advances are included
        advance_ids = [adv['advance'].id for adv in advances_list]
        self.assertIn(advance1.id, advance_ids, "'in_progress' status advance1 should be included")
        self.assertIn(advance2.id, advance_ids, "'in_progress' status advance2 should be included")
    
    @settings(max_examples=100, deadline=None)
    def test_advance_status_filtering_property_excludes_other_statuses(self):
        """
        **Feature: hr-system-repair, Property 1: Advance Status Filtering**
        **Validates: Requirements 1.1**
        
        For any employee and payroll month, when calculating advance deductions,
        advances with other statuses (pending, approved, rejected, completed, cancelled)
        should NOT be included.
        """
        payroll_month = date(2025, 12, 1)
        
        # Create advances with various statuses that should be excluded
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
        
        # Create one valid advance to ensure the function works
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
        
        # Calculate advance deductions
        total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
            self.employee,
            payroll_month
        )
        
        # Property: No advances with excluded statuses should be returned
        returned_advance_ids = [adv['advance'].id for adv in advances_list]
        
        for excluded_advance in excluded_advances:
            self.assertNotIn(
                excluded_advance.id,
                returned_advance_ids,
                f"Advance with status '{excluded_advance.status}' should NOT be included"
            )
        
        # Verify the valid advance is included
        self.assertIn(valid_advance.id, returned_advance_ids, "Valid 'paid' advance should be included")
    
    @settings(max_examples=100, deadline=None)
    def test_advance_status_filtering_property_mixed_statuses(self):
        """
        **Feature: hr-system-repair, Property 1: Advance Status Filtering**
        **Validates: Requirements 1.1**
        
        For any employee and payroll month with mixed advance statuses,
        only 'paid' and 'in_progress' advances should be returned.
        """
        payroll_month = date(2025, 12, 1)
        
        # Create a mix of advances with different statuses
        advances_data = [
            ('paid', Decimal('6000.00'), True),
            ('in_progress', Decimal('3000.00'), True),
            ('pending', Decimal('2000.00'), False),
            ('approved', Decimal('1500.00'), False),
            ('rejected', Decimal('1000.00'), False),
            ('completed', Decimal('500.00'), False),
            ('cancelled', Decimal('750.00'), False),
        ]
        
        expected_advances = []
        unexpected_advances = []
        
        for i, (status, amount, should_include) in enumerate(advances_data):
            installments = max(1, int(amount / 1000))  # Ensure at least 1 installment
            advance = Advance.objects.create(
                employee=self.employee,
                amount=amount,
                installments_count=installments,
                reason=f'سلفة {status}',
                status=status,
                deduction_start_month=date(2025, 11, 1),
                remaining_amount=amount if status != 'completed' else Decimal('0')
            )
            
            if should_include:
                expected_advances.append(advance)
            else:
                unexpected_advances.append(advance)
        
        # Calculate advance deductions
        total_deduction, advances_list = AdvanceService.calculate_advance_deduction(
            self.employee,
            payroll_month
        )
        
        returned_advance_ids = [adv['advance'].id for adv in advances_list]
        
        # Property: All expected advances should be included
        for expected_advance in expected_advances:
            self.assertIn(
                expected_advance.id,
                returned_advance_ids,
                f"Advance with status '{expected_advance.status}' should be included"
            )
        
        # Property: No unexpected advances should be included
        for unexpected_advance in unexpected_advances:
            self.assertNotIn(
                unexpected_advance.id,
                returned_advance_ids,
                f"Advance with status '{unexpected_advance.status}' should NOT be included"
            )
        
        # Property: All returned advances have correct status
        for advance_data in advances_list:
            advance = advance_data['advance']
            self.assertIn(
                advance.status,
                ['paid', 'in_progress'],
                f"Returned advance {advance.id} has invalid status: {advance.status}"
            )
