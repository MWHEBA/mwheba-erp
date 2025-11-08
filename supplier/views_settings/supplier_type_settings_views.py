"""عروض إدارة أنواع الموردين"""
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.db.models import Q
from django.urls import reverse

from ..models import SupplierTypeSettings
from ..forms.supplier_type_forms import (
    SupplierTypeSettingsForm,
    SupplierTypeReorderForm,
    SupplierTypeDeleteForm,
    SupplierTypeBulkActionForm
)


@login_required
def supplier_type_settings_list(request):
    """عرض قائمة إعدادات أنواع الموردين"""
    
    # فلترة وبحث
    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '')  # all, active, inactive
    
    # جلب البيانات
    supplier_types = SupplierTypeSettings.objects.all()
    
    # تطبيق الفلاتر
    if search:
        supplier_types = supplier_types.filter(
            Q(name__icontains=search) |
            Q(code__icontains=search) |
            Q(description__icontains=search)
        )
    
    if status == 'active':
        supplier_types = supplier_types.filter(is_active=True)
    elif status == 'inactive':
        supplier_types = supplier_types.filter(is_active=False)
    
    # ترتيب النتائج
    supplier_types = supplier_types.order_by('display_order', 'name')
    
    # تقسيم الصفحات
    paginator = Paginator(supplier_types, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # إحصائيات
    stats = {
        'total': SupplierTypeSettings.objects.count(),
        'active': SupplierTypeSettings.objects.filter(is_active=True).count(),
        'inactive': SupplierTypeSettings.objects.filter(is_active=False).count(),
        'system': SupplierTypeSettings.objects.filter(is_system=True).count(),
    }
    
    context = {
        'page_obj': page_obj,
        'supplier_types': page_obj.object_list,
        'stats': stats,
        'search': search,
        'status': status,
        'page_title': _('إعدادات أنواع الموردين'),
        'page_subtitle': 'إدارة وتخصيص أنواع الموردين والخدمات',
        'page_icon': 'fas fa-tags',
        'header_buttons': [
            {
                'onclick': "openModal('createModal')",
                'icon': 'fa-plus',
                'text': 'إضافة نوع جديد',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': 'الإعدادات', 'icon': 'fas fa-cog'},
            {'title': 'أنواع الموردين', 'active': True},
        ],
    }
    
    return render(request, 'supplier/settings/supplier_types/list.html', context)


@login_required
def supplier_type_settings_create(request):
    """إضافة نوع مورد جديد - حل جذري"""
    
    if request.method == 'POST':
        # حل جذري - إنشاء النوع مباشرة
        try:
            # جلب البيانات من الطلب
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip()
            description = request.POST.get('description', '').strip()
            icon = request.POST.get('icon', 'fas fa-truck').strip()
            color = request.POST.get('color', '#007bff').strip()
            display_order = request.POST.get('display_order', '0')
            is_active = request.POST.get('is_active') == 'on'
            
            # التحقق من البيانات الأساسية
            if not name:
                raise ValueError("اسم النوع مطلوب")
            if not code:
                raise ValueError("رمز النوع مطلوب")
            
            # التحقق من عدم تكرار الرمز
            if SupplierTypeSettings.objects.filter(code=code).exists():
                raise ValueError("هذا الرمز مستخدم بالفعل")
            
            # إنشاء النوع الجديد
            supplier_type = SupplierTypeSettings.objects.create(
                name=name,
                code=code,
                description=description,
                icon=icon,
                color=color,
                display_order=int(display_order) if display_order.isdigit() else 0,
                is_active=is_active,
                created_by=request.user,
                updated_by=request.user
            )
            
            success_message = f'تم إضافة نوع المورد "{name}" بنجاح'
            messages.success(request, success_message)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_message,
                })
            
            return redirect('supplier:supplier_type_settings_list')
            
        except Exception as e:
            error_message = f'حدث خطأ: {str(e)}'
            messages.error(request, error_message)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                })
    
    # إنشاء نموذج فارغ للعرض
    form = SupplierTypeSettingsForm()
    
    context = {
        'form': form,
        'title': 'إضافة نوع مورد جديد',
        'action_url': request.path,
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'supplier/settings/supplier_types/form_modal.html', context)
    else:
        return redirect('supplier:supplier_type_settings_list')


@login_required
def supplier_type_settings_edit(request, pk):
    """تعديل نوع مورد"""
    supplier_type = get_object_or_404(SupplierTypeSettings, pk=pk)
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            code = request.POST.get('code', '').strip()
            description = request.POST.get('description', '').strip()
            icon = request.POST.get('icon', 'fas fa-truck').strip()
            color = request.POST.get('color', '#007bff').strip()
            display_order = request.POST.get('display_order', '0')
            is_active = request.POST.get('is_active') == 'on'
            
            # التحقق من البيانات الأساسية
            if not name:
                raise ValueError("اسم النوع مطلوب")
            if not code:
                raise ValueError("رمز النوع مطلوب")
            
            # التحقق من عدم تكرار الرمز
            existing = SupplierTypeSettings.objects.filter(code=code).exclude(pk=pk)
            if existing.exists():
                raise ValueError("هذا الرمز مستخدم بالفعل")
            
            supplier_type.name = name
            supplier_type.code = code
            supplier_type.description = description
            supplier_type.icon = icon
            supplier_type.color = color
            supplier_type.display_order = int(display_order) if display_order.isdigit() else 0
            supplier_type.is_active = is_active
            supplier_type.updated_by = request.user
            supplier_type.save()
            
            success_message = f'تم تحديث نوع المورد "{name}" بنجاح'
            messages.success(request, success_message)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': success_message,
                })
            
            return redirect('supplier:supplier_type_settings_list')
            
        except Exception as e:
            error_message = f'حدث خطأ: {str(e)}'
            messages.error(request, error_message)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': error_message,
                })
    
    # إنشاء النموذج للعرض
    form = SupplierTypeSettingsForm(instance=supplier_type)
    
    context = {
        'form': form,
        'supplier_type': supplier_type,
        'title': f'تعديل نوع المورد: {supplier_type.name}',
        'action_url': request.path,
    }
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'supplier/settings/supplier_types/form_modal.html', context)
    else:
        return redirect('supplier:supplier_type_settings_list')


@login_required
def supplier_type_settings_delete(request, pk):
    """حذف نوع مورد"""
    
    supplier_type = get_object_or_404(SupplierTypeSettings, pk=pk)
    
    if request.method == 'POST':
        form = SupplierTypeDeleteForm(supplier_type, request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    name = supplier_type.name
                    supplier_type.delete()
                    
                    success_message = _('تم حذف نوع المورد "{}" بنجاح').format(name)
                    messages.success(request, success_message)
                    
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': success_message,
                            'redirect_url': '/supplier/settings/types/'
                        })
                    
                    return redirect('supplier:supplier_type_settings_list')
                    
            except Exception as e:
                messages.error(request, _('حدث خطأ أثناء حذف نوع المورد: {}').format(str(e)))
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'message': str(e)
                    })
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': _('لا يمكن حذف هذا النوع'),
                    'errors': form.errors
                })
    else:
        form = SupplierTypeDeleteForm(supplier_type)
    
    context = {
        'form': form,
        'supplier_type': supplier_type,
        'title': _('حذف نوع المورد: {}').format(supplier_type.name),
    }
    
    # استخدام المودال فقط
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'supplier/settings/supplier_types/delete_modal.html', context)
    else:
        # إعادة توجيه للقائمة
        return redirect('supplier:supplier_type_settings_list')


@login_required
@require_POST
def supplier_type_settings_reorder(request):
    """إعادة ترتيب أنواع الموردين"""
    
    try:
        data = json.loads(request.body)
        type_ids = data.get('type_ids', [])
        
        if not type_ids:
            return JsonResponse({
                'success': False,
                'message': _('قائمة الأنواع مطلوبة')
            })
        
        with transaction.atomic():
            for index, type_id in enumerate(type_ids):
                SupplierTypeSettings.objects.filter(id=type_id).update(
                    display_order=index + 1
                )
        
        return JsonResponse({
            'success': True,
            'message': _('تم إعادة ترتيب الأنواع بنجاح')
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': _('حدث خطأ أثناء إعادة الترتيب: {}').format(str(e))
        })


@login_required
@require_POST
def supplier_type_settings_toggle_status(request, pk):
    """تبديل حالة نوع المورد (نشط/غير نشط)"""
    
    supplier_type = get_object_or_404(SupplierTypeSettings, pk=pk)
    
    try:
        supplier_type.is_active = not supplier_type.is_active
        supplier_type.updated_by = request.user
        supplier_type.save()
        
        status_text = _('نشط') if supplier_type.is_active else _('غير نشط')
        
        return JsonResponse({
            'success': True,
            'message': _('تم تغيير حالة "{}" إلى {}').format(supplier_type.name, status_text),
            'is_active': supplier_type.is_active
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': _('حدث خطأ أثناء تغيير الحالة: {}').format(str(e))
        })


@login_required
@require_POST
def supplier_type_settings_bulk_action(request):
    """العمليات المجمعة على أنواع الموردين"""
    
    form = SupplierTypeBulkActionForm(request.POST)
    
    if form.is_valid():
        try:
            selected_types = form.cleaned_data['selected_types']
            action = form.cleaned_data['action']
            
            with transaction.atomic():
                if action == 'activate':
                    selected_types.update(is_active=True)
                    message = _('تم تفعيل {} نوع بنجاح').format(selected_types.count())
                    
                elif action == 'deactivate':
                    selected_types.update(is_active=False)
                    message = _('تم إلغاء تفعيل {} نوع بنجاح').format(selected_types.count())
                    
                elif action == 'delete':
                    count = selected_types.count()
                    selected_types.delete()
                    message = _('تم حذف {} نوع بنجاح').format(count)
            
            return JsonResponse({
                'success': True,
                'message': message
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': _('حدث خطأ أثناء تنفيذ العملية: {}').format(str(e))
            })
    else:
        return JsonResponse({
            'success': False,
            'message': _('بيانات غير صحيحة'),
            'errors': form.errors
        })


@login_required
def supplier_type_settings_preview(request, pk):
    """معاينة نوع المورد"""
    
    supplier_type = get_object_or_404(SupplierTypeSettings, pk=pk)
    
    context = {
        'supplier_type': supplier_type,
        'suppliers_count': supplier_type.suppliers_count,
    }
    
    return render(request, 'supplier/settings/supplier_types/preview_modal.html', context)


@login_required
def supplier_type_settings_export(request):
    """تصدير إعدادات أنواع الموردين"""
    
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="supplier_types_settings.csv"'
    
    # إضافة BOM للتعامل مع UTF-8 في Excel
    response.write('\ufeff')
    
    writer = csv.writer(response)
    
    # كتابة العناوين
    writer.writerow([
        'الاسم', 'الرمز', 'الوصف', 'الأيقونة', 'اللون', 
        'ترتيب العرض', 'نشط', 'نوع نظام', 'عدد الموردين'
    ])
    
    # كتابة البيانات
    for supplier_type in SupplierTypeSettings.objects.all().order_by('display_order'):
        writer.writerow([
            supplier_type.name,
            supplier_type.code,
            supplier_type.description,
            supplier_type.icon,
            supplier_type.color,
            supplier_type.display_order,
            'نعم' if supplier_type.is_active else 'لا',
            'نعم' if supplier_type.is_system else 'لا',
            supplier_type.suppliers_count,
        ])
    
    return response


@login_required
def supplier_type_settings_sync(request):
    """مزامنة أنواع الموردين مع النظام القديم"""
    
    if request.method == 'POST':
        try:
            from ..models import SupplierType
            
            with transaction.atomic():
                # تشغيل عملية المزامنة
                SupplierType.sync_with_settings()
                
                messages.success(
                    request, 
                    _('تم مزامنة أنواع الموردين مع النظام الجديد بنجاح')
                )
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': str(messages.get_messages(request)[-1])
                    })
                
        except Exception as e:
            messages.error(request, _('حدث خطأ أثناء المزامنة: {}').format(str(e)))
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                })
    
    return redirect('supplier:supplier_type_settings_list')
