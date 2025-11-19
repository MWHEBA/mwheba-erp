"""
اختبارات التكامل الشاملة
=========================
دمج اختبارات tests_comprehensive.py و tests_edge_cases.py
"""
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal

from hr.models import (
    Department, JobTitle, Employee, Advance, AdvanceInstallment
)
from hr.services import PayrollService

User = get_user_model()


# ============================================================================
# اختبارات التكامل الكاملة
# ============================================================================

class AdvanceSystemIntegrationTest(TransactionTestCase):
    """اختبارات تكامل نظام السلف الكامل"""
    
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
        # Note: Salary model has been replaced with Payroll
        # This test needs to be updated to use the new payroll system
        # self.salary = Payroll.objects.create(...)
    
    def test_complete_advance_lifecycle(self):
        """اختبار دورة حياة السلفة الكاملة"""
        # 1. إنشاء سلفة
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة تكامل',
            status='pending'
        )
        self.assertEqual(advance.status, 'pending')
        
        # 2. اعتماد السلفة
        advance.status = 'approved'
        advance.approved_by = self.user
        advance.approved_at = timezone.now()
        advance.save()
        self.assertEqual(advance.status, 'approved')
        
        # 3. صرف السلفة
        advance.status = 'paid'
        advance.payment_date = date.today()
        advance.deduction_start_month = date(2025, 12, 1)
        advance.save()
        self.assertEqual(advance.status, 'paid')
        
        # 4. خصم الأقساط عبر 6 أشهر
        for month_num in range(6):
            month = date(2025, 12 + month_num, 1) if month_num < 1 else date(2026, month_num, 1)
            
            payroll = PayrollService.calculate_payroll(
                self.employee,
                month,
                self.user
            )
            
            self.assertGreater(payroll.advance_deduction, 0)
        
        # 5. التحقق من إكمال السلفة
        advance.refresh_from_db()
        self.assertEqual(advance.status, 'completed')
        self.assertEqual(advance.paid_installments, 6)
        self.assertEqual(advance.remaining_amount, Decimal('0'))
        self.assertTrue(advance.is_completed)
        
        # 6. التحقق من سجل الأقساط
        installments = AdvanceInstallment.objects.filter(advance=advance)
        self.assertEqual(installments.count(), 6)
        
        total_paid = sum(inst.amount for inst in installments)
        self.assertEqual(total_paid, advance.amount)


# ============================================================================
# اختبارات إضافية منقولة (النقل الكامل)
# ============================================================================

    def test_concurrent_leave_requests(self):
        """اختبار طلبات الإجازة المتزامنة"""
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        leave_type = LeaveType.objects.create(
            name_ar=f'إجازة_{ts}',
            code=f'ANN_{ts[:8]}',
            max_days_per_year=21,
            is_paid=True
        )
        
        def create_leave(days):
            try:
                Leave.objects.create(
                    employee=self.employee,
                    leave_type=leave_type,
                    start_date=date.today(),
                    end_date=date.today() + timedelta(days=days),
                    days_count=days,
                    reason='إجازة اختبار',
                    status='pending'
                )
            except Exception:
                pass
        
        # محاولة إنشاء إجازات متزامنة
        thread1 = threading.Thread(target=create_leave, args=(5,))
        thread2 = threading.Thread(target=create_leave, args=(7,))
        
        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()
        
        # التحقق من عدد الإجازات المُنشأة
        leaves_count = Leave.objects.filter(employee=self.employee).count()
        self.assertGreaterEqual(leaves_count, 1)



