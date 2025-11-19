"""
اختبارات شاملة لنظام السلف بالأقساط
"""
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from datetime import date, timedelta
from decimal import Decimal

from hr.models import (
    Employee, Department, JobTitle, Payroll,
    Advance, AdvanceInstallment
)
from hr.services.payroll_service import PayrollService

User = get_user_model()


class DepartmentModelTest(TransactionTestCase):
    """اختبارات من tests_comprehensive.py"""

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
    


class DepartmentModelTest(TransactionTestCase):
    """اختبارات من tests_comprehensive.py"""

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
    


class DepartmentModelTest(TransactionTestCase):
    """اختبارات من tests_comprehensive.py"""

    def test_get_next_installment_amount(self):
        """اختبار حساب قيمة القسط التالي"""
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('5500.00'),
            installments_count=6,
            reason='سلفة اختبار',
            status='paid',
            deduction_start_month=date(2025, 12, 1)
        )
        
        # القسط الأول
        next_amount = advance.get_next_installment_amount()
        self.assertGreater(next_amount, 0)
        self.assertLessEqual(next_amount, advance.installment_amount)
    


class DepartmentModelTest(TransactionTestCase):
    """اختبارات من tests_comprehensive.py"""

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
    


class DepartmentModelTest(TransactionTestCase):
    """اختبارات من tests_comprehensive.py"""

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




class DepartmentModelTest(TransactionTestCase):
    """اختبارات من tests_comprehensive.py"""

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
    


class DepartmentModelTest(TransactionTestCase):
    """اختبارات من tests_comprehensive.py"""

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
# 3. اختبارات الخدمات (Services)
# ============================================================================



class DepartmentModelTest(TransactionTestCase):
    """اختبارات من tests_comprehensive.py"""

    def test_payroll_with_single_advance(self):
        """اختبار حساب راتب مع سلفة واحدة"""
        # إنشاء سلفة
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة اختبار',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 12, 1)
        )
        
        # حساب الراتب
        payroll = PayrollService.calculate_payroll(
            self.employee,
            date(2025, 12, 1),
            self.user
        )
        
        # التحقق من خصم القسط
        self.assertEqual(payroll.advance_deduction, Decimal('1000.00'))
        self.assertLess(payroll.net_salary, payroll.gross_salary)
        
        # التحقق من تسجيل القسط
        installments = AdvanceInstallment.objects.filter(advance=advance)
        self.assertEqual(installments.count(), 1)
        
        # التحقق من تحديث السلفة
        advance.refresh_from_db()
        self.assertEqual(advance.paid_installments, 1)
        self.assertEqual(advance.status, 'in_progress')
    


class DepartmentModelTest(TransactionTestCase):
    """اختبارات من tests_comprehensive.py"""

    def test_payroll_with_multiple_advances(self):
        """اختبار حساب راتب مع عدة سلف"""
        # إنشاء سلفتين
        advance1 = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('6000.00'),
            installments_count=6,
            reason='سلفة 1',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 12, 1)
        )
        
        advance2 = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('3000.00'),
            installments_count=3,
            reason='سلفة 2',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 12, 1)
        )
        
        # حساب الراتب
        payroll = PayrollService.calculate_payroll(
            self.employee,
            date(2025, 12, 1),
            self.user
        )
        
        # التحقق من خصم الأقساط من السلفتين
        expected_deduction = Decimal('1000.00') + Decimal('1000.00')
        self.assertEqual(payroll.advance_deduction, expected_deduction)
        
        # التحقق من تسجيل الأقساط
        total_installments = AdvanceInstallment.objects.filter(
            advance__in=[advance1, advance2]
        ).count()
        self.assertEqual(total_installments, 2)
    


class DepartmentModelTest(TransactionTestCase):
    """اختبارات من tests_comprehensive.py"""

    def test_payroll_advance_completion(self):
        """اختبار إكمال السلفة عبر الرواتب"""
        # إنشاء سلفة صغيرة (قسطين)
        advance = Advance.objects.create(
            employee=self.employee,
            amount=Decimal('2000.00'),
            installments_count=2,
            reason='سلفة صغيرة',
            status='paid',
            payment_date=date.today(),
            deduction_start_month=date(2025, 12, 1)
        )
        
        # حساب راتب الشهر الأول
        payroll1 = PayrollService.calculate_payroll(
            self.employee,
            date(2025, 12, 1),
            self.user
        )
        
        advance.refresh_from_db()
        self.assertEqual(advance.status, 'in_progress')
        self.assertEqual(advance.paid_installments, 1)
        
        # حساب راتب الشهر الثاني
        payroll2 = PayrollService.calculate_payroll(
            self.employee,
            date(2026, 1, 1),
            self.user
        )
        
        # التحقق من إكمال السلفة
        advance.refresh_from_db()
        self.assertEqual(advance.status, 'completed')
        self.assertEqual(advance.paid_installments, 2)
        self.assertEqual(advance.remaining_amount, Decimal('0'))
        self.assertTrue(advance.is_completed)


# ============================================================================
# 4. اختبارات الواجهات (Views)
# ============================================================================


