"""
اختبارات حاسبة ساعات العمل للورديات
"""
from django.test import TestCase
from datetime import time
from hr.models.attendance import Shift


class ShiftCalculatorTest(TestCase):
    """اختبارات حاسبة ساعات العمل"""

    def test_normal_shift_calculation(self):
        """اختبار حساب وردية عادية"""
        shift = Shift(
            name="الوردية الصباحية",
            shift_type="morning",
            start_time=time(9, 0),  # 09:00
            end_time=time(17, 0),   # 17:00
        )
        
        calculated_hours = shift.calculate_work_hours()
        self.assertEqual(calculated_hours, 8.0)

    def test_night_shift_calculation(self):
        """اختبار حساب وردية ليلية"""
        shift = Shift(
            name="الوردية الليلية",
            shift_type="night",
            start_time=time(22, 0),  # 22:00
            end_time=time(6, 0),     # 06:00 (اليوم التالي)
        )
        
        calculated_hours = shift.calculate_work_hours()
        self.assertEqual(calculated_hours, 8.0)

    def test_short_shift_calculation(self):
        """اختبار حساب وردية قصيرة"""
        shift = Shift(
            name="وردية قصيرة",
            shift_type="morning",
            start_time=time(14, 0),  # 14:00
            end_time=time(18, 0),    # 18:00
        )
        
        calculated_hours = shift.calculate_work_hours()
        self.assertEqual(calculated_hours, 4.0)

    def test_shift_with_minutes(self):
        """اختبار حساب وردية بالدقائق"""
        shift = Shift(
            name="وردية بدقائق",
            shift_type="morning",
            start_time=time(9, 30),   # 09:30
            end_time=time(17, 45),    # 17:45
        )
        
        calculated_hours = shift.calculate_work_hours()
        self.assertEqual(calculated_hours, 8.25)  # 8 ساعات و 15 دقيقة

    def test_auto_save_calculation(self):
        """اختبار الحساب التلقائي عند الحفظ"""
        shift = Shift(
            name="وردية تلقائية",
            shift_type="morning",
            start_time=time(8, 0),
            end_time=time(16, 0),
        )
        
        # الحفظ بدون تحديد ساعات العمل
        shift.save()
        
        # التأكد من الحساب التلقائي
        self.assertEqual(shift.work_hours, 8.0)

    def test_manual_work_hours_preserved(self):
        """اختبار الحفاظ على ساعات العمل المحددة يدوياً"""
        shift = Shift(
            name="وردية يدوية",
            shift_type="morning",
            start_time=time(9, 0),
            end_time=time(17, 0),
            work_hours=7.5  # تحديد يدوي
        )
        
        shift.save()
        
        # التأكد من عدم تغيير القيمة المحددة يدوياً
        self.assertEqual(shift.work_hours, 7.5)

    def test_zero_work_hours_recalculated(self):
        """اختبار إعادة حساب ساعات العمل إذا كانت صفر"""
        shift = Shift(
            name="وردية صفر",
            shift_type="morning",
            start_time=time(9, 0),
            end_time=time(17, 0),
            work_hours=0  # قيمة صفر
        )
        
        shift.save()
        
        # التأكد من إعادة الحساب
        self.assertEqual(shift.work_hours, 8.0)

    def test_empty_times_no_calculation(self):
        """اختبار عدم الحساب مع أوقات فارغة"""
        shift = Shift(
            name="وردية فارغة",
            shift_type="morning",
        )
        
        calculated_hours = shift.calculate_work_hours()
        self.assertEqual(calculated_hours, 0)

    def test_long_night_shift(self):
        """اختبار وردية ليلية طويلة"""
        shift = Shift(
            name="وردية ليلية طويلة",
            shift_type="night",
            start_time=time(20, 0),  # 20:00
            end_time=time(8, 0),     # 08:00 (اليوم التالي)
        )
        
        calculated_hours = shift.calculate_work_hours()
        self.assertEqual(calculated_hours, 12.0)

    def test_shift_string_representation(self):
        """اختبار تمثيل الوردية كنص"""
        shift = Shift(
            name="وردية الاختبار",
            shift_type="morning",
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        
        expected_str = "وردية الاختبار (09:00:00 - 17:00:00)"
        self.assertEqual(str(shift), expected_str)