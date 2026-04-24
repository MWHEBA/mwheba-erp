from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from users.decorators import require_superuser
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import models
import os
import subprocess
import datetime
import tempfile
import json
import sqlite3
import shutil
import zipfile
import io
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.db.models import Q

from .logs import create_log
from django.contrib.admin.views.decorators import staff_member_required
from .models import SystemLog
from product.models import Stock, Product, StockMovement
from django.contrib.auth import get_user_model
import logging


def is_superuser(user):
    """
    التحقق مما إذا كان المستخدم مشرفًا
    """
    return user.is_superuser


@login_required
@require_superuser()
def system_logs(request):
    """
    عرض سجلات النظام
    """
    from .logs import get_logs

    # الحصول على المعلمات من الطلب
    user_id = request.GET.get("user_id")
    model_name = request.GET.get("model_name")
    action = request.GET.get("action")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    try:
        # الحصول على السجلات مع تطبيق التصفية
        logs = get_logs(
            user_id=user_id,
            model_name=model_name,
            action=action,
            date_from=date_from,
            date_to=date_to,
        )

        # التأكد من أن هناك سجلات حتى إذا كانت فارغة
        if logs is None:
            logs = []
    except Exception as e:
        # في حالة وجود خطأ، سجل الخطأ وأعد قائمة فارغة
        logger = logging.getLogger(__name__)
        logger.error(f"خطأ في استرجاع سجلات النظام: {str(e)}")
        logs = []

    # عرض صفحة السجلات
    return render(
        request,
        "utils/logs.html",
        {
            "logs": logs,
            "title": _("سجلات النظام"),
            "page_title": _("سجلات النظام"),
            "page_icon": "fas fa-history",
            "breadcrumb_items": [
                {
                    "title": _("الرئيسية"),
                    "url": "core:dashboard",
                    "icon": "fas fa-home",
                },
                {"title": _("سجلات النظام"), "active": True},
            ],
        },
    )


class SystemLogView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    عرض سجلات النظام مع إمكانية التصفية حسب المستخدم والنموذج والإجراء والتاريخ
    """

    def test_func(self):
        """
        التحقق من أن المستخدم مشرف
        """
        return self.request.user.is_superuser

    def get(self, request):
        # الحصول على معايير التصفية من الطلب
        user_id = request.GET.get("user_id")
        model_name = request.GET.get("model_name")
        action = request.GET.get("action")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")

        # البدء بجميع السجلات مع تحسين الاستعلام لتجنب N+1 queries
        logs = SystemLog.objects.select_related('user').all().order_by("-timestamp")

        # تطبيق التصفية إذا تم تقديم المعايير
        if user_id:
            logs = logs.filter(user_id=user_id)

        if model_name:
            logs = logs.filter(model_name=model_name)

        if action:
            logs = logs.filter(action=action)

        # معالجة نطاق التاريخ
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
                logs = logs.filter(timestamp__date__gte=date_from_obj)
            except ValueError:
                messages.error(request, _("تنسيق تاريخ البداية غير صالح"))

        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
                # إضافة يوم واحد لتضمين اليوم المحدد بالكامل
                date_to_obj = date_to_obj + datetime.timedelta(days=1)
                logs = logs.filter(timestamp__date__lt=date_to_obj)
            except ValueError:
                messages.error(request, _("تنسيق تاريخ النهاية غير صالح"))

        # الحصول على القيم الفريدة للقوائم المنسدلة
        users = (
            get_user_model()
            .objects.filter(is_active=True)
            .order_by("first_name", "last_name")
        )
        models = (
            SystemLog.objects.values_list("model_name", flat=True)
            .distinct()
            .order_by("model_name")
        )
        actions = (
            SystemLog.objects.values_list("action", flat=True)
            .distinct()
            .order_by("action")
        )

        context = {
            "logs": logs[:200],  # تحديد عدد السجلات لتجنب البطء
            "users": users,
            "models": models,
            "actions": actions,
            "title": _("سجلات النظام"),
            "page_title": _("سجلات النظام"),
            "page_icon": "fas fa-history",
        }

        return render(request, "utils/logs.html", context)


@login_required
def inventory_check(request):
    """
    فحص المخزون للتأكد من صحة البيانات وتحديد المنتجات منخفضة المخزون
    """
    # المنتجات التي بها مخزون أقل من الحد الأدنى
    low_stock_items = Stock.objects.filter(quantity__lt=models.F("product__min_stock"))

    # المنتجات التي نفذت من المخزون
    out_of_stock_items = Stock.objects.filter(quantity__lte=0)

    context = {
        "title": _("فحص المخزون"),
        "page_title": _("فحص المخزون"),
        "page_icon": "fas fa-clipboard-check",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": "core:dashboard", "icon": "fas fa-home"},
            {"title": _("فحص المخزون"), "active": True},
        ],
        "low_stock_items": low_stock_items,
        "out_of_stock_items": out_of_stock_items,
    }

    return render(request, "utils/inventory_check.html", context)


@login_required
def system_help(request):
    """
    عرض صفحة المساعدة والدعم الفني
    """
    context = {
        "title": _("المساعدة والدعم"),
        "page_title": _("المساعدة والدعم"),
        "page_icon": "fas fa-question-circle",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": "core:dashboard", "icon": "fas fa-home"},
            {"title": _("المساعدة والدعم"), "active": True},
        ],
    }

    return render(request, "utils/system_help.html", context)


