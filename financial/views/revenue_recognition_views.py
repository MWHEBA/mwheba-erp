"""
RevenueRecognitionViews - مناظر إدارة ومتابعة الإيرادات المؤجلة وتوزيع العقود (IFRS 15)
"""

from decimal import Decimal
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum

from financial.models.revenue_recognition import (
    RevenueRecognitionSchedule,
    RevenueRecognitionScheduleLine,
    RevenueRecognitionEntry
)
from financial.services.revenue_recognition_service import RevenueRecognitionService


@login_required
def revenue_recognition_dashboard_view(request):
    """
    الداشبورد المالي لمتابعة الإيرادات المؤجلة والأقساط
    """
    today = timezone.now().date()

    schedules = RevenueRecognitionSchedule.objects.select_related(
        "policy", "invoice_item__sales_invoice__customer"
    ).prefetch_related("lines").all().order_by("-created_at")

    total_deferred = schedules.aggregate(s=Sum("deferred_amount"))["s"] or Decimal("0.00")
    total_recognized = schedules.aggregate(s=Sum("recognized_amount"))["s"] or Decimal("0.00")
    due_lines_count = RevenueRecognitionScheduleLine.objects.filter(
        status="SCHEDULED", recognition_date__lte=today, schedule__status="ACTIVE"
    ).count()
    active_schedules_count = schedules.filter(status="ACTIVE").count()

    breadcrumb_items = [
        {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
        {"title": _("الإدارة المالية"), "url": reverse("financial:chart_of_accounts_list"), "icon": "fa-calculator"},
        {"title": _("إقرار وتوزيع الإيرادات (IFRS 15)"), "active": True},
    ]

    context = {
        "page_title": _("لوحة إقرار وتوزيع الإيرادات المؤجلة (IFRS 15)"),
        "page_icon": "fa-hand-holding-usd",
        "breadcrumb_items": breadcrumb_items,
        "schedules": schedules,
        "total_deferred_amount": total_deferred,
        "total_recognized_amount": total_recognized,
        "due_lines_count": due_lines_count,
        "active_schedules_count": active_schedules_count,
        "today_date": today,
    }
    return render(request, "financial/revenue_recognition_dashboard.html", context)


@login_required
def process_due_revenues_action_view(request):
    """
    إجراء ترحيل أقساط الإيرادات المستحقة من لوحة التحكم
    """
    if request.method == "POST":
        date_str = request.POST.get("as_of_date")
        target_date = None
        if date_str:
            try:
                from datetime import datetime
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                target_date = None

        target_date = target_date or timezone.now().date()
        result = RevenueRecognitionService.process_all_due_schedules(as_of_date=target_date, user=request.user)

        if result["processed_count"] > 0:
            messages.success(
                request,
                _(f"تم ترحيل {result['processed_count']} قسط إيراد مستحق بنجاح بإجمالي {result['total_recognized_amount']} EGP.")
            )
        else:
            messages.info(request, _("لا توجد أقساط جديدة مستحقة للترحيل حتى هذا التاريخ."))

        if result.get("failed_count", 0) > 0:
            messages.warning(request, _(f"تعذر ترحيل {result['failed_count']} قسط، يرجى مراجعة سجل الأخطاء."))

    return redirect("financial:revenue_recognition_dashboard")
