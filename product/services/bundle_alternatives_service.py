# -*- coding: utf-8 -*-
"""
Bundle Alternatives Service
خدمة إدارة البدائل للمنتجات المجمعة
"""
from decimal import Decimal
from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.conf import settings


class BundleAlternativesService:
    """
    خدمة إدارة البدائل للمنتجات المجمعة
    """
    
    @staticmethod
    def is_enabled():
        """التحقق من تفعيل النظام"""
        return settings.MIGRATION_FLAGS.get('BUNDLE_ALTERNATIVES_ENABLED', False)
    
    @staticmethod
    def get_bundle_with_alternatives(bundle_id):
        """
        الحصول على المنتج المجمع مع جميع البدائل المتاحة
        
        Args:
            bundle_id: معرف المنتج المجمع
            
        Returns:
            dict: بيانات المنتج المجمع مع المكونات والبدائل
        """
        from product.models import Product, BundleComponent, BundleComponentAlternative
        
        try:
            bundle = Product.objects.select_related('category', 'unit').get(
                id=bundle_id,
                is_bundle=True,
                is_active=True
            )
        except Product.DoesNotExist:
            raise ValidationError("المنتج المجمع غير موجود أو غير نشط")
        
        # جلب المكونات مع البدائل
        components = BundleComponent.objects.filter(
            bundle_product=bundle
        ).select_related(
            'component_product'
        ).prefetch_related(
            models.Prefetch(
                'alternatives',
                queryset=BundleComponentAlternative.objects.filter(
                    is_active=True
                ).select_related('alternative_product').order_by('display_order')
            )
        )
        
        result = {
            'id': bundle.id,
            'name': bundle.name,
            'sku': bundle.sku,
            'base_price': float(bundle.selling_price),
            'components': []
        }
        
        for component in components:
            component_data = {
                'id': component.id,
                'name': component.component_product.name,
                'required_quantity': component.required_quantity,
                'default_product': {
                    'id': component.component_product.id,
                    'name': component.component_product.name,
                    'sku': component.component_product.sku,
                    'price': float(component.component_product.selling_price),
                    'stock': component.component_product.current_stock
                },
                'alternatives': []
            }
            
            # إضافة البدائل (already prefetched)
            for alt in component.alternatives.all():
                alt_data = {
                    'id': alt.alternative_product.id,
                    'name': alt.alternative_product.name,
                    'sku': alt.alternative_product.sku,
                    'is_default': alt.is_default,
                    'price_adjustment': float(alt.price_adjustment),
                    'final_price': float(alt.final_price),
                    'stock': alt.alternative_product.current_stock,
                    'is_available': alt.is_available,
                    'display_order': alt.display_order
                }
                component_data['alternatives'].append(alt_data)
            
            result['components'].append(component_data)
        
        return result
    
    @staticmethod
    def get_component_alternatives(component_id):
        """
        الحصول على البدائل المتاحة لمكون معين
        
        Args:
            component_id: معرف المكون
            
        Returns:
            list: قائمة البدائل المتاحة
        """
        from product.models import BundleComponent, BundleComponentAlternative
        
        try:
            component = BundleComponent.objects.select_related(
                'component_product'
            ).get(id=component_id)
        except BundleComponent.DoesNotExist:
            raise ValidationError("المكون غير موجود")
        
        alternatives = BundleComponentAlternative.objects.filter(
            bundle_component=component,
            is_active=True
        ).select_related('alternative_product').order_by('display_order')
        
        result = []
        for alt in alternatives:
            result.append({
                'id': alt.id,
                'product_id': alt.alternative_product.id,
                'product_name': alt.alternative_product.name,
                'is_default': alt.is_default,
                'price_adjustment': float(alt.price_adjustment),
                'final_price': float(alt.final_price),
                'stock': alt.alternative_product.current_stock,
                'is_available': alt.is_available
            })
        
        return result
    
    @staticmethod
    def calculate_bundle_price_with_selections(bundle_id, selections):
        """
        حساب السعر النهائي بناءً على الاختيارات
        
        Args:
            bundle_id: معرف المنتج المجمع
            selections: dict mapping component_id -> selected_product_id
            
        Returns:
            dict: تفاصيل السعر
        """
        from product.models import Product, BundleComponent, BundleComponentAlternative
        
        try:
            bundle = Product.objects.get(id=bundle_id, is_bundle=True, is_active=True)
        except Product.DoesNotExist:
            raise ValidationError("المنتج المجمع غير موجود")
        
        base_price = bundle.selling_price
        total_adjustment = Decimal('0.00')
        details = []
        
        for component_id, selected_product_id in selections.items():
            try:
                component = BundleComponent.objects.select_related(
                    'component_product'
                ).get(id=component_id, bundle_product=bundle)
            except BundleComponent.DoesNotExist:
                raise ValidationError(f"المكون {component_id} غير موجود في المنتج المجمع")
            
            # إذا كان المنتج المختار هو المكون الأساسي
            if selected_product_id == component.component_product.id:
                details.append({
                    'component_id': component_id,
                    'component_name': component.component_product.name,
                    'selected_product_id': selected_product_id,
                    'selected_product_name': component.component_product.name,
                    'is_alternative': False,
                    'price_adjustment': 0.00
                })
                continue
            
            # البحث عن البديل
            try:
                alternative = BundleComponentAlternative.objects.select_related(
                    'alternative_product'
                ).get(
                    bundle_component=component,
                    alternative_product_id=selected_product_id,
                    is_active=True
                )
            except BundleComponentAlternative.DoesNotExist:
                raise ValidationError(
                    f"المنتج {selected_product_id} ليس بديلاً متاحاً للمكون {component_id}"
                )
            
            total_adjustment += alternative.price_adjustment
            details.append({
                'component_id': component_id,
                'component_name': component.component_product.name,
                'selected_product_id': selected_product_id,
                'selected_product_name': alternative.alternative_product.name,
                'is_alternative': True,
                'price_adjustment': float(alternative.price_adjustment)
            })
        
        final_price = base_price + total_adjustment
        
        return {
            'base_price': float(base_price),
            'total_adjustment': float(total_adjustment),
            'final_price': float(final_price),
            'details': details
        }
    
    @staticmethod
    def validate_component_selections(bundle_id, selections):
        """
        التحقق من صحة الاختيارات
        
        Args:
            bundle_id: معرف المنتج المجمع
            selections: dict mapping component_id -> selected_product_id
            
        Returns:
            tuple: (is_valid, error_message)
        """
        from product.models import Product, BundleComponent, BundleComponentAlternative
        
        try:
            bundle = Product.objects.get(id=bundle_id, is_bundle=True, is_active=True)
        except Product.DoesNotExist:
            return False, "المنتج المجمع غير موجود أو غير نشط"
        
        # الحصول على جميع المكونات المطلوبة
        required_components = BundleComponent.objects.filter(
            bundle_product=bundle
        ).values_list('id', flat=True)
        
        # التحقق من اختيار جميع المكونات
        selected_components = set(int(k) for k in selections.keys())
        required_components_set = set(required_components)
        
        if selected_components != required_components_set:
            missing = required_components_set - selected_components
            if missing:
                return False, f"يجب اختيار جميع المكونات. المكونات المفقودة: {missing}"
            extra = selected_components - required_components_set
            if extra:
                return False, f"مكونات غير صحيحة: {extra}"
        
        # التحقق من صحة كل اختيار
        for component_id, selected_product_id in selections.items():
            try:
                component = BundleComponent.objects.select_related(
                    'component_product'
                ).get(id=component_id, bundle_product=bundle)
            except BundleComponent.DoesNotExist:
                return False, f"المكون {component_id} غير موجود"
            
            # إذا كان المنتج المختار هو المكون الأساسي
            if selected_product_id == component.component_product.id:
                # التحقق من المخزون
                if component.component_product.current_stock < component.required_quantity:
                    return False, f"المخزون غير كافي للمنتج {component.component_product.name}"
                continue
            
            # التحقق من أن المنتج المختار هو بديل متاح
            alternative = BundleComponentAlternative.objects.filter(
                bundle_component=component,
                alternative_product_id=selected_product_id,
                is_active=True
            ).select_related('alternative_product').first()
            
            if not alternative:
                return False, f"المنتج {selected_product_id} ليس بديلاً متاحاً للمكون {component_id}"
            
            # التحقق من المخزون
            if alternative.alternative_product.current_stock < component.required_quantity:
                return False, f"المخزون غير كافي للمنتج {alternative.alternative_product.name}"
        
        return True, "الاختيارات صحيحة"
    
    @staticmethod
    def get_default_selections(bundle_id):
        """
        الحصول على الاختيارات الافتراضية
        
        Args:
            bundle_id: معرف المنتج المجمع
            
        Returns:
            dict: mapping component_id -> selected_product_id
        """
        from product.models import Product, BundleComponent, BundleComponentAlternative
        
        try:
            bundle = Product.objects.get(id=bundle_id, is_bundle=True, is_active=True)
        except Product.DoesNotExist:
            raise ValidationError("المنتج المجمع غير موجود")
        
        components = BundleComponent.objects.filter(
            bundle_product=bundle
        ).select_related('component_product')
        
        selections = {}
        
        for component in components:
            # البحث عن بديل افتراضي
            default_alternative = BundleComponentAlternative.objects.filter(
                bundle_component=component,
                is_default=True,
                is_active=True
            ).select_related('alternative_product').first()
            
            if default_alternative:
                selections[component.id] = default_alternative.alternative_product.id
            else:
                # استخدام المكون الأساسي
                selections[component.id] = component.component_product.id
        
        return selections
