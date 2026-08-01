"""
اختبارات المسلسلات (Serializers) بدون تخطي
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from datetime import date

from hr.models import Department, JobTitle, Employee
from hr.serializers import (
    DepartmentSerializer,
    JobTitleSerializer,
    EmployeeSerializer
)

User = get_user_model()


class SerializersTest(TestCase):
    """اختبارات المسلسلات"""
    
    def setUp(self):
        self.user = User.objects.create_user(username='test_ser_user', password='testpass123')
        self.department = Department.objects.create(code='IT_SER', name_ar='تقنية المعلومات')
        self.job_title = JobTitle.objects.create(code='DEV_SER', title_ar='مطور', department=self.department)
        self.employee = Employee.objects.create(
            user=self.user,
            employee_number='EMP_SER_001',
            name='أحمد محمد',
            national_id='12345678901234',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            work_email='test_ser@example.com',
            mobile_phone='01234567890',
            address='القاهرة',
            city='القاهرة',
            department=self.department,
            job_title=self.job_title,
            hire_date=date.today(),
            created_by=self.user
        )
    
    def test_department_serializer(self):
        """اختبار مسلسل القسم"""
        serializer = DepartmentSerializer(self.department)
        self.assertIsNotNone(serializer.data)
        self.assertEqual(serializer.data['code'], 'IT_SER')
    
    def test_employee_serializer(self):
        """اختبار مسلسل الموظف"""
        serializer = EmployeeSerializer(self.employee)
        self.assertIsNotNone(serializer.data)
        self.assertEqual(serializer.data['employee_number'], 'EMP_SER_001')
