"""
Views إدارة أنواع الإجازات - CRUD عبر مودال
"""
from .base_imports import *
from ..models import LeaveType
from ..decorators import require_hr
from django.views.decorators.http import require_POST

__all__ = [
    'leave_type_list',
    'leave_type_save',
    'leave_type_delete',
    'leave_type_toggle',
]

CATEGORY_CHOICES = [
    ('annual',      'اعتيادي'),
    ('emergency',   'عارضة'),
    ('sick',        'مرضي'),
    ('exceptional', 'استثنائي (مدفوع)'),
    ('unpaid',      'غير مدفوع'),
]


@login_required
@require_hr
def leave_type_list(request):
    """قائمة أنواع الإجازات مع CRUD بالمودال"""
    leave_types = LeaveType.objects.all().order_by('category', 'name_ar')

    context = {
        'leave_types': leave_types,
        'category_choices': CATEGORY_CHOICES,
        'page_title': 'أنواع الإجازات',
        'page_subtitle': 'إدارة أنواع الإجازات المتاحة في النظام',
        'page_icon': 'fas fa-tags',
        'header_buttons': [
            {
                'onclick': 'openAddModal()',
                'icon': 'fa-plus',
                'text': 'إضافة نوع جديد',
                'class': 'btn-primary',
            },
            {
                'url': reverse('hr:leave_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الإجازات', 'url': reverse('hr:leave_list'), 'icon': 'fas fa-calendar-alt'},
            {'title': 'أنواع الإجازات', 'active': True},
        ],
    }
    return render(request, 'hr/leave/type_list.html', context)


@login_required
@require_hr
@require_POST
def leave_type_save(request, pk=None):
    """حفظ نوع إجازة (إضافة أو تعديل) - JSON"""
    try:
        if pk:
            obj = get_object_or_404(LeaveType, pk=pk)
        else:
            obj = LeaveType()

        obj.name_ar             = request.POST.get('name_ar', '').strip()
        obj.name_en             = request.POST.get('name_en', '').strip()
        obj.code                = request.POST.get('code', '').strip().upper()
        obj.category            = request.POST.get('category', 'annual')
        obj.max_days_per_year   = int(request.POST.get('max_days_per_year', 21))
        obj.is_paid             = request.POST.get('is_paid') == 'true'
        obj.requires_approval   = request.POST.get('requires_approval') == 'true'
        obj.requires_document   = request.POST.get('requires_document') == 'true'
        obj.allow_encashment    = request.POST.get('allow_encashment') == 'true'
        obj.is_active           = request.POST.get('is_active', 'true') == 'true'

        from decimal import Decimal
        obj.deduction_multiplier = Decimal(request.POST.get('deduction_multiplier', '1.0'))

        if not obj.name_ar:
            return JsonResponse({'success': False, 'error': 'الاسم العربي مطلوب'})
        if not obj.code:
            return JsonResponse({'success': False, 'error': 'الكود مطلوب'})

        # التحقق من تكرار الكود
        qs = LeaveType.objects.filter(code=obj.code)
        if pk:
            qs = qs.exclude(pk=pk)
        if qs.exists():
            return JsonResponse({'success': False, 'error': f'الكود "{obj.code}" مستخدم بالفعل'})

        obj.save()
        return JsonResponse({'success': True, 'message': 'تم الحفظ بنجاح'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_hr
@require_POST
def leave_type_delete(request, pk):
    """حذف نوع إجازة - JSON"""
    obj = get_object_or_404(LeaveType, pk=pk)
    try:
        name = obj.name_ar
        obj.delete()
        return JsonResponse({'success': True, 'message': f'تم حذف "{name}"'})
    except Exception:
        return JsonResponse({'success': False, 'error': 'لا يمكن الحذف: النوع مرتبط ببيانات موجودة'})


@login_required
@require_hr
@require_POST
def leave_type_toggle(request, pk):
    """تفعيل/تعطيل نوع إجازة - JSON"""
    obj = get_object_or_404(LeaveType, pk=pk)
    obj.is_active = not obj.is_active
    obj.save()
    return JsonResponse({
        'success': True,
        'is_active': obj.is_active,
        'status': 'نشط' if obj.is_active else 'غير نشط',
    })
