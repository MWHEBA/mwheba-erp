"""
عرض سجل الحركات الفاشلة في التحقق من المعاملات المالية
"""
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse
from datetime import timedelta

from financial.models.validation_audit_log import ValidationAuditLog


@login_required
@permission_required('financial.view_validationauditlog', raise_exception=True)
def validation_logs_list(request):
    """
    عرض قائمة مفصلة بجميع محاولات التحقق الفاشلة
    """
    # الحصول على معاملات التصفية
    days = int(request.GET.get('days', 30))
    validation_type = request.GET.get('validation_type', '')
    entity_type = request.GET.get('entity_type', '')
    module = request.GET.get('module', '')
    search = request.GET.get('search', '')
    
    # الفترة الزمنية
    since = timezone.now() - timedelta(days=days)
    
    # الاستعلام الأساسي
    logs = ValidationAuditLog.objects.filter(timestamp__gte=since).select_related('user')
    
    # تطبيق التصفيات
    if validation_type:
        logs = logs.filter(validation_type=validation_type)
    
    if entity_type:
        logs = logs.filter(entity_type=entity_type)
    
    if module:
        logs = logs.filter(module=module)
    
    if search:
        logs = logs.filter(
            Q(entity_name__icontains=search) |
            Q(failure_reason__icontains=search) |
            Q(error_message__icontains=search) |
            Q(user__username__icontains=search)
        )
    
    # ترتيب النتائج
    logs = logs.order_by('-timestamp')
    
    # ترجمة أسباب الفشل
    failure_reason_translations = {
        'missing_account': 'الحساب المحاسبي غير موجود',
        'invalid_account': 'الحساب المحاسبي غير صالح',
        'inactive_account': 'الحساب المحاسبي غير مفعّل',
        'not_leaf_account': 'الحساب المحاسبي ليس حساباً نهائياً',
        'closed_period': 'الفترة المحاسبية مغلقة',
        'missing_period': 'الفترة المحاسبية غير موجودة',
        'no_active_period': 'لا توجد فترة محاسبية نشطة',
        'date_outside_period': 'التاريخ خارج نطاق الفترة المحاسبية',
    }
    
    # تحضير بيانات الجدول
    table_data = []
    for log in logs:
        # اسم المستخدم
        if log.user:
            if log.user.first_name or log.user.last_name:
                user_name = f"{log.user.first_name} {log.user.last_name}".strip()
            else:
                user_name = log.user.username
        else:
            user_name = "النظام"
        
        # ترجمة سبب الفشل
        failure_reason_ar = failure_reason_translations.get(
            log.failure_reason,
            log.failure_reason
        )
        
        # أيقونة نوع التحقق
        validation_icon = {
            'chart_of_accounts': 'fa-sitemap',
            'accounting_period': 'fa-calendar-alt',
            'both': 'fa-check-double'
        }.get(log.validation_type, 'fa-question')
        
        # لون الحالة
        status_class = 'danger' if not log.is_bypass_attempt else 'warning'
        
        actions = [
            {
                'url': reverse('financial:validation_log_detail', args=[log.pk]),
                'icon': 'fas fa-eye',
                'label': 'التفاصيل',
                'class': 'btn-outline-info btn-sm',
                'title': 'عرض التفاصيل الكاملة'
            }
        ]
        
        row = {
            'id': log.id,
            'timestamp': log.timestamp,
            'user': user_name,
            'entity_type': log.get_entity_type_display(),
            'entity_name': log.entity_name,
            'validation_type': f'<i class="fas {validation_icon} me-1"></i>{log.get_validation_type_display()}',
            'failure_reason': failure_reason_ar,
            'module': log.get_module_display(),
            'is_bypass': log.is_bypass_attempt,
            'status_class': status_class,
            'actions': actions
        }
        table_data.append(row)
    
    # رؤوس الجدول
    table_headers = [
        {'key': 'timestamp', 'label': 'التاريخ والوقت', 'sortable': True, 'width': '12%', 'format': 'datetime'},
        {'key': 'user', 'label': 'المستخدم', 'sortable': True, 'width': '10%'},
        {'key': 'entity_type', 'label': 'نوع الكيان', 'sortable': True, 'width': '10%', 'class': 'text-center'},
        {'key': 'entity_name', 'label': 'اسم الكيان', 'sortable': True, 'width': '15%'},
        {'key': 'validation_type', 'label': 'نوع التحقق', 'sortable': True, 'width': '12%', 'format': 'html', 'class': 'text-center'},
        {'key': 'failure_reason', 'label': 'سبب الفشل', 'width': '18%'},
        {'key': 'module', 'label': 'الوحدة', 'sortable': True, 'width': '10%', 'class': 'text-center'},
        {'key': 'is_bypass', 'label': 'محاولة تجاوز', 'sortable': True, 'width': '8%', 'format': 'boolean', 'class': 'text-center'},
        {'key': 'actions', 'label': 'الإجراءات', 'width': '5%', 'class': 'text-center'}
    ]
    
    context = {
        'active_menu': 'financial',
        'title': 'سجل الحركات الفاشلة',
        'days': days,
        'validation_type': validation_type,
        'entity_type': entity_type,
        'module': module,
        'search': search,
        'total_logs': logs.count(),
        
        # الجدول
        'table_headers': table_headers,
        'table_data': table_data,
        
        # الخيارات للتصفية
        'validation_type_choices': ValidationAuditLog.VALIDATION_TYPE_CHOICES,
        'entity_type_choices': ValidationAuditLog.ENTITY_TYPE_CHOICES,
        'module_choices': ValidationAuditLog.MODULE_CHOICES,
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('financial:validation_dashboard'),
                'icon': 'fa-chart-line',
                'text': 'لوحة المعلومات',
                'class': 'btn-outline-primary'
            },
            {
                'onclick': 'exportToExcel()',
                'icon': 'fa-file-excel',
                'text': 'تصدير Excel',
                'class': 'btn-success'
            },
        ],
        
        # مسار التنقل
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المالية', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-coins'},
            {'title': 'لوحة التحقق', 'url': reverse('financial:validation_dashboard'), 'icon': 'fas fa-chart-line'},
            {'title': 'سجل الحركات الفاشلة', 'active': True}
        ],
    }
    
    return render(request, 'financial/validation/logs_list.html', context)


@login_required
@permission_required('financial.view_validationauditlog', raise_exception=True)
def validation_log_detail(request, pk):
    """
    عرض تفاصيل محاولة تحقق فاشلة
    """
    log = get_object_or_404(ValidationAuditLog, pk=pk)
    
    # ترجمة سبب الفشل
    failure_reason_translations = {
        'missing_account': 'الحساب المحاسبي غير موجود',
        'invalid_account': 'الحساب المحاسبي غير صالح',
        'inactive_account': 'الحساب المحاسبي غير مفعّل',
        'not_leaf_account': 'الحساب المحاسبي ليس حساباً نهائياً',
        'closed_period': 'الفترة المحاسبية مغلقة',
        'missing_period': 'الفترة المحاسبية غير موجودة',
        'no_active_period': 'لا توجد فترة محاسبية نشطة',
        'date_outside_period': 'التاريخ خارج نطاق الفترة المحاسبية',
    }
    
    failure_reason_ar = failure_reason_translations.get(
        log.failure_reason,
        log.failure_reason
    )
    
    # اسم المستخدم
    if log.user:
        if log.user.first_name or log.user.last_name:
            user_name = f"{log.user.first_name} {log.user.last_name}".strip()
        else:
            user_name = log.user.username
    else:
        user_name = "النظام"
    
    context = {
        'active_menu': 'financial',
        'title': f'تفاصيل المحاولة #{log.id}',
        'log': log,
        'failure_reason_ar': failure_reason_ar,
        'user_name': user_name,
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('financial:validation_logs_list'),
                'icon': 'fa-arrow-right',
                'text': 'العودة للقائمة',
                'class': 'btn-outline-secondary'
            },
        ],
        
        # مسار التنقل
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المالية', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-coins'},
            {'title': 'لوحة التحقق', 'url': reverse('financial:validation_dashboard'), 'icon': 'fas fa-chart-line'},
            {'title': 'سجل الحركات', 'url': reverse('financial:validation_logs_list'), 'icon': 'fas fa-list'},
            {'title': f'المحاولة #{log.id}', 'active': True}
        ],
    }
    
    return render(request, 'financial/validation/log_detail.html', context)



@login_required
@permission_required('financial.view_validationauditlog', raise_exception=True)
def validation_audit_tool(request):
    """
    أداة تدقيق المعاملات المالية الموجودة
    """
    from django.core.management import call_command
    from io import StringIO
    import json
    
    result = None
    error = None
    
    if request.method == 'POST':
        # الحصول على المعاملات
        module = request.POST.get('module', 'all')
        check_type = request.POST.get('check_type', 'all')
        limit = request.POST.get('limit', '')
        
        try:
            # تشغيل الأمر
            out = StringIO()
            
            args = ['--module', module, '--check-type', check_type]
            if limit:
                args.extend(['--limit', limit])
            
            call_command('audit_existing_transactions', *args, stdout=out)
            
            # الحصول على النتيجة
            output = out.getvalue()
            
            # استخراج الإحصائيات من النص
            result = {
                'output': output,
                'success': True
            }
            
        except Exception as e:
            error = str(e)
    
    context = {
        'active_menu': 'financial',
        'title': 'أداة تدقيق المعاملات المالية',
        'result': result,
        'error': error,
        
        # الخيارات
        'module_choices': [
            ('all', 'جميع الوحدات'),
            ('financial', 'المالية'),
            ('client', 'العملاء'),
            ('activities', 'الأنشطة'),
            ('transportation', 'النقل'),
            ('hr', 'الموارد البشرية'),
            ('supplier', 'الموردين'),
        ],
        'check_type_choices': [
            ('all', 'كلاهما'),
            ('account', 'الحساب المحاسبي فقط'),
            ('period', 'الفترة المحاسبية فقط'),
        ],
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('financial:validation_dashboard'),
                'icon': 'fa-chart-line',
                'text': 'لوحة المعلومات',
                'class': 'btn-outline-primary'
            },
        ],
        
        # مسار التنقل
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المالية', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-coins'},
            {'title': 'لوحة التحقق', 'url': reverse('financial:validation_dashboard'), 'icon': 'fas fa-chart-line'},
            {'title': 'أداة التدقيق', 'active': True}
        ],
    }
    
    return render(request, 'financial/validation/audit_tool.html', context)
