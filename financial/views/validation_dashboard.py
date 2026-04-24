"""
عرض لوحة معلومات إحصائيات التحقق من المعاملات المالية
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django.urls import reverse
from datetime import timedelta
from collections import defaultdict

from financial.models.validation_audit_log import ValidationAuditLog


@login_required
@permission_required('financial.view_validationauditlog', raise_exception=True)
def validation_dashboard(request):
    """
    لوحة معلومات إحصائيات التحقق من المعاملات المالية
    
    عرض:
    - إحصائيات ValidationAuditLog (عدد المحاولات المرفوضة، أكثر الأخطاء شيوعاً)
    - الكيانات المعلمة للمراجعة
    - المستخدمين ذوي المحاولات المتكررة
    - رسوم بيانية باستخدام Chart.js
    """
    # الحصول على الفترة الزمنية من الطلب (افتراضي: 30 يوم)
    days = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)
    
    # الحصول على جميع السجلات في الفترة المحددة
    all_logs = ValidationAuditLog.objects.filter(timestamp__gte=since)
    
    # ========== الإحصائيات العامة ==========
    total_failures = all_logs.count()
    
    # عدد المحاولات المرفوضة حسب نوع التحقق
    failures_by_validation_type = dict(
        all_logs.values('validation_type')
        .annotate(count=Count('id'))
        .values_list('validation_type', 'count')
    )
    
    # عدد المحاولات المرفوضة حسب نوع الكيان
    failures_by_entity_type = dict(
        all_logs.values('entity_type')
        .annotate(count=Count('id'))
        .values_list('entity_type', 'count')
    )
    
    # عدد المحاولات المرفوضة حسب الوحدة
    failures_by_module = dict(
        all_logs.values('module')
        .annotate(count=Count('id'))
        .values_list('module', 'count')
    )
    
    # أكثر أسباب الفشل شيوعاً
    top_failure_reasons = list(
        all_logs.values('failure_reason')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    # ترجمة أسباب الفشل للعربية
    failure_reason_translations = {
        # أسباب متعلقة بالحساب المحاسبي
        'missing_account': 'الحساب المحاسبي غير موجود',
        'invalid_account': 'الحساب المحاسبي غير صالح',
        'inactive_account': 'الحساب المحاسبي غير مفعّل',
        'not_leaf_account': 'الحساب المحاسبي ليس حساباً نهائياً',
        'chart_of_accounts_missing': 'الحساب المحاسبي غير موجود',
        'chart_of_accounts_inactive': 'الحساب المحاسبي غير مفعّل',
        'chart_of_accounts_not_leaf': 'الحساب المحاسبي ليس حساباً نهائياً',
        
        # أسباب متعلقة بالفترة المحاسبية
        'missing_period': 'الفترة المحاسبية غير موجودة',
        'closed_period': 'الفترة المحاسبية مغلقة',
        'no_active_period': 'لا توجد فترة محاسبية نشطة',
        'accounting_period_missing': 'الفترة المحاسبية غير موجودة',
        'accounting_period_closed': 'الفترة المحاسبية مغلقة',
        'accounting_period_not_found': 'لم يتم العثور على فترة محاسبية',
        
        # أسباب أخرى
        'invalid_transaction_date': 'تاريخ المعاملة غير صحيح',
        'entity_missing_account': 'الكيان لا يحتوي على حساب محاسبي',
        'date_outside_period': 'التاريخ خارج نطاق الفترة المحاسبية',
    }
    
    for reason in top_failure_reasons:
        reason['failure_reason_ar'] = failure_reason_translations.get(
            reason['failure_reason'], 
            reason['failure_reason']
        )
    
    # ========== المستخدمين ذوي المحاولات المتكررة ==========
    # المستخدمين الذين لديهم أكثر من 3 محاولات فاشلة في آخر ساعة
    one_hour_ago = timezone.now() - timedelta(hours=1)
    recent_logs = ValidationAuditLog.objects.filter(timestamp__gte=one_hour_ago)
    
    users_with_repeated_attempts = list(
        recent_logs.values('user__id', 'user__username', 'user__first_name', 'user__last_name')
        .annotate(attempt_count=Count('id'))
        .filter(attempt_count__gt=3)
        .order_by('-attempt_count')[:20]
    )
    
    # إضافة اسم كامل للمستخدمين
    for user_data in users_with_repeated_attempts:
        if user_data['user__first_name'] or user_data['user__last_name']:
            user_data['full_name'] = f"{user_data['user__first_name']} {user_data['user__last_name']}".strip()
        else:
            user_data['full_name'] = user_data['user__username']
    
    # ========== الكيانات المعلمة للمراجعة ==========
    # الكيانات التي لديها أكثر من 5 محاولات فاشلة في آخر 24 ساعة
    twenty_four_hours_ago = timezone.now() - timedelta(hours=24)
    recent_entity_logs = ValidationAuditLog.objects.filter(timestamp__gte=twenty_four_hours_ago)
    
    flagged_entities = list(
        recent_entity_logs.values('entity_type', 'entity_id', 'entity_name')
        .annotate(failure_count=Count('id'))
        .filter(failure_count__gt=5)
        .order_by('-failure_count')[:20]
    )
    
    # إضافة ترجمة نوع الكيان
    entity_type_labels = dict(ValidationAuditLog.ENTITY_TYPE_CHOICES)
    for entity in flagged_entities:
        entity['entity_type_label'] = entity_type_labels.get(entity['entity_type'], entity['entity_type'])
    
    # ========== بيانات الرسوم البيانية ==========
    
    # 1. رسم بياني: المحاولات المرفوضة حسب اليوم (آخر 30 يوم)
    daily_failures = defaultdict(int)
    for log in all_logs:
        date_key = log.timestamp.date().isoformat()
        daily_failures[date_key] += 1
    
    # ترتيب البيانات حسب التاريخ
    sorted_dates = sorted(daily_failures.keys())
    daily_failures_labels = sorted_dates
    daily_failures_data = [daily_failures[date] for date in sorted_dates]
    
    # 2. رسم بياني: توزيع أنواع التحقق
    validation_type_labels = dict(ValidationAuditLog.VALIDATION_TYPE_CHOICES)
    validation_type_chart_labels = [
        validation_type_labels.get(vt, vt) 
        for vt in failures_by_validation_type.keys()
    ]
    validation_type_chart_data = list(failures_by_validation_type.values())
    
    # 3. رسم بياني: توزيع أنواع الكيانات
    entity_type_chart_labels = [
        entity_type_labels.get(et, et) 
        for et in failures_by_entity_type.keys()
    ]
    entity_type_chart_data = list(failures_by_entity_type.values())
    
    # 4. رسم بياني: توزيع الوحدات
    module_labels = dict(ValidationAuditLog.MODULE_CHOICES)
    module_chart_labels = [
        module_labels.get(m, m) 
        for m in failures_by_module.keys()
    ]
    module_chart_data = list(failures_by_module.values())
    
    # 5. رسم بياني: أكثر المستخدمين محاولات فاشلة
    top_users = list(
        all_logs.exclude(user__isnull=True)
        .values('user__username', 'user__first_name', 'user__last_name')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    top_users_labels = []
    for user in top_users:
        if user['user__first_name'] or user['user__last_name']:
            full_name = f"{user['user__first_name']} {user['user__last_name']}".strip()
        else:
            full_name = user['user__username']
        top_users_labels.append(full_name)
    
    top_users_data = [user['count'] for user in top_users]
    
    # ========== إحصائيات إضافية ==========
    
    # عدد محاولات التجاوز
    bypass_attempts_count = all_logs.filter(is_bypass_attempt=True).count()
    
    # عدد المستخدمين الفريدين
    unique_users_count = all_logs.exclude(user__isnull=True).values('user').distinct().count()
    
    # عدد الكيانات الفريدة
    unique_entities_count = all_logs.values('entity_type', 'entity_id').distinct().count()
    
    # متوسط المحاولات الفاشلة في اليوم
    avg_daily_failures = total_failures / max(days, 1)
    
    # ========== السياق ==========
    context = {
        'active_menu': 'financial',
        'title': 'لوحة معلومات التحقق من المعاملات المالية',
        'days': days,
        
        # أزرار الهيدر
        'header_buttons': [
            {
                'url': reverse('financial:validation_logs_list'),
                'icon': 'fa-list',
                'text': 'سجل الحركات الفاشلة',
                'class': 'btn-primary'
            },
            {
                'url': reverse('financial:validation_fix_dashboard'),
                'icon': 'fa-wrench',
                'text': 'إصلاح المشاكل',
                'class': 'btn-success'
            },
            {
                'url': reverse('financial:validation_audit_tool'),
                'icon': 'fa-tools',
                'text': 'أداة التدقيق',
                'class': 'btn-warning'
            },
        ],
        
        # الإحصائيات العامة
        'total_failures': total_failures,
        'bypass_attempts_count': bypass_attempts_count,
        'unique_users_count': unique_users_count,
        'unique_entities_count': unique_entities_count,
        'avg_daily_failures': round(avg_daily_failures, 2),
        
        # التوزيعات
        'failures_by_validation_type': failures_by_validation_type,
        'failures_by_entity_type': failures_by_entity_type,
        'failures_by_module': failures_by_module,
        'top_failure_reasons': top_failure_reasons,
        
        # المستخدمين والكيانات
        'users_with_repeated_attempts': users_with_repeated_attempts,
        'flagged_entities': flagged_entities,
        
        # بيانات الرسوم البيانية
        'daily_failures_labels': daily_failures_labels,
        'daily_failures_data': daily_failures_data,
        'validation_type_chart_labels': validation_type_chart_labels,
        'validation_type_chart_data': validation_type_chart_data,
        'entity_type_chart_labels': entity_type_chart_labels,
        'entity_type_chart_data': entity_type_chart_data,
        'module_chart_labels': module_chart_labels,
        'module_chart_data': module_chart_data,
        'top_users_labels': top_users_labels,
        'top_users_data': top_users_data,
        
        # مسار التنقل
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المالية', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-coins'},
            {'title': 'لوحة معلومات التحقق', 'active': True}
        ],
    }
    
    return render(request, 'financial/validation/dashboard.html', context)
