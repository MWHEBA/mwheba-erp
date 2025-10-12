from django.db.models import Sum, Count, Avg
from django.utils import timezone
from datetime import timedelta


def get_date_range_stats(queryset, date_field, value_field, range_type='daily', start_date=None, end_date=None):
    """
    الحصول على إحصائيات لفترة زمنية محددة
    
    المعلمات:
    queryset: مجموعة الاستعلام
    date_field: اسم حقل التاريخ
    value_field: اسم حقل القيمة
    range_type: نوع النطاق الزمني (daily, weekly, monthly, yearly, custom)
    start_date: تاريخ البداية (في حالة النطاق المخصص)
    end_date: تاريخ النهاية (في حالة النطاق المخصص)
    
    تُرجع:
    dict: إحصائيات النطاق الزمني
    """
    today = timezone.now().date()
    
    # تحديد نطاق التاريخ بناءً على النوع
    filter_kwargs = {}
    
    if range_type == 'daily':
        filter_kwargs[f'{date_field}__date'] = today
    elif range_type == 'weekly':
        start_of_week = today - timedelta(days=today.weekday())
        filter_kwargs[f'{date_field}__date__gte'] = start_of_week
        filter_kwargs[f'{date_field}__date__lte'] = today
    elif range_type == 'monthly':
        filter_kwargs[f'{date_field}__year'] = today.year
        filter_kwargs[f'{date_field}__month'] = today.month
    elif range_type == 'yearly':
        filter_kwargs[f'{date_field}__year'] = today.year
    elif range_type == 'custom' and start_date and end_date:
        filter_kwargs[f'{date_field}__date__gte'] = start_date.date() if hasattr(start_date, 'date') else start_date
        filter_kwargs[f'{date_field}__date__lte'] = end_date.date() if hasattr(end_date, 'date') else end_date
    
    # تطبيق الاستعلام مع الفلتر
    filtered_queryset = queryset.filter(**filter_kwargs)
    
    # حساب الإحصائيات
    stats = filtered_queryset.aggregate(
        total=Sum(value_field),
        count=Count('id')
    )
    
    # التعامل مع القيم الفارغة
    if stats['total'] is None:
        stats['total'] = 0
    
    return stats


def get_period_comparison(queryset, date_field, value_field, range_type='monthly', custom_period=None):
    """
    مقارنة بين فترتين زمنيتين
    
    المعلمات:
    queryset: مجموعة الاستعلام
    date_field: اسم حقل التاريخ
    value_field: اسم حقل القيمة
    range_type: نوع النطاق الزمني (daily, weekly, monthly, yearly)
    custom_period: عدد الأيام للفترة المخصصة
    
    تُرجع:
    dict: بيانات المقارنة بين الفترتين
    """
    today = timezone.now().date()
    
    # تحديد بداية ونهاية الفترة الحالية
    if range_type == 'daily':
        current_start = today
        current_end = today
        
        previous_start = today - timedelta(days=1)
        previous_end = previous_start
    elif range_type == 'weekly':
        current_start = today - timedelta(days=today.weekday())
        current_end = today
        
        previous_start = current_start - timedelta(days=7)
        previous_end = current_start - timedelta(days=1)
    elif range_type == 'monthly':
        # الشهر الحالي
        current_start = today.replace(day=1)
        current_end = today
        
        # الشهر السابق (تقريبي)
        if current_start.month == 1:
            previous_start = current_start.replace(year=current_start.year-1, month=12, day=1)
        else:
            previous_start = current_start.replace(month=current_start.month-1)
        
        previous_end = current_start - timedelta(days=1)
    elif range_type == 'yearly':
        # السنة الحالية
        current_start = today.replace(month=1, day=1)
        current_end = today
        
        # السنة السابقة
        previous_start = current_start.replace(year=current_start.year-1)
        previous_end = current_end.replace(year=current_end.year-1)
    elif range_type == 'custom' and custom_period:
        # فترة مخصصة
        current_end = today
        current_start = today - timedelta(days=custom_period)
        
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=custom_period)
    else:
        # افتراضي: الشهر الحالي
        current_start = today.replace(day=1)
        current_end = today
        
        # الشهر السابق (تقريبي)
        if current_start.month == 1:
            previous_start = current_start.replace(year=current_start.year-1, month=12, day=1)
        else:
            previous_start = current_start.replace(month=current_start.month-1)
        
        previous_end = current_start - timedelta(days=1)
    
    # الحصول على إحصائيات الفترة الحالية
    current_stats = get_date_range_stats(
        queryset=queryset,
        date_field=date_field,
        value_field=value_field,
        range_type='custom',
        start_date=current_start,
        end_date=current_end
    )
    
    # الحصول على إحصائيات الفترة السابقة
    previous_stats = get_date_range_stats(
        queryset=queryset,
        date_field=date_field,
        value_field=value_field,
        range_type='custom',
        start_date=previous_start,
        end_date=previous_end
    )
    
    # حساب معدل النمو
    growth_rate = calculate_growth_rate(
        current_stats['total'],
        previous_stats['total']
    )
    
    count_growth_rate = calculate_growth_rate(
        current_stats['count'],
        previous_stats['count']
    )
    
    return {
        'current_period': current_stats,
        'previous_period': previous_stats,
        'growth_rate': growth_rate,
        'count_growth_rate': count_growth_rate,
        'period_info': {
            'current_start': current_start,
            'current_end': current_end,
            'previous_start': previous_start,
            'previous_end': previous_end
        }
    }


def get_top_items(queryset, group_by, value_field, order_field='total', limit=5):
    """
    الحصول على العناصر الأعلى في المبيعات أو المشتريات
    
    المعلمات:
    queryset: مجموعة الاستعلام
    group_by: حقل التجميع
    value_field: حقل القيمة
    order_field: حقل الترتيب
    limit: عدد العناصر
    
    تُرجع:
    list: قائمة بالعناصر الأعلى
    """
    result = queryset.values(group_by, f'{group_by}__name').annotate(
        total=Sum(value_field),
        count=Count('id')
    ).order_by(f'-{order_field}')[:limit]
    
    return list(result)


def calculate_growth_rate(current_value, previous_value):
    """
    حساب معدل النمو
    
    المعلمات:
    current_value: القيمة الحالية
    previous_value: القيمة السابقة
    
    تُرجع:
    float: معدل النمو (نسبة مئوية)
    """
    if previous_value == 0:
        if current_value == 0:
            return 0
        return 100.0  # نمو 100% من الصفر
    
    return ((current_value - previous_value) / previous_value) * 100


def calculate_percentage(value, total):
    """
    حساب النسبة المئوية
    
    المعلمات:
    value: القيمة
    total: المجموع
    
    تُرجع:
    float: النسبة المئوية
    """
    if total == 0:
        return 0
    
    return (value / total) * 100


def calculate_average(total, count):
    """
    حساب المتوسط
    
    المعلمات:
    total: المجموع
    count: العدد
    
    تُرجع:
    float: المتوسط
    """
    if count == 0:
        return 0
    
    return total / count 