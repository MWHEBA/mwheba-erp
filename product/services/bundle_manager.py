# -*- coding: utf-8 -*-
"""
مدير المنتجات المجمعة
Bundle Manager for Bundle Products

يتعامل مع إنشاء وتحديث المنتجات المجمعة مع التحقق من صحة البيانات
Requirements: 1.1, 8.2
"""

from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple, Union, Any, Set

logger = logging.getLogger(__name__)


class BundleManager:
    """
    مدير المنتجات المجمعة
    
    يتعامل مع:
    - إنشاء منتجات مجمعة جديدة مع مكوناتها
    - تحديث مكونات المنتجات المجمعة الموجودة
    - التحقق من التبعيات الدائرية (Circular Dependencies)
    - التحقق من سلامة بيانات المنتجات المجمعة
    
    Requirements: 1.1, 8.2
    """
    
    @staticmethod
    def create_bundle(
        product_data: Dict[str, Any], 
        components_data: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[Any], Optional[str]]:
        """
        إنشاء منتج مجمع جديد مع مكوناته
        
        Args:
            product_data: بيانات المنتج المجمع (name, description, price, etc.)
            components_data: قائمة بيانات المكونات [{'component_product_id': int, 'required_quantity': int}, ...]
            
        Returns:
            Tuple[bool, Optional[Product], Optional[str]]: 
                (نجح أم لا، المنتج المجمع المُنشأ، رسالة الخطأ)
                
        Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.4
        """
        try:
            # التحقق من صحة بيانات المنتج
            validation_result = BundleManager._validate_product_data(product_data)
            if not validation_result[0]:
                return False, None, validation_result[1]
            
            # التحقق من صحة بيانات المكونات
            components_validation = BundleManager._validate_components_data(components_data)
            if not components_validation[0]:
                return False, None, components_validation[1]
            
            # التحقق من عدم وجود تبعيات دائرية (للمنتجات الموجودة)
            circular_check = BundleManager._check_circular_dependencies(
                None, components_data
            )
            if not circular_check[0]:
                return False, None, circular_check[1]
            
            # إنشاء المنتج والمكونات داخل معاملة ذرية
            with transaction.atomic():
                # إنشاء المنتج المجمع
                bundle_product = BundleManager._create_bundle_product(product_data)
                
                # إنشاء مكونات المنتج المجمع
                components = BundleManager._create_bundle_components(
                    bundle_product, components_data
                )
                
                # التحقق من سلامة المنتج المجمع المُنشأ
                integrity_check = BundleManager.validate_bundle_integrity(bundle_product)
                if not integrity_check[0]:
                    raise ValidationError(integrity_check[1])
                
                
                return True, bundle_product, None
                
        except ValidationError as e:
            error_msg = f"خطأ في التحقق من صحة البيانات: {e}"
            logger.error(error_msg)
            return False, None, error_msg
        except Exception as e:
            error_msg = f"خطأ في إنشاء المنتج المجمع: {e}"
            logger.error(error_msg)
            return False, None, error_msg
    
    @staticmethod
    def update_bundle_components(
        bundle_product, 
        new_components: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[str]]:
        """
        تحديث مكونات منتج مجمع موجود
        
        Args:
            bundle_product: المنتج المجمع المراد تحديث مكوناته
            new_components: قائمة المكونات الجديدة [{'component_product_id': int, 'required_quantity': int}, ...]
            
        Returns:
            Tuple[bool, Optional[str]]: (نجح أم لا، رسالة الخطأ)
            
        Requirements: 1.6, 8.2
        """
        try:
            # التحقق من صحة المنتج المجمع
            if not bundle_product or not bundle_product.is_bundle:
                return False, _("المنتج المحدد ليس منتجاً مجمعاً")
            
            # التحقق من صحة بيانات المكونات الجديدة
            components_validation = BundleManager._validate_components_data(new_components)
            if not components_validation[0]:
                return False, components_validation[1]
            
            # التحقق من عدم وجود تبعيات دائرية مع المكونات الجديدة
            circular_check = BundleManager._check_circular_dependencies(
                bundle_product, new_components
            )
            if not circular_check[0]:
                return False, circular_check[1]
            
            # تحديث المكونات داخل معاملة ذرية
            with transaction.atomic():
                # حفظ المكونات القديمة للمقارنة
                old_components = list(bundle_product.components.all())
                
                # حذف جميع المكونات القديمة
                bundle_product.components.all().delete()
                
                # إنشاء المكونات الجديدة
                new_component_objects = BundleManager._create_bundle_components(
                    bundle_product, new_components
                )
                
                # التحقق من سلامة المنتج المجمع بعد التحديث
                integrity_check = BundleManager.validate_bundle_integrity(bundle_product)
                if not integrity_check[0]:
                    raise ValidationError(integrity_check[1])
                
                # إعادة حساب مخزون المنتج المجمع
                from .stock_calculation_engine import StockCalculationEngine
                StockCalculationEngine.recalculate_affected_bundles(bundle_product)
                
                
                return True, None
                
        except ValidationError as e:
            error_msg = f"خطأ في التحقق من صحة البيانات: {e}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"خطأ في تحديث مكونات المنتج المجمع {bundle_product.name}: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def validate_bundle_integrity(bundle_product) -> Tuple[bool, Optional[str]]:
        """
        التحقق من سلامة بيانات المنتج المجمع
        
        Args:
            bundle_product: المنتج المجمع المراد التحقق من سلامته
            
        Returns:
            Tuple[bool, Optional[str]]: (سليم أم لا، رسالة الخطأ)
            
        Requirements: 8.1, 8.3, 8.4
        """
        try:
            # التحقق من أن المنتج موجود ومجمع
            if not bundle_product:
                return False, _("المنتج المجمع غير موجود")
            
            if not bundle_product.is_bundle:
                return False, _("المنتج المحدد ليس منتجاً مجمعاً")
            
            # التحقق من وجود مكونات
            components = bundle_product.components.select_related('component_product').all()
            
            if not components.exists():
                return False, _("المنتج المجمع يجب أن يحتوي على مكون واحد على الأقل")
            
            # التحقق من صحة كل مكون
            for component in components:
                component_product = component.component_product
                
                # التحقق من وجود المنتج المكون
                if not component_product:
                    return False, _("أحد المكونات غير موجود")
                
                # التحقق من أن المنتج المكون ليس مجمعاً (تجنب التعقيد)
                # ملاحظة: يمكن السماح بالمنتجات المجمعة كمكونات في المستقبل
                if component_product.is_bundle:
                    return False, _("لا يمكن أن يكون المنتج المجمع مكوناً لمنتج مجمع آخر حالياً")
                
                # التحقق من أن الكمية المطلوبة صحيحة
                if component.required_quantity <= 0:
                    return False, _("الكمية المطلوبة للمكون {} يجب أن تكون أكبر من صفر").format(
                        component_product.name
                    )
                
                # التحقق من عدم تكرار المكون
                duplicate_count = components.filter(
                    component_product=component_product
                ).count()
                if duplicate_count > 1:
                    return False, _("المكون {} مكرر في المنتج المجمع").format(
                        component_product.name
                    )
            
            # التحقق من عدم وجود تبعيات دائرية
            circular_check = BundleManager._check_bundle_circular_dependencies(bundle_product)
            if not circular_check[0]:
                return False, circular_check[1]
            
            # التحقق من أن سعر المنتج المجمع موجب
            if bundle_product.selling_price <= 0:
                return False, _("سعر المنتج المجمع يجب أن يكون أكبر من صفر")
            
            return True, None
            
        except Exception as e:
            error_msg = f"خطأ في التحقق من سلامة المنتج المجمع: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def _validate_product_data(product_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        التحقق من صحة بيانات المنتج المجمع
        
        Args:
            product_data: بيانات المنتج
            
        Returns:
            Tuple[bool, Optional[str]]: (صحيح أم لا، رسالة الخطأ)
        """
        if not isinstance(product_data, dict):
            return False, _("بيانات المنتج يجب أن تكون قاموس")
        
        # التحقق من الحقول المطلوبة
        required_fields = ['name', 'selling_price', 'category_id', 'unit_id', 'sku', 'created_by_id']
        for field in required_fields:
            if field not in product_data or product_data[field] is None:
                return False, _("الحقل المطلوب {} مفقود").format(field)
        
        # التحقق من صحة الاسم
        name = product_data.get('name', '').strip()
        if not name or len(name) < 2:
            return False, _("اسم المنتج يجب أن يكون على الأقل حرفين")
        
        # التحقق من صحة السعر
        try:
            price = Decimal(str(product_data['selling_price']))
            if price <= 0:
                return False, _("سعر البيع يجب أن يكون أكبر من صفر")
        except (ValueError, TypeError):
            return False, _("سعر البيع غير صحيح")
        
        # التحقق من صحة كود المنتج
        sku = product_data.get('sku', '').strip()
        if not sku:
            return False, _("كود المنتج مطلوب")
        
        # التحقق من عدم تكرار كود المنتج
        from ..models import Product
        if Product.objects.filter(sku=sku).exists():
            return False, _("كود المنتج {} موجود مسبقاً").format(sku)
        
        return True, None
    
    @staticmethod
    def _validate_components_data(components_data: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """
        التحقق من صحة بيانات المكونات
        
        Args:
            components_data: قائمة بيانات المكونات
            
        Returns:
            Tuple[bool, Optional[str]]: (صحيح أم لا، رسالة الخطأ)
        """
        if not isinstance(components_data, list):
            return False, _("بيانات المكونات يجب أن تكون قائمة")
        
        if len(components_data) == 0:
            return False, _("المنتج المجمع يجب أن يحتوي على مكون واحد على الأقل")
        
        seen_component_ids = set()
        
        for i, component_data in enumerate(components_data):
            if not isinstance(component_data, dict):
                return False, _("بيانات المكون {} يجب أن تكون قاموس").format(i + 1)
            
            # التحقق من الحقول المطلوبة
            if 'component_product_id' not in component_data:
                return False, _("معرف المنتج المكون مفقود في المكون {}").format(i + 1)
            
            if 'required_quantity' not in component_data:
                return False, _("الكمية المطلوبة مفقودة في المكون {}").format(i + 1)
            
            # التحقق من صحة معرف المنتج المكون
            component_id = component_data['component_product_id']
            if not isinstance(component_id, int) or component_id <= 0:
                return False, _("معرف المنتج المكون غير صحيح في المكون {}").format(i + 1)
            
            # التحقق من عدم تكرار المكونات
            if component_id in seen_component_ids:
                return False, _("المنتج المكون {} مكرر في القائمة").format(component_id)
            seen_component_ids.add(component_id)
            
            # التحقق من صحة الكمية المطلوبة
            try:
                required_quantity = int(component_data['required_quantity'])
                if required_quantity <= 0:
                    return False, _("الكمية المطلوبة يجب أن تكون أكبر من صفر في المكون {}").format(i + 1)
            except (ValueError, TypeError):
                return False, _("الكمية المطلوبة غير صحيحة في المكون {}").format(i + 1)
            
            # التحقق من وجود المنتج المكون
            from ..models import Product
            try:
                component_product = Product.objects.get(id=component_id, is_active=True)
                
                # التحقق من أن المنتج المكون ليس مجمعاً (حالياً)
                if component_product.is_bundle:
                    return False, _("المنتج المكون {} لا يمكن أن يكون منتجاً مجمعاً").format(
                        component_product.name
                    )
                    
            except Product.DoesNotExist:
                return False, _("المنتج المكون {} غير موجود أو غير نشط").format(component_id)
        
        return True, None
    
    @staticmethod
    def _check_circular_dependencies(
        bundle_product, 
        components_data: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[str]]:
        """
        التحقق من عدم وجود تبعيات دائرية
        
        Args:
            bundle_product: المنتج المجمع (None للمنتجات الجديدة)
            components_data: قائمة بيانات المكونات
            
        Returns:
            Tuple[bool, Optional[str]]: (لا توجد تبعيات دائرية، رسالة الخطأ)
            
        Requirements: 8.2
        """
        try:
            # إذا كان المنتج جديد، لا توجد تبعيات دائرية ممكنة
            if bundle_product is None:
                return True, None
            
            bundle_id = bundle_product.id
            component_ids = [comp['component_product_id'] for comp in components_data]
            
            # التحقق من أن المنتج المجمع ليس مكوناً لنفسه
            if bundle_id in component_ids:
                return False, _("لا يمكن أن يكون المنتج مكوناً لنفسه")
            
            # التحقق من التبعيات الدائرية غير المباشرة
            # (حالياً نمنع المنتجات المجمعة كمكونات، لذا هذا التحقق احترازي للمستقبل)
            circular_path = BundleManager._find_circular_dependency_path(
                bundle_id, component_ids, set()
            )
            
            if circular_path:
                path_names = BundleManager._get_product_names_for_path(circular_path)
                return False, _("تبعية دائرية مكتشفة: {}").format(' → '.join(path_names))
            
            return True, None
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من التبعيات الدائرية: {e}")
            return False, _("خطأ في التحقق من التبعيات الدائرية")
    
    @staticmethod
    def _check_bundle_circular_dependencies(bundle_product) -> Tuple[bool, Optional[str]]:
        """
        التحقق من عدم وجود تبعيات دائرية في منتج مجمع موجود
        
        Args:
            bundle_product: المنتج المجمع
            
        Returns:
            Tuple[bool, Optional[str]]: (لا توجد تبعيات دائرية، رسالة الخطأ)
        """
        try:
            components = bundle_product.components.all()
            component_ids = [comp.component_product_id for comp in components]
            
            return BundleManager._check_circular_dependencies(bundle_product, [
                {'component_product_id': comp_id, 'required_quantity': 1} 
                for comp_id in component_ids
            ])
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من التبعيات الدائرية للمنتج المجمع: {e}")
            return False, _("خطأ في التحقق من التبعيات الدائرية")
    
    @staticmethod
    def _find_circular_dependency_path(
        bundle_id: int, 
        component_ids: List[int], 
        visited: Set[int]
    ) -> Optional[List[int]]:
        """
        البحث عن مسار التبعية الدائرية باستخدام DFS
        
        Args:
            bundle_id: معرف المنتج المجمع
            component_ids: قائمة معرفات المكونات
            visited: المنتجات المزارة (لتجنب الحلقات اللانهائية)
            
        Returns:
            Optional[List[int]]: مسار التبعية الدائرية إن وُجد
        """
        if bundle_id in visited:
            return [bundle_id]  # وُجدت تبعية دائرية
        
        visited.add(bundle_id)
        
        try:
            from ..models import Product
            
            # البحث في مكونات كل منتج مكون (إذا كان مجمعاً)
            for component_id in component_ids:
                try:
                    component_product = Product.objects.get(id=component_id)
                    
                    # إذا كان المكون منتجاً مجمعاً، تحقق من مكوناته
                    if component_product.is_bundle:
                        sub_component_ids = list(
                            component_product.components.values_list('component_product_id', flat=True)
                        )
                        
                        circular_path = BundleManager._find_circular_dependency_path(
                            component_id, sub_component_ids, visited.copy()
                        )
                        
                        if circular_path:
                            return [bundle_id] + circular_path
                            
                except Product.DoesNotExist:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"خطأ في البحث عن التبعيات الدائرية: {e}")
            return None
    
    @staticmethod
    def _get_product_names_for_path(product_ids: List[int]) -> List[str]:
        """
        الحصول على أسماء المنتجات لمسار معين
        
        Args:
            product_ids: قائمة معرفات المنتجات
            
        Returns:
            List[str]: قائمة أسماء المنتجات
        """
        try:
            from ..models import Product
            
            products = Product.objects.filter(id__in=product_ids).values('id', 'name')
            product_names_map = {p['id']: p['name'] for p in products}
            
            return [product_names_map.get(pid, f"منتج {pid}") for pid in product_ids]
            
        except Exception as e:
            logger.error(f"خطأ في الحصول على أسماء المنتجات: {e}")
            return [f"منتج {pid}" for pid in product_ids]
    
    @staticmethod
    def _create_bundle_product(product_data: Dict[str, Any]):
        """
        إنشاء المنتج المجمع
        
        Args:
            product_data: بيانات المنتج
            
        Returns:
            Product: المنتج المجمع المُنشأ
        """
        from ..models import Product, Category, Unit
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # الحصول على الكائنات المرتبطة
        category = Category.objects.get(id=product_data['category_id'])
        unit = Unit.objects.get(id=product_data['unit_id'])
        created_by = User.objects.get(id=product_data['created_by_id'])
        
        # إنشاء المنتج المجمع
        bundle_product = Product.objects.create(
            name=product_data['name'],
            description=product_data.get('description', ''),
            sku=product_data['sku'],
            barcode=product_data.get('barcode', ''),
            category=category,
            unit=unit,
            cost_price=product_data.get('cost_price', 0),
            selling_price=product_data['selling_price'],
            min_stock=product_data.get('min_stock', 0),
            is_active=product_data.get('is_active', True),
            is_featured=product_data.get('is_featured', False),
            tax_rate=product_data.get('tax_rate', 0),
            discount_rate=product_data.get('discount_rate', 0),
            created_by=created_by,
            is_bundle=True,  # هذا هو الأهم - تعيين المنتج كمجمع
            # نوع المنتج وخصائصه
            item_type=product_data.get('item_type', 'general'),
            suitable_for_grades=product_data.get('suitable_for_grades', ''),
            uniform_size=product_data.get('uniform_size', ''),
            uniform_gender=product_data.get('uniform_gender', ''),
            educational_subject=product_data.get('educational_subject', ''),
            is_child_safe=product_data.get('is_child_safe', True),
            quality_certificate=product_data.get('quality_certificate', ''),
        )
        
        return bundle_product
    
    @staticmethod
    def _create_bundle_components(bundle_product, components_data: List[Dict[str, Any]]) -> List:
        """
        إنشاء مكونات المنتج المجمع
        
        Args:
            bundle_product: المنتج المجمع
            components_data: قائمة بيانات المكونات
            
        Returns:
            List[BundleComponent]: قائمة مكونات المنتج المجمع المُنشأة
        """
        from ..models import BundleComponent, Product
        
        components = []
        
        for component_data in components_data:
            component_product = Product.objects.get(
                id=component_data['component_product_id']
            )
            
            bundle_component = BundleComponent.objects.create(
                bundle_product=bundle_product,
                component_product=component_product,
                required_quantity=component_data['required_quantity']
            )
            
            components.append(bundle_component)
        
        return components
    
    @staticmethod
    def check_bundle_usage_in_orders(bundle_product) -> Dict[str, Any]:
        """
        فحص استخدام المنتج المجمع في الطلبات والمبيعات الموجودة
        
        Args:
            bundle_product: المنتج المجمع المراد فحصه
            
        Returns:
            Dict[str, Any]: معلومات الاستخدام في الطلبات
            
        Requirements: 1.6, 1.7
        """
        try:
            usage_info = {
                'has_sales': False,
                'sales_count': 0,
                'total_sold_quantity': 0,
                'last_sale_date': None,
                'has_pending_orders': False,
                'pending_orders_count': 0,
                'can_modify_safely': True,
                'warning_message': None,
                'destructive_changes': []
            }
            
            # فحص المبيعات من sale.models
            try:
                from sale.models import SaleItem
                
                sale_items = SaleItem.objects.filter(product=bundle_product)
                
                if sale_items.exists():
                    usage_info['has_sales'] = True
                    usage_info['sales_count'] = sale_items.count()
                    usage_info['total_sold_quantity'] = sum(
                        float(item.quantity) for item in sale_items
                    )
                
            except ImportError:
                logger.info("نموذج المبيعات غير متاح")
            
            # تحديد إمكانية التعديل الآمن
            if usage_info['has_sales'] or usage_info['has_pending_orders']:
                usage_info['can_modify_safely'] = False
                
                if usage_info['has_pending_orders']:
                    usage_info['warning_message'] = (
                        f"تحذير: يوجد {usage_info['pending_orders_count']} طلب معلق "
                        f"لهذا المنتج المجمع. تعديل المكونات قد يؤثر على هذه الطلبات."
                    )
                    usage_info['destructive_changes'].append('pending_orders')
                
                if usage_info['has_sales']:
                    usage_info['warning_message'] = (
                        f"تحذير: تم بيع {usage_info['total_sold_quantity']} وحدة "
                        f"من هذا المنتج المجمع في {usage_info['sales_count']} عملية بيع. "
                        f"تعديل المكونات قد يؤثر على تتبع المخزون والتقارير."
                    )
                    usage_info['destructive_changes'].append('existing_sales')
            
            return usage_info
            
        except Exception as e:
            logger.error(f"خطأ في فحص استخدام المنتج المجمع في الطلبات: {e}")
            return {
                'has_sales': False,
                'sales_count': 0,
                'total_sold_quantity': 0,
                'last_sale_date': None,
                'has_pending_orders': False,
                'pending_orders_count': 0,
                'can_modify_safely': True,
                'warning_message': None,
                'destructive_changes': [],
                'error': str(e)
            }
    
    @staticmethod
    def analyze_component_changes(
        bundle_product, 
        new_components_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        تحليل التغييرات في مكونات المنتج المجمع
        
        Args:
            bundle_product: المنتج المجمع
            new_components_data: بيانات المكونات الجديدة
            
        Returns:
            Dict[str, Any]: تحليل التغييرات
            
        Requirements: 1.6, 1.7
        """
        try:
            # الحصول على المكونات الحالية
            current_components = {}
            for component in bundle_product.components.all():
                current_components[component.component_product_id] = {
                    'product_name': component.component_product.name,
                    'required_quantity': component.required_quantity
                }
            
            # تحليل المكونات الجديدة
            new_components = {}
            for comp_data in new_components_data:
                comp_id = comp_data['component_product_id']
                new_components[comp_id] = {
                    'required_quantity': comp_data['required_quantity']
                }
            
            # تحديد التغييرات
            changes = {
                'added_components': [],      # مكونات جديدة
                'removed_components': [],    # مكونات محذوفة
                'modified_components': [],   # مكونات معدلة الكمية
                'unchanged_components': [],  # مكونات بدون تغيير
                'has_changes': False,
                'is_destructive': False,
                'change_summary': []
            }
            
            # المكونات المضافة
            for comp_id in new_components:
                if comp_id not in current_components:
                    try:
                        from ..models import Product
                        product = Product.objects.get(id=comp_id)
                        changes['added_components'].append({
                            'product_id': comp_id,
                            'product_name': product.name,
                            'required_quantity': new_components[comp_id]['required_quantity']
                        })
                    except Product.DoesNotExist:
                        pass
            
            # المكونات المحذوفة
            for comp_id in current_components:
                if comp_id not in new_components:
                    changes['removed_components'].append({
                        'product_id': comp_id,
                        'product_name': current_components[comp_id]['product_name'],
                        'required_quantity': current_components[comp_id]['required_quantity']
                    })
            
            # المكونات المعدلة
            for comp_id in current_components:
                if comp_id in new_components:
                    current_qty = current_components[comp_id]['required_quantity']
                    new_qty = new_components[comp_id]['required_quantity']
                    
                    if current_qty != new_qty:
                        changes['modified_components'].append({
                            'product_id': comp_id,
                            'product_name': current_components[comp_id]['product_name'],
                            'old_quantity': current_qty,
                            'new_quantity': new_qty
                        })
                    else:
                        changes['unchanged_components'].append({
                            'product_id': comp_id,
                            'product_name': current_components[comp_id]['product_name'],
                            'required_quantity': current_qty
                        })
            
            # تحديد وجود تغييرات
            changes['has_changes'] = bool(
                changes['added_components'] or 
                changes['removed_components'] or 
                changes['modified_components']
            )
            
            # تحديد إذا كانت التغييرات مدمرة
            changes['is_destructive'] = bool(
                changes['removed_components'] or changes['modified_components']
            )
            
            # إنشاء ملخص التغييرات
            if changes['added_components']:
                changes['change_summary'].append(
                    f"إضافة {len(changes['added_components'])} مكون جديد"
                )
            
            if changes['removed_components']:
                changes['change_summary'].append(
                    f"حذف {len(changes['removed_components'])} مكون"
                )
            
            if changes['modified_components']:
                changes['change_summary'].append(
                    f"تعديل كمية {len(changes['modified_components'])} مكون"
                )
            
            return changes
            
        except Exception as e:
            logger.error(f"خطأ في تحليل تغييرات المكونات: {e}")
            return {
                'added_components': [],
                'removed_components': [],
                'modified_components': [],
                'unchanged_components': [],
                'has_changes': False,
                'is_destructive': False,
                'change_summary': [],
                'error': str(e)
            }

    @staticmethod
    def get_bundle_creation_summary(
        product_data: Dict[str, Any], 
        components_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        الحصول على ملخص إنشاء المنتج المجمع قبل التنفيذ
        
        Args:
            product_data: بيانات المنتج المجمع
            components_data: قائمة بيانات المكونات
            
        Returns:
            Dict[str, Any]: ملخص الإنشاء المتوقع
        """
        try:
            summary = {
                'product_info': {
                    'name': product_data.get('name', ''),
                    'sku': product_data.get('sku', ''),
                    'selling_price': product_data.get('selling_price', 0),
                    'is_valid': False
                },
                'components_info': [],
                'validation_results': {
                    'product_valid': False,
                    'components_valid': False,
                    'no_circular_dependencies': False,
                    'can_create': False
                },
                'estimated_stock': 0
            }
            
            # التحقق من صحة بيانات المنتج
            product_validation = BundleManager._validate_product_data(product_data)
            summary['validation_results']['product_valid'] = product_validation[0]
            summary['product_info']['is_valid'] = product_validation[0]
            
            if not product_validation[0]:
                summary['validation_results']['error_message'] = product_validation[1]
                return summary
            
            # التحقق من صحة بيانات المكونات
            components_validation = BundleManager._validate_components_data(components_data)
            summary['validation_results']['components_valid'] = components_validation[0]
            
            if not components_validation[0]:
                summary['validation_results']['error_message'] = components_validation[1]
                return summary
            
            # معلومات المكونات
            from ..models import Product
            min_possible_bundles = float('inf')
            
            for component_data in components_data:
                try:
                    component_product = Product.objects.get(
                        id=component_data['component_product_id']
                    )
                    required_quantity = component_data['required_quantity']
                    current_stock = component_product.current_stock
                    possible_bundles = current_stock // required_quantity if required_quantity > 0 else 0
                    
                    min_possible_bundles = min(min_possible_bundles, possible_bundles)
                    
                    summary['components_info'].append({
                        'component_name': component_product.name,
                        'component_sku': component_product.sku,
                        'required_quantity': required_quantity,
                        'current_stock': current_stock,
                        'possible_bundles': possible_bundles
                    })
                    
                except Product.DoesNotExist:
                    summary['components_info'].append({
                        'component_id': component_data['component_product_id'],
                        'error': 'المنتج غير موجود'
                    })
            
            # التحقق من التبعيات الدائرية
            circular_check = BundleManager._check_circular_dependencies(None, components_data)
            summary['validation_results']['no_circular_dependencies'] = circular_check[0]
            
            if not circular_check[0]:
                summary['validation_results']['error_message'] = circular_check[1]
                return summary
            
            # حساب المخزون المتوقع
            summary['estimated_stock'] = int(min_possible_bundles) if min_possible_bundles != float('inf') else 0
            
            # تحديد إمكانية الإنشاء
            summary['validation_results']['can_create'] = (
                summary['validation_results']['product_valid'] and
                summary['validation_results']['components_valid'] and
                summary['validation_results']['no_circular_dependencies']
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء ملخص إنشاء المنتج المجمع: {e}")
            return {
                'error': str(e),
                'validation_results': {'can_create': False}
            }