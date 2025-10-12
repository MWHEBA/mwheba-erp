"""
خدمة حسابات التشطيب المتخصصة
"""
from decimal import Decimal
from ..models import FinishingType
from supplier.models import SpecializedService


class FinishingCalculatorService:
    """خدمة حسابات التشطيب"""
    
    @staticmethod
    def calculate_coating_cost(service_id, quantity):
        """حساب تكلفة التغطية"""
        try:
            service = SpecializedService.objects.get(id=service_id, category__code='finishing', is_active=True)
            
            # التحقق من الحد الأدنى للكمية
            if quantity < service.minimum_quantity:
                quantity = service.minimum_quantity
            
            total_cost = quantity * service.unit_price
            
            return {
                'success': True,
                'total_cost': float(total_cost),
                'unit_price': float(service.unit_price),
                'quantity': quantity,
                'minimum_quantity': service.minimum_quantity,
                'service_name': service.name,
                'supplier_name': service.supplier.name
            }
            
        except SpecializedService.DoesNotExist:
            return {
                'success': False,
                'error': 'خدمة التغطية غير موجودة'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في حساب تكلفة التغطية: {str(e)}'
            }
    
    @staticmethod
    def calculate_folding_cost(service_id, quantity, folds_count=1):
        """حساب تكلفة الطي"""
        try:
            service = SpecializedService.objects.get(id=service_id, category__code='finishing', is_active=True)
            
            # التحقق من الحد الأدنى للكمية
            if quantity < service.minimum_quantity:
                quantity = service.minimum_quantity
            
            # تكلفة إضافية للطيات المتعددة
            fold_multiplier = Decimal(str(folds_count)) if folds_count > 1 else Decimal('1.0')
            
            unit_cost = service.unit_price * fold_multiplier
            total_cost = quantity * unit_cost
            
            return {
                'success': True,
                'total_cost': float(total_cost),
                'unit_price': float(unit_cost),
                'base_unit_price': float(service.unit_price),
                'quantity': quantity,
                'folds_count': folds_count,
                'minimum_quantity': service.minimum_quantity,
                'service_name': service.name,
                'supplier_name': service.supplier.name
            }
            
        except SpecializedService.DoesNotExist:
            return {
                'success': False,
                'error': 'خدمة الطي غير موجودة'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في حساب تكلفة الطي: {str(e)}'
            }
    
    @staticmethod
    def calculate_die_cut_cost(service_id, quantity, cut_complexity='simple'):
        """حساب تكلفة القص"""
        try:
            service = SpecializedService.objects.get(id=service_id, category__code='finishing', is_active=True)
            
            # التحقق من الحد الأدنى للكمية
            if quantity < service.minimum_quantity:
                quantity = service.minimum_quantity
            
            # مضاعف التعقيد
            complexity_multipliers = {
                'simple': Decimal('1.0'),
                'medium': Decimal('1.5'),
                'complex': Decimal('2.0')
            }
            
            complexity_multiplier = complexity_multipliers.get(cut_complexity, Decimal('1.0'))
            
            unit_cost = service.unit_price * complexity_multiplier
            total_cost = quantity * unit_cost
            
            return {
                'success': True,
                'total_cost': float(total_cost),
                'unit_price': float(unit_cost),
                'base_unit_price': float(service.unit_price),
                'quantity': quantity,
                'cut_complexity': cut_complexity,
                'complexity_multiplier': float(complexity_multiplier),
                'minimum_quantity': service.minimum_quantity,
                'service_name': service.name,
                'supplier_name': service.supplier.name
            }
            
        except SpecializedService.DoesNotExist:
            return {
                'success': False,
                'error': 'خدمة القص غير موجودة'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في حساب تكلفة القص: {str(e)}'
            }
    
    @staticmethod
    def calculate_spot_uv_cost(service_id, quantity, coverage_percentage=10):
        """حساب تكلفة الورنيش الموضعي"""
        try:
            service = SpecializedService.objects.get(id=service_id, category__code='finishing', is_active=True)
            
            # التحقق من الحد الأدنى للكمية
            if quantity < service.minimum_quantity:
                quantity = service.minimum_quantity
            
            # مضاعف التغطية (كلما زادت المساحة المغطاة زادت التكلفة)
            coverage_factor = Decimal(str(coverage_percentage)) / Decimal('100.0')
            coverage_multiplier = Decimal('0.5') + coverage_factor  # حد أدنى 50% من السعر
            
            unit_cost = service.unit_price * coverage_multiplier
            total_cost = quantity * unit_cost
            
            return {
                'success': True,
                'total_cost': float(total_cost),
                'unit_price': float(unit_cost),
                'base_unit_price': float(service.unit_price),
                'quantity': quantity,
                'coverage_percentage': coverage_percentage,
                'coverage_multiplier': float(coverage_multiplier),
                'minimum_quantity': service.minimum_quantity,
                'service_name': service.name,
                'supplier_name': service.supplier.name
            }
            
        except SpecializedService.DoesNotExist:
            return {
                'success': False,
                'error': 'خدمة الورنيش الموضعي غير موجودة'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في حساب تكلفة الورنيش الموضعي: {str(e)}'
            }
    
    @staticmethod
    def calculate_binding_cost(service_id, quantity, pages_count=1, binding_type='saddle_stitch'):
        """حساب تكلفة التجليد"""
        try:
            service = SpecializedService.objects.get(id=service_id, category__code='finishing', is_active=True)
            
            # التحقق من الحد الأدنى للكمية
            if quantity < service.minimum_quantity:
                quantity = service.minimum_quantity
            
            # مضاعفات أنواع التجليد
            binding_multipliers = {
                'saddle_stitch': Decimal('1.0'),      # تدبيس وسط
                'perfect_binding': Decimal('2.0'),    # تجليد مثالي
                'spiral_binding': Decimal('1.5'),     # تجليد حلزوني
                'hardcover': Decimal('3.0')           # غلاف صلب
            }
            
            binding_multiplier = binding_multipliers.get(binding_type, Decimal('1.0'))
            
            # مضاعف عدد الصفحات
            pages_multiplier = Decimal('1.0') + (Decimal(str(pages_count)) / Decimal('100.0'))
            
            unit_cost = service.unit_price * binding_multiplier * pages_multiplier
            total_cost = quantity * unit_cost
            
            return {
                'success': True,
                'total_cost': float(total_cost),
                'unit_price': float(unit_cost),
                'base_unit_price': float(service.unit_price),
                'quantity': quantity,
                'pages_count': pages_count,
                'binding_type': binding_type,
                'binding_multiplier': float(binding_multiplier),
                'pages_multiplier': float(pages_multiplier),
                'minimum_quantity': service.minimum_quantity,
                'service_name': service.name,
                'supplier_name': service.supplier.name
            }
            
        except SpecializedService.DoesNotExist:
            return {
                'success': False,
                'error': 'خدمة التجليد غير موجودة'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في حساب تكلفة التجليد: {str(e)}'
            }
    
    @staticmethod
    def calculate_multiple_services_cost(services_data, quantity):
        """حساب تكلفة خدمات متعددة"""
        try:
            total_cost = Decimal('0.00')
            services_breakdown = []
            
            for service_data in services_data:
                service_type = service_data.get('service_type')
                service_id = service_data.get('service_id')
                
                if service_type == 'coating':
                    result = FinishingCalculatorService.calculate_coating_cost(service_id, quantity)
                elif service_type == 'folding':
                    folds_count = service_data.get('folds_count', 1)
                    result = FinishingCalculatorService.calculate_folding_cost(service_id, quantity, folds_count)
                elif service_type == 'die_cut':
                    complexity = service_data.get('cut_complexity', 'simple')
                    result = FinishingCalculatorService.calculate_die_cut_cost(service_id, quantity, complexity)
                elif service_type == 'spot_uv':
                    coverage = service_data.get('coverage_percentage', 10)
                    result = FinishingCalculatorService.calculate_spot_uv_cost(service_id, quantity, coverage)
                elif service_type == 'binding':
                    pages_count = service_data.get('pages_count', 1)
                    binding_type = service_data.get('binding_type', 'saddle_stitch')
                    result = FinishingCalculatorService.calculate_binding_cost(service_id, quantity, pages_count, binding_type)
                else:
                    continue
                
                if result['success']:
                    total_cost += Decimal(str(result['total_cost']))
                    services_breakdown.append(result)
                else:
                    services_breakdown.append(result)
            
            return {
                'success': True,
                'total_finishing_cost': float(total_cost),
                'services_breakdown': services_breakdown,
                'services_count': len([s for s in services_breakdown if s['success']])
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في حساب تكلفة الخدمات المتعددة: {str(e)}'
            }
    
    @staticmethod
    def get_finishing_services_by_type(service_type):
        """الحصول على خدمات التشطيب حسب النوع"""
        try:
            services = SpecializedService.objects.filter(
                category__code='finishing',
                is_active=True
            ).select_related('supplier')
            
            services_list = []
            for service in services:
                services_list.append({
                    'id': service.id,
                    'name': service.name,
                    'description': service.description,
                    'unit_price': float(service.unit_price),
                    'minimum_quantity': service.minimum_quantity,
                    'supplier_id': service.supplier.id,
                    'supplier_name': service.supplier.name
                })
            
            return {
                'success': True,
                'services': services_list
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في جلب خدمات التشطيب: {str(e)}'
            }
