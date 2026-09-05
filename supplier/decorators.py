from functools import wraps
from django.shortcuts import redirect
from django.http import JsonResponse
from django.contrib import messages


def require_printing_pricing_enabled(view_func):
    """
    Decorator لمنع الوصول إلى أي شاشات أو عمليات أو خدمات تسعير
    إذا كان موديول تسعير الطباعة غير مفعّل في النظام.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        from core.models import SystemModule
        if not SystemModule.objects.filter(code='printing_pricing', is_enabled=True).exists():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': 'موديول تسعير الطباعة غير مفعّل في النظام.'
                }, status=403)
            messages.error(request, 'موديول تسعير الطباعة غير مفعّل في النظام.')
            pk = kwargs.get('pk')
            if pk:
                return redirect('supplier:supplier_detail', pk=pk)
            return redirect('supplier:supplier_list')
        return view_func(request, *args, **kwargs)
    return _wrapped
