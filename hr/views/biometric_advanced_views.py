"""
Views متقدمة لإدارة البصمة - Dashboard & Mapping & APIs
"""
from .base_imports import *
from ..models import (
    BiometricLog, BiometricUserMapping, BiometricDevice, 
    Attendance, Employee
)
from ..forms.biometric_forms import BiometricUserMappingForm, BulkMappingForm
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q

__all__ = [
    'biometric_dashboard',
    'biometric_mapping_list',
    'biometric_mapping_create',
    'biometric_mapping_update',
    'biometric_mapping_delete',
    'biometric_mapping_bulk_import',
    'api_link_single_log',
    'api_process_single_log',
    'api_mapping_suggestions',
    'api_bulk_link_logs',
    'api_bulk_process_logs',
    'api_biometric_stats',
]


# ==================== Biometric Dashboard ====================

@login_required
def biometric_dashboard(request):
    """لوحة تحكم شاملة لمراقبة سجلات البصمة"""
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # إحصائيات السجلات
    total_logs = BiometricLog.objects.count()
    linked_logs = BiometricLog.objects.filter(employee__isnull=False).count()
    unlinked_logs = total_logs - linked_logs
    
    # سجلات اليوم
    today_logs = BiometricLog.objects.filter(timestamp__date=today)
    today_total = today_logs.count()
    today_linked = today_logs.filter(employee__isnull=False).count()
    
    # سجلات الأسبوع
    week_logs = BiometricLog.objects.filter(timestamp__date__gte=week_ago)
    week_total = week_logs.count()
    week_linked = week_logs.filter(employee__isnull=False).count()
    
    # إحصائيات الربط
    total_mappings = BiometricUserMapping.objects.count()
    active_mappings = BiometricUserMapping.objects.filter(is_active=True).count()
    inactive_mappings = total_mappings - active_mappings
    
    # إحصائيات الأجهزة
    total_devices = BiometricDevice.objects.count()
    active_devices = BiometricDevice.objects.filter(is_active=True).count()
    online_devices = BiometricDevice.objects.filter(is_active=True, status='online').count()
    offline_devices = active_devices - online_devices
    
    # إحصائيات الحضور
    today_attendance = Attendance.objects.filter(date=today)
    today_attendance_total = today_attendance.count()
    today_present = today_attendance.filter(status='present').count()
    today_absent = today_attendance.filter(status='absent').count()
    today_late = today_attendance.filter(late_minutes__gt=0).count()
    
    # آخر السجلات غير المربوطة
    recent_unlinked = BiometricLog.objects.filter(
        employee__isnull=True
    ).select_related('device').order_by('-timestamp')[:10]
    
    # آخر السجلات المربوطة
    recent_linked = BiometricLog.objects.filter(
        employee__isnull=False
    ).select_related('employee', 'device').order_by('-timestamp')[:10]
    
    # الأجهزة غير المتصلة
    offline_device_list = BiometricDevice.objects.filter(
        is_active=True,
        status='offline'
    )[:5]
    
    # إحصائيات يومية للأسبوع الماضي
    daily_stats = []
    for i in range(7):
        day = today - timedelta(days=6-i)
        day_logs = BiometricLog.objects.filter(timestamp__date=day)
        total_count = day_logs.count()
        linked_count = day_logs.filter(employee__isnull=False).count()
        processed_count = day_logs.filter(is_processed=True).count()
        daily_stats.append({
            'date': day.strftime('%Y-%m-%d'),
            'date_display': day.strftime('%d/%m'),
            'total': total_count,
            'linked': linked_count,
            'processed': processed_count,
        })
    
    # نسب الإنجاز
    link_percentage = (linked_logs / total_logs * 100) if total_logs > 0 else 0
    online_percentage = (online_devices / active_devices * 100) if active_devices > 0 else 0
    offline_percentage = (offline_devices / active_devices * 100) if active_devices > 0 else 0
    week_linked_percentage = (week_linked / week_total * 100) if week_total > 0 else 0
    
    # حساب processed_logs و unprocessed_logs
    processed_logs = BiometricLog.objects.filter(is_processed=True).count()
    unprocessed_logs = total_logs - processed_logs
    process_percentage = (processed_logs / total_logs * 100) if total_logs > 0 else 0
    week_processed = week_logs.filter(is_processed=True).count()
    week_processed_percentage = (week_processed / week_total * 100) if week_total > 0 else 0
    
    # آخر السجلات غير المعالجة
    recent_unprocessed = BiometricLog.objects.filter(
        is_processed=False,
        employee__isnull=False
    ).select_related('employee', 'device').order_by('-timestamp')[:10]
    
    context = {
        # إحصائيات عامة
        'total_logs': total_logs,
        'linked_logs': linked_logs,
        'unlinked_logs': unlinked_logs,
        'link_percentage': round(link_percentage, 1),
        'processed_logs': processed_logs,
        'unprocessed_logs': unprocessed_logs,
        'process_percentage': round(process_percentage, 1),
        
        # إحصائيات اليوم
        'today_total': today_total,
        'today_linked': today_linked,
        
        # إحصائيات الأسبوع
        'week_total': week_total,
        'week_linked': week_linked,
        'week_linked_percentage': round(week_linked_percentage, 1),
        'week_processed': week_processed,
        'week_processed_percentage': round(week_processed_percentage, 1),
        
        # إحصائيات الربط
        'total_mappings': total_mappings,
        'active_mappings': active_mappings,
        'inactive_mappings': inactive_mappings,
        
        # إحصائيات الأجهزة
        'total_devices': total_devices,
        'active_devices': active_devices,
        'online_devices': online_devices,
        'offline_devices': offline_devices,
        'online_percentage': round(online_percentage, 1),
        'offline_percentage': round(offline_percentage, 1),
        
        # إحصائيات الحضور
        'today_attendance_total': today_attendance_total,
        'today_present': today_present,
        'today_absent': today_absent,
        'today_late': today_late,
        
        # قوائم
        'recent_unlinked': recent_unlinked,
        'recent_linked': recent_linked,
        'recent_unprocessed': recent_unprocessed,
        'offline_device_list': offline_device_list,
        'daily_stats': daily_stats,
        
        # بيانات الهيدر الموحد
        'page_title': 'لوحة تحكم البصمة',
        'page_subtitle': 'مراقبة شاملة لسجلات البصمة والحضور',
        'page_icon': 'fas fa-fingerprint',
        'header_buttons': [
            {
                'url': reverse('hr:biometric_log_list'),
                'icon': 'fa-list',
                'text': 'جميع السجلات',
                'class': 'btn-outline-primary',
            },
            {
                'url': reverse('hr:biometric_mapping_list'),
                'icon': 'fa-link',
                'text': 'إدارة الربط',
                'class': 'btn-outline-secondary',
            },
            {
                'url': reverse('hr:biometric_device_list'),
                'icon': 'fa-server',
                'text': 'الأجهزة',
                'class': 'btn-outline-info',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'لوحة تحكم البصمة', 'active': True},
        ],
    }
    
    return render(request, 'hr/biometric/dashboard.html', context)


# ==================== BiometricUserMapping Management ====================

@login_required
def biometric_mapping_list(request):
    """قائمة ربط معرفات البصمة"""
    from django.urls import reverse
    
    mappings = BiometricUserMapping.objects.select_related(
        'employee', 'device'
    ).all()
    
    # الفلترة حسب البحث
    search = request.GET.get('search', '')
    if search:
        mappings = mappings.filter(
            Q(employee__first_name_ar__icontains=search) |
            Q(employee__last_name_ar__icontains=search) |
            Q(employee__employee_number__icontains=search) |
            Q(biometric_user_id__icontains=search)
        )
    
    # الفلترة حسب الجهاز
    device_id = request.GET.get('device', '')
    if device_id:
        mappings = mappings.filter(device_id=device_id)
    
    # الفلترة حسب الحالة
    is_active = request.GET.get('is_active', '')
    if is_active:
        mappings = mappings.filter(is_active=(is_active == 'true'))
    
    # إحصائيات
    stats = {
        'total': BiometricUserMapping.objects.count(),
        'active': BiometricUserMapping.objects.filter(is_active=True).count(),
        'inactive': BiometricUserMapping.objects.filter(is_active=False).count(),
    }
    
    # Headers للجدول
    headers = [
        {'key': 'employee', 'label': 'الموظف', 'width': '25%', 'sortable': True},
        {'key': 'biometric_user_id', 'label': 'معرف البصمة', 'width': '15%', 'sortable': True},
        {'key': 'device', 'label': 'الماكينة', 'width': '20%', 'sortable': True},
        {'key': 'is_active', 'label': 'الحالة', 'width': '10%', 'class': 'text-center'},
        {'key': 'created_at', 'label': 'تاريخ الإنشاء', 'width': '15%', 'format': 'date'},
    ]
    
    # أزرار الإجراءات
    action_buttons = [
        {
            'url': 'hr:biometric_mapping_update',
            'icon': 'fa-edit',
            'class': 'btn-warning',
            'label': 'تعديل'
        },
        {
            'url': 'hr:biometric_mapping_delete',
            'icon': 'fa-trash',
            'class': 'btn-danger',
            'label': 'حذف'
        },
    ]
    
    # جلب الأجهزة للفلترة
    devices = BiometricDevice.objects.filter(is_active=True)
    
    context = {
        'mappings': mappings,
        'stats': stats,
        'headers': headers,
        'action_buttons': action_buttons,
        'devices': devices,
        'page_title': 'ربط معرفات البصمة بالموظفين',
        'page_subtitle': 'إدارة الربط بين معرفات البصمة وأرقام الموظفين',
        'page_icon': 'fas fa-link',
        'header_buttons': [
            {
                'url': reverse('hr:biometric_mapping_bulk_import'),
                'icon': 'fa-file-csv',
                'text': 'استيراد جماعي',
                'class': 'btn-success',
            },
            {
                'url': reverse('hr:biometric_mapping_create'),
                'icon': 'fa-plus',
                'text': 'إضافة ربط',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'ماكينات البصمة', 'url': reverse('hr:biometric_device_list'), 'icon': 'fas fa-fingerprint'},
            {'title': 'ربط معرفات البصمة', 'active': True},
        ],
    }
    return render(request, 'hr/biometric/mapping_list.html', context)


@login_required
def biometric_mapping_create(request):
    """إنشاء ربط جديد"""
    from django.urls import reverse
    
    if request.method == 'POST':
        form = BiometricUserMappingForm(request.POST)
        if form.is_valid():
            mapping = form.save()
            messages.success(request, f'تم إنشاء الربط بنجاح: {mapping.employee.get_full_name_ar()}')
            return redirect('hr:biometric_mapping_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = BiometricUserMappingForm()
    
    context = {
        'form': form,
        'is_edit': False,
        'page_title': 'إضافة ربط البصمة',
        'page_subtitle': 'ربط معرف البصمة بموظف في النظام',
        'page_icon': 'fas fa-plus',
        'header_buttons': [
            {
                'url': reverse('hr:biometric_mapping_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'ربط معرفات البصمة', 'url': reverse('hr:biometric_mapping_list'), 'icon': 'fas fa-link'},
            {'title': 'إضافة', 'active': True},
        ],
    }
    return render(request, 'hr/biometric/mapping_form.html', context)


@login_required
def biometric_mapping_update(request, pk):
    """تعديل ربط موجود"""
    from django.urls import reverse
    
    mapping = get_object_or_404(BiometricUserMapping, pk=pk)
    
    if request.method == 'POST':
        form = BiometricUserMappingForm(request.POST, instance=mapping)
        if form.is_valid():
            mapping = form.save()
            messages.success(request, f'تم تحديث الربط بنجاح: {mapping.employee.get_full_name_ar()}')
            return redirect('hr:biometric_mapping_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = BiometricUserMappingForm(instance=mapping)
    
    context = {
        'form': form,
        'mapping': mapping,
        'is_edit': True,
        'page_title': 'تعديل ربط البصمة',
        'page_subtitle': 'ربط معرف البصمة بموظف في النظام',
        'page_icon': 'fas fa-edit',
        'header_buttons': [
            {
                'url': reverse('hr:biometric_mapping_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'ربط معرفات البصمة', 'url': reverse('hr:biometric_mapping_list'), 'icon': 'fas fa-link'},
            {'title': 'تعديل', 'active': True},
        ],
    }
    return render(request, 'hr/biometric/mapping_form.html', context)


@login_required
def biometric_mapping_delete(request, pk):
    """حذف ربط"""
    mapping = get_object_or_404(BiometricUserMapping, pk=pk)
    
    if request.method == 'POST':
        employee_name = mapping.employee.get_full_name_ar()
        biometric_id = mapping.biometric_user_id
        mapping.delete()
        messages.success(request, f'تم حذف الربط: {employee_name} ({biometric_id})')
        return redirect('hr:biometric_mapping_list')
    
    # تجهيز البيانات للمودال
    item_fields = [
        {'label': 'الموظف', 'value': mapping.employee.get_full_name_ar()},
        {'label': 'معرف البصمة', 'value': mapping.biometric_user_id},
        {'label': 'الماكينة', 'value': mapping.device.device_name if mapping.device else 'عام'},
        {'label': 'الحالة', 'value': 'نشط' if mapping.is_active else 'غير نشط'},
    ]
    
    context = {
        'mapping': mapping,
        'item_fields': item_fields,
    }
    return render(request, 'hr/biometric/mapping_delete.html', context)


@login_required
def biometric_mapping_bulk_import(request):
    """استيراد جماعي من CSV"""
    if request.method == 'POST':
        form = BulkMappingForm(request.POST, request.FILES)
        if form.is_valid():
            # معالجة الملف
            stats = form.process_csv()
            
            # عرض النتائج
            if stats['created'] > 0 or stats['updated'] > 0:
                messages.success(
                    request,
                    f'تم الاستيراد بنجاح: {stats["created"]} جديد، {stats["updated"]} محدث'
                )
            
            if stats['errors']:
                for error in stats['errors'][:5]:
                    messages.warning(request, error)
                
                if len(stats['errors']) > 5:
                    messages.warning(request, f'... و {len(stats["errors"]) - 5} خطأ آخر')
            
            return redirect('hr:biometric_mapping_list')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = BulkMappingForm()
    
    context = {
        'form': form,
    }
    return render(request, 'hr/biometric/mapping_bulk_import.html', context)


# ==================== BiometricUserMapping APIs ====================

@api_view(['POST'])
@login_required
def api_link_single_log(request, log_id):
    """
    API لربط سجل واحد بموظف
    
    POST /hr/api/biometric/logs/<log_id>/link/
    Body: {"employee_id": 123} (اختياري)
    """
    from ..utils.biometric_utils import link_single_log
    
    try:
        log = get_object_or_404(BiometricLog, pk=log_id)
        employee_id = request.data.get('employee_id')
        
        success, message = link_single_log(log, employee_id)
        
        return JsonResponse({
            'success': success,
            'message': message,
            'log': {
                'id': log.id,
                'user_id': log.user_id,
                'employee': log.employee.get_full_name_ar() if log.employee else None,
                'timestamp': log.timestamp.isoformat()
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@api_view(['POST'])
@login_required
def api_process_single_log(request, log_id):
    """
    API لمعالجة سجل واحد
    
    POST /hr/api/biometric/logs/<log_id>/process/
    """
    from ..utils.biometric_utils import process_single_log
    
    try:
        log = get_object_or_404(BiometricLog, pk=log_id)
        
        success, message = process_single_log(log)
        
        return JsonResponse({
            'success': success,
            'message': message,
            'log': {
                'id': log.id,
                'is_processed': log.is_processed,
                'attendance_id': log.attendance.id if log.attendance else None
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@api_view(['GET'])
@login_required
def api_mapping_suggestions(request):
    """
    API للحصول على اقتراحات الربط التلقائي
    
    GET /hr/api/biometric/mapping/suggestions/
    """
    from ..utils.biometric_utils import get_mapping_suggestions
    
    try:
        suggestions = get_mapping_suggestions()
        
        return JsonResponse({
            'success': True,
            'count': len(suggestions),
            'suggestions': suggestions
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@api_view(['POST'])
@login_required
def api_bulk_link_logs(request):
    """
    API للربط الجماعي
    
    POST /hr/api/biometric/logs/bulk-link/
    Body: {
        "device_id": 1 (optional),
        "unlinked_only": true,
        "limit": 100
    }
    """
    from ..utils.biometric_utils import bulk_link_logs
    
    try:
        device_id = request.data.get('device_id')
        unlinked_only = request.data.get('unlinked_only', True)
        limit = request.data.get('limit')
        
        stats = bulk_link_logs(
            device_id=device_id,
            unlinked_only=unlinked_only,
            dry_run=False,
            limit=limit
        )
        
        return JsonResponse({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@api_view(['POST'])
@login_required
def api_bulk_process_logs(request):
    """
    API للمعالجة الجماعية
    
    POST /hr/api/biometric/logs/bulk-process/
    Body: {
        "date": "2025-01-15" (optional),
        "employee_id": 1 (optional),
        "unprocessed_only": true
    }
    """
    from ..utils.biometric_utils import bulk_process_logs
    from datetime import datetime
    
    try:
        date_str = request.data.get('date')
        target_date = None
        if date_str:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        employee_id = request.data.get('employee_id')
        unprocessed_only = request.data.get('unprocessed_only', True)
        
        stats = bulk_process_logs(
            date=target_date,
            employee_id=employee_id,
            unprocessed_only=unprocessed_only,
            dry_run=False
        )
        
        return JsonResponse({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@api_view(['GET'])
@login_required
def api_biometric_stats(request):
    """
    API للحصول على إحصائيات البصمة
    
    GET /hr/api/biometric/stats/
    """
    try:
        today = timezone.now().date()
        
        # إحصائيات السجلات
        total_logs = BiometricLog.objects.count()
        linked_logs = BiometricLog.objects.filter(employee__isnull=False).count()
        today_logs = BiometricLog.objects.filter(timestamp__date=today).count()
        
        # إحصائيات الربط
        total_mappings = BiometricUserMapping.objects.count()
        active_mappings = BiometricUserMapping.objects.filter(is_active=True).count()
        
        return JsonResponse({
            'success': True,
            'stats': {
                'total': total_logs,
                'linked': linked_logs,
                'unlinked': total_logs - linked_logs,
                'today': today_logs
            },
            'mappings': {
                'total': total_mappings,
                'active': active_mappings,
                'inactive': total_mappings - active_mappings
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
