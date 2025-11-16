"""
Views إدارة أجهزة البصمة
"""
from .base_imports import *
from ..models import BiometricDevice, BiometricLog, BiometricSyncLog, Employee, Department
from ..forms.biometric_forms import BiometricDeviceForm
from ..bridge_agent_utils import (
    test_device_connection,
    generate_agent_config,
    create_agent_zip_package,
    create_download_response
)
from django.db.models import Sum

__all__ = [
    'biometric_device_list',
    'biometric_device_detail',
    'biometric_device_logs_ajax',
    'biometric_device_form',
    'biometric_device_delete',
    'biometric_device_test',
    'biometric_agent_setup',
    'biometric_device_download_agent',
    'biometric_log_list',
]


@login_required
def biometric_device_list(request):
    """قائمة ماكينات البصمة - جدول موحد"""
    devices = BiometricDevice.objects.select_related('department', 'created_by').all()
    
    # إحصائيات
    stats = {
        'total_devices': devices.count(),
        'active_devices': devices.filter(is_active=True, status='active').count(),
        'offline_devices': devices.filter(status='error').count(),
        'total_users': devices.aggregate(Sum('total_users'))['total_users__sum'] or 0,
        'total_records': devices.aggregate(Sum('total_records'))['total_records__sum'] or 0,
    }
    
    # Headers للجدول الموحد
    headers = [
        {'key': 'device_name', 'label': 'اسم الماكينة', 'width': '20%', 'template': 'hr/biometric/cells/device_name.html'},
        {'key': 'device_type', 'label': 'النوع', 'width': '10%', 'template': 'hr/biometric/cells/device_type.html'},
        {'key': 'location', 'label': 'الموقع', 'width': '15%', 'template': 'hr/biometric/cells/location.html'},
        {'key': 'ip_address', 'label': 'IP Address', 'width': '12%', 'template': 'hr/biometric/cells/ip_address.html'},
        {'key': 'status', 'label': 'الحالة', 'width': '12%', 'class': 'text-center', 'template': 'hr/biometric/cells/status.html'},
        {'key': 'last_connection', 'label': 'آخر اتصال', 'width': '13%', 'template': 'hr/biometric/cells/last_connection.html'},
        {'key': 'total_users', 'label': 'المستخدمين', 'width': '8%', 'template': 'hr/biometric/cells/total_users.html'},
    ]
    
    # أزرار الإجراءات
    action_buttons = [
        {
            'url': 'hr:biometric_device_detail',
            'icon': 'fa-eye',
            'class': 'btn-info',
            'label': 'عرض'
        },
        {
            'url': 'hr:biometric_device_form_edit',
            'icon': 'fa-edit',
            'class': 'btn-warning',
            'label': 'تعديل'
        }
    ]
    
    context = {
        'devices': devices,
        'stats': stats,
        'headers': headers,
        'action_buttons': action_buttons,
        
        # بيانات الهيدر الموحد
        'page_title': 'ماكينات البصمة',
        'page_subtitle': 'إدارة ومزامنة ماكينات الحضور والانصراف',
        'page_icon': 'fas fa-fingerprint',
        'header_buttons': [
            {
                'url': reverse('hr:biometric_log_list'),
                'icon': 'fa-list',
                'text': 'سجلات البصمات',
                'class': 'btn-info',
            },
            {
                'url': reverse('hr:biometric_device_form'),
                'icon': 'fa-plus',
                'text': 'إضافة ماكينة',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'الإعدادات', 'url': reverse('hr:hr_settings'), 'icon': 'fas fa-cog'},
            {'title': 'ماكينات البصمة', 'active': True},
        ],
    }
    return render(request, 'hr/biometric/device_list.html', context)

@login_required
def biometric_device_detail(request, pk):
    """تفاصيل ماكينة البصمة - محسّن"""
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    # العدد الافتراضي للسجلات
    default_logs_count = 10
    
    # آخر السجلات
    recent_logs = BiometricLog.objects.filter(device=device).select_related('employee')[:default_logs_count]
    
    # آخر عمليات المزامنة
    sync_logs = BiometricSyncLog.objects.filter(device=device).order_by('-started_at')[:10]
    
    # Headers للجدول الموحد - سجلات البصمة
    log_headers = [
        {'key': 'timestamp', 'label': 'الوقت', 'format': 'datetime_12h', 'width': '20%'},
        {'key': 'user_id', 'label': 'معرف المستخدم', 'width': '15%'},
        {'key': 'employee', 'label': 'الموظف', 'width': '25%', 'template': 'hr/biometric/cells/log_employee.html'},
        {'key': 'log_type', 'label': 'النوع', 'width': '20%', 'template': 'hr/biometric/cells/log_type.html'},
        {'key': 'is_processed', 'label': 'حالة المعالجة', 'width': '20%', 'template': 'hr/biometric/cells/log_status.html'},
    ]
    
    context = {
        'device': device,
        'recent_logs': recent_logs,
        'sync_logs': sync_logs,
        'log_headers': log_headers,
        'logs_count': default_logs_count,  # إضافة العدد للـ context
    }
    return render(request, 'hr/biometric/device_detail.html', context)


@login_required
def biometric_device_logs_ajax(request, pk):
    """جلب سجلات البصمة ديناميكياً حسب العدد المطلوب"""
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    # الحصول على العدد المطلوب من الـ query parameter
    limit = int(request.GET.get('limit', 10))
    
    # جلب السجلات
    recent_logs = BiometricLog.objects.filter(device=device).select_related('employee')[:limit]
    
    # Headers للجدول
    log_headers = [
        {'key': 'timestamp', 'label': 'الوقت', 'format': 'datetime_12h', 'width': '20%'},
        {'key': 'user_id', 'label': 'معرف المستخدم', 'width': '15%'},
        {'key': 'employee', 'label': 'الموظف', 'width': '25%', 'template': 'hr/biometric/cells/log_employee.html'},
        {'key': 'log_type', 'label': 'النوع', 'width': '20%', 'template': 'hr/biometric/cells/log_type.html'},
        {'key': 'is_processed', 'label': 'حالة المعالجة', 'width': '20%', 'template': 'hr/biometric/cells/log_status.html'},
    ]
    
    context = {
        'data': recent_logs,
        'headers': log_headers,
        'empty_message': 'لا توجد سجلات بصمة',
        'empty_icon': 'fingerprint',
        'primary_key': 'id',
        'table_id': 'biometric-logs-table',
        'length_options': '5,10,20,50',
        'default_length': str(limit),  # القيمة المختارة حالياً
    }
    
    return render(request, 'components/data_table.html', context)


@login_required
def biometric_device_form(request, pk=None):
    """نموذج موحد لإضافة/تعديل ماكينة بصمة"""
    from django.urls import reverse
    from ..forms.biometric_forms import BiometricDeviceForm
    
    device = get_object_or_404(BiometricDevice, pk=pk) if pk else None
    
    if request.method == 'POST':
        form = BiometricDeviceForm(request.POST, instance=device)
        if form.is_valid():
            device_obj = form.save(commit=False)
            if not pk:
                device_obj.created_by = request.user
            device_obj.save()
            
            if pk:
                messages.success(request, 'تم تحديث الماكينة بنجاح')
                return redirect('hr:biometric_device_detail', pk=pk)
            else:
                messages.success(request, f'تم إضافة الماكينة بنجاح - الكود: {device_obj.device_code}')
                return redirect('hr:biometric_device_detail', pk=device_obj.pk)
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = BiometricDeviceForm(instance=device)
    
    is_edit = pk is not None
    context = {
        'form': form,
        'device': device,
        'page_title': f'{"تعديل ماكينة" if is_edit else "إضافة ماكينة بصمة"}',
        'page_subtitle': f'{"تعديل بيانات الماكينة" if is_edit else "إضافة جهاز بصمة جديد للنظام"}',
        'page_icon': 'fas fa-fingerprint',
        'header_buttons': [
            {
                'url': reverse('hr:biometric_device_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users'},
            {'title': 'ماكينات البصمة', 'url': reverse('hr:biometric_device_list'), 'icon': 'fas fa-fingerprint'},
            {'title': 'تعديل ماكينة' if is_edit else 'إضافة ماكينة', 'active': True},
        ],
    }
    
    return render(request, 'hr/biometric/device_form.html', context)


@login_required
def biometric_device_delete(request, pk):
    """حذف ماكينة البصمة"""
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    if request.method == 'POST':
        device.is_active = False
        device.status = 'inactive'
        device.save()
        messages.success(request, 'تم إلغاء تفعيل الماكينة')
        return redirect('hr:biometric_device_list')
    
    logs_count = BiometricLog.objects.filter(device=device).count()
    
    # تجهيز البيانات للمودال الموحد
    item_fields = [
        {'label': 'اسم الماكينة', 'value': device.device_name},
        {'label': 'الموقع', 'value': device.location},
        {'label': 'IP Address', 'value': device.connection_string},
        {'label': 'عدد السجلات', 'value': logs_count},
    ]
    
    warning_message = 'سيتم إلغاء تفعيل الماكينة فقط. السجلات ستبقى محفوظة.' if logs_count > 0 else ''
    
    context = {
        'device': device,
        'item_fields': item_fields,
        'logs_count': logs_count,
        'warning_message': warning_message,
    }
    return render(request, 'hr/biometric/device_delete_modal.html', context)




@login_required
def biometric_device_test(request, pk):
    """اختبار الاتصال بالماكينة - AJAX Modal"""
    from ..bridge_agent_utils import test_device_connection
    
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    if request.method == 'GET':
        # عرض المودال
        context = {'device': device}
        return render(request, 'hr/biometric/device_test_modal.html', context)
    
    # POST - تنفيذ الاختبار
    if request.method == 'POST':
        success, message, details = test_device_connection(device)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            response_data = {
                'success': success,
                'message': message
            }
            if details:
                response_data['details'] = details
            return JsonResponse(response_data)
        
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
    
    return redirect('hr:biometric_device_detail', pk=pk)


@login_required
def biometric_agent_setup(request, pk):
    """صفحة إرشادات إعداد Bridge Agent"""
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    context = {
        'device': device,
        'page_title': 'إعداد Bridge Agent',
    }
    
    return render(request, 'hr/biometric_agent_setup.html', context)


@login_required
def biometric_device_download_agent(request, pk):
    """تحميل ملف إعدادات Bridge Agent"""
    from ..bridge_agent_utils import generate_agent_config, create_agent_zip_package, create_download_response
    
    device = get_object_or_404(BiometricDevice, pk=pk)
    
    # توليد الإعدادات
    config, agent_secret = generate_agent_config(device, request)
    
    # إنشاء ملف ZIP
    zip_buffer = create_agent_zip_package(device, config)
    
    # عرض رسالة للمستخدم
    messages.success(
        request,
        f'تم تحميل Bridge Agent. لا تنسى إضافة المفتاح السري في settings.py:\n'
        f'BRIDGE_AGENTS = {{\'{device.device_code}\': \'{agent_secret}\'}}'
    )
    
    # إرجاع الملف
    return create_download_response(device, zip_buffer)


@login_required
def biometric_log_list(request):
    """قائمة سجلات البصمات"""
    logs = BiometricLog.objects.select_related(
        'device', 'employee', 'attendance'
    )
    
    # فلترة
    device_id = request.GET.get('device')
    if device_id:
        logs = logs.filter(device_id=device_id)
    
    employee_id = request.GET.get('employee')
    if employee_id:
        logs = logs.filter(employee_id=employee_id)
    
    # فلتر حالة الربط (مربوط/غير مربوط)
    linked = request.GET.get('linked')
    if linked == 'true':
        logs = logs.filter(employee__isnull=False)
    elif linked == 'false':
        logs = logs.filter(employee__isnull=True)
    
    # الترتيب (بدون limit - DataTables هيعمل pagination)
    logs = logs.order_by('-timestamp')
    
    devices = BiometricDevice.objects.filter(is_active=True)
    
    # إعداد headers للجدول الموحد
    headers = [
        {'key': 'timestamp', 'label': 'التاريخ والوقت', 'sortable': True, 'width': '15%', 'template': 'components/cells/biometric_log_timestamp.html'},
        {'key': 'device', 'label': 'الماكينة', 'sortable': True, 'width': '15%', 'template': 'components/cells/biometric_log_device.html'},
        {'key': 'user_id', 'label': 'معرف المستخدم', 'sortable': False, 'width': '12%', 'class': 'text-center', 'template': 'components/cells/biometric_log_user_id.html'},
        {'key': 'employee', 'label': 'الموظف', 'sortable': True, 'width': '20%', 'class': 'text-center', 'template': 'components/cells/biometric_log_employee.html'},
        {'key': 'log_type', 'label': 'النوع', 'sortable': True, 'width': '12%', 'class': 'text-center', 'template': 'components/cells/biometric_log_punch_type.html'},
        {'key': 'employee', 'label': 'حالة الربط', 'sortable': True, 'width': '12%', 'class': 'text-center', 'template': 'components/cells/biometric_log_is_processed.html'},
        {'key': 'actions', 'label': 'الإجراءات', 'sortable': False, 'width': '14%', 'class': 'text-center', 'template': 'components/cells/biometric_log_actions.html'},
    ]
    
    context = {
        'logs': logs,
        'devices': devices,
        'headers': headers,
        
        # بيانات الهيدر الموحد
        'page_title': 'سجلات البصمات',
        'page_subtitle': 'سجلات الحضور والانصراف من ماكينات البصمة',
        'page_icon': 'fas fa-list',
        'header_buttons': [
            {
                'onclick': 'runBiometricBulkLink()',
                'icon': 'fa-sync',
                'text': 'تحديث الربط',
                'class': 'btn-success',
                'id': 'btn-biometric-refresh-linking',
            },
            {
                'url': reverse('hr:biometric_device_list'),
                'icon': 'fa-fingerprint',
                'text': 'الماكينات',
                'class': 'btn-info',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:dashboard'), 'icon': 'fas fa-users-cog'},
            {'title': 'سجلات البصمات', 'active': True},
        ],
    }
    return render(request, 'hr/biometric/log_list.html', context)
