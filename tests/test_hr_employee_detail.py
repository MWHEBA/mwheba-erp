import pytest
from datetime import date
from django.urls import reverse
from django.test import Client
from hr.models import Employee, Department, JobTitle, EmployeeAssetCustody
from django.utils import timezone
from users.models import User

@pytest.mark.django_db
def test_employee_detail_with_asset_custody():
    user = User.objects.create_superuser(
        username="admin_test",
        email="admin_test@example.com",
        password="password123"
    )
    dept = Department.objects.create(code="IT_DEPT", name_ar="تكنولوجيا المعلومات")
    job = JobTitle.objects.create(code="ENG_JOB", title_ar="مهندس", department=dept)
    emp = Employee.objects.create(
        name="أحمد محمد علي",
        employee_number="EMP999",
        national_id="29001011234567",
        birth_date=date(1990, 1, 1),
        gender="male",
        marital_status="single",
        department=dept,
        job_title=job,
        hire_date=date(2022, 1, 1),
        status="active",
        created_by=user
    )
    # Create asset custody
    EmployeeAssetCustody.objects.create(
        custody_code="AST-001",
        employee=emp,
        item_name="Dell Latitude 5420",
        delivered_date=timezone.now().date()
    )

    client = Client()
    client.force_login(user)

    url = reverse("hr:employee_detail", kwargs={"pk": emp.pk})
    response = client.get(url)
    assert response.status_code == 200
    assert "Dell Latitude 5420" in response.content.decode("utf-8")
