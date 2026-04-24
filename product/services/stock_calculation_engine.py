# -*- coding: utf-8 -*-
"""
محرك حساب مخزون المنتجات المجمعة
Stock Calculation Engine for Bundle Products

يحسب المخزون المتاح للمنتجات المجمعة بناءً على توفر المكونات
Requirements: 2.2, 2.3, 2.4
"""

from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple, Union

from .bundle_cache_service import BundleCacheService

logger = logging.getLogger('bundle_system')


class StockCalculationEngine:
    """
    محرك حساب مخزون المنتجات المجمعة
    
    يحسب المخزون المتاح للمنتجات المجمعة باستخدام صيغة:
    MIN(component_stock ÷ required_quantity) لجميع المكونات
    
    Requirements: 2.2, 2.3, 2.4
    """
    
    @staticmethod
    def calculate_bundle_stock(bundle_product, use_cache: bool = True) -> int:
        """
        حساب المخزون المتاح لمنتج مجمع
        
        Args:
            bundle_product: المنتج المجمع (Product instance)
            use_cache: استخدام التخزين المؤقت (افتراضي: True)
            
        Returns:
            int: المخزون المتاح للمنتج المجمع
            
        Requirements: 2.2, 2.3, 2.4
        """
        try:
            # التحقق من صحة المدخل
            if bundle_product is None:
                logger.warning("تم تمرير منتج فارغ (None) لحساب المخزون")
                return 0
            
            # محاولة الحصول على المخزون من التخزين المؤقت أولاً
            if use_cache:
                cached_stock = BundleCacheService.get_bundle_stock(bundle_product.id)
                if cached_stock is not None:
                    return cached_stock
            
            # التحقق من أن المنتج هو منتج مجمع
            if not bundle_product.is_bundle:
                logger.warning(f"المنتج {bundle_product.name} ليس منتجاً مجمعاً")
                return 0
            
            # الحصول على جميع مكونات المنتج المجمع
            components = bundle_product.components.select_related('component_product').all()
            
            if not components.exists():
                logger.warning(f"المنتج المجمع {bundle_product.name} لا يحتوي على مكونات")
                return 0
            
            min_available_bundles = float('inf')
            
            for component in components:
                component_product = component.component_product
                required_quantity = component.required_quantity
                
                # التحقق من أن المنتج المكون نشط
                if not component_product.is_active:
                    return 0
                
                # الحصول على المخزون الحالي للمكون
                component_stock = component_product.current_stock
                
                # إذا كان أي مكون بدون مخزون، فالمنتج المجمع غير متاح
                if component_stock <= 0:
                    return 0
                
                # حساب عدد الوحدات المجمعة الممكنة من هذا المكون
                possible_bundles = component_stock // required_quantity
                
                # أخذ الحد الأدنى
                min_available_bundles = min(min_available_bundles, possible_bundles)
                
                logger.debug(
                    f"المكون: {component_product.name}, "
                    f"المخزون: {component_stock}, "
                    f"المطلوب: {required_quantity}, "
                    f"الوحدات الممكنة: {possible_bundles}"
                )
            
            # إذا لم نجد أي مكونات صالحة
            if min_available_bundles == float('inf'):
                return 0
            
            result = int(min_available_bundles)
            logger.debug(f"المخزون المحسوب للمنتج المجمع {bundle_product.name}: {result}")
            
            # حفظ النتيجة في التخزين المؤقت
            if use_cache:
                BundleCacheService.set_bundle_stock(bundle_product.id, result)
            
            return result
            
        except Exception as e:
            product_name = getattr(bundle_product, 'name', 'منتج غير معروف') if bundle_product else 'منتج فارغ'
            logger.error(f"خطأ في حساب مخزون المنتج المجمع {product_name}: {e}")
            return 0
    
    @staticmethod
    def recalculate_affected_bundles(component_product) -> List[Dict]:
        """
        إعادة حساب مخزون جميع المنتجات المجمعة التي تحتوي على مكون معين
        
        Args:
            component_product: المنتج المكون (Product instance)
            
        Returns:
            List[Dict]: قائمة بالمنتجات المجمعة المتأثرة ومخزونها الجديد
            
        Requirements: 2.1
        """
        try:
            from ..models import Product
            
            # البحث عن جميع المنتجات المجمعة التي تحتوي على هذا المكون
            affected_bundles = Product.objects.filter(
                is_bundle=True,
                is_active=True,
                components__component_product=component_product
            ).distinct()
            
            results = []
            
            for bundle in affected_bundles:
                old_stock = getattr(bundle, '_cached_bundle_stock', None)
                new_stock = StockCalculationEngine.calculate_bundle_stock(bundle)
                
                results.append({
                    'bundle_product': bundle,
                    'old_stock': old_stock,
                    'new_stock': new_stock,
                    'component_changed': component_product,
                    'recalculated_at': timezone.now()
                })
                
            
            return results
            
        except Exception as e:
            logger.error(f"خطأ في إعادة حساب المنتجات المجمعة المتأثرة بـ {component_product.name}: {e}")
            return []
    
    @classmethod
    def bulk_recalculate(cls, product_ids: List[int] = None) -> Dict[str, Union[int, List[Dict]]]:
        """
        إعادة حساب مخزون عدة منتجات مجمعة بكفاءة
        
        Args:
            product_ids: قائمة معرفات المنتجات المجمعة (اختياري، إذا لم تُحدد يتم حساب جميع المنتجات المجمعة)
            
        Returns:
            Dict: تقرير بنتائج إعادة الحساب
            
        Requirements: Performance optimization
        """
        try:
            from ..models import Product
            
            # تحديد المنتجات المجمعة المراد إعادة حساب مخزونها
            bundles_query = Product.objects.filter(is_bundle=True, is_active=True)
            
            if product_ids:
                bundles_query = bundles_query.filter(id__in=product_ids)
            
            # تحسين الاستعلام بتحميل المكونات مسبقاً
            bundles = bundles_query.prefetch_related(
                'components__component_product'
            ).all()
            
            results = []
            total_processed = 0
            errors = []
            
            with transaction.atomic():
                for bundle in bundles:
                    try:
                        old_stock = getattr(bundle, '_cached_bundle_stock', None)
                        new_stock = cls.calculate_bundle_stock(bundle)
                        
                        results.append({
                            'bundle_id': bundle.id,
                            'bundle_name': bundle.name,
                            'old_stock': old_stock,
                            'new_stock': new_stock,
                            'recalculated_at': timezone.now()
                        })
                        
                        total_processed += 1
                        
                    except Exception as e:
                        error_msg = f"خطأ في حساب مخزون {bundle.name}: {e}"
                        errors.append(error_msg)
                        logger.error(error_msg)
            
            
            return {
                'total_processed': total_processed,
                'results': results,
                'errors': errors,
                'success': len(errors) == 0
            }
            
        except Exception as e:
            logger.error(f"خطأ في إعادة الحساب الجماعي: {e}")
            return {
                'total_processed': 0,
                'results': [],
                'errors': [str(e)],
                'success': False
            }
    
    @staticmethod
    def validate_bundle_availability(bundle_product, requested_quantity: int) -> Tuple[bool, str]:
        """
        التحقق من توفر كمية معينة من منتج مجمع
        
        Args:
            bundle_product: المنتج المجمع
            requested_quantity: الكمية المطلوبة
            
        Returns:
            Tuple[bool, str]: (متوفر أم لا، رسالة توضيحية)
            
        Requirements: 3.2, 3.3
        """
        try:
            if not bundle_product.is_bundle:
                return False, _("المنتج المحدد ليس منتجاً مجمعاً")
            
            if requested_quantity <= 0:
                return False, _("الكمية المطلوبة يجب أن تكون أكبر من صفر")
            
            available_stock = StockCalculationEngine.calculate_bundle_stock(bundle_product)
            
            if available_stock >= requested_quantity:
                return True, _("الكمية متوفرة")
            
            # تحديد المكونات غير المتوفرة
            insufficient_components = []
            components = bundle_product.components.select_related('component_product').all()
            
            for component in components:
                component_stock = component.component_product.current_stock
                required_for_request = component.required_quantity * requested_quantity
                
                if component_stock < required_for_request:
                    shortage = required_for_request - component_stock
                    insufficient_components.append({
                        'name': component.component_product.name,
                        'available': component_stock,
                        'required': required_for_request,
                        'shortage': shortage
                    })
            
            if insufficient_components:
                component_names = [comp['name'] for comp in insufficient_components]
                message = _("مخزون غير كافي في المكونات: {}").format(', '.join(component_names))
            else:
                message = _("المخزون المتاح: {} وحدة").format(available_stock)
            
            return False, message
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من توفر المنتج المجمع {bundle_product.name}: {e}")
            return False, _("خطأ في التحقق من التوفر")
    
    @staticmethod
    def get_bundle_stock_breakdown(bundle_product) -> Dict:
        """
        الحصول على تفصيل مخزون المنتج المجمع ومكوناته
        
        Args:
            bundle_product: المنتج المجمع
            
        Returns:
            Dict: تفصيل المخزون والمكونات
        """
        try:
            if not bundle_product.is_bundle:
                return {'error': 'المنتج ليس منتجاً مجمعاً'}
            
            components_info = []
            min_bundles = float('inf')
            
            components = bundle_product.components.select_related('component_product').all()
            
            for component in components:
                component_product = component.component_product
                component_stock = component_product.current_stock
                required_quantity = component.required_quantity
                
                possible_bundles = component_stock // required_quantity if required_quantity > 0 else 0
                min_bundles = min(min_bundles, possible_bundles)
                
                components_info.append({
                    'component_name': component_product.name,
                    'component_sku': component_product.sku,
                    'current_stock': component_stock,
                    'required_quantity': required_quantity,
                    'possible_bundles': possible_bundles,
                    'is_active': component_product.is_active,
                    'is_limiting_factor': False  # سيتم تحديثه لاحقاً
                })
            
            # تحديد المكونات المحددة للمخزون
            final_stock = int(min_bundles) if min_bundles != float('inf') else 0
            
            for comp_info in components_info:
                if comp_info['possible_bundles'] == final_stock:
                    comp_info['is_limiting_factor'] = True
            
            return {
                'bundle_name': bundle_product.name,
                'bundle_sku': bundle_product.sku,
                'calculated_stock': final_stock,
                'components': components_info,
                'total_components': len(components_info),
                'calculated_at': timezone.now()
            }
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على تفصيل مخزون المنتج المجمع {bundle_product.name}: {e}")
            return {'error': str(e)}