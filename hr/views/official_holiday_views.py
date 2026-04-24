"""
Views إدارة الإجازات الرسمية — كل العمليات POST ترجع للـ list
"""
from .base_imports import *
from ..models import OfficialHoliday
from ..forms.official_holiday_form import OfficialHolidayForm

__all__ = [
    'official_holiday_list',
    'official_holiday_create',
    'official_holiday_update',
    'official_holiday_delete',
    'official_holiday_toggle',
]


def _get_list_context(year):
    """context مشترك لصفحة القائمة"""
    holidays = OfficialHoliday.objects.filter(start_date__year=year).order_by('start_date')

    available_years = list(
        OfficialHoliday.objects.dates('start_date', 'year')
        .values_list('start_date__year', flat=True)
        .distinct()
        .order_by('-start_date__year')
    )
    if date.today().year not in available_years:
        available_years.insert(0, date.today().year)

    return {
        'holidays': holidays,
        'selected_year': year,
        'available_years': available_years,
        'page_title': 'الإجازات الرسمية',
        'page_subtitle': f'إدارة الإجازات والعطلات الرسمية لسنة {year}',
        'page_icon': 'fas fa-calendar-day',
        'header_buttons': [
            {
                'onclick': 'openCreateModal()',
                'icon': 'fa-plus',
                'text': 'إضافة إجازة',
                'class': 'btn-primary',
            },
        ],
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموارد البشرية', 'url': reverse('hr:employee_list'), 'icon': 'fas fa-users-cog'},
            {'title': 'الإجازات الرسمية', 'active': True},
        ],
        'active_menu': 'hr',
    }


@login_required
def official_holiday_list(request):
    """قائمة الإجازات الرسمية"""
    year = request.GET.get('year', date.today().year)
    try:
        year = int(year)
    except (ValueError, TypeError):
        year = date.today().year

    return render(request, 'hr/official_holiday/list.html', _get_list_context(year))


@login_required
def official_holiday_create(request):
    """إضافة إجازة رسمية — POST فقط من المودال"""
    year = date.today().year
    if request.method == 'POST':
        form = OfficialHolidayForm(request.POST)
        if form.is_valid():
            holiday = form.save(commit=False)
            holiday.created_by = request.user
            holiday.save()
            year = holiday.start_date.year
            messages.success(request, f'تم إضافة الإجازة "{holiday.name}" بنجاح')
        else:
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)

    return redirect(f"{reverse('hr:official_holiday_list')}?year={year}")


@login_required
def official_holiday_update(request, pk):
    """تعديل إجازة رسمية — POST فقط من المودال"""
    holiday = get_object_or_404(OfficialHoliday, pk=pk)
    year = holiday.start_date.year

    if request.method == 'POST':
        form = OfficialHolidayForm(request.POST, instance=holiday)
        if form.is_valid():
            holiday = form.save()
            year = holiday.start_date.year
            messages.success(request, f'تم تحديث الإجازة "{holiday.name}" بنجاح')
        else:
            for field_errors in form.errors.values():
                for error in field_errors:
                    messages.error(request, error)

    return redirect(f"{reverse('hr:official_holiday_list')}?year={year}")


@login_required
def official_holiday_delete(request, pk):
    """حذف إجازة رسمية — POST فقط من SweetAlert"""
    holiday = get_object_or_404(OfficialHoliday, pk=pk)
    year = holiday.start_date.year

    if request.method == 'POST':
        name = holiday.name
        holiday.delete()
        messages.success(request, f'تم حذف الإجازة "{name}" بنجاح')

    return redirect(f"{reverse('hr:official_holiday_list')}?year={year}")


@login_required
@require_POST
def official_holiday_toggle(request, pk):
    """تفعيل/تعطيل إجازة رسمية"""
    holiday = get_object_or_404(OfficialHoliday, pk=pk)
    year = holiday.start_date.year
    holiday.is_active = not holiday.is_active
    holiday.save()
    status_text = 'تفعيل' if holiday.is_active else 'تعطيل'
    messages.success(request, f'تم {status_text} الإجازة "{holiday.name}"')
    return redirect(f"{reverse('hr:official_holiday_list')}?year={year}")
