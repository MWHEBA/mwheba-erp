# -*- coding: utf-8 -*-
"""
عرض الأخطاء والـ Logs للـ Admin
"""
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.conf import settings
from pathlib import Path
import os


def is_superuser(user):
    """التحقق من أن المستخدم admin"""
    return user.is_superuser


@login_required
@user_passes_test(is_superuser)
def view_error_logs(request):
    """عرض آخر 200 سطر من ملف الأخطاء"""
    from django.urls import reverse
    
    log_file = settings.BASE_DIR / 'logs' / 'django.log'
    
    context = {
        'log_exists': False,
        'log_lines': [],
        'log_file_path': str(log_file),
        'log_size': 0,
        
        # بيانات الهيدر
        'page_title': 'سجل الأخطاء',
        'page_subtitle': 'عرض وإدارة سجلات الأخطاء والـ Logs في النظام',
        'page_icon': 'fas fa-file-alt',
        
        # البريدكرمب
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الإعدادات', 'url': reverse('core:system_settings'), 'icon': 'fas fa-cog'},
            {'title': 'سجل الأخطاء', 'active': True},
        ],
    }
    
    if log_file.exists():
        context['log_exists'] = True
        context['log_size'] = os.path.getsize(log_file)
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                # اقرأ آخر 200 سطر
                lines = f.readlines()
                context['log_lines'] = lines[-200:]
                context['total_lines'] = len(lines)
        except Exception as e:
            context['error'] = str(e)
    
    return render(request, 'core/error_logs.html', context)


@login_required
@user_passes_test(is_superuser)
def clear_error_logs(request):
    """مسح ملف الأخطاء"""
    if request.method == 'POST':
        log_file = settings.BASE_DIR / 'logs' / 'django.log'
        
        if log_file.exists():
            try:
                # امسح محتوى الملف
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write('')
                
                from django.contrib import messages
                messages.success(request, 'تم مسح ملف الأخطاء بنجاح')
            except Exception as e:
                from django.contrib import messages
                messages.error(request, f'فشل مسح الملف: {str(e)}')
    
    from django.shortcuts import redirect
    return redirect('core:view_error_logs')
