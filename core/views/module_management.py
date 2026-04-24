"""
Views لإدارة تطبيقات النظام
"""
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.cache import cache
from core.models import SystemModule


@login_required
@user_passes_test(lambda u: u.is_superuser)
def module_management(request):
    """
    صفحة إدارة تطبيقات النظام
    """
    if request.method == 'POST':
        module_code = request.POST.get('module_code')
        action = request.POST.get('action')
        
        try:
            module = SystemModule.objects.get(code=module_code)
            
            if action == 'enable':
                # التحقق من التطبيقات المطلوبة
                deps_status = module.get_dependencies_status()
                if not deps_status['all_enabled']:
                    missing_names = ', '.join([dep.name_ar for dep in deps_status['missing']])
                    messages.error(request, 
                        f'يجب تفعيل التطبيقات التالية أولاً: {missing_names}')
                else:
                    module.is_enabled = True
                    module.save()
                    # مسح الكاش
                    _clear_modules_cache()
                    messages.success(request, f'تم تفعيل تطبيق {module.name_ar}')
            
            elif action == 'disable':
                if not module.can_disable():
                    if module.module_type == 'core':
                        messages.error(request, 'لا يمكن تعطيل التطبيقات الأساسية')
                    else:
                        dependent = module.dependent_modules.filter(is_enabled=True).first()
                        if dependent:
                            messages.error(request, 
                                f'لا يمكن تعطيل هذا التطبيق لأن "{dependent.name_ar}" يعتمد عليه')
                else:
                    module.is_enabled = False
                    module.save()
                    _clear_modules_cache()
                    messages.success(request, f'تم تعطيل تطبيق {module.name_ar}')
        
        except SystemModule.DoesNotExist:
            messages.error(request, 'التطبيق غير موجود')
        
        return redirect('core:module_management')
    
    # جلب جميع التطبيقات
    modules = SystemModule.objects.all().prefetch_related('required_modules', 'dependent_modules')
    
    # تقسيم التطبيقات
    core_modules = modules.filter(module_type='core')
    optional_modules = modules.filter(module_type='optional')
    
    context = {
        'title': 'إدارة تطبيقات النظام',
        'core_modules': core_modules,
        'optional_modules': optional_modules,
        'active_menu': 'settings',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': '/'},
            {'title': 'الإعدادات', 'url': None},
            {'title': 'تطبيقات النظام', 'active': True}
        ],
    }
    
    return render(request, 'core/module_management.html', context)


def _clear_modules_cache():
    """مسح كاش التطبيقات"""
    cache.delete('enabled_modules_dict')
    cache.delete('enabled_modules_set')
    # مسح جميع الكاش الخاص بالتطبيقات الفردية
    try:
        cache.delete_pattern('module_enabled_*')
    except AttributeError:
        # في حالة استخدام backend لا يدعم delete_pattern
        pass
