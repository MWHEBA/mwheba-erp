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

# استيراد نماذج الورق من النماذج الموجودة (بدون اعتماد على النظام القديم في APIs)
from supplier.models import Supplier, PaperServiceDetails
from printing_pricing.models.settings_models import PaperOrigin, PieceSize


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
    API لجلب المطابع المتاحة
    """
    
    def get(self, request):
        try:
            from supplier.models import Supplier, SupplierServiceTag, OffsetPrintingDetails, DigitalPrintingDetails
            
            # معامل نوع الطلب (اختياري)
            order_type = request.GET.get('order_type', '')
            
            # جلب المطابع النشطة فقط التي لديها ماكينات طباعة
            suppliers_query = Supplier.objects.filter(is_active=True)
            
            # تصفية حسب نوع الطلب إذا تم تحديده
            if order_type == 'offset':
                # جلب فقط المطابع التي لديها ماكينات أوفست
                suppliers_with_offset = []
                for supplier in suppliers_query:
                    offset_count = OffsetPrintingDetails.objects.filter(
                        service__supplier=supplier
                    ).count()
                    if offset_count > 0:
                        suppliers_with_offset.append(supplier)
                suppliers = suppliers_with_offset
            elif order_type == 'digital':
                # جلب فقط المطابع التي لديها ماكينات ديجيتال
                suppliers_with_digital = []
                for supplier in suppliers_query:
                    digital_count = DigitalPrintingDetails.objects.filter(
                        service__supplier=supplier
                    ).count()
                    if digital_count > 0:
                        suppliers_with_digital.append(supplier)
                suppliers = suppliers_with_digital
            else:
                # جلب المطابع التي لديها أي نوع من الماكينات
                suppliers_with_machines = []
                for supplier in suppliers_query:
                    offset_count = OffsetPrintingDetails.objects.filter(
                        service__supplier=supplier
                    ).count()
                    digital_count = DigitalPrintingDetails.objects.filter(
                        service__supplier=supplier
                    ).count()
                    if offset_count > 0 or digital_count > 0:
                        suppliers_with_machines.append(supplier)
                suppliers = suppliers_with_machines
            
            # ترتيب النتائج
            suppliers = sorted(suppliers, key=lambda s: s.name)
            
            results = []
            for supplier in suppliers:
                # إضافة معلومات عن أنواع الماكينات المتاحة
                offset_count = OffsetPrintingDetails.objects.filter(
                    service__supplier=supplier
                ).count()
                digital_count = DigitalPrintingDetails.objects.filter(
                    service__supplier=supplier
                ).count()
                
                # إضافة وصف للماكينات المتاحة
                machine_info = []
                if offset_count > 0:
                    machine_info.append(f"{offset_count} أوفست")
                if digital_count > 0:
                    machine_info.append(f"{digital_count} ديجيتال")
                
                display_name = supplier.name
                if machine_info:
                    display_name += f" ({', '.join(machine_info)})"
                
                results.append({
                    'id': supplier.id,
                    'text': display_name,
                    'name': supplier.name,
                    'contact_person': supplier.contact_person or '',
                    'phone': supplier.phone or '',
                    'email': supplier.email or '',
                    'address': supplier.address or '',
                    'offset_machines': offset_count,
                    'digital_machines': digital_count
                })
            
            return JsonResponse({
                'success': True,
                'suppliers': results,
                'total_count': len(results)
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetPrintingSuppliersAPIView.get")


class GetPressesAPIView(BaseAPIView):
    """
    API لجلب الماكينات المتاحة لدى المطبعة
    """
    
    def get(self, request):
        try:
            supplier_id = request.GET.get('supplier_id')
            order_type = request.GET.get('order_type', '')
            
            if not supplier_id:
                return JsonResponse({
                    'success': False,
                    'error': _('معرف المطبعة مطلوب'),
                    'missing_params': ['supplier_id'],
                    'suggestion': _('حدد المطبعة أولاً')
                }, status=400)
            
            # التحقق من وجود المطبعة
            from supplier.models import Supplier
            try:
                supplier = Supplier.objects.get(id=supplier_id, is_active=True)
            except Supplier.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': _('المطبعة غير موجودة أو غير نشطة'),
                    'supplier_id': supplier_id,
                    'suggestion': _('تأكد من صحة معرف المطبعة')
                }, status=404)
            
            # جلب الماكينات المتاحة لدى هذه المطبعة من قاعدة البيانات
            from supplier.models import OffsetPrintingDetails, DigitalPrintingDetails
            
            presses = []
            
            # جلب ماكينات الأوفست
            offset_machines = OffsetPrintingDetails.objects.filter(
                service__supplier=supplier
            ).select_related('service')
            for machine in offset_machines:
                # استخدام اسم الخدمة الحقيقي إذا كان متاحاً
                if hasattr(machine, 'service') and machine.service and hasattr(machine.service, 'name'):
                    machine_name = machine.service.name
                else:
                    # اسم افتراضي إذا لم يتوفر اسم الخدمة
                    machine_name = f"ماكينة أوفست - {machine.machine_type}" if machine.machine_type else "ماكينة أوفست"
                
                presses.append({
                    'id': f'offset_{machine.id}',
                    'name': machine_name,
                    'type': 'offset',
                    'price_per_1000': float(getattr(machine, 'impression_cost_per_1000', 50.00))
                })
            
            # جلب ماكينات الديجيتال فقط إذا لم يتم تحديد نوع الطلب أو كان ديجيتال
            if not order_type or order_type != 'offset':
                digital_machines = DigitalPrintingDetails.objects.filter(
                    service__supplier=supplier
                ).select_related('service')
                
                for machine in digital_machines:
                    # استخدام اسم الخدمة الحقيقي إذا كان متاحاً
                    if hasattr(machine, 'service') and machine.service and hasattr(machine.service, 'name'):
                        machine_name = machine.service.name
                    else:
                        # اسم افتراضي إذا لم يتوفر اسم الخدمة
                        machine_name = f"ماكينة ديجيتال - {machine.get_machine_type_display()}" if machine.machine_type else "ماكينة ديجيتال"
                    
                    # حساب السعر لكل 1000 (متوسط الأبيض والأسود والملون)
                    price_bw = float(getattr(machine, 'price_per_page_bw', 0.035))
                    price_color = float(getattr(machine, 'price_per_page_color', 0.15))
                    avg_price_per_page = (price_bw + price_color) / 2
                    price_per_1000 = avg_price_per_page * 1000
                    
                    presses.append({
                        'id': f'digital_{machine.id}',
                        'name': machine_name,
                        'type': 'digital',
                        'colors': 4,  # الديجيتال عادة يدعم الألوان الكاملة
                        'price_per_1000': price_per_1000,
                        'price_per_page_bw': price_bw,
                        'price_per_page_color': price_color
                    })
            
            # إذا لم توجد ماكينات، إرجاع قائمة فارغة
            # (لا نحتاج ماكينات افتراضية)
            
            # التصفية تمت مسبقاً عند جلب الماكينات
            
            return JsonResponse({
                'success': True,
                'presses': presses,
                'supplier_info': {
                    'id': supplier.id,
                    'name': supplier.name
                },
                'total_count': len(presses)
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetPressesAPIView.get")


class GetPressPriceAPIView(BaseAPIView):
    """
    API لجلب سعر ماكينة معينة
    """
    
    def get(self, request):
        try:
            press_id = request.GET.get('press_id')
            
            if not press_id:
                return JsonResponse({
                    'success': False,
                    'error': _('معرف الماكينة مطلوب'),
                    'missing_params': ['press_id'],
                    'suggestion': _('حدد الماكينة أولاً')
                }, status=400)
            
            # استخراج معلومات الماكينة من المعرف
            from supplier.models import OffsetPrintingDetails, DigitalPrintingDetails
            
            price_info = None
            
            # تحليل معرف الماكينة لتحديد النوع والـ ID
            if press_id.startswith('offset_'):
                machine_id = press_id.replace('offset_', '')
                try:
                    machine = OffsetPrintingDetails.objects.get(id=machine_id)
                    price_info = {
                        'price_per_1000': float(getattr(machine, 'impression_cost_per_1000', 50.00)),
                        'setup_cost': float(getattr(machine, 'color_calibration_cost', 20.00)),
                        'minimum_quantity': 500,  # الأوفست عادة كميات أكبر
                        'max_colors': getattr(machine, 'max_colors', 4),
                        'sheet_size': getattr(machine, 'sheet_size', 'غير محدد')
                    }
                except OffsetPrintingDetails.DoesNotExist:
                    pass
                    
            elif press_id.startswith('digital_'):
                machine_id = press_id.replace('digital_', '')
                try:
                    machine = DigitalPrintingDetails.objects.get(id=machine_id)
                    # حساب السعر لكل 1000 من أسعار الصفحات
                    price_bw = float(getattr(machine, 'price_per_page_bw', 0.035))
                    price_color = float(getattr(machine, 'price_per_page_color', 0.15))
                    avg_price_per_page = (price_bw + price_color) / 2
                    price_per_1000 = avg_price_per_page * 1000
                    
                    # وقت الإعداد كتكلفة ثابتة
                    setup_time = getattr(machine, 'setup_time_minutes', 5)
                    setup_cost = setup_time * 2.0  # افتراض 2 جنيه/دقيقة
                    
                    price_info = {
                        'price_per_1000': price_per_1000,
                        'setup_cost': setup_cost,
                        'minimum_quantity': 100,  # الديجيتال عادة كميات أقل
                        'price_per_page_bw': price_bw,
                        'price_per_page_color': price_color
                    }
                except DigitalPrintingDetails.DoesNotExist:
                    pass
            
            # إذا لم يتم العثور على الماكينة، استخدم أسعار افتراضية
            if not price_info:
                # تحديد نوع الماكينة من المعرف للسعر الافتراضي
                if 'digital' in press_id.lower():
                    price_info = {
                        'price_per_1000': 35.00,
                        'setup_cost': 10.00,
                        'minimum_quantity': 200
                    }
                else:
                    price_info = {
                        'price_per_1000': 50.00,
                        'setup_cost': 20.00,
                        'minimum_quantity': 500
                    }
            
            return JsonResponse({
                'success': True,
                'press_id': press_id,
                'price_per_1000': price_info['price_per_1000'],
                'price': price_info['price_per_1000'],  # للتوافق
                'unit_price': price_info['price_per_1000'],  # للتوافق
                'setup_cost': price_info['setup_cost'],
                'minimum_quantity': price_info['minimum_quantity']
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetPressPriceAPIView.get")


class GetCTPSuppliersAPIView(BaseAPIView):
    """
    API لجلب موردي الزنكات المتاحين
    """
    
    def get(self, request):
        try:
            from supplier.models import Supplier, PlateServiceDetails
            
            # جلب الموردين النشطين الذين لديهم خدمات زنكات
            suppliers_with_ctp = []
            suppliers_query = Supplier.objects.filter(is_active=True)
            
            for supplier in suppliers_query:
                ctp_count = PlateServiceDetails.objects.filter(
                    service__supplier=supplier
                ).count()
                if ctp_count > 0:
                    suppliers_with_ctp.append(supplier)
            
            # ترتيب النتائج
            suppliers = sorted(suppliers_with_ctp, key=lambda s: s.name)
            
            results = []
            for supplier in suppliers:
                # عدد خدمات الزنكات المتاحة
                ctp_count = PlateServiceDetails.objects.filter(
                    service__supplier=supplier
                ).count()
                
                display_name = f"{supplier.name} ({ctp_count} خدمات زنكات)"
                
                results.append({
                    'id': supplier.id,
                    'text': display_name,
                    'name': supplier.name,
                    'contact_person': supplier.contact_person or '',
                    'phone': supplier.phone or '',
                    'email': supplier.email or '',
                    'address': supplier.address or '',
                    'ctp_services_count': ctp_count
                })
            
            return JsonResponse({
                'success': True,
                'suppliers': results,
                'total_count': len(results)
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetCTPSuppliersAPIView.get")


class GetCTPPlatesAPIView(BaseAPIView):
    """
    API لجلب مقاسات الزنكات المتاحة لدى مورد معين
    """
    
    def get(self, request):
        try:
            supplier_id = request.GET.get('supplier_id')
            
            if not supplier_id:
                return JsonResponse({
                    'success': False,
                    'error': _('معرف المورد مطلوب'),
                    'missing_params': ['supplier_id'],
                    'suggestion': _('حدد المورد أولاً')
                }, status=400)
            
            # التحقق من وجود المورد
            from supplier.models import Supplier, PlateServiceDetails
            try:
                supplier = Supplier.objects.get(id=supplier_id, is_active=True)
            except Supplier.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': _('المورد غير موجود أو غير نشط'),
                    'supplier_id': supplier_id,
                    'suggestion': _('تأكد من صحة معرف المورد')
                }, status=404)
            
            # جلب خدمات الزنكات المتاحة لدى هذا المورد
            from printing_pricing.models.settings_models import PaperSize
            
            ctp_services = PlateServiceDetails.objects.filter(
                service__supplier=supplier
            ).select_related('service')
            
            plates = []
            
            for service in ctp_services:
                # استخدام اسم الخدمة الجاهز مباشرة
                service_name = service.service.name if service.service else "خدمة زنكات"
                
                plates.append({
                    'id': f'ctp_{service.id}',
                    'name': service_name,  # اسم الخدمة الكامل كما هو
                    'service_name': service_name,
                    'plate_type': getattr(service, 'plate_type', 'عادي'),
                    'price_per_plate': float(getattr(service, 'price_per_plate', 15.00))
                })
            
            # إذا لم توجد خدمات، إرجاع قائمة فارغة
            return JsonResponse({
                'success': True,
                'plates': plates,
                'supplier_info': {
                    'id': supplier.id,
                    'name': supplier.name
                },
                'total_count': len(plates)
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetCTPPlatesAPIView.get")


class GetCTPPriceAPIView(BaseAPIView):
    """
    API لجلب سعر زنكة معينة
    """
    
    def get(self, request):
        try:
            plate_id = request.GET.get('plate_id')
            
            if not plate_id:
                return JsonResponse({
                    'success': False,
                    'error': _('معرف الزنكة مطلوب'),
                    'missing_params': ['plate_id'],
                    'suggestion': _('حدد الزنكة أولاً')
                }, status=400)
            
            # استخراج معلومات الزنكة من المعرف
            from supplier.models import PlateServiceDetails
            
            price_info = None
            
            # تحليل معرف الزنكة لتحديد الخدمة
            if plate_id.startswith('ctp_'):
                service_id = plate_id.replace('ctp_', '')
                try:
                    service = PlateServiceDetails.objects.get(id=service_id)
                    price_info = {
                        'price_per_plate': float(getattr(service, 'price_per_plate', 15.00)),
                        'setup_cost': float(getattr(service, 'set_price', 5.00)),  # استخدام set_price من النموذج
                        'minimum_quantity': 1  # افتراضي للزنكات
                    }
                except PlateServiceDetails.DoesNotExist:
                    pass
            
            # إذا لم يتم العثور على الخدمة، استخدم أسعار افتراضية
            if not price_info:
                price_info = {
                    'price_per_plate': 15.00,
                    'setup_cost': 5.00,
                    'minimum_quantity': 1
                }
            
            return JsonResponse({
                'success': True,
                'plate_id': plate_id,
                'price_per_plate': price_info['price_per_plate'],
                'price': price_info['price_per_plate'],  # للتوافق
                'unit_price': price_info['price_per_plate'],  # للتوافق
                'setup_cost': price_info['setup_cost'],
                'minimum_quantity': price_info['minimum_quantity']
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetCTPPriceAPIView.get")


# ==================== APIs الورق ====================

class GetPaperTypesAPIView(BaseAPIView):
    """
    API لجلب أنواع الورق المتاحة من خدمات الموردين
    """
    
    def get(self, request):
        """جلب قائمة أنواع الورق النشطة من خدمات الموردين"""
        try:
            # جلب أنواع الورق المتاحة من خدمات الموردين النشطة
            paper_types = PaperServiceDetails.objects.filter(
                service__supplier__is_active=True,
                service__is_active=True
            ).values_list('paper_type', flat=True).distinct().order_by('paper_type')
            
            types_data = []
            for i, paper_type in enumerate(paper_types, 1):
                if paper_type:  # تجاهل القيم الفارغة
                    types_data.append({
                        'id': i,  # استخدام رقم تسلسلي
                        'name': paper_type,
                        'description': f'نوع ورق {paper_type}',
                        'is_default': i == 1  # الأول افتراضي
                    })
            
            return JsonResponse({
                'success': True,
                'paper_types': types_data,
                'total_count': len(types_data)
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetPaperTypesAPIView.get")


class GetPaperSuppliersAPIView(BaseAPIView):
    """
    API لجلب موردي الورق المتاحين
    """
    
    def get(self, request):
        """جلب قائمة موردي الورق النشطين مع إمكانية الفلترة حسب نوع الورق"""
        try:
            paper_type_id = request.GET.get('paper_type_id')
            
            # بناء الاستعلام الأساسي
            filters = {
                'service__is_active': True,
                'service__supplier__is_active': True
            }
            
            # إضافة فلتر نوع الورق إذا تم تحديده
            if paper_type_id:
                # الحصول على اسم نوع الورق من الرقم التسلسلي
                paper_types = list(PaperServiceDetails.objects.filter(
                    service__supplier__is_active=True,
                    service__is_active=True
                ).values_list('paper_type', flat=True).distinct().order_by('paper_type'))
                
                try:
                    paper_type_name = paper_types[int(paper_type_id) - 1]
                    filters['paper_type'] = paper_type_name
                except (IndexError, ValueError):
                    return JsonResponse({
                        'success': False,
                        'error': 'نوع الورق غير موجود',
                        'paper_type_id': paper_type_id
                    }, status=404)
            
            # جلب الموردين الذين لديهم خدمات ورق (مع الفلتر إذا وُجد)
            paper_services = PaperServiceDetails.objects.filter(**filters).select_related('service__supplier')
            
            # استخراج الموردين الفريدين
            suppliers_dict = {}
            for paper_service in paper_services:
                supplier = paper_service.service.supplier
                if supplier.id not in suppliers_dict:
                    suppliers_dict[supplier.id] = {
                        'id': supplier.id,
                        'name': supplier.name,
                        'contact_info': supplier.contact_person or '',
                        'phone': supplier.phone or '',
                        'email': supplier.email or ''
                    }
            
            suppliers_data = list(suppliers_dict.values())
            suppliers_data.sort(key=lambda x: x['name'])
            
            response_data = {
                'success': True,
                'suppliers': suppliers_data,
                'total_count': len(suppliers_data)
            }
            
            # إضافة معلومات نوع الورق إذا تم الفلترة
            if paper_type_id:
                response_data['filtered_by_paper_type'] = {
                    'id': paper_type_id,
                    'name': paper_type_name
                }
            
            return JsonResponse(response_data)
            
        except Exception as e:
            return self.handle_exception(e, "GetPaperSuppliersAPIView.get")


class GetPaperWeightsAPIView(BaseAPIView):
    """
    API لجلب أوزان الورق حسب نوع الورق من خدمات الموردين
    """
    
    def get(self, request):
        """جلب أوزان الورق المتاحة حسب المعايير المحددة"""
        try:
            paper_type_id = request.GET.get('paper_type_id')
            supplier_id = request.GET.get('supplier_id')
            sheet_type = request.GET.get('sheet_type')
            
            if not paper_type_id:
                return JsonResponse({
                    'success': False,
                    'error': 'معرف نوع الورق مطلوب',
                    'missing_params': ['paper_type_id']
                }, status=400)
            
            # الحصول على اسم نوع الورق من الرقم التسلسلي
            paper_types = list(PaperServiceDetails.objects.filter(
                service__supplier__is_active=True,
                service__is_active=True
            ).values_list('paper_type', flat=True).distinct().order_by('paper_type'))
            
            try:
                paper_type_name = paper_types[int(paper_type_id) - 1]
            except (IndexError, ValueError):
                return JsonResponse({
                    'success': False,
                    'error': 'نوع الورق غير موجود',
                    'paper_type_id': paper_type_id
                }, status=404)
            
            # بناء الفلاتر الأساسية
            filters = {
                'service__supplier__is_active': True,
                'service__is_active': True,
                'paper_type': paper_type_name
            }
            
            # إضافة فلتر المورد إذا تم تحديده
            if supplier_id:
                filters['service__supplier_id'] = supplier_id
            
            # إضافة فلتر مقاس الفرخ إذا تم تحديده
            if sheet_type:
                filters['sheet_size'] = sheet_type
            
            # جلب الأوزان المتاحة حسب المعايير المحددة
            weights = PaperServiceDetails.objects.filter(**filters).values_list('gsm', flat=True).distinct().order_by('gsm')
            
            weights_data = []
            for weight in weights:
                if weight:  # تجاهل القيم الفارغة
                    weights_data.append({
                        'value': str(weight),
                        'display_name': f"{weight} جرام",
                        'name': f"{weight} جرام",
                        'gsm': weight
                    })
            
            return JsonResponse({
                'success': True,
                'weights': weights_data,
                'paper_type': {
                    'id': paper_type_id,
                    'name': paper_type_name
                },
                'total_count': len(weights_data)
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetPaperWeightsAPIView.get")


class GetPaperSheetTypesAPIView(BaseAPIView):
    """
    API لجلب مقاسات الفرخ حسب المورد ونوع الورق
    """
    
    def get(self, request):
        """جلب مقاسات الفرخ المتاحة"""
        try:
            supplier_id = request.GET.get('supplier_id')
            paper_type_id = request.GET.get('paper_type_id')
            
            if not supplier_id or not paper_type_id:
                return JsonResponse({
                    'success': False,
                    'error': 'معرف المورد ونوع الورق مطلوبان',
                    'missing_params': [
                        param for param in ['supplier_id', 'paper_type_id'] 
                        if not request.GET.get(param)
                    ]
                }, status=400)
            
            # الحصول على أسماء نوع الورق والمورد من الأرقام التسلسلية
            paper_types = list(PaperServiceDetails.objects.filter(
                service__supplier__is_active=True,
                service__is_active=True
            ).values_list('paper_type', flat=True).distinct().order_by('paper_type'))
            
            try:
                paper_type_name = paper_types[int(paper_type_id) - 1]
            except (IndexError, ValueError):
                return JsonResponse({
                    'success': False,
                    'error': 'نوع الورق غير موجود',
                    'paper_type_id': paper_type_id
                }, status=404)
            
            # التحقق من وجود المورد
            try:
                supplier = Supplier.objects.get(id=supplier_id, is_active=True)
            except Supplier.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'المورد غير موجود أو غير نشط',
                    'supplier_id': supplier_id
                }, status=404)
            
            # جلب خدمات الورق للمورد ونوع الورق المحدد
            paper_services = PaperServiceDetails.objects.filter(
                service__supplier=supplier,
                paper_type=paper_type_name,
                service__is_active=True
            ).select_related('service')
            
            sheet_types_data = []
            seen_sizes = set()
            
            for service in paper_services:
                # استخدام sheet_size من PaperServiceDetails
                if service.sheet_size and service.sheet_size not in seen_sizes:
                    seen_sizes.add(service.sheet_size)
                    sheet_types_data.append({
                        'sheet_type': service.sheet_size,
                        'display_name': service.get_sheet_size_display(),
                        'sheet_size': service.sheet_size
                    })
            
            return JsonResponse({
                'success': True,
                'sheet_types': sheet_types_data,
                'supplier': {
                    'id': supplier.id,
                    'name': supplier.name
                },
                'paper_type': {
                    'id': paper_type_id,
                    'name': paper_type_name
                },
                'total_count': len(sheet_types_data)
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetPaperSheetTypesAPIView.get")


class GetPaperOriginsAPIView(BaseAPIView):
    """
    API لجلب منشأ الورق حسب المعايير المحددة
    """
    
    def get(self, request):
        """جلب منشأ الورق المتاح"""
        try:
            paper_type_id = request.GET.get('paper_type_id')
            supplier_id = request.GET.get('supplier_id')
            sheet_type = request.GET.get('sheet_type')
            weight = request.GET.get('weight')
            
            if not paper_type_id or not supplier_id:
                return JsonResponse({
                    'success': False,
                    'error': 'معرف نوع الورق والمورد مطلوبان',
                    'missing_params': [
                        param for param in ['paper_type_id', 'supplier_id'] 
                        if not request.GET.get(param)
                    ]
                }, status=400)
            
            # الحصول على اسم نوع الورق من الرقم التسلسلي
            paper_types = list(PaperServiceDetails.objects.filter(
                service__supplier__is_active=True,
                service__is_active=True
            ).values_list('paper_type', flat=True).distinct().order_by('paper_type'))
            
            try:
                paper_type_name = paper_types[int(paper_type_id) - 1]
            except (IndexError, ValueError):
                return JsonResponse({
                    'success': False,
                    'error': 'نوع الورق غير موجود',
                    'paper_type_id': paper_type_id
                }, status=404)
            
            # بناء الاستعلام
            filters = {
                'service__supplier_id': supplier_id,
                'paper_type': paper_type_name,
                'service__is_active': True
            }
            
            if sheet_type:
                filters['sheet_size'] = sheet_type
            
            if weight:
                filters['gsm'] = int(weight)
            
            # جلب خدمات الورق المطابقة
            paper_services = PaperServiceDetails.objects.filter(**filters)
            
            # تحويل رموز المناشئ إلى أسماء كاملة
            code_to_name = {
                'EG': 'مصر',
                'DE': 'ألمانيا', 
                'CN': 'صيني',
                'US': 'أمريكا',
                'IT': 'إيطاليا',
                'FR': 'فرنسا'
            }
            
            origins_data = []
            seen_codes = set()
            
            for service in paper_services:
                if service.country_of_origin and service.country_of_origin not in seen_codes:
                    seen_codes.add(service.country_of_origin)
                    
                    # تحويل الرمز إلى اسم كامل
                    origin_name = code_to_name.get(service.country_of_origin, service.country_of_origin)
                    
                    origins_data.append({
                        'origin': origin_name,  # استخدام الاسم الكامل كقيمة
                        'display_name': origin_name,  # عرض الاسم الكامل
                        'code': service.country_of_origin,  # الرمز المختصر
                        'name': origin_name  # الاسم الكامل
                    })
            
            return JsonResponse({
                'success': True,
                'origins': origins_data,
                'paper_type': {
                    'id': paper_type_id,
                    'name': paper_type_name
                },
                'supplier': {
                    'id': supplier_id,
                    'name': 'المورد المحدد'
                },
                'total_count': len(origins_data)
            })
            
        except Exception as e:
            return self.handle_exception(e, "GetPaperOriginsAPIView.get")


class GetPaperPriceAPIView(BaseAPIView):
    """
    API لجلب سعر الورق حسب المعايير المحددة
    """
    
    def get(self, request):
        """جلب سعر الورق"""
        try:
            paper_type_id = request.GET.get('paper_type_id')
            supplier_id = request.GET.get('supplier_id')
            sheet_type = request.GET.get('sheet_type')
            weight = request.GET.get('weight')
            origin = request.GET.get('origin')
            
            required_params = ['paper_type_id', 'supplier_id', 'sheet_type', 'weight', 'origin']
            missing_params = [param for param in required_params if not request.GET.get(param)]
            
            if missing_params:
                return JsonResponse({
                    'success': False,
                    'error': 'معاملات مطلوبة مفقودة',
                    'missing_params': missing_params,
                    'required_params': required_params
                }, status=400)
            
            
            # الحصول على اسم نوع الورق من الرقم التسلسلي
            paper_types = list(PaperServiceDetails.objects.filter(
                service__supplier__is_active=True,
                service__is_active=True
            ).values_list('paper_type', flat=True).distinct().order_by('paper_type'))
            
            try:
                paper_type_name = paper_types[int(paper_type_id) - 1]
            except (IndexError, ValueError):
                return JsonResponse({
                    'success': False,
                    'error': 'نوع الورق غير موجود',
                    'paper_type_id': paper_type_id
                }, status=404)
            
            # تحويل اسم المنشأ إلى رمز للبحث في قاعدة البيانات
            origin_mapping = {
                'مصر': 'EG',
                'ألمانيا': 'DE', 
                'صيني': 'CN',
                'الصين': 'CN',
                'أمريكا': 'US',
                'إيطاليا': 'IT',
                'فرنسا': 'FR'
            }
            
            origin_code = origin_mapping.get(origin, origin)
            
            # بناء الاستعلام
            filters = {
                'service__supplier_id': supplier_id,
                'paper_type': paper_type_name,
                'sheet_size': sheet_type,
                'gsm': int(weight),
                'country_of_origin': origin_code,  # استخدام الرمز
                'service__is_active': True
            }
            
            # البحث عن خدمة الورق المطابقة
            paper_service = PaperServiceDetails.objects.filter(**filters).first()
            
            if not paper_service:
                return JsonResponse({
                    'success': False,
                    'error': 'لا توجد خدمة ورق متاحة للمعايير المحددة',
                    'search_criteria': {
                        'paper_type_id': paper_type_id,
                        'supplier_id': supplier_id,
                        'sheet_type': sheet_type,
                        'weight': weight,
                        'origin': origin
                    },
                    'suggestion': 'تأكد من صحة جميع المعايير المحددة'
                }, status=404)
            
            return JsonResponse({
                'success': True,
                'price': float(paper_service.price_per_sheet),
                'unit_price': float(paper_service.price_per_sheet),
                'price_per_sheet': float(paper_service.price_per_sheet),
                'currency': 'EGP',
                'service_info': {
                    'id': paper_service.id,
                    'supplier_name': paper_service.service.supplier.name,
                    'paper_type_name': paper_type_name,
                    'sheet_size': paper_service.sheet_size,
                    'weight_gsm': paper_service.gsm,
                    'origin_name': origin  # الاسم الكامل المرسل من المستخدم
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
    'GetPieceSizesAPIView'
]
