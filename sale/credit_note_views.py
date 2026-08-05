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
    قائمة الإشعارات الدائنة والخصومات المالية
    """
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    credit_notes = CreditNote.objects.select_related('customer', 'sale', 'created_by').order_by('-created_at')

    if query:
        credit_notes = credit_notes.filter(
            credit_note_number__icontains=query
        ) | credit_notes.filter(
            customer__name__icontains=query
        )

    if status_filter:
        credit_notes = credit_notes.filter(status=status_filter)

    paginator = Paginator(credit_notes, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "credit_notes": page_obj.object_list,
        "query": query,
        "status_filter": status_filter,
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
