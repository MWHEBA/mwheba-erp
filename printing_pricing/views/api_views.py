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

from supplier.models import Supplier
from printing_pricing.models.settings_models import PaperOrigin, PieceSize

# تحميل نماذج خدمات الموردين — متاحة بعد المرحلة الأولى
try:
    from supplier.models import ServiceType, SupplierService as SupplierServiceModel
    HAS_SUPPLIER_SERVICES = True
except ImportError:
    ServiceType = None
    SupplierServiceModel = None
    HAS_SUPPLIER_SERVICES = False

# النماذج القديمة غير موجودة — الـ APIs تعمل بـ fallback حتى تكتمل المرحلة الأولى
PaperServiceDetails = None
OffsetPrintingDetails = None
DigitalPrintingDetails = None
PlateServiceDetails = None
HAS_PAPER_SERVICE_DETAILS = False
HAS_MACHINE_MODELS = False
HAS_PLATE_MODEL = False


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
                    'last_updated': '2025-01-15'
                },
                'ink': {
                    'unit_cost': 150.00,
                    'unit': 'kilogram',
                    'supplier': 'مورد الأحبار',
                    'last_updated': '2025-01-10'
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
                    'supplier': 'ورشة خدمات الطباعة',
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
                # بناء النص المعروض بطريقة واضحة ومنظمة
                display_parts = []
                
                # إضافة الكود إذا وُجد
                if client.code:
                    display_parts.append(f"[{client.code}]")
                
                # إضافة اسم العميل
                display_parts.append(client.name)
                
                # إضافة اسم الشركة إذا وُجد ومختلف عن اسم العميل
                if client.company_name and client.company_name != client.name:
                    display_parts.append(f"- {client.company_name}")
                
                # دمج الأجزاء
                display_name = " ".join(display_parts)
                
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
            from printing_pricing.models.settings_models import ProductType
            
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
            from printing_pricing.models.settings_models import ProductSize
            
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


class GetPrintingSuppliersAPIView(BaseAPIView):
    """
    API لجلب المطابع المتاحة — يستخدم SupplierService (offset_printing / digital_printing)
    """
    
    def get(self, request):
        try:
            order_type = request.GET.get('order_type', '')

            if HAS_SUPPLIER_SERVICES:
                # تحديد كود نوع الخدمة حسب نوع الطلب
                if order_type == 'offset':
                    codes = ['offset_printing']
                elif order_type == 'digital':
                    codes = ['digital_printing']
                else:
                    codes = ['offset_printing', 'digital_printing']

                from supplier.services.supplier_service import SupplierService as SvcClass
                results = []
                seen = set()
                for code in codes:
                    for s in SvcClass.get_suppliers_by_service_type(code):
                        if s.id not in seen:
                            seen.add(s.id)
                            offset_count = s.services.filter(service_type__code='offset_printing', is_active=True).count()
                            digital_count = s.services.filter(service_type__code='digital_printing', is_active=True).count()
                            machine_info = []
                            if offset_count: machine_info.append(f"{offset_count} أوفست")
                            if digital_count: machine_info.append(f"{digital_count} ديجيتال")
                            display_name = s.name + (f" ({', '.join(machine_info)})" if machine_info else "")
                            results.append({
                                'id': s.id, 'text': display_name, 'name': s.name,
                                'contact_person': s.contact_person or '', 'phone': s.phone or '',
                                'email': s.email or '', 'address': s.address or '',
                                'offset_machines': offset_count, 'digital_machines': digital_count,
                            })
                return JsonResponse({'success': True, 'suppliers': results, 'total_count': len(results)})

            return JsonResponse({'success': True, 'suppliers': [], 'total_count': 0})
        except Exception as e:
            return self.handle_exception(e, "GetPrintingSuppliersAPIView.get")


class GetPressesAPIView(BaseAPIView):
    """
    API لجلب الماكينات المتاحة لدى المطبعة — يستخدم SupplierService
    """
    
    def get(self, request):
        try:
            supplier_id = request.GET.get('supplier_id')
            order_type  = request.GET.get('order_type', '')

            if not supplier_id:
                return JsonResponse({'success': False, 'error': _('معرف المطبعة مطلوب'), 'missing_params': ['supplier_id']}, status=400)

            try:
                supplier = Supplier.objects.get(id=supplier_id, is_active=True)
            except Supplier.DoesNotExist:
                return JsonResponse({'success': False, 'error': _('المطبعة غير موجودة أو غير نشطة')}, status=404)

            if not HAS_SUPPLIER_SERVICES:
                return JsonResponse({'success': True, 'presses': [], 'supplier_info': {'id': supplier.id, 'name': supplier.name}, 'total_count': 0})

            from supplier.services.supplier_service import SupplierService as SvcClass

            if order_type == 'offset':
                codes = ['offset_printing']
            elif order_type == 'digital':
                codes = ['digital_printing']
            else:
                codes = ['offset_printing', 'digital_printing']

            presses = []
            for code in codes:
                for svc in SvcClass.get_supplier_services(supplier_id, code):
                    svc_type = 'offset' if code == 'offset_printing' else 'digital'
                    price = float(svc.get_price_for_quantity(1))
                    presses.append({
                        'id':            f'{svc_type}_{svc.id}',
                        'name':          svc.name,
                        'type':          svc_type,
                        'price_per_1000': price,
                        'setup_cost':    float(svc.setup_cost),
                        'attributes':    svc.attributes,
                        'service_id':    svc.id,
                    })

            return JsonResponse({'success': True, 'presses': presses,
                                 'supplier_info': {'id': supplier.id, 'name': supplier.name}, 'total_count': len(presses)})
        except Exception as e:
            return self.handle_exception(e, "GetPressesAPIView.get")


class GetPressPriceAPIView(BaseAPIView):
    """
    API لجلب سعر ماكينة معينة — يستخدم SupplierService
    """
    
    def get(self, request):
        try:
            press_id = request.GET.get('press_id')
            if not press_id:
                return JsonResponse({'success': False, 'error': _('معرف الماكينة مطلوب'), 'missing_params': ['press_id']}, status=400)

            price_info = None

            if HAS_SUPPLIER_SERVICES:
                # press_id format: offset_<service_id> or digital_<service_id>
                for prefix in ('offset_', 'digital_'):
                    if press_id.startswith(prefix):
                        svc_id = press_id.replace(prefix, '')
                        from supplier.services.supplier_service import SupplierService as SvcClass
                        result = SvcClass.get_service_price(svc_id)
                        if result:
                            price_info = {
                                'price_per_1000': float(result['price']),
                                'setup_cost':     float(result['setup_cost']),
                                'minimum_quantity': 500 if prefix == 'offset_' else 100,
                                'service_id':     svc_id,
                                'supplier_name':  result['supplier_name'],
                                'attributes':     result['attributes'],
                            }
                        break

            if not price_info:
                price_info = {
                    'price_per_1000': 35.00 if 'digital' in press_id.lower() else 50.00,
                    'setup_cost':     10.00 if 'digital' in press_id.lower() else 20.00,
                    'minimum_quantity': 200 if 'digital' in press_id.lower() else 500,
                }

            return JsonResponse({'success': True, 'press_id': press_id,
                                 'price_per_1000': price_info['price_per_1000'],
                                 'price':          price_info['price_per_1000'],
                                 'unit_price':     price_info['price_per_1000'],
                                 'setup_cost':     price_info['setup_cost'],
                                 'minimum_quantity': price_info['minimum_quantity'],
                                 'service_id':     price_info.get('service_id'),
                                 'supplier_name':  price_info.get('supplier_name', ''),
                                 'attributes':     price_info.get('attributes', {}),
                                 })
        except Exception as e:
            return self.handle_exception(e, "GetPressPriceAPIView.get")


class GetCTPSuppliersAPIView(BaseAPIView):
    """
    API لجلب موردي الزنكات — يستخدم SupplierService (ctp_plates)
    """
    
    def get(self, request):
        try:
            if not HAS_SUPPLIER_SERVICES:
                return JsonResponse({'success': True, 'suppliers': [], 'total_count': 0})

            from supplier.services.supplier_service import SupplierService as SvcClass
            results = []
            for s in SvcClass.get_suppliers_by_service_type('ctp_plates'):
                ctp_count = s.services.filter(service_type__code='ctp_plates', is_active=True).count()
                results.append({
                    'id': s.id, 'text': f"{s.name} ({ctp_count} خدمات زنكات)",
                    'name': s.name, 'contact_person': s.contact_person or '',
                    'phone': s.phone or '', 'email': s.email or '',
                    'address': s.address or '', 'ctp_services_count': ctp_count,
                })
            return JsonResponse({'success': True, 'suppliers': results, 'total_count': len(results)})
        except Exception as e:
            return self.handle_exception(e, "GetCTPSuppliersAPIView.get")


class GetCTPPlatesAPIView(BaseAPIView):
    """
    API لجلب خدمات الزنكات لمورد معين — يستخدم SupplierService
    """
    
    def get(self, request):
        try:
            supplier_id = request.GET.get('supplier_id')
            if not supplier_id:
                return JsonResponse({'success': False, 'error': _('معرف المورد مطلوب'), 'missing_params': ['supplier_id']}, status=400)

            try:
                supplier = Supplier.objects.get(id=supplier_id, is_active=True)
            except Supplier.DoesNotExist:
                return JsonResponse({'success': False, 'error': _('المورد غير موجود أو غير نشط')}, status=404)

            if not HAS_SUPPLIER_SERVICES:
                return JsonResponse({'success': True, 'plates': [], 'supplier_info': {'id': supplier.id, 'name': supplier.name}, 'total_count': 0})

            from supplier.services.supplier_service import SupplierService as SvcClass
            plates = []
            for svc in SvcClass.get_supplier_services(supplier_id, 'ctp_plates'):
                plates.append({
                    'id':              f'ctp_{svc.id}',
                    'name':            svc.name,
                    'service_name':    svc.name,
                    'plate_type':      svc.attributes.get('plate_type', 'عادي'),
                    'price_per_plate': float(svc.get_price_for_quantity(1)),
                    'service_id':      svc.id,
                    'attributes':      svc.attributes,
                })
            return JsonResponse({'success': True, 'plates': plates,
                                 'supplier_info': {'id': supplier.id, 'name': supplier.name}, 'total_count': len(plates)})
        except Exception as e:
            return self.handle_exception(e, "GetCTPPlatesAPIView.get")


class GetCTPPriceAPIView(BaseAPIView):
    """
    API لجلب سعر زنكة معينة — يستخدم SupplierService
    """
    
    def get(self, request):
        try:
            plate_id = request.GET.get('plate_id')
            if not plate_id:
                return JsonResponse({'success': False, 'error': _('معرف الزنكة مطلوب'), 'missing_params': ['plate_id']}, status=400)

            price_info = None

            if HAS_SUPPLIER_SERVICES and plate_id.startswith('ctp_'):
                svc_id = plate_id.replace('ctp_', '')
                from supplier.services.supplier_service import SupplierService as SvcClass
                result = SvcClass.get_service_price(svc_id)
                if result:
                    price_info = {
                        'price_per_plate': float(result['price']),
                        'setup_cost':      float(result['setup_cost']),
                        'minimum_quantity': 1,
                        'service_id':      svc_id,
                        'supplier_name':   result['supplier_name'],
                        'attributes':      result['attributes'],
                    }

            if not price_info:
                price_info = {'price_per_plate': 15.00, 'setup_cost': 5.00, 'minimum_quantity': 1}

            return JsonResponse({'success': True, 'plate_id': plate_id,
                                 'price_per_plate': price_info['price_per_plate'],
                                 'price':           price_info['price_per_plate'],
                                 'unit_price':      price_info['price_per_plate'],
                                 'setup_cost':      price_info['setup_cost'],
                                 'minimum_quantity': price_info['minimum_quantity'],
                                 'service_id':      price_info.get('service_id'),
                                 'supplier_name':   price_info.get('supplier_name', ''),
                                 'attributes':      price_info.get('attributes', {}),
                                 })
        except Exception as e:
            return self.handle_exception(e, "GetCTPPriceAPIView.get")


# ==================== APIs الورق ====================

class GetPaperTypesAPIView(BaseAPIView):
    """
    API لجلب أنواع الورق — من SupplierService.attributes أو PaperType settings
    """
    
    def get(self, request):
        try:
            # أولاً: جلب من SupplierService إذا متاح
            if HAS_SUPPLIER_SERVICES:
                paper_types_set = set()
                for svc in SupplierServiceModel.objects.filter(
                    service_type__code='paper', is_active=True, supplier__is_active=True
                ).values_list('attributes', flat=True):
                    pt = svc.get('paper_type') if isinstance(svc, dict) else None
                    if pt:
                        paper_types_set.add(pt)

                if paper_types_set:
                    types_data = [
                        {'id': i, 'name': pt, 'description': f'نوع ورق {pt}', 'is_default': i == 1}
                        for i, pt in enumerate(sorted(paper_types_set), 1)
                    ]
                    return JsonResponse({'success': True, 'paper_types': types_data, 'total_count': len(types_data)})

            # Fallback: من PaperType settings model
            if not HAS_PAPER_SERVICE_DETAILS:
                return JsonResponse({'success': True, 'paper_types': [], 'total_count': 0})

            paper_types = PaperServiceDetails.objects.filter(
                service__supplier__is_active=True, service__is_active=True
            ).values_list('paper_type', flat=True).distinct().order_by('paper_type')

            types_data = [
                {'id': i, 'name': pt, 'description': f'نوع ورق {pt}', 'is_default': i == 1}
                for i, pt in enumerate(paper_types, 1) if pt
            ]
            return JsonResponse({'success': True, 'paper_types': types_data, 'total_count': len(types_data)})
        except Exception as e:
            return self.handle_exception(e, "GetPaperTypesAPIView.get")


class GetPaperSuppliersAPIView(BaseAPIView):
    """
    API لجلب موردي الورق — يستخدم SupplierService (paper)
    """
    
    def get(self, request):
        try:
            paper_type_id = request.GET.get('paper_type_id')

            if HAS_SUPPLIER_SERVICES:
                qs = SupplierServiceModel.objects.filter(
                    service_type__code='paper', is_active=True, supplier__is_active=True
                ).select_related('supplier')

                # فلتر حسب نوع الورق إذا محدد
                if paper_type_id:
                    # paper_type_id هو رقم تسلسلي — نجلب اسم النوع أولاً
                    all_types = sorted(set(
                        s.get('paper_type') for s in SupplierServiceModel.objects.filter(
                            service_type__code='paper', is_active=True
                        ).values_list('attributes', flat=True)
                        if isinstance(s, dict) and s.get('paper_type')
                    ))
                    try:
                        paper_type_name = all_types[int(paper_type_id) - 1]
                        qs = [s for s in qs if s.attributes.get('paper_type') == paper_type_name]
                    except (IndexError, ValueError):
                        pass

                suppliers_dict = {}
                for svc in qs:
                    s = svc.supplier
                    if s.id not in suppliers_dict:
                        suppliers_dict[s.id] = {
                            'id': s.id, 'name': s.name,
                            'contact_info': s.contact_person or '',
                            'phone': s.phone or '', 'email': s.email or '',
                        }
                suppliers_data = sorted(suppliers_dict.values(), key=lambda x: x['name'])
                return JsonResponse({'success': True, 'suppliers': suppliers_data, 'total_count': len(suppliers_data)})

            if not HAS_PAPER_SERVICE_DETAILS:
                return JsonResponse({'success': True, 'suppliers': [], 'total_count': 0})

            # Fallback legacy
            filters = {'service__is_active': True, 'service__supplier__is_active': True}
            if paper_type_id:
                paper_types = list(PaperServiceDetails.objects.filter(**filters).values_list('paper_type', flat=True).distinct().order_by('paper_type'))
                try:
                    filters['paper_type'] = paper_types[int(paper_type_id) - 1]
                except (IndexError, ValueError):
                    return JsonResponse({'success': False, 'error': 'نوع الورق غير موجود'}, status=404)

            paper_services = PaperServiceDetails.objects.filter(**filters).select_related('service__supplier')
            suppliers_dict = {}
            for ps in paper_services:
                s = ps.service.supplier
                if s.id not in suppliers_dict:
                    suppliers_dict[s.id] = {'id': s.id, 'name': s.name, 'contact_info': s.contact_person or '', 'phone': s.phone or '', 'email': s.email or ''}
            suppliers_data = sorted(suppliers_dict.values(), key=lambda x: x['name'])
            return JsonResponse({'success': True, 'suppliers': suppliers_data, 'total_count': len(suppliers_data)})
        except Exception as e:
            return self.handle_exception(e, "GetPaperSuppliersAPIView.get")


class GetPaperWeightsAPIView(BaseAPIView):
    """
    API لجلب أوزان الورق — يستخدم SupplierService.attributes
    """
    
    def get(self, request):
        try:
            paper_type_id = request.GET.get('paper_type_id')
            supplier_id   = request.GET.get('supplier_id')

            if not paper_type_id:
                return JsonResponse({'success': False, 'error': 'معرف نوع الورق مطلوب', 'missing_params': ['paper_type_id']}, status=400)

            if HAS_SUPPLIER_SERVICES:
                qs = SupplierServiceModel.objects.filter(service_type__code='paper', is_active=True, supplier__is_active=True)
                if supplier_id:
                    qs = qs.filter(supplier_id=supplier_id)

                all_types = sorted(set(
                    s.get('paper_type') for s in SupplierServiceModel.objects.filter(
                        service_type__code='paper', is_active=True
                    ).values_list('attributes', flat=True)
                    if isinstance(s, dict) and s.get('paper_type')
                ))
                try:
                    paper_type_name = all_types[int(paper_type_id) - 1]
                except (IndexError, ValueError):
                    return JsonResponse({'success': False, 'error': 'نوع الورق غير موجود'}, status=404)

                weights = sorted(set(
                    s.attributes.get('gsm') for s in qs
                    if s.attributes.get('paper_type') == paper_type_name and s.attributes.get('gsm')
                ))
                weights_data = [{'value': str(w), 'display_name': f"{w} جرام", 'name': f"{w} جرام", 'gsm': w} for w in weights]
                return JsonResponse({'success': True, 'weights': weights_data,
                                     'paper_type': {'id': paper_type_id, 'name': paper_type_name},
                                     'total_count': len(weights_data)})

            if not HAS_PAPER_SERVICE_DETAILS:
                return JsonResponse({'success': True, 'weights': [], 'total_count': 0})

            paper_types = list(PaperServiceDetails.objects.filter(service__supplier__is_active=True, service__is_active=True).values_list('paper_type', flat=True).distinct().order_by('paper_type'))
            try:
                paper_type_name = paper_types[int(paper_type_id) - 1]
            except (IndexError, ValueError):
                return JsonResponse({'success': False, 'error': 'نوع الورق غير موجود'}, status=404)

            filters = {'service__supplier__is_active': True, 'service__is_active': True, 'paper_type': paper_type_name}
            if supplier_id:
                filters['service__supplier_id'] = supplier_id
            weights = PaperServiceDetails.objects.filter(**filters).values_list('gsm', flat=True).distinct().order_by('gsm')
            weights_data = [{'value': str(w), 'display_name': f"{w} جرام", 'name': f"{w} جرام", 'gsm': w} for w in weights if w]
            return JsonResponse({'success': True, 'weights': weights_data, 'paper_type': {'id': paper_type_id, 'name': paper_type_name}, 'total_count': len(weights_data)})
        except Exception as e:
            return self.handle_exception(e, "GetPaperWeightsAPIView.get")


class GetPaperSheetTypesAPIView(BaseAPIView):
    """
    API لجلب مقاسات الفرخ — يستخدم SupplierService.attributes
    """
    
    def get(self, request):
        try:
            supplier_id   = request.GET.get('supplier_id')
            paper_type_id = request.GET.get('paper_type_id')

            if not supplier_id or not paper_type_id:
                return JsonResponse({'success': False, 'error': 'معرف المورد ونوع الورق مطلوبان',
                                     'missing_params': [p for p in ['supplier_id', 'paper_type_id'] if not request.GET.get(p)]}, status=400)

            try:
                supplier = Supplier.objects.get(id=supplier_id, is_active=True)
            except Supplier.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'المورد غير موجود أو غير نشط'}, status=404)

            if HAS_SUPPLIER_SERVICES:
                all_types = sorted(set(
                    s.get('paper_type') for s in SupplierServiceModel.objects.filter(
                        service_type__code='paper', is_active=True
                    ).values_list('attributes', flat=True)
                    if isinstance(s, dict) and s.get('paper_type')
                ))
                try:
                    paper_type_name = all_types[int(paper_type_id) - 1]
                except (IndexError, ValueError):
                    return JsonResponse({'success': False, 'error': 'نوع الورق غير موجود'}, status=404)

                sheet_types = sorted(set(
                    s.attributes.get('sheet_size') for s in SupplierServiceModel.objects.filter(
                        service_type__code='paper', supplier_id=supplier_id, is_active=True
                    ) if s.attributes.get('paper_type') == paper_type_name and s.attributes.get('sheet_size')
                ))
                sheet_types_data = [{'sheet_type': st, 'display_name': st, 'sheet_size': st} for st in sheet_types]
                return JsonResponse({'success': True, 'sheet_types': sheet_types_data,
                                     'supplier': {'id': supplier.id, 'name': supplier.name},
                                     'paper_type': {'id': paper_type_id, 'name': paper_type_name},
                                     'total_count': len(sheet_types_data)})

            if not HAS_PAPER_SERVICE_DETAILS:
                return JsonResponse({'success': True, 'sheet_types': [], 'total_count': 0})

            paper_types = list(PaperServiceDetails.objects.filter(service__supplier__is_active=True, service__is_active=True).values_list('paper_type', flat=True).distinct().order_by('paper_type'))
            try:
                paper_type_name = paper_types[int(paper_type_id) - 1]
            except (IndexError, ValueError):
                return JsonResponse({'success': False, 'error': 'نوع الورق غير موجود'}, status=404)

            paper_services = PaperServiceDetails.objects.filter(service__supplier=supplier, paper_type=paper_type_name, service__is_active=True).select_related('service')
            sheet_types_data = []
            seen = set()
            for svc in paper_services:
                if svc.sheet_size and svc.sheet_size not in seen:
                    seen.add(svc.sheet_size)
                    sheet_types_data.append({'sheet_type': svc.sheet_size, 'display_name': svc.get_sheet_size_display(), 'sheet_size': svc.sheet_size})
            return JsonResponse({'success': True, 'sheet_types': sheet_types_data,
                                 'supplier': {'id': supplier.id, 'name': supplier.name},
                                 'paper_type': {'id': paper_type_id, 'name': paper_type_name},
                                 'total_count': len(sheet_types_data)})
        except Exception as e:
            return self.handle_exception(e, "GetPaperSheetTypesAPIView.get")


class GetPaperOriginsAPIView(BaseAPIView):
    """
    API لجلب منشأ الورق — يستخدم SupplierService.attributes
    """
    
    def get(self, request):
        try:
            paper_type_id = request.GET.get('paper_type_id')
            supplier_id   = request.GET.get('supplier_id')
            sheet_type    = request.GET.get('sheet_type')
            weight        = request.GET.get('weight')

            if not paper_type_id or not supplier_id:
                return JsonResponse({'success': False, 'error': 'معرف نوع الورق والمورد مطلوبان',
                                     'missing_params': [p for p in ['paper_type_id', 'supplier_id'] if not request.GET.get(p)]}, status=400)

            if HAS_SUPPLIER_SERVICES:
                all_types = sorted(set(
                    s.get('paper_type') for s in SupplierServiceModel.objects.filter(
                        service_type__code='paper', is_active=True
                    ).values_list('attributes', flat=True)
                    if isinstance(s, dict) and s.get('paper_type')
                ))
                try:
                    paper_type_name = all_types[int(paper_type_id) - 1]
                except (IndexError, ValueError):
                    return JsonResponse({'success': False, 'error': 'نوع الورق غير موجود'}, status=404)

                qs = SupplierServiceModel.objects.filter(
                    service_type__code='paper', supplier_id=supplier_id, is_active=True
                )
                origins = set()
                for svc in qs:
                    attrs = svc.attributes
                    if attrs.get('paper_type') != paper_type_name:
                        continue
                    if sheet_type and attrs.get('sheet_size') != sheet_type:
                        continue
                    if weight and str(attrs.get('gsm', '')) != str(weight):
                        continue
                    origin = attrs.get('origin')
                    if origin:
                        origins.add(origin)

                origins_data = [{'origin': o, 'display_name': o, 'code': o, 'name': o} for o in sorted(origins)]
                return JsonResponse({'success': True, 'origins': origins_data,
                                     'paper_type': {'id': paper_type_id, 'name': paper_type_name},
                                     'supplier': {'id': supplier_id, 'name': 'المورد المحدد'},
                                     'total_count': len(origins_data)})

            if not HAS_PAPER_SERVICE_DETAILS:
                return JsonResponse({'success': True, 'origins': [], 'total_count': 0})

            paper_types = list(PaperServiceDetails.objects.filter(service__supplier__is_active=True, service__is_active=True).values_list('paper_type', flat=True).distinct().order_by('paper_type'))
            try:
                paper_type_name = paper_types[int(paper_type_id) - 1]
            except (IndexError, ValueError):
                return JsonResponse({'success': False, 'error': 'نوع الورق غير موجود'}, status=404)

            filters = {'service__supplier_id': supplier_id, 'paper_type': paper_type_name, 'service__is_active': True}
            if sheet_type: filters['sheet_size'] = sheet_type
            if weight:     filters['gsm'] = int(weight)

            code_to_name = {'EG': 'مصر', 'DE': 'ألمانيا', 'CN': 'صيني', 'US': 'أمريكا', 'IT': 'إيطاليا', 'FR': 'فرنسا'}
            origins_data = []
            seen = set()
            for svc in PaperServiceDetails.objects.filter(**filters):
                if svc.country_of_origin and svc.country_of_origin not in seen:
                    seen.add(svc.country_of_origin)
                    name = code_to_name.get(svc.country_of_origin, svc.country_of_origin)
                    origins_data.append({'origin': name, 'display_name': name, 'code': svc.country_of_origin, 'name': name})

            return JsonResponse({'success': True, 'origins': origins_data,
                                 'paper_type': {'id': paper_type_id, 'name': paper_type_name},
                                 'supplier': {'id': supplier_id, 'name': 'المورد المحدد'},
                                 'total_count': len(origins_data)})
        except Exception as e:
            return self.handle_exception(e, "GetPaperOriginsAPIView.get")


class GetPaperPriceAPIView(BaseAPIView):
    """
    API لجلب سعر الورق — يستخدم SupplierService.attributes
    """
    
    def get(self, request):
        try:
            paper_type_id = request.GET.get('paper_type_id')
            supplier_id   = request.GET.get('supplier_id')
            sheet_type    = request.GET.get('sheet_type')
            weight        = request.GET.get('weight')
            origin        = request.GET.get('origin')

            required = ['paper_type_id', 'supplier_id', 'sheet_type', 'weight']
            missing  = [p for p in required if not request.GET.get(p)]
            if missing:
                return JsonResponse({'success': False, 'error': 'معاملات مطلوبة مفقودة',
                                     'missing_params': missing}, status=400)

            if HAS_SUPPLIER_SERVICES:
                all_types = sorted(set(
                    s.get('paper_type') for s in SupplierServiceModel.objects.filter(
                        service_type__code='paper', is_active=True
                    ).values_list('attributes', flat=True)
                    if isinstance(s, dict) and s.get('paper_type')
                ))
                try:
                    paper_type_name = all_types[int(paper_type_id) - 1]
                except (IndexError, ValueError):
                    return JsonResponse({'success': False, 'error': 'نوع الورق غير موجود'}, status=404)

                # البحث عن الخدمة المطابقة
                matched = None
                for svc in SupplierServiceModel.objects.filter(
                    service_type__code='paper', supplier_id=supplier_id, is_active=True
                ):
                    attrs = svc.attributes
                    if attrs.get('paper_type') != paper_type_name:
                        continue
                    if sheet_type and attrs.get('sheet_size') != sheet_type:
                        continue
                    if weight and str(attrs.get('gsm', '')) != str(weight):
                        continue
                    if origin and attrs.get('origin') and attrs.get('origin') != origin:
                        continue
                    matched = svc
                    break

                if matched:
                    price = float(matched.get_price_for_quantity(1))
                    from core.utils import get_default_currency
                    return JsonResponse({
                        'success':       True,
                        'price':         price,
                        'unit_price':    price,
                        'price_per_sheet': price,
                        'currency':      get_default_currency(),
                        'service_id':    matched.id,
                        'service_info':  {
                            'id':              matched.id,
                            'supplier_name':   matched.supplier.name,
                            'paper_type_name': paper_type_name,
                            'sheet_size':      sheet_type,
                            'weight_gsm':      weight,
                            'origin_name':     origin or '',
                            'attributes':      matched.attributes,
                        }
                    })

                return JsonResponse({'success': False, 'error': 'لا توجد خدمة ورق متاحة للمعايير المحددة',
                                     'suggestion': 'أضف خدمة ورق للمورد من صفحة تفاصيل المورد'}, status=404)

            if not HAS_PAPER_SERVICE_DETAILS:
                return JsonResponse({'success': False, 'error': 'لا توجد بيانات أسعار ورق متاحة حالياً',
                                     'suggestion': 'يرجى إضافة خدمات الورق للموردين أولاً'}, status=404)

            # Fallback legacy
            paper_types = list(PaperServiceDetails.objects.filter(service__supplier__is_active=True, service__is_active=True).values_list('paper_type', flat=True).distinct().order_by('paper_type'))
            try:
                paper_type_name = paper_types[int(paper_type_id) - 1]
            except (IndexError, ValueError):
                return JsonResponse({'success': False, 'error': 'نوع الورق غير موجود'}, status=404)

            origin_mapping = {'مصر': 'EG', 'ألمانيا': 'DE', 'صيني': 'CN', 'الصين': 'CN', 'أمريكا': 'US', 'إيطاليا': 'IT', 'فرنسا': 'FR'}
            origin_code = origin_mapping.get(origin, origin) if origin else None

            filters = {'service__supplier_id': supplier_id, 'paper_type': paper_type_name,
                       'sheet_size': sheet_type, 'gsm': int(weight), 'service__is_active': True}
            if origin_code:
                filters['country_of_origin'] = origin_code

            paper_service = PaperServiceDetails.objects.filter(**filters).first()
            if not paper_service:
                return JsonResponse({'success': False, 'error': 'لا توجد خدمة ورق متاحة للمعايير المحددة'}, status=404)

            from core.utils import get_default_currency
            return JsonResponse({
                'success': True,
                'price': float(paper_service.price_per_sheet),
                'unit_price': float(paper_service.price_per_sheet),
                'price_per_sheet': float(paper_service.price_per_sheet),
                'currency': get_default_currency(),
                'service_info': {
                    'id': paper_service.id, 'supplier_name': paper_service.service.supplier.name,
                    'paper_type_name': paper_type_name, 'sheet_size': paper_service.sheet_size,
                    'weight_gsm': paper_service.gsm, 'origin_name': origin or '',
                }
            })
        except Exception as e:
            return self.handle_exception(e, "GetPaperPriceAPIView.get")


class GetPieceSizesAPIView(BaseAPIView):
    """
    API لجلب مقاسات القطع النشطة مع فلترة ذكية
    """
    
    def get(self, request):
        """جلب مقاسات القطع المتاحة مع إمكانية الفلترة حسب مقاس الورق الأساسي"""
        
        try:
            # الحصول على المعاملات
            paper_sheet_type = request.GET.get('paper_sheet_type')
            
            # بناء الاستعلام الأساسي
            piece_sizes = PieceSize.objects.filter(is_active=True)
            
            # فلترة حسب مقاس الورق الأساسي إذا تم تحديده
            if paper_sheet_type:
                # استخراج أبعاد الفرخ من النص (مثل: "70.00x100.00")
                try:
                    sheet_width, sheet_height = paper_sheet_type.split('x')
                    sheet_width = float(sheet_width)
                    sheet_height = float(sheet_height)
                    
                    # فلترة المقاسات التي لها نفس مقاس الورق الأساسي
                    piece_sizes = piece_sizes.filter(
                        paper_type__width=sheet_width,
                        paper_type__height=sheet_height
                    )
                    
                except (ValueError, AttributeError):
                    # في حالة فشل تحليل مقاس الفرخ، لا نطبق الفلتر
                    pass
            
            # ترتيب النتائج
            piece_sizes = piece_sizes.order_by('name')
            
            def format_number(value):
                """تنسيق الأرقام: بدون علامة عشرية للأرقام الصحيحة، مع علامة عشرية للكسور"""
                if value == int(value):
                    return str(int(value))
                else:
                    return str(float(value))
            
            piece_sizes_data = []
            for piece_size in piece_sizes:
                # تنسيق الأبعاد
                width_formatted = format_number(piece_size.width)
                height_formatted = format_number(piece_size.height)
                
                piece_sizes_data.append({
                    'id': piece_size.id,
                    'name': piece_size.name,
                    'width': float(piece_size.width),
                    'height': float(piece_size.height),
                    'width_formatted': width_formatted,
                    'height_formatted': height_formatted,
                    'display_name': f"{piece_size.name} ({width_formatted}×{height_formatted} سم)",
                    'paper_type': piece_size.get_paper_type_display(),
                    'paper_type_id': piece_size.paper_type.id if piece_size.paper_type else None,
                    'pieces_per_sheet': piece_size.pieces_per_sheet,
                    'pieces_per_sheet_display': piece_size.get_pieces_per_sheet_display(),
                    'is_default': piece_size.is_default
                })
            
            # رسائل حالة مختلفة حسب الفلاتر المطبقة
            status_message = ""
            if not paper_sheet_type:
                status_message = "جميع مقاسات القطع"
            else:
                status_message = f"مقاسات القطع المتاحة للورق {paper_sheet_type}"
            
            return JsonResponse({
                'success': True,
                'piece_sizes': piece_sizes_data,
                'total_count': len(piece_sizes_data),
                'filters_applied': {
                    'paper_sheet_type': paper_sheet_type
                },
                'status_message': status_message
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'خطأ في جلب مقاسات القطع: {str(e)}'
            }, status=500)


__all__ = [
    'BaseAPIView', 'CalculateCostAPIView', 'GetMaterialPriceAPIView',
    'GetServicePriceAPIView', 'ValidateOrderAPIView', 'OrderSummaryAPIView',
    'GetClientsAPIView', 'GetProductTypesAPIView', 'GetProductSizesAPIView',
    'GetPrintingSuppliersAPIView', 'GetPressesAPIView', 'GetPressPriceAPIView',
    'GetCTPSuppliersAPIView', 'GetCTPPlatesAPIView', 'GetCTPPriceAPIView',
    'GetPaperTypesAPIView', 'GetPaperSuppliersAPIView', 'GetPaperWeightsAPIView',
    'GetPaperSheetTypesAPIView', 'GetPaperOriginsAPIView', 'GetPaperPriceAPIView',
    'GetPieceSizesAPIView',
    # المرحلة الأولى — APIs خدمات الموردين
    'GetServiceTypesAPIView', 'GetSuppliersByServiceAPIView',
    'GetSupplierServicesAPIView', 'GetServicePriceByIdAPIView',
    # المرحلة الثالثة — ربط التسعير
    'SaveOrderServiceSupplierAPIView',
]


# ================================================================
# APIs خدمات الموردين — المرحلة الأولى
# ================================================================

class GetServiceTypesAPIView(BaseAPIView):
    """
    GET /api/printing/service-types/
    جلب جميع أنواع الخدمات النشطة مع attribute_schema الخاص بكل نوع.
    """

    def get(self, request):
        try:
            if not HAS_SUPPLIER_SERVICES:
                return JsonResponse({'success': True, 'service_types': [], 'total_count': 0})

            category = request.GET.get('category', '')
            qs = ServiceType.objects.filter(is_active=True)
            if category:
                qs = qs.filter(category=category)

            data = [
                {
                    'id':               st.id,
                    'code':             st.code,
                    'name':             st.name,
                    'category':         st.category,
                    'icon':             st.icon,
                    'attribute_schema': st.attribute_schema,
                }
                for st in qs.order_by('order', 'name')
            ]
            return JsonResponse({'success': True, 'service_types': data, 'total_count': len(data)})
        except Exception as e:
            return self.handle_exception(e, 'GetServiceTypesAPIView.get')


class GetSuppliersByServiceAPIView(BaseAPIView):
    """
    GET /api/printing/suppliers-by-service/?service_type=paper
    جلب الموردين الذين يقدمون خدمة من نوع معين.
    """

    def get(self, request):
        try:
            if not HAS_SUPPLIER_SERVICES:
                return JsonResponse({'success': True, 'suppliers': [], 'total_count': 0})

            service_type_code = request.GET.get('service_type', '')
            if not service_type_code:
                return JsonResponse(
                    {'success': False, 'error': _('معامل service_type مطلوب'), 'missing_params': ['service_type']},
                    status=400
                )

            from supplier.services.supplier_service import SupplierService
            suppliers = SupplierService.get_suppliers_by_service_type(service_type_code)

            data = [
                {
                    'id':             s.id,
                    'name':           s.name,
                    'text':           s.name,
                    'phone':          s.phone or '',
                    'contact_person': s.contact_person or '',
                    'is_preferred':   s.is_preferred,
                }
                for s in suppliers
            ]
            return JsonResponse({'success': True, 'suppliers': data, 'total_count': len(data)})
        except Exception as e:
            return self.handle_exception(e, 'GetSuppliersByServiceAPIView.get')


class GetSupplierServicesAPIView(BaseAPIView):
    """
    GET /api/printing/supplier-services/?supplier_id=5&service_type=paper
    جلب الخدمات المتاحة عند مورد معين (مع فلتر اختياري بنوع الخدمة).
    """

    def get(self, request):
        try:
            if not HAS_SUPPLIER_SERVICES:
                return JsonResponse({'success': True, 'services': [], 'total_count': 0})

            supplier_id = request.GET.get('supplier_id')
            if not supplier_id:
                return JsonResponse(
                    {'success': False, 'error': _('معامل supplier_id مطلوب'), 'missing_params': ['supplier_id']},
                    status=400
                )

            service_type_code = request.GET.get('service_type', '')

            from supplier.services.supplier_service import SupplierService
            services = SupplierService.get_supplier_services(supplier_id, service_type_code or None)

            data = []
            for svc in services:
                data.append({
                    'id':           svc.id,
                    'name':         svc.name,
                    'text':         svc.name,
                    'service_type': svc.service_type.code,
                    'base_price':   float(svc.base_price),
                    'setup_cost':   float(svc.setup_cost),
                    'attributes':   svc.attributes,
                })

            return JsonResponse({'success': True, 'services': data, 'total_count': len(data)})
        except Exception as e:
            return self.handle_exception(e, 'GetSupplierServicesAPIView.get')


class GetServicePriceByIdAPIView(BaseAPIView):
    """
    GET /api/printing/service-price/?service_id=12&quantity=1000
    جلب سعر خدمة معينة للكمية المطلوبة (مع دعم الشرائح السعرية).
    """

    def get(self, request):
        try:
            if not HAS_SUPPLIER_SERVICES:
                return JsonResponse(
                    {'success': False, 'error': _('نظام خدمات الموردين غير مفعل بعد')},
                    status=404
                )

            service_id = request.GET.get('service_id')
            if not service_id:
                return JsonResponse(
                    {'success': False, 'error': _('معامل service_id مطلوب'), 'missing_params': ['service_id']},
                    status=400
                )

            try:
                quantity = int(request.GET.get('quantity', 1))
            except (ValueError, TypeError):
                quantity = 1

            from supplier.services.supplier_service import SupplierService
            result = SupplierService.get_service_price(service_id, quantity)

            if result is None:
                return JsonResponse(
                    {'success': False, 'error': _('الخدمة غير موجودة أو غير نشطة')},
                    status=404
                )

            return JsonResponse({
                'success':       True,
                'service_id':    service_id,
                'quantity':      quantity,
                'price':         float(result['price']),
                'unit_price':    float(result['price']),
                'setup_cost':    float(result['setup_cost']),
                'service_name':  result['service_name'],
                'supplier_name': result['supplier_name'],
                'supplier_id':   result['supplier_id'],
                'service_type':  result['service_type'],
                'attributes':    result['attributes'],
                'is_fallback':   result['is_fallback'],
            })
        except Exception as e:
            return self.handle_exception(e, 'GetServicePriceByIdAPIView.get')


# ================================================================
# المرحلة الثالثة — ربط التسعير بخدمات الموردين
# ================================================================

@method_decorator(csrf_exempt, name='dispatch')
class SaveOrderServiceSupplierAPIView(BaseAPIView):
    """
    POST /printing-pricing/api/save-order-service-supplier/
    يحفظ supplier_service FK وsnapshot في OrderService.supplier_info.

    Body JSON:
    {
        "order_service_id": 5,       # اختياري — لو موجود يحدّث
        "order_id": 12,              # مطلوب لو order_service_id غير موجود
        "service_category": "printing",
        "service_name": "طباعة أوفست",
        "supplier_service_id": 3,    # FK لـ SupplierService
        "quantity": 1000,
        "unit_price": 50.00,
        "setup_cost": 20.00
    }
    """

    def post(self, request):
        try:
            data = json.loads(request.body)

            supplier_service_id = data.get('supplier_service_id')
            if not supplier_service_id:
                return JsonResponse({'success': False, 'error': 'supplier_service_id مطلوب'}, status=400)

            if not HAS_SUPPLIER_SERVICES:
                return JsonResponse({'success': False, 'error': 'نظام خدمات الموردين غير مفعل'}, status=400)

            # جلب SupplierService
            try:
                svc = SupplierServiceModel.objects.select_related('supplier', 'service_type').get(
                    id=supplier_service_id, is_active=True
                )
            except SupplierServiceModel.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'خدمة المورد غير موجودة'}, status=404)

            # بناء snapshot
            quantity   = int(data.get('quantity', 1))
            price_used = float(svc.get_price_for_quantity(quantity))
            snapshot   = {
                'supplier_id':      svc.supplier_id,
                'supplier_name':    svc.supplier.name,
                'service_type':     svc.service_type.code,
                'service_name':     svc.name,
                'price_used':       price_used,
                'setup_cost':       float(svc.setup_cost),
                'attributes':       svc.attributes,
                'saved_at':         str(json.dumps(None)),  # placeholder
            }

            from ..models import OrderService, PrintingOrder
            from decimal import Decimal

            order_service_id = data.get('order_service_id')
            if order_service_id:
                # تحديث OrderService موجود
                try:
                    order_svc = OrderService.objects.get(id=order_service_id)
                    order_svc.supplier_service = svc
                    order_svc.supplier_info    = snapshot
                    if data.get('unit_price') is not None:
                        order_svc.unit_price = Decimal(str(data['unit_price']))
                    if data.get('setup_cost') is not None:
                        order_svc.setup_cost = Decimal(str(data['setup_cost']))
                    order_svc.save()
                    return JsonResponse({'success': True, 'order_service_id': order_svc.id,
                                         'message': 'تم تحديث خدمة الطلب بنجاح', 'snapshot': snapshot})
                except OrderService.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'OrderService غير موجود'}, status=404)
            else:
                # إنشاء OrderService جديد
                order_id = data.get('order_id')
                if not order_id:
                    return JsonResponse({'success': False, 'error': 'order_id أو order_service_id مطلوب'}, status=400)
                try:
                    order = PrintingOrder.objects.get(id=order_id)
                except PrintingOrder.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'الطلب غير موجود'}, status=404)

                from ..models.base import PriceUnit
                order_svc = OrderService.objects.create(
                    order            = order,
                    service_category = data.get('service_category', 'other'),
                    service_name     = data.get('service_name', svc.name),
                    quantity         = Decimal(str(data.get('quantity', 1))),
                    unit             = data.get('unit', PriceUnit.PIECE),
                    unit_price       = Decimal(str(data.get('unit_price', price_used))),
                    setup_cost       = Decimal(str(data.get('setup_cost', float(svc.setup_cost)))),
                    supplier_service = svc,
                    supplier_info    = snapshot,
                )
                return JsonResponse({'success': True, 'order_service_id': order_svc.id,
                                     'message': 'تم إنشاء خدمة الطلب بنجاح', 'snapshot': snapshot})

        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'JSON غير صحيح'}, status=400)
        except Exception as e:
            return self.handle_exception(e, 'SaveOrderServiceSupplierAPIView.post')
