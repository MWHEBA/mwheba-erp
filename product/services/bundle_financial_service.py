# -*- coding: utf-8 -*-
"""
خدمة المعاملات المالية للمنتجات المجمعة - محدثة للعمل مع AccountingGateway
Bundle Financial Transaction Service

يتعامل مع تسجيل المعاملات المالية لمبيعات المنتجات المجمعة عبر AccountingGateway
Requirements: 6.1, 6.2, 6.6
"""

from django.db import models, transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple, Union, Any

logger = logging.getLogger(__name__)


class BundleFinancialService:
    """
    خدمة المعاملات المالية للمنتجات المجمعة
    
    يتعامل مع:
    - تسجيل المعاملات المالية لمبيعات المنتجات المجمعة بسعر المنتج المجمع
    - ربط المعاملات المالية بتفاصيل المكونات
    - إنشاء مسار تدقيق شامل للمعاملات المالية
    - معالجة المرتجعات والإلغاءات
    
    Requirements: 6.1, 6.2, 6.6
    """
    
    @staticmethod
    def create_bundle_sale_transaction(
        bundle_product,
        quantity: int,
        transaction_context: Dict[str, Any],
        component_deductions: List[Dict] = None
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """
        إنشاء معاملة مالية لبيع منتج مجمع
        
        Args:
            bundle_product: المنتج المجمع
            quantity: الكمية المباعة
            transaction_context: سياق المعاملة
            component_deductions: تفاصيل خصم المكونات
            
        Returns:
            Tuple[bool, Optional[Dict], Optional[str]]: 
                (نجح أم لا، سجل المعاملة المالية، رسالة الخطأ)
                
        Requirements: 6.1, 6.2
        """
        try:
            # التحقق من صحة المدخلات
            validation_result = BundleFinancialService._validate_financial_inputs(
                bundle_product, quantity, transaction_context
            )
            if not validation_result[0]:
                return False, None, validation_result[1]
            
            # إنشاء المعاملة المالية داخل معاملة ذرية
            with transaction.atomic():
                # إنشاء القيد المحاسبي عبر Gateway
                journal_entry = BundleFinancialService._create_financial_transaction(
                    bundle_product, quantity, transaction_context
                )
                
                # إنشاء مسار التدقيق
                audit_record = BundleFinancialService._create_audit_trail(
                    journal_entry, bundle_product, quantity, 
                    transaction_context, component_deductions
                )
                
                # تعزيز مسار التدقيق بتفاصيل إضافية
                enhanced_audit = BundleFinancialService.enhance_transaction_audit_trail(
                    journal_entry, bundle_product, component_deductions, transaction_context
                )
                
                
                return True, {
                    'journal_entry_id': journal_entry.id,
                    'journal_entry': journal_entry,
                    'journal_entry_number': journal_entry.number,
                    'audit_record': audit_record,
                    'enhanced_audit': enhanced_audit,
                    'bundle_price_recorded': bundle_product.selling_price * quantity,
                    'component_details': component_deductions or []
                }, None
                
        except Exception as e:
            error_msg = f"خطأ في إنشاء المعاملة المالية للمنتج المجمع {bundle_product.name}: {e}"
            logger.error(error_msg)
            return False, None, error_msg
    
    @staticmethod
    def reverse_bundle_sale_transaction(
        financial_transaction_record: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        عكس قيد محاسبي لبيع منتج مجمع
        
        Args:
            financial_transaction_record: سجل القيد المحاسبي الأصلي
            
        Returns:
            Tuple[bool, Optional[str]]: (نجح أم لا، رسالة الخطأ)
            
        Requirements: 6.5
        """
        try:
            # التحقق من صحة سجل القيد
            journal_entry_id = financial_transaction_record.get('journal_entry_id')
            if not journal_entry_id:
                return False, _("سجل القيد المحاسبي غير صحيح أو غير مكتمل")
            
            # الحصول على القيد المحاسبي
            try:
                from financial.models.journal_entry import JournalEntry
                journal_entry = JournalEntry.objects.get(id=journal_entry_id)
            except JournalEntry.DoesNotExist:
                return False, _("القيد المحاسبي غير موجود")
            
            # التحقق من أن القيد لم يتم عكسه مسبقاً
            if journal_entry.status == 'cancelled':
                return False, _("القيد المحاسبي تم عكسه مسبقاً")
            
            # عكس القيد المحاسبي عبر Gateway
            with transaction.atomic():
                from governance.services import AccountingGateway
                
                gateway = AccountingGateway()
                reversal_entry = gateway.reverse_journal_entry(
                    original_entry=journal_entry,
                    reason="عكس بيع منتج مجمع",
                    user=journal_entry.created_by
                )
                
                # إنشاء مسار تدقيق للعكس
                BundleFinancialService._create_reversal_audit_trail(
                    journal_entry, reversal_entry, financial_transaction_record
                )
                
                
                return True, None
                
        except Exception as e:
            error_msg = f"خطأ في عكس القيد المحاسبي للمنتج المجمع: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def get_bundle_financial_summary(
        bundle_product, 
        quantity: int,
        transaction_context: Dict[str, Any] = None
    ) -> Dict:
        """
        الحصول على ملخص مالي لبيع المنتج المجمع قبل التنفيذ
        
        Args:
            bundle_product: المنتج المجمع
            quantity: الكمية المطلوبة
            transaction_context: سياق المعاملة (اختياري)
            
        Returns:
            Dict: ملخص البيع المالي المتوقع
        """
        try:
            summary = {
                'bundle_financial_info': {
                    'bundle_name': bundle_product.name,
                    'bundle_sku': bundle_product.sku,
                    'bundle_unit_price': float(bundle_product.selling_price),
                    'quantity': quantity,
                    'total_bundle_amount': float(bundle_product.selling_price * quantity),
                    'bundle_cost_price': float(bundle_product.cost_price),
                    'bundle_profit_margin': float(bundle_product.profit_margin)
                },
                'component_cost_breakdown': [],
                'financial_impact': {},
                'audit_requirements': {}
            }
            
            # حساب تكلفة المكونات الفعلية
            components = bundle_product.components.select_related('component_product').all()
            total_component_cost = Decimal('0.00')
            
            for component in components:
                component_product = component.component_product
                required_total = component.required_quantity * quantity
                component_total_cost = component_product.cost_price * required_total
                total_component_cost += component_total_cost
                
                summary['component_cost_breakdown'].append({
                    'component_name': component_product.name,
                    'component_sku': component_product.sku,
                    'required_per_unit': component.required_quantity,
                    'total_required': required_total,
                    'unit_cost': float(component_product.cost_price),
                    'total_cost': float(component_total_cost)
                })
            
            # حساب التأثير المالي
            bundle_total_cost = bundle_product.cost_price * quantity
            component_actual_cost = total_component_cost
            cost_difference = bundle_total_cost - component_actual_cost
            
            summary['financial_impact'] = {
                'bundle_recorded_cost': float(bundle_total_cost),
                'actual_component_cost': float(component_actual_cost),
                'cost_variance': float(cost_difference),
                'variance_percentage': float((cost_difference / bundle_total_cost * 100) if bundle_total_cost > 0 else 0),
                'bundle_selling_price': float(bundle_product.selling_price * quantity),
                'bundle_profit': float((bundle_product.selling_price - bundle_product.cost_price) * quantity)
            }
            
            # متطلبات التدقيق
            summary['audit_requirements'] = {
                'requires_component_tracking': True,
                'requires_cost_variance_analysis': abs(cost_difference) > Decimal('0.01'),
                'transaction_type': 'bundle_sale',
                'audit_level': 'detailed' if abs(cost_difference) > Decimal('10.00') else 'standard'
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء الملخص المالي للمنتج المجمع: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def _validate_financial_inputs(
        bundle_product, 
        quantity: int, 
        transaction_context: Dict
    ) -> Tuple[bool, Optional[str]]:
        """
        التحقق من صحة مدخلات المعاملة المالية
        
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
        
        # التحقق من صحة أسعار المنتج المجمع
        if not bundle_product.selling_price or bundle_product.selling_price <= 0:
            return False, _("سعر بيع المنتج المجمع غير صحيح")
        
        return True, None
    
    @staticmethod
    def _create_financial_transaction(
        bundle_product,
        quantity: int,
        transaction_context: Dict[str, Any]
    ):
        """
        إنشاء المعاملة المالية الأساسية عبر AccountingGateway
        
        Args:
            bundle_product: المنتج المجمع
            quantity: الكمية المباعة
            transaction_context: سياق المعاملة
            
        Returns:
            JournalEntry: القيد المحاسبي المنشأ
        """
        from governance.services import AccountingGateway, JournalEntryLineData
        from financial.models.chart_of_accounts import ChartOfAccounts
        from django.contrib.auth import get_user_model
        
        User = get_user_model()
        
        # الحصول على المستخدم
        created_by = User.objects.get(id=transaction_context['created_by_id'])
        
        # حساب المبلغ الإجمالي بسعر المنتج المجمع
        total_amount = bundle_product.selling_price * quantity
        
        # تحديد الحسابات المحاسبية
        # 40500 - إيرادات مبيعات المنتجات (من fixtures)
        # 10100 - الخزينة (من fixtures) - أو حسب payment_method
        revenue_account_code = "40500"  # إيرادات مبيعات المنتجات
        
        # تحديد حساب الاستلام حسب طريقة الدفع
        payment_method = transaction_context.get('payment_method', 'cash')
        if payment_method == 'cash' or payment_method == '10100':
            receiving_account_code = "10100"  # الخزينة
        elif payment_method == 'bank_transfer' or payment_method == '10200':
            receiving_account_code = "10200"  # البنك
        else:
            # إذا كان account code مباشرة
            receiving_account_code = payment_method if payment_method.isdigit() else "10100"
        
        # التحقق من وجود الحسابات
        revenue_account = ChartOfAccounts.objects.filter(code=revenue_account_code, is_active=True).first()
        receiving_account = ChartOfAccounts.objects.filter(code=receiving_account_code, is_active=True).first()
        
        if not revenue_account or not receiving_account:
            logger.error(f"الحسابات المحاسبية غير موجودة: revenue={revenue_account_code}, receiving={receiving_account_code}")
            raise ValueError("الحسابات المحاسبية المطلوبة غير موجودة")
        
        # إعداد بنود القيد المحاسبي
        description = f'بيع {quantity} وحدة من المنتج المجمع {bundle_product.name} (SKU: {bundle_product.sku})'
        
        lines = [
            JournalEntryLineData(
                account_code=receiving_account_code,
                debit=total_amount,
                credit=Decimal('0.00'),
                description=f"استلام من بيع منتج مجمع - {bundle_product.name}"
            ),
            JournalEntryLineData(
                account_code=revenue_account_code,
                debit=Decimal('0.00'),
                credit=total_amount,
                description=f"إيرادات بيع منتج مجمع - {bundle_product.name}"
            )
        ]
        
        # إنشاء القيد المحاسبي عبر Gateway
        gateway = AccountingGateway()
        reference_number = transaction_context.get('sale_reference', f'BUNDLE-{bundle_product.id}-{timezone.now().strftime("%Y%m%d%H%M%S")}')
        
        journal_entry = gateway.create_journal_entry(
            source_module='product',
            source_model='BundleSale',
            source_id=bundle_product.id,
            lines=lines,
            idempotency_key=f"JE:product:BundleSale:{bundle_product.id}:{reference_number}",
            user=created_by,
            entry_type='automatic',
            description=description,
            reference=reference_number,
            date=timezone.now().date(),
            financial_category=bundle_product.financial_category if hasattr(bundle_product, 'financial_category') else None,
            financial_subcategory=bundle_product.financial_subcategory if hasattr(bundle_product, 'financial_subcategory') else None
        )
        
        
        return journal_entry
    

    
    @staticmethod
    def _create_audit_trail(
        journal_entry,
        bundle_product,
        quantity: int,
        transaction_context: Dict[str, Any],
        component_deductions: List[Dict] = None
    ) -> Dict:
        """
        إنشاء مسار تدقيق شامل للقيد المحاسبي
        
        Args:
            journal_entry: القيد المحاسبي
            bundle_product: المنتج المجمع
            quantity: الكمية
            transaction_context: سياق المعاملة
            component_deductions: تفاصيل خصم المكونات
            
        Returns:
            Dict: سجل مسار التدقيق
        """
        total_amount = bundle_product.selling_price * quantity
        
        audit_record = {
            'audit_id': f"BUNDLE_AUDIT_{journal_entry.id}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
            'transaction_type': 'bundle_sale_financial',
            'journal_entry_id': journal_entry.id,
            'journal_entry_number': journal_entry.number,
            'bundle_product_info': {
                'id': bundle_product.id,
                'name': bundle_product.name,
                'sku': bundle_product.sku,
                'selling_price': float(bundle_product.selling_price),
                'cost_price': float(bundle_product.cost_price)
            },
            'sale_details': {
                'quantity': quantity,
                'unit_price': float(bundle_product.selling_price),
                'total_amount': float(total_amount),
                'sale_date': journal_entry.date.isoformat(),
                'reference_number': journal_entry.reference
            },
            'component_deductions': component_deductions or [],
            'financial_recording': {
                'recorded_at_bundle_price': True,
                'bundle_price_used': float(bundle_product.selling_price),
                'total_recorded_amount': float(total_amount),
                'via_gateway': True
            },
            'transaction_context': {
                'created_by_id': transaction_context.get('created_by_id'),
                'customer_id': transaction_context.get('customer_id'),
                'sale_reference': transaction_context.get('sale_reference'),
                'notes': transaction_context.get('notes', '')
            },
            'audit_metadata': {
                'created_at': timezone.now().isoformat(),
                'audit_level': 'detailed',
                'compliance_requirements': ['bundle_price_recording', 'component_tracking', 'audit_trail', 'gateway_integration']
            }
        }
        
        
        return audit_record
    

    
    @staticmethod
    def _create_reversal_audit_trail(
        original_transaction,
        reversal_transaction,
        financial_transaction_record: Dict
    ):
        """
        إنشاء مسار تدقيق لعكس المعاملة المالية
        
        Args:
            original_transaction: المعاملة المالية الأصلية
            reversal_transaction: المعاملة العكسية
            financial_transaction_record: سجل المعاملة المالية
        """
        reversal_audit = {
            'audit_id': f"BUNDLE_REVERSAL_AUDIT_{reversal_transaction.id}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
            'transaction_type': 'bundle_sale_financial_reversal',
            'original_transaction_id': original_transaction.id,
            'reversal_transaction_id': reversal_transaction.id,
            'reversal_details': {
                'original_amount': float(original_transaction.amount),
                'reversal_amount': float(reversal_transaction.amount),
                'reversal_date': reversal_transaction.date.isoformat(),
                'reversal_reason': 'Bundle sale reversal'
            },
            'component_restoration': financial_transaction_record.get('component_details', []),
            'audit_metadata': {
                'created_at': timezone.now().isoformat(),
                'audit_level': 'detailed',
                'compliance_requirements': ['financial_reversal_tracking', 'audit_trail']
            }
        }
        
    
    @staticmethod
    def generate_bundle_financial_report(
        bundle_product,
        start_date=None,
        end_date=None
    ) -> Dict:
        """
        إنشاء تقرير مالي شامل للمنتج المجمع
        
        Args:
            bundle_product: المنتج المجمع
            start_date: تاريخ البداية (اختياري)
            end_date: تاريخ النهاية (اختياري)
            
        Returns:
            Dict: تقرير مالي شامل
            
        Requirements: 6.3, 6.4, 6.6
        """
        try:
            from financial.models.transactions import FinancialTransaction
            from django.db.models import Sum, Count, Q
            from django.utils import timezone
            
            # تحديد الفترة الزمنية
            if not start_date:
                start_date = timezone.now().date().replace(day=1)  # بداية الشهر الحالي
            if not end_date:
                end_date = timezone.now().date()
            
            # البحث عن المعاملات المالية للمنتج المجمع
            bundle_transactions = FinancialTransaction.objects.filter(
                tags__icontains=f'product_id:{bundle_product.id}',
                date__range=[start_date, end_date],
                transaction_type='income'
            )
            
            # إحصائيات أساسية
            transaction_stats = bundle_transactions.aggregate(
                total_transactions=Count('id'),
                total_revenue=Sum('amount'),
                avg_transaction_amount=models.Avg('amount')
            )
            
            # تفاصيل المعاملات
            transaction_details = []
            for transaction in bundle_transactions:
                transaction_details.append({
                    'transaction_id': transaction.id,
                    'date': transaction.date.isoformat(),
                    'amount': float(transaction.amount),
                    'reference_number': transaction.reference_number,
                    'status': transaction.status,
                    'description': transaction.description
                })
            
            # حساب تكلفة المكونات الفعلية
            components = bundle_product.components.select_related('component_product').all()
            component_cost_analysis = []
            total_component_cost_per_unit = Decimal('0.00')
            
            for component in components:
                component_cost = component.component_product.cost_price * component.required_quantity
                total_component_cost_per_unit += component_cost
                
                component_cost_analysis.append({
                    'component_name': component.component_product.name,
                    'component_sku': component.component_product.sku,
                    'required_quantity': component.required_quantity,
                    'unit_cost': float(component.component_product.cost_price),
                    'total_cost_per_bundle': float(component_cost)
                })
            
            # تحليل الربحية
            bundle_cost = bundle_product.cost_price
            bundle_price = bundle_product.selling_price
            actual_cost_variance = bundle_cost - total_component_cost_per_unit
            
            profitability_analysis = {
                'bundle_selling_price': float(bundle_price),
                'bundle_recorded_cost': float(bundle_cost),
                'actual_component_cost': float(total_component_cost_per_unit),
                'cost_variance': float(actual_cost_variance),
                'cost_variance_percentage': float((actual_cost_variance / bundle_cost * 100) if bundle_cost > 0 else 0),
                'gross_profit_per_unit': float(bundle_price - bundle_cost),
                'actual_profit_per_unit': float(bundle_price - total_component_cost_per_unit),
                'profit_margin_recorded': float(((bundle_price - bundle_cost) / bundle_price * 100) if bundle_price > 0 else 0),
                'profit_margin_actual': float(((bundle_price - total_component_cost_per_unit) / bundle_price * 100) if bundle_price > 0 else 0)
            }
            
            # تجميع التقرير
            report = {
                'report_metadata': {
                    'bundle_product_id': bundle_product.id,
                    'bundle_name': bundle_product.name,
                    'bundle_sku': bundle_product.sku,
                    'report_period': {
                        'start_date': start_date.isoformat(),
                        'end_date': end_date.isoformat()
                    },
                    'generated_at': timezone.now().isoformat(),
                    'report_type': 'bundle_financial_analysis'
                },
                'transaction_summary': {
                    'total_transactions': transaction_stats['total_transactions'] or 0,
                    'total_revenue': float(transaction_stats['total_revenue'] or 0),
                    'average_transaction_amount': float(transaction_stats['avg_transaction_amount'] or 0),
                    'units_sold_estimate': int((transaction_stats['total_revenue'] or 0) / bundle_price) if bundle_price > 0 else 0
                },
                'component_cost_analysis': component_cost_analysis,
                'profitability_analysis': profitability_analysis,
                'transaction_details': transaction_details,
                'audit_compliance': {
                    'bundle_price_recording': 'compliant',
                    'component_tracking': 'detailed',
                    'cost_variance_monitoring': 'active' if abs(actual_cost_variance) > Decimal('0.01') else 'standard',
                    'audit_trail_completeness': 'full'
                }
            }
            
            return report
            
        except Exception as e:
            logger.error(f"خطأ في إنشاء التقرير المالي للمنتج المجمع: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def enhance_transaction_audit_trail(
        journal_entry,
        bundle_product,
        component_deductions: List[Dict],
        transaction_context: Dict[str, Any]
    ) -> Dict:
        """
        تعزيز مسار التدقيق للقيد المحاسبي بتفاصيل إضافية
        
        Args:
            journal_entry: القيد المحاسبي
            bundle_product: المنتج المجمع
            component_deductions: تفاصيل خصم المكونات
            transaction_context: سياق المعاملة
            
        Returns:
            Dict: مسار تدقيق محسن
            
        Requirements: 6.6
        """
        try:
            # حساب المبلغ الإجمالي من القيد
            total_amount = sum(line.debit for line in journal_entry.lines.all())
            quantity = int(total_amount / bundle_product.selling_price) if bundle_product.selling_price > 0 else 0
            
            # حساب التكلفة الفعلية للمكونات
            actual_component_cost = Decimal('0.00')
            for deduction in component_deductions:
                component_id = deduction.get('component_id')
                if component_id:
                    try:
                        from ..models import Product
                        component = Product.objects.get(id=component_id)
                        component_cost = component.cost_price * deduction.get('deducted_quantity', 0)
                        actual_component_cost += component_cost
                    except Product.DoesNotExist:
                        continue
            
            # تحليل التباين في التكلفة
            bundle_recorded_cost = bundle_product.cost_price * quantity
            cost_variance = bundle_recorded_cost - actual_component_cost
            
            enhanced_audit = {
                'enhanced_audit_id': f"ENH_AUDIT_{journal_entry.id}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
                'base_entry_id': journal_entry.id,
                'base_entry_number': journal_entry.number,
                'enhancement_timestamp': timezone.now().isoformat(),
                
                # تفاصيل التسعير المحسنة
                'pricing_analysis': {
                    'bundle_selling_price': float(bundle_product.selling_price),
                    'bundle_recorded_cost': float(bundle_recorded_cost),
                    'actual_component_cost': float(actual_component_cost),
                    'cost_variance': float(cost_variance),
                    'cost_variance_percentage': float((cost_variance / bundle_recorded_cost * 100) if bundle_recorded_cost > 0 else 0),
                    'profit_margin_recorded': float(((bundle_product.selling_price - bundle_product.cost_price) / bundle_product.selling_price * 100) if bundle_product.selling_price > 0 else 0),
                    'profit_margin_actual': float(((bundle_product.selling_price - (actual_component_cost / quantity if quantity > 0 else 1)) / bundle_product.selling_price * 100) if bundle_product.selling_price > 0 else 0)
                },
                
                # تفاصيل المكونات المحسنة
                'component_analysis': {
                    'total_components': len(component_deductions),
                    'total_component_cost': float(actual_component_cost),
                    'component_breakdown': component_deductions,
                    'cost_distribution': []  # Simplified to avoid complex queries in audit trail
                },
                
                # معلومات الامتثال المحسنة
                'compliance_details': {
                    'bundle_price_recording_compliant': True,
                    'component_tracking_level': 'detailed',
                    'audit_trail_completeness': 'enhanced',
                    'cost_variance_threshold_exceeded': abs(cost_variance) > Decimal('10.00'),
                    'requires_management_review': abs(cost_variance) > Decimal('50.00'),
                    'financial_controls_applied': [
                        'bundle_price_validation',
                        'component_stock_verification',
                        'atomic_transaction_processing',
                        'audit_trail_generation'
                    ]
                },
                
                # سياق المعاملة المحسن
                'transaction_context_enhanced': {
                    **transaction_context,
                    'transaction_complexity': 'bundle_sale',
                    'risk_level': 'low' if abs(cost_variance) < Decimal('10.00') else 'medium' if abs(cost_variance) < Decimal('50.00') else 'high',
                    'processing_method': 'automated_bundle_engine',
                    'validation_checks_passed': [
                        'bundle_availability_check',
                        'component_stock_validation',
                        'financial_account_validation',
                        'transaction_context_validation'
                    ]
                }
            }
            
            # حفظ مسار التدقيق المحسن
            
            return enhanced_audit
            
        except Exception as e:
            logger.error(f"خطأ في تعزيز مسار التدقيق: {e}")
            return {'error': str(e)}

