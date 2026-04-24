# -*- coding: utf-8 -*-
"""
خدمة تحليلات المنتجات المجمعة
Bundle Analytics Service

توفر إحصائيات وتحليلات شاملة للمنتجات المجمعة
Requirements: 5.1, 5.2
"""

from django.db import models
from django.db.models import Count, Sum, Avg, Q, F, Case, When
from django.utils import timezone
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

from ..models import Product, BundleComponent
from .bundle_query_optimizer import BundleQueryOptimizer

logger = logging.getLogger('bundle_system')


class BundleAnalyticsService:
    """
    خدمة تحليلات المنتجات المجمعة
    
    توفر:
    - إحصائيات الأداء
    - تحليل المبيعات
    - تقارير المخزون
    - مقاييس الاستخدام
    
    Requirements: 5.1, 5.2
    """
    
    @classmethod
    def get_dashboard_stats(cls) -> Dict[str, Any]:
        """الحصول على إحصائيات لوحة التحكم الرئيسية"""
        try:
            # إحصائيات أساسية
            total_bundles = Product.objects.filter(is_bundle=True).count()
            active_bundles = Product.objects.filter(is_bundle=True, is_active=True).count()
            inactive_bundles = total_bundles - active_bundles
            
            # إحصائيات المكونات
            total_components = BundleComponent.objects.count()
            avg_components = BundleComponent.objects.values('bundle_product').annotate(
                count=Count('id')
            ).aggregate(avg=Avg('count'))['avg'] or 0
            
            # المنتجات المجمعة بدون مكونات
            bundles_without_components = Product.objects.filter(
                is_bundle=True
            ).annotate(
                component_count=Count('components')
            ).filter(component_count=0).count()
            
            # المنتجات المجمعة مع مكونات غير نشطة
            bundles_with_inactive_components = Product.objects.filter(
                is_bundle=True,
                is_active=True,
                components__component_product__is_active=False
            ).distinct().count()
            
            return {
                'total_bundles': total_bundles,
                'active_bundles': active_bundles,
                'inactive_bundles': inactive_bundles,
                'total_components': total_components,
                'avg_components_per_bundle': round(avg_components, 1),
                'bundles_without_components': bundles_without_components,
                'bundles_with_inactive_components': bundles_with_inactive_components,
                'bundle_utilization_rate': round((active_bundles / total_bundles * 100) if total_bundles > 0 else 0, 1)
            }
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات لوحة التحكم: {str(e)}")
            return {}
    
    @classmethod
    def get_bundle_performance_metrics(cls, days: int = 30) -> Dict[str, Any]:
        """الحصول على مقاييس أداء المنتجات المجمعة"""
        try:
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)
            
            # المنتجات المجمعة الأكثر شعبية (بناءً على عدد المكونات كمؤشر)
            popular_bundles = Product.objects.filter(
                is_bundle=True,
                is_active=True
            ).annotate(
                component_count=Count('components')
            ).order_by('-component_count')[:10]
            
            # توزيع المنتجات المجمعة حسب عدد المكونات
            component_distribution = BundleComponent.objects.values(
                'bundle_product__name'
            ).annotate(
                component_count=Count('id')
            ).order_by('-component_count')[:10]
            
            # المكونات الأكثر استخداماً
            popular_components = BundleComponent.objects.values(
                'component_product__name'
            ).annotate(
                usage_count=Count('bundle_product')
            ).order_by('-usage_count')[:10]
            
            return {
                'period_days': days,
                'popular_bundles': [
                    {
                        'name': bundle.name,
                        'component_count': bundle.component_count,
                        'is_active': bundle.is_active
                    }
                    for bundle in popular_bundles
                ],
                'component_distribution': list(component_distribution),
                'popular_components': list(popular_components)
            }
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على مقاييس الأداء: {str(e)}")
            return {}
    
    @classmethod
    def get_stock_analytics(cls) -> Dict[str, Any]:
        """تحليل مخزون المنتجات المجمعة"""
        try:
            from .stock_calculation_engine import StockCalculationEngine
            
            # تصنيف المنتجات المجمعة حسب حالة المخزون
            stock_categories = {
                'high_stock': 0,      # مخزون عالي (أكثر من 10)
                'medium_stock': 0,    # مخزون متوسط (5-10)
                'low_stock': 0,       # مخزون منخفض (1-4)
                'out_of_stock': 0     # نفذ المخزون (0)
            }
            
            stock_details = []
            
            # فحص عينة من المنتجات المجمعة النشطة
            active_bundles = Product.objects.filter(is_bundle=True, is_active=True)[:50]
            
            for bundle in active_bundles:
                try:
                    calculated_stock = StockCalculationEngine.calculate_bundle_stock(bundle)
                    
                    if calculated_stock > 10:
                        stock_categories['high_stock'] += 1
                        category = 'high'
                    elif calculated_stock >= 5:
                        stock_categories['medium_stock'] += 1
                        category = 'medium'
                    elif calculated_stock > 0:
                        stock_categories['low_stock'] += 1
                        category = 'low'
                    else:
                        stock_categories['out_of_stock'] += 1
                        category = 'out'
                    
                    stock_details.append({
                        'bundle_name': bundle.name,
                        'calculated_stock': calculated_stock,
                        'category': category
                    })
                    
                except Exception:
                    continue
            
            # المنتجات المجمعة التي تحتاج لإعادة تخزين
            low_stock_bundles = [
                detail for detail in stock_details 
                if detail['category'] in ['low', 'out']
            ]
            
            return {
                'stock_categories': stock_categories,
                'low_stock_bundles': low_stock_bundles[:10],  # أول 10
                'total_analyzed': len(stock_details),
                'stock_health_score': cls._calculate_stock_health_score(stock_categories)
            }
            
        except Exception as e:
            logger.error(f"خطأ في تحليل المخزون: {str(e)}")
            return {}
    
    @classmethod
    def get_component_usage_analytics(cls) -> Dict[str, Any]:
        """تحليل استخدام المكونات في المنتجات المجمعة"""
        try:
            # المكونات الأكثر استخداماً
            component_usage = BundleComponent.objects.values(
                'component_product__name',
                'component_product__id'
            ).annotate(
                bundle_count=Count('bundle_product', distinct=True),
                total_quantity_needed=Sum('required_quantity')
            ).order_by('-bundle_count')
            
            # المكونات غير المستخدمة (منتجات عادية لا تستخدم في أي منتج مجمع)
            used_component_ids = BundleComponent.objects.values_list(
                'component_product_id', flat=True
            ).distinct()
            
            unused_products = Product.objects.filter(
                is_active=True,
                is_bundle=False
            ).exclude(
                id__in=used_component_ids
            ).count()
            
            # توزيع الكميات المطلوبة
            quantity_distribution = BundleComponent.objects.values(
                'required_quantity'
            ).annotate(
                count=Count('id')
            ).order_by('required_quantity')
            
            return {
                'component_usage': list(component_usage[:15]),
                'unused_products_count': unused_products,
                'quantity_distribution': list(quantity_distribution),
                'total_unique_components': component_usage.count()
            }
            
        except Exception as e:
            logger.error(f"خطأ في تحليل استخدام المكونات: {str(e)}")
            return {}
    
    @classmethod
    def get_bundle_trends(cls, days: int = 30) -> Dict[str, Any]:
        """تحليل اتجاهات المنتجات المجمعة"""
        try:
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)
            
            # المنتجات المجمعة المضافة حديثاً
            recent_bundles = Product.objects.filter(
                is_bundle=True,
                created_at__gte=start_date
            ).order_by('-created_at')
            
            # توزيع المنتجات المجمعة حسب التاريخ
            daily_creation = {}
            for bundle in recent_bundles:
                date_key = bundle.created_at.date().isoformat()
                daily_creation[date_key] = daily_creation.get(date_key, 0) + 1
            
            # المنتجات المجمعة المعدلة حديثاً
            recently_modified = Product.objects.filter(
                is_bundle=True,
                updated_at__gte=start_date
            ).exclude(
                created_at__gte=start_date  # استبعاد المنشأة حديثاً
            ).order_by('-updated_at')[:10]
            
            return {
                'period_days': days,
                'recent_bundles_count': recent_bundles.count(),
                'daily_creation': daily_creation,
                'recently_modified': [
                    {
                        'name': bundle.name,
                        'updated_at': bundle.updated_at,
                        'is_active': bundle.is_active
                    }
                    for bundle in recently_modified
                ]
            }
            
        except Exception as e:
            logger.error(f"خطأ في تحليل الاتجاهات: {str(e)}")
            return {}
    
    @classmethod
    def get_system_health_metrics(cls) -> Dict[str, Any]:
        """مقاييس صحة نظام المنتجات المجمعة"""
        try:
            # فحص المشاكل الشائعة
            issues = {
                'bundles_without_components': Product.objects.filter(
                    is_bundle=True,
                    is_active=True
                ).annotate(
                    component_count=Count('components')
                ).filter(component_count=0).count(),
                
                'inactive_components_in_active_bundles': BundleComponent.objects.filter(
                    bundle_product__is_active=True,
                    component_product__is_active=False
                ).count(),
                
                'zero_quantity_components': BundleComponent.objects.filter(
                    required_quantity__lte=0
                ).count()
            }
            
            # حساب نقاط الصحة
            total_bundles = Product.objects.filter(is_bundle=True, is_active=True).count()
            health_score = 100
            
            if total_bundles > 0:
                # خصم نقاط للمشاكل
                health_score -= (issues['bundles_without_components'] / total_bundles) * 30
                health_score -= (issues['inactive_components_in_active_bundles'] / total_bundles) * 20
                health_score -= (issues['zero_quantity_components'] / total_bundles) * 10
                
                health_score = max(0, min(100, health_score))
            
            # تحديد حالة النظام
            if health_score >= 90:
                system_status = 'excellent'
                status_text = 'ممتاز'
            elif health_score >= 75:
                system_status = 'good'
                status_text = 'جيد'
            elif health_score >= 60:
                system_status = 'fair'
                status_text = 'مقبول'
            else:
                system_status = 'poor'
                status_text = 'يحتاج تحسين'
            
            return {
                'health_score': round(health_score, 1),
                'system_status': system_status,
                'status_text': status_text,
                'issues': issues,
                'total_active_bundles': total_bundles
            }
            
        except Exception as e:
            logger.error(f"خطأ في حساب مقاييس صحة النظام: {str(e)}")
            return {'health_score': 0, 'system_status': 'error'}
    
    @classmethod
    def _calculate_stock_health_score(cls, stock_categories: Dict[str, int]) -> float:
        """حساب نقاط صحة المخزون"""
        total = sum(stock_categories.values())
        if total == 0:
            return 0
        
        # وزن كل فئة
        weights = {
            'high_stock': 1.0,
            'medium_stock': 0.8,
            'low_stock': 0.4,
            'out_of_stock': 0.0
        }
        
        weighted_sum = sum(
            stock_categories[category] * weight 
            for category, weight in weights.items()
        )
        
        return round((weighted_sum / total) * 100, 1)
    
    @classmethod
    def generate_analytics_report(cls, include_details: bool = False) -> Dict[str, Any]:
        """إنشاء تقرير تحليلي شامل"""
        try:
            report = {
                'generated_at': timezone.now(),
                'dashboard_stats': cls.get_dashboard_stats(),
                'performance_metrics': cls.get_bundle_performance_metrics(),
                'stock_analytics': cls.get_stock_analytics(),
                'system_health': cls.get_system_health_metrics()
            }
            
            if include_details:
                report.update({
                    'component_usage': cls.get_component_usage_analytics(),
                    'trends': cls.get_bundle_trends()
                })
            
            return report
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء التقرير التحليلي: {str(e)}")
            return {'error': str(e)}


class BundleChartDataService:
    """
    خدمة بيانات الرسوم البيانية للمنتجات المجمعة
    
    Requirements: 5.1, 5.2
    """
    
    @classmethod
    def get_bundle_distribution_chart(cls) -> Dict[str, Any]:
        """بيانات رسم توزيع المنتجات المجمعة"""
        try:
            # توزيع حسب الحالة
            active_count = Product.objects.filter(is_bundle=True, is_active=True).count()
            inactive_count = Product.objects.filter(is_bundle=True, is_active=False).count()
            
            return {
                'type': 'doughnut',
                'data': {
                    'labels': ['نشط', 'غير نشط'],
                    'datasets': [{
                        'data': [active_count, inactive_count],
                        'backgroundColor': ['#28a745', '#dc3545'],
                        'borderWidth': 2
                    }]
                },
                'options': {
                    'responsive': True,
                    'plugins': {
                        'legend': {
                            'position': 'bottom'
                        }
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"خطأ في بيانات رسم التوزيع: {str(e)}")
            return {}
    
    @classmethod
    def get_component_usage_chart(cls) -> Dict[str, Any]:
        """بيانات رسم استخدام المكونات"""
        try:
            # أكثر 10 مكونات استخداماً
            component_data = BundleComponent.objects.values(
                'component_product__name'
            ).annotate(
                usage_count=Count('bundle_product')
            ).order_by('-usage_count')[:10]
            
            labels = [item['component_product__name'] for item in component_data]
            data = [item['usage_count'] for item in component_data]
            
            return {
                'type': 'bar',
                'data': {
                    'labels': labels,
                    'datasets': [{
                        'label': 'عدد مرات الاستخدام',
                        'data': data,
                        'backgroundColor': '#007bff',
                        'borderColor': '#0056b3',
                        'borderWidth': 1
                    }]
                },
                'options': {
                    'responsive': True,
                    'scales': {
                        'y': {
                            'beginAtZero': True
                        }
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"خطأ في بيانات رسم استخدام المكونات: {str(e)}")
            return {}
    
    @classmethod
    def get_bundle_creation_trend_chart(cls, days: int = 30) -> Dict[str, Any]:
        """بيانات رسم اتجاه إنشاء المنتجات المجمعة"""
        try:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days)
            
            # إنشاء قائمة بجميع التواريخ في النطاق
            date_range = []
            current_date = start_date
            while current_date <= end_date:
                date_range.append(current_date)
                current_date += timedelta(days=1)
            
            # حساب عدد المنتجات المجمعة المنشأة في كل يوم
            daily_counts = {}
            bundles = Product.objects.filter(
                is_bundle=True,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date
            )
            
            for bundle in bundles:
                date_key = bundle.created_at.date()
                daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
            
            # تحضير البيانات للرسم
            labels = [date.strftime('%Y-%m-%d') for date in date_range]
            data = [daily_counts.get(date, 0) for date in date_range]
            
            return {
                'type': 'line',
                'data': {
                    'labels': labels,
                    'datasets': [{
                        'label': 'منتجات مجمعة جديدة',
                        'data': data,
                        'borderColor': '#28a745',
                        'backgroundColor': 'rgba(40, 167, 69, 0.1)',
                        'fill': True,
                        'tension': 0.4
                    }]
                },
                'options': {
                    'responsive': True,
                    'scales': {
                        'y': {
                            'beginAtZero': True
                        }
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"خطأ في بيانات رسم اتجاه الإنشاء: {str(e)}")
            return {}