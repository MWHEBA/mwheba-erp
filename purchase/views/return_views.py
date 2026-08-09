"""
Purchase Return Views
عرض وإدارة مرتجعات المشتريات
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.urls import reverse
from decimal import Decimal
import logging

from django.core.paginator import Paginator
from datetime import datetime
from supplier.models import Supplier
from purchase.models import Purchase, PurchaseItem, PurchaseReturn, PurchaseReturnItem
from purchase.forms import PurchaseReturnForm
from core.models import SystemSetting

logger = logging.getLogger(__name__)


@login_required
def purchase_return(request, pk):
    """
    إرجاع فاتورة المشتريات
    """
    purchase = get_object_or_404(Purchase, pk=pk)
    items = purchase.items.all()

    # الحصول على الكميات المرتجعة سابقاً لكل عنصر
    previously_returned_quantities = {}
    for item in items:
        returned_items = PurchaseReturnItem.objects.filter(
            purchase_item=item, purchase_return__status__in=["draft", "confirmed"]
        )
        previously_returned_quantities[item.id] = sum(
            returned_item.quantity for returned_item in returned_items
        )

    if request.method == "POST":
        try:
            # استيراد StockMovement محلياً لتجنب مشاكل الاستيراد الدائري
            from product.models import StockMovement
            
            with transaction.atomic():
                # إنشاء مرتجع المشتريات
                return_data = {
                    "date": request.POST.get("date") or timezone.now().date(),
                    "warehouse": purchase.warehouse.id,  # استخدام نفس مخزن الفاتورة
                    "notes": request.POST.get("notes", ""),
                }

                return_form = PurchaseReturnForm(return_data)
                if return_form.is_valid():
                    purchase_return = return_form.save(commit=False)
                    purchase_return.purchase = purchase
                    purchase_return.created_by = request.user
                    purchase_return.warehouse = (
                        purchase.warehouse
                    )  # استخدام نفس مخزن الفاتورة

                    # تعيين قيم افتراضية للحقول المطلوبة
                    purchase_return.subtotal = 0
                    purchase_return.discount = 0
                    purchase_return.tax = 0
                    purchase_return.total = 0

                    # تحديد رقم المرتجع
                    if not purchase_return.number:
                        from django.utils.crypto import get_random_string

                        purchase_return.number = f"RET-{get_random_string(6).upper()}"

                    purchase_return.save()

                    # إضافة بنود المرتجع
                    item_ids = request.POST.getlist("item_id")
                    return_quantities = request.POST.getlist("return_quantity")
                    return_reasons = request.POST.getlist("return_reason")

                    valid_items = False  # التحقق من وجود منتجات مرتجعة
                    subtotal = 0
                    for i in range(len(item_ids)):
                        if (
                            not item_ids[i]
                            or not return_quantities[i]
                            or int(return_quantities[i]) <= 0
                        ):
                            continue  # تجاهل البنود الفارغة أو الصفرية

                        try:
                            purchase_item = get_object_or_404(
                                PurchaseItem, id=item_ids[i]
                            )
                            return_quantity = int(float(return_quantities[i]))
                            previously_returned = previously_returned_quantities.get(
                                purchase_item.id, 0
                            )
                            available_quantity = (
                                purchase_item.quantity - previously_returned
                            )

                            return_reason = (
                                return_reasons[i]
                                if i < len(return_reasons) and return_reasons[i]
                                else "إرجاع بضاعة"
                            )

                            # التأكد من أن الكمية المرتجعة لا تتجاوز الكمية المتبقية
                            if return_quantity > available_quantity:
                                messages.warning(
                                    request,
                                    f"تم تعديل الكمية المرتجعة للمنتج {purchase_item.product.name} إلى {available_quantity} (الكمية المتبقية المتاحة للإرجاع)",
                                )
                                return_quantity = available_quantity

                            # تجاهل العناصر التي ليس لديها كمية متاحة للإرجاع
                            if return_quantity <= 0:
                                continue

                            # إنشاء بند المرتجع
                            return_item = PurchaseReturnItem(
                                purchase_return=purchase_return,
                                purchase_item=purchase_item,
                                product=purchase_item.product,
                                quantity=return_quantity,
                                unit_price=purchase_item.unit_price,
                                discount=0,  # تعيين قيمة افتراضية
                                total=(
                                    return_quantity * purchase_item.unit_price
                                ),  # حساب الإجمالي
                                reason=return_reason,
                            )
                            return_item.save()

                            valid_items = True  # تم إنشاء بند واحد على الأقل بنجاح

                            # تحديث المجموع
                            subtotal += return_item.total

                            # إنشاء حركة مخزون صادر (مرتجع مشتريات) عبر MovementService
                            from governance.services.movement_service import MovementService
                            movement_service = MovementService()
                            
                            movement_service.process_movement(
                                product_id=purchase_item.product.id,
                                quantity_change=return_quantity,
                                movement_type='out',
                                source_reference=f"PURCHASE_RETURN:{purchase_return.number}",
                                idempotency_key=f"SM:purchase_return:{purchase_return.id}:item:{return_item.id}",
                                user=request.user,
                                warehouse_id=purchase_return.warehouse.id,
                                document_number=purchase_return.number,
                                notes=f"مرتجع مشتريات - {return_reason}"
                            )
                        except Exception as e:
                            logger.error(f"Error processing return item: {str(e)}")
                            continue

                    if not valid_items:
                        # إذا لم يتم إضافة أي بنود صالحة، قم بإلغاء العملية
                        messages.error(
                            request, "يرجى تحديد كمية مرتجعة واحدة على الأقل"
                        )
                        raise Exception("لم يتم تحديد أي منتجات للإرجاع")

                    # تحديث المرتجع
                    purchase_return.subtotal = subtotal
                    purchase_return.tax = 0  # إزالة الضريبة
                    purchase_return.total = (
                        subtotal  # الإجمالي يساوي المجموع الفرعي بدون ضريبة
                    )
                    purchase_return.save()

                    messages.success(request, "تم إنشاء مرتجع المشتريات بنجاح")
                    return redirect("purchase:purchase_detail", pk=purchase.pk)
                else:
                    for field, errors in return_form.errors.items():
                        for error in errors:
                            messages.error(request, f"خطأ في حقل {field}: {error}")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء مرتجع المشتريات: {str(e)}")
            logger.error(f"Error creating purchase return: {str(e)}")

    # حساب الكميات المتبقية للعرض
    available_quantities = {}
    for item in items:
        available_quantities[item.id] = item.quantity - previously_returned_quantities.get(item.id, 0)
    
    context = {
        "purchase": purchase,
        "items": items,
        "page_title": f"مرتجع مشتريات",
        "page_subtitle": f"فاتورة {purchase.number} | {purchase.supplier.name}",
        "page_icon": "fas fa-undo-alt",
        "breadcrumb_items": [
            {
                "title": "لوحة التحكم",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-tachometer-alt",
            },
            {
                "title": "المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-shopping-basket",
            },
            {
                "title": f"فاتورة {purchase.number}",
                "url": reverse("purchase:purchase_detail", kwargs={"pk": purchase.pk}),
                "icon": "fas fa-file-invoice",
            },
            {"title": "مرتجع مشتريات", "active": True},
        ],
        "previously_returned_quantities": previously_returned_quantities,
        "has_returns": any(previously_returned_quantities.values()),
    }
    return render(request, "purchase/purchase_return.html", context)


@login_required
def purchase_return_list(request):
    """
    عرض وإدارة مرتجعات المشتريات وفق النظام الموحد ERP
    """
    queryset = PurchaseReturn.objects.select_related("purchase", "purchase__supplier").order_by("-date", "-id")

    # الفلترة
    supplier_id = request.GET.get("supplier")
    status_filter = request.GET.get("status")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if supplier_id:
        queryset = queryset.filter(purchase__supplier_id=supplier_id)
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if date_from:
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            queryset = queryset.filter(date__gte=d_from)
        except ValueError:
            pass
    if date_to:
        try:
            d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            queryset = queryset.filter(date__lte=d_to)
        except ValueError:
            pass

    # الكروت الإحصائية
    total_returns_count = PurchaseReturn.objects.count()
    total_returns_amount = PurchaseReturn.objects.aggregate(total=Sum("total"))["total"] or 0
    confirmed_returns_count = PurchaseReturn.objects.filter(status="confirmed").count()
    draft_returns_count = PurchaseReturn.objects.filter(status="draft").count()

    # Pagination
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    curr_sym = SystemSetting.get_currency_symbol()

    # تجهيز بيانات الجدول الموحد
    return_headers = [
        {"key": "id", "label": "#", "width": "5%", "class": "text-center"},
        {"key": "purchase_number", "label": "الفاتورة الأصلية", "width": "15%", "format": "html"},
        {"key": "supplier_name", "label": "المورد", "width": "25%"},
        {"key": "date", "label": "تاريخ المرتجع", "width": "15%", "class": "text-center"},
        {"key": "total_amount", "label": "إجمالي المرتجع", "width": "15%", "class": "text-end fw-bold"},
        {"key": "status", "label": "الحالة", "width": "10%", "class": "text-center", "format": "html"},
        {"key": "actions", "label": "الإجراءات", "width": "15%", "class": "text-center text-nowrap"}
    ]

    purchase_returns_data = []
    for ret in page_obj:
        if ret.status == 'confirmed':
            status_badge = '<span class="badge bg-success">مؤكد</span>'
        elif ret.status == 'cancelled':
            status_badge = '<span class="badge bg-danger">ملغي</span>'
        else:
            status_badge = '<span class="badge bg-secondary">مسودة</span>'

        purchase_num_html = f'<a href="/purchase/{ret.purchase.id}/" class="text-primary font-monospace fw-bold">{ret.purchase.number}</a>' if ret.purchase else '-'
        actions_html = f'<a href="/purchases/returns/{ret.id}/" class="btn btn-sm btn-outline-primary" title="عرض"><i class="fas fa-eye"></i></a>'

        purchase_returns_data.append({
            'id': ret.id,
            'purchase_number': purchase_num_html,
            'supplier_name': ret.purchase.supplier.name if (ret.purchase and ret.purchase.supplier) else '-',
            'date': ret.date.strftime('%Y-%m-%d') if ret.date else '-',
            'total_amount': f'{ret.total:,.2f} {curr_sym}',
            'status': status_badge,
            'actions': actions_html,
        })

    suppliers = Supplier.objects.filter(is_active=True).order_by("name")

    context = {
        "returns": page_obj,
        "purchase_returns_data": purchase_returns_data,
        "return_headers": return_headers,
        "total_returns_count": total_returns_count,
        "total_returns_amount": total_returns_amount,
        "confirmed_returns_count": confirmed_returns_count,
        "draft_returns_count": draft_returns_count,
        "suppliers": suppliers,
        "currency_symbol": curr_sym,
        "active_menu": "purchases",
        "title": "مرتجعات المشتريات",
        "page_title": "مرتجعات المشتريات",
        "page_subtitle": "عرض وإدارة جميع مرتجعات المشتريات",
        "page_icon": "fas fa-undo-alt",
        "header_buttons": [
            {
                "url": reverse("purchase:purchase_list"),
                "icon": "fa-shopping-cart",
                "text": "المشتريات",
                "class": "btn-outline-primary",
            },
        ],
        "breadcrumb_items": [
            {
                "title": "الرئيسية",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-home",
            },
            {
                "title": "المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-truck",
            },
            {"title": "مرتجعات المشتريات", "active": True},
        ],
    }

    return render(request, "purchase/purchase_return_list.html", context)


@login_required
def purchase_return_detail(request, pk):
    """
    عرض تفاصيل مرتجع المشتريات
    """
    purchase_return = get_object_or_404(PurchaseReturn, pk=pk)

    context = {
        "purchase_return": purchase_return,
        "page_title": f"مرتجع رقم {purchase_return.number}",
        "page_subtitle": f"فاتورة {purchase_return.purchase.number} | {purchase_return.purchase.supplier.name}",
        "page_icon": "fas fa-undo-alt",
        "header_buttons": ([] if purchase_return.status != 'draft' else [
            {
                "url": reverse("purchase:purchase_return_confirm", kwargs={"pk": purchase_return.pk}),
                "icon": "fa-check",
                "text": "تأكيد المرتجع",
                "class": "btn-success",
                "onclick": "return confirm('هل أنت متأكد من تأكيد هذا المرتجع؟')",
            },
            {
                "url": reverse("purchase:purchase_return_cancel", kwargs={"pk": purchase_return.pk}),
                "icon": "fa-times",
                "text": "إلغاء المرتجع",
                "class": "btn-danger",
                "onclick": "return confirm('هل أنت متأكد من إلغاء هذا المرتجع؟')",
            },
        ]),
        "breadcrumb_items": [
            {
                "title": "لوحة التحكم",
                "url": reverse("core:dashboard"),
                "icon": "fas fa-tachometer-alt",
            },
            {
                "title": "المشتريات",
                "url": reverse("purchase:purchase_list"),
                "icon": "fas fa-shopping-basket",
            },
            {
                "title": "مرتجعات المشتريات",
                "url": reverse("purchase:purchase_return_list"),
                "icon": "fas fa-undo-alt",
            },
            {"title": purchase_return.number, "active": True},
        ],
    }

    return render(request, "purchase/purchase_return_detail.html", context)


@login_required
def purchase_return_confirm(request, pk):
    """
    تأكيد مرتجع المشتريات وتغيير حالته من مسودة إلى مؤكد
    """
    purchase_return = get_object_or_404(PurchaseReturn, pk=pk)

    # التأكد من أن المرتجع في حالة مسودة
    if purchase_return.status != "draft":
        messages.error(request, "لا يمكن تأكيد مرتجع تم تأكيده أو إلغاؤه من قبل")
        return redirect("purchase:purchase_return_detail", pk=purchase_return.pk)

    try:
        with transaction.atomic():
            # تحديث حالة المرتجع إلى مؤكد
            purchase_return.status = "confirmed"
            purchase_return.save()

            # يمكن هنا إضافة أي إجراءات إضافية مثل تحديث حسابات المورد
            # أو إنشاء قيود محاسبية أو إرسال إشعارات للموردين المعنيين

            messages.success(request, "تم تأكيد مرتجع المشتريات بنجاح")
    except Exception as e:
        logger.error(f"Error confirming purchase return: {str(e)}")
        messages.error(request, f"حدث خطأ أثناء تأكيد المرتجع: {str(e)}")

    return redirect("purchase:purchase_return_detail", pk=purchase_return.pk)


@login_required
def purchase_return_cancel(request, pk):
    """
    إلغاء مرتجع المشتريات وتغيير حالته إلى ملغي
    """
    purchase_return = get_object_or_404(PurchaseReturn, pk=pk)

    # التأكد من أن المرتجع في حالة مسودة
    if purchase_return.status != "draft":
        messages.error(request, "لا يمكن إلغاء مرتجع تم تأكيده أو إلغاؤه من قبل")
        return redirect("purchase:purchase_return_detail", pk=purchase_return.pk)

    try:
        with transaction.atomic():
            # تحديث حالة المرتجع إلى ملغي
            purchase_return.status = "cancelled"
            purchase_return.save()

            # يمكن هنا إضافة أي إجراءات إضافية مثل عكس حركات المخزون المرتبطة بالمرتجع

            messages.success(request, "تم إلغاء مرتجع المشتريات بنجاح")
    except Exception as e:
        logger.error(f"Error cancelling purchase return: {str(e)}")
        messages.error(request, f"حدث خطأ أثناء إلغاء المرتجع: {str(e)}")

    return redirect("purchase:purchase_return_detail", pk=purchase_return.pk)
