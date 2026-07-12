"""
Sale Views - Updated with SaleService
محدث: يستخدم SaleService مع AccountingGateway و MovementService
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext as _
from django.urls import reverse
from django.core.paginator import Paginator
from decimal import Decimal
import logging

from sale.models import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem
from sale.forms import SaleForm, SalePaymentForm, SaleReturnForm
from sale.services import SaleService
from product.models import Product, Warehouse, SerialNumber
from client.models import Customer

logger = logging.getLogger(__name__)


@login_required
def sale_create(request, customer_id=None):
    """
    إنشاء فاتورة مبيعات جديدة
    ✅ محدث: يستخدم SaleService مع الحوكمة الكاملة
    """
    # جلب نوع البنود المسموح بها من الإعدادات
    from core.models import SystemSetting
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

    if request.method == "POST":
        form = SaleForm(request.POST)

        if form.is_valid():
            try:
                # تجهيز بيانات الفاتورة
                sale_data = {
                    'date': form.cleaned_data['date'],
                    'customer_id': form.cleaned_data['customer'].id,
                    'warehouse_id': form.cleaned_data['warehouse'].id,
                    'discount': Decimal(request.POST.get("discount", "0")),
                    'tax': Decimal(request.POST.get("tax", "0")),
                    'notes': form.cleaned_data.get('notes', ''),
                    'work_order_id': form.cleaned_data['work_order'].id if form.cleaned_data.get('work_order') else None,
                    'items': []
                }
                
                # معالجة نوع الفاتورة
                invoice_type = form.cleaned_data.get("invoice_type", "credit")
                payment_method = form.cleaned_data.get("payment_method", "")
                down_payment_amount = form.cleaned_data.get("down_payment_amount") or Decimal('0')

                if invoice_type == "credit":
                    sale_data['payment_method'] = "credit"
                elif invoice_type == "cash":
                    sale_data['payment_method'] = payment_method if payment_method else "cash"
                elif invoice_type == "credit_with_downpayment":
                    sale_data['payment_method'] = "credit_with_downpayment"
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
                        sale_data['items'].append({
                            'product_id': int(product_ids[i]),
                            'quantity': Decimal(quantities[i]),
                            'unit_price': Decimal(unit_prices[i].replace(',', '')),
                            'discount': Decimal(discounts[i] if discounts[i] else '0'),
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
                            
                    elif invoice_type == "credit_with_downpayment" and down_payment_amount > 0:
                        # التحقق من أن مبلغ الدفعة أقل من إجمالي الفاتورة
                        if down_payment_amount >= sale.total:
                            raise ValueError(f"مبلغ الدفعة المقدمة ({down_payment_amount} ج.م) يجب أن يكون أقل من إجمالي الفاتورة ({sale.total} ج.م)")
                            
                        payment_data = {
                            'amount': down_payment_amount,
                            'payment_method': payment_method,
                            'payment_date': sale.date,
                            'notes': f'دفعة مقدمة تلقائية مع الفاتورة - المتبقي: {sale.total - down_payment_amount} ج.م'
                        }
                        SaleService.process_payment(sale, payment_data, request.user)
                        logger.info(f"✅ تم إنشاء دفعة مقدمة للفاتورة: {sale.number}")
                
                messages.success(request, "تم إنشاء فاتورة المبيعات بنجاح")
                return redirect("sale:sale_detail", pk=sale.pk)

            except Exception as e:
                logger.error(f"❌ خطأ في إنشاء الفاتورة: {str(e)}")
                messages.error(request, f"حدث خطأ أثناء إنشاء الفاتورة: {str(e)}")
    else:
        # تهيئة بيانات افتراضية
        initial_data = {
            "date": timezone.now().date(),
        }
        if selected_customer:
            initial_data["customer"] = selected_customer
        if selected_work_order:
            initial_data["work_order"] = selected_work_order
        
        warehouses = Warehouse.objects.filter(is_active=True).order_by("name")
        if warehouses.exists():
            initial_data["warehouse"] = warehouses.first()
            
        form = SaleForm(initial=initial_data)

    # الحصول على الرقم التسلسلي التالي
    next_sale_number = None
    try:
        serial, created = SerialNumber.objects.get_or_create(
            document_type="sale",
            year=timezone.now().year,
            defaults={"prefix": "SALE", "last_number": 0},
        )
        last_sale = Sale.objects.order_by("-id").first()
        last_number = 0
        if last_sale and last_sale.number:
            try:
                last_number = int(last_sale.number.replace("SALE", ""))
            except (ValueError, AttributeError):
                pass
        next_number = max(serial.last_number, last_number) + 1
        next_sale_number = f"{serial.prefix}{next_number:04d}"
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

    context = {
        "products": products,
        "product_categories": product_categories,
        "allowed_item_types": allowed_item_types,
        "form": form,
        "next_sale_number": next_sale_number,
        "customers": customers,
        "warehouses": warehouses,
        "selected_customer": selected_customer,
        "default_warehouse": warehouses.first() if warehouses.exists() else None,
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
    sale = get_object_or_404(Sale, pk=pk)

    if request.method == "POST":
        form = SalePaymentForm(request.POST)
        if form.is_valid():
            try:
                # تجهيز بيانات الدفعة
                payment_data = {
                    'amount': form.cleaned_data['amount'],
                    'payment_method': request.POST.get('payment_method'),  # من payment_account_select
                    'payment_date': form.cleaned_data.get('payment_date', timezone.now().date()),
                    'notes': form.cleaned_data.get('notes', ''),
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
        form = SalePaymentForm(initial=initial_data)

    context = {
        "invoice": sale,  # الـ template بيستخدم invoice مش sale
        "sale": sale,  # للتوافق
        "form": form,
        "is_purchase": False,  # للتمييز بين المبيعات والمشتريات
        "title": f"إضافة دفعة - فاتورة {sale.number}",
        "page_title": f"إضافة دفعة - فاتورة {sale.number}",
        "page_subtitle": f"المبلغ المتبقي: {sale.amount_due} ج.م",
        "page_icon": "fas fa-money-bill-wave",
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": f"فاتورة {sale.number}", "url": reverse("sale:sale_detail", kwargs={"pk": sale.pk}), "icon": "fas fa-file-invoice"},
            {"title": "إضافة دفعة", "active": True},
        ],
        "header_buttons": [],
    }
    return render(request, "sale/sale_payment_form.html", context)


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
    ✅ محدث: يستخدم SaleService للإحصائيات
    """
    sale = get_object_or_404(Sale, pk=pk)
    
    # الحصول على الإحصائيات من SaleService
    statistics = SaleService.get_sale_statistics(sale)
    
    # الحصول على البنود والدفعات والمرتجعات
    items = sale.items.all()
    payments = sale.payments.all().order_by('-payment_date')
    returns = sale.returns.filter(status='confirmed').order_by('-date')
    is_service_invoice = all(item.product.is_service for item in items)

    context = {
        "sale": sale,
        "items": items,
        "payments": payments,
        "returns": returns,
        "is_service_invoice": is_service_invoice,
        "statistics": statistics,
        "title": f"تفاصيل فاتورة مبيعات - {sale.number}",
        "page_title": f"فاتورة مبيعات {sale.number}",
        "page_subtitle": f"العميل: {sale.customer.name} - التاريخ: {sale.date}",
        "page_icon": "fas fa-file-invoice-dollar",
        "header_buttons": [
            *([{
                "url": reverse("sale:sale_add_payment", kwargs={"pk": sale.pk}),
                "icon": "fa-money-bill-wave",
                "text": "إضافة دفعة",
                "class": "btn-success",
            }] if sale.payment_status != 'paid' else []),
            *([{
                "url": reverse("sale:sale_return", kwargs={"pk": sale.pk}),
                "icon": "fa-undo",
                "text": "إنشاء مرتجع",
                "class": "btn-warning",
            }] if sale.status != 'cancelled' else []),
            {
                "url": reverse("sale:sale_duplicate", kwargs={"pk": sale.pk}),
                "icon": "fa-copy",
                "text": "نسخ",
                "class": "btn-outline-primary",
            },
            {
                "url": reverse("sale:sale_print", kwargs={"pk": sale.pk}),
                "icon": "fa-print",
                "text": "طباعة (A4)",
                "class": "btn-info",
            },
            {
                "url": reverse("sale:sale_print_thermal", kwargs={"pk": sale.pk}),
                "icon": "fa-receipt",
                "text": "طباعة حرارية",
                "class": "btn-outline-info",
            },
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "url": reverse("sale:sale_list"), "icon": "fas fa-shopping-cart"},
            {"title": f"فاتورة {sale.number}", "active": True},
        ],
    }
    return render(request, "sale/sale_detail.html", context)



@login_required
def sale_list(request):
    """
    عرض قائمة فواتير المبيعات
    """
    sales_query = Sale.objects.all().order_by("-date", "-id")

    # تصفية حسب العميل
    customer = request.GET.get("customer")
    if customer:
        sales_query = sales_query.filter(customer_id=customer)

    # تصفية حسب المخزن
    warehouse = request.GET.get("warehouse")
    if warehouse:
        sales_query = sales_query.filter(warehouse_id=warehouse)

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

    # الترقيم
    from django.core.paginator import Paginator
    paginator = Paginator(sales_query, 25)
    page_number = request.GET.get("page", 1)
    sales_page = paginator.get_page(page_number)
    
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

        # زر إضافة دفعة (إذا لم تكن مدفوعة بالكامل)
        if sale.payment_status != 'paid':
            actions.append({
                'url': reverse('sale:sale_add_payment', args=[sale.pk]),
                'icon': 'fas fa-money-bill',
                'label': 'دفعة',
                'class': 'btn-outline-success btn-sm',
            })

        # زر الطباعة (للفواتير المدفوعة فقط)
        if sale.payment_status == 'paid':
            actions.append({
                'url': reverse('sale:sale_print', args=[sale.pk]),
                'icon': 'fas fa-print',
                'label': 'طباعة',
                'class': 'btn-outline-secondary btn-sm',
                'target': '_blank',
            })

        # زر نسخ الفاتورة
        actions.append({
            'url': reverse('sale:sale_duplicate', args=[sale.pk]),
            'icon': 'fas fa-copy',
            'label': 'نسخ',
            'class': 'btn-outline-primary btn-sm',
        })

        
        sales_data.append({
            'id': sale.id,
            'number': sale.number,
            'created_at': sale.created_at,
            'customer': sale.customer.name,
            'warehouse': sale.warehouse.name,
            'total': sale.total,
            'amount_paid': sale.amount_paid,
            'amount_due': sale.amount_due,
            'payment_status': payment_status_html,
            'actions': actions
        })

    # إحصائيات
    paid_sales_count = Sale.objects.filter(payment_status="paid").count()
    partially_paid_sales_count = Sale.objects.filter(payment_status="partially_paid").count()
    unpaid_sales_count = Sale.objects.filter(payment_status="unpaid").count()
    returned_sales_count = Sale.objects.filter(returns__status="confirmed").distinct().count()
    total_amount = Sale.objects.aggregate(Sum("total"))["total__sum"] or 0

    from core.models import SystemSetting
    allowed_types = SystemSetting.get_setting('sale_invoice_item_types', 'both')

    customers = Customer.objects.filter(id__in=Sale.objects.values('customer_id')).order_by("name")
    warehouses = Warehouse.objects.filter(is_active=True).order_by("name") if allowed_types != 'services' else Warehouse.objects.none()

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
            'label': 'التاريخ والوقت',
            'sortable': True,
            'class': 'text-center',
            'format': 'datetime_12h',
        },
        {'key': 'customer', 'label': 'العميل', 'sortable': True, 'width': '20%', 'class': 'fw-bold'},
    ]
    if allowed_types != 'services':
        sale_headers.append({'key': 'warehouse', 'label': 'المخزن', 'sortable': True, 'width': '12%'})
        
    sale_headers.extend([
        {'key': 'total', 'label': 'الإجمالي', 'sortable': True, 'class': 'text-center', 'format': 'currency'},
        {'key': 'amount_due', 'label': 'المتبقي', 'sortable': True, 'class': 'text-center', 'format': 'currency', 'variant': 'text-danger'},
        {'key': 'payment_status', 'label': 'حالة الدفع', 'sortable': True, 'class': 'text-center', 'format': 'html'},
        {'key': 'actions', 'label': 'الإجراءات', 'width': '1%', 'class': 'text-center text-nowrap'}
    ])

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        from django.http import JsonResponse
        ctx = {
            'table_id': 'sales-table',
            'headers': sale_headers,
            'data': sales_data,
            'empty_message': 'لا توجد فواتير مبيعات متاحة',
            'table_class': 'hover',
            'primary_key': 'id',
            'clickable_rows': True,
            'row_click_url': '/sales/0/',
            'show_currency': True,
            'currency_symbol': getattr(request, 'currency_symbol', 'ج.م'),
            'disable_pagination': True,
            'show_search': False,
            'show_length_menu': False,
            'sortable': False,
        }
        table_html = render_to_string('components/data_table.html', ctx, request=request)
        pagination_html = ''
        if paginator.num_pages > 1:
            pagination_html = render_to_string('partials/pagination.html', {
                'page_obj': sales_page,
                'align': 'center',
            }, request=request)
            
        return JsonResponse({
            'table_html': table_html,
            'pagination_html': pagination_html,
            'count': paginator.count,
        })

    context = {
        "sales": sales_data,
        "sale_headers": sale_headers,
        "page_obj": sales_page,  # للـ pagination
        "paginator": paginator,
        "paid_sales_count": paid_sales_count,
        "partially_paid_sales_count": partially_paid_sales_count,
        "unpaid_sales_count": unpaid_sales_count,
        "returned_sales_count": returned_sales_count,
        "total_amount": total_amount,
        "customers": customers,
        "warehouses": warehouses,
        "allowed_item_types": allowed_types,
        "page_title": "فواتير المبيعات",
        "page_subtitle": "قائمة بجميع فواتير المبيعات في النظام",
        "page_icon": "fas fa-shopping-cart",
        "header_buttons": [
            {
                "url": reverse("sale:sale_create"),
                "icon": "fa-plus",
                "text": "إضافة فاتورة",
                "class": "btn-primary",
            }
        ],
        "breadcrumb_items": [
            {"title": "الرئيسية", "url": reverse("core:dashboard"), "icon": "fas fa-home"},
            {"title": "المبيعات", "url": "#", "icon": "fas fa-truck"},
            {"title": "فواتير المبيعات", "active": True},
        ],
    }

    return render(request, "sale/sale_list.html", context)


@login_required
def sale_print(request, pk):
    """
    طباعة فاتورة مبيعات
    """
    sale = get_object_or_404(Sale, pk=pk)
    items = sale.items.all()
    from core.models import SystemSetting
    
    # جلب الإعدادات المحددة للشركة
    company_name = SystemSetting.objects.filter(key="company_name").values_list("value", flat=True).first() or "مؤسسة موهبة"
    company_address = SystemSetting.objects.filter(key="company_address").values_list("value", flat=True).first() or ""
    company_phone = SystemSetting.objects.filter(key="company_phone").values_list("value", flat=True).first() or ""
    company_tax_number = SystemSetting.objects.filter(key="company_tax_number").values_list("value", flat=True).first() or ""
    company_logo = SystemSetting.objects.filter(key="company_logo").values_list("value", flat=True).first() or ""
    company_email = SystemSetting.objects.filter(key="company_email").values_list("value", flat=True).first() or ""
    company_website = SystemSetting.objects.filter(key="company_website").values_list("value", flat=True).first() or ""
    
    is_service_invoice = all(item.product.is_service for item in items)
    context = {
        "sale": sale,
        "items": items,
        "company_name": company_name,
        "company_address": company_address,
        "company_phone": company_phone,
        "company_tax_number": company_tax_number,
        "company_logo": company_logo,
        "company_email": company_email,
        "company_website": company_website,
        "title": f"فاتورة مبيعات - {sale.number}",
        "is_service_invoice": is_service_invoice,
    }
    
    return render(request, "sale/sale_print.html", context)


@login_required
def sale_print_thermal(request, pk):
    """
    طباعة فاتورة حرارية لمبيعات
    """
    import qrcode
    import io
    import base64
    from core.models import SystemSetting
    
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
    تعديل فاتورة مبيعات
    ملاحظة: التعديل محدود - لا يمكن تعديل فاتورة مدفوعة بالكامل
    """
    sale = get_object_or_404(Sale, pk=pk)
    
    # التحقق من إمكانية التعديل
    if sale.is_fully_paid:
        messages.error(request, "لا يمكن تعديل فاتورة مدفوعة بالكامل")
        return redirect("sale:sale_detail", pk=pk)
    
    if sale.has_posted_payments:
        messages.warning(request, "تحذير: هذه الفاتورة تحتوي على دفعات مرحلة. التعديل محدود.")
    
    messages.info(request, "تعديل الفواتير محدود حالياً. يُنصح بإنشاء فاتورة جديدة.")
    return redirect("sale:sale_detail", pk=pk)


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
    
    context = {
        "payment": payment,
        "sale": payment.sale,
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
            # TODO: Implement posting logic with SaleService
            payment.is_posted = True
            payment.posted_at = timezone.now()
            payment.posted_by = request.user
            payment.save()
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
def edit_payment(request, payment_id):
    """
    تعديل دفعة
    """
    payment = get_object_or_404(SalePayment, pk=payment_id)
    
    if payment.is_posted:
        messages.error(request, "لا يمكن تعديل دفعة مرحلة. يجب إلغاء الترحيل أولاً")
        return redirect("sale:payment_detail", pk=payment_id)
    
    if request.method == "POST":
        form = SalePaymentForm(request.POST, instance=payment)
        if form.is_valid():
            form.save()
            messages.success(request, "تم تعديل الدفعة بنجاح")
            return redirect("sale:payment_detail", pk=payment_id)
    else:
        form = SalePaymentForm(instance=payment)
    
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
    قائمة مرتجعات المبيعات
    """
    returns = SaleReturn.objects.select_related("sale", "sale__customer").order_by("-date")
    
    # Pagination
    paginator = Paginator(returns, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    context = {
        "returns": page_obj,
        "active_menu": "sales",
        "title": "مرتجعات المبيعات",
    }
    
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
    from core.models import SystemSetting
    allowed_item_types = SystemSetting.get_setting('sale_invoice_item_types', 'both')

    # جلب المنتجات اللي ليها stock في مخزن الفاتورة الأصلية (الخدمات تظهر دائماً)
    from django.db import models
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
            products_filter & (models.Q(is_service=True) | models.Q(id__in=products_with_stock))
        ).order_by("name")
    elif allowed_item_types == 'products':
        products = Product.objects.filter(
            products_filter & models.Q(id__in=products_with_stock)
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

    # رقم الفاتورة الجديد
    next_sale_number = None
    try:
        serial, _ = SerialNumber.objects.get_or_create(
            document_type="sale",
            year=timezone.now().year,
            defaults={"prefix": "SALE", "last_number": 0},
        )
        last_sale = Sale.objects.order_by("-id").first()
        last_number = 0
        if last_sale and last_sale.number:
            try:
                last_number = int(last_sale.number.replace("SALE", ""))
            except (ValueError, AttributeError):
                pass
        next_number = max(serial.last_number, last_number) + 1
        next_sale_number = f"{serial.prefix}{next_number:04d}"
    except Exception as e:
        logger.error(f"خطأ في الحصول على الرقم التالي: {str(e)}")

    # تحديد نوع الفاتورة
    if original.payment_method == "credit":
        invoice_type = "credit"
    elif original.payment_method == "credit_with_downpayment":
        invoice_type = "credit_with_downpayment"
    else:
        invoice_type = "cash"

    # التصنيف المالي بصيغة cat_X
    financial_category_id = f"cat_{original.financial_category.id}" if original.financial_category else None

    # بيانات البنود
    duplicate_items = json.dumps([
        {
            "product_id": item.product.id,
            "quantity": float(item.quantity),
            "unit_price": float(item.unit_price),
            "discount": float(item.discount),
            "total": float(item.total),
            "is_service": item.product.is_service,
        }
        for item in original.items.all()
    ])

    form = SaleForm(initial={
        "date": timezone.now().date(),
        "customer": original.customer,
        "warehouse": original.warehouse,
        "discount": original.discount,
        "notes": original.notes,
        "payment_method": original.payment_method,
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
        "duplicate_invoice_type": invoice_type,
        "duplicate_payment_method": original.payment_method,
        "duplicate_financial_category_id": financial_category_id,
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
