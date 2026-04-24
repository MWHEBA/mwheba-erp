"""
Views الجزاءات والمكافآت
"""
from .base_imports import *
from ..models import PenaltyReward, Employee
from ..forms.penalty_reward_forms import PenaltyRewardForm
from hr.services.penalty_reward_service import PenaltyRewardService
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)

__all__ = [
    'penalty_reward_list',
    'penalty_reward_create',
    'penalty_reward_detail',
    'penalty_reward_edit',
    'penalty_reward_delete',
    'penalty_reward_approve',
    'penalty_reward_reject',
]


@login_required
def penalty_reward_list(request):
    """قائمة الجزاءات والمكافآت"""
    qs = PenaltyReward.objects.select_related(
        'employee', 'employee__department', 'approved_by', 'created_by'
    ).all()

    # الإحصائيات
    total_penalties = qs.filter(category='penalty').count()
    total_rewards = qs.filter(category='reward').count()
    pending_count = qs.filter(status='pending').count()
    approved_count = qs.filter(status='approved').count()

    # الفلاتر
    employee_filter = request.GET.get('employee')
    category_filter = request.GET.get('category')
    status_filter = request.GET.get('status')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')

    if employee_filter:
        qs = qs.filter(employee_id=employee_filter)
    if category_filter:
        qs = qs.filter(category=category_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if from_date:
        qs = qs.filter(date__gte=from_date)
    if to_date:
        qs = qs.filter(date__lte=to_date)

    employees = Employee.objects.filter(status='active', is_insurance_only=False).order_by('name')

    paginator = Paginator(qs, 30)
    page = request.GET.get('page', 1)
    items_page = paginator.get_page(page)

    context = {
        'items': items_page,
        'employees': employees,
        'total_penalties': total_penalties,
        'total_rewards': total_rewards,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'active_menu': 'hr',
        'title': 'الجزاءات والمكافآت',
        'header_buttons': [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': 'إضافة جديد',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الجزاءات والمكافآت', 'active': True},
        ],
    }
    return render(request, 'hr/penalty_reward/list.html', context)


@login_required
def penalty_reward_create(request):
    """إنشاء جزاء/مكافأة - يُستدعى من المودال عبر AJAX"""
    if request.method == 'POST':
        form = PenaltyRewardForm(request.POST)
        if form.is_valid():
            try:
                pr = PenaltyRewardService.create(
                    employee=form.cleaned_data['employee'],
                    data={
                        'category': form.cleaned_data['category'],
                        'date': form.cleaned_data['date'],
                        'month': form.cleaned_data['month'],
                        'calculation_method': form.cleaned_data['calculation_method'],
                        'value': form.cleaned_data['value'],
                        'reason': form.cleaned_data['reason'],
                    },
                    created_by=request.user,
                )
                label = 'الجزاء' if pr.category == 'penalty' else 'المكافأة'
                return JsonResponse({'success': True, 'message': f'تم إضافة {label} بنجاح'})
            except Exception as e:
                logger.exception(f"خطأ في إنشاء جزاء/مكافأة: {e}")
                return JsonResponse({'success': False, 'message': str(e)})
        else:
            # إرجاع أخطاء الفورم بشكل واضح
            errors = {}
            for field, error_list in form.errors.items():
                if field == '__all__':
                    # أخطاء عامة غير مرتبطة بحقل معين
                    errors['__all__'] = {'label': 'خطأ عام', 'errors': list(error_list)}
                else:
                    label = form.fields[field].label if field in form.fields else field
                    errors[field] = {'label': label, 'errors': list(error_list)}
            return JsonResponse({'success': False, 'form_errors': errors, 'message': 'يرجى تصحيح الأخطاء في النموذج'})

    return JsonResponse({'success': False, 'message': 'طلب غير صالح'})


@login_required
def penalty_reward_detail(request, pk):
    """تفاصيل الجزاء/المكافأة"""
    pr = get_object_or_404(
        PenaltyReward.objects.select_related(
            'employee', 'employee__department', 'created_by', 'approved_by', 'payroll'
        ),
        pk=pk
    )

    context = {
        'pr': pr,
        'active_menu': 'hr',
        'title': f"{'جزاء' if pr.category == 'penalty' else 'مكافأة'}: {pr.employee.get_full_name_ar()}",
        'header_buttons': [
            {
                'url': reverse('hr:penalty_reward_list'),
                'icon': 'fa-arrow-right',
                'text': 'رجوع',
                'class': 'btn-outline-secondary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الجزاءات والمكافآت', 'url': reverse('hr:penalty_reward_list'), 'icon': 'fas fa-gavel'},
            {'title': 'التفاصيل', 'active': True},
        ],
    }
    return render(request, 'hr/penalty_reward/detail.html', context)


@login_required
def penalty_reward_edit(request, pk):
    """تعديل جزاء/مكافأة - يُستدعى من المودال"""
    pr = get_object_or_404(PenaltyReward, pk=pk)

    if pr.status != 'pending':
        messages.error(request, 'لا يمكن تعديل إلا الطلبات المعلقة')
        return redirect('hr:penalty_reward_detail', pk=pk)

    if request.method == 'POST':
        form = PenaltyRewardForm(request.POST, instance=pr)
        if form.is_valid():
            try:
                pr = form.save(commit=False)
                pr.calculated_amount = 0  # إعادة الحساب
                pr.calculate_amount()
                pr.save()
                messages.success(request, 'تم تحديث البيانات بنجاح')
                return redirect('hr:penalty_reward_detail', pk=pr.pk)
            except Exception as e:
                logger.exception(f"خطأ في تعديل جزاء/مكافأة: {e}")
                messages.error(request, f'حدث خطأ: {str(e)}')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')

    return redirect('hr:penalty_reward_detail', pk=pk)


@login_required
@require_POST
def penalty_reward_delete(request, pk):
    """حذف جزاء/مكافأة"""
    pr = get_object_or_404(PenaltyReward, pk=pk)

    if pr.status == 'applied':
        return JsonResponse({'success': False, 'message': 'لا يمكن حذف جزاء/مكافأة مطبق على الراتب'})

    label = 'الجزاء' if pr.category == 'penalty' else 'المكافأة'
    pr.delete()
    messages.success(request, f'تم حذف {label} بنجاح')
    return JsonResponse({'success': True, 'message': f'تم حذف {label} بنجاح'})


@login_required
@require_POST
def penalty_reward_approve(request, pk):
    """اعتماد الجزاء/المكافأة عبر AJAX"""
    pr = get_object_or_404(PenaltyReward, pk=pk)
    notes = request.POST.get('review_notes', '')

    try:
        PenaltyRewardService.approve(pr, request.user, notes)
        return JsonResponse({'success': True, 'message': 'تم الاعتماد بنجاح'})
    except ValidationError as e:
        return JsonResponse({'success': False, 'message': str(e.message)})
    except Exception as e:
        logger.exception(f"خطأ في اعتماد جزاء/مكافأة: {e}")
        return JsonResponse({'success': False, 'message': str(e)})


@login_required
@require_POST
def penalty_reward_reject(request, pk):
    """رفض الجزاء/المكافأة عبر AJAX"""
    pr = get_object_or_404(PenaltyReward, pk=pk)
    notes = request.POST.get('review_notes', '')

    try:
        PenaltyRewardService.reject(pr, request.user, notes)
        return JsonResponse({'success': True, 'message': 'تم الرفض'})
    except ValidationError as e:
        return JsonResponse({'success': False, 'message': str(e.message)})
    except Exception as e:
        logger.exception(f"خطأ في رفض جزاء/مكافأة: {e}")
        return JsonResponse({'success': False, 'message': str(e)})
