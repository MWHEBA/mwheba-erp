from django.test import TestCase
from unittest.mock import patch, MagicMock
from django.db.models import Sum, Count, Avg
from datetime import datetime, timedelta

from utils.statistics import (
    get_date_range_stats, get_period_comparison, 
    get_top_items, calculate_growth_rate,
    calculate_percentage, calculate_average
)


class DateRangeStatsTest(TestCase):
    """
    اختبارات دالة إحصاءات النطاق الزمني
    """
    
    @patch('utils.statistics.timezone')
    def test_get_date_range_stats(self, mock_timezone):
        """اختبار الحصول على إحصاءات لفترة زمنية"""
        # تهيئة التاريخ الحالي
        today = datetime(2023, 1, 31)
        mock_timezone.now.return_value = today
        
        # إنشاء مجموعة استعلام وهمية
        queryset = MagicMock()
        queryset.filter.return_value = MagicMock()
        queryset.filter().aggregate.return_value = {'total': 1000, 'count': 10}
        
        # اختبار النطاق اليومي
        result = get_date_range_stats(
            queryset,
            date_field='created_at',
            value_field='amount',
            range_type='daily'
        )
        
        # التحقق من النتائج
        queryset.filter.assert_called_with(
            created_at__date=today.date()
        )
        self.assertEqual(result, {'total': 1000, 'count': 10})
        
        # اختبار النطاق الأسبوعي
        queryset.reset_mock()
        queryset.filter().aggregate.return_value = {'total': 2000, 'count': 20}
        
        result = get_date_range_stats(
            queryset,
            date_field='created_at',
            value_field='amount',
            range_type='weekly'
        )
        
        # التحقق من النتائج
        queryset.filter.assert_called_once()
        self.assertEqual(result, {'total': 2000, 'count': 20})
        
        # اختبار النطاق الشهري
        queryset.reset_mock()
        queryset.filter().aggregate.return_value = {'total': 3000, 'count': 30}
        
        result = get_date_range_stats(
            queryset,
            date_field='created_at',
            value_field='amount',
            range_type='monthly'
        )
        
        # التحقق من النتائج
        queryset.filter.assert_called_once()
        self.assertEqual(result, {'total': 3000, 'count': 30})
        
        # اختبار النطاق السنوي
        queryset.reset_mock()
        queryset.filter().aggregate.return_value = {'total': 4000, 'count': 40}
        
        result = get_date_range_stats(
            queryset,
            date_field='created_at',
            value_field='amount',
            range_type='yearly'
        )
        
        # التحقق من النتائج
        queryset.filter.assert_called_once()
        self.assertEqual(result, {'total': 4000, 'count': 40})
        
        # اختبار النطاق المخصص
        queryset.reset_mock()
        queryset.filter().aggregate.return_value = {'total': 5000, 'count': 50}
        
        start_date = today - timedelta(days=10)
        end_date = today
        
        result = get_date_range_stats(
            queryset,
            date_field='created_at',
            value_field='amount',
            range_type='custom',
            start_date=start_date,
            end_date=end_date
        )
        
        # التحقق من النتائج
        queryset.filter.assert_called_with(
            created_at__date__gte=start_date.date(),
            created_at__date__lte=end_date.date()
        )
        self.assertEqual(result, {'total': 5000, 'count': 50})


class PeriodComparisonTest(TestCase):
    """
    اختبارات دالة مقارنة الفترات الزمنية
    """
    
    @patch('utils.statistics.get_date_range_stats')
    @patch('utils.statistics.timezone')
    def test_get_period_comparison(self, mock_timezone, mock_get_stats):
        """اختبار الحصول على مقارنة بين فترتين زمنيتين"""
        # تهيئة البيانات
        today = datetime(2023, 1, 31)
        mock_timezone.now.return_value = today
        
        # تعيين قيم عودة الدالة المستعارة
        mock_get_stats.side_effect = [
            {'total': 1000, 'count': 10},  # الفترة الحالية
            {'total': 800, 'count': 8}     # الفترة السابقة
        ]
        
        # إنشاء مجموعة استعلام وهمية
        queryset = MagicMock()
        
        # اختبار مقارنة الفترات
        result = get_period_comparison(
            queryset,
            date_field='created_at',
            value_field='amount',
            range_type='monthly'
        )
        
        # التحقق من النتائج
        self.assertEqual(result['current_period'], {'total': 1000, 'count': 10})
        self.assertEqual(result['previous_period'], {'total': 800, 'count': 8})
        self.assertEqual(result['growth_rate'], 25.0)  # (1000 - 800) / 800 * 100
        self.assertEqual(result['count_growth_rate'], 25.0)  # (10 - 8) / 8 * 100


class TopItemsTest(TestCase):
    """
    اختبارات دالة الحصول على العناصر الأعلى
    """
    
    def test_get_top_items(self):
        """اختبار الحصول على العناصر الأعلى في المبيعات أو المشتريات"""
        # إنشاء مجموعة استعلام وهمية
        queryset = MagicMock()
        
        # تهيئة قيمة العودة للدالة values().annotate().order_by()
        mock_result = [
            {'product__name': 'منتج 1', 'total': 1000, 'count': 10},
            {'product__name': 'منتج 2', 'total': 800, 'count': 8},
            {'product__name': 'منتج 3', 'total': 600, 'count': 6},
        ]
        
        queryset.values.return_value = MagicMock()
        queryset.values().annotate.return_value = MagicMock()
        queryset.values().annotate().order_by.return_value = mock_result
        
        # اختبار الحصول على العناصر الأعلى
        result = get_top_items(
            queryset,
            group_by='product',
            value_field='amount',
            order_field='total',
            limit=3
        )
        
        # التحقق من النتائج
        queryset.values.assert_called_with('product', 'product__name')
        queryset.values().annotate.assert_called_with(
            total=Sum('amount'),
            count=Count('id')
        )
        queryset.values().annotate().order_by.assert_called_with('-total')
        
        self.assertEqual(result, mock_result)
        self.assertEqual(len(result), 3)


class StatsCalculationsTest(TestCase):
    """
    اختبارات دوال الحسابات الإحصائية
    """
    
    def test_calculate_growth_rate(self):
        """اختبار حساب معدل النمو"""
        # اختبار النمو الإيجابي
        self.assertEqual(calculate_growth_rate(100, 80), 25.0)  # (100 - 80) / 80 * 100
        
        # اختبار النمو السلبي
        self.assertEqual(calculate_growth_rate(80, 100), -20.0)  # (80 - 100) / 100 * 100
        
        # اختبار عندما تكون القيمة السابقة صفر
        self.assertEqual(calculate_growth_rate(100, 0), 100.0)  # نفترض نمو 100%
        
        # اختبار عندما تكون القيمتان صفر
        self.assertEqual(calculate_growth_rate(0, 0), 0.0)  # لا نمو
    
    def test_calculate_percentage(self):
        """اختبار حساب النسبة المئوية"""
        # اختبار حساب النسبة المئوية
        self.assertEqual(calculate_percentage(20, 100), 20.0)  # (20 / 100) * 100
        
        # اختبار عندما يكون المجموع صفر
        self.assertEqual(calculate_percentage(20, 0), 0.0)  # نفترض 0%
    
    def test_calculate_average(self):
        """اختبار حساب المتوسط"""
        # اختبار حساب المتوسط
        self.assertEqual(calculate_average(100, 4), 25.0)  # 100 / 4
        
        # اختبار عندما يكون العدد صفر
        self.assertEqual(calculate_average(100, 0), 0.0)  # نفترض 0 