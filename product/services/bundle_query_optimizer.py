# -*- coding: utf-8 -*-
"""
محسن استعلامات قاعدة البيانات للمنتجات المجمعة
Bundle Database Query Optimizer

يوفر استعلامات محسنة للمنتجات المجمعة مع select_related و prefetch_related
Requirements: 9.2
"""

from django.db import models
from django.db.models import Prefetch, Count, Sum, Q, F, QuerySet
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger('bundle_system')


class BundleQueryOptimizer:
    """
    محسن استعلامات المنتجات المجمعة
    
    يوفر استعلامات محسنة مع:
    - select_related للعلاقات المباشرة
    - prefetch_related للعلاقات المتعددة
    - تجميع البيانات المطلوبة
    - فهرسة محسنة
    
    Requirements: 9.2
    """
    
    @classmethod
    def get_bundles_with_components(cls, bundle_ids: List[int] = None) -> QuerySet:
        """
        الحصول على المنتجات المجمعة مع مكوناتها بشكل محسن
        
        Args:
            bundle_ids: قائمة معرفات المنتجات المجمعة (اختياري)
            
        Returns:
            QuerySet: استعلام محسن للمنتجات المجمعة
        """
        from product.models import Product, BundleComponent
        
        # إعداد prefetch للمكونات مع بياناتها
        components_prefetch = Prefetch(
            'components',
            queryset=BundleComponent.objects.select_related(
                'component_product'
            ).order_by('id'),
            to_attr='prefetched_components'
        )
        
        # بناء الاستعلام الأساسي
        queryset = Product.objects.filter(is_bundle=True)
        
        if bundle_ids:
            queryset = queryset.filter(id__in=bundle_ids)
        
        # تطبيق التحسينات
        return queryset.select_related(
            # يمكن إضافة علاقات أخرى هنا حسب الحاجة
        ).prefetch_related(
            components_prefetch
        ).annotate(
            component_count=Count('components'),
        )
    
    @classmethod
    def get_bundle_with_stock_info(cls, bundle_id: int) -> Optional[models.Model]:
        """
        الحصول على منتج مجمع واحد مع معلومات المخزون المحسنة
        
        Args:
            bundle_id: معرف المنتج المجمع
            
        Returns:
            Product: المنتج المجمع مع البيانات المحسنة
        """
        from product.models import Product, BundleComponent
        
        try:
            # إعداد prefetch للمكونات مع معلومات المخزون
            components_with_stock = Prefetch(
                'components',
                queryset=BundleComponent.objects.select_related(
                    'component_product'
                ).order_by('id'),
                to_attr='components_with_stock'
            )
            
            return Product.objects.filter(
                id=bundle_id,
                is_bundle=True
            ).prefetch_related(
                components_with_stock
            ).annotate(
                component_count=Count('components')
            ).first()
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على المنتج المجمع {bundle_id}: {str(e)}")
            return None
    
    @classmethod
    def get_bundles_for_listing(cls, active_only: bool = True, limit: int = None) -> QuerySet:
        """
        الحصول على المنتجات المجمعة للعرض في القوائم
        
        Args:
            active_only: المنتجات النشطة فقط
            limit: حد أقصى للنتائج
            
        Returns:
            QuerySet: استعلام محسن لقائمة المنتجات المجمعة
        """
        from product.models import Product
        
        queryset = Product.objects.filter(is_bundle=True)
        
        if active_only:
            queryset = queryset.filter(is_active=True)
        
        # إضافة إحصائيات مفيدة للعرض
        queryset = queryset.annotate(
            component_count=Count('components'),
            active_component_count=Count(
                'components',
                filter=Q(components__component_product__is_active=True)
            )
        ).order_by('-created_at')
        
        if limit:
            queryset = queryset[:limit]
        
        return queryset
    
    @classmethod
    def get_components_by_bundle_ids(cls, bundle_ids: List[int]) -> Dict[int, List[Dict]]:
        """
        الحصول على مكونات متعددة منتجات مجمعة بشكل محسن
        
        Args:
            bundle_ids: قائمة معرفات المنتجات المجمعة
            
        Returns:
            Dict: قاموس يربط معرف المنتج المجمع بمكوناته
        """
        from product.models import BundleComponent
        
        try:
            # استعلام واحد للحصول على جميع المكونات
            components = BundleComponent.objects.filter(
                bundle_product_id__in=bundle_ids
            ).select_related(
                'bundle_product',
                'component_product'
            ).order_by('bundle_product_id', 'id')
            
            # تجميع النتائج حسب المنتج المجمع
            result = {}
            for component in components:
                bundle_id = component.bundle_product_id
                if bundle_id not in result:
                    result[bundle_id] = []
                
                result[bundle_id].append({
                    'id': component.id,
                    'component_product': component.component_product,
                    'required_quantity': component.required_quantity,
                    'component_name': component.component_product.name,
                    'component_stock': getattr(component.component_product, 'current_stock', 0),
                    'is_active': component.component_product.is_active
                })
            
            return result
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على مكونات المنتجات المجمعة: {str(e)}")
            return {}
    
    @classmethod
    def get_bundles_with_low_stock(cls, threshold: int = 5) -> QuerySet:
        """
        الحصول على المنتجات المجمعة ذات المخزون المنخفض
        
        Args:
            threshold: حد المخزون المنخفض
            
        Returns:
            QuerySet: المنتجات المجمعة ذات المخزون المنخفض
        """
        from product.models import Product
        
        # استعلام معقد لحساب المخزون المتاح للمنتجات المجمعة
        return Product.objects.filter(
            is_bundle=True,
            is_active=True
        ).annotate(
            min_component_ratio=models.Min(
                F('components__component_product__current_stock') / 
                F('components__required_quantity')
            )
        ).filter(
            min_component_ratio__lt=threshold
        ).select_related().prefetch_related(
            'components__component_product'
        ).order_by('min_component_ratio')
    
    @classmethod
    def get_popular_bundles(cls, days: int = 30, limit: int = 10) -> QuerySet:
        """
        الحصول على المنتجات المجمعة الأكثر شعبية
        
        Args:
            days: عدد الأيام للإحصائيات
            limit: عدد النتائج
            
        Returns:
            QuerySet: المنتجات المجمعة الأكثر شعبية
        """
        from product.models import Product
        from django.utils import timezone
        from datetime import timedelta
        
        # تاريخ البداية للإحصائيات
        start_date = timezone.now() - timedelta(days=days)
        
        # يمكن إضافة منطق لحساب الشعبية بناءً على المبيعات أو الطلبات
        # للآن، سنستخدم ترتيب بسيط
        return Product.objects.filter(
            is_bundle=True,
            is_active=True
        ).annotate(
            component_count=Count('components')
        ).order_by('-created_at')[:limit]
    
    @classmethod
    def bulk_update_bundle_stocks(cls, bundle_stock_data: List[Dict[str, Any]]) -> bool:
        """
        تحديث مخزون متعدد منتجات مجمعة بشكل مجمع
        
        Args:
            bundle_stock_data: قائمة بيانات المخزون [{bundle_id, stock}, ...]
            
        Returns:
            bool: نجح التحديث أم لا
        """
        try:
            from product.models import Product
            from django.db import transaction
            
            with transaction.atomic():
                # تحضير البيانات للتحديث المجمع
                bundle_ids = [item['bundle_id'] for item in bundle_stock_data]
                bundles = Product.objects.filter(
                    id__in=bundle_ids,
                    is_bundle=True
                )
                
                # إنشاء قاموس للبحث السريع
                stock_lookup = {
                    item['bundle_id']: item['stock'] 
                    for item in bundle_stock_data
                }
                
                # تحديث المخزون
                updated_bundles = []
                for bundle in bundles:
                    if bundle.id in stock_lookup:
                        # إذا كان هناك حقل calculated_stock
                        if hasattr(bundle, 'calculated_stock'):
                            bundle.calculated_stock = stock_lookup[bundle.id]
                            updated_bundles.append(bundle)
                
                # تحديث مجمع
                if updated_bundles:
                    Product.objects.bulk_update(
                        updated_bundles, 
                        ['calculated_stock'], 
                        batch_size=100
                    )
                
                return True
                
        except Exception as e:
            logger.error(f"خطأ في التحديث المجمع لمخزون المنتجات المجمعة: {str(e)}")
            return False
    
    @classmethod
    def get_bundle_sales_stats(cls, bundle_ids: List[int] = None, days: int = 30) -> Dict[str, Any]:
        """
        الحصول على إحصائيات مبيعات المنتجات المجمعة
        
        Args:
            bundle_ids: معرفات المنتجات المجمعة (اختياري)
            days: عدد الأيام للإحصائيات
            
        Returns:
            Dict: إحصائيات المبيعات
        """
        try:
            from django.utils import timezone
            from datetime import timedelta
            
            # تاريخ البداية
            start_date = timezone.now() - timedelta(days=days)
            
            # يمكن إضافة استعلامات حقيقية للمبيعات هنا
            # للآن، سنعيد إحصائيات أساسية
            
            stats = {
                'period_days': days,
                'start_date': start_date,
                'total_bundles': 0,
                'active_bundles': 0,
                'bundles_with_stock': 0,
                'avg_components_per_bundle': 0
            }
            
            from product.models import Product
            
            queryset = Product.objects.filter(is_bundle=True)
            if bundle_ids:
                queryset = queryset.filter(id__in=bundle_ids)
            
            stats['total_bundles'] = queryset.count()
            stats['active_bundles'] = queryset.filter(is_active=True).count()
            
            # حساب متوسط المكونات
            avg_components = queryset.annotate(
                component_count=Count('components')
            ).aggregate(
                avg_components=models.Avg('component_count')
            )
            
            stats['avg_components_per_bundle'] = avg_components['avg_components'] or 0
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات المبيعات: {str(e)}")
            return {}


class BundleIndexOptimizer:
    """
    محسن فهارس قاعدة البيانات للمنتجات المجمعة
    
    Requirements: 9.2
    """
    
    @classmethod
    def get_recommended_indexes(cls) -> List[Dict[str, Any]]:
        """
        الحصول على الفهارس المقترحة للمنتجات المجمعة
        
        Returns:
            List: قائمة الفهارس المقترحة
        """
        return [
            {
                'table': 'product_product',
                'columns': ['is_bundle', 'is_active'],
                'name': 'idx_product_bundle_active',
                'description': 'فهرس للمنتجات المجمعة النشطة'
            },
            {
                'table': 'product_bundlecomponent',
                'columns': ['bundle_product_id', 'component_product_id'],
                'name': 'idx_bundle_component_relation',
                'description': 'فهرس لعلاقة المنتج المجمع والمكون'
            },
            {
                'table': 'product_bundlecomponent',
                'columns': ['component_product_id'],
                'name': 'idx_bundle_component_product',
                'description': 'فهرس للبحث بالمكون'
            },
            {
                'table': 'product_product',
                'columns': ['is_bundle', 'created_at'],
                'name': 'idx_product_bundle_created',
                'description': 'فهرس للمنتجات المجمعة مرتبة بالتاريخ'
            }
        ]
    
    @classmethod
    def generate_index_sql(cls) -> List[str]:
        """
        إنشاء أوامر SQL لإنشاء الفهارس المقترحة
        
        Returns:
            List: قائمة أوامر SQL
        """
        indexes = cls.get_recommended_indexes()
        sql_commands = []
        
        for index in indexes:
            columns_str = ', '.join(index['columns'])
            sql = f"CREATE INDEX IF NOT EXISTS {index['name']} ON {index['table']} ({columns_str});"
            sql_commands.append(sql)
        
        return sql_commands