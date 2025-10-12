"""
APIs للحسابات التلقائية في نظام التسعير
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
import json
from decimal import Decimal

from .models import PricingOrder, PaperType, PaperSize
from supplier.models import (
    PaperServiceDetails, DigitalPrintingDetails, 
    PlateServiceDetails, Supplier
)
from .services import PricingCalculatorService


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def calculate_cost(request):
    """حساب التكلفة الإجمالية للطلب"""
    try:
        data = json.loads(request.body)
        
        # الحصول على البيانات
        order_type = data.get('order_type')
        quantity = int(data.get('quantity', 0))
        paper_type_id = data.get('paper_type')
        paper_size_id = data.get('paper_size')
        paper_weight = int(data.get('paper_weight', 80))
        supplier_id = data.get('supplier')
        colors_front = int(data.get('colors_front', 4))
        colors_back = int(data.get('colors_back', 0))
        
        # التحقق من البيانات المطلوبة
        if not all([order_type, quantity, paper_type_id, paper_size_id]):
            return JsonResponse({
                'success': False,
                'error': 'بيانات مطلوبة مفقودة'
            })
        
        # إنشاء طلب مؤقت للحسابات
        temp_order = PricingOrder(
            order_type=order_type,
            quantity=quantity,
            paper_type_id=paper_type_id,
            paper_size_id=paper_size_id,
            paper_weight=paper_weight,
            supplier_id=supplier_id,
            colors_front=colors_front,
            colors_back=colors_back,
            profit_margin=Decimal('20.00')  # هامش ربح افتراضي
        )
        
        # حساب التكاليف
        calculator = PricingCalculatorService(temp_order)
        result = calculator.calculate_all_costs()
        
        if result['success']:
            return JsonResponse({
                'success': True,
                'material_cost': float(result['material_cost']),
                'printing_cost': float(result['printing_cost']),
                'plates_cost': float(result['plates_cost']),
                'finishing_cost': float(result['finishing_cost']),
                'total_cost': float(result['total_cost']),
                'sale_price': float(result['sale_price'])
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result['error']
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في الحساب: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def get_paper_price(request):
    """جلب سعر الورق من المورد"""
    try:
        supplier_id = request.GET.get('supplier_id')
        paper_type_id = request.GET.get('paper_type_id')
        paper_size_id = request.GET.get('paper_size_id')
        weight = request.GET.get('weight', 80)
        origin = request.GET.get('origin', 'local')
        
        if not all([supplier_id, paper_type_id, paper_size_id]):
            return JsonResponse({
                'success': False,
                'error': 'بيانات مطلوبة مفقودة'
            })
        
        # البحث عن خدمة الورق
        paper_service = PaperServiceDetails.find_paper_service(
            supplier_id=supplier_id,
            paper_type_id=paper_type_id,
            paper_size_id=paper_size_id,
            weight=int(weight),
            origin=origin
        )
        
        if paper_service:
            return JsonResponse({
                'success': True,
                'price_per_sheet': float(paper_service.price_per_sheet),
                'price_per_kg': float(paper_service.price_per_kg),
                'sheet_type': paper_service.sheet_type,
                'origin': paper_service.origin,
                'minimum_quantity': paper_service.minimum_quantity
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'لم يتم العثور على سعر للورق المحدد'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب سعر الورق: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def get_plate_price(request):
    """جلب سعر الزنكات من المورد"""
    try:
        supplier_id = request.GET.get('supplier_id')
        plate_size_id = request.GET.get('plate_size_id')
        
        if not all([supplier_id, plate_size_id]):
            return JsonResponse({
                'success': False,
                'error': 'بيانات مطلوبة مفقودة'
            })
        
        # البحث عن خدمة الزنكات
        plate_service = PlateServiceDetails.find_plate_service(
            supplier_id=supplier_id,
            plate_size_id=plate_size_id
        )
        
        if plate_service:
            return JsonResponse({
                'success': True,
                'plate_price': float(plate_service.price_per_plate),
                'setup_cost': float(plate_service.setup_cost),
                'transportation_cost': float(plate_service.transportation_cost),
                'minimum_quantity': plate_service.minimum_quantity,
                'min_plates_count': plate_service.minimum_quantity
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'لم يتم العثور على سعر للزنك المحدد'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب سعر الزنك: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def get_digital_printing_price(request):
    """جلب سعر الطباعة الرقمية"""
    try:
        supplier_id = request.GET.get('supplier_id')
        paper_size_id = request.GET.get('paper_size_id')
        color_type = request.GET.get('color_type', 'color')
        
        if not all([supplier_id, paper_size_id]):
            return JsonResponse({
                'success': False,
                'error': 'بيانات مطلوبة مفقودة'
            })
        
        # البحث عن خدمة الطباعة الرقمية
        digital_service = DigitalPrintingDetails.objects.filter(
            supplier_id=supplier_id,
            paper_size_id=paper_size_id,
            color_type=color_type,
            is_active=True
        ).first()
        
        if digital_service:
            return JsonResponse({
                'success': True,
                'price_per_copy': float(digital_service.price_per_copy),
                'minimum_quantity': digital_service.minimum_quantity,
                'maximum_quantity': digital_service.maximum_quantity,
                'color_type': digital_service.color_type
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'لم يتم العثور على سعر للطباعة الرقمية'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب سعر الطباعة الرقمية: {str(e)}'
        })


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def calculate_finishing_cost(request):
    """حساب تكلفة خدمات التشطيب"""
    try:
        data = json.loads(request.body)
        
        finishing_services = data.get('finishing_services', [])
        quantity = int(data.get('quantity', 0))
        
        if not quantity:
            return JsonResponse({
                'success': False,
                'error': 'الكمية مطلوبة'
            })
        
        total_cost = Decimal('0.00')
        service_costs = []
        
        for service_data in finishing_services:
            service_type = service_data.get('service_type')
            unit_price = Decimal(str(service_data.get('unit_price', 0)))
            service_quantity = int(service_data.get('quantity', quantity))
            
            service_cost = unit_price * service_quantity
            total_cost += service_cost
            
            service_costs.append({
                'service_type': service_type,
                'unit_price': float(unit_price),
                'quantity': service_quantity,
                'total_cost': float(service_cost)
            })
        
        return JsonResponse({
            'success': True,
            'total_finishing_cost': float(total_cost),
            'service_costs': service_costs
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في حساب تكلفة التشطيب: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def get_paper_types(request):
    """جلب أنواع الورق النشطة"""
    try:
        paper_types = PaperType.objects.filter(is_active=True).order_by('name')
        
        data = [{
            'id': pt.id,
            'name': pt.name,
            'description': pt.description,
            'is_default': pt.is_default
        } for pt in paper_types]
        
        return JsonResponse({
            'success': True,
            'paper_types': data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب أنواع الورق: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def get_paper_sizes(request):
    """جلب مقاسات المنتجات النشطة"""
    try:
        from .models import ProductSize
        product_sizes = ProductSize.objects.filter(is_active=True).order_by('name')
        
        data = [{
            'id': ps.id,
            'name': ps.name,
            'width': float(ps.width),
            'height': float(ps.height),
            'is_default': getattr(ps, 'is_default', False)
        } for ps in product_sizes]
        
        return JsonResponse({
            'success': True,
            'paper_sizes': data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب مقاسات الورق: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def get_suppliers(request):
    """جلب الموردين النشطين"""
    try:
        suppliers = Supplier.objects.filter(is_active=True).order_by('name')
        
        data = [{
            'id': s.id,
            'name': s.name,
            'phone': getattr(s, 'phone', ''),
            'email': getattr(s, 'email', ''),
            'contact_person': getattr(s, 'contact_person', '')
        } for s in suppliers]
        
        return JsonResponse({
            'success': True,
            'suppliers': data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب الموردين: {str(e)}'
        })


@login_required
@require_http_methods(["GET"])
def get_order_summary(request, order_id):
    """جلب ملخص طلب التسعير"""
    try:
        order = get_object_or_404(PricingOrder, id=order_id)
        calculator = PricingCalculatorService(order)
        breakdown = calculator.get_cost_breakdown()
        
        return JsonResponse({
            'success': True,
            'order_number': order.order_number,
            'client_name': order.client.name,
            'quantity': order.quantity,
            'order_type': order.get_order_type_display(),
            'status': order.get_status_display(),
            'breakdown': {
                'material_cost': float(breakdown['material_cost']),
                'printing_cost': float(breakdown['printing_cost']),
                'plates_cost': float(breakdown['plates_cost']),
                'finishing_cost': float(breakdown['finishing_cost']),
                'extra_cost': float(breakdown['extra_cost']),
                'total_cost': float(breakdown['total_cost']),
                'profit_margin': float(breakdown['profit_margin']),
                'profit_amount': float(breakdown['profit_amount']),
                'sale_price': float(breakdown['sale_price']),
                'unit_price': float(breakdown['unit_price'])
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب ملخص الطلب: {str(e)}'
        })
