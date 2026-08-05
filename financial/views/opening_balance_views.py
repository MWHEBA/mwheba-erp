from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.core.paginator import Paginator
from django.utils import timezone

from financial.models.opening_balance import OpeningBalanceBatch, OpeningBalanceLine


@login_required
def opening_balance_list(request):
    """عرض دفعات الأرصدة الافتتاحية"""
    batches = OpeningBalanceBatch.objects.select_related('created_by').order_by('-created_at')
    paginator = Paginator(batches, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'financial/opening_balance_list.html', {
        'page_obj': page_obj,
        'batches': page_obj.object_list,
        'page_title': _("الأرصدة الافتتاحية والفترات"),
        'page_subtitle': _("إدارة وتأكيد دفعة الأرصدة الافتتاحية للدفاتر المحاسبية"),
        'page_icon': "fas fa-balance-scale",
        'header_buttons': [
            {
                'url': '#',
                'icon': 'fa-plus',
                'text': _("إضافة دفعة رصيد إفتتاحي"),
                'class': 'btn-primary',
            }
        ]
    })


@login_required
def opening_balance_create(request):
    """إنشاء دفعة أرصدة افتتاحية جديدة"""
    if request.method == "POST":
        batch_number = f"OPB-{timezone.now().strftime('%Y%m%d%H%M%S')}"
        notes = request.POST.get("notes", "").strip()

        batch = OpeningBalanceBatch.objects.create(
            batch_number=batch_number,
            notes=notes,
            created_by=request.user,
            status="DRAFT"
        )

        messages.success(request, _("تم إنشاء دفعة الأرصدة الافتتاحية رقم {} بنجاح").format(batch.batch_number))
        return redirect("financial:opening_balance_list")

    return render(request, "financial/opening_balance_form.html", {
        'page_title': _("إضافة أرصدة افتتاحية"),
        'page_subtitle': _("تسجيل الأرصدة الافتتاحية للحسابات"),
        'page_icon': "fas fa-plus-circle",
    })
