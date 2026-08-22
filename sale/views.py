"""
Sale Views - Updated with SaleService
محدث: يستخدم SaleService مع AccountingGateway و MovementService
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext as _
from django.urls import reverse
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from decimal import Decimal
import logging

from sale.models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem
from sale.forms import SaleForm, SalePaymentForm, SaleReturnForm
from sale.services import SaleService
from product.models import Product, Warehouse, SerialNumber
from client.models import Customer
from core.models import SystemSetting

logger = logging.getLogger(__name__)


def get_status_color(status):
    colors = {
        'draft': 'secondary',
        'confirmed': 'success',
        'cancelled': 'danger',
        'completed': 'success',
        'pending': 'warning'
    }
    return colors.get(status, 'secondary')


def _extract_posted_items(request):
    """
    استخراج البنود المرسلة في POST لإعادة عرضها في الواجهة في حالة وجود خطأ للنموذج
    """
    product_ids = request.POST.getlist("product[]")
    quantities = request.POST.getlist("quantity[]")
    unit_prices = request.POST.getlist("unit_price[]")
    discounts = request.POST.getlist("discount[]")

    posted_items = []
    if product_ids:
        valid_ids = [int(p) for p in product_ids if p and str(p).isdigit()]
        if valid_ids:
            prod_map = {p.id: p for p in Product.objects.filter(id__in=valid_ids).select_related("unit")}
            for i in range(len(product_ids)):
                if product_ids[i] and str(product_ids[i]).isdigit():
                    p_id = int(product_ids[i])
                    prod_obj = prod_map.get(p_id)
                    if prod_obj:
                        try:
                            q = Decimal(str(quantities[i])) if i < len(quantities) and quantities[i] else Decimal("1")
                        except (ValueError, TypeError):
                            q = Decimal("1")
                        try:
                            p = Decimal(str(unit_prices[i]).replace(',', '')) if i < len(unit_prices) and unit_prices[i] else Decimal(str(prod_obj.selling_price))
                        except (ValueError, TypeError):
                            p = Decimal(str(prod_obj.selling_price))
                        try:
                            d = Decimal(str(discounts[i])) if i < len(discounts) and discounts[i] else Decimal("0")
                        except (ValueError, TypeError):
                            d = Decimal("0")
                        
                        item_cost_centers = request.POST.getlist("item_cost_center[]")
                        item_cc = int(item_cost_centers[i]) if (i < len(item_cost_centers) and item_cost_centers[i] and str(item_cost_centers[i]).isdigit()) else ""
                        
                        product_code = getattr(prod_obj, 'code', None) or getattr(prod_obj, 'sku', '') or ""
                        posted_items.append({
                            "id": prod_obj.id,
                            "product_id": prod_obj.id,
                            "code": product_code,
                            "name": prod_obj.name,
                            "quantity": float(q),
                            "unit_price": float(p),
                            "price": float(p),
                            "discount": float(d),
                            "cost_center": item_cc,
                            "is_service": prod_obj.is_service,
                            "unit": prod_obj.unit.name if prod_obj.unit else "",
                        })
    return posted_items


@login_required
def sale_create(request, customer_id=None):
    """
    إنشاء فاتورة مبيعات جديدة
    ✅ محدث: يستخدم SaleService مع الحوكمة الكاملة
    """
    # جلب نوع البنود المسموح بها من الإعدادات
    allowed_item_types = SystemSetting.get_setting('sale_invoice_item_types', 'both')

    # جلب المخزن الافتراضي
    default_warehouse = Warehouse.objects.filter(is_active=True).order_by("name").first()

    # بناء الفلتر للخدمات والمنتجات حسب الإعداد
    from django.db import models
    products_filter = models.Q(is_active=True, is_bundle=False)
    if allowed_item_types == 'products':
        products_filter &= models.Q(is_service=False)
    elif allowed_item_types == 'services':
        products_filter &= models.Q(is_service=True)

    # افتراضياً: المنتجات المادية اللي ليها stock في المخزن الافتراضي فقط (الخدمات تظهر دائماً)
    if default_warehouse:
        from product.models import Stock
        products_with_stock = Stock.objects.filter(
            warehouse=default_warehouse, quantity__gt=0
        ).values_list("product_id", flat=True)
        
        if allowed_item_types == 'both':
            products = Product.objects.filter(
                products_filter & (models.Q(is_service=True) | models.Q(id__in=products_with_stock))
            ).order_by("name")
        elif allowed_item_types == 'products':
            products = Product.objects.filter(
                products_filter & models.Q(id__in=products_with_stock)
            ).order_by("name")
        else:  # services
            products = Product.objects.filter(products_filter).order_by("name")
    else:
        products = Product.objects.filter(products_filter).order_by("name")
    
    # التحقق من وجود العميل إذا تم تمرير معرفه
    selected_customer = None
    if customer_id:
        try:
            selected_customer = Customer.objects.get(id=customer_id, is_active=True)
        except Customer.DoesNotExist:
            messages.error(request, "العميل المحدد غير موجود أو غير نشط")
            return redirect("sale:sale_list")

    # قراءة أمر الشغل إذا تم تمريره
    work_order_id = request.GET.get('work_order')
    selected_work_order = None
    if work_order_id:
        from work_order.models import WorkOrder
        try:
            selected_work_order = WorkOrder.objects.get(id=work_order_id)
            selected_customer = selected_work_order.customer
        except WorkOrder.DoesNotExist:
            pass

    posted_items = []
    if request.method == "POST":
        posted_items = _extract_posted_items(request)
        form = SaleForm(request.POST, user=request.user)

        if form.is_valid():
            try:
                discount_input = Decimal(request.POST.get("discount", "0") or "0")
                discount_type = request.POST.get("discount_type", "fixed")
                
                adjustment_name = request.POST.get("adjustment_name", "").strip()
                adjustment_type = request.POST.get("adjustment_type", "add")
                raw_adj_amount = Decimal(request.POST.get("adjustment_amount", "0") or "0")
                adj_amount = -abs(raw_adj_amount) if adjustment_type == "subtract" else abs(raw_adj_amount)

                # حساب المجموع الفرعي من البنود لحساب الخصم المئوي
                subtotal_calc = Decimal('0')
                product_ids = request.POST.getlist("product[]")
                quantities = request.POST.getlist("quantity[]")
                unit_prices = request.POST.getlist("unit_price[]")
                discounts = request.POST.getlist("discount[]")
                for i in range(len(product_ids)):
                    if product_ids[i]:
                        q = Decimal(quantities[i])
                        p = Decimal(unit_prices[i].replace(',', ''))
                        d = Decimal(discounts[i] if discounts[i] else '0')
                        subtotal_calc += max(Decimal('0'), q * p - d)

                if discount_type == "percentage":
                    if discount_input > Decimal("100"):
                        discount_input = Decimal("100")
                    discount_amount = (subtotal_calc * discount_input) / Decimal("100")
                else:
                    discount_amount = discount_input

                if discount_amount > subtotal_calc and subtotal_calc > 0:
                    discount_amount = subtotal_calc

                # تجهيز بيانات الفاتورة
                sale_data = {
                    'date': form.cleaned_data['date'],
                    'customer_id': form.cleaned_data['customer'].id,
                    'warehouse_id': form.cleaned_data['warehouse'].id,
                    'salesman': form.cleaned_data.get('salesman'),
                    'cost_center_id': form.cleaned_data.get('cost_center').id if form.cleaned_data.get('cost_center') else (request.POST.get('cost_center') or None),
                    'discount': discount_amount,
                    'discount_type': discount_type,
                    'adjustment_name': adjustment_name,
                    'adjustment_amount': adj_amount,
                    'tax': Decimal(request.POST.get("tax", "0")),
                    'notes': form.cleaned_data.get('notes', ''),
                    'currency_id': request.POST.get("currency"),
                    'exchange_rate': request.POST.get("exchange_rate", "1.0"),
                    'exchange_rate_override_reason': request.POST.get("exchange_rate_override_reason", ""),
                    'work_order_id': form.cleaned_data['work_order'].id if form.cleaned_data.get('work_order') else None,
                    'custom_fields': SaleService.parse_custom_fields(request.POST.get('custom_fields_json', '[]')),
                    'items': []
                }
                
                # معالجة نوع الفاتورة
                invoice_type = form.cleaned_data.get("invoice_type", "credit")
                payment_method = form.cleaned_data.get("payment_method", "")
                down_payment_amount = form.cleaned_data.get("down_payment_amount") or Decimal('0')

                if invoice_type == "cash":
                    sale_data['payment_method'] = payment_method if payment_method else "cash"
                elif invoice_type == "credit":
                    if down_payment_amount > Decimal('0'):
                        sale_data['payment_method'] = "credit_with_downpayment"
                    else:
                        sale_data['payment_method'] = "credit"
                else:
                    sale_data['payment_method'] = "credit"

                # التصنيف المالي
                financial_category = form.cleaned_data.get('financial_category')
                if financial_category:
                    sale_data['financial_category_id'] = financial_category.pk

                # تجهيز بيانات البنود
                product_ids = request.POST.getlist("product[]")
                quantities = request.POST.getlist("quantity[]")
                unit_prices = request.POST.getlist("unit_price[]")
                discounts = request.POST.getlist("discount[]")
                cost_centers = request.POST.getlist("item_cost_center[]")
                
                # التحقق من أن مندوب المبيعات لم يغير أسعار المنتجات
                if request.user.user_type == "sales_rep" and not request.user.is_superuser and not request.user.is_admin:
                    for i in range(len(product_ids)):
                        if product_ids[i]:
                            prod_id = int(product_ids[i])
                            input_price = Decimal(unit_prices[i].replace(',', ''))
                            prod_obj = Product.objects.get(pk=prod_id)
                            if Decimal(str(input_price)) != Decimal(str(prod_obj.selling_price)):
                                raise ValueError(f"غير مسموح لك بتغيير سعر المنتج '{prod_obj.name}'. السعر الرسمي هو {prod_obj.selling_price} ج.م")

                for i in range(len(product_ids)):
                    if product_ids[i]:
                        item_cc = int(cost_centers[i]) if (i < len(cost_centers) and cost_centers[i] and str(cost_centers[i]).isdigit()) else sale_data.get('cost_center_id')
                        sale_data['items'].append({
                            'product_id': int(product_ids[i]),
                            'quantity': Decimal(quantities[i]),
                            'unit_price': Decimal(unit_prices[i].replace(',', '')),
                            'discount': Decimal(discounts[i] if discounts[i] else '0'),
                            'cost_center_id': item_cc,
                        })
                
                # إنشاء الفاتورة مع معالجة الدفعة في وحدة تزامنية قواعد بيانات (Atomic Transaction)
                from django.db import transaction
                sale = None
                with transaction.atomic():
                    # إنشاء الفاتورة عبر SaleService (مع الحوكمة الكاملة)
                    sale = SaleService.create_sale(data=sale_data, user=request.user)
                    
                    # معالجة الدفعة التلقائية حسب نوع الفاتورة
                    if invoice_type == "cash":
                        if payment_method:
                            payment_data = {
                                'amount': sale.total,
                                'payment_method': payment_method,
                                'payment_date': sale.date,
                                'notes': 'دفعة تلقائية كاملة - فاتورة نقدية'
                            }
                            SaleService.process_payment(sale, payment_data, request.user)
                            logger.info(f"✅ تم إنشاء دفعة تلقائية كاملة للفاتورة النقدية: {sale.number}")
                        else:
                            raise ValueError("لم يتم اختيار حساب دفع للفاتورة النقدية")
                            
                    elif invoice_type == "credit" and down_payment_amount > Decimal('0'):
                        # التحقق من أن مبلغ الدفعة لا يتجاوز إجمالي الفاتورة
                        if down_payment_amount > sale.total:
                            raise ValueError(f"مبلغ الدفعة المقدمة ({down_payment_amount} ج.م) لا يمكن أن يتجاوز إجمالي الفاتورة ({sale.total} ج.م)")
                            
                        payment_data = {
                            'amount': down_payment_amount,
                            'payment_method': payment_method,
                            'payment_date': sale.date,
                            'notes': f'دفعة مقدمة تلقائية مع الفاتورة - المتبقي: {sale.total - down_payment_amount} ج.م' if down_payment_amount < sale.total else 'دفعة كاملة مع الفاتورة'
                        }
                        SaleService.process_payment(sale, payment_data, request.user)
                        logger.info(f"✅ تم إنشاء دفعة مقدمة للفاتورة: {sale.number}")
                
                messages.success(request, "تم إنشاء فاتورة المبيعات بنجاح")
                return redirect("sale:sale_detail", pk=sale.pk)

            except Exception as e:
                logger.error(f"❌ خطأ في إنشاء الفاتورة: {str(e)}")
                messages.error(request, str(e))
    else:
        # تهيئة بيانات افتراضية
        default_sale_notes = SystemSetting.get_setting('default_sale_invoice_notes', '')
        if not default_sale_notes:
            default_sale_notes = SystemSetting.get_setting('invoice_notes', '')

        from financial.services.account_helper import AccountHelperService
        default_cash = AccountHelperService.get_default_cash_account()

        initial_data = {
            "date": timezone.now().date(),
            "invoice_type": "credit",
            "notes": default_sale_notes,
        }
        if default_cash:
            initial_data["payment_method"] = default_cash.code
        if selected_customer:
            initial_data["customer"] = selected_customer
        if selected_work_order:
            initial_data["work_order"] = selected_work_order
        
        warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
        if warehouses.exists():
            initial_data["warehouse"] = warehouses.first()
            
        form = SaleForm(initial=initial_data, user=request.user)

    # الحصول على الرقم التسلسلي التالي (معاينة بدون حجز)
    next_sale_number = None
    try:
        from core.services.sequence_service import SequenceService
        from core.enums.document_types import DocumentType
        next_sale_number = SequenceService.peek_next_number(DocumentType.SALES_INVOICE)
    except Exception as e:
        logger.error(f"خطأ في الحصول على الرقم التالي: {str(e)}")

    # جلب البيانات للنموذج
    customers = Customer.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")

    # جلب التصنيفات للفلترة في مودال اختيار المنتج
    from product.models import Category
    category_filter = models.Q(is_active=True, products__is_active=True, products__is_bundle=False)
    if allowed_item_types == 'products':
        category_filter &= models.Q(products__is_service=False)
    elif allowed_item_types == 'services':
        category_filter &= models.Q(products__is_service=True)
        
    product_categories = Category.objects.filter(category_filter).distinct().order_by("name")

    customer_prepaid_balance = Decimal('0.00')
    if selected_customer and hasattr(selected_customer, 'available_prepaid_balance'):
        try:
            customer_prepaid_balance = selected_customer.available_prepaid_balance
        except Exception:
            pass

    import json
    custom_fields_merged = SaleService.smart_merge_custom_fields('sale', [])
    from financial.models import Currency
    context = {
        "products": products,
        "product_categories": product_categories,
        "allowed_item_types": allowed_item_types,
        "form": form,
        "next_sale_number": next_sale_number,
        "customers": customers,
        "warehouses": warehouses,
        "currencies": Currency.objects.filter(is_active=True).order_by("code"),
        "selected_customer": selected_customer,
        "customer_prepaid_balance": customer_prepaid_balance,
        "default_warehouse": warehouses.first() if warehouses.exists() else None,
        "posted_items_json": json.dumps(posted_items, cls=DjangoJSONEncoder) if posted_items else "null",
        "custom_fields_json": json.dumps(custom_fields_merged),
        "custom_fields_display_mode": SystemSetting.get_setting('custom_fields_display_mode', 'expanded'),
        "enable_custom_fields": SystemSetting.get_setting('enable_custom_fields', 'true'),
        "page_title": "إضافة فاتورة مبيعات" + (f" - {selected_customer.name}" if selected_customer else ""),
        "page_subtitle": "إضافة فاتورة مبيعات جديدة إلى النظام",
        "page_icon": "fas fa-file-invoice-dollar",
        "header_buttons": ([
            {
                "url": reverse("client:customer_detail", kwargs={"pk": selected_customer.pk}),
                "icon": "fa-arrow-right",
                "text": f"العودة لتفاصيل {selected_customer.name}",
                "class": "btn-secondary",
            }
        ] if selected_customer else []),
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fa-home"},
            *([
                {"title": _("أوامر الشغل"), "url": reverse("work_order:work_order_list"), "icon": "fa-briefcase"},
                {"title": selected_work_order.number, "url": reverse("work_order:work_order_detail", kwargs={"pk": selected_work_order.pk}), "icon": "fa-file-alt"},
            ] if selected_work_order else [
                {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
            ] + ([{
                "title": selected_customer.name,
                "url": reverse("client:customer_detail", kwargs={"pk": selected_customer.pk}),
                "icon": "fa-user",
            }] if selected_customer else [])),
            {"title": _("إضافة فاتورة مبيعات"), "active": True, "icon": "fa-plus-circle"},
        ],
    }

    return render(request, "sale/sale_form.html", context)


@login_required
def sale_delete(request, pk):
    """
    حذف فاتورة مبيعات
    ✅ محدث: يستخدم SaleService للحذف الآمن
    """
    sale = get_object_or_404(Sale, pk=pk)

    if request.method == "POST":
        try:
            sale_number = sale.number
            
            # حذف الفاتورة عبر SaleService (مع التراجع الكامل)
            SaleService.delete_sale(sale, request.user)
            
            messages.success(request, f"تم حذف فاتورة المبيعات {sale_number} بنجاح")
            return redirect("sale:sale_list")
            
        except Exception as e:
            from django.db.models import ProtectedError
            if isinstance(e, ProtectedError) or 'PROTECT' in str(type(e)):
                messages.error(request, "عفواً، لا يمكن حذف هذه الفاتورة لوجود مدفوعات أو سجلات مالية حساسة مرتبطة بها. يرجى إلغاء المدفوعات أولاً.")
            else:
                logger.error(f"❌ خطأ في حذف الفاتورة: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء حذف الفاتورة: {str(e)}")
            return redirect("sale:sale_detail", pk=pk)

    context = {
        "sale": sale,
        "page_title": f"حذف فاتورة {sale.number}",
        "page_subtitle": "تأكيد حذف فاتورة المبيعات",
        "page_icon": "fas fa-trash",
    }
    return render(request, "sale/sale_confirm_delete.html", context)


@login_required
def add_payment(request, pk):
    """
    إضافة دفعة على فاتورة مبيعات
    ✅ محدث: يستخدم SaleService لمعالجة الدفعات
    """
    import uuid
    from financial.models import CostCenter
    
    sale = get_object_or_404(Sale, pk=pk)

    # التحقق من أن الفاتورة غير مسددة بالكامل
    if sale.amount_due <= Decimal('0.00') or sale.payment_status == 'paid':
        messages.info(request, f"فاتورة المبيعات #{sale.number} مسددة بالكامل بالفعل.")
        return redirect("sale:sale_detail", pk=sale.pk)

    if request.method == "POST":
        form = SalePaymentForm(request.POST, sale=sale)
        if form.is_valid():
            try:
                # تجهيز بيانات الدفعة
                payment_data = {
                    'amount': form.cleaned_data['amount'],
                    'payment_method': request.POST.get('payment_method'),  # من payment_account_select
                    'payment_exchange_rate': request.POST.get('payment_exchange_rate'),
                    'amount_paid_currency': request.POST.get('amount_paid_currency'),
                    'payment_date': form.cleaned_data.get('payment_date', timezone.now().date()),
                    'cost_center_id': request.POST.get('cost_center') or None,
                    'reference_number': request.POST.get('reference_number') or '',
                    'notes': form.cleaned_data.get('notes', ''),
                    'idempotency_key': request.POST.get('idempotency_token') or None,
                }
                
                # معالجة الدفعة عبر SaleService
                payment = SaleService.process_payment(sale, payment_data, request.user)
                
                messages.success(request, f"تم إضافة الدفعة بنجاح - المبلغ: {payment.amount} ج.م")
                return redirect("sale:sale_detail", pk=sale.pk)
                
            except Exception as e:
                logger.error(f"❌ خطأ في إضافة الدفعة: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء إضافة الدفعة: {str(e)}")
        else:
            messages.error(request, "يرجى تصحيح الأخطاء في النموذج")
    else:
        initial_data = {
            'amount': sale.amount_due,
            'payment_date': timezone.now().date(),
        }
        form = SalePaymentForm(initial=initial_data, sale=sale)

    customer_prepaid = Decimal('0.00')
    if sale.customer and hasattr(sale.customer, 'available_prepaid_balance'):
        customer_prepaid = sale.customer.available_prepaid_balance

    context = {
        "invoice": sale,  # الـ template بيستخدم invoice
        "sale": sale,  # للتوافق
        "form": form,
        "is_purchase": False,  # للتمييز بين المبيعات والمشتريات
        "customer_prepaid_balance": customer_prepaid,
        "cost_centers": CostCenter.objects.filter(is_active=True).order_by('code'),
        "idempotency_token": uuid.uuid4().hex,
        "page_title": f"إضافة دفعة - فاتورة مبيعات #{sale.number}",
        "page_subtitle": f"المبلغ المستحق: {sale.amount_due} ج.م | العميل: {sale.customer.name if sale.customer else '-'}",
        "page_icon": "fas fa-money-bill-wave",
        "header_buttons": [
            {
                "url": reverse("sale:sale_detail", kwargs={"pk": sale.pk}),
                "icon": "fa-arrow-right",
                "text": "العودة للفاتورة",
                "class": "btn-outline-secondary",
            }
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": f"فاتورة {sale.number}", "url": reverse("sale:sale_detail", kwargs={"pk": sale.pk}), "icon": "fas fa-file-invoice"},
            {"title": "إضافة دفعة", "active": True},
        ],
    }
    return render(request, "sale/sale_payment_form.html", context)


@login_required
def allocate_prepaid_balance(request, pk):
    """
    تخصيص رصيد مسبق للعميل على فاتورة مبيعات (آلياً FIFO أو يدوي)
    """
    sale = get_object_or_404(Sale, pk=pk)
    if request.method == "POST":
        amount_str = request.POST.get("amount")
        is_auto = request.POST.get("auto_fifo") == "true"

        try:
            from client.services.customer_allocation_audit_service import CustomerAllocationAuditService
            from decimal import Decimal
            available = sale.customer.available_prepaid_balance if sale.customer else Decimal("0.00")
            open_amount = sale.total - (sale.amount_paid or Decimal("0.00"))

            if is_auto:
                alloc_amount = min(available, open_amount)
            else:
                alloc_amount = Decimal(amount_str) if amount_str else Decimal("0.00")

            if alloc_amount <= Decimal("0.00"):
                messages.error(request, "يرجى إدخال مبلغ تخصيص أكبر من صفر.")
            elif alloc_amount > available:
                messages.error(request, f"المبلغ المطلوب ({alloc_amount}) يتجاوز الرصيد المسبق المتاح للعميل ({available}).")
            else:
                CustomerAllocationAuditService.allocate_customer_prepaid_balance_to_sale(
                    sale=sale,
                    amount_to_allocate=alloc_amount,
                    user=request.user
                )
                messages.success(request, f"تم تخصيص {alloc_amount} ج.م من الرصيد المسبق على الفاتورة بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء تخصيص الرصيد المسبق: {str(e)}")

    return redirect("sale:sale_detail", pk=sale.pk)


@login_required
def sale_return(request, pk):
    """
    إنشاء مرتجع لفاتورة مبيعات
    ✅ محدث: يستخدم SaleService لإنشاء المرتجعات
    """
    sale = get_object_or_404(Sale, pk=pk)

    if request.method == "POST":
        try:
            sale_item_ids = request.POST.getlist("sale_item[]")
            quantities = request.POST.getlist("quantity[]")

            # التحقق من وجود كميات مرتجعة
            has_returns = any(
                q and int(float(q)) > 0
                for q in quantities
            )
            if not has_returns:
                messages.error(request, "يجب تحديد كمية مرتجعة واحدة على الأقل")
            else:
                return_data = {
                    'date': request.POST.get('date') or timezone.now().date(),
                    'reason': '',
                    'notes': '',
                    'items': []
                }

                for i in range(len(sale_item_ids)):
                    if sale_item_ids[i] and quantities[i]:
                        qty = int(float(quantities[i]))
                        if qty > 0:
                            sale_item = get_object_or_404(SaleItem, id=sale_item_ids[i], sale=sale)
                            return_data['items'].append({
                                'sale_item_id': int(sale_item_ids[i]),
                                'quantity': Decimal(str(qty)),
                                'unit_price': sale_item.unit_price,
                            })

                sale_return = SaleService.create_return(sale, return_data, request.user)
                messages.success(request, f"تم إنشاء المرتجع بنجاح - رقم المرتجع: {sale_return.number}")
                return redirect("sale:sale_return_detail", pk=sale_return.pk)

        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء المرتجع: {str(e)}")
            messages.error(request, f"حدث خطأ أثناء إنشاء المرتجع: {str(e)}")
    else:
        initial_data = {
            'date': timezone.now().date(),
        }
        form = SaleReturnForm(initial=initial_data)

    context = {
        "sale": sale,
        "sale_items": sale.items.all(),
        "page_title": f"إنشاء مرتجع - فاتورة {sale.number}",
        "page_subtitle": f"العميل: {sale.customer.name}",
        "page_icon": "fas fa-undo",
        "header_buttons": [],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": f"فاتورة {sale.number}", "url": reverse("sale:sale_detail", kwargs={"pk": sale.pk}), "icon": "fas fa-file-invoice"},
            {"title": "إنشاء مرتجع", "active": True},
        ],
    }
    return render(request, "sale/sale_return_form.html", context)


@login_required
def sale_detail(request, pk):
    """
    عرض تفاصيل فاتورة مبيعات
    ✅ محدث: يستخدم معمارية with_details() المجمعة للأداء وسرعة الاستجابة
    """
    sale_qs = Sale.objects.with_details()
    if not request.user.is_superuser and not request.user.is_staff:
        if hasattr(request.user, 'warehouse') and request.user.warehouse:
            sale_qs = sale_qs.filter(warehouse=request.user.warehouse)
        elif not request.user.has_perm('sale.view_sale'):
            sale_qs = sale_qs.filter(created_by=request.user)

    sale = get_object_or_404(sale_qs, pk=pk)
    
    # الحصول على البنود والدفعات والمرتجعات في قوائم صريحة بالذاكرة لمنع Lazy Evaluation
    items = list(sale.items.all())
    payments = list(sale.payments.all())
    returns = list(sale.returns.all())
    
    # الحصول على الإحصائيات من SaleService بتمرير القوائم المجلوبة
    statistics = SaleService.get_sale_statistics(sale, items=items, returns=returns)
    is_service_invoice = all(item.product and getattr(item.product, 'is_service', False) for item in items)

    context = {
        "sale": sale,
        "items": items,
        "payments": payments,
        "returns": returns,
        "is_service_invoice": is_service_invoice,
        "statistics": statistics,
        "title": f"فاتورة مبيعات {sale.number}",
        "page_title": f"فاتورة مبيعات {sale.number}",
        "page_subtitle": _('العميل: <a href="{}" class="text-decoration-none fw-bold text-primary"><i class="fas fa-user-tie me-1"></i>{}</a>').format(
            reverse("client:customer_detail", kwargs={"pk": sale.customer.id}),
            sale.customer.name
        ),
        "page_icon": "fas fa-file-invoice-dollar",
        "header_buttons": ([{
            "url": reverse("sale:sale_add_payment", kwargs={"pk": sale.pk}),
            "icon": "fa-money-bill",
            "text": "إضافة دفعة",
            "class": "btn-success",
        }] if sale.payment_status != 'paid' else []) + [
            {
                "url": reverse("sale:sale_print", kwargs={"pk": sale.pk}),
                "icon": "fa-print",
                "text": "طباعة",
                "class": "btn-info",
            },
            {
                "dropdown": True,
                "icon": "fa-file-pdf",
                "text": "مشاركة",
                "class": "btn-success",
                "items": [
                    {
                        "onclick": f"downloadDocumentPDF('{reverse('sale:sale_pdf_download', kwargs={'pk': sale.pk})}', '{reverse('sale:sale_print', kwargs={'pk': sale.pk})}', '{sale.number}')",
                        "icon": "fas fa-file-download text-primary",
                        "text": "تحميل PDF"
                    },
                    {
                        "onclick": f"shareWhatsAppPDF('{sale.customer.phone if sale.customer and sale.customer.phone else ''}', '{sale.number}', 'فاتورة مبيعات', '{reverse('sale:sale_pdf_download', kwargs={'pk': sale.pk})}', '{reverse('sale:sale_print', kwargs={'pk': sale.pk})}')",
                        "icon": "fab fa-whatsapp text-success",
                        "text": "إرسال واتساب"
                    },
                    {
                        "onclick": f"sendEmailPDF('{reverse('sale:sale_email_pdf', kwargs={'pk': sale.pk})}', '{sale.customer.email if sale.customer and sale.customer.email else ''}', '{sale.number}', 'فاتورة مبيعات', '{reverse('sale:sale_pdf_download', kwargs={'pk': sale.pk})}', '{reverse('sale:sale_print', kwargs={'pk': sale.pk})}')",
                        "icon": "far fa-envelope text-primary",
                        "text": "إرسال بريد"
                    }
                ]
            },
            {
                "url": reverse("sale:sale_duplicate", kwargs={"pk": sale.pk}),
                "icon": "fa-copy",
                "text": "نسخ",
                "class": "btn-outline-primary",
            },
            {
                "url": "#",
                "icon": "fa-ellipsis-v",
                "text": "",
                "class": "btn-outline-secondary",
                "toggle": "modal",
                "target": "#actionsModal",
            },
        ],
        "page_title": f"فاتورة مبيعات {sale.number}",
        "page_subtitle": _('العميل: <a href="{}" class="text-decoration-none fw-bold text-primary"><i class="fas fa-user-tie me-1"></i>{}</a>').format(
            reverse("client:customer_detail", kwargs={"pk": sale.customer.id}),
            sale.customer.name
        ),
        "page_icon": "fas fa-file-invoice",
        "header_badges": [
            *([{"text": sale.work_order.number, "class": "bg-info text-white", "icon": "fas fa-tasks", "url": reverse("work_order:work_order_detail", kwargs={"pk": sale.work_order.pk})}] if hasattr(sale, 'work_order') and sale.work_order else []),
            *([{"text": sale.get_status_display(), "class": f"bg-{get_status_color(sale.status)} text-white", "icon": "fas fa-info-circle"}] if sale.status != 'confirmed' else []),
        ],
        "active_menu": "sales",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            *([
                {"title": "أوامر الشغل", "url": reverse("work_order:work_order_list"), "icon": "fas fa-tasks"},
                {"title": f"أمر شغل {sale.work_order.number}", "url": reverse("work_order:work_order_detail", kwargs={"pk": sale.work_order.pk})},
            ] if hasattr(sale, 'work_order') and sale.work_order else [
                {"title": "المبيعات", "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            ]),
            {"title": f"فاتورة مبيعات {sale.number}", "active": True},
        ],
    }
    return render(request, "sale/sale_detail.html", context)



@login_required
def sale_list(request):
    """
    عرض قائمة فواتير المبيعات
    """
    sales_query = Sale.objects.with_list_details().all().order_by("-date", "-id")

    # تصفية حسب نص البحث
    search_query = request.GET.get("search") or request.GET.get("q")
    if search_query:
        search_query = search_query.strip()
        sales_query = sales_query.filter(
            models.Q(number__icontains=search_query) |
            models.Q(customer__name__icontains=search_query) |
            models.Q(notes__icontains=search_query) |
            models.Q(custom_fields__icontains=search_query)
        )

    # تصفية حسب العميل
    customer = request.GET.get("customer")
    if customer:
        sales_query = sales_query.filter(customer_id=customer)

    # تصفية حسب المخزن
    warehouse = request.GET.get("warehouse")
    if warehouse:
        sales_query = sales_query.filter(warehouse_id=warehouse)

    # تصفية حسب مسؤول المبيعات
    salesman_filter = request.GET.get("salesman")
    if salesman_filter:
        sales_query = sales_query.filter(models.Q(salesman_id=salesman_filter) | models.Q(created_by_id=salesman_filter))

    # تصفية حسب حالة الدفع
    payment_status = request.GET.get("payment_status")
    if payment_status:
        sales_query = sales_query.filter(payment_status=payment_status)

    # تصفية حسب التاريخ
    date_from = request.GET.get("date_from")
    if date_from:
        sales_query = sales_query.filter(date__gte=date_from)

    date_to = request.GET.get("date_to")
    if date_to:
        sales_query = sales_query.filter(date__lte=date_to)

    # التصدير المزدوج: تصدير كافة الفواتير المفلترة من الباك إند
    if request.GET.get('export') == 'excel':
        from utils.export import export_queryset_to_excel
        return export_queryset_to_excel(
            sales_query,
            filename="sales_invoices_export.xlsx",
            fields=["number", "created_at", "customer.name", "total", "amount_paid", "amount_due", "payment_status"],
            headers=["رقم الفاتورة", "التاريخ", "العميل", "الإجمالي", "المدفوع", "المتبقي", "حالة الدفع"]
        )

    # Whitelist الفرز الأمني
    allowed_sort_fields = {
        'number': 'number',
        'created_at': 'created_at',
        'customer': 'customer__name',
        'salesman': 'created_by__username',
        'total': 'total',
        'amount_due': 'amount_due',
        'payment_status': 'payment_status',
    }

    # الترقيم والفرز الـ SSR عبر المحرك المركزي
    from core.utils import paginate_queryset, render_paginated_response
    pagination_data = paginate_queryset(
        sales_query,
        request,
        default_per_page=25,
        allowed_sort_fields=allowed_sort_fields
    )

    sales_page = pagination_data['page_obj']
    
    # تحويل الـ queryset لـ list of dicts للجدول الموحد
    sales_data = []
    for sale in sales_page:
        # تحديد حالة الدفع badge
        if sale.payment_status == 'paid':
            payment_status_html = '<span class="badge bg-success">مدفوعة</span>'
        elif sale.payment_status == 'partially_paid':
            payment_status_html = '<span class="badge bg-warning">مدفوعة جزئياً</span>'
        else:
            payment_status_html = '<span class="badge bg-danger">غير مدفوعة</span>'
        
        # أزرار الإجراءات
        actions = []

        # زر عرض التفاصيل
        actions.append({
            'url': reverse('sale:sale_detail', args=[sale.pk]),
            'icon': 'fa-eye',
            'label': 'عرض التفاصيل',
            'class': 'action-view',
        })

        # زر إضافة دفعة (إذا لم تكن مدفوعة بالكامل)
        if sale.payment_status != 'paid':
            actions.append({
                'url': reverse('sale:sale_add_payment', args=[sale.pk]),
                'icon': 'fa-money-bill-wave',
                'label': 'إضافة دفعة',
                'class': 'action-paid',
            })

        # زر الطباعة (للفواتير المدفوعة فقط)
        if sale.payment_status == 'paid':
            actions.append({
                'url': reverse('sale:sale_print', args=[sale.pk]),
                'icon': 'fa-print',
                'label': 'طباعة',
                'class': 'action-print',
                'target': '_blank',
            })

        # زر نسخ الفاتورة
        actions.append({
            'url': reverse('sale:sale_duplicate', args=[sale.pk]),
            'icon': 'fa-copy',
            'label': 'نسخ الفاتورة',
            'class': 'action-copy',
        })
        
        sales_data.append({
            'id': sale.id,
            'number': sale.number,
            'created_at': sale.created_at,
            'customer': sale.customer.name if sale.customer else '-',
            'salesman': sale.salesman_display_name,
            'warehouse': sale.warehouse.name if sale.warehouse else '-',
            'total': sale.total,
            'amount_paid': sale.amount_paid,
            'amount_due': sale.amount_due,
            'currency_symbol': sale.currency_symbol,
            'payment_status': payment_status_html,
            'actions': actions
        })

    # إحصائيات
    paid_sales_count = Sale.objects.filter(payment_status="paid").count()
    partially_paid_sales_count = Sale.objects.filter(payment_status="partially_paid").count()
    unpaid_sales_count = Sale.objects.filter(payment_status="unpaid").count()
    returned_sales_count = Sale.objects.filter(returns__status="confirmed").distinct().count()
    total_amount = Sale.objects.aggregate(Sum("total"))["total__sum"] or 0

    allowed_types = SystemSetting.get_setting('sale_invoice_item_types', 'both')

    customers = Customer.objects.filter(id__in=Sale.objects.values('customer_id')).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name") if allowed_types != 'services' else Warehouse.objects.none()

    from django.contrib.auth import get_user_model
    User = get_user_model()
    salesmen = User.objects.filter(is_active=True).order_by("first_name", "username")

    # إعداد headers للجدول الموحد
    sale_headers = [
        {
            'key': 'number',
            'label': 'رقم الفاتورة',
            'sortable': True,
            'class': 'text-center',
            'format': 'reference',
            'variant': 'highlight-code',
            'app': 'sale',
        },
        {
            'key': 'created_at',
            'label': 'التاريخ',
            'sortable': True,
            'class': 'text-center',
            'format': 'datetime_12h',
        },
        {'key': 'customer', 'label': 'العميل', 'sortable': True, 'width': '18%', 'class': 'fw-bold'},
        {'key': 'salesman', 'label': 'مسؤول المبيعات', 'sortable': True, 'class': 'text-center'},
    ]
    if allowed_types != 'services':
        sale_headers.append({'key': 'warehouse', 'label': 'المخزن', 'sortable': True, 'width': '12%'})
        
    sale_headers.extend([
        {'key': 'total', 'label': 'الإجمالي', 'sortable': True, 'class': 'text-center', 'format': 'currency'},
        {'key': 'amount_due', 'label': 'المتبقي', 'sortable': True, 'class': 'text-center', 'format': 'currency', 'variant': 'text-danger'},
        {'key': 'payment_status', 'label': 'حالة الدفع', 'sortable': True, 'class': 'text-center', 'format': 'html'},
        {'key': 'actions', 'label': 'الإجراءات', 'width': '1%', 'class': 'text-center text-nowrap'}
    ])

    context = {
        **pagination_data,
        "sales": sales_page,
        "sales_data": sales_data,
        "sale_headers": sale_headers,
        "paid_sales_count": paid_sales_count,
        "partially_paid_sales_count": partially_paid_sales_count,
        "unpaid_sales_count": unpaid_sales_count,
        "returned_sales_count": returned_sales_count,
        "total_amount": total_amount,
        "customers": customers,
        "warehouses": warehouses,
        "salesmen": salesmen,
        "selected_customer": customer,
        "selected_warehouse": warehouse,
        "selected_salesman": salesman_filter,
        "selected_payment_status": payment_status,
        "date_from": date_from,
        "date_to": date_to,
        "show_export": True,
        "title": "فواتير المبيعات",
        "page_title": "فواتير المبيعات",
        "page_subtitle": "عرض وإدارة فواتير المبيعات",
        "page_icon": "fas fa-shopping-cart",
        "header_buttons": [
            {
                "url": reverse("sale:sale_create"),
                "icon": "fa-plus-circle",
                "text": "إضافة فاتورة جديدة",
                "class": "btn-primary",
            }
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "active": True, "icon": "fas fa-shopping-cart"},
        ],
    }

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        from django.http import JsonResponse
        table_html = render_to_string('components/data_table.html', {
            'table_id': 'sales-table',
            'headers': sale_headers,
            'data': sales_data,
            'empty_message': 'لا توجد فواتير مبيعات متاحة',
            'table_class': 'hover',
            'primary_key': 'id',
            'clickable_rows': True,
            'row_click_url': '/sales/0/',
            'show_currency': True,
            'disable_pagination': True,
            'show_search': False,
            'show_length_menu': False,
            'sortable': False
        }, request=request)
        pagination_html = render_to_string('partials/pagination.html', context, request=request)
        return JsonResponse({
            'table_html': table_html,
            'pagination_html': pagination_html
        })

    return render(request, "sale/sale_list.html", context)


def get_sale_print_context(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    items = sale.items.all().select_related('product', 'product__unit', 'product__category')
    
    default_lang = SystemSetting.get_default_print_language()
    print_lang = request.GET.get('lang', default_lang).lower()
    if print_lang not in ['ar', 'en']:
        print_lang = 'ar'
    
    is_english = (print_lang == 'en')
    is_bilingual = False
    print_dir = 'ltr' if is_english else 'rtl'
    
    company_name = SystemSetting.objects.filter(key="company_name").values_list("value", flat=True).first() or "مؤسسة موهبة"
    company_address = SystemSetting.objects.filter(key="company_address").values_list("value", flat=True).first() or ""
    company_phone = SystemSetting.objects.filter(key="company_phone").values_list("value", flat=True).first() or ""
    company_tax_number = SystemSetting.objects.filter(key="company_tax_number").values_list("value", flat=True).first() or ""
    company_logo = SystemSetting.objects.filter(key="company_logo").values_list("value", flat=True).first() or ""
    company_email = SystemSetting.objects.filter(key="company_email").values_list("value", flat=True).first() or ""
    company_website = SystemSetting.objects.filter(key="company_website").values_list("value", flat=True).first() or ""

    if is_english:
        company_name_active = SystemSetting.get_setting('company_name_en') or SystemSetting.get_setting('site_name_en') or company_name
        company_address_active = SystemSetting.get_company_address_en() or company_address
        invoice_title_active = SystemSetting.get_invoice_title_sale_en()
        default_notes = SystemSetting.get_sale_invoice_notes_en()
        sale_currency = getattr(sale, 'currency', None)
        currency_symbol_active = sale_currency if (sale_currency and sale_currency != 'ج.م') else SystemSetting.get_currency_symbol_en()
        status_map = {
            'paid': 'PAID',
            'unpaid': 'UNPAID',
            'partial': 'PARTIALLY PAID',
            'draft': 'DRAFT'
        }
    elif is_bilingual:
        company_name_en = SystemSetting.get_setting('company_name_en') or SystemSetting.get_setting('site_name_en') or ''
        company_name_active = f"{company_name} / {company_name_en}" if company_name_en else company_name
        company_address_active = company_address
        invoice_title_active = "فاتورة مبيعات / Sales Invoice"
        default_notes = SystemSetting.get_setting('default_sale_invoice_notes', '')
        currency_symbol_active = getattr(sale, 'currency', None) or SystemSetting.get_currency_symbol()
        status_map = {
            'paid': 'مدفوع بالكامل / PAID',
            'unpaid': 'غير مدفوع / UNPAID',
            'partial': 'مدفوع جزئياً / PARTIAL',
            'draft': 'مسودة / DRAFT'
        }
    else:
        company_name_active = company_name
        company_address_active = company_address
        invoice_title_active = "فاتورة مبيعات"
        default_notes = SystemSetting.get_setting('default_sale_invoice_notes', '')
        currency_symbol_active = getattr(sale, 'currency', None) or SystemSetting.get_currency_symbol()
        status_map = {
            'paid': 'مدفوع بالكامل',
            'unpaid': 'غير مدفوع',
            'partial': 'مدفوع جزئياً',
            'draft': 'مسودة'
        }

    status_code = getattr(sale, 'payment_status', getattr(sale, 'status', 'unpaid'))
    translated_status = status_map.get(str(status_code).lower(), str(status_code))
    
    is_service_invoice = all(item.product.is_service for item in items)
    context = {
        "sale": sale,
        "items": items,
        "company_name": company_name_active,
        "company_address": company_address_active,
        "company_phone": company_phone,
        "company_tax_number": company_tax_number,
        "company_logo": company_logo,
        "company_email": company_email,
        "company_website": company_website,
        "title": f"{invoice_title_active} - {sale.number}",
        "document_title": invoice_title_active,
        "print_lang": print_lang,
        "print_dir": print_dir,
        "is_english": is_english,
        "is_bilingual": is_bilingual,
        "currency_symbol_active": currency_symbol_active,
        "default_notes": default_notes,
        "translated_status": translated_status,
        "is_service_invoice": is_service_invoice,
        "has_item_discounts": sale.has_item_discounts,
        "salesman_name": sale.salesman_display_name,
    }
    return sale, context


@login_required
def sale_print(request, pk):
    """
    طباعة فاتورة مبيعات (عربي / إنجليزي / ثنائي اللغة)
    """
    sale, context = get_sale_print_context(request, pk)
    return render(request, "sale/sale_print.html", context)


@login_required
def sale_pdf_download(request, pk):
    """
    تصدير/تحميل فاتورة مبيعات مباشرة كـ PDF بنسق نقي
    """
    from django.template.loader import render_to_string
    from utils.pdf_utils import generate_pdf_from_html, generate_guaranteed_pdf_response
    
    sale, context = get_sale_print_context(request, pk)
    
    try:
        html_content = render_to_string("sale/sale_print.html", context, request=request)
        pdf_response = generate_pdf_from_html(html_content, request=request, filename=f"{sale.number}.pdf", doc_type="sale", context=context)
        
        if pdf_response:
            return pdf_response
    except Exception as e:
        logger.error(f"Sale PDF generation error for {sale.number}: {e}")
        
    return generate_guaranteed_pdf_response("sale", context, filename=f"{sale.number}.pdf")


@login_required
def sale_email_pdf(request, pk):
    """
    إرسال الفاتورة عبر البريد الإلكتروني للعميل مباشرة
    """
    from django.http import JsonResponse
    sale = get_object_or_404(Sale, pk=pk)
    customer_email = sale.customer.email if sale.customer and sale.customer.email else None
    if not customer_email:
        return JsonResponse({'success': False, 'message': 'لا يوجد بريد إلكتروني مسجل للعميل'}, status=400)
    
    try:
        from utils.email_utils import send_email
        subject = f"فاتورة مبيعات #{sale.number}"
        body = f"مرحباً {sale.customer.name}،\n\nيرجى الاطلاع على فاتورة المبيعات الخاصة بكم رقم #{sale.number}.\n\nرابط الفاتورة المباشر:\n{request.build_absolute_uri(reverse('sale:sale_print', kwargs={'pk': sale.pk}))}\n\nشكراً لتعاملكم معنا."
        send_email(subject, body, [customer_email])
        return JsonResponse({'success': True, 'message': 'تم إرسال البريد بنجاح!'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def sale_print_thermal(request, pk):
    """
    طباعة فاتورة حرارية لمبيعات
    """
    import qrcode
    import io
    import base64
    
    enable_thermal = SystemSetting.get_setting('enable_thermal_printing', 'false') == 'true'
    if not enable_thermal:
        messages.error(request, "الطباعة الحرارية غير مفعلة في إعدادات النظام")
        return redirect("sale:sale_detail", pk=pk)

    sale = get_object_or_404(Sale, pk=pk)
    items = sale.items.all()
    
    # جلب الإعدادات المحددة للشركة وعرض الورق
    company_name = SystemSetting.objects.filter(key="company_name").values_list("value", flat=True).first() or "مؤسسة موهبة"
    company_address = SystemSetting.objects.filter(key="company_address").values_list("value", flat=True).first() or ""
    company_phone = SystemSetting.objects.filter(key="company_phone").values_list("value", flat=True).first() or ""
    company_tax_number = SystemSetting.objects.filter(key="company_tax_number").values_list("value", flat=True).first() or ""
    company_logo = SystemSetting.objects.filter(key="company_logo").values_list("value", flat=True).first() or ""
    
    paper_width = SystemSetting.objects.filter(key="receipt_paper_width").values_list("value", flat=True).first() or "80"
    
    # توليد كود الـ QR
    qr_text = (
        f"المؤسسة: {company_name}\n"
        f"الرقم الضريبي: {company_tax_number}\n"
        f"التاريخ: {sale.created_at.strftime('%Y-%m-%d %H:%M') if sale.created_at else ''}\n"
        f"رقم الفاتورة: {sale.number}\n"
        f"الإجمالي: {sale.total}\n"
        f"الضريبة: {sale.tax}"
    )
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=5,
        border=1
    )
    qr.add_data(qr_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    
    is_service_invoice = all(item.product.is_service for item in items)
    context = {
        "sale": sale,
        "items": items,
        "company_name": company_name,
        "company_address": company_address,
        "company_phone": company_phone,
        "company_tax_number": company_tax_number,
        "company_logo": company_logo,
        "paper_width": paper_width,
        "qr_code": qr_code_base64,
        "title": f"فاتورة حرارية - {sale.number}",
        "is_service_invoice": is_service_invoice,
    }
    
    return render(request, "sale/sale_print_thermal.html", context)


@login_required
def sale_edit(request, pk):
    """
    تعديل فاتورة مبيعات مع إعادة تسوية حركات المخزن والقيد المحاسبي بالحوكمة
    """
    sale = get_object_or_404(Sale, pk=pk)
    
    # التحقق من شروط المنع
    if sale.status == 'cancelled':
        messages.error(request, "لا يمكن تعديل فاتورة ملغية")
        return redirect("sale:sale_detail", pk=pk)

    if sale.is_fully_paid:
        messages.error(request, "لا يمكن تعديل فاتورة مدفوعة بالكامل")
        return redirect("sale:sale_detail", pk=pk)
        
    if sale.returns.filter(status='confirmed').exists():
        messages.error(request, "لا يمكن تعديل فاتورة تمت عليها عمليات مرتجع مؤكدة")
        return redirect("sale:sale_detail", pk=pk)

    import json
    from sale.forms import SaleForm
    from product.models import Product, Warehouse
    from client.models import Customer

    posted_items = []
    if request.method == "POST":
        posted_items = _extract_posted_items(request)
        form = SaleForm(request.POST, instance=sale)
        if form.is_valid():
            try:
                sale_data = {
                    'date': form.cleaned_data.get('date', sale.date),
                    'customer_id': form.cleaned_data['customer'].pk,
                    'warehouse_id': form.cleaned_data['warehouse'].pk,
                    'cost_center_id': form.cleaned_data.get('cost_center').id if form.cleaned_data.get('cost_center') else (request.POST.get('cost_center') or None),
                    'discount': form.cleaned_data.get('discount', 0) or Decimal('0'),
                    'discount_type': form.cleaned_data.get('discount_type', 'fixed'),
                    'adjustment_name': form.cleaned_data.get('adjustment_name'),
                    'adjustment_amount': form.cleaned_data.get('adjustment_amount', 0) or Decimal('0'),
                    'tax': form.cleaned_data.get('tax', 0) or Decimal('0'),
                    'notes': form.cleaned_data.get('notes', ''),
                    'items': [],
                }
                
                financial_category = form.cleaned_data.get('financial_category')
                if financial_category:
                    sale_data['financial_category_id'] = financial_category.pk

                product_ids = request.POST.getlist("product[]")
                quantities = request.POST.getlist("quantity[]")
                unit_prices = request.POST.getlist("unit_price[]")
                discounts = request.POST.getlist("discount[]")
                cost_centers = request.POST.getlist("item_cost_center[]")

                for i in range(len(product_ids)):
                    if product_ids[i]:
                        item_cc = int(cost_centers[i]) if (i < len(cost_centers) and cost_centers[i] and str(cost_centers[i]).isdigit()) else sale_data.get('cost_center_id')
                        sale_data['items'].append({
                            'product_id': int(product_ids[i]),
                            'quantity': Decimal(quantities[i]),
                            'unit_price': Decimal(unit_prices[i].replace(',', '')),
                            'discount': Decimal(discounts[i] if discounts[i] else '0'),
                            'cost_center_id': item_cc,
                        })

                updated_sale = SaleService.update_sale(sale=sale, data=sale_data, user=request.user)
                messages.success(request, f"تم تعديل فاتورة المبيعات رقم {updated_sale.number} بنجاح")
                return redirect("sale:sale_detail", pk=updated_sale.pk)
            except Exception as e:
                logger.error(f"❌ خطأ أثناء تعديل الفاتورة: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء تعديل الفاتورة: {str(e)}")
        else:
            messages.error(request, "يرجى تصحيح الأخطاء في النموذج")
    else:
        form = SaleForm(instance=sale)

    # تجهيز البنود الحالية كـ JSON للواجهة التفاعلية
    duplicate_items = []
    for item in sale.items.all():
        product_code = getattr(item.product, 'code', None) or getattr(item.product, 'sku', '')
        duplicate_items.append({
            "id": item.product.id,
            "product_id": item.product.id,
            "code": product_code,
            "name": item.product.name,
            "quantity": float(item.quantity),
            "price": float(item.unit_price),
            "unit_price": float(item.unit_price),
            "discount": float(item.discount or 0),
            "cost_center": item.cost_center_id or "",
            "is_service": item.product.is_service,
            "unit": item.product.unit.name if item.product.unit else "",
        })

    products = Product.objects.filter(is_active=True).select_related("unit")
    customers = Customer.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")

    from financial.models import Currency
    from product.models import Category
    from core.models import SystemSetting

    custom_fields_merged = SaleService.smart_merge_custom_fields('sale', getattr(sale, 'custom_fields', []))
    product_categories = Category.objects.filter(is_active=True).order_by("name")
    allowed_item_types = SystemSetting.get_setting('allowed_item_types', 'both')
    
    customer_prepaid_balance = Decimal('0.00')
    if sale.customer and hasattr(sale.customer, 'available_prepaid_balance'):
        try:
            customer_prepaid_balance = sale.customer.available_prepaid_balance
        except Exception:
            pass

    currencies_qs = Currency.objects.filter(is_active=True).order_by("code")

    context = {
        "sale": sale,
        "form": form,
        "is_edit": True,
        "products": products,
        "product_categories": product_categories,
        "allowed_item_types": allowed_item_types,
        "customers": customers,
        "warehouses": warehouses,
        "currencies": currencies_qs,
        "active_currencies": currencies_qs,
        "selected_customer": sale.customer,
        "customer_prepaid_balance": customer_prepaid_balance,
        "duplicate_items": json.dumps(duplicate_items),
        "posted_items_json": json.dumps(posted_items, cls=DjangoJSONEncoder) if posted_items else "null",
        "custom_fields_json": json.dumps(custom_fields_merged),
        "custom_fields_display_mode": SystemSetting.get_setting('custom_fields_display_mode', 'expanded'),
        "enable_custom_fields": SystemSetting.get_setting('enable_custom_fields', 'true'),
        "duplicate_invoice_type": getattr(sale, 'payment_method', 'credit'),
        "currency_symbol": "ج.م",
        "page_title": f"تعديل فاتورة مبيعات {sale.number}",
        "page_subtitle": f"العميل: {sale.customer.name}",
        "page_icon": "fas fa-edit",
        "header_buttons": [
            {
                "url": reverse("sale:sale_detail", kwargs={"pk": sale.pk}),
                "icon": "fa-arrow-right",
                "text": "العودة للتفاصيل",
                "class": "btn-secondary",
            }
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fa-home"},
            {"title": "المبيعات", "url": reverse("sale:sale_list"), "icon": "fa-shopping-cart"},
            {"title": f"فاتورة {sale.number}", "url": reverse("sale:sale_detail", kwargs={"pk": sale.pk})},
            {"title": "تعديل", "active": True},
        ],
    }
    return render(request, "sale/sale_form.html", context)


# Import necessary for sale_list
from django.db.models import Sum


# ==================== Payment Views ====================

@login_required
def redirect_to_unified_payments(request):
    """
    إعادة توجيه لصفحة المدفوعات الموحدة
    """
    messages.info(request, "يتم استخدام نظام المدفوعات الموحد")
    return redirect("financial:cash_accounts_list")


@login_required
def payment_detail(request, pk):
    """
    عرض تفاصيل دفعة
    """
    payment = get_object_or_404(SalePayment, pk=pk)
    
    from financial.services.payment_edit_service import PaymentEditService
    financial_info = PaymentEditService.get_edit_permissions(request.user, payment)
    
    context = {
        "payment": payment,
        "sale": payment.sale,
        "financial_info": financial_info,
        "active_menu": "sales",
        "title": f"تفاصيل الدفعة #{payment.id}",
    }
    
    return render(request, "sale/payment_detail.html", context)


@login_required
def post_payment(request, payment_id):
    """
    ترحيل دفعة
    """
    payment = get_object_or_404(SalePayment, pk=payment_id)
    
    if payment.is_posted:
        messages.warning(request, "هذه الدفعة مرحلة بالفعل")
    else:
        try:
            from sale.services.sale_service import SaleService
            journal_entry = SaleService._create_payment_journal_entry(payment, request.user)
            if journal_entry:
                payment.financial_transaction = journal_entry
            payment.status = "posted"
            payment.posted_at = timezone.now()
            payment.posted_by = request.user
            payment.save()
            
            if payment.sale:
                payment.sale.update_payment_status()

            messages.success(request, "تم ترحيل الدفعة بنجاح")
        except Exception as e:
            messages.error(request, f"خطأ في ترحيل الدفعة: {str(e)}")
    
    return redirect("sale:payment_detail", pk=payment_id)


@login_required
def unpost_payment(request, payment_id):
    """
    إلغاء ترحيل دفعة
    """
    payment = get_object_or_404(SalePayment, pk=payment_id)
    
    if not payment.is_posted:
        messages.warning(request, "هذه الدفعة غير مرحلة")
    else:
        try:
            result = payment.unpost(user=request.user)
            if result["success"]:
                messages.success(request, "تم إلغاء ترحيل الدفعة بنجاح")
            else:
                messages.error(request, result.get("message", "فشل إلغاء الترحيل"))
        except Exception as e:
            messages.error(request, f"خطأ في إلغاء ترحيل الدفعة: {str(e)}")
    
    return redirect("sale:payment_detail", pk=payment_id)


@login_required
def unpost_payment_only(request, payment_id):
    """
    إلغاء ترحيل دفعة فقط (بدون إعادة توجيه)
    """
    payment = get_object_or_404(SalePayment, pk=payment_id)
    
    if not payment.is_posted:
        messages.warning(request, "هذه الدفعة غير مرحلة")
    else:
        try:
            result = payment.unpost(user=request.user)
            if result["success"]:
                messages.success(request, "تم إلغاء ترحيل الدفعة")
            else:
                messages.error(request, result.get("message", "فشل إلغاء الترحيل"))
        except Exception as e:
            messages.error(request, f"خطأ: {str(e)}")
    
    return redirect("sale:sale_detail", pk=payment.sale.id)


@login_required
def delete_payment(request, payment_id):
    """
    حذف دفعة مبيعات - يُسمح بالحذف فقط للدفعات غير المرحلة (المسودة)
    """
    payment = get_object_or_404(SalePayment, pk=payment_id)
    sale = payment.sale
    
    if not payment.can_delete:
        messages.error(request, "لا يمكن حذف الدفعة المرحلة. يجب إلغاء الترحيل أولاً.")
        return redirect("sale:payment_detail", pk=payment.id)
    
    if request.method == "POST":
        try:
            if hasattr(payment, 'log_payment_action'):
                payment.log_payment_action(
                    action="delete",
                    user=request.user,
                    description=f"حذف دفعة مبيعات - المبلغ: {payment.amount} - التاريخ: {payment.payment_date}",
                    reason=request.POST.get("reason", "حذف الدفعة"),
                    old_values={
                        "amount": float(payment.amount),
                        "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
                        "payment_method": payment.payment_method,
                        "notes": payment.notes,
                        "status": payment.status,
                    }
                )
            
            from financial.services.payment_management_service import PaymentManagementService
            PaymentManagementService.delete_payment(payment, user=request.user)
            messages.success(request, "تم حذف الدفعة بنجاح")
            return redirect("sale:sale_detail", pk=sale.pk)
            
        except Exception as e:
            logger.error(f"خطأ في حذف الدفعة {payment_id}: {str(e)}")
            messages.error(request, f"حدث خطأ أثناء حذف الدفعة: {str(e)}")
            return redirect("sale:payment_detail", pk=payment.id)
            
    return redirect("sale:payment_detail", pk=payment.id)


@login_required
def edit_payment(request, payment_id):
    """
    تعديل دفعة
    """
    payment = get_object_or_404(SalePayment, pk=payment_id)
    
    if payment.is_posted:
        messages.error(request, "لا يمكن تعديل دفعة مرحلة. يجب إلغاء الترحيل أولاً")
        return redirect("sale:payment_detail", pk=payment_id)
    
    if request.method == "POST":
        form = SalePaymentForm(request.POST, instance=payment, sale=payment.sale)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل الدفعة بنجاح")
            return redirect("sale:payment_detail", pk=payment_id)
    else:
        form = SalePaymentForm(instance=payment, sale=payment.sale)
    
    context = {
        "form": form,
        "payment": payment,
        "active_menu": "sales",
        "title": "تعديل دفعة",
    }
    
    return render(request, "sale/payment_edit.html", context)


# ==================== Sale Return Views ====================

@login_required
def sale_return_list(request):
    """
    عرض وإدارة مرتجعات المبيعات وفق النظام الموحد ERP
    """
    queryset = SaleReturn.objects.select_related("sale", "sale__customer").order_by("-date", "-id")

    # الفلترة
    customer_id = request.GET.get("customer")
    status_filter = request.GET.get("status")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    if customer_id:
        queryset = queryset.filter(sale__customer_id=customer_id)
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
    total_returns_count = SaleReturn.objects.count()
    total_returns_amount = SaleReturn.objects.aggregate(total=Sum("total"))["total"] or 0
    confirmed_returns_count = SaleReturn.objects.filter(status="confirmed").count()
    draft_returns_count = SaleReturn.objects.filter(status="draft").count()

    # الترقيم الموحد SSR
    from core.utils import paginate_queryset
    pagination_context = paginate_queryset(queryset, request)
    page_obj = pagination_context["page_obj"]

    curr_sym = SystemSetting.get_currency_symbol()

    # تجهيز بيانات الجدول الموحد
    return_headers = [
        {"key": "id", "label": "#", "width": "5%", "class": "text-center"},
        {"key": "sale_number", "label": "الفاتورة الأصلية", "width": "15%", "format": "html"},
        {"key": "customer_name", "label": "العميل", "width": "25%"},
        {"key": "date", "label": "تاريخ المرتجع", "width": "15%", "class": "text-center"},
        {"key": "total_amount", "label": "إجمالي المرتجع", "width": "15%", "class": "text-end fw-bold"},
        {"key": "status", "label": "الحالة", "width": "10%", "class": "text-center", "format": "html"},
        {"key": "actions", "label": "الإجراءات", "width": "15%", "class": "text-center text-nowrap"}
    ]

    sale_returns_data = []
    for ret in page_obj:
        if ret.status == 'confirmed':
            status_badge = '<span class="badge bg-success">مؤكد</span>'
        elif ret.status == 'cancelled':
            status_badge = '<span class="badge bg-danger">ملغي</span>'
        else:
            status_badge = '<span class="badge bg-secondary">مسودة</span>'

        sale_num_html = f'<a href="/sales/{ret.sale.id}/" class="text-primary fw-bold">{ret.sale.number}</a>' if ret.sale else '-'
        actions_html = f'<a href="/sales/returns/{ret.id}/" class="btn btn-sm btn-outline-primary" title="عرض"><i class="fas fa-eye"></i></a>'

        sale_returns_data.append({
            'id': ret.id,
            'sale_number': sale_num_html,
            'customer_name': ret.sale.customer.name if (ret.sale and ret.sale.customer) else '-',
            'date': ret.date.strftime('%Y-%m-%d') if ret.date else '-',
            'total_amount': f'{ret.total:,.2f} {curr_sym}',
            'status': status_badge,
            'actions': actions_html,
        })

    customers = Customer.objects.filter(is_active=True).order_by("name")

    context = {
        "returns": page_obj,
        "page_obj": page_obj,
        **pagination_context,
        "sale_returns_data": sale_returns_data,
        "return_headers": return_headers,
        "total_returns_count": total_returns_count,
        "total_returns_amount": total_returns_amount,
        "confirmed_returns_count": confirmed_returns_count,
        "draft_returns_count": draft_returns_count,
        "customers": customers,
        "currency_symbol": curr_sym,
        "active_menu": "sales",
        "title": "مرتجعات المبيعات",
        "page_title": "مرتجعات المبيعات",
        "page_subtitle": "عرض وإدارة جميع مرتجعات المبيعات",
        "page_icon": "fas fa-undo-alt",
        "header_buttons": [
            {
                "url": reverse("sale:sale_list"),
                "icon": "fa-file-invoice",
                "text": "فواتير المبيعات",
                "class": "btn-outline-primary",
            }
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": "مرتجعات المبيعات", "active": True},
        ],
    }

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        from django.http import JsonResponse
        table_html = render_to_string('components/data_table.html', {
            'table_id': 'sale-returns-table',
            'headers': return_headers,
            'data': sale_returns_data,
            'empty_message': 'لا توجد مرتجعات مبيعات متاحة',
            'table_class': 'hover',
            'primary_key': 'id',
            'clickable_rows': True,
            'row_click_url': '/sales/returns/0/',
            'show_currency': True,
            'disable_pagination': True,
            'show_search': False,
            'show_length_menu': False,
            'sortable': False
        }, request=request)
        pagination_html = render_to_string('partials/pagination.html', context, request=request)
        return JsonResponse({
            'table_html': table_html,
            'pagination_html': pagination_html
        })

    return render(request, "sale/sale_return_list.html", context)


@login_required
def sale_return_detail(request, pk):
    """
    تفاصيل مرتجع مبيعات
    """
    sale_return = get_object_or_404(SaleReturn, pk=pk)
    items = sale_return.items.select_related("product").all()
    
    context = {
        "sale_return": sale_return,
        "items": items,
        "active_menu": "sales",
        "title": f"تفاصيل المرتجع #{sale_return.id}",
    }
    
    return render(request, "sale/sale_return_detail.html", context)


@login_required
def sale_return_confirm(request, pk):
    """
    تأكيد مرتجع مبيعات
    """
    sale_return = get_object_or_404(SaleReturn, pk=pk)
    
    if sale_return.status == "confirmed":
        messages.warning(request, "هذا المرتجع مؤكد بالفعل")
    else:
        try:
            # TODO: Implement confirmation logic with SaleService
            sale_return.status = "confirmed"
            sale_return.confirmed_at = timezone.now()
            sale_return.confirmed_by = request.user
            sale_return.save()
            messages.success(request, "تم تأكيد المرتجع بنجاح")
        except Exception as e:
            messages.error(request, f"خطأ في تأكيد المرتجع: {str(e)}")
    
    return redirect("sale:sale_return_detail", pk=pk)


@login_required
def sale_return_cancel(request, pk):
    """
    إلغاء مرتجع مبيعات
    """
    sale_return = get_object_or_404(SaleReturn, pk=pk)
    
    if sale_return.status == "cancelled":
        messages.warning(request, "هذا المرتجع ملغي بالفعل")
    elif sale_return.status == "confirmed":
        messages.error(request, "لا يمكن إلغاء مرتجع مؤكد")
    else:
        try:
            sale_return.status = "cancelled"
            sale_return.save()
            messages.success(request, "تم إلغاء المرتجع بنجاح")
        except Exception as e:
            messages.error(request, f"خطأ في إلغاء المرتجع: {str(e)}")
    
    return redirect("sale:sale_return_detail", pk=pk)


@login_required
def sale_duplicate(request, pk):
    """
    نسخ فاتورة مبيعات - فتح صفحة الإنشاء مع تحميل بيانات الفاتورة الأصلية
    المستخدم يراجع ويعدّل ثم يحفظ
    """
    import json
    original = get_object_or_404(Sale, pk=pk)

    # جلب نوع البنود المسموح بها من الإعدادات
    allowed_item_types = SystemSetting.get_setting('sale_invoice_item_types', 'both')

    # جلب المنتجات المسجلة في الفاتورة الأصلية مضافاً إليها المنتجات ذات المخزون المتاح
    from django.db import models
    original_item_product_ids = list(original.items.values_list("product_id", flat=True))

    products_filter = models.Q(is_active=True, is_bundle=False)
    if allowed_item_types == 'products':
        products_filter &= models.Q(is_service=False)
    elif allowed_item_types == 'services':
        products_filter &= models.Q(is_service=True)

    from product.models import Stock as StockModel
    products_with_stock = StockModel.objects.filter(
        warehouse=original.warehouse, quantity__gt=0
    ).values_list("product_id", flat=True)
    
    if allowed_item_types == 'both':
        products = Product.objects.filter(
            products_filter & (models.Q(is_service=True) | models.Q(id__in=products_with_stock) | models.Q(id__in=original_item_product_ids))
        ).order_by("name")
    elif allowed_item_types == 'products':
        products = Product.objects.filter(
            products_filter & (models.Q(id__in=products_with_stock) | models.Q(id__in=original_item_product_ids))
        ).order_by("name")
    else:  # services
        products = Product.objects.filter(products_filter).order_by("name")
        
    customers = Customer.objects.filter(is_active=True).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name")

    # جلب التصنيفات
    from product.models import Category
    category_filter = models.Q(is_active=True, products__is_active=True, products__is_bundle=False)
    if allowed_item_types == 'products':
        category_filter &= models.Q(products__is_service=False)
    elif allowed_item_types == 'services':
        category_filter &= models.Q(products__is_service=True)
        
    product_categories = Category.objects.filter(category_filter).distinct().order_by("name")

    # رقم الفاتورة الجديد (معاينة بدون حجز)
    next_sale_number = None
    try:
        from core.services.sequence_service import SequenceService
        from core.enums.document_types import DocumentType
        next_sale_number = SequenceService.peek_next_number(DocumentType.SALES_INVOICE)
    except Exception as e:
        logger.error(f"خطأ في الحصول على الرقم التالي: {str(e)}")

    # تحديد نوع الفاتورة وحساب الدفع والدفعة المقدمة
    first_payment = original.payments.order_by("id").first()
    payment_account_code = ""
    if first_payment:
        payment_account_code = first_payment.payment_method or (
            first_payment.financial_account.code if first_payment.financial_account else ""
        )

    down_payment_amount = 0

    if original.payment_method == "credit":
        invoice_type = "credit"
    elif original.payment_method == "credit_with_downpayment":
        invoice_type = "credit"
        if first_payment:
            down_payment_amount = float(first_payment.amount)
    elif original.payment_status == "paid" or original.payment_method in ["cash", "bank_transfer", "check"] or payment_account_code:
        invoice_type = "cash"
        if not payment_account_code and original.payment_method not in ["cash", "bank_transfer", "check"]:
            payment_account_code = original.payment_method
    else:
        invoice_type = "credit"

    # التصنيف المالي بصيغة cat_X
    financial_category_id = f"cat_{original.financial_category.id}" if original.financial_category else None

    # بيانات الخصم والتسوية
    discount_val = float(original.discount) if original.discount else 0
    discount_type = original.discount_type or "fixed"

    adj_name = original.adjustment_name or ""
    adj_amount = float(original.adjustment_amount) if original.adjustment_amount else 0
    adj_type = "subtract" if adj_amount < 0 else "add"
    abs_adj_amount = abs(adj_amount)

    # بيانات البنود الكاملة (متضمنة الاسم والكود لضمان ظهورها فوراً)
    duplicate_items = json.dumps([
        {
            "product_id": item.product.id,
            "id": item.product.id,
            "code": getattr(item.product, 'code', None) or getattr(item.product, 'sku', '') or getattr(item.product, 'barcode', '') or "",
            "name": item.product.name,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "price": float(item.unit_price),
            "discount": float(item.discount),
            "total": float(item.total),
            "cost_center": item.cost_center_id or "",
            "is_service": item.product.is_service,
        }
        for item in original.items.all()
    ])

    form = SaleForm(initial={
        "date": timezone.now().date(),
        "customer": original.customer,
        "warehouse": original.warehouse,
        "cost_center": original.cost_center_id,
        "discount": discount_val,
        "discount_type": discount_type,
        "adjustment_name": adj_name,
        "adjustment_type": adj_type,
        "adjustment_amount": abs_adj_amount,
        "notes": original.notes,
        "payment_method": payment_account_code,
        "invoice_type": invoice_type,
        "down_payment_amount": down_payment_amount,
        "financial_category": financial_category_id,
    })

    context = {
        "form": form,
        "products": products,
        "product_categories": product_categories,
        "allowed_item_types": allowed_item_types,
        "customers": customers,
        "warehouses": warehouses,
        "next_sale_number": next_sale_number,
        "selected_customer": original.customer,
        "default_warehouse": original.warehouse or (warehouses.first() if warehouses.exists() else None),
        # بيانات النسخ
        "is_duplicate": True,
        "duplicate_from": original.number,
        "duplicate_items": duplicate_items,
        "duplicate_custom_fields_json": json.dumps(SaleService.smart_merge_custom_fields('sale', original.custom_fields)),
        "custom_fields_json": json.dumps(SaleService.smart_merge_custom_fields('sale', original.custom_fields)),
        "custom_fields_display_mode": SystemSetting.get_setting('custom_fields_display_mode', 'expanded'),
        "enable_custom_fields": SystemSetting.get_setting('enable_custom_fields', 'true'),
        "duplicate_invoice_type": invoice_type,
        "duplicate_payment_method": payment_account_code,
        "duplicate_down_payment_amount": down_payment_amount,
        "duplicate_financial_category_id": financial_category_id,
        "duplicate_discount": discount_val,
        "duplicate_discount_type": discount_type,
        "duplicate_adjustment_name": adj_name,
        "duplicate_adjustment_type": adj_type,
        "duplicate_adjustment_amount": abs_adj_amount,
        "page_title": f"نسخ فاتورة - {original.number}",
        "page_subtitle": f"نسخة من فاتورة {original.number} | {original.customer.name}",
        "page_icon": "fas fa-copy",
        "header_buttons": [
            {
                "url": reverse("sale:sale_detail", kwargs={"pk": original.pk}),
                "icon": "fa-arrow-right",
                "text": "العودة للفاتورة الأصلية",
                "class": "btn-secondary",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": original.number, "url": reverse("sale:sale_detail", kwargs={"pk": original.pk}), "icon": "fas fa-file-invoice"},
            {"title": "نسخ الفاتورة", "active": True},
        ],
    }

    return render(request, "sale/sale_form.html", context)


# استيراد واجهات عروض الأسعار لتسهيل الوصول إليها
from .quotation_views import (
    quotation_list,
    quotation_create,
    quotation_edit,
    quotation_detail,
    quotation_delete,
    quotation_print,
    quotation_convert_to_sale,
    check_product_stock
)


# ==================== إدارة تعاريف الحقول الإضافية ====================

@login_required
def custom_field_list(request):
    """
    قائمة تعاريف الحقول الإضافية المخصصة
    """
    if not request.user.is_superuser and not request.user.is_admin and not request.user.has_perm('sale.manage_custom_fields'):
        messages.error(request, _("ليس لديك صلاحية لإدارة الحقول الإضافية"))
        return redirect("sale:sale_list")

    from sale.models import CustomFieldDefinition
    from sale.forms import CustomFieldDefinitionForm
    from core.utils import paginate_queryset
    
    fields_list = CustomFieldDefinition.objects.all().order_by("sort_order", "id")
    pagination_context = paginate_queryset(fields_list, request, default_per_page=25)
    page_obj = pagination_context["page_obj"]
    form = CustomFieldDefinitionForm()

    context = {
        "fields_list": page_obj,
        "page_obj": page_obj,
        **pagination_context,
        "form": form,
        "page_title": _("إدارة الحقول الإضافية المخصصة"),
        "page_subtitle": _("تخصيص الحقول الاختيارية لعروض الأسعار وفواتير البيع"),
        "page_icon": "fas fa-sliders-h",
        "breadcrumb_items": [
            {"title": _("الرئيسية"), "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": _("المبيعات"), "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": _("إدارة الحقول الإضافية"), "active": True},
        ],
    }
    return render(request, "sale/custom_fields/custom_field_list.html", context)


@login_required
def custom_field_create(request):
    """
    إنشاء تعريف حقل إضافي جديد
    """
    if not request.user.is_superuser and not request.user.is_admin and not request.user.has_perm('sale.manage_custom_fields'):
        messages.error(request, _("ليس لديك صلاحية لإدارة الحقول الإضافية"))
        return redirect("sale:sale_list")

    from sale.forms import CustomFieldDefinitionForm
    if request.method == "POST":
        form = CustomFieldDefinitionForm(request.POST)
        if form.is_valid():
            custom_field = form.save()
            messages.success(request, _("تم إضافة الحقل الإضافي '{}' بنجاح").format(custom_field.name))
        else:
            messages.error(request, _("حدث خطأ أثناء إضافة الحقل: {}").format(form.errors))
    
    return redirect("sale:custom_field_list")


@login_required
def custom_field_edit(request, pk):
    """
    تعديل تعريف حقل إضافي
    """
    if not request.user.is_superuser and not request.user.is_admin and not request.user.has_perm('sale.manage_custom_fields'):
        messages.error(request, _("ليس لديك صلاحية لإدارة الحقول الإضافية"))
        return redirect("sale:sale_list")

    from sale.models import CustomFieldDefinition
    from sale.forms import CustomFieldDefinitionForm
    
    custom_field = get_object_or_404(CustomFieldDefinition, pk=pk)
    if request.method == "POST":
        form = CustomFieldDefinitionForm(request.POST, instance=custom_field)
        if form.is_valid():
            form.save()
            messages.success(request, _("تم تحديث الحقل الإضافي بنجاح"))
        else:
            messages.error(request, _("حدث خطأ أثناء تعديل الحقل"))
    
    return redirect("sale:custom_field_list")


@login_required
def custom_field_toggle(request, pk):
    """
    تفعيل أو تعطيل حقل إضافي
    """
    if not request.user.is_superuser and not request.user.is_admin and not request.user.has_perm('sale.manage_custom_fields'):
        messages.error(request, _("غير مصرح"))
        return redirect("sale:sale_list")

    from sale.models import CustomFieldDefinition
    custom_field = get_object_or_404(CustomFieldDefinition, pk=pk)
    custom_field.is_active = not custom_field.is_active
    custom_field.save()
    
    status_str = _("تفعيل") if custom_field.is_active else _("تعطيل")
    messages.success(request, _("تم {} الحقل '{}' بنجاح").format(status_str, custom_field.name))
    return redirect("sale:custom_field_list")


@login_required
def custom_field_delete(request, pk):
    """
    حذف تعريف حقل إضافي
    """
    if not request.user.is_superuser and not request.user.is_admin and not request.user.has_perm('sale.manage_custom_fields'):
        messages.error(request, _("غير مصرح"))
        return redirect("sale:sale_list")

    from sale.models import CustomFieldDefinition
    custom_field = get_object_or_404(CustomFieldDefinition, pk=pk)
    name = custom_field.name
    custom_field.delete()
    messages.success(request, _("تم حذف الحقل '{}' بنجاح").format(name))
    return redirect("sale:custom_field_list")


@login_required
def api_create_custom_field(request):
    """
    API إنشاء حقل إضافي جديد عبر AJAX Modal من داخل نموذج الفاتورة
    """
    from django.http import JsonResponse
    if not request.user.is_superuser and not request.user.is_admin and not request.user.has_perm('sale.manage_custom_fields'):
        return JsonResponse({"success": False, "message": _("غير مصرح لك بإضافة حقول إضافية")}, status=403)

    if request.method == "POST":
        from sale.forms import CustomFieldDefinitionForm
        form = CustomFieldDefinitionForm(request.POST)
        if form.is_valid():
            custom_field = form.save()
            return JsonResponse({
                "success": True,
                "field": {
                    "key": custom_field.key,
                    "name": custom_field.name,
                    "field_type": custom_field.field_type,
                    "select_options": custom_field.get_options_list(),
                    "is_required": custom_field.is_required,
                    "show_on_print": custom_field.show_on_print,
                    "show_on_thermal": custom_field.show_on_thermal,
                }
            })
        else:
            return JsonResponse({"success": False, "errors": form.errors}, status=400)
            
    return JsonResponse({"success": False, "message": _("طريقة الطلب غير صحيحة")}, status=405)


from .quotation_views import (
    quotation_list,
    quotation_create,
    quotation_detail,
    quotation_edit,
    quotation_delete,
    quotation_print,
    quotation_pdf_download,
    quotation_email_pdf,
    quotation_convert_to_sale,
    check_product_stock,
)

from .credit_note_views import (
    credit_note_list,
    credit_note_create,
    credit_note_detail,
    credit_note_post,
    credit_note_reverse,
)


@login_required
@require_POST
def allocate_prepaid_balance(request, pk):
    """
    تخصيص وتسوية مبلغ من الرصيد المسبق للعميل على الفاتورة بنسبة 1:1 للعملات المتطابقة
    """
    sale = get_object_or_404(Sale, pk=pk)
    if not sale.customer:
        messages.error(request, _("لا يوجد عميل مرتبط بهذه الفاتورة."))
        return redirect("sale:sale_detail", pk=sale.pk)

    try:
        from financial.services.partner_advance_service import PartnerAdvanceService
        target_currency = sale.currency
        if not target_currency:
            from financial.services.exchange_rate_service import ExchangeRateService
            target_currency = ExchangeRateService.get_functional_currency()

        payment = sale.customer.payments.filter(currency=target_currency, status="posted").order_by("payment_date").first()
        if not payment:
            payment = sale.customer.payments.filter(status="posted").order_by("payment_date").first()

        if not payment:
            messages.error(request, _("لا تتوفر أي دفعات مقدمة مسجلة ومتاحة للعميل."))
            return redirect("sale:sale_detail", pk=sale.pk)

        requested_amount_str = request.POST.get("amount")
        if requested_amount_str:
            amount = Decimal(requested_amount_str)
        else:
            avail = PartnerAdvanceService.get_available_balance(sale.customer, currency=target_currency)
            amount = min(avail, sale.amount_due)

        if amount <= Decimal("0.00"):
            messages.warning(request, _("لا يوجد مبلغ قابل للتخصيص."))
            return redirect("sale:sale_detail", pk=sale.pk)

        settlement = PartnerAdvanceService.allocate(
            partner=sale.customer,
            payment=payment,
            invoice=sale,
            amount=amount,
            user=request.user
        )
        messages.success(request, f"تم تخصيص تسوية رصيد مسبق بمبلغ {amount} بنجاح.")
    except Exception as e:
        logger.error(f"❌ خطأ أثناء تخصيص الرصيد المسبق: {str(e)}")
        messages.error(request, f"خطأ أثناء التخصيص: {str(e)}")

    return redirect("sale:sale_detail", pk=sale.pk)


# ==================== أوامر البيع وإذون التسليم ====================
from .sales_order_views import (
    sales_order_list,
    sales_order_create,
    sales_order_detail,
    sales_order_confirm,
    sales_order_cancel,
    sales_order_convert_to_sale,
)

from .delivery_note_views import (
    delivery_note_list,
    delivery_note_create,
    delivery_note_detail,
    delivery_note_convert_to_sale,
)

from .pricing_policy_views import (
    price_list_list,
    price_list_detail,
    price_list_create,
    price_list_edit,
    discount_rule_list,
    discount_rule_create,
)

from .quotation_views import (
    quotation_list,
    quotation_create,
    quotation_detail,
    quotation_edit,
    quotation_delete,
    quotation_print,
    quotation_pdf_download,
    quotation_email_pdf,
    quotation_convert_to_sale,
    check_product_stock,
)



