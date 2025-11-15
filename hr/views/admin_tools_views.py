from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q
from hr.models import SalaryComponent, Employee
from hr.services.component_classification_service import ComponentClassificationService
import json


def is_admin_user(user):
    """التحقق من صلاحيات الإدارة"""
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(is_admin_user)
def maintenance_overview(request):
    """صفحة نظرة عامة على أدوات الصيانة"""
    
    # إحصائيات عامة
    total_components = SalaryComponent.objects.count()
    active_components = SalaryComponent.objects.filter(is_active=True).count()
    
    # البنود المنتهية
    expired_components = SalaryComponent.objects.filter(
        effective_to__lt=timezone.now().date(),
        is_active=True
    ).count()
    
    # البنود التي ستنتهي قريباً (خلال 30 يوم)
    soon_expiring = SalaryComponent.objects.filter(
        effective_to__gte=timezone.now().date(),
        effective_to__lte=timezone.now().date() + timedelta(days=30),
        is_active=True
    ).count()
    
    # إحصائيات حسب النوع
    source_stats = []
    for source, name in SalaryComponent.COMPONENT_SOURCE_CHOICES:
        count = SalaryComponent.objects.filter(source=source, is_active=True).count()
        source_stats.append({
            'source': source,
            'name': name,
            'count': count
        })
    
    # البنود غير المصنفة (تحتاج مراجعة)
    unclassified_count = SalaryComponent.objects.filter(
        Q(source='contract') & Q(is_from_contract=False)
    ).count()
    
    context = {
        'total_components': total_components,
        'active_components': active_components,
        'inactive_components': total_components - active_components,
        'expired_components': expired_components,
        'soon_expiring': soon_expiring,
        'source_stats': source_stats,
        'unclassified_count': unclassified_count,
    }
    
    return render(request, 'hr/admin/maintenance_overview.html', context)


@login_required
@user_passes_test(is_admin_user)
def cleanup_expired_components(request):
    """تنظيف البنود المنتهية"""
    
    if request.method == 'POST':
        days_threshold = int(request.POST.get('days_threshold', 30))
        confirm = request.POST.get('confirm') == 'true'
        
        cutoff_date = timezone.now().date() - timedelta(days=days_threshold)
        expired_components = SalaryComponent.objects.filter(
            effective_to__lt=cutoff_date,
            is_active=True
        )
        
        if confirm:
            # تطبيق التنظيف
            updated_count = expired_components.update(is_active=False)
            messages.success(
                request, 
                f'تم إلغاء تفعيل {updated_count} بند منتهي الصلاحية بنجاح'
            )
            return redirect('hr:maintenance_overview')
        else:
            # معاينة فقط
            components_list = list(expired_components.values(
                'id', 'employee__name', 'name', 'effective_to'
            ))
            
            return JsonResponse({
                'success': True,
                'count': expired_components.count(),
                'components': components_list
            })
    
    return JsonResponse({'success': False, 'message': 'طريقة طلب غير صحيحة'})


@login_required
@user_passes_test(is_admin_user)
def auto_classify_components(request):
    """تصنيف البنود تلقائياً"""
    
    if request.method == 'POST':
        confirm = request.POST.get('confirm') == 'true'
        
        # البنود التي تحتاج تصنيف
        unclassified_components = SalaryComponent.objects.filter(
            Q(source='contract') & Q(is_from_contract=False)
        )
        
        classification_service = ComponentClassificationService()
        changes = []
        
        for component in unclassified_components:
            old_source = component.source
            suggested_source = classification_service.suggest_component_source(component)
            
            if suggested_source != old_source:
                changes.append({
                    'id': component.id,
                    'employee_name': component.employee.name,
                    'component_name': component.name,
                    'old_source': old_source,
                    'new_source': suggested_source
                })
                
                if confirm:
                    component.source = suggested_source
                    component.save()
        
        if confirm:
            messages.success(
                request, 
                f'تم تصنيف {len(changes)} بند تلقائياً'
            )
            return redirect('hr:maintenance_overview')
        else:
            return JsonResponse({
                'success': True,
                'changes': changes
            })
    
    return JsonResponse({'success': False, 'message': 'طريقة طلب غير صحيحة'})


@login_required
@user_passes_test(is_admin_user)
def backup_components_data(request):
    """إنشاء نسخة احتياطية من بيانات البنود"""
    
    if request.method == 'POST':
        # جمع جميع بيانات البنود
        components_data = []
        
        for component in SalaryComponent.objects.all():
            components_data.append({
                'id': component.id,
                'employee_id': component.employee.id,
                'employee_name': component.employee.name,
                'name': component.name,
                'amount': float(component.amount),
                'component_type': component.component_type,
                'source': component.source,
                'is_active': component.is_active,
                'is_recurring': component.is_recurring,
                'auto_renew': component.auto_renew,
                'renewal_period_months': component.renewal_period_months,
                'effective_from': component.effective_from.isoformat() if component.effective_from else None,
                'effective_to': component.effective_to.isoformat() if component.effective_to else None,
                'is_from_contract': component.is_from_contract,
                'created_at': component.created_at.isoformat(),
                'updated_at': component.updated_at.isoformat(),
            })
        
        # إنشاء ملف النسخة الاحتياطية
        backup_data = {
            'backup_date': timezone.now().isoformat(),
            'total_components': len(components_data),
            'components': components_data
        }
        
        # إرجاع البيانات كـ JSON للتحميل
        response = JsonResponse(backup_data, json_dumps_params={'indent': 2, 'ensure_ascii': False})
        response['Content-Disposition'] = f'attachment; filename="salary_components_backup_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json"'
        
        return response
    
    return JsonResponse({'success': False, 'message': 'طريقة طلب غير صحيحة'})


@login_required
@user_passes_test(is_admin_user)
def component_statistics_api(request):
    """API لإحصائيات البنود (للرسوم البيانية)"""
    
    # إحصائيات حسب النوع
    source_data = []
    for source, name in SalaryComponent.COMPONENT_SOURCE_CHOICES:
        count = SalaryComponent.objects.filter(source=source, is_active=True).count()
        source_data.append({
            'label': name,
            'value': count,
            'source': source
        })
    
    # إحصائيات حسب الموظف (أعلى 10)
    employee_data = SalaryComponent.objects.filter(is_active=True)\
        .values('employee__name')\
        .annotate(count=Count('id'))\
        .order_by('-count')[:10]
    
    # إحصائيات حسب النوع (استحقاق/خصم)
    type_data = SalaryComponent.objects.filter(is_active=True)\
        .values('component_type')\
        .annotate(count=Count('id'))
    
    return JsonResponse({
        'source_distribution': source_data,
        'top_employees': list(employee_data),
        'type_distribution': list(type_data)
    })
