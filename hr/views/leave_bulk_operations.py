"""
Bulk Operations for Leave Management
Issue #32-35: Missing bulk operations
"""
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods
from django.db import transaction
from ..models import Leave
from ..services.leave_service import LeaveService
import logging

logger = logging.getLogger(__name__)


@require_http_methods(['POST'])
@login_required
@permission_required('hr.approve_leave', raise_exception=True)
def bulk_approve_leaves(request):
    """
    Approve multiple leaves at once
    Issue #32: Missing bulk approve operation
    """
    leave_ids = request.POST.getlist('leave_ids')
    
    if not leave_ids:
        messages.error(request, 'لم يتم تحديد أي إجازات')
        return redirect('hr:leave_list')
    
    # Get all leaves in one query with related data
    leaves = Leave.objects.filter(
        id__in=leave_ids,
        status='pending'
    ).select_related('employee', 'leave_type')
    
    if not leaves.exists():
        messages.warning(request, 'لا توجد إجازات معلقة للاعتماد')
        return redirect('hr:leave_list')
    
    approved_count = 0
    failed_count = 0
    failed_reasons = []
    
    for leave in leaves:
        try:
            LeaveService.approve_leave(leave, request.user)
            approved_count += 1
        except Exception as e:
            failed_count += 1
            failed_reasons.append(f'{leave.employee.get_full_name_ar()}: {str(e)}')
            logger.error(f'فشل اعتماد الإجازة {leave.id}: {e}')
    
    # Success message
    if approved_count > 0:
        messages.success(
            request,
            f'تم اعتماد {approved_count} إجازة بنجاح'
        )
    
    # Failure message
    if failed_count > 0:
        messages.warning(
            request,
            f'فشل اعتماد {failed_count} إجازة. الأسباب: {", ".join(failed_reasons[:3])}'
        )
    
    return redirect('hr:leave_list')


@require_http_methods(['POST'])
@login_required
@permission_required('hr.approve_leave', raise_exception=True)
def bulk_reject_leaves(request):
    """
    Reject multiple leaves at once
    Issue #33: Missing bulk reject operation
    """
    leave_ids = request.POST.getlist('leave_ids')
    rejection_notes = request.POST.get('rejection_notes', '')
    
    if not leave_ids:
        messages.error(request, 'لم يتم تحديد أي إجازات')
        return redirect('hr:leave_list')
    
    if not rejection_notes:
        messages.error(request, 'سبب الرفض مطلوب')
        return redirect('hr:leave_list')
    
    # Get all leaves in one query
    leaves = Leave.objects.filter(
        id__in=leave_ids,
        status='pending'
    ).select_related('employee', 'leave_type')
    
    if not leaves.exists():
        messages.warning(request, 'لا توجد إجازات معلقة للرفض')
        return redirect('hr:leave_list')
    
    rejected_count = 0
    failed_count = 0
    
    for leave in leaves:
        try:
            LeaveService.reject_leave(leave, request.user, rejection_notes)
            rejected_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f'فشل رفض الإجازة {leave.id}: {e}')
    
    # Success message
    if rejected_count > 0:
        messages.success(
            request,
            f'تم رفض {rejected_count} إجازة'
        )
    
    # Failure message
    if failed_count > 0:
        messages.warning(
            request,
            f'فشل رفض {failed_count} إجازة'
        )
    
    return redirect('hr:leave_list')
