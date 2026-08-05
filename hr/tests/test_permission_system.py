import pytest
from threading import Thread, Barrier
from datetime import date, time
from decimal import Decimal
from django.contrib.auth import get_user_model
from hr.models import Employee, Department, JobTitle, PermissionType, PermissionRequest
from hr.services.permission_quota_service import PermissionQuotaService
from django.db import connection

User = get_user_model()

@pytest.mark.django_db(transaction=True)
class TestConcurrency:
    
    @pytest.fixture(autouse=True)
    def setup_data(self, db):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.department = Department.objects.create(name_ar='HR', code='HR')
        self.job_title = JobTitle.objects.create(title_ar='Manager', code='MGR', department=self.department)
        self.employee = Employee.objects.create(
            user=self.user,
            employee_number='EMP001',
            name='أحمد محمد',
            national_id='12345678901234',
            birth_date=date(1990, 1, 1),
            gender='male',
            marital_status='single',
            department=self.department,
            job_title=self.job_title,
            status='active',
            hire_date=date(2020, 1, 1),
            created_by=self.user
        )
        self.permission_type = PermissionType.objects.create(
            name_ar='إذن شخصي',
            code='PRSN',
            max_hours_per_request=Decimal('4.00'),
            is_active=True
        )
        from core.models import SystemSetting
        SystemSetting.set_setting('hr_permission_max_count_monthly', 4)
        SystemSetting.set_setting('hr_permission_max_hours_monthly', 4)
        from django.core.cache import cache
        cache.clear()

    def test_concurrent_requests_with_locking(self):
        """
        ✅ اختبار أن select_for_update يمنع race conditions
        """
        results = []
        barrier = Barrier(5)  # Sync 5 threads
        
        def create_permission(thread_id):
            barrier.wait()  # Wait for all threads
            from django.db import close_old_connections
            close_old_connections()
            try:
                for attempt in range(5):
                    try:
                        success, result = PermissionQuotaService.create_permission_request(
                            employee_id=self.employee.id,
                            permission_data={
                                'permission_type': self.permission_type,
                                'date': date.today(),
                                'start_time': time(9 + thread_id, 0),
                                'end_time': time(10 + thread_id, 0),
                                'duration_hours': Decimal('1.00'),
                                'reason': f'Test {thread_id}',
                                'status': 'approved'
                            }
                        )
                        results.append('success' if success else 'failed')
                        break
                    except Exception as e:
                        if ('1213' in str(e) or 'deadlock' in str(e).lower()) and attempt < 4:
                            import time as t_mod
                            t_mod.sleep(0.05 * (attempt + 1))
                            continue
                        results.append('failed')
                        break
            finally:
                close_old_connections()
        
        # Create 5 concurrent requests (limit is usually 4 per month)
        threads = [Thread(target=create_permission, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        if 'sqlite_error' in results or 'error' in results:
            pytest.skip("SQLite in-memory doesn't support threaded connections well. Skipping assertions.")
            
        assert results.count('success') == 4
        assert results.count('failed') == 1
