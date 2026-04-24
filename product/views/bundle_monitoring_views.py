# -*- coding: utf-8 -*-
"""
عروض مراقبة نظام المنتجات المجمعة
Bundle System Monitoring Views

Requirements: 10.4, 10.5
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.urls import reverse
from typing import Dict, Any

from ..monitoring import BundleSystemMonitor, BundleAlertManager
from ..models import Product


def is_admin_user(user):
    """التحقق من أن المستخدم مدير"""
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(is_admin_user)
def bundle_monitoring_dashboard(request):
    """لوحة مراقبة نظام المنتجات المجمعة"""
    try:
        # الحصول على تقرير صحة النظام
        health_report = BundleSystemMonitor.get_system_health()
        
        # الحصول على التنبيهات الحديثة
        recent_alerts = BundleAlertManager.get_recent_alerts(hours=24)
        
        # إحصائيات سريعة
        quick_stats = {
            'total_bundles': Product.objects.filter(is_bundle=True).count(),
            'active_bundles': Product.objects.filter(is_bundle=True, is_active=True).count(),
            'recent_alerts_count': len(recent_alerts),
            'system_status': health_report.get('system_status', 'unknown')
        }
        
        # إعداد السياق
        context = {
            'title': 'مراقبة نظام المنتجات المجمعة',
            'active_menu': 'bundle_monitoring',
            'health_report': health_report,
            'recent_alerts': recent_alerts[:10],  # أحدث 10 تنبيهات
            'quick_stats': quick_stats,
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المنتجات', 'url': reverse('product:list'), 'icon': 'fas fa-boxes'},
                {'title': 'مراقبة المنتجات المجمعة', 'active': True}
            ],
            'header_buttons': [
                {
                    'url': reverse('product:bundle_integrity_check'),
                    'icon': 'fa-check-circle',
                    'text': 'فحص التكامل',
                    'class': 'btn-primary'
                },
                {
                    'onclick': 'refreshMonitoring()',
                    'icon': 'fa-sync',
                    'text': 'تحديث',
                    'class': 'btn-outline-secondary'
                }
            ]
        }
        
        return render(request, 'product/bundle_monitoring_dashboard.html', context)
        
    except Exception as e:
        messages.error(request, f'خطأ في تحميل لوحة المراقبة: {str(e)}')
        return render(request, 'product/bundle_monitoring_dashboard.html', {
            'title': 'مراقبة نظام المنتجات المجمعة',
            'error': str(e)
        })


@login_required
@user_passes_test(is_admin_user)
@require_http_methods(["GET"])
def bundle_health_api(request):
    """API للحصول على تقرير صحة النظام"""
    try:
        health_report = BundleSystemMonitor.get_system_health()
        return JsonResponse({
            'success': True,
            'data': health_report
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_user)
@require_http_methods(["GET"])
def bundle_alerts_api(request):
    """API للحصول على التنبيهات"""
    try:
        hours = int(request.GET.get('hours', 24))
        alerts = BundleAlertManager.get_recent_alerts(hours=hours)
        
        return JsonResponse({
            'success': True,
            'data': {
                'alerts': alerts,
                'total_count': len(alerts)
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_user)
@require_http_methods(["GET"])
def bundle_operation_stats_api(request):
    """API للحصول على إحصائيات العمليات"""
    try:
        operation_type = request.GET.get('operation_type', 'bundle_sale')
        hours = int(request.GET.get('hours', 24))
        
        stats = BundleSystemMonitor.get_operation_stats(operation_type, hours)
        
        return JsonResponse({
            'success': True,
            'data': stats
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_user)
def bundle_integrity_check(request):
    """صفحة فحص تكامل البيانات"""
    context = {
        'title': 'فحص تكامل المنتجات المجمعة',
        'active_menu': 'bundle_monitoring',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:list'), 'icon': 'fas fa-boxes'},
            {'title': 'مراقبة المنتجات المجمعة', 'url': reverse('product:bundle_monitoring'), 'icon': 'fas fa-chart-line'},
            {'title': 'فحص التكامل', 'active': True}
        ],
        'header_buttons': [
            {
                'onclick': 'runIntegrityCheck()',
                'icon': 'fa-play',
                'text': 'تشغيل الفحص',
                'class': 'btn-primary'
            },
            {
                'url': reverse('product:bundle_monitoring'),
                'icon': 'fa-arrow-right',
                'text': 'العودة للمراقبة',
                'class': 'btn-outline-secondary'
            }
        ]
    }
    
    return render(request, 'product/bundle_integrity_check.html', context)


@login_required
@user_passes_test(is_admin_user)
@require_http_methods(["POST"])
def run_integrity_check_api(request):
    """API لتشغيل فحص التكامل"""
    try:
        from django.core.management import call_command
        from io import StringIO
        import json
        
        # تشغيل أمر فحص التكامل
        output = StringIO()
        call_command('verify_bundle_integrity', stdout=output, verbosity=1)
        
        # يمكن إضافة منطق لتحليل النتائج هنا
        result = {
            'success': True,
            'message': 'تم تشغيل فحص التكامل بنجاح',
            'output': output.getvalue()
        }
        
        return JsonResponse(result)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في تشغيل فحص التكامل: {str(e)}'
        }, status=500)