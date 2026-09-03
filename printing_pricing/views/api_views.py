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
from ..services import PrintingCalculationEngine

from supplier.models import Supplier
from printing_pricing.models import PaperOrigin, PieceSize, PaperWeight, PaperType, PaperSize

# تحميل نماذج خدمات الموردين — متاحة بعد المرحلة الأولى
try:
    from supplier.models import ServiceType, SupplierService as SupplierServiceModel
    HAS_SUPPLIER_SERVICES = True
except ImportError:
    ServiceType = None
    SupplierServiceModel = None
    HAS_SUPPLIER_SERVICES = False




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
    
    def has_order_permission(self, request, order):
        """التحقق من صلاحية الوصول لطلب معين لمنع ثغرات IDOR"""
        if request.user.is_superuser or getattr(request.user, 'is_staff', False):
            return True
        return order.created_by == request.user
    
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
class LivePricingCalculateAPIView(BaseAPIView):
    """
    API الحساب اللحظي الموحد لتسعير المطبوعات (Single Source of Truth)
    يستدعي PrintingCalculationEngine ويرجع هيكل النتائج الكامل بالجنيه المصري في أقل من 3ms.
    """
    def post(self, request):
        try:
            if request.content_type and 'application/json' in request.content_type:
                try:
                    payload = json.loads(request.body)
                except Exception:
                    payload = {}
            else:
                payload = request.POST.dict()

            from ..services import PrintingCalculationEngine
            result = PrintingCalculationEngine.calculate(payload)
            return JsonResponse(result)
        except Exception as e:
            return self.handle_exception(e, "LivePricingCalculateAPIView.post")




@method_decorator(csrf_exempt, name='dispatch')
class OrderSummaryAPIView(BaseAPIView):
    """
    API ملخص الطلب
    """
    
    def get(self, request, order_id):
        """جلب ملخص شامل للطلب"""
        try:
            order = get_object_or_404(PrintingOrder, pk=order_id, is_active=True)
            
            # التحقق من الصلاحية (IDOR)
            if not self.has_order_permission(request, order):
                return JsonResponse({
                    'success': False,
                    'error': _('غير مصرح لك بإجراء هذه العملية على هذا الطلب'),
                    'error_code': 'FORBIDDEN'
                }, status=403)
            
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


class GetCustomersAPIView(BaseAPIView):
    """
    API لجلب قائمة العملاء للـ Select2
    """
    
    def get(self, request):
        try:
            from customer.models import Customer
            
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
            customers = queryset[start:end]
            
            # تحويل البيانات لصيغة Select2
            results = []
            for customer in customers:
                # بناء النص المعروض بطريقة واضحة ومنظمة
                display_parts = []
                
                # إضافة الكود إذا وُجد
                if customer.code:
                    display_parts.append(f"[{customer.code}]")
                
                # إضافة اسم العميل
                display_parts.append(customer.name)
                
                # إضافة اسم الشركة إذا وُجد ومختلف عن اسم العميل
                if customer.company_name and customer.company_name != customer.name:
                    display_parts.append(f"- {customer.company_name}")
                
                # دمج الأجزاء
                display_name = " ".join(display_parts)
                
                results.append({
                    'id': customer.id,
                    'text': display_name,
                    'name': customer.name,
                    'company_name': customer.company_name or '',
                    'code': customer.code,
                    'phone': customer.phone_primary or customer.phone or '',
                    'email': customer.email or ''
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
            return self.handle_exception(e, "GetCustomersAPIView.get")


class GetProductTypesAPIView(BaseAPIView):
    """
    API لجلب أنواع المنتجات
    """
    
    def get(self, request):
        try:
            from printing_pricing.models import ProductType
            
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
            from printing_pricing.models import ProductSize
            
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
                    price = float(svc.get_price_for_quantity(1) or svc.base_price)
                    attrs = svc.attributes or {}
                    
                    # استخراج مقاس الماكينة ومقاس السلندر
                    sheet_size = attrs.get('sheet_size')
                    if not sheet_size:
                        if '100' in svc.name or 'فرخ كامل' in svc.name:
                            sheet_size = '70x100'
                        elif '70' in svc.name or 'نصف فرخ' in svc.name:
                            sheet_size = '50x70'
                        elif '50' in svc.name or 'ربع فرخ' in svc.name:
                            sheet_size = '35x50'
                        else:
                            sheet_size = '50x70'

                    max_colors = int(attrs.get('max_colors') or (4 if '4' in svc.name else 2))
                    setup_cost = float(svc.setup_cost) if svc.setup_cost else (200.0 if svc_type == 'offset' else 30.0)
                    price_bw = float(attrs.get('price_per_page_bw') or 0.80)
                    price_color = float(attrs.get('price_per_page_color') or (price if price > 0 else 2.50))

                    presses.append({
                        'id':                   f'{svc_type}_{svc.id}',
                        'name':                 svc.name,
                        'type':                 svc_type,
                        'bed_size':             sheet_size,
                        'sheet_size':           sheet_size,
                        'max_colors':           max_colors,
                        'price_per_1000':       price,
                        'setup_cost':           setup_cost,
                        'price_per_page_bw':    price_bw,
                        'price_per_page_color': price_color,
                        'attributes':           attrs,
                        'service_id':           svc.id,
                    })

            return JsonResponse({
                'success': True, 
                'presses': presses,
                'supplier_info': {'id': supplier.id, 'name': supplier.name}, 
                'total_count': len(presses)
            })
        except Exception as e:
            return self.handle_exception(e, "GetPressesAPIView.get")



# ==================== APIs الورق ====================

class GetPaperTypesAPIView(BaseAPIView):
    """
    API لجلب أنواع الورق — يدعم الفلترة حسب مورد الورق (supplier_id) مع إرجاع معرفات نموذج PaperType الحقيقية
    """
    
    def get(self, request):
        try:
            supplier_id = request.GET.get('supplier_id')
            
            # جلب كل أنواع الورق النشطة من نموذج الإعدادات كمرجع أصلي
            all_paper_types = PaperType.objects.filter(is_active=True).order_by('name')
            
            supplier_paper_type_names = set()
            if supplier_id and HAS_SUPPLIER_SERVICES:
                for svc in SupplierServiceModel.objects.filter(
                    service_type__code='paper', supplier_id=supplier_id, is_active=True
                ).values_list('attributes', flat=True):
                    if isinstance(svc, dict):
                        pt = svc.get('paper_type')
                        if pt:
                            supplier_paper_type_names.add(str(pt).strip())

            types_data = []
            for pt in all_paper_types:
                # التحقق من توفر هذا النوع لدى المورد المختار
                is_available = True
                if supplier_id:
                    is_available = any(
                        s_name.lower() in pt.name.lower() or pt.name.lower() in s_name.lower()
                        for s_name in supplier_paper_type_names
                    ) if supplier_paper_type_names else False

                types_data.append({
                    'id': pt.id,
                    'name': pt.name,
                    'description': pt.description or f'نوع ورق {pt.name}',
                    'override_sheets_per_pack': pt.override_sheets_per_pack or '',
                    'is_default': pt.is_default,
                    'is_available_with_supplier': is_available,
                })

            # ترتيب القائمة بحيث تظهر الخامات المتوفرة لدى المورد في البداية
            if supplier_id and supplier_paper_type_names:
                types_data.sort(key=lambda x: (not x['is_available_with_supplier'], x['name']))

            return JsonResponse({
                'success': True,
                'paper_types': types_data,
                'total_count': len(types_data),
                'supplier_id': supplier_id
            })
        except Exception as e:
            return self.handle_exception(e, "GetPaperTypesAPIView.get")


class GetPaperSuppliersAPIView(BaseAPIView):
    """
    API لجلب موردي الورق — يدعم الفلترة حسب نوع الورق المختار وترشيح الموردين الذين يوفرونه
    """
    
    def get(self, request):
        try:
            paper_type_id = request.GET.get('paper_type_id')
            
            # جلب كل موردي الورق النشطين
            paper_suppliers = Supplier.objects.filter(
                is_active=True,
                services__service_type__code='paper',
                services__is_active=True
            ).distinct().order_by('name')
            
            if not paper_suppliers.exists():
                paper_suppliers = Supplier.objects.filter(is_active=True).order_by('name')

            paper_type_name = ''
            if paper_type_id:
                try:
                    pt_obj = PaperType.objects.filter(id=int(paper_type_id)).first()
                    if pt_obj:
                        paper_type_name = pt_obj.name
                except (ValueError, TypeError):
                    paper_type_name = str(paper_type_id)

            suppliers_data = []
            for s in paper_suppliers:
                is_available = True
                if paper_type_name and HAS_SUPPLIER_SERVICES:
                    matched = SupplierServiceModel.objects.filter(
                        service_type__code='paper',
                        supplier_id=s.id,
                        is_active=True
                    )
                    has_type = False
                    for svc in matched:
                        attrs = svc.attributes if isinstance(svc.attributes, dict) else {}
                        pt = attrs.get('paper_type', '')
                        if pt and (paper_type_name.lower() in str(pt).lower() or str(pt).lower() in paper_type_name.lower()):
                            has_type = True
                            break
                        if paper_type_name.lower() in svc.name.lower():
                            has_type = True
                            break
                    is_available = has_type

                suppliers_data.append({
                    'id': s.id,
                    'name': s.name,
                    'contact_info': getattr(s, 'contact_person', '') or '',
                    'phone': getattr(s, 'phone', '') or '',
                    'email': getattr(s, 'email', '') or '',
                    'is_available_for_paper': is_available,
                })

            if paper_type_name:
                suppliers_data.sort(key=lambda x: (not x['is_available_for_paper'], x['name']))

            return JsonResponse({
                'success': True,
                'suppliers': suppliers_data,
                'total_count': len(suppliers_data),
                'paper_type': paper_type_name
            })
        except Exception as e:
            return self.handle_exception(e, "GetPaperSuppliersAPIView.get")


class GetPaperWeightsAPIView(BaseAPIView):
    """
    API لجلب أوزان الورق — فلترة شلالية بناءً على المورد ونوع الورق ومقاس الفرخ
    """
    
    def get(self, request):
        try:
            paper_type_id = request.GET.get('paper_type_id')
            supplier_id   = request.GET.get('supplier_id')
            sheet_size    = request.GET.get('sheet_size')

            all_weights = PaperWeight.objects.filter(is_active=True).order_by('gsm')

            if not paper_type_id and not supplier_id:
                weights_data = [{
                    'id': w.id,
                    'value': str(w.gsm),
                    'gsm': w.gsm,
                    'name': w.name,
                    'display_name': f"{w.name} ({w.gsm} جم)",
                    'sheets_per_pack': w.sheets_per_pack,
                    'is_default': w.is_default,
                } for w in all_weights]
                return JsonResponse({'success': True, 'weights': weights_data, 'total_count': len(weights_data)})

            paper_type_name = ''
            if paper_type_id:
                try:
                    pt_obj = PaperType.objects.filter(id=int(paper_type_id)).first()
                    if pt_obj:
                        paper_type_name = pt_obj.name
                except (ValueError, TypeError):
                    paper_type_name = str(paper_type_id)

            available_gsms = set()
            if HAS_SUPPLIER_SERVICES and supplier_id:
                qs = SupplierServiceModel.objects.filter(
                    service_type__code='paper', supplier_id=supplier_id, is_active=True
                )
                for svc in qs:
                    attrs = svc.attributes if isinstance(svc.attributes, dict) else {}
                    pt = str(attrs.get('paper_type', ''))
                    if paper_type_name and not (paper_type_name.lower() in pt.lower() or pt.lower() in paper_type_name.lower()):
                        continue
                    if sheet_size:
                        svc_sheet = str(attrs.get('sheet_size', ''))
                        if sheet_size not in svc_sheet and svc_sheet not in sheet_size:
                            import re
                            req_dims = set(re.findall(r'\d+', sheet_size))
                            svc_dims = set(re.findall(r'\d+', svc_sheet))
                            if req_dims and svc_dims and not (req_dims & svc_dims):
                                continue
                    gsm_val = attrs.get('gsm')
                    if gsm_val:
                        try:
                            available_gsms.add(int(gsm_val))
                        except (ValueError, TypeError):
                            pass

            if available_gsms:
                filtered_weights = all_weights.filter(gsm__in=available_gsms)
                if not filtered_weights.exists():
                    filtered_weights = all_weights
            else:
                filtered_weights = all_weights

            weights_data = [{
                'id': w.id,
                'value': str(w.gsm),
                'gsm': w.gsm,
                'name': w.name,
                'display_name': f"{w.name} ({w.gsm} جم)",
                'sheets_per_pack': w.sheets_per_pack,
                'is_default': w.is_default,
                'is_available_with_supplier': w.gsm in available_gsms if available_gsms else True
            } for w in filtered_weights]

            return JsonResponse({
                'success': True,
                'weights': weights_data,
                'total_count': len(weights_data)
            })
        except Exception as e:
            return self.handle_exception(e, "GetPaperWeightsAPIView.get")


class GetPaperSheetTypesAPIView(BaseAPIView):
    """
    API لجلب مقاسات الفرخ — مخصصة حصراً حسب المورد ونوع الورق المحددين
    """
    
    def get(self, request):
        try:
            supplier_id   = request.GET.get('supplier_id')
            paper_type_id = request.GET.get('paper_type_id')
            paper_source  = request.GET.get('paper_source')

            all_sizes = PaperSize.objects.filter(is_active=True).order_by('name')

            # لو مصدر الورق من المخزن أو توريد عميل، نرجع المقاسات القياسية فوراً
            if paper_source in ['warehouse', 'customer_supplied']:
                sheet_types_data = [{
                    'id': ps.id,
                    'sheet_type': ps.name,
                    'display_name': f"{ps.name} ({float(ps.width):.0f}×{float(ps.height):.0f} سم)",
                    'sheet_size': ps.name,
                    'width': float(ps.width),
                    'height': float(ps.height),
                } for ps in all_sizes]
                return JsonResponse({'success': True, 'sheet_types': sheet_types_data, 'total_count': len(sheet_types_data)})

            # شرط ملء المورد ونوع الورق معاً
            if not supplier_id or not paper_type_id:
                return JsonResponse({
                    'success': True,
                    'requires_supplier_and_paper': True,
                    'sheet_types': [],
                    'total_count': 0,
                    'message': 'يرجى اختيار نوع الورق ومورد الورق أولاً'
                })

            paper_type_name = ''
            try:
                pt_obj = PaperType.objects.filter(id=int(paper_type_id)).first()
                if pt_obj:
                    paper_type_name = pt_obj.name
            except (ValueError, TypeError):
                paper_type_name = str(paper_type_id)

            available_sheet_names = set()
            if HAS_SUPPLIER_SERVICES:
                qs = SupplierServiceModel.objects.filter(
                    service_type__code='paper', supplier_id=supplier_id, is_active=True
                )
                for svc in qs:
                    attrs = svc.attributes if isinstance(svc.attributes, dict) else {}
                    pt = str(attrs.get('paper_type', ''))
                    if paper_type_name and not (paper_type_name.lower() in pt.lower() or pt.lower() in paper_type_name.lower()):
                        continue
                    s_size = attrs.get('sheet_size')
                    if s_size:
                        available_sheet_names.add(str(s_size).strip())

            sheet_types_data = []
            if available_sheet_names:
                for s_name in sorted(available_sheet_names):
                    matched_size = None
                    import re
                    dims = re.findall(r'\d+', s_name)
                    if len(dims) >= 2:
                        d1, d2 = float(dims[0]), float(dims[1])
                        matched_size = all_sizes.filter(
                            models.Q(width=d1, height=d2) | models.Q(width=d2, height=d1)
                        ).first()

                    w = float(matched_size.width) if matched_size else 70.0
                    h = float(matched_size.height) if matched_size else 100.0
                    disp_name = matched_size.name if matched_size else s_name

                    sheet_types_data.append({
                        'id': matched_size.id if matched_size else s_name,
                        'sheet_type': s_name,
                        'display_name': f"{disp_name} ({w:.0f}×{h:.0f} سم)",
                        'sheet_size': s_name,
                        'width': w,
                        'height': h,
                    })

            # Fallback لو المورد مسجل بدون مقاسات تفصيلية
            if not sheet_types_data:
                sheet_types_data = [{
                    'id': ps.id,
                    'sheet_type': ps.name,
                    'display_name': f"{ps.name} ({float(ps.width):.0f}×{float(ps.height):.0f} سم)",
                    'sheet_size': ps.name,
                    'width': float(ps.width),
                    'height': float(ps.height),
                } for ps in all_sizes]

            return JsonResponse({
                'success': True,
                'sheet_types': sheet_types_data,
                'total_count': len(sheet_types_data)
            })
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

            paper_type_name = ''
            try:
                pt_obj = PaperType.objects.filter(id=int(paper_type_id)).first()
                if pt_obj:
                    paper_type_name = pt_obj.name
            except (ValueError, TypeError):
                paper_type_name = str(paper_type_id)

            if HAS_SUPPLIER_SERVICES:
                if not paper_type_name:
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
                    attrs = svc.attributes if isinstance(svc.attributes, dict) else {}
                    pt = str(attrs.get('paper_type', ''))
                    if paper_type_name and not (paper_type_name.lower() in pt.lower() or pt.lower() in paper_type_name.lower()):
                        continue
                    if sheet_type:
                        svc_sheet = str(attrs.get('sheet_size', ''))
                        if sheet_type not in svc_sheet and svc_sheet not in sheet_type:
                            import re
                            req_dims = set(re.findall(r'\d+', sheet_type))
                            svc_dims = set(re.findall(r'\d+', svc_sheet))
                            if req_dims and svc_dims and not (req_dims & svc_dims):
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

            return JsonResponse({'success': True, 'origins': [], 'total_count': 0})
        except Exception as e:
            return self.handle_exception(e, "GetPaperOriginsAPIView.get")


class GetPaperPriceAPIView(BaseAPIView):
    """
    API لجلب سعر الورق — يستخدم SupplierService.attributes مع مطابقة الأبعاد والمنشأ والعملة
    """
    
    def get(self, request):
        try:
            paper_type_id = request.GET.get('paper_type_id')
            supplier_id   = request.GET.get('supplier_id')
            sheet_type    = request.GET.get('sheet_type') or request.GET.get('sheet_size')
            weight        = request.GET.get('weight')
            origin        = request.GET.get('origin')

            missing = []
            if not paper_type_id: missing.append('paper_type_id')
            if not supplier_id: missing.append('supplier_id')
            if not sheet_type: missing.append('sheet_size')
            if not weight: missing.append('weight')
            if missing:
                return JsonResponse({'success': False, 'error': 'معاملات مطلوبة مفقودة',
                                     'missing_params': missing}, status=400)

            paper_type_name = ''
            pt_obj = None
            try:
                pt_obj = PaperType.objects.filter(id=int(paper_type_id)).first()
                if pt_obj:
                    paper_type_name = pt_obj.name
            except (ValueError, TypeError):
                paper_type_name = str(paper_type_id)

            if HAS_SUPPLIER_SERVICES:
                if not paper_type_name and paper_type_id:
                    # محاولة استخراج الاسم مباشرة من خدمات المورد بالمعرف
                    svc_by_id = SupplierServiceModel.objects.filter(id=paper_type_id).first()
                    if svc_by_id:
                        paper_type_name = svc_by_id.name

                # البحث عن الخدمة المطابقة في خامات المورد
                matched = None
                for svc in SupplierServiceModel.objects.filter(
                    service_type__code='paper', supplier_id=supplier_id, is_active=True
                ):
                    attrs = svc.attributes if isinstance(svc.attributes, dict) else {}
                    pt = str(attrs.get('paper_type', ''))
                    # مطابقة نوع الورق بالاسم أو السمة
                    if paper_type_name:
                        p_lower = paper_type_name.lower()
                        if not (p_lower in pt.lower() or pt.lower() in p_lower or p_lower in svc.name.lower()):
                            continue
                    if sheet_type:
                        svc_sheet = str(attrs.get('sheet_size', ''))
                        if sheet_type not in svc_sheet and svc_sheet not in sheet_type:
                            import re
                            req_dims = set(re.findall(r'\d+', sheet_type))
                            svc_dims = set(re.findall(r'\d+', svc_sheet))
                            if req_dims and svc_dims and not (req_dims & svc_dims):
                                continue
                    if weight and str(attrs.get('gsm', '')) != str(weight):
                        continue
                    if origin and attrs.get('origin') and attrs.get('origin') != origin:
                        continue
                    matched = svc
                    break

                if matched:
                    # حساب سعر الفرخ الفعلي بالمعادلة الصناعية (سواء كان التسعير بالفرخ، الرزمة، أو الطن)
                    width_val, height_val = None, None
                    if sheet_type:
                        import re
                        dims = re.findall(r'\d+', str(sheet_type))
                        if len(dims) >= 2:
                            width_val, height_val = float(dims[0]), float(dims[1])

                    sheet_price = float(matched.get_effective_sheet_price(
                        width_cm=width_val,
                        height_cm=height_val,
                        gsm=weight
                    ))
                    from core.utils import get_default_currency
                    detected_origin = matched.attributes.get('origin', '') if isinstance(matched.attributes, dict) else ''
                    currency_code = matched.currency.code if matched.currency else get_default_currency()

                    return JsonResponse({
                        'success':         True,
                        'price':           sheet_price,
                        'unit_price':      sheet_price,
                        'price_per_sheet': sheet_price,
                        'pricing_formula': matched.pricing_formula,
                        'origin':          detected_origin or origin or '',
                        'currency':        currency_code,
                        'service_id':      matched.id,
                        'service_info':    {
                            'id':              matched.id,
                            'supplier_name':   matched.supplier.name,
                            'paper_type_name': paper_type_name or matched.name,
                            'sheet_size':      sheet_type,
                            'weight_gsm':      weight,
                            'origin_name':     detected_origin or origin or '',
                            'attributes':      matched.attributes,
                        }
                    })

                return JsonResponse({'success': False, 'error': 'لا توجد خدمة ورق متاحة للمعايير المحددة',
                                     'suggestion': 'أضف خدمة ورق للمورد من صفحة تفاصيل المورد'}, status=404)


            return JsonResponse({'success': False, 'error': 'لا توجد بيانات أسعار ورق متاحة حالياً',
                                 'suggestion': 'يرجى إضافة خدمات الورق للموردين أولاً'}, status=404)
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
    'BaseAPIView', 'LivePricingCalculateAPIView',
    'OrderSummaryAPIView', 'GetCustomersAPIView', 'CustomerInfoAPIView',
    'GetProductTypesAPIView', 'GetProductSizesAPIView',
    'GetPressesAPIView',
    'GetPaperTypesAPIView', 'GetPaperSuppliersAPIView', 'GetPaperWeightsAPIView',
    'GetPaperSheetTypesAPIView', 'GetPaperOriginsAPIView', 'GetPaperPriceAPIView',
    'GetPieceSizesAPIView',
    'GetServiceTypesAPIView', 'GetSuppliersByServiceAPIView',
    'GetSupplierServicesAPIView', 'GetServicePriceByIdAPIView',
    'SaveOrderServiceSupplierAPIView',
    'BulkPriceUpdateAPIView', 'GenerateVendorPOsAPIView',
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
                    # التحقق من الصلاحية (IDOR)
                    if not self.has_order_permission(request, order_svc.order):
                        return JsonResponse({
                            'success': False,
                            'error': _('غير مصرح لك بتعديل هذا الطلب'),
                            'error_code': 'FORBIDDEN'
                        }, status=403)
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
                    # التحقق من الصلاحية (IDOR)
                    if not self.has_order_permission(request, order):
                        return JsonResponse({
                            'success': False,
                            'error': _('غير مصرح لك بإضافة خدمات لهذا الطلب'),
                            'error_code': 'FORBIDDEN'
                        }, status=403)
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


class CustomerInfoAPIView(BaseAPIView):
    """
    API جلب معلومات العميل وتصنيفه وهامش ربحه والذاكرة السعرية فورياً (<15ms)
    """
    def get(self, request, customer_id):
        try:
            from customer.models import Customer
            customer = get_object_or_404(Customer, pk=customer_id, is_active=True)
            
            customer_type = getattr(customer, 'customer_type', 'individual')
            
            # تحديد فئة العميل وهامش الربح الافتراضي
            if customer_type == 'individual':
                category = 'retail'
                default_profit_margin = 35.0
            elif customer_type in ('company', 'government'):
                category = 'corporate'
                default_profit_margin = 25.0
            else:
                category = 'b2b_trade'
                default_profit_margin = 15.0
                
            # ذاكرة الأسعار لآخر 5 طلبات لهذا العميل
            past_orders = PrintingOrder.objects.filter(
                customer=customer,
                is_active=True
            ).exclude(final_price__isnull=True).order_by('-created_at')[:5]
            
            price_memory = []
            for po in past_orders:
                price_memory.append({
                    'order_number': po.order_number,
                    'title': po.title,
                    'order_type': po.get_order_type_display() if hasattr(po, 'get_order_type_display') else po.order_type,
                    'quantity': po.quantity,
                    'final_price': float(po.final_price or 0),
                    'unit_price': float(round((po.final_price or 0) / (po.quantity or 1), 2)),
                    'date': po.created_at.strftime('%Y-%m-%d')
                })
                
            return JsonResponse({
                'success': True,
                'customer_id': customer.id,
                'customer_name': customer.name,
                'customer_type': customer_type,
                'category': category,
                'default_profit_margin': default_profit_margin,
                'credit_limit': float(getattr(customer, 'credit_limit', 0) or 0),
                'balance': float(getattr(customer, 'balance', 0) or 0),
                'currency_code': customer.default_currency.code if getattr(customer, 'default_currency', None) else 'EGP',
                'price_memory': price_memory
            })
        except Exception as e:
            return self.handle_exception(e, "CustomerInfoAPIView")


class BulkPriceUpdateAPIView(BaseAPIView):
    """
    API لتحديث أسعار خدمات الموردين بشكل مجمع
    """
    def post(self, request):
        try:
            data = json.loads(request.body) if request.body else {}
            updates = data.get('updates', [])
            from ..services import BulkPriceUpdaterService
            res = BulkPriceUpdaterService.bulk_update_supplier_services(updates, user=request.user)
            return JsonResponse(res)
        except Exception as e:
            return self.handle_exception(e, "BulkPriceUpdateAPIView.post")


class GenerateVendorPOsAPIView(BaseAPIView):
    """
    API لتوليد أوامر الشراء المجمعة للموردين والورش
    """
    def post(self, request, order_id):
        try:
            order = get_object_or_404(PrintingOrder, pk=order_id, is_active=True)
            if not self.has_order_permission(request, order):
                return JsonResponse({'success': False, 'error': _('غير مصرح لك بإصدار أوامر الشراء')}, status=403)

            data = json.loads(request.body) if request.body else {}
            override_reason = data.get('override_reason', '')
            
            from ..services import ProcurementBridgeService
            pos = ProcurementBridgeService.generate_vendor_purchase_orders(
                order=order,
                gated=False,
                override_reason=override_reason,
                user=request.user
            )

            return JsonResponse({
                'success': True,
                'message': _('تم إصدار أوامر الشراء بنجاح'),
                'pos_count': len(pos),
                'po_ids': [p.pk for p in pos]
            })
        except Exception as e:
            return self.handle_exception(e, "GenerateVendorPOsAPIView.post")


class ApprovedOrdersAPIView(BaseAPIView):
    """
    API جلب طلبات التسعير المعتمدة لربطها بشاشات المبيعات وعروض الأسعار
    """
    def get(self, request):
        try:
            customer_id = request.GET.get('customer_id')
            qs = PrintingOrder.objects.filter(status='approved', is_active=True).select_related('customer')
            if customer_id:
                qs = qs.filter(customer_id=customer_id)

            from product.models import Product
            generic_prod = Product.objects.filter(type='service', is_active=True).first() if hasattr(Product, 'type') else Product.objects.filter(is_active=True).first()
            prod_id = generic_prod.id if generic_prod else ""

            orders_data = []
            for o in qs[:50]:
                u_price = round((o.final_price or Decimal('0.00')) / o.quantity, 4) if o.quantity else Decimal('0.00')
                orders_data.append({
                    'id': o.id,
                    'order_number': o.order_number,
                    'title': o.title or _("طلب مطبوعات"),
                    'customer_name': o.customer.name if o.customer else (o.customer_name or _("عميل نقدي")),
                    'quantity': o.quantity,
                    'final_price': str(o.final_price or 0),
                    'unit_price': str(u_price),
                    'product_id': prod_id,
                })
            return JsonResponse({'success': True, 'orders': orders_data})
        except Exception as e:
            return self.handle_exception(e, "ApprovedOrdersAPIView.get")

