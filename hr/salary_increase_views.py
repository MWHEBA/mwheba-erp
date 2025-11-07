"""
Views لإدارة زيادات المرتبات من الإعدادات
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.db.models import Sum, Count, Q
from django.utils import timezone
from decimal import Decimal

from .models.salary_increase import (
    SalaryIncreaseTemplate, AnnualIncreasePlan,
    PlannedIncrease, EmployeeIncreaseCategory
)
from .models import Employee, Contract


# ============================================
# صفحة الإعدادات الرئيسية
# ============================================

@login_required
def salary_increase_settings_home(request):
    """الصفحة الرئيسية لإعدادات زيادات المرتبات"""
    context = {
        'total_templates': SalaryIncreaseTemplate.objects.filter(is_active=True).count(),
        'total_plans': AnnualIncreasePlan.objects.count(),
        'active_plans': AnnualIncreasePlan.objects.filter(status='in_progress').count(),
        'total_categories': EmployeeIncreaseCategory.objects.filter(is_active=True).count(),
        'pending_increases': PlannedIncrease.objects.filter(status='pending').count(),
    }
    return render(request, 'hr/salary_increase/settings_home.html', context)


# ============================================
# قوالب الزيادات (Templates)
# ============================================

class IncreaseTemplateListView(LoginRequiredMixin, ListView):
    """قائمة قوالب الزيادات"""
    model = SalaryIncreaseTemplate
    template_name = 'hr/salary_increase/template_list.html'
    context_object_name = 'templates'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = super().get_queryset()
        increase_type = self.request.GET.get('type')
        if increase_type:
            queryset = queryset.filter(increase_type=increase_type)
        is_active = self.request.GET.get('active')
        if is_active:
            queryset = queryset.filter(is_active=is_active == 'true')
        return queryset.order_by('-is_default', 'name')


class IncreaseTemplateCreateView(LoginRequiredMixin, CreateView):
    """إنشاء قالب زيادة جديد"""
    model = SalaryIncreaseTemplate
    template_name = 'hr/salary_increase/template_form.html'
    fields = [
        'name', 'code', 'description', 'increase_type',
        'default_percentage', 'default_amount', 'frequency',
        'min_service_months', 'is_active', 'is_default'
    ]
    success_url = reverse_lazy('hr:increase_template_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        if form.instance.is_default:
            SalaryIncreaseTemplate.objects.filter(is_default=True).update(is_default=False)
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'تم إنشاء القالب بنجاح'})
        messages.success(self.request, 'تم إنشاء قالب الزيادة بنجاح')
        return response


class IncreaseTemplateUpdateView(LoginRequiredMixin, UpdateView):
    """تعديل قالب زيادة"""
    model = SalaryIncreaseTemplate
    template_name = 'hr/salary_increase/template_form.html'
    fields = [
        'name', 'code', 'description', 'increase_type',
        'default_percentage', 'default_amount', 'frequency',
        'min_service_months', 'is_active', 'is_default'
    ]
    success_url = reverse_lazy('hr:increase_template_list')
    
    def form_valid(self, form):
        if form.instance.is_default:
            SalaryIncreaseTemplate.objects.exclude(pk=self.object.pk).update(is_default=False)
        response = super().form_valid(form)
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'تم تحديث القالب بنجاح'})
        messages.success(self.request, 'تم تحديث قالب الزيادة بنجاح')
        return response


class IncreaseTemplateDeleteView(LoginRequiredMixin, DeleteView):
    """حذف قالب زيادة"""
    model = SalaryIncreaseTemplate
    template_name = 'hr/salary_increase/template_delete.html'
    success_url = reverse_lazy('hr:increase_template_list')
    
    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'تم حذف القالب بنجاح'})
        messages.success(request, 'تم حذف قالب الزيادة بنجاح')
        return response


# ============================================
# الخطط السنوية (Annual Plans)
# ============================================

class AnnualPlanListView(LoginRequiredMixin, ListView):
    """قائمة خطط الزيادات السنوية"""
    model = AnnualIncreasePlan
    template_name = 'hr/salary_increase/plan_list.html'
    context_object_name = 'plans'
    paginate_by = 20
    
    def get_queryset(self):
        queryset = super().get_queryset()
        year = self.request.GET.get('year')
        if year:
            queryset = queryset.filter(year=year)
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        return queryset.order_by('-year', '-created_at')


class AnnualPlanCreateView(LoginRequiredMixin, CreateView):
    """إنشاء خطة زيادات سنوية"""
    model = AnnualIncreasePlan
    template_name = 'hr/salary_increase/plan_form.html'
    fields = [
        'name', 'year', 'template', 'effective_date',
        'total_budget', 'notes'
    ]
    success_url = reverse_lazy('hr:annual_plan_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, 'تم إنشاء خطة الزيادات بنجاح')
        return response
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['templates'] = SalaryIncreaseTemplate.objects.filter(is_active=True)
        return context


class AnnualPlanUpdateView(LoginRequiredMixin, UpdateView):
    """تعديل خطة زيادات سنوية"""
    model = AnnualIncreasePlan
    template_name = 'hr/salary_increase/plan_form.html'
    fields = [
        'name', 'year', 'template', 'effective_date',
        'total_budget', 'notes', 'status'
    ]
    success_url = reverse_lazy('hr:annual_plan_list')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'تم تحديث خطة الزيادات بنجاح')
        return response


class AnnualPlanDetailView(LoginRequiredMixin, ListView):
    """تفاصيل خطة الزيادات مع الزيادات المخططة"""
    model = PlannedIncrease
    template_name = 'hr/salary_increase/plan_detail.html'
    context_object_name = 'planned_increases'
    paginate_by = 50
    
    def get_queryset(self):
        self.plan = get_object_or_404(AnnualIncreasePlan, pk=self.kwargs['pk'])
        return PlannedIncrease.objects.filter(plan=self.plan).select_related(
            'employee', 'contract'
        ).order_by('employee__employee_number')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['plan'] = self.plan
        context['total_cost'] = self.plan.planned_increases.filter(
            status='approved'
        ).aggregate(total=Sum('calculated_amount'))['total'] or Decimal('0')
        context['stats'] = {
            'pending': self.plan.planned_increases.filter(status='pending').count(),
            'approved': self.plan.planned_increases.filter(status='approved').count(),
            'rejected': self.plan.planned_increases.filter(status='rejected').count(),
            'applied': self.plan.planned_increases.filter(status='applied').count(),
        }
        return context


# ============================================
# الزيادات المخططة (Planned Increases)
# ============================================

@login_required
def generate_planned_increases(request, plan_id):
    """توليد زيادات مخططة للموظفين المؤهلين"""
    plan = get_object_or_404(AnnualIncreasePlan, pk=plan_id)
    
    if request.method == 'POST':
        # الحصول على الموظفين المؤهلين
        employees = Employee.objects.filter(status='active')
        
        # تطبيق شروط القالب
        if plan.template.min_service_months > 0:
            min_hire_date = timezone.now().date() - timezone.timedelta(
                days=plan.template.min_service_months * 30
            )
            employees = employees.filter(hire_date__lte=min_hire_date)
        
        created_count = 0
        for employee in employees:
            # الحصول على العقد النشط
            contract = employee.contracts.filter(status='active').first()
            if not contract:
                continue
            
            # التحقق من عدم وجود زيادة مخططة بالفعل
            if PlannedIncrease.objects.filter(plan=plan, employee=employee).exists():
                continue
            
            # حساب الزيادة
            current_salary = contract.basic_salary
            if plan.template.increase_type == 'percentage':
                increase_percentage = plan.template.default_percentage
                calculated_amount = current_salary * increase_percentage / Decimal('100')
            else:
                increase_percentage = None
                calculated_amount = plan.template.default_amount
            
            new_salary = current_salary + calculated_amount
            
            # إنشاء الزيادة المخططة
            PlannedIncrease.objects.create(
                plan=plan,
                employee=employee,
                contract=contract,
                current_salary=current_salary,
                increase_percentage=increase_percentage,
                calculated_amount=calculated_amount,
                new_salary=new_salary,
                status='pending'
            )
            created_count += 1
        
        messages.success(request, f'تم توليد {created_count} زيادة مخططة')
        return redirect('hr:annual_plan_detail', pk=plan_id)
    
    return render(request, 'hr/salary_increase/generate_increases.html', {'plan': plan})


@login_required
def approve_planned_increase(request, increase_id):
    """اعتماد زيادة مخططة"""
    increase = get_object_or_404(PlannedIncrease, pk=increase_id)
    
    if request.method == 'POST':
        increase.status = 'approved'
        increase.save()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'تم اعتماد الزيادة'})
        
        messages.success(request, 'تم اعتماد الزيادة بنجاح')
        return redirect('hr:annual_plan_detail', pk=increase.plan.pk)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير صحيحة'})


@login_required
def reject_planned_increase(request, increase_id):
    """رفض زيادة مخططة"""
    increase = get_object_or_404(PlannedIncrease, pk=increase_id)
    
    if request.method == 'POST':
        increase.status = 'rejected'
        increase.save()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'تم رفض الزيادة'})
        
        messages.success(request, 'تم رفض الزيادة')
        return redirect('hr:annual_plan_detail', pk=increase.plan.pk)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير صحيحة'})


@login_required
def apply_planned_increase(request, increase_id):
    """تطبيق زيادة مخططة على العقد"""
    increase = get_object_or_404(PlannedIncrease, pk=increase_id)
    
    if request.method == 'POST':
        if increase.status != 'approved':
            return JsonResponse({'success': False, 'message': 'الزيادة غير معتمدة'})
        
        # تطبيق الزيادة على العقد
        contract = increase.contract
        contract.basic_salary = increase.new_salary
        contract.save()
        
        # تحديث حالة الزيادة
        increase.status = 'applied'
        increase.applied_date = timezone.now().date()
        increase.save()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'تم تطبيق الزيادة بنجاح'})
        
        messages.success(request, 'تم تطبيق الزيادة على العقد بنجاح')
        return redirect('hr:annual_plan_detail', pk=increase.plan.pk)
    
    return JsonResponse({'success': False, 'message': 'طريقة غير صحيحة'})


@login_required
def bulk_apply_increases(request, plan_id):
    """تطبيق جميع الزيادات المعتمدة دفعة واحدة"""
    plan = get_object_or_404(AnnualIncreasePlan, pk=plan_id)
    
    if request.method == 'POST':
        approved_increases = plan.planned_increases.filter(status='approved')
        applied_count = 0
        
        for increase in approved_increases:
            contract = increase.contract
            contract.basic_salary = increase.new_salary
            contract.save()
            
            increase.status = 'applied'
            increase.applied_date = timezone.now().date()
            increase.save()
            
            applied_count += 1
        
        # تحديث حالة الخطة
        if applied_count > 0:
            plan.status = 'completed'
            plan.save()
        
        messages.success(request, f'تم تطبيق {applied_count} زيادة بنجاح')
        return redirect('hr:annual_plan_detail', pk=plan_id)
    
    return render(request, 'hr/salary_increase/bulk_apply_confirm.html', {'plan': plan})


# ============================================
# فئات الموظفين (Employee Categories)
# ============================================

class EmployeeCategoryListView(LoginRequiredMixin, ListView):
    """قائمة فئات الموظفين"""
    model = EmployeeIncreaseCategory
    template_name = 'hr/salary_increase/category_list.html'
    context_object_name = 'categories'
    paginate_by = 20


class EmployeeCategoryCreateView(LoginRequiredMixin, CreateView):
    """إنشاء فئة موظفين"""
    model = EmployeeIncreaseCategory
    template_name = 'hr/salary_increase/category_form.html'
    fields = ['name', 'code', 'description', 'default_template', 'is_active']
    success_url = reverse_lazy('hr:employee_category_list')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'تم إنشاء فئة الموظفين بنجاح')
        return response


class EmployeeCategoryUpdateView(LoginRequiredMixin, UpdateView):
    """تعديل فئة موظفين"""
    model = EmployeeIncreaseCategory
    template_name = 'hr/salary_increase/category_form.html'
    fields = ['name', 'code', 'description', 'default_template', 'is_active']
    success_url = reverse_lazy('hr:employee_category_list')
    
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, 'تم تحديث فئة الموظفين بنجاح')
        return response


class EmployeeCategoryDeleteView(LoginRequiredMixin, DeleteView):
    """حذف فئة موظفين"""
    model = EmployeeIncreaseCategory
    template_name = 'hr/salary_increase/category_delete.html'
    success_url = reverse_lazy('hr:employee_category_list')
    
    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        messages.success(request, 'تم حذف فئة الموظفين بنجاح')
        return response
