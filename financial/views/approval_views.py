from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.paginator import Paginator

from financial.models.approval import EnterpriseApprovalRequest, EnterpriseApprovalRule
from financial.services.approval_service import ApprovalService
from financial.exceptions import FinancialCoreError


@login_required
def approval_inbox(request):
    """صندوق موافقات المؤسسة"""
    requests_qs = EnterpriseApprovalRequest.objects.select_related('rule', 'requested_by').order_by('-created_at')
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)

    pending_count = EnterpriseApprovalRequest.objects.filter(status="PENDING").count()
    approved_count = EnterpriseApprovalRequest.objects.filter(status="APPROVED").count()
    rejected_count = EnterpriseApprovalRequest.objects.filter(status="REJECTED").count()

    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(requests_qs, request)
    page_obj = pagination_context["page_obj"]

    return render(request, 'financial/approval_inbox.html', {
        'page_obj': page_obj,
        'requests_list': page_obj.object_list,
        **pagination_context,
        'status_filter': status_filter,
        'pending_count': pending_count,
        'approved_count': approved_count,
        'rejected_count': rejected_count,
        'page_title': _("صندوق موافقات المؤسسة"),
        'page_subtitle': _("مراجعة واعتماد طلبات وموافقات السياسات الكبيرة"),
        'page_icon': "fas fa-user-check",
    })


@login_required
def approval_approve(request, pk):
    """اعتماد طلب الموافقة عبر النموذج"""
    if request.method == "POST":
        comments = request.POST.get("comments", "").strip()
        try:
            ApprovalService.approve_request(pk, user=request.user, comments=comments)
            messages.success(request, _(f"تم اعتماد الطلب #{pk} وتحديث حالة المستند الأصلي بنجاح."))
        except FinancialCoreError as e:
            messages.error(request, _(f"فشل الاعتماد: {str(e)}"))
        except Exception as e:
            messages.error(request, _(f"حدث خطأ غير متوقع أثناء الاعتماد: {str(e)}"))

    return redirect("financial:approval_inbox")


@login_required
def approval_reject(request, pk):
    """رفض طلب الموافقة عبر النموذج"""
    if request.method == "POST":
        comments = request.POST.get("comments", "").strip()
        try:
            ApprovalService.reject_request(pk, user=request.user, comments=comments)
            messages.warning(request, _(f"تم رفض الطلب #{pk} بنجاح."))
        except FinancialCoreError as e:
            messages.error(request, _(f"فشل الرفض: {str(e)}"))
        except Exception as e:
            messages.error(request, _(f"حدث خطأ غير متوقع أثناء الرفض: {str(e)}"))

    return redirect("financial:approval_inbox")

