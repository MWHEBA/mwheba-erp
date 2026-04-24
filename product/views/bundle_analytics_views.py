# -*- coding: utf-8 -*-
"""
عروض تحليلات المنتجات المجمعة
Bundle Analytics Views

Requirements: 5.1, 5.2
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.urls import reverse
from typing import Dict, Any

from ..services.bundle_analytics_service import BundleAnalyticsService, BundleChartDataService


def is_admin_user(user):
    """التحقق من أن المستخدم مدير"""
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(is_admin_user)
def bundle_analytics_dashboard(request):
    """لوحة تحليلات المنتجات المجمعة"""
    try:
        # الحصول على الإحصائيات الأساسية
        dashboard_stats = BundleAnalyticsService.get_dashboard_stats()
        performance_metrics = BundleAnalyticsService.get_bundle_performance_metrics()
        stock_analytics = BundleAnalyticsService.get_stock_analytics()
        system_health = BundleAnalyticsService.get_system_health_metrics()
        
        # إعداد بطاقات الإحصائيات
        stats_cards = [
            {
                'title': 'إجمالي المنتجات المجمعة',
                'value': dashboard_stats.get('total_bundles', 0),
                'icon': 'fas fa-boxes',
                'color': 'primary',
                'unit': 'منتج'
            },
            {
                'title': 'المنتجات النشطة',
                'value': dashboard_stats.get('active_bundles', 0),
                'icon': 'fas fa-check-circle',
                'color': 'success',
                'unit': 'منتج'
            },
            {
                'title': 'متوسط المكونات',
                'value': dashboard_stats.get('avg_components_per_bundle', 0),
                'icon': 'fas fa-puzzle-piece',
                'color': 'info',
                'unit': 'مكون'
            },
            {
                'title': 'نقاط صحة النظام',
                'value': system_health.get('health_score', 0),
                'icon': 'fas fa-heartbeat',
                'color': _get_health_color(system_health.get('health_score', 0)),
                'unit': '%'
            }
        ]
        
        # إعداد السياق
        context = {
            'title': 'تحليلات المنتجات المجمعة',
            'active_menu': 'bundle_analytics',
            'stats_cards': stats_cards,
            'dashboard_stats': dashboard_stats,
            'performance_metrics': performance_metrics,
            'stock_analytics': stock_analytics,
            'system_health': system_health,
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المنتجات', 'url': reverse('product:list'), 'icon': 'fas fa-boxes'},
                {'title': 'تحليلات المنتجات المجمعة', 'active': True}
            ],
            'header_buttons': [
                {
                    'onclick': 'exportAnalyticsReport()',
                    'icon': 'fa-download',
                    'text': 'تصدير التقرير',
                    'class': 'btn-primary'
                },
                {
                    'onclick': 'refreshAnalytics()',
                    'icon': 'fa-sync',
                    'text': 'تحديث',
                    'class': 'btn-outline-secondary'
                }
            ]
        }
        
        return render(request, 'product/bundle_analytics_dashboard.html', context)
        
    except Exception as e:
        messages.error(request, f'خطأ في تحميل لوحة التحليلات: {str(e)}')
        return render(request, 'product/bundle_analytics_dashboard.html', {
            'title': 'تحليلات المنتجات المجمعة',
            'error': str(e)
        })


@login_required
@user_passes_test(is_admin_user)
@require_http_methods(["GET"])
def bundle_analytics_api(request):
    """API للحصول على بيانات التحليلات"""
    try:
        analytics_type = request.GET.get('type', 'dashboard')
        
        if analytics_type == 'dashboard':
            data = BundleAnalyticsService.get_dashboard_stats()
        elif analytics_type == 'performance':
            days = int(request.GET.get('days', 30))
            data = BundleAnalyticsService.get_bundle_performance_metrics(days)
        elif analytics_type == 'stock':
            data = BundleAnalyticsService.get_stock_analytics()
        elif analytics_type == 'components':
            data = BundleAnalyticsService.get_component_usage_analytics()
        elif analytics_type == 'trends':
            days = int(request.GET.get('days', 30))
            data = BundleAnalyticsService.get_bundle_trends(days)
        elif analytics_type == 'health':
            data = BundleAnalyticsService.get_system_health_metrics()
        else:
            return JsonResponse({
                'success': False,
                'error': 'نوع التحليل غير مدعوم'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_user)
@require_http_methods(["GET"])
def bundle_chart_data_api(request):
    """API للحصول على بيانات الرسوم البيانية"""
    try:
        chart_type = request.GET.get('type', 'distribution')
        
        if chart_type == 'distribution':
            data = BundleChartDataService.get_bundle_distribution_chart()
        elif chart_type == 'component_usage':
            data = BundleChartDataService.get_component_usage_chart()
        elif chart_type == 'creation_trend':
            days = int(request.GET.get('days', 30))
            data = BundleChartDataService.get_bundle_creation_trend_chart(days)
        else:
            return JsonResponse({
                'success': False,
                'error': 'نوع الرسم البياني غير مدعوم'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'data': data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@user_passes_test(is_admin_user)
@require_http_methods(["GET"])
def bundle_analytics_report_api(request):
    """API لإنشاء تقرير تحليلي شامل"""
    try:
        include_details = request.GET.get('details', 'false').lower() == 'true'
        
        report = BundleAnalyticsService.generate_analytics_report(
            include_details=include_details
        )
        
        return JsonResponse({
            'success': True,
            'data': report
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def _get_health_color(health_score: float) -> str:
    """تحديد لون بطاقة صحة النظام"""
    if health_score >= 90:
        return 'success'
    elif health_score >= 75:
        return 'info'
    elif health_score >= 60:
        return 'warning'
    else:
        return 'danger'