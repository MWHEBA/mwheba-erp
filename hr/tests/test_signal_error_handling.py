"""
Test signal error handling for salary components
Tests that signals handle missing contracts gracefully
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import date
from decimal import Decimal
import logging

from hr.models import Department, JobTitle, Employee, SalaryComponent

User = get_user_model()


class SignalErrorHandlingTest(TestCase):
    """Test signal error handling"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(username='test', password='test')
        self.department = Department.objects.create(code='IT', name_ar='IT')
        self.job_title = JobTitle.objects.create(code='DEV', title_ar='Dev', department=self.department)
        
        # Create employee without contract
        self.employee = Employee.objects.create(
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
    
    def test_salary_component_creation_without_contract(self):
        """Test that creating a salary component without contract doesn't raise exception"""
        # This should not raise an exception
        try:
            component = SalaryComponent.objects.create(
                employee=self.employee,
                code='HOUSING',
                name='بدل سكن',
                component_type='earning',
                amount=Decimal('500.00'),
                is_active=True
            )
            self.assertIsNotNone(component)
            self.assertEqual(component.employee, self.employee)
        except Exception as e:
            self.fail(f"Creating salary component without contract raised exception: {e}")
    
    def test_salary_component_update_without_contract(self):
        """Test that updating a salary component without contract doesn't raise exception"""
        # Create component
        component = SalaryComponent.objects.create(
            employee=self.employee,
            code='HOUSING',
            name='بدل سكن',
            component_type='earning',
            amount=Decimal('500.00'),
            is_active=True
        )
        
        # Update should not raise exception
        try:
            component.amount = Decimal('600.00')
            component.save()
            component.refresh_from_db()
            self.assertEqual(component.amount, Decimal('600.00'))
        except Exception as e:
            self.fail(f"Updating salary component without contract raised exception: {e}")
    
    def test_salary_component_deletion_without_contract(self):
        """Test that deleting a salary component without contract doesn't raise exception"""
        # Create component
        component = SalaryComponent.objects.create(
            employee=self.employee,
            code='HOUSING',
            name='بدل سكن',
            component_type='earning',
            amount=Decimal('500.00'),
            is_active=True
        )
        
        component_id = component.id
        
        # Delete should not raise exception
        try:
            component.delete()
            # Verify deletion
            self.assertFalse(SalaryComponent.objects.filter(id=component_id).exists())
        except Exception as e:
            self.fail(f"Deleting salary component without contract raised exception: {e}")
