import uuid
import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator

from client.models import Customer
from sale.models import Sale, CreditNote
from sale.services.sales_reversal_service import SalesReversalService

logger = logging.getLogger("sale.credit_note_views")


@login_required
def credit_note_list(request):
    """
    قائمة الإشعارات الدائنة والخصومات المالية وفق نظام ERP الموحد
    """
    from django.db.models import Sum
    from datetime import datetime
    from core.models import SystemSetting

    queryset = CreditNote.objects.select_related('customer', 'sale', 'created_by').order_by('-created_at', '-id')

    customer_id = request.GET.get('customer')
    status_filter = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if customer_id:
        queryset = queryset.filter(customer_id=customer_id)
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            queryset = queryset.filter(created_at__date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            queryset = queryset.filter(created_at__date__lte=d_to)
        except ValueError:
            pass

    # الكروت الإحصائية
    total_credit_notes_count = CreditNote.objects.count()
    total_credit_notes_amount = CreditNote.objects.aggregate(total=Sum('total_amount'))['total'] or 0
    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(queryset, request)
    page_obj = pagination_context["page_obj"]

    curr_sym = SystemSetting.get_currency_symbol()

    cn_headers = [
        {"key": "credit_note_number", "label": "رقم الإشعار", "width": "15%", "format": "html"},
        {"key": "customer_name", "label": "العميل", "width": "20%"},
        {"key": "sale_number", "label": "الفاتورة الأصلية", "width": "15%", "format": "html"},
        {"key": "subtotal_amount", "label": "المبلغ قبل الضريبة", "width": "12%", "class": "text-end"},
        {"key": "tax_amount", "label": "الضريبة", "width": "10%", "class": "text-end"},
        {"key": "total_amount", "label": "الإجمالي", "width": "13%", "class": "text-end fw-bold"},
        {"key": "status", "label": "الحالة", "width": "10%", "class": "text-center", "format": "html"},
        {"key": "created_at", "label": "التاريخ", "width": "10%", "class": "text-center"},
        {"key": "actions", "label": "الإجراءات", "width": "10%", "class": "text-center text-nowrap"}
    ]

    credit_notes_data = []
    for cn in page_obj:
        if cn.status == 'POSTED':
            status_badge = '<span class="badge bg-success"><i class="fas fa-check-circle me-1"></i>مُرحل للدفاتر</span>'
        elif cn.status == 'APPROVED':
            status_badge = '<span class="badge bg-primary"><i class="fas fa-thumbs-up me-1"></i>معتمد</span>'
        else:
            status_badge = '<span class="badge bg-secondary">مسودة</span>'

        cn_num_html = f'<a href="/sales/credit-notes/{cn.id}/" class="text-primary font-monospace fw-bold">{cn.credit_note_number}</a>'
        sale_num_html = f'<a href="/sales/{cn.sale.id}/" class="text-primary font-monospace">{cn.sale.number}</a>' if cn.sale else '-'
        actions_html = f'<a href="/sales/credit-notes/{cn.id}/" class="btn btn-sm btn-outline-primary" title="عرض"><i class="fas fa-eye"></i></a>'

        credit_notes_data.append({
            'id': cn.id,
            'credit_note_number': cn_num_html,
            'customer_name': cn.customer.name if cn.customer else '-',
            'sale_number': sale_num_html,
            'subtotal_amount': f'{cn.subtotal_amount:,.2f} {curr_sym}',
            'tax_amount': f'{cn.tax_amount:,.2f} {curr_sym}',
            'total_amount': f'{cn.total_amount:,.2f} {curr_sym}',
            'status': status_badge,
            'created_at': cn.created_at.strftime('%Y-%m-%d') if cn.created_at else '-',
            'actions': actions_html,
        })

    customers = Customer.objects.filter(is_active=True).order_by("name")

    context = {
        "page_obj": page_obj,
        **pagination_context,
        "credit_notes": page_obj,
        "credit_notes_data": credit_notes_data,
        "cn_headers": cn_headers,
        "total_credit_notes_count": total_credit_notes_count,
        "total_credit_notes_amount": total_credit_notes_amount,
        "posted_credit_notes_count": posted_credit_notes_count,
        "draft_credit_notes_count": draft_credit_notes_count,
        "customers": customers,
        "currency_symbol": curr_sym,
        "page_title": _("الإشعارات الدائنة والخصومات"),
        "page_subtitle": _("إدارة وتتبع الإشعارات الدائنة المالية والخصومات الصادرة للعملاء"),
        "page_icon": "fas fa-file-invoice-dollar",
        "header_buttons": [
            {
                "url": reverse("sale:credit_note_create"),
                "icon": "fa-plus",
                "text": _("إصدار إشعار دائن جديد"),
                "class": "btn-primary",
            }
        ],
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": _("الإشعارات الدائنة"), "active": True},
        ]
    }

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        from django.http import JsonResponse
        table_html = render_to_string('components/data_table.html', {
            'table_id': 'credit-notes-table',
            'headers': cn_headers,
            'data': credit_notes_data,
            'empty_message': 'لا توجد إشعارات دائنة مسجلة حتى الآن.',
            'table_class': 'hover',
            'primary_key': 'id',
            'clickable_rows': True,
            'row_click_url': '/sales/credit-notes/0/',
            'show_currency': True,
            'disable_pagination': True,
            'show_search': False,
            'show_length_menu': False,
            'sortable': False
        }, request=request)
        pagination_html = render_to_string('partials/pagination.html', {
            'page_obj': page_obj
        }, request=request)
        return JsonResponse({
            'table_html': table_html,
            'pagination_html': pagination_html
        })

    return render(request, "sale/credit_note_list.html", context)


@login_required
def credit_note_create(request):
    """
    إصدار إشعار دائن مالي جديد
    """
    sale_id = request.GET.get('sale_id')
    selected_sale = None
    if sale_id:
        selected_sale = get_object_or_404(Sale, pk=sale_id)

    if request.method == "POST":
        customer_id = request.POST.get('customer')
        post_sale_id = request.POST.get('sale')
        amount_str = request.POST.get('amount', '0')
        reason = request.POST.get('reason', '').strip()
        source_type = request.POST.get('source_type', 'PRICE_ADJUSTMENT')

        try:
            amount = Decimal(amount_str)
            if amount <= Decimal('0'):
                raise ValueError(_("مبلغ الإشعار الدائن يجب أن يكون أكبر من صفر."))

            if post_sale_id:
                cn = SalesReversalService.create_credit_note_for_sale(
                    sale_id=int(post_sale_id),
                    amount=amount,
                    reason=reason,
                    source_type=source_type,
                    user=request.user
                )
            else:
                customer = get_object_or_404(Customer, pk=customer_id)
                cn_num = f"CN-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
                subtotal = (amount / Decimal("1.14")).quantize(Decimal("0.01"))
                tax_amount = (amount - subtotal).quantize(Decimal("0.01"))

                cn = CreditNote.objects.create(
                    credit_note_number=cn_num,
                    customer=customer,
                    source_type=source_type,
                    status="APPROVED",
                    reason=reason,
                    subtotal_amount=subtotal,
                    tax_amount=tax_amount,
                    total_amount=amount,
                    currency="EGP",
                    created_by=request.user
                )

            messages.success(request, _("تم إصدار الإشعار الدائن رقم {} بنجاح").format(cn.credit_note_number))
            return redirect("sale:credit_note_detail", pk=cn.pk)

        except Exception as e:
            logger.error(f"Error creating credit note: {str(e)}")
            messages.error(request, _("تعذر إصدار الإشعار الدائن: {}").format(str(e)))

    customers = Customer.objects.filter(is_active=True).order_by('name')

    context = {
        "customers": customers,
        "selected_sale": selected_sale,
        "page_title": _("إصدار إشعار دائن جديد"),
        "page_subtitle": _("تسجيل إشعار دائن أو تسوية خصم مالي لصالح عميل"),
        "page_icon": "fas fa-file-signature",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": _("الإشعارات الدائنة"), "url": reverse("sale:credit_note_list")},
            {"title": _("إصدار إشعار دائن"), "active": True},
        ]
    }
    return render(request, "sale/credit_note_form.html", context)


@login_required
def credit_note_detail(request, pk):
    """
    عرض تفاصيل الإشعار الدائن ومتابعة التوافق المالي
    """
    credit_note = get_object_or_404(CreditNote, pk=pk)

    context = {
        "credit_note": credit_note,
        "page_title": f"إشعار دائن {credit_note.credit_note_number}",
        "page_subtitle": f"العميل: {credit_note.customer.name} - القيمة: {credit_note.total_amount} EGP",
        "page_icon": "fas fa-file-invoice-dollar",
        "header_buttons": [
            *([{
                "url": reverse("sale:credit_note_post", kwargs={"pk": credit_note.pk}),
                "icon": "fa-check-circle",
                "text": _("ترحيل مالياً للدفاتر"),
                "class": "btn-success",
            }] if credit_note.status != "POSTED" else []),
        ],
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": _("الإشعارات الدائنة"), "url": reverse("sale:credit_note_list")},
            {"title": credit_note.credit_note_number, "active": True},
        ]
    }
    return render(request, "sale/credit_note_detail.html", context)


@login_required
def credit_note_post(request, pk):
    """
    ترحيل الإشعار الدائن للحسابات العامة وأستاذ العملاء الفرعي
    """
    credit_note = get_object_or_404(CreditNote, pk=pk)
    try:
        SalesReversalService.post_credit_note(credit_note.id, user=request.user)
        messages.success(request, _("تم ترحيل الإشعار الدائن رقم {} بنجاح للدفاتر المحاسبية").format(credit_note.credit_note_number))
    except Exception as e:
        logger.error(f"Error posting credit note: {str(e)}")
        messages.error(request, _("تعذر ترحيل الإشعار الدائن: {}").format(str(e)))

    return redirect("sale:credit_note_detail", pk=credit_note.pk)


@login_required
def credit_note_reverse(request, pk):
    """
    عكس الإشعار الدائن المرحل وفق الحوكمة المحاسبية والأثر الرجعي
    """
    credit_note = get_object_or_404(CreditNote, pk=pk)
    if request.method == "POST":
        reason = request.POST.get("reason", "Credit note cancellation and reversal")
        try:
            SalesReversalService.reverse_credit_note(credit_note.id, reason=reason, user=request.user)
            messages.success(request, _("تم عكس الإشعار الدائن رقم {} وتوليد قيد العكس بنجاح").format(credit_note.credit_note_number))
        except Exception as e:
            logger.error(f"Error reversing credit note: {str(e)}")
            messages.error(request, _("تعذر عكس الإشعار الدائن: {}").format(str(e)))

    return redirect("sale:credit_note_detail", pk=credit_note.pk)

