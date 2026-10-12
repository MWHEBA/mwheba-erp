"""
Views لإدارة تطبيقات النظام
"""
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.core.cache import cache
from core.models import SystemModule, SystemSetting
import logging

logger = logging.getLogger(__name__)


@login_required
@user_passes_test(lambda u: u.is_authenticated and (u.is_superuser or getattr(u, 'is_admin', False)))
def module_management(request):
    """
    صفحة إدارة تطبيقات النظام
    """
    if request.method == 'POST':
        module_code = request.POST.get('module_code')
        action = request.POST.get('action')
        
        # حماية الصلاحيات: التحكم في منظومة WhatsApp مقتصر حصرياً على المدير العام Superuser
        if module_code == 'whatsapp' and not request.user.is_superuser:
            messages.error(request, 'عذراً، التحكم في منظومة WhatsApp مقتصر حصرياً على المدير العام (Superuser)')
            return redirect('core:module_management')

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
                    # فحص الجاهزية الفنية لمنظومة WhatsApp
                    if module.code == 'whatsapp':
                        from core.services.whatsapp_service import WhatsAppService
                        config = WhatsAppService.get_config()
                        if not (config.get('phone_number_id') and config.get('access_token')):
                            messages.warning(request, 'تنبيه: تم تفعيل الموديول، ولكن لا يوجد حساب WhatsApp مربوط وجاهز بعد. يرجى إعداد بيانات الربط والـ API.')

                    module.is_enabled = True
                    module.save()
                    _log_module_audit(request, module, 'ENABLE')
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
                    # إيقاف الحملات النشطة مؤقتاً بأمان عند تعطيل منظومة WhatsApp
                    if module.code == 'whatsapp':
                        try:
                            from core.models import WhatsAppCampaign
                            paused_count = WhatsAppCampaign.objects.filter(status='RUNNING').update(status='PAUSED')
                            if paused_count > 0:
                                messages.info(request, f'تم إيقاف مؤقت لـ {paused_count} حملة تسويقية نشطة لحماية رصيد ورقم الحساب')
                        except Exception:
                            pass

                    module.is_enabled = False
                    module.save()
                    _log_module_audit(request, module, 'DISABLE')
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
    
    # فحص الجاهزية الفنية للواتساب لعرض الشارة الحية
    whatsapp_is_connected = False
    try:
        from core.services.whatsapp_service import WhatsAppService
        cfg = WhatsAppService.get_config()
        whatsapp_is_connected = bool(cfg.get('access_token') and cfg.get('phone_number_id'))
    except Exception:
        pass

    context = {
        'title': 'إدارة تطبيقات النظام',
        'core_modules': core_modules,
        'optional_modules': optional_modules,
        'whatsapp_is_connected': whatsapp_is_connected,
        'active_menu': 'settings',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fa-home'},
            {'title': 'الإعدادات', 'url': None, 'icon': 'fa-cogs'},
            {'title': 'تطبيقات النظام', 'active': True}
        ],
    }
    
    return render(request, 'core/module_management.html', context)


def _log_module_audit(request, module, action_type):
    """توثيق عملية تفعيل أو تعطيل التطبيق في سجل الحوكمة والرقابة"""
    try:
        from governance.services import AuditService
        AuditService.log_action(
            user=request.user,
            action=f"MODULE_{action_type}",
            model_name="SystemModule",
            object_id=str(module.id),
            details={
                "code": module.code,
                "name": module.name_ar,
                "is_enabled": module.is_enabled
            },
            ip_address=request.META.get('REMOTE_ADDR')
        )
    except Exception as e:
        logger.debug(f"Audit log skipped for module toggle: {e}")


def _clear_modules_cache():
    """مسح كاش التطبيقات والإعدادات العامة لحظياً"""
    cache.delete('enabled_modules_dict')
    cache.delete('enabled_modules_dict_v2')
    cache.delete('enabled_modules_set')
    cache.delete('module_enabled_whatsapp')
    SystemSetting.invalidate_all_system_caches()
    try:
        from core.services.whatsapp_service import WhatsAppService
        WhatsAppService.reset_session()
    except Exception:
        pass
    try:
        cache.delete_pattern('module_enabled_*')
    except AttributeError:
        pass
