"""
APIs لتصفية الموردين
"""

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .supplier_filters import get_printing_suppliers, get_ctp_suppliers


@login_required
def get_printing_suppliers_api(request):
    """API لجلب موردي الطباعة المفلترين"""
    try:
        order_type = request.GET.get('order_type')
        
        suppliers = get_printing_suppliers(order_type)
        
        suppliers_data = []
        for supplier in suppliers:
            suppliers_data.append({
                'id': supplier.id,
                'name': supplier.name
            })
        
        return JsonResponse({
            'success': True,
            'suppliers': suppliers_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب موردي الطباعة: {str(e)}',
            'suppliers': []
        })


@login_required
def get_ctp_suppliers_api(request):
    """API لجلب موردي الزنكات CTP"""
    try:
        suppliers = get_ctp_suppliers()
        
        suppliers_data = []
        for supplier in suppliers:
            suppliers_data.append({
                'id': supplier.id,
                'name': supplier.name
            })
        
        return JsonResponse({
            'success': True,
            'suppliers': suppliers_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب موردي الزنكات: {str(e)}',
            'suppliers': []
        })
