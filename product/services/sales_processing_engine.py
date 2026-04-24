# -*- coding: utf-8 -*-
"""
محرك معالجة مبيعات المنتجات المجمعة
Sales Processing Engine for Bundle Products

يتعامل مع معالجة مبيعات المنتجات المجمعة وخصم كميات المكونات
Requirements: 3.1, 3.2, 3.3, 3.5
"""

from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple, Union, Any

from ..exceptions import (
    BundleSystemError, BundleStockError, BundleSalesError,
    BundleValidationError, get_error_message
)
from .bundle_error_handler import BundleErrorHandler

logger = logging.getLogger('bundle_system')


class SalesProcessingEngine:
    """
    محرك معالجة مبيعات المنتجات المجمعة
    
    يتعامل مع:
    - التحقق من توفر المخزون قبل البيع
    - خصم كميات المكونات بشكل ذري (atomic)
    - تسجيل تفاصيل المعاملة
    - عكس المبيعات (refunds)
    
    Requirements: 3.1, 3.2, 3.3, 3.5
    """
    
    @staticmethod
    def process_bundle_sale(
        bundle_product, 
        quantity: int, 
        transaction_context: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        معالجة بيع منتج مجمع مع خصم كميات المكونات
        
        Args:
            bundle_product: المنتج المجمع (Product instance)
            quantity: الكمية المباعة
            transaction_context: سياق المعاملة (معلومات إضافية مثل المستخدم، رقم الفاتورة، إلخ)
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: 
                (نجح أم لا، سجل المعاملة، رسالة الخطأ)
                
        Requirements: 3.1, 3.4, 3.5
        """
        context = {
            'bundle_id': bundle_product.id if bundle_product else None,
            'quantity': quantity,
            'user_id': transaction_context.get('user_id') if isinstance(transaction_context, dict) else None,
            'operation': 'bundle_sale'
        }
        
        try:
            # التحقق من صحة المدخلات
            validation_result = SalesProcessingEngine._validate_sale_inputs(
                bundle_product, quantity, transaction_context
            )
            if not validation_result[0]:
                return False, None, validation_result[1]
            
            # التحقق من توفر المخزون
            availability_check = SalesProcessingEngine.validate_bundle_availability(
                bundle_product, quantity
            )
            if not availability_check[0]:
                return False, None, availability_check[1]
            
            # معالجة البيع داخل معاملة ذرية
            with transaction.atomic():
                # إنشاء سجل المعاملة
                transaction_record = SalesProcessingEngine._create_transaction_record(
                    bundle_product, quantity, transaction_context
                )
                context['transaction_id'] = transaction_record.get('transaction_id')
                
                try:
                    # خصم كميات المكونات
                    component_deductions = SalesProcessingEngine._deduct_component_quantities(
                        bundle_product, quantity, transaction_record
                    )
                    
                    # إنشاء المعاملة المالية للمنتج المجمع
                    financial_success, financial_record, financial_error = SalesProcessingEngine._create_bundle_financial_transaction(
                        bundle_product, quantity, transaction_context, component_deductions
                    )
                    
                    if not financial_success:
                        logger.warning(f"تحذير: فشل في إنشاء المعاملة المالية للمنتج المجمع: {financial_error}")
                        # يمكن المتابعة حتى لو فشلت المعاملة المالية، لكن نسجل التحذير
                    
                    # تحديث سجل المعاملة بتفاصيل المكونات والمعاملة المالية
                    transaction_record['component_deductions'] = component_deductions
                    transaction_record['financial_record'] = financial_record
                    transaction_record['status'] = 'completed'
                    transaction_record['completed_at'] = timezone.now()
                    
                    
                    return True, transaction_record, None
                    
                except Exception as inner_error:
                    # محاولة التراجع عن المعاملة
                    logger.error(f"خطأ أثناء معالجة البيع، محاولة التراجع: {str(inner_error)}")
                    return False, None, f"فشل في معالجة بيع المنتج المجمع: {str(inner_error)}"
                
        except BundleSystemError as e:
            # إرجاع رسالة الخطأ بدلاً من رفع الاستثناء
            return False, None, str(e)
        except Exception as e:
            # تحويل الأخطاء العامة إلى رسائل خطأ
            error_details = BundleErrorHandler.handle_error(e, context, 'rollback_transaction')
            return False, None, f"خطأ غير متوقع في معالجة بيع المنتج المجمع: {str(e)}"
    
    @staticmethod
    def validate_bundle_availability(bundle_product, requested_quantity: int) -> Tuple[bool, str]:
        """
        التحقق من توفر كمية معينة من منتج مجمع للبيع
        
        Args:
            bundle_product: المنتج المجمع
            requested_quantity: الكمية المطلوبة
            
        Returns:
            Tuple[bool, str]: (متوفر أم لا، رسالة توضيحية)
            
        Requirements: 3.2, 3.3
        """
        try:
            # التحقق من أن المنتج مجمع ونشط
            if not bundle_product.is_bundle:
                return False, _("المنتج المحدد ليس منتجاً مجمعاً")
            
            if not bundle_product.is_active:
                return False, _("المنتج المجمع غير نشط")
            
            if requested_quantity <= 0:
                return False, _("الكمية المطلوبة يجب أن تكون أكبر من صفر")
            
            # الحصول على مكونات المنتج المجمع
            components = bundle_product.components.select_related('component_product').all()
            
            if not components.exists():
                return False, _("المنتج المجمع لا يحتوي على مكونات")
            
            # التحقق من توفر كل مكون
            insufficient_components = []
            
            for component in components:
                component_product = component.component_product
                required_total = component.required_quantity * requested_quantity
                available_stock = component_product.current_stock
                
                # التحقق من أن المكون نشط
                if not component_product.is_active:
                    return False, _("المكون {} غير نشط").format(component_product.name)
                
                # التحقق من توفر المخزون
                if available_stock < required_total:
                    shortage = required_total - available_stock
                    insufficient_components.append({
                        'name': component_product.name,
                        'sku': component_product.sku,
                        'available': available_stock,
                        'required': required_total,
                        'shortage': shortage
                    })
            
            # إذا كان هناك نقص في أي مكون
            if insufficient_components:
                component_details = []
                for comp in insufficient_components:
                    component_details.append(
                        f"{comp['name']} (متوفر: {comp['available']}, مطلوب: {comp['required']}, نقص: {comp['shortage']})"
                    )
                
                message = _("مخزون غير كافي في المكونات التالية: {}").format(
                    '; '.join(component_details)
                )
                return False, message
            
            return True, _("الكمية متوفرة للبيع")
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من توفر المنتج المجمع {bundle_product.name}: {e}")
            return False, _("خطأ في التحقق من التوفر")
    
    @staticmethod
    def reverse_bundle_sale(transaction_record: Dict) -> Tuple[bool, Optional[str]]:
        """
        عكس بيع منتج مجمع (إرجاع كميات المكونات)
        
        Args:
            transaction_record: سجل المعاملة الأصلية
            
        Returns:
            Tuple[bool, Optional[str]]: (نجح أم لا، رسالة الخطأ)
            
        Requirements: 3.6
        """
        try:
            # التحقق من صحة سجل المعاملة
            if not transaction_record or transaction_record.get('status') != 'completed':
                return False, _("سجل المعاملة غير صحيح أو غير مكتمل")
            
            if transaction_record.get('reversed', False):
                return False, _("المعاملة تم عكسها مسبقاً")
            
            bundle_product_id = transaction_record.get('bundle_product_id')
            if not bundle_product_id:
                return False, _("معرف المنتج المجمع غير موجود في سجل المعاملة")
            
            # الحصول على المنتج المجمع
            from ..models import Product
            try:
                bundle_product = Product.objects.get(id=bundle_product_id, is_bundle=True)
            except Product.DoesNotExist:
                return False, _("المنتج المجمع غير موجود")
            
            # عكس المعاملة داخل معاملة ذرية
            with transaction.atomic():
                component_deductions = transaction_record.get('component_deductions', [])
                
                if not component_deductions:
                    return False, _("تفاصيل خصم المكونات غير موجودة في سجل المعاملة")
                
                # إرجاع كميات المكونات
                restored_components = []
                
                for deduction in component_deductions:
                    component_id = deduction.get('component_id')
                    deducted_quantity = deduction.get('deducted_quantity', 0)
                    
                    if component_id and deducted_quantity > 0:
                        # إنشاء حركة مخزون لإرجاع الكمية
                        SalesProcessingEngine._create_stock_movement(
                            product_id=component_id,
                            quantity=deducted_quantity,
                            movement_type='return_in',
                            reference_number=transaction_record.get('transaction_id'),
                            notes=f"إرجاع مكون من عكس بيع المنتج المجمع {bundle_product.name}",
                            created_by_id=transaction_record.get('created_by_id')
                        )
                        
                        restored_components.append({
                            'component_id': component_id,
                            'restored_quantity': deducted_quantity
                        })
                
                # عكس المعاملة المالية إذا كانت موجودة
                financial_reversal_success = True
                financial_reversal_error = None
                
                financial_record = transaction_record.get('financial_record')
                if financial_record:
                    financial_reversal_success, financial_reversal_error = SalesProcessingEngine._reverse_bundle_financial_transaction(
                        financial_record
                    )
                    
                    if not financial_reversal_success:
                        logger.warning(f"فشل في عكس المعاملة المالية: {financial_reversal_error}")
                
                # تحديث سجل المعاملة
                transaction_record['reversed'] = True
                transaction_record['reversed_at'] = timezone.now()
                transaction_record['restored_components'] = restored_components
                transaction_record['financial_reversal_success'] = financial_reversal_success
                transaction_record['financial_reversal_error'] = financial_reversal_error
                
                
                return True, None
                
        except Exception as e:
            error_msg = f"خطأ في عكس بيع المنتج المجمع: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def _validate_sale_inputs(
        bundle_product, 
        quantity: int, 
        transaction_context: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        التحقق من صحة مدخلات البيع
        
        Args:
            bundle_product: المنتج المجمع
            quantity: الكمية
            transaction_context: سياق المعاملة
            
        Returns:
            Tuple[bool, Optional[str]]: (صحيح أم لا، رسالة الخطأ)
        """
        if bundle_product is None:
            return False, _("المنتج المجمع غير محدد")
        
        if not hasattr(bundle_product, 'is_bundle') or not bundle_product.is_bundle:
            return False, _("المنتج المحدد ليس منتجاً مجمعاً")
        
        if quantity <= 0:
            return False, _("الكمية يجب أن تكون أكبر من صفر")
        
        if not isinstance(transaction_context, dict):
            return False, _("سياق المعاملة يجب أن يكون قاموس")
        
        # التحقق من وجود المعلومات المطلوبة في سياق المعاملة
        required_fields = ['created_by_id']
        for field in required_fields:
            if field not in transaction_context:
                return False, _("معلومة مطلوبة مفقودة في سياق المعاملة: {}").format(field)
        
        return True, None
    
    @staticmethod
    def _create_transaction_record(
        bundle_product, 
        quantity: int, 
        transaction_context: Dict
    ) -> Dict:
        """
        إنشاء سجل المعاملة
        
        Args:
            bundle_product: المنتج المجمع
            quantity: الكمية المباعة
            transaction_context: سياق المعاملة
            
        Returns:
            Dict: سجل المعاملة
        """
        from django.utils.crypto import get_random_string
        
        transaction_id = f"BUNDLE_{timezone.now().strftime('%Y%m%d_%H%M%S')}_{get_random_string(6)}"
        
        return {
            'transaction_id': transaction_id,
            'transaction_type': 'bundle_sale',
            'bundle_product_id': bundle_product.id,
            'bundle_product_name': bundle_product.name,
            'bundle_product_sku': bundle_product.sku,
            'quantity_sold': quantity,
            'unit_price': bundle_product.selling_price,
            'total_amount': bundle_product.selling_price * quantity,
            'status': 'processing',
            'created_at': timezone.now(),
            'created_by_id': transaction_context.get('created_by_id'),
            'sale_reference': transaction_context.get('sale_reference'),
            'customer_id': transaction_context.get('customer_id'),
            'notes': transaction_context.get('notes', ''),
            'reversed': False
        }
    
    @staticmethod
    def _deduct_component_quantities(
        bundle_product, 
        quantity: int, 
        transaction_record: Dict,
        selected_components: Dict = None
    ) -> List[Dict]:
        """
        خصم كميات المكونات من المخزون
        يدعم خصم البدائل المختارة بدلاً من المكونات الأساسية
        
        Args:
            bundle_product: المنتج المجمع
            quantity: الكمية المباعة
            transaction_record: سجل المعاملة
            selected_components: dict mapping component_id -> selected_product_id (اختياري)
            
        Returns:
            List[Dict]: قائمة بتفاصيل خصم المكونات
        """
        from product.models import Product
        
        component_deductions = []
        components = bundle_product.components.select_related('component_product').all()
        
        for component in components:
            # تحديد المنتج الذي سيتم الخصم منه
            if selected_components and component.id in selected_components:
                # استخدام المنتج المختار (قد يكون بديل)
                selected_product_id = selected_components[component.id]
                try:
                    deduction_product = Product.objects.get(id=selected_product_id)
                except Product.DoesNotExist:
                    # في حالة عدم وجود المنتج، استخدم المكون الأساسي
                    deduction_product = component.component_product
                    logger.warning(
                        f"المنتج المختار {selected_product_id} غير موجود، "
                        f"استخدام المكون الأساسي {component.component_product.name}"
                    )
            else:
                # استخدام المكون الأساسي
                deduction_product = component.component_product
            
            required_quantity = component.required_quantity
            total_deduction = required_quantity * quantity
            
            # إنشاء حركة مخزون للخصم
            SalesProcessingEngine._create_stock_movement(
                product_id=deduction_product.id,
                quantity=total_deduction,
                movement_type='out',
                reference_number=transaction_record['transaction_id'],
                notes=f"خصم مكون من بيع المنتج المجمع {bundle_product.name}",
                created_by_id=transaction_record['created_by_id']
            )
            
            component_deductions.append({
                'component_id': component.id,
                'component_name': component.component_product.name,
                'deducted_product_id': deduction_product.id,
                'deducted_product_name': deduction_product.name,
                'deducted_product_sku': deduction_product.sku,
                'is_alternative': deduction_product.id != component.component_product.id,
                'required_per_unit': required_quantity,
                'units_sold': quantity,
                'deducted_quantity': total_deduction,
                'deducted_at': timezone.now()
            })
            
            logger.debug(
                f"خصم {total_deduction} وحدة من {deduction_product.name} "
                f"لبيع {quantity} وحدة من المنتج المجمع {bundle_product.name}"
            )
        
        return component_deductions
    
    @staticmethod
    def _create_bundle_financial_transaction(
        bundle_product,
        quantity: int,
        transaction_context: Dict[str, Any],
        component_deductions: List[Dict]
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        إنشاء معاملة مالية لبيع المنتج المجمع
        
        Args:
            bundle_product: المنتج المجمع
            quantity: الكمية المباعة
            transaction_context: سياق المعاملة
            component_deductions: تفاصيل خصم المكونات
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: 
                (نجح أم لا، سجل المعاملة المالية، رسالة الخطأ)
        """
        try:
            from .bundle_financial_service import BundleFinancialService
            
            return BundleFinancialService.create_bundle_sale_transaction(
                bundle_product=bundle_product,
                quantity=quantity,
                transaction_context=transaction_context,
                component_deductions=component_deductions
            )
            
        except ImportError:
            logger.warning("خدمة المعاملات المالية للمنتجات المجمعة غير متاحة")
            return False, None, "خدمة المعاملات المالية غير متاحة"
        except Exception as e:
            logger.error(f"خطأ في إنشاء المعاملة المالية للمنتج المجمع: {e}")
            return False, None, str(e)

    @staticmethod
    def _create_stock_movement(
        product_id: int,
        quantity: int,
        movement_type: str,
        reference_number: str,
        notes: str,
        created_by_id: int
    ) -> None:
        """
        إنشاء حركة مخزون
        
        Args:
            product_id: معرف المنتج
            quantity: الكمية
            movement_type: نوع الحركة (out, return_in)
            reference_number: رقم المرجع
            notes: ملاحظات
            created_by_id: معرف المستخدم المنشئ
        """
        try:
            from ..models import StockMovement, Product, Warehouse, Stock
            from django.contrib.auth import get_user_model
            
            User = get_user_model()
            
            # الحصول على المنتج
            product = Product.objects.get(id=product_id)
            
            # الحصول على المخزن الافتراضي (أول مخزن نشط)
            warehouse = Warehouse.objects.filter(is_active=True).first()
            if not warehouse:
                raise ValidationError(_("لا يوجد مخزن نشط لإنشاء حركة المخزون"))
            
            # الحصول على المستخدم
            created_by = User.objects.get(id=created_by_id)
            
            # الحصول على المخزون الحالي قبل الحركة
            stock, _ = Stock.objects.get_or_create(
                product=product,
                warehouse=warehouse,
                defaults={'quantity': 0}
            )
            quantity_before = stock.quantity
            
            # حساب الكمية بعد الحركة
            if movement_type == 'out':
                quantity_after = max(0, quantity_before - quantity)
            elif movement_type == 'return_in':
                quantity_after = quantity_before + quantity
            else:
                quantity_after = quantity_before
            
            # إنشاء حركة المخزون
            stock_movement = StockMovement.objects.create(
                product=product,
                warehouse=warehouse,
                movement_type=movement_type,
                quantity=quantity,
                reference_number=reference_number,
                document_type='sale' if movement_type == 'out' else 'sale_return',
                notes=notes,
                created_by=created_by,
                quantity_before=quantity_before,
                quantity_after=quantity_after
            )
            
            # تحديث كمية المخزون
            stock.quantity = quantity_after
            stock.save(update_fields=['quantity'])
            
            logger.debug(f"تم إنشاء حركة مخزون: {stock_movement}")
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء حركة المخزون: {e}")
            raise
    
    @staticmethod
    def get_bundle_sale_summary(bundle_product, quantity: int) -> Dict:
        """
        الحصول على ملخص بيع المنتج المجمع قبل التنفيذ
        
        Args:
            bundle_product: المنتج المجمع
            quantity: الكمية المطلوبة
            
        Returns:
            Dict: ملخص البيع المتوقع
        """
        try:
            summary = {
                'bundle_info': {
                    'name': bundle_product.name,
                    'sku': bundle_product.sku,
                    'unit_price': float(bundle_product.selling_price),
                    'quantity': quantity,
                    'total_amount': float(bundle_product.selling_price * quantity)
                },
                'components_impact': [],
                'availability_check': None,
                'can_proceed': False
            }
            
            # التحقق من التوفر
            availability = SalesProcessingEngine.validate_bundle_availability(bundle_product, quantity)
            summary['availability_check'] = {
                'available': availability[0],
                'message': availability[1]
            }
            summary['can_proceed'] = availability[0]
            
            # تفاصيل تأثير المكونات
            components = bundle_product.components.select_related('component_product').all()
            
            for component in components:
                component_product = component.component_product
                required_total = component.required_quantity * quantity
                current_stock = component_product.current_stock
                remaining_after_sale = current_stock - required_total
                
                summary['components_impact'].append({
                    'component_name': component_product.name,
                    'component_sku': component_product.sku,
                    'required_per_unit': component.required_quantity,
                    'total_required': required_total,
                    'current_stock': current_stock,
                    'remaining_after_sale': max(0, remaining_after_sale),
                    'sufficient': current_stock >= required_total
                })
            
            return summary
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء ملخص بيع المنتج المجمع: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def _reverse_bundle_financial_transaction(
        financial_record: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        عكس معاملة مالية لبيع منتج مجمع
        
        Args:
            financial_record: سجل المعاملة المالية
            
        Returns:
            Tuple[bool, Optional[str]]: (نجح أم لا، رسالة الخطأ)
        """
        try:
            from .bundle_financial_service import BundleFinancialService
            
            return BundleFinancialService.reverse_bundle_sale_transaction(financial_record)
            
        except ImportError:
            logger.warning("خدمة المعاملات المالية للمنتجات المجمعة غير متاحة")
            return False, "خدمة المعاملات المالية غير متاحة"
        except Exception as e:
            logger.error(f"خطأ في عكس المعاملة المالية للمنتج المجمع: {e}")
            return False, str(e)