from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from django.db import models
from decimal import Decimal
import json

from ..models import PrintingOrder, CostCalculation, OrderSummary, CalculationType
from ..services.calculators.base_calculator import BaseCalculator


class BaseAPIView(LoginRequiredMixin, View):
    """
    الفئة الأساسية لجميع APIs مع معالجة محسنة للأخطاء
    """
    
    def dispatch(self, request, *args, **kwargs):
        """معالجة الطلبات مع التحقق من الصلاحيات"""
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'error': _('يجب تسجيل الدخول أولاً'),
                'error_code': 'AUTHENTICATION_REQUIRED'
            }, status=401)
        
        return super().dispatch(request, *args, **kwargs)
    
    def handle_exception(self, e, context=""):
        """معالجة موحدة للأخطاء مع رسائل مفصلة"""
        error_message = str(e)
        
        if isinstance(e, ValueError):
            return JsonResponse({
                'success': False,
                'error': _('خطأ في البيانات المرسلة'),
                'details': error_message,
                'suggestion': _('تأكد من صحة جميع القيم المدخلة'),
                'error_code': 'VALIDATION_ERROR',
                'context': context
            }, status=400)
        
        elif isinstance(e, KeyError):
            return JsonResponse({
                'success': False,
                'error': _('معاملات مطلوبة مفقودة'),
                'details': _('المعامل المفقود: {}').format(error_message),
                'suggestion': _('تأكد من إرسال جميع المعاملات المطلوبة'),
                'error_code': 'MISSING_PARAMETERS',
                'context': context
            }, status=400)
        
        elif hasattr(e, '__class__') and 'DoesNotExist' in e.__class__.__name__:
            return JsonResponse({
                'success': False,
                'error': _('البيانات المطلوبة غير موجودة'),
                'details': error_message,
                'suggestion': _('تأكد من صحة معرف الطلب'),
                'error_code': 'NOT_FOUND',
                'context': context
            }, status=404)
        
        else:
            return JsonResponse({
                'success': False,
                'error': _('حدث خطأ غير متوقع'),
                'details': error_message,
                'suggestion': _('يرجى المحاولة مرة أخرى أو الاتصال بالدعم الفني'),
                'error_code': 'INTERNAL_ERROR',
                'context': context
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class CalculateCostAPIView(BaseAPIView):
    """
    API حساب التكلفة الشامل
    """
    
    def post(self, request):
        """حساب التكلفة لطلب معين"""
        try:
            data = json.loads(request.body)
            
            # التحقق من المعاملات المطلوبة
            required_params = ['order_id', 'calculation_types']
            missing_params = []
            
            for param in required_params:
                if param not in data:
                    missing_params.append(param)
            
            if missing_params:
                return JsonResponse({
                    'success': False,
                    'error': _('معاملات مطلوبة مفقودة: {}').format(', '.join(missing_params)),
                    'missing_params': missing_params,
                    'received_params': list(data.keys()),
                    'suggestion': _('تأكد من إرسال جميع المعاملات المطلوبة')
                }, status=400)
            
            # جلب الطلب
            order = get_object_or_404(PrintingOrder, pk=data['order_id'], is_active=True)
            
            # أنواع الحسابات المطلوبة
            calculation_types = data['calculation_types']
            if not isinstance(calculation_types, list):
                calculation_types = [calculation_types]
            
            results = {}
            total_cost = Decimal('0.00')
            
            # تنفيذ الحسابات
            for calc_type in calculation_types:
                try:
                    # هنا سيتم استدعاء الحاسبات المتخصصة لاحقاً
                    calculator = BaseCalculator(order)
                    result = calculator.calculate(calc_type, data.get('parameters', {}))
                    
                    results[calc_type] = result
                    total_cost += result.get('total_cost', Decimal('0.00'))
                    
                    # حفظ نتيجة الحساب
                    CostCalculation.objects.create(
                        order=order,
                        calculation_type=calc_type,
                        base_cost=result.get('base_cost', Decimal('0.00')),
                        additional_costs=result.get('additional_costs', Decimal('0.00')),
                        total_cost=result.get('total_cost', Decimal('0.00')),
                        calculation_details=result.get('details', {}),
                        parameters_used=data.get('parameters', {}),
                        created_by=request.user
                    )
                    
                except Exception as calc_error:
                    results[calc_type] = {
                        'success': False,
                        'error': str(calc_error)
                    }
            
            # تحديث تكلفة الطلب
            order.estimated_cost = total_cost
            order.updated_by = request.user
            order.save()
            
            # تحديث ملخص التكاليف
            try:
                summary = order.summary
                summary.update_from_calculations()
            except OrderSummary.DoesNotExist:
                OrderSummary.objects.create(order=order)
            
            return JsonResponse({
                'success': True,
                'message': _('تم حساب التكلفة بنجاح'),
                'results': results,
                'total_cost': float(total_cost),
                'order_id': order.id,
                'calculation_timestamp': order.updated_at.isoformat()
            })
            
        except Exception as e:
            return self.handle_exception(e, "CalculateCostAPIView.post")


@method_decorator(csrf_exempt, name='dispatch')
class GetMaterialPriceAPIView(BaseAPIView):
    """
    API جلب أسعار المواد
    """
    
    def get(self, request):
        """جلب سعر مادة معينة"""
        try:
            # معاملات البحث
            material_type = request.GET.get('material_type')
            material_name = request.GET.get('material_name')
            supplier_id = request.GET.get('supplier_id')
            
            # التحقق من المعاملات
            if not material_type:
                return JsonResponse({
                    'success': False,
                    'error': _('نوع المادة مطلوب'),
                    'missing_params': ['material_type'],
                    'suggestion': _('حدد نوع المادة المطلوبة')
                }, status=400)
            
            # هنا سيتم البحث في قاعدة بيانات المواد والموردين
            # مؤقتاً نرجع أسعار تجريبية
            sample_prices = {
                'paper': {
                    'unit_cost': 2.50,
                    'unit': 'sheet',
                    'supplier': 'مورد الورق الرئيسي',
                    'last_updated': '2024-01-15'
                },
                'ink': {
                    'unit_cost': 150.00,
                    'unit': 'kilogram',
                    'supplier': 'مورد الأحبار',
                    'last_updated': '2024-01-10'
                }
            }
            
            price_info = sample_prices.get(material_type)
            if not price_info:
                return JsonResponse({
                    'success': False,
                    'error': _('لا توجد معلومات أسعار لهذا النوع من المواد'),
                    'search_criteria': {
                        'material_type': material_type,
                        'material_name': material_name,
                        'supplier_id': supplier_id
                    },
                    'suggestion': _('تأكد من صحة نوع المادة أو أضف السعر يدوياً')
                }, status=404)
            
            return JsonResponse({
                'success': True,
                'price_info': price_info,
                'search_criteria': {
                    'material_type': material_type,
                    'material_name': material_name,
                    'supplier_id': supplier_id
                }
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetMaterialPriceAPIView.get")


@method_decorator(csrf_exempt, name='dispatch')
class GetServicePriceAPIView(BaseAPIView):
    """
    API جلب أسعار الخدمات
    """
    
    def get(self, request):
        """جلب سعر خدمة معينة"""
        try:
            # معاملات البحث
            service_category = request.GET.get('service_category')
            service_name = request.GET.get('service_name')
            supplier_id = request.GET.get('supplier_id')
            
            # التحقق من المعاملات
            if not service_category:
                return JsonResponse({
                    'success': False,
                    'error': _('فئة الخدمة مطلوبة'),
                    'missing_params': ['service_category'],
                    'suggestion': _('حدد فئة الخدمة المطلوبة')
                }, status=400)
            
            # أسعار تجريبية للخدمات
            sample_prices = {
                'printing': {
                    'unit_price': 0.50,
                    'setup_cost': 25.00,
                    'unit': 'piece',
                    'supplier': 'مطبعة الجودة',
                    'execution_time': 2
                },
                'finishing': {
                    'unit_price': 0.25,
                    'setup_cost': 15.00,
                    'unit': 'piece',
                    'supplier': 'ورشة التشطيبات',
                    'execution_time': 1
                }
            }
            
            price_info = sample_prices.get(service_category)
            if not price_info:
                return JsonResponse({
                    'success': False,
                    'error': _('لا توجد معلومات أسعار لهذه الفئة من الخدمات'),
                    'search_criteria': {
                        'service_category': service_category,
                        'service_name': service_name,
                        'supplier_id': supplier_id
                    },
                    'suggestion': _('تأكد من صحة فئة الخدمة أو أضف السعر يدوياً')
                }, status=404)
            
            return JsonResponse({
                'success': True,
                'price_info': price_info,
                'search_criteria': {
                    'service_category': service_category,
                    'service_name': service_name,
                    'supplier_id': supplier_id
                }
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetServicePriceAPIView.get")


@method_decorator(csrf_exempt, name='dispatch')
class ValidateOrderAPIView(BaseAPIView):
    """
    API التحقق من صحة بيانات الطلب
    """
    
    def post(self, request):
        """التحقق من صحة بيانات الطلب"""
        try:
            data = json.loads(request.body)
            
            # قائمة الأخطاء
            errors = []
            warnings = []
            
            # التحقق من البيانات الأساسية
            required_fields = ['customer_id', 'title', 'quantity', 'order_type']
            for field in required_fields:
                if not data.get(field):
                    errors.append(_('الحقل {} مطلوب').format(field))
            
            # التحقق من الكمية
            quantity = data.get('quantity')
            if quantity and (not isinstance(quantity, (int, float)) or quantity <= 0):
                errors.append(_('الكمية يجب أن تكون رقماً موجباً'))
            
            # التحقق من الأبعاد
            width = data.get('width')
            height = data.get('height')
            if width and height:
                if width <= 0 or height <= 0:
                    errors.append(_('الأبعاد يجب أن تكون أكبر من صفر'))
            elif width or height:
                warnings.append(_('يُفضل تحديد كلا البعدين (العرض والارتفاع)'))
            
            # التحقق من هامش الربح
            profit_margin = data.get('profit_margin')
            if profit_margin and (profit_margin < 0 or profit_margin > 100):
                errors.append(_('هامش الربح يجب أن يكون بين 0 و 100%'))
            
            # تحذيرات إضافية
            if quantity and quantity > 10000:
                warnings.append(_('الكمية كبيرة جداً، تأكد من صحتها'))
            
            if not data.get('due_date'):
                warnings.append(_('لم يتم تحديد تاريخ التسليم'))
            
            # النتيجة
            is_valid = len(errors) == 0
            
            return JsonResponse({
                'success': True,
                'is_valid': is_valid,
                'errors': errors,
                'warnings': warnings,
                'validated_data': data,
                'validation_summary': {
                    'total_errors': len(errors),
                    'total_warnings': len(warnings),
                    'status': 'valid' if is_valid else 'invalid'
                }
            })
            
        except Exception as e:
            return self.handle_exception(e, "ValidateOrderAPIView.post")


@method_decorator(csrf_exempt, name='dispatch')
class OrderSummaryAPIView(BaseAPIView):
    """
    API ملخص الطلب
    """
    
    def get(self, request, order_id):
        """جلب ملخص شامل للطلب"""
        try:
            order = get_object_or_404(PrintingOrder, pk=order_id, is_active=True)
            
            # معلومات أساسية
            order_info = {
                'id': order.id,
                'order_number': order.order_number,
                'title': order.title,
                'customer': {
                    'id': order.customer.id,
                    'name': order.customer.name,
                    'company': getattr(order.customer, 'company_name', '')
                },
                'status': order.status,
                'order_type': order.order_type,
                'quantity': order.quantity,
                'estimated_cost': float(order.estimated_cost or 0),
                'created_at': order.created_at.isoformat(),
                'updated_at': order.updated_at.isoformat()
            }
            
            # المواد والخدمات
            materials = []
            for material in order.materials.filter(is_active=True):
                materials.append({
                    'id': material.id,
                    'type': material.material_type,
                    'name': material.material_name,
                    'quantity': float(material.quantity),
                    'unit': material.unit,
                    'unit_cost': float(material.unit_cost),
                    'total_cost': float(material.total_cost)
                })
            
            services = []
            for service in order.services.filter(is_active=True):
                services.append({
                    'id': service.id,
                    'category': service.service_category,
                    'name': service.service_name,
                    'quantity': float(service.quantity),
                    'unit': service.unit,
                    'unit_price': float(service.unit_price),
                    'total_cost': float(service.total_cost),
                    'is_optional': service.is_optional
                })
            
            # الحسابات الحالية
            calculations = {}
            for calc in order.calculations.filter(is_current=True):
                calculations[calc.calculation_type] = {
                    'base_cost': float(calc.base_cost),
                    'additional_costs': float(calc.additional_costs),
                    'total_cost': float(calc.total_cost),
                    'calculation_date': calc.calculation_date.isoformat()
                }
            
            # ملخص التكاليف
            try:
                summary = order.summary
                cost_summary = {
                    'material_cost': float(summary.material_cost),
                    'printing_cost': float(summary.printing_cost),
                    'finishing_cost': float(summary.finishing_cost),
                    'design_cost': float(summary.design_cost),
                    'subtotal': float(summary.subtotal),
                    'total_cost': float(summary.total_cost),
                    'profit_margin': float(summary.profit_margin_percentage),
                    'final_price': float(summary.final_price)
                }
            except OrderSummary.DoesNotExist:
                cost_summary = None
            
            return JsonResponse({
                'success': True,
                'order_info': order_info,
                'materials': materials,
                'services': services,
                'calculations': calculations,
                'cost_summary': cost_summary,
                'totals': {
                    'materials_count': len(materials),
                    'services_count': len(services),
                    'calculations_count': len(calculations)
                }
            })
            
        except Exception as e:
            return self.handle_exception(e, "OrderSummaryAPIView.get")


class GetClientsAPIView(BaseAPIView):
    """
    API لجلب قائمة العملاء للـ Select2
    """
    
    def get(self, request):
        try:
            from client.models import Customer
            
            # الحصول على معامل البحث
            search = request.GET.get('search', '').strip()
            page = int(request.GET.get('page', 1))
            page_size = 20  # عدد النتائج في كل صفحة
            
            # بناء الاستعلام
            queryset = Customer.objects.filter(is_active=True)
            
            if search:
                queryset = queryset.filter(
                    models.Q(name__icontains=search) |
                    models.Q(company_name__icontains=search) |
                    models.Q(code__icontains=search)
                ).distinct()
            
            # ترقيم الصفحات
            total_count = queryset.count()
            start = (page - 1) * page_size
            end = start + page_size
            clients = queryset[start:end]
            
            # تحويل البيانات لصيغة Select2
            results = []
            for client in clients:
                display_name = client.name
                if client.company_name:
                    display_name = f"{client.name} - {client.company_name}"
                if client.code:
                    display_name = f"[{client.code}] {display_name}"
                
                results.append({
                    'id': client.id,
                    'text': display_name,
                    'name': client.name,
                    'company_name': client.company_name or '',
                    'code': client.code,
                    'phone': client.phone_primary or client.phone or '',
                    'email': client.email or ''
                })
            
            return JsonResponse({
                'success': True,
                'results': results,
                'pagination': {
                    'more': end < total_count,
                    'total_count': total_count,
                    'page': page,
                    'page_size': page_size
                }
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetClientsAPIView.get")


class GetProductTypesAPIView(BaseAPIView):
    """
    API لجلب أنواع المنتجات
    """
    
    def get(self, request):
        try:
            from pricing.models import ProductType
            
            # جلب أنواع المنتجات النشطة
            product_types = ProductType.objects.filter(is_active=True).order_by('name')
            
            results = []
            for product_type in product_types:
                results.append({
                    'id': product_type.id,
                    'text': product_type.name,
                    'name': product_type.name,
                    'description': product_type.description or '',
                    'is_default': product_type.is_default
                })
            
            return JsonResponse({
                'success': True,
                'results': results,
                'total_count': len(results)
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetProductTypesAPIView.get")


class GetProductSizesAPIView(BaseAPIView):
    """
    API لجلب أحجام المنتجات
    """
    
    def get(self, request):
        try:
            from pricing.models import ProductSize
            
            # جلب أحجام المنتجات النشطة
            product_sizes = ProductSize.objects.filter(is_active=True).order_by('name')
            
            results = []
            for product_size in product_sizes:
                # تنسيق الأبعاد
                dimensions = f"{product_size.width} × {product_size.height} سم"
                display_text = f"{product_size.name} ({dimensions})"
                
                results.append({
                    'id': product_size.id,
                    'text': display_text,
                    'name': product_size.name,
                    'width': float(product_size.width),
                    'height': float(product_size.height),
                    'dimensions': dimensions,
                    'description': product_size.description or '',
                    'is_default': product_size.is_default
                })
            
            return JsonResponse({
                'success': True,
                'results': results,
                'total_count': len(results)
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetProductSizesAPIView.get")


__all__ = [
    'BaseAPIView', 'CalculateCostAPIView', 'GetMaterialPriceAPIView',
    'GetServicePriceAPIView', 'ValidateOrderAPIView', 'OrderSummaryAPIView',
    'GetClientsAPIView', 'GetProductTypesAPIView', 'GetProductSizesAPIView'
]
