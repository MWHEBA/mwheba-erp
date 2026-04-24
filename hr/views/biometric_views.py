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
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الإعدادات', 'url': reverse('hr:hr_settings'), 'icon': 'fas fa-cog'},
            {'title': 'لوحة تحكم البصمة', 'url': reverse('hr:biometric_dashboard'), 'icon': 'fas fa-fingerprint'},
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
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users'},
            {'title': 'لوحة تحكم البصمة', 'url': reverse('hr:biometric_dashboard'), 'icon': 'fas fa-fingerprint'},
            {'title': 'ماكينات البصمة', 'url': reverse('hr:biometric_device_list'), 'icon': 'fas fa-server'},
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
    """قائمة سجلات البصمات - مع pagination"""
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    
    logs = BiometricLog.objects.select_related(
        'device', 'employee', 'attendance'
    )
    
    # فلترة بالتاريخ
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            # Make timezone aware
            date_from_aware = timezone.make_aware(date_from_obj)
            logs = logs.filter(timestamp__gte=date_from_aware)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day and make timezone aware to include the entire day
            date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
            date_to_aware = timezone.make_aware(date_to_obj)
            logs = logs.filter(timestamp__lte=date_to_aware)
        except ValueError:
            pass
    
    # فلترة بالماكينة
    device_id = request.GET.get('device')
    if device_id:
        logs = logs.filter(device_id=device_id)
    
    # فلترة بالموظف
    employee_id = request.GET.get('employee')
    if employee_id:
        logs = logs.filter(employee_id=employee_id)
    
    # فلتر حالة الربط (مربوط/غير مربوط)
    linked = request.GET.get('linked')
    if linked == 'true':
        logs = logs.filter(employee__isnull=False)
    elif linked == 'false':
        logs = logs.filter(employee__isnull=True)
    
    # الترتيب
    logs = logs.order_by('-timestamp')
    
    # Pagination - 50 سجل في الصفحة
    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    
    try:
        logs_page = paginator.page(page)
    except PageNotAnInteger:
        logs_page = paginator.page(1)
    except EmptyPage:
        logs_page = paginator.page(paginator.num_pages)
    
    devices = BiometricDevice.objects.filter(is_active=True)
    employees = Employee.objects.filter(status='active', is_insurance_only=False).order_by('name')

    # حساب display_log_type لكل بصمة بناءً على ترتيبها في اليوم لنفس الموظف
    # الجهاز أحياناً بيبعت كل البصمات بـ log_type=check_in، فنحدد النوع الصحيح من الترتيب
    page_log_ids = [log.id for log in logs_page]
    if page_log_ids:
        # جلب كل بصمات نفس الموظفين/الأيام الموجودة في الصفحة الحالية
        from django.db.models import Min, Max
        page_logs_qs = BiometricLog.objects.filter(id__in=page_log_ids).select_related('employee')
        
        # بناء map: (employee_id, date) → [sorted log ids]
        from collections import defaultdict
        day_employee_logs = defaultdict(list)
        for log in page_logs_qs:
            if log.employee_id:
                key = (log.employee_id, log.timestamp.date())
                day_employee_logs[key].append((log.timestamp, log.id))

        # جلب كل بصمات هذه الموظفين في هذه الأيام (مش بس الصفحة الحالية)
        all_day_logs_map = {}  # (employee_id, date) → sorted list of (timestamp, id)
        for (emp_id, log_date) in day_employee_logs.keys():
            day_start = timezone.make_aware(datetime(log_date.year, log_date.month, log_date.day, 0, 0, 0))
            day_end = timezone.make_aware(datetime(log_date.year, log_date.month, log_date.day, 23, 59, 59))
            all_day = list(
                BiometricLog.objects.filter(
                    employee_id=emp_id,
                    timestamp__gte=day_start,
                    timestamp__lte=day_end,
                ).values_list('id', 'timestamp').order_by('timestamp')
            )
            all_day_logs_map[(emp_id, log_date)] = all_day  # [(id, timestamp), ...]

        # بناء display_log_type map: log_id → 'check_in' | 'check_out' | 'intermediate'
        display_type_map = {}
        for (emp_id, log_date), sorted_logs in all_day_logs_map.items():
            for idx, (log_id, _) in enumerate(sorted_logs):
                if idx == 0:
                    display_type_map[log_id] = 'check_in'
                elif idx == len(sorted_logs) - 1:
                    display_type_map[log_id] = 'check_out'
                else:
                    display_type_map[log_id] = 'intermediate'

        # إضافة display_log_type لكل log في الصفحة
        for log in logs_page:
            log.display_log_type = display_type_map.get(log.id, log.log_type)
    else:
        for log in logs_page:
            log.display_log_type = log.log_type

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
        'logs': logs_page,
        'devices': devices,
        'employees': employees,
        'headers': headers,
        'paginator': paginator,
        'page_obj': logs_page,
        'date_from': date_from if date_from else '',
        'date_to': date_to if date_to else '',
        
        # بيانات الهيدر الموحد
        'page_title': 'سجلات البصمات',
        'page_subtitle': 'سجلات الحضور والانصراف من ماكينات البصمة',
        'page_icon': 'fas fa-list',
        'header_buttons': [
            {
                'url': reverse('hr:attendance_list'),
                'icon': 'fa-clock',
                'text': 'سجلات الحضور',
                'class': 'btn-primary',
            },
            {
                'onclick': 'runBiometricBulkLink()',
                'icon': 'fa-sync',
                'text': 'تحديث الربط',
                'class': 'btn-success',
                'id': 'btn-biometric-refresh-linking',
            },
            {
                'onclick': 'cleanupOldLogs()',
                'icon': 'fa-trash-alt',
                'text': 'حذف السجلات القديمة',
                'class': 'btn-danger',
                'id': 'btn-cleanup-old-logs',
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
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'لوحة تحكم البصمة', 'url': reverse('hr:biometric_dashboard'), 'icon': 'fas fa-fingerprint'},
            {'title': 'سجلات البصمات', 'active': True},
        ],
    }
    return render(request, 'hr/biometric/log_list.html', context)
