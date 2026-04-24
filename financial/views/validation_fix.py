"""
عرض لإصلاح المعاملات الفاشلة في التحقق
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from financial.models.validation_audit_log import ValidationAuditLog
from financial.models.chart_of_accounts import ChartOfAccounts
from financial.models.journal_entry import AccountingPeriod
from financial.services.entity_mapper import EntityAccountMapper


@login_required
@permission_required('financial.change_chartofaccounts', raise_exception=True)
def validation_fix_dashboard(request):
    """
    لوحة معلومات إصلاح المشاكل
    """
    # الحصول على المشاكل الشائعة
    from datetime import timedelta
    from django.db.models import Count
    
    since = timezone.now() - timedelta(days=30)
    logs = ValidationAuditLog.objects.filter(timestamp__gte=since)
    
    # تجميع المشاكل حسب النوع
    problems = {
        'missing_accounts': [],
        'inactive_accounts': [],
        'closed_periods': [],
        'missing_periods': [],
    }
    
    # المشاكل المتعلقة بالحسابات
    account_issues = logs.filter(
        failure_reason__in=['missing_account', 'invalid_account', 'inactive_account']
    ).values('entity_type', 'entity_id', 'entity_name', 'failure_reason').annotate(
        count=Count('id')
    ).order_by('-count')[:20]
    
    for issue in account_issues:
        if issue['failure_reason'] == 'missing_account':
            problems['missing_accounts'].append(issue)
        elif issue['failure_reason'] == 'inactive_account':
            problems['inactive_accounts'].append(issue)
    
    # المشاكل المتعلقة بالفترات
    period_issues = logs.filter(
        failure_reason__in=['closed_period', 'missing_period', 'no_active_period']
    ).values('transaction_date', 'failure_reason').annotate(
        count=Count('id')
    ).order_by('-count')[:20]
    
    for issue in period_issues:
        if issue['failure_reason'] == 'closed_period':
            problems['closed_periods'].append(issue)
        elif issue['failure_reason'] in ['missing_period', 'no_active_period']:
            problems['missing_periods'].append(issue)
    
    context = {
        'active_menu': 'financial',
        'title': 'إصلاح المشاكل المالية',
        'problems': problems,
        
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
            {'title': 'إصلاح المشاكل', 'active': True}
        ],
    }
    
    return render(request, 'financial/validation/fix_dashboard.html', context)


@login_required
@permission_required('financial.change_chartofaccounts', raise_exception=True)
def fix_missing_account(request, entity_type, entity_id):
    """
    إصلاح مشكلة الحساب المحاسبي المفقود
    """
    if request.method == 'POST':
        account_id = request.POST.get('account_id')
        
        if not account_id:
            messages.error(request, 'يرجى اختيار حساب محاسبي')
            return redirect('financial:validation_fix_dashboard')
        
        try:
            account = ChartOfAccounts.objects.get(id=account_id)
            
            # الحصول على الكيان
            entity = EntityAccountMapper.get_entity_by_type(entity_type, entity_id)
            
            if not entity:
                messages.error(request, 'لم يتم العثور على الكيان')
                return redirect('financial:validation_fix_dashboard')
            
            # ربط الحساب بالكيان
            field_name = EntityAccountMapper.ENTITY_ACCOUNT_FIELDS.get(entity_type)
            if field_name:
                # دعم الحقول المتداخلة (مثل parent.financial_account)
                if '.' in field_name:
                    parts = field_name.split('.')
                    target = entity
                    # التنقل عبر الحقول المتداخلة
                    for part in parts[:-1]:
                        target = getattr(target, part)
                        if target is None:
                            messages.error(request, f'الحقل {part} غير موجود أو None')
                            return redirect('financial:validation_fix_dashboard')
                    # تعيين القيمة للحقل النهائي
                    setattr(target, parts[-1], account)
                    target.save()
                else:
                    # حقل بسيط (غير متداخل)
                    setattr(entity, field_name, account)
                    entity.save()
                
                messages.success(
                    request,
                    f'تم ربط الحساب المحاسبي "{account.name}" بـ "{entity}" بنجاح'
                )
            else:
                messages.error(request, 'نوع الكيان غير مدعوم')
        
        except ChartOfAccounts.DoesNotExist:
            messages.error(request, 'الحساب المحاسبي غير موجود')
        except Exception as e:
            messages.error(request, f'حدث خطأ: {str(e)}')
        
        return redirect('financial:validation_fix_dashboard')
    
    # GET request - عرض نموذج الإصلاح
    entity = EntityAccountMapper.get_entity_by_type(entity_type, entity_id)
    
    if not entity:
        messages.error(request, 'لم يتم العثور على الكيان')
        return redirect('financial:validation_fix_dashboard')
    
    # الحصول على الحسابات المتاحة
    accounts = ChartOfAccounts.objects.filter(
        is_active=True,
        is_leaf=True
    ).order_by('code')
    
    context = {
        'active_menu': 'financial',
        'title': 'إصلاح الحساب المحاسبي المفقود',
        'entity': entity,
        'entity_type': entity_type,
        'entity_id': entity_id,
        'accounts': accounts,
        
        # مسار التنقل
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المالية', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-coins'},
            {'title': 'إصلاح المشاكل', 'url': reverse('financial:validation_fix_dashboard'), 'icon': 'fas fa-wrench'},
            {'title': 'إصلاح الحساب المحاسبي', 'active': True}
        ],
    }
    
    return render(request, 'financial/validation/fix_missing_account.html', context)


@login_required
@permission_required('financial.change_chartofaccounts', raise_exception=True)
def fix_inactive_account(request, entity_type, entity_id):
    """
    إصلاح مشكلة الحساب المحاسبي غير المفعّل
    """
    if request.method == 'POST':
        action = request.POST.get('action')
        
        try:
            # الحصول على الكيان
            entity = EntityAccountMapper.get_entity_by_type(entity_type, entity_id)
            
            if not entity:
                messages.error(request, 'لم يتم العثور على الكيان')
                return redirect('financial:validation_fix_dashboard')
            
            # الحصول على الحساب الحالي
            field_name = EntityAccountMapper.ENTITY_ACCOUNT_FIELDS.get(entity_type)
            if not field_name:
                messages.error(request, 'نوع الكيان غير مدعوم')
                return redirect('financial:validation_fix_dashboard')
            
            # دعم الحقول المتداخلة
            if '.' in field_name:
                parts = field_name.split('.')
                account = entity
                for part in parts:
                    account = getattr(account, part, None)
                    if account is None:
                        break
            else:
                account = getattr(entity, field_name)
            
            if not account:
                messages.error(request, 'لا يوجد حساب محاسبي مرتبط')
                return redirect('financial:validation_fix_dashboard')
            
            if action == 'activate':
                # تفعيل الحساب
                account.is_active = True
                account.save()
                
                messages.success(
                    request,
                    f'تم تفعيل الحساب المحاسبي "{account.name}" بنجاح'
                )
            
            elif action == 'replace':
                # استبدال الحساب
                new_account_id = request.POST.get('new_account_id')
                
                if not new_account_id:
                    messages.error(request, 'يرجى اختيار حساب محاسبي جديد')
                    return redirect('financial:validation_fix_dashboard')
                
                new_account = ChartOfAccounts.objects.get(id=new_account_id)
                
                # دعم الحقول المتداخلة
                if '.' in field_name:
                    parts = field_name.split('.')
                    target = entity
                    for part in parts[:-1]:
                        target = getattr(target, part)
                        if target is None:
                            messages.error(request, f'الحقل {part} غير موجود أو None')
                            return redirect('financial:validation_fix_dashboard')
                    setattr(target, parts[-1], new_account)
                    target.save()
                else:
                    setattr(entity, field_name, new_account)
                    entity.save()
                
                messages.success(
                    request,
                    f'تم استبدال الحساب المحاسبي بـ "{new_account.name}" بنجاح'
                )
        
        except ChartOfAccounts.DoesNotExist:
            messages.error(request, 'الحساب المحاسبي غير موجود')
        except Exception as e:
            messages.error(request, f'حدث خطأ: {str(e)}')
        
        return redirect('financial:validation_fix_dashboard')
    
    # GET request
    entity = EntityAccountMapper.get_entity_by_type(entity_type, entity_id)
    
    if not entity:
        messages.error(request, 'لم يتم العثور على الكيان')
        return redirect('financial:validation_fix_dashboard')
    
    # الحصول على الحساب الحالي
    field_name = EntityAccountMapper.ENTITY_ACCOUNT_FIELDS.get(entity_type)
    
    # دعم الحقول المتداخلة
    current_account = None
    if field_name:
        if '.' in field_name:
            parts = field_name.split('.')
            current_account = entity
            for part in parts:
                current_account = getattr(current_account, part, None)
                if current_account is None:
                    break
        else:
            current_account = getattr(entity, field_name, None)
    
    # الحسابات البديلة
    alternative_accounts = ChartOfAccounts.objects.filter(
        is_active=True,
        is_leaf=True
    ).exclude(id=current_account.id if current_account else None).order_by('code')
    
    context = {
        'active_menu': 'financial',
        'title': 'إصلاح الحساب المحاسبي غير المفعّل',
        'entity': entity,
        'entity_type': entity_type,
        'entity_id': entity_id,
        'current_account': current_account,
        'alternative_accounts': alternative_accounts,
        
        # مسار التنقل
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المالية', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-coins'},
            {'title': 'إصلاح المشاكل', 'url': reverse('financial:validation_fix_dashboard'), 'icon': 'fas fa-wrench'},
            {'title': 'إصلاح الحساب غير المفعّل', 'active': True}
        ],
    }
    
    return render(request, 'financial/validation/fix_inactive_account.html', context)


@login_required
@permission_required('financial.add_accountingperiod', raise_exception=True)
def fix_missing_period(request):
    """
    إصلاح مشكلة الفترة المحاسبية المفقودة
    """
    if request.method == 'POST':
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        name = request.POST.get('name')
        
        try:
            # إنشاء فترة محاسبية جديدة
            period = AccountingPeriod.objects.create(
                name=name,
                start_date=start_date,
                end_date=end_date,
                status='open'
            )
            
            messages.success(
                request,
                f'تم إنشاء الفترة المحاسبية "{period.name}" بنجاح'
            )
        
        except Exception as e:
            messages.error(request, f'حدث خطأ: {str(e)}')
        
        return redirect('financial:validation_fix_dashboard')
    
    # GET request
    context = {
        'active_menu': 'financial',
        'title': 'إنشاء فترة محاسبية جديدة',
        
        # مسار التنقل
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المالية', 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fas fa-coins'},
            {'title': 'إصلاح المشاكل', 'url': reverse('financial:validation_fix_dashboard'), 'icon': 'fas fa-wrench'},
            {'title': 'إنشاء فترة محاسبية', 'active': True}
        ],
    }
    
    return render(request, 'financial/validation/fix_missing_period.html', context)
