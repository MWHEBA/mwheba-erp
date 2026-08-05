from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.paginator import Paginator

from financial.models.approval import EnterpriseApprovalRequest, EnterpriseApprovalRule


@login_required
def approval_inbox(request):
    """صندوق موافقات المؤسسة"""
    requests_qs = EnterpriseApprovalRequest.objects.select_related('rule', 'requested_by').order_by('-created_at')
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)

    paginator = Paginator(requests_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'financial/approval_inbox.html', {
        'page_obj': page_obj,
        'requests_list': page_obj.object_list,
        'status_filter': status_filter,
        'page_title': _("صندوق موافقات المؤسسة"),
        'page_subtitle': _("مراجعة واعتماد طلبات وموافقات السياسات الكبيرة"),
        'page_icon': "fas fa-user-check",
    })
