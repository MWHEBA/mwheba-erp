"""
اختبارات شاملة لـ API ViewSets
================================
تغطية API endpoints لنظام HR
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from datetime import date, timedelta
from decimal import Decimal

from hr.models import (
    Employee, Department, JobTitle, Shift, Attendance,
    LeaveType, LeaveBalance, Leave, Payroll, Advance
)

User = get_user_model()


# ============================================================================
# اختبارات API الأقسام
# ============================================================================

class DepartmentViewSetTest(TestCase):
    """اختبارات API الأقسام"""
    
    def setUp(self):
        self.client = APIClient()
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        self.user = User.objects.create_user(
            username=f'api_user_{ts}',
            password='testpass123',
            email=f'api_{ts}@test.com'
        )
        self.client.force_authenticate(user=self.user)
        
        self.department = Department.objects.create(
            code=f'IT_{ts}',
            name_ar='تقنية المعلومات'
        )
    
    def test_list_departments(self):
        """اختبار قائمة الأقسام"""
        response = self.client.get('/hr/api/departments/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_retrieve_department(self):
        """اختبار الحصول على قسم محدد"""
        response = self.client.get(f'/hr/api/departments/{self.department.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_search_departments(self):
        """اختبار البحث في الأقسام"""
        response = self.client.get('/hr/api/departments/?search=تقنية')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ============================================================================
# اختبارات API المسميات الوظيفية
# ============================================================================

class JobTitleViewSetTest(TestCase):
    """اختبارات API المسميات الوظيفية"""
    
    def setUp(self):
        self.client = APIClient()
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        self.user = User.objects.create_user(
            username=f'api_job_{ts}',
            password='testpass123',
            email=f'api_job_{ts}@test.com'
        )
        self.client.force_authenticate(user=self.user)
        
        self.department = Department.objects.create(
            code=f'IT_{ts}',
            name_ar='تقنية المعلومات'
        )
        
        self.job_title = JobTitle.objects.create(
            code=f'DEV_{ts}',
            title_ar='مطور',
            department=self.department
        )
    
    def test_list_job_titles(self):
        """اختبار قائمة المسميات الوظيفية"""
        response = self.client.get('/hr/api/job-titles/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_filter_by_department(self):
        """اختبار التصفية حسب القسم"""
        response = self.client.get(f'/hr/api/job-titles/?department={self.department.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ============================================================================
# اختبارات API الموظفين
# ============================================================================

class EmployeeViewSetTest(TestCase):
    """اختبارات API الموظفين"""
    
    def setUp(self):
        self.client = APIClient()
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        self.user = User.objects.create_user(
            username=f'api_emp_{ts}',
            password='testpass123',
            email=f'api_emp_{ts}@test.com'
        )
        self.client.force_authenticate(user=self.user)
        
        self.department = Department.objects.create(
            code=f'IT_{ts}',
            name_ar='IT'
        )
        self.job_title = JobTitle.objects.create(
            code=f'DEV_{ts}',
            title_ar='Dev',
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
            created_by=self.user
        )
    
    def test_list_employees(self):
        """اختبار قائمة الموظفين"""
        response = self.client.get('/hr/api/employees/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_retrieve_employee(self):
        """اختبار الحصول على موظف محدد"""
        response = self.client.get(f'/hr/api/employees/{self.employee.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


# ============================================================================
# اختبارات إضافية منقولة (النقل الكامل)
# ============================================================================

