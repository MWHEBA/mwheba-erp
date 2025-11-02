"""
Template tags للوقت بالعربي
"""
from django import template
from django.utils import timezone
from datetime import datetime, timedelta

register = template.Library()


@register.filter
def arabic_timesince(value):
    """
    تحويل الوقت إلى صيغة عربية (منذ كم)
    """
    if not value:
        return ""
    
    now = timezone.now()
    if timezone.is_aware(value):
        diff = now - value
    else:
        diff = datetime.now() - value
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "الآن"
    elif seconds < 3600:  # أقل من ساعة
        minutes = int(seconds / 60)
        if minutes == 1:
            return "منذ دقيقة"
        elif minutes == 2:
            return "منذ دقيقتين"
        elif minutes <= 10:
            return f"منذ {minutes} دقائق"
        else:
            return f"منذ {minutes} دقيقة"
    elif seconds < 86400:  # أقل من يوم
        hours = int(seconds / 3600)
        if hours == 1:
            return "منذ ساعة"
        elif hours == 2:
            return "منذ ساعتين"
        elif hours <= 10:
            return f"منذ {hours} ساعات"
        else:
            return f"منذ {hours} ساعة"
    elif seconds < 604800:  # أقل من أسبوع
        days = int(seconds / 86400)
        if days == 1:
            return "منذ يوم"
        elif days == 2:
            return "منذ يومين"
        elif days <= 10:
            return f"منذ {days} أيام"
        else:
            return f"منذ {days} يوم"
    elif seconds < 2592000:  # أقل من شهر
        weeks = int(seconds / 604800)
        if weeks == 1:
            return "منذ أسبوع"
        elif weeks == 2:
            return "منذ أسبوعين"
        else:
            return f"منذ {weeks} أسابيع"
    elif seconds < 31536000:  # أقل من سنة
        months = int(seconds / 2592000)
        if months == 1:
            return "منذ شهر"
        elif months == 2:
            return "منذ شهرين"
        elif months <= 10:
            return f"منذ {months} أشهر"
        else:
            return f"منذ {months} شهر"
    else:  # أكثر من سنة
        years = int(seconds / 31536000)
        if years == 1:
            return "منذ سنة"
        elif years == 2:
            return "منذ سنتين"
        elif years <= 10:
            return f"منذ {years} سنوات"
        else:
            return f"منذ {years} سنة"
