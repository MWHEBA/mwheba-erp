from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.paginator import Paginator

from financial.models.revenue_recognition import RevenueRecognitionSchedule, RevenueRecognitionPolicy, RevenueRecognitionScheduleLine


@login_required
def revenue_schedule_list(request):
    """عرض قائمة جداول الاعتراف بالإيراد المؤجل"""
    schedules = RevenueRecognitionSchedule.objects.select_related('policy').order_by('-created_at')
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        schedules = schedules.filter(status=status_filter)

    paginator = Paginator(schedules, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'financial/revenue_schedule_list.html', {
        'page_obj': page_obj,
        'schedules': page_obj.object_list,
        'status_filter': status_filter,
        'page_title': _("جداول الاعتراف بالإيراد المؤجل"),
        'page_subtitle': _("متابعة الاعتراف بالإيرادات وجدول الفترات المالية"),
        'page_icon': "fas fa-calendar-check",
    })
