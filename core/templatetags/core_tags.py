from django import template

register = template.Library()

@register.inclusion_tag('hr/attendance/partials/status_badge.html')
def display_attendance_status(status):
    """
    يعرض badge منسق لحالة الحضور.
    """
    status_map = {
        'present': {'label': 'حاضر', 'color': 'success'},
        'absent': {'label': 'غائب', 'color': 'danger'},
        'late': {'label': 'متأخر', 'color': 'warning'},
        'early_leave': {'label': 'انصراف مبكر', 'color': 'info'},
        'on_leave': {'label': 'إجازة', 'color': 'purple'},
        'weekend': {'label': 'عطلة', 'color': 'secondary'},
        'holiday': {'label': 'عطلة رسمية', 'color': 'primary'},
        'no_shift': {'label': 'لا توجد وردية', 'color': 'dark'},
    }
    default_status = {'label': status, 'color': 'light'}
    status_info = status_map.get(status, default_status)

    return {
        'label': status_info['label'],
        'color': status_info['color'],
    }
