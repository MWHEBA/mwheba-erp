# -*- coding: utf-8 -*-
"""
خدمة تخزين مؤقت للمنتجات المجمعة
Bundle Cache Service

يوفر تخزين مؤقت ذكي لحسابات المخزون والبيانات المتكررة
Requirements: 9.4
"""

from django.core.cache import cache
from django.conf import settings
from typing import Dict, List, Optional, Any, Union
import logging
import hashlib
import json
from datetime import datetime, timedelta

logger = logging.getLogger('bundle_system')


class BundleCacheService:
    """
    خدمة التخزين المؤقت للمنتجات المجمعة
    
    يوفر:
    - تخزين مؤقت لحسابات المخزون
    - إبطال ذكي للتخزين المؤقت
    - تدفئة التخزين المؤقت للمنتجات الشائعة
    - إحصائيات استخدام التخزين المؤقت
    
    Requirements: 9.4
    """
    
    # مفاتيح التخزين المؤقت
    CACHE_PREFIXES = {
        'bundle_stock': 'bundle_stock',
        'bundle_components': 'bundle_components',
        'bundle_availability': 'bundle_availability',
        'bundle_breakdown': 'bundle_breakdown',
        'popular_bundles': 'popular_bundles'
    }
    
    # أوقات انتهاء الصلاحية (بالثواني)
    CACHE_TIMEOUTS = {
        'bundle_stock': 300,        # 5 دقائق
        'bundle_components': 600,   # 10 دقائق
        'bundle_availability': 180, # 3 دقائق
        'bundle_breakdown': 300,    # 5 دقائق
        'popular_bundles': 3600     # ساعة واحدة
    }
    
    @classmethod
    def get_bundle_stock(cls, bundle_id: int) -> Optional[int]:
        """الحصول على مخزون المنتج المجمع من التخزين المؤقت"""
        cache_key = cls._get_cache_key('bundle_stock', bundle_id)
        
        try:
            cached_stock = cache.get(cache_key)
            if cached_stock is not None:
                cls._record_cache_hit('bundle_stock')
                logger.debug(f"Cache hit for bundle stock {bundle_id}: {cached_stock}")
                return cached_stock
            
            cls._record_cache_miss('bundle_stock')
            return None
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على مخزون المنتج المجمع من التخزين المؤقت: {str(e)}")
            return None
    
    @classmethod
    def set_bundle_stock(cls, bundle_id: int, stock: int) -> bool:
        """حفظ مخزون المنتج المجمع في التخزين المؤقت"""
        cache_key = cls._get_cache_key('bundle_stock', bundle_id)
        timeout = cls.CACHE_TIMEOUTS['bundle_stock']
        
        try:
            cache.set(cache_key, stock, timeout)
            logger.debug(f"Cached bundle stock {bundle_id}: {stock}")
            return True
            
        except Exception as e:
            logger.error(f"خطأ في حفظ مخزون المنتج المجمع في التخزين المؤقت: {str(e)}")
            return False
    
    @classmethod
    def get_bundle_components(cls, bundle_id: int) -> Optional[List[Dict]]:
        """الحصول على مكونات المنتج المجمع من التخزين المؤقت"""
        cache_key = cls._get_cache_key('bundle_components', bundle_id)
        
        try:
            cached_components = cache.get(cache_key)
            if cached_components is not None:
                cls._record_cache_hit('bundle_components')
                return cached_components
            
            cls._record_cache_miss('bundle_components')
            return None
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على مكونات المنتج المجمع من التخزين المؤقت: {str(e)}")
            return None
    
    @classmethod
    def set_bundle_components(cls, bundle_id: int, components: List[Dict]) -> bool:
        """حفظ مكونات المنتج المجمع في التخزين المؤقت"""
        cache_key = cls._get_cache_key('bundle_components', bundle_id)
        timeout = cls.CACHE_TIMEOUTS['bundle_components']
        
        try:
            cache.set(cache_key, components, timeout)
            return True
            
        except Exception as e:
            logger.error(f"خطأ في حفظ مكونات المنتج المجمع في التخزين المؤقت: {str(e)}")
            return False
    
    @classmethod
    def get_bundle_availability(cls, bundle_id: int, quantity: int) -> Optional[Dict]:
        """الحصول على توفر المنتج المجمع من التخزين المؤقت"""
        cache_key = cls._get_cache_key('bundle_availability', bundle_id, quantity)
        
        try:
            cached_availability = cache.get(cache_key)
            if cached_availability is not None:
                cls._record_cache_hit('bundle_availability')
                return cached_availability
            
            cls._record_cache_miss('bundle_availability')
            return None
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على توفر المنتج المجمع من التخزين المؤقت: {str(e)}")
            return None
    
    @classmethod
    def set_bundle_availability(cls, bundle_id: int, quantity: int, availability: Dict) -> bool:
        """حفظ توفر المنتج المجمع في التخزين المؤقت"""
        cache_key = cls._get_cache_key('bundle_availability', bundle_id, quantity)
        timeout = cls.CACHE_TIMEOUTS['bundle_availability']
        
        try:
            cache.set(cache_key, availability, timeout)
            return True
            
        except Exception as e:
            logger.error(f"خطأ في حفظ توفر المنتج المجمع في التخزين المؤقت: {str(e)}")
            return False
    
    @classmethod
    def invalidate_bundle_cache(cls, bundle_id: int) -> bool:
        """إبطال جميع التخزين المؤقت المتعلق بمنتج مجمع"""
        try:
            # إبطال مخزون المنتج المجمع
            stock_key = cls._get_cache_key('bundle_stock', bundle_id)
            cache.delete(stock_key)
            
            # إبطال مكونات المنتج المجمع
            components_key = cls._get_cache_key('bundle_components', bundle_id)
            cache.delete(components_key)
            
            # إبطال تفصيل المنتج المجمع
            breakdown_key = cls._get_cache_key('bundle_breakdown', bundle_id)
            cache.delete(breakdown_key)
            
            # إبطال توفر المنتج المجمع (جميع الكميات)
            # نحتاج لحذف جميع مفاتيح التوفر المتعلقة بهذا المنتج
            cls._invalidate_availability_cache(bundle_id)
            
            return True
            
        except Exception as e:
            logger.error(f"خطأ في إبطال التخزين المؤقت للمنتج المجمع {bundle_id}: {str(e)}")
            return False
    
    @classmethod
    def invalidate_component_cache(cls, component_id: int) -> bool:
        """إبطال التخزين المؤقت للمنتجات المجمعة التي تحتوي على مكون معين"""
        try:
            from product.models import BundleComponent
            
            # العثور على جميع المنتجات المجمعة التي تحتوي على هذا المكون
            bundle_components = BundleComponent.objects.filter(
                component_product_id=component_id
            ).select_related('bundle_product')
            
            affected_bundles = []
            for bundle_component in bundle_components:
                bundle_id = bundle_component.bundle_product.id
                cls.invalidate_bundle_cache(bundle_id)
                affected_bundles.append(bundle_id)
            
            return True
            
        except Exception as e:
            logger.error(f"خطأ في إبطال التخزين المؤقت للمكون {component_id}: {str(e)}")
            return False
    
    @classmethod
    def warm_popular_bundles_cache(cls) -> bool:
        """تدفئة التخزين المؤقت للمنتجات المجمعة الشائعة"""
        try:
            from product.models import Product
            from .stock_calculation_engine import StockCalculationEngine
            
            # الحصول على المنتجات المجمعة النشطة
            popular_bundles = Product.objects.filter(
                is_bundle=True,
                is_active=True
            ).order_by('-id')[:20]  # أحدث 20 منتج مجمع
            
            warmed_count = 0
            for bundle in popular_bundles:
                try:
                    # حساب وحفظ المخزون
                    stock = StockCalculationEngine.calculate_bundle_stock(bundle)
                    cls.set_bundle_stock(bundle.id, stock)
                    
                    # حساب وحفظ تفصيل المخزون
                    breakdown = StockCalculationEngine.get_bundle_stock_breakdown(bundle)
                    cls.set_bundle_breakdown(bundle.id, breakdown)
                    
                    warmed_count += 1
                    
                except Exception as e:
                    logger.warning(f"فشل في تدفئة التخزين المؤقت للمنتج المجمع {bundle.id}: {str(e)}")
                    continue
            
            return True
            
        except Exception as e:
            logger.error(f"خطأ في تدفئة التخزين المؤقت: {str(e)}")
            return False
    
    @classmethod
    def get_bundle_breakdown(cls, bundle_id: int) -> Optional[Dict]:
        """الحصول على تفصيل مخزون المنتج المجمع من التخزين المؤقت"""
        cache_key = cls._get_cache_key('bundle_breakdown', bundle_id)
        
        try:
            cached_breakdown = cache.get(cache_key)
            if cached_breakdown is not None:
                cls._record_cache_hit('bundle_breakdown')
                return cached_breakdown
            
            cls._record_cache_miss('bundle_breakdown')
            return None
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على تفصيل المنتج المجمع من التخزين المؤقت: {str(e)}")
            return None
    
    @classmethod
    def set_bundle_breakdown(cls, bundle_id: int, breakdown: Dict) -> bool:
        """حفظ تفصيل مخزون المنتج المجمع في التخزين المؤقت"""
        cache_key = cls._get_cache_key('bundle_breakdown', bundle_id)
        timeout = cls.CACHE_TIMEOUTS['bundle_breakdown']
        
        try:
            cache.set(cache_key, breakdown, timeout)
            return True
            
        except Exception as e:
            logger.error(f"خطأ في حفظ تفصيل المنتج المجمع في التخزين المؤقت: {str(e)}")
            return False
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """الحصول على إحصائيات التخزين المؤقت"""
        try:
            stats = {}
            
            for cache_type in cls.CACHE_PREFIXES.keys():
                hits_key = f'cache_hits:{cache_type}'
                misses_key = f'cache_misses:{cache_type}'
                
                hits = cache.get(hits_key, 0)
                misses = cache.get(misses_key, 0)
                total = hits + misses
                
                hit_rate = (hits / total * 100) if total > 0 else 0
                
                stats[cache_type] = {
                    'hits': hits,
                    'misses': misses,
                    'total_requests': total,
                    'hit_rate': round(hit_rate, 2)
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على إحصائيات التخزين المؤقت: {str(e)}")
            return {}
    
    @classmethod
    def clear_all_bundle_cache(cls) -> bool:
        """مسح جميع التخزين المؤقت للمنتجات المجمعة"""
        try:
            # مسح جميع مفاتيح التخزين المؤقت
            for prefix in cls.CACHE_PREFIXES.values():
                cache.delete_many(cache.keys(f'{prefix}:*'))
            
            # مسح إحصائيات التخزين المؤقت
            for cache_type in cls.CACHE_PREFIXES.keys():
                cache.delete(f'cache_hits:{cache_type}')
                cache.delete(f'cache_misses:{cache_type}')
            
            return True
            
        except Exception as e:
            logger.error(f"خطأ في مسح التخزين المؤقت: {str(e)}")
            return False
    
    # الطرق المساعدة الخاصة
    
    @classmethod
    def _get_cache_key(cls, cache_type: str, *args) -> str:
        """إنشاء مفتاح التخزين المؤقت"""
        prefix = cls.CACHE_PREFIXES.get(cache_type, cache_type)
        
        if args:
            # تحويل المعاملات إلى string وإنشاء hash
            args_str = ':'.join(str(arg) for arg in args)
            args_hash = hashlib.md5(args_str.encode()).hexdigest()[:8]
            return f'{prefix}:{args_hash}'
        else:
            return f'{prefix}:default'
    
    @classmethod
    def _record_cache_hit(cls, cache_type: str) -> None:
        """تسجيل إصابة في التخزين المؤقت"""
        try:
            hits_key = f'cache_hits:{cache_type}'
            current_hits = cache.get(hits_key, 0)
            cache.set(hits_key, current_hits + 1, 86400)  # 24 ساعة
        except Exception:
            pass  # تجاهل أخطاء الإحصائيات
    
    @classmethod
    def _record_cache_miss(cls, cache_type: str) -> None:
        """تسجيل فقدان في التخزين المؤقت"""
        try:
            misses_key = f'cache_misses:{cache_type}'
            current_misses = cache.get(misses_key, 0)
            cache.set(misses_key, current_misses + 1, 86400)  # 24 ساعة
        except Exception:
            pass  # تجاهل أخطاء الإحصائيات
    
    @classmethod
    def _invalidate_availability_cache(cls, bundle_id: int) -> None:
        """إبطال جميع مفاتيح توفر المنتج المجمع"""
        try:
            # نظراً لأن مفاتيح التوفر تحتوي على الكمية، نحتاج لحذف جميع المفاتيح المتعلقة
            # هذا تبسيط - في التطبيق الحقيقي يمكن استخدام نمط أكثر تطوراً
            prefix = cls.CACHE_PREFIXES['bundle_availability']
            
            # محاولة حذف مفاتيح التوفر الشائعة (كميات 1-100)
            for quantity in range(1, 101):
                availability_key = cls._get_cache_key('bundle_availability', bundle_id, quantity)
                cache.delete(availability_key)
                
        except Exception as e:
            logger.warning(f"خطأ في إبطال مفاتيح التوفر للمنتج المجمع {bundle_id}: {str(e)}")


class BundleCacheWarmer:
    """
    أداة تدفئة التخزين المؤقت للمنتجات المجمعة
    
    Requirements: 9.4
    """
    
    @classmethod
    def warm_bundle_cache(cls, bundle_id: int) -> bool:
        """تدفئة التخزين المؤقت لمنتج مجمع واحد"""
        try:
            from product.models import Product
            from .stock_calculation_engine import StockCalculationEngine
            
            bundle = Product.objects.get(id=bundle_id, is_bundle=True)
            
            # حساب وحفظ المخزون
            stock = StockCalculationEngine.calculate_bundle_stock(bundle)
            BundleCacheService.set_bundle_stock(bundle_id, stock)
            
            # حساب وحفظ تفصيل المخزون
            breakdown = StockCalculationEngine.get_bundle_stock_breakdown(bundle)
            BundleCacheService.set_bundle_breakdown(bundle_id, breakdown)
            
            # حساب وحفظ التوفر للكميات الشائعة
            common_quantities = [1, 2, 3, 5, 10]
            for quantity in common_quantities:
                availability = StockCalculationEngine.validate_bundle_availability(bundle, quantity)
                availability_data = {
                    'available': availability[0],
                    'message': availability[1],
                    'calculated_at': datetime.now().isoformat()
                }
                BundleCacheService.set_bundle_availability(bundle_id, quantity, availability_data)
            
            return True
            
        except Exception as e:
            logger.error(f"خطأ في تدفئة التخزين المؤقت للمنتج المجمع {bundle_id}: {str(e)}")
            return False
    
    @classmethod
    def schedule_cache_warming(cls) -> bool:
        """جدولة تدفئة التخزين المؤقت"""
        try:
            # يمكن استخدام Celery أو أي نظام مهام آخر هنا
            # للآن، سنقوم بتدفئة المنتجات الشائعة مباشرة
            return BundleCacheService.warm_popular_bundles_cache()
            
        except Exception as e:
            logger.error(f"خطأ في جدولة تدفئة التخزين المؤقت: {str(e)}")
            return False