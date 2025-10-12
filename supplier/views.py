from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.db import models
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from .models import (
    Supplier, SupplierType, SpecializedService,
    PaperServiceDetails, DigitalPrintingDetails, FinishingServiceDetails
)
from .forms import SupplierForm, SupplierAccountChangeForm
from purchase.models import Purchase, PurchaseItem


@login_required
def supplier_list(request):
    """
    عرض قائمة الموردين
    """
    # فلترة بناءً على المعايير
    status = request.GET.get('status', '')
    search = request.GET.get('search', '')
    supplier_type = request.GET.get('supplier_type', '')
    preferred = request.GET.get('preferred', '')
    order_by = request.GET.get('order_by', 'balance')
    order_dir = request.GET.get('order_dir', 'desc')  # تنازلي افتراضيًا
    
    suppliers = Supplier.objects.prefetch_related('supplier_types').all()
    
    if status == 'active':
        suppliers = suppliers.filter(is_active=True)
    elif status == 'inactive':
        suppliers = suppliers.filter(is_active=False)
    
    if supplier_type:
        suppliers = suppliers.filter(supplier_types__id=supplier_type)
    
    if preferred == '1':
        suppliers = suppliers.filter(is_preferred=True)
        
    if search:
        suppliers = suppliers.filter(
            models.Q(name__icontains=search) | 
            models.Q(code__icontains=search) |
            models.Q(phone__icontains=search) |
            models.Q(city__icontains=search)
        )
    
    # ترتيب النتائج
    if order_by:
        order_field = order_by
        if order_dir == 'desc':
            order_field = f'-{order_by}'
        suppliers = suppliers.order_by(order_field)
    else:
        # ترتيب حسب الأعلى استحقاق افتراضيًا
        suppliers = suppliers.order_by('-balance')
    
    active_suppliers = suppliers.filter(is_active=True).count()
    preferred_suppliers = suppliers.filter(is_preferred=True).count()
    
    # حساب إجمالي الاستحقاق الفعلي
    total_debt = 0
    for supplier in suppliers:
        supplier_debt = supplier.actual_balance
        if supplier_debt > 0:  # فقط الاستحقاق الموجب
            total_debt += supplier_debt
    
    total_purchases = 0  # قد تحتاج لحساب إجمالي المشتريات من موديل آخر
    
    # جلب أنواع الموردين للفلتر
    supplier_types = SupplierType.objects.filter(is_active=True).order_by('display_order')
    
    # تعريف أعمدة الجدول
    headers = [
        {'key': 'name', 'label': 'اسم المورد', 'sortable': True, 'class': 'text-center', 'format': 'link', 'url': 'supplier:supplier_detail'},
        {'key': 'code', 'label': 'الكود', 'sortable': True},
        {'key': 'supplier_types_display', 'label': 'أنواع الخدمات', 'sortable': False, 'format': 'html'},
        {'key': 'phone', 'label': 'رقم الهاتف', 'sortable': False},
        {'key': 'city', 'label': 'المدينة', 'sortable': True},
        {'key': 'is_preferred', 'label': 'مفضل', 'sortable': True, 'format': 'boolean_badge'},
        {'key': 'actual_balance', 'label': 'الاستحقاق', 'sortable': True, 'format': 'currency', 'decimals': 2, 'variant': 'text-danger'},
        {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'format': 'boolean'},
    ]
    
    # تعريف أزرار الإجراءات
    action_buttons = [
        {'url': 'supplier:supplier_detail', 'icon': 'fa-eye', 'class': 'action-view', 'label': 'عرض'},
        {'url': 'supplier:supplier_edit', 'icon': 'fa-edit', 'class': 'action-edit', 'label': 'تعديل'},
        {'url': 'supplier:supplier_delete', 'icon': 'fa-trash', 'class': 'action-delete', 'label': 'حذف'}
    ]
    
    context = {
        'suppliers': suppliers,
        'headers': headers,
        'action_buttons': action_buttons,
        'active_suppliers': active_suppliers,
        'preferred_suppliers': preferred_suppliers,
        'total_debt': total_debt,
        'total_purchases': total_purchases,
        'supplier_types': supplier_types,
        'page_title': 'قائمة الموردين',
        'page_icon': 'fas fa-truck',
        'current_order_by': order_by,
        'current_order_dir': order_dir,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'active': True}
        ],
    }
    
    # Ajax response
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'html': render_to_string('supplier/supplier_list.html', context, request),
            'success': True
        })
    
    return render(request, 'supplier/supplier_list.html', context)


@login_required
def supplier_add(request):
    """
    إضافة مورد جديد
    """
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.created_by = request.user
            supplier.save()
            messages.success(request, _('تم إضافة المورد بنجاح'))
            return redirect('supplier:supplier_list')
    else:
        form = SupplierForm()
    
    context = {
        'form': form,
        'page_title': 'إضافة مورد جديد',
        'page_icon': 'fas fa-user-plus',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': 'إضافة مورد', 'active': True}
        ],
    }
    
    return render(request, 'supplier/supplier_form.html', context)


@login_required
def supplier_edit(request, pk):
    """
    تعديل بيانات مورد
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    
    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, _('تم تعديل بيانات المورد بنجاح'))
            return redirect('supplier:supplier_list')
    else:
        form = SupplierForm(instance=supplier)
    
    context = {
        'form': form,
        'supplier': supplier,
        'page_title': f'تعديل بيانات المورد: {supplier.name}',
        'page_icon': 'fas fa-user-edit',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': supplier.pk})},
            {'title': 'تعديل', 'active': True}
        ],
    }
    
    return render(request, 'supplier/supplier_form.html', context)


@login_required
def supplier_delete(request, pk):
    """
    حذف مورد (تعطيل)
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    
    if request.method == 'POST':
        supplier.is_active = False
        supplier.save()
        messages.success(request, _('تم حذف المورد بنجاح'))
        return redirect('supplier:supplier_list')
    
    context = {
        'supplier': supplier,
        'page_title': f'حذف المورد: {supplier.name}',
        'page_icon': 'fas fa-user-times',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': supplier.pk})},
            {'title': 'حذف', 'active': True}
        ],
    }
    
    return render(request, 'supplier/supplier_delete.html', context)


@login_required
def supplier_detail(request, pk):
    """
    عرض تفاصيل المورد ودفعات الفواتير
    """
    supplier = get_object_or_404(
        Supplier.objects.prefetch_related(
            'specialized_services__paper_details',
            'specialized_services__offset_details', 
            'specialized_services__digital_details',
            'specialized_services__category'
        ), 
        pk=pk
    )
    
    # جلب دفعات فواتير المشتريات المرتبطة بالمورد
    from purchase.models import PurchasePayment
    payments = PurchasePayment.objects.filter(purchase__supplier=supplier).order_by('-payment_date')
    
    # جلب فواتير الشراء المرتبطة بالمورد
    purchases = Purchase.objects.filter(supplier=supplier).order_by('-date')
    purchases_count = purchases.count()
    
    # حساب إجمالي المشتريات
    total_purchases = purchases.aggregate(total=Sum('total'))['total'] or 0
    
    # حساب عدد المنتجات الفريدة في فواتير الشراء
    purchase_items = PurchaseItem.objects.filter(purchase__supplier=supplier)
    products_count = purchase_items.values('product').distinct().count()
    
    # جلب المنتجات مع تفاصيل الشراء
    from django.db.models import Max, Min, Avg, Count
    supplier_products = purchase_items.values(
        'product__id',
        'product__name', 
        'product__sku',
        'product__category__name'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_purchases=Count('purchase', distinct=True),
        last_purchase_date=Max('purchase__created_at'),
        first_purchase_date=Min('purchase__created_at'),
        avg_price=Avg('unit_price'),
        last_price=Max('unit_price'),
        min_price=Min('unit_price'),
        max_price=Max('unit_price')
    ).order_by('-last_purchase_date')[:20]  # أحدث 20 منتج
    
    # تاريخ آخر معاملة
    last_transaction_date = None
    if payments.exists() or purchases.exists():
        last_payment_date = payments.first().payment_date if payments.exists() else None
        last_purchase_date = purchases.first().date if purchases.exists() else None
        
        if last_payment_date and last_purchase_date:
            last_transaction_date = max(last_payment_date, last_purchase_date)
        elif last_payment_date:
            last_transaction_date = last_payment_date
        else:
            last_transaction_date = last_purchase_date
    
    total_payments = payments.aggregate(total=Sum('amount'))['total'] or 0
    
    # جلب القيود المحاسبية المرتبطة بالمورد
    from financial.models import JournalEntry, JournalEntryLine
    journal_entries = []
    journal_entries_count = 0
    
    try:
        # البحث عن القيود المرتبطة بفواتير المورد - بحث أوسع
        # نبحث بـ contains عشان نلاقي أي قيد فيه رقم الفاتورة أو الدفعة
        purchase_ids = [p.id for p in purchases]
        payment_ids = [pay.id for pay in payments]
        
        # بناء query للبحث
        query = Q()
        for p_id in purchase_ids:
            query |= Q(reference__icontains=f'PURCH-{p_id}') | Q(reference__icontains=f'{p_id}')
        for pay_id in payment_ids:
            query |= Q(reference__icontains=f'PAY-{pay_id}') | Q(reference__icontains=f'{pay_id}')
        
        if query:
            journal_entries = JournalEntry.objects.filter(query).prefetch_related('lines').order_by('-date')
            journal_entries_count = journal_entries.count()
            
            # حساب إجمالي المدين لكل قيد
            for entry in journal_entries:
                entry.total_amount = entry.lines.aggregate(total=Sum('debit'))['total'] or 0
        
        # Debug: طباعة عدد القيود
        print(f"عدد القيود المحاسبية للمورد: {journal_entries_count}")
    except Exception as e:
        print(f"خطأ في جلب القيود المحاسبية: {e}")
        import traceback
        traceback.print_exc()
    
    # محاولة الحصول على حساب المورد في دليل الحسابات
    financial_account = None
    try:
        from financial.models import ChartOfAccounts, AccountType
        
        # البحث بطرق متعددة
        # 1. البحث باسم المورد في حسابات الموردين
        payables_type = AccountType.objects.filter(code='PAYABLES').first()
        if payables_type:
            financial_account = ChartOfAccounts.objects.filter(
                name__icontains=supplier.name,
                account_type=payables_type,
                is_active=True
            ).first()
        
        # 2. إذا لم نجد، نبحث في أي حساب يحتوي على اسم المورد
        if not financial_account:
            financial_account = ChartOfAccounts.objects.filter(
                name__icontains=supplier.name,
                is_active=True
            ).first()
        
        # 3. إذا لم نجد، نبحث في حسابات الموردين العامة
        if not financial_account and payables_type:
            # نجيب أول حساب موردين نشط
            financial_account = ChartOfAccounts.objects.filter(
                account_type=payables_type,
                is_active=True
            ).first()
        
        # Debug
        print(f"حساب المورد المالي: {financial_account.name if financial_account else 'لا يوجد'}")
    except Exception as e:
        print(f"خطأ في جلب الحساب المالي: {e}")
        import traceback
        traceback.print_exc()
    
    # تجهيز بيانات المعاملات لكشف الحساب
    transactions = []
    
    # إضافة فواتير الشراء
    for purchase in purchases:
        transactions.append({
            'date': purchase.created_at,
            'reference': purchase.number,
            'purchase_id': purchase.id,
            'type': 'purchase',
            'description': f'فاتورة شراء رقم {purchase.number}',
            'debit': purchase.total,
            'credit': 0,
            'balance': 0  # سيتم حسابه لاحقاً
        })
    
    # إضافة المدفوعات
    for payment in payments:
        payment_desc = f'دفعة {payment.get_payment_method_display()}'
        if payment.purchase:
            payment_desc += f' - فاتورة {payment.purchase.number}'
        
        transactions.append({
            'date': payment.created_at,
            'reference': payment.reference_number,
            'payment_id': payment.id,
            'purchase_id': payment.purchase.id if payment.purchase else None,
            'type': 'payment',
            'description': payment_desc,
            'debit': 0,
            'credit': payment.amount,
            'balance': 0  # سيتم حسابه لاحقاً
        })
    
    # ترتيب المعاملات حسب التاريخ (من الأقدم للأحدث)
    transactions.sort(key=lambda x: x['date'])
    
    # حساب الرصيد التراكمي
    running_balance = 0
    for transaction in transactions:
        running_balance = running_balance + transaction['debit'] - transaction['credit']
        transaction['balance'] = running_balance
    
    # عكس ترتيب المعاملات (من الأحدث للأقدم) للعرض
    transactions.reverse()
    
    # حساب عدد أنواع الخدمات المتخصصة (عدد الفئات المختلفة)
    supplier_service_categories_count = 0
    try:
        # الحصول على عدد الفئات المختلفة للخدمات المتخصصة
        supplier_service_categories_count = supplier.specialized_services.filter(
            is_active=True
        ).values('category').distinct().count()
    except Exception as e:
        print(f"خطأ في حساب عدد أنواع الخدمات: {e}")
    
    # تعريف أعمدة جدول المشتريات للنظام المحسن
    purchase_headers = [
        {'key': 'id', 'label': '#', 'sortable': True, 'class': 'text-center', 'width': '60px'},
        {'key': 'created_at', 'label': 'التاريخ والوقت', 'sortable': True, 'class': 'text-center', 'format': 'datetime_12h'},
        {'key': 'number', 'label': 'رقم الفاتورة', 'sortable': True, 'class': 'text-center', 'format': 'reference', 'variant': 'highlight-code', 'app': 'purchase'},
        {'key': 'total', 'label': 'المبلغ', 'sortable': True, 'class': 'text-center', 'format': 'currency'},
        {'key': 'amount_paid', 'label': 'المدفوع', 'sortable': True, 'class': 'text-center', 'format': 'currency'},
        {'key': 'amount_due', 'label': 'المتبقي', 'sortable': True, 'class': 'text-center', 'format': 'currency', 'variant': 'negative'},
        {'key': 'payment_status', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'format': 'status'},
    ]
    
    # تعريف أزرار الإجراءات لجدول المشتريات
    purchase_action_buttons = [
        {'url': 'purchase:purchase_detail', 'icon': 'fa-eye', 'class': 'action-view', 'label': 'عرض الفاتورة'},
        {'url': 'purchase:purchase_add_payment', 'icon': 'fa-money-bill', 'class': 'action-paid', 'label': 'إضافة دفعة', 'condition': 'not_fully_paid'},
    ]
    
    # تعريف أعمدة جدول المنتجات للنظام المحسن
    products_headers = [
        {'key': 'product__sku', 'label': 'كود المنتج', 'sortable': True, 'class': 'text-center', 'width': '100px'},
        {'key': 'product__name', 'label': 'اسم المنتج', 'sortable': True, 'class': 'text-start'},
        {'key': 'product__category__name', 'label': 'التصنيف', 'sortable': True, 'class': 'text-center'},
        {'key': 'total_quantity', 'label': 'إجمالي الكمية', 'sortable': True, 'class': 'text-center'},
        {'key': 'total_purchases', 'label': 'عدد الفواتير', 'sortable': True, 'class': 'text-center'},
        {'key': 'last_purchase_date', 'label': 'آخر شراء', 'sortable': True, 'class': 'text-center', 'format': 'datetime_12h'},
        {'key': 'avg_price', 'label': 'متوسط السعر', 'sortable': True, 'class': 'text-center', 'format': 'currency'},
        {'key': 'last_price', 'label': 'آخر سعر', 'sortable': True, 'class': 'text-center', 'format': 'currency'},
    ]
    
    # إضافة أزرار إجراءات للمنتجات (معطلة مؤقتاً - namespace غير موجود)
    products_action_buttons = []
    
    # تعريف أعمدة جدول المدفوعات للنظام المحسن
    payments_headers = [
        {'key': 'id', 'label': '#', 'sortable': True, 'class': 'text-center', 'width': '50px'},
        {'key': 'created_at', 'label': 'تاريخ ووقت الدفع', 'sortable': True, 'class': 'text-center', 'format': 'datetime_12h', 'width': '140px'},
        {'key': 'purchase__number', 'label': 'رقم الفاتورة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/invoice_reference.html', 'width': '130px'},
        {'key': 'amount', 'label': 'المبلغ', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/payment_amount.html', 'width': '120px'},
        {'key': 'payment_method', 'label': 'طريقة الدفع', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/payment_method.html', 'width': '120px'},
        {'key': 'notes', 'label': 'ملاحظات', 'sortable': False, 'class': 'text-start'},
    ]
    
    # تعريف أعمدة جدول القيود المحاسبية للنظام المحسن
    journal_headers = [
        {'key': 'id', 'label': '#', 'sortable': True, 'class': 'text-center', 'width': '50px'},
        {'key': 'number', 'label': 'رقم القيد', 'sortable': True, 'class': 'text-center', 'width': '140px'},
        {'key': 'created_at', 'label': 'التاريخ والوقت', 'sortable': True, 'class': 'text-center', 'format': 'datetime_12h', 'width': '140px'},
        {'key': 'status', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/journal_status.html', 'width': '90px'},
        {'key': 'reference', 'label': 'المرجع', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/journal_reference.html', 'width': '150px'},
        {'key': 'description', 'label': 'الوصف', 'sortable': False, 'class': 'text-start'},
        {'key': 'total_amount', 'label': 'المبلغ', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/journal_amount.html', 'width': '110px'},
    ]
    
    # أزرار إجراءات القيود المحاسبية (معطلة مؤقتاً - للتحقق من namespace)
    journal_action_buttons = []
    
    # تعريف أعمدة جدول الخدمات المتخصصة للنظام المحسن
    # أعمدة الأوفست
    offset_services_headers = [
        {'key': 'name', 'label': 'اسم الماكينة', 'sortable': True, 'class': 'text-start', 'width': '35%'},
        {'key': 'sheet_size', 'label': 'المقاس', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/offset_sheet_size.html', 'width': '15%'},
        {'key': 'colors_capacity', 'label': 'عدد الألوان', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/offset_colors.html', 'width': '12%'},
        {'key': 'impression_cost', 'label': 'سعر التراج', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/offset_impression_cost.html', 'width': '18%'},
        {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'format': 'status', 'width': '10%'},
        {'key': 'actions', 'label': 'الإجراءات', 'sortable': False, 'class': 'text-center', 'template': 'components/cells/service_actions.html', 'width': '10%'},
    ]
    
    # أعمدة الديجيتال
    digital_services_headers = [
        {'key': 'name', 'label': 'اسم الماكينة', 'sortable': True, 'class': 'text-start', 'width': '35%'},
        {'key': 'paper_size', 'label': 'المقاس', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/digital_sheet_size.html', 'width': '15%'},
        {'key': 'price_tiers_count', 'label': 'عدد الشرائح', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/digital_tiers_count.html', 'width': '12%'},
        {'key': 'price_range', 'label': 'السعر', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/digital_price_range.html', 'width': '18%'},
        {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'format': 'status', 'width': '10%'},
        {'key': 'actions', 'label': 'الإجراءات', 'sortable': False, 'class': 'text-center', 'template': 'components/cells/service_actions.html', 'width': '10%'},
    ]
    
    # أعمدة الورق
    paper_services_headers = [
        {'key': 'name', 'label': 'اسم الورق', 'sortable': True, 'class': 'text-start', 'width': '25%'},
        {'key': 'paper_details.paper_type', 'label': 'النوع', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/paper_type.html', 'width': '15%'},
        {'key': 'paper_details.sheet_size', 'label': 'المقاس', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/paper_size_simple.html', 'width': '20%'},
        {'key': 'paper_details.gsm', 'label': 'الوزن', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/paper_weight.html', 'width': '15%'},
        {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'format': 'status', 'width': '10%'},
        {'key': 'actions', 'label': 'الإجراءات', 'sortable': False, 'class': 'text-center', 'template': 'components/cells/service_actions.html', 'width': '15%'},
    ]
    
    # أعمدة الزنكات CTP
    plates_services_headers = [
        {'key': 'name', 'label': 'اسم الخدمة', 'sortable': True, 'class': 'text-start', 'width': '25%'},
        {'key': 'plate_size', 'label': 'مقاس الزنك', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/plate_size_simple.html', 'width': '20%'},
        {'key': 'plate_price', 'label': 'سعر الزنك', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/plate_price.html', 'width': '15%'},
        {'key': 'set_price', 'label': 'سعر الطقم', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/plate_set_price.html', 'width': '15%'},
        {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'format': 'status', 'width': '10%'},
        {'key': 'actions', 'label': 'الإجراءات', 'sortable': False, 'class': 'text-center', 'template': 'components/cells/service_actions.html', 'width': '15%'},
    ]
    
    # Headers افتراضية (للأوفست)
    services_headers = offset_services_headers
    
    # أزرار إجراءات الخدمات المتخصصة (تعديل وحذف فقط)
    services_action_buttons = []
    
    # تعريف أعمدة جدول كشف الحساب للنظام المحسن
    statement_headers = [
        {'key': 'date', 'label': 'التاريخ والوقت', 'sortable': True, 'class': 'text-center', 'format': 'datetime_12h', 'width': '140px'},
        {'key': 'reference', 'label': 'المرجع', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/statement_reference.html', 'width': '120px'},
        {'key': 'type', 'label': 'نوع الحركة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/statement_type.html', 'width': '100px'},
        {'key': 'description', 'label': 'الوصف', 'sortable': True, 'class': 'text-start'},
        {'key': 'debit', 'label': 'مدين', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/statement_amount.html', 'width': '120px'},
        {'key': 'credit', 'label': 'دائن', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/statement_amount.html', 'width': '120px'},
        {'key': 'balance', 'label': 'الرصيد', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/statement_balance.html', 'width': '120px'},
    ]


    context = {
        'supplier': supplier,
        'payments': payments,
        'purchases': purchases,
        'purchases_count': purchases_count,
        'total_purchases': total_purchases,
        'products_count': products_count,
        'supplier_products': supplier_products,
        'total_payments': total_payments,
        'last_transaction_date': last_transaction_date,
        'transactions': transactions,
        'journal_entries': journal_entries,
        'journal_entries_count': journal_entries_count,
        'financial_account': financial_account,
        'supplier_services_count': supplier.get_specialized_services_count(),  # عدد الخدمات الإجمالي
        'supplier_service_categories_count': supplier_service_categories_count,  # عدد أنواع الخدمات (الفئات)
        'purchase_headers': purchase_headers,  # أعمدة جدول المشتريات
        'purchase_action_buttons': purchase_action_buttons,  # أزرار إجراءات المشتريات
        'products_headers': products_headers,  # أعمدة جدول المنتجات
        'products_action_buttons': products_action_buttons,  # أزرار إجراءات المنتجات
        'payments_headers': payments_headers,  # أعمدة جدول المدفوعات
        'journal_headers': journal_headers,  # أعمدة جدول القيود المحاسبية
        'journal_action_buttons': journal_action_buttons,  # أزرار إجراءات القيود
        'services_headers': services_headers,  # أعمدة جدول الخدمات المتخصصة (افتراضي للأوفست)
        'offset_services_headers': offset_services_headers,  # أعمدة جدول الأوفست
        'digital_services_headers': digital_services_headers,  # أعمدة جدول الديجيتال
        'paper_services_headers': paper_services_headers,  # أعمدة جدول الورق
        'plates_services_headers': plates_services_headers,  # أعمدة جدول الزنكات CTP
        'services_action_buttons': services_action_buttons,  # أزرار إجراءات الخدمات
        'statement_headers': statement_headers,  # أعمدة جدول كشف الحساب
        'primary_key': 'id',  # المفتاح الأساسي للجداول
        'products_primary_key': 'product__id',  # المفتاح الأساسي لجدول المنتجات
        # إعدادات الصفوف القابلة للنقر
        'purchases_clickable': True,
        'purchases_click_url': 'purchase:purchase_detail',
        'payments_clickable': True,
        'payments_click_url': 'purchase:payment_detail',
        'journal_clickable': True,
        'journal_click_url': 'financial:journal_entry_detail',
        'page_title': f'بيانات المورد: {supplier.name}',
        'page_icon': 'fas fa-truck',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'active': True}
        ],
    }
    
    return render(request, 'supplier/supplier_detail.html', context)


@login_required
def supplier_list_api(request):
    """
    API لإرجاع قائمة الموردين النشطين
    """
    from django.http import JsonResponse
    
    try:
        suppliers = Supplier.objects.filter(is_active=True).order_by('name')
        
        suppliers_data = []
        for supplier in suppliers:
            suppliers_data.append({
                'id': supplier.id,
                'name': supplier.name,
                'code': supplier.code,
                'phone': supplier.phone,
                'balance': float(supplier.balance) if supplier.balance else 0
            })
        
        return JsonResponse({
            'success': True,
            'suppliers': suppliers_data
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'خطأ في تحميل الموردين: {str(e)}'
        })


@login_required
def supplier_change_account(request, pk):
    """
    تغيير الحساب المحاسبي للمورد
    """
    supplier = get_object_or_404(Supplier, pk=pk)
    
    if request.method == 'POST':
        form = SupplierAccountChangeForm(request.POST, instance=supplier)
        if form.is_valid():
            old_account = supplier.financial_account
            form.save()
            
            # رسالة تأكيد
            if old_account:
                messages.success(request, f'تم تغيير الحساب المحاسبي من "{old_account.name}" إلى "{supplier.financial_account.name}" بنجاح')
            else:
                messages.success(request, f'تم ربط المورد بالحساب المحاسبي "{supplier.financial_account.name}" بنجاح')
            
            return redirect('supplier:supplier_detail', pk=supplier.pk)
    else:
        form = SupplierAccountChangeForm(instance=supplier)
    
    context = {
        'form': form,
        'supplier': supplier,
        'page_title': f'تغيير الحساب المحاسبي للمورد: {supplier.name}',
        'page_icon': 'fas fa-exchange-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': supplier.pk})},
            {'title': 'تغيير الحساب المحاسبي', 'active': True}
        ],
    }
    
    return render(request, 'supplier/supplier_change_account.html', context)


# ===== تم حذف النظام القديم واستبداله بالنظام المتخصص الجديد =====
# الخدمات المتخصصة الجديدة متاحة في views_pricing.py


# ===== الخدمات المتخصصة الجديدة =====

@login_required
def specialized_services_list(request):
    """عرض قائمة الخدمات المتخصصة مع تصميم Accordion محسن"""
    
    # فلترة
    category_filter = request.GET.get('category', '')
    supplier_type_filter = request.GET.get('supplier_type', '')
    search = request.GET.get('search', '')
    
    # استعلام محسن مع العلاقات المطلوبة
    services = SpecializedService.objects.filter(is_active=True).select_related(
        'supplier', 
        'category',
        'supplier__primary_type'
    ).prefetch_related(
        'supplier__supplier_types'
    )
    
    # تطبيق الفلاتر
    if category_filter:
        services = services.filter(category__code=category_filter)
    
    if supplier_type_filter:
        services = services.filter(supplier__primary_type__code=supplier_type_filter)
    
    if search:
        services = services.filter(
            Q(name__icontains=search) |
            Q(supplier__name__icontains=search) |
            Q(description__icontains=search) |
            Q(category__name__icontains=search)
        )
    
    # ترتيب الخدمات حسب الفئة ثم الاسم
    services = services.order_by('category__name', 'name')
    
    # البيانات للفلاتر - فقط الفئات التي لها خدمات
    categories = SupplierType.objects.filter(
        is_active=True,
        specialized_services__is_active=True
    ).distinct().order_by('name')
    
    supplier_types = SupplierType.objects.filter(
        is_active=True,
        suppliers__specialized_services__is_active=True
    ).distinct().order_by('name')
    
    # إحصائيات إضافية
    total_services = services.count()
    total_suppliers = services.values('supplier').distinct().count() if services.exists() else 0
    total_categories = services.values('category').distinct().count() if services.exists() else 0
    
    # متوسط التقييم
    avg_rating = 0
    if services.exists():
        ratings = [s.supplier.supplier_rating for s in services if s.supplier.supplier_rating and s.supplier.supplier_rating > 0]
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
    
    # تعريف عناوين أعمدة الجدول (العرض العام)
    general_service_headers = [
        {'key': 'name', 'label': 'اسم الخدمة', 'sortable': True, 'class': 'text-start'},
        {'key': 'category.name', 'label': 'الفئة', 'sortable': True, 'class': 'text-center'},
        {'key': 'supplier.name', 'label': 'المورد', 'sortable': True, 'format': 'link', 'url': 'supplier:supplier_detail'},
        {'key': 'setup_cost', 'label': 'تكلفة التجهيز', 'sortable': True, 'class': 'text-center', 'format': 'currency'},
        {'key': 'supplier.supplier_rating', 'label': 'التقييم', 'sortable': True, 'class': 'text-center', 'format': 'rating'},
        {'key': 'supplier.is_preferred', 'label': 'مفضل', 'sortable': True, 'class': 'text-center', 'format': 'boolean_badge'},
    ]

    # تعريف headers لصفحة المورد (بدون عمود المورد)
    supplier_service_headers = [
        {'key': 'name', 'label': 'اسم الخدمة', 'sortable': True, 'class': 'text-start'},
        {'key': 'category.name', 'label': 'الفئة', 'sortable': True, 'class': 'text-center'},
        {'key': 'setup_cost', 'label': 'تكلفة التجهيز', 'sortable': True, 'class': 'text-center', 'format': 'currency'},
        {'key': 'description', 'label': 'الوصف', 'sortable': False, 'class': 'text-start', 'ellipsis': True},
    ]

    # تعريف headers لصفحة الفئة (مع عمود المورد)
    category_service_headers = [
        {'key': 'name', 'label': 'اسم الخدمة', 'sortable': True, 'class': 'text-start'},
        {'key': 'supplier.name', 'label': 'المورد', 'sortable': True, 'format': 'link', 'url': 'supplier:supplier_detail'},
        {'key': 'setup_cost', 'label': 'تكلفة التجهيز', 'sortable': True, 'class': 'text-center', 'format': 'currency'},
        {'key': 'supplier.supplier_rating', 'label': 'التقييم', 'sortable': True, 'class': 'text-center', 'format': 'rating'},
        {'key': 'supplier.is_preferred', 'label': 'مفضل', 'sortable': True, 'class': 'text-center', 'format': 'boolean_badge'},
    ]

    # تعريف أزرار الإجراءات للجدول
    general_service_actions = [
        {'url': 'supplier:supplier_detail', 'icon': 'fa-eye', 'label': 'عرض المورد', 'class': 'action-view'},
        {'url': 'supplier:supplier_detail', 'icon': 'fa-info-circle', 'label': 'تفاصيل الخدمة', 'class': 'action-info'},
    ]

    supplier_service_actions = [
        {'url': 'supplier:supplier_detail', 'icon': 'fa-edit', 'label': 'تعديل الخدمة', 'class': 'action-edit'},
        {'url': 'supplier:supplier_detail', 'icon': 'fa-info-circle', 'label': 'تفاصيل الخدمة', 'class': 'action-info'},
    ]

    category_service_actions = [
        {'url': 'supplier:supplier_detail', 'icon': 'fa-eye', 'label': 'عرض المورد', 'class': 'action-view'},
        {'url': 'supplier:supplier_detail', 'icon': 'fa-info-circle', 'label': 'تفاصيل الخدمة', 'class': 'action-info'},
    ]

    context = {
        'services': services,
        'categories': categories,
        'supplier_types': supplier_types,
        'current_category': category_filter,
        'current_supplier_type': supplier_type_filter,
        'current_search': search,
        'page_title': 'الخدمات المتخصصة',
        'page_icon': 'fas fa-cogs',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': 'الخدمات المتخصصة', 'active': True}
        ],
        # إحصائيات للواجهة الجديدة
        'stats': {
            'total_services': total_services,
            'total_suppliers': total_suppliers,
            'total_categories': total_categories,
            'avg_rating': round(avg_rating, 1) if avg_rating else 0,
        },
        # معلومات إضافية للتصميم المحسن
        'has_filters': bool(category_filter or supplier_type_filter or search),
        'results_count': total_services,
        # بيانات الجدول الموحد
        'general_service_headers': general_service_headers,
        'general_service_actions': general_service_actions,
        'supplier_service_headers': supplier_service_headers,
        'supplier_service_actions': supplier_service_actions,
        'category_service_headers': category_service_headers,
        'category_service_actions': category_service_actions,
    }
    
    return render(request, 'supplier/specialized_services_list.html', context)


@login_required
def suppliers_by_type(request):
    """عرض الموردين مصنفين حسب النوع"""
    
    # جلب جميع أنواع الموردين النشطة مع الموردين المرتبطين
    supplier_types = SupplierType.objects.filter(is_active=True).prefetch_related(
        'primary_suppliers',
        'suppliers'
    ).order_by('display_order')
    
    # إضافة الإحصائيات لكل نوع مورد
    for supplier_type in supplier_types:
        # جميع الموردين النشطين المرتبطين بهذا النوع (many-to-many)
        active_suppliers = supplier_type.suppliers.filter(is_active=True).order_by('name')
        
        # حساب الخدمات المتخصصة
        try:
            total_services = SpecializedService.objects.filter(
                supplier__in=active_suppliers,
                is_active=True
            ).count()
        except:
            total_services = 0
        
        # إضافة الإحصائيات كخصائص للكائن
        supplier_type.total_suppliers = active_suppliers.count()
        supplier_type.total_services = total_services
        # إضافة قائمة الموردين النشطين للعرض
        supplier_type.active_suppliers_list = active_suppliers
    
    context = {
        'supplier_types': supplier_types,
        'page_title': 'الموردين حسب النوع',
        'page_icon': 'fas fa-layer-group',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': 'تصنيف حسب النوع', 'active': True}
        ],
    }
    
    return render(request, 'supplier/suppliers_by_type.html', context)


@login_required
def service_comparison(request):
    """مقارنة الخدمات والأسعار"""
    
    category_code = request.GET.get('category', 'paper')
    category = get_object_or_404(SupplierType, code=category_code, is_active=True)
    
    services = SpecializedService.objects.filter(
        category=category,
        is_active=True
    ).select_related('supplier').order_by('setup_cost')
    
    # تجهيز بيانات المقارنة
    comparison_data = []
    for service in services:
        service_data = {
            'service': service,
            'supplier': service.supplier,
            'contact_methods': service.supplier.get_contact_methods(),
            'rating_stars': service.supplier.get_rating_stars(),
            'quality_stars': service.supplier.get_quality_rating_stars(),
        }
        
        # إضافة التفاصيل المتخصصة
        if category.code == 'paper' and hasattr(service, 'paper_details'):
            service_data['details'] = service.paper_details
        elif category.code == 'digital_printing' and hasattr(service, 'digital_details'):
            service_data['details'] = service.digital_details
        elif category.code == 'finishing' and hasattr(service, 'finishing_details'):
            service_data['details'] = service.finishing_details
        
        comparison_data.append(service_data)
    
    categories = SupplierType.objects.filter(is_active=True)
    
    context = {
        'category': category,
        'categories': categories,
        'comparison_data': comparison_data,
        'page_title': f'مقارنة خدمات {category.name}',
        'page_icon': 'fas fa-balance-scale',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': 'مقارنة الخدمات', 'active': True}
        ],
    }
    
    return render(request, 'supplier/service_comparison.html', context)


@login_required
def supplier_services_detail(request, pk):
    """عرض تفاصيل خدمات مورد معين"""
    
    supplier = get_object_or_404(Supplier, pk=pk)
    services = supplier.specialized_services.filter(is_active=True).select_related('category')
    
    # تجميع الخدمات حسب الفئة
    services_by_category = {}
    for service in services:
        category_name = service.category.name
        if category_name not in services_by_category:
            services_by_category[category_name] = []
        
        service_data = {'service': service}
        
        # إضافة التفاصيل المتخصصة
        if hasattr(service, 'paper_details'):
            service_data['details'] = service.paper_details
        elif hasattr(service, 'digital_details'):
            service_data['details'] = service.digital_details
        elif hasattr(service, 'finishing_details'):
            service_data['details'] = service.finishing_details
        
        services_by_category[category_name].append(service_data)
    
    context = {
        'supplier': supplier,
        'services_by_category': services_by_category,
        'total_services': services.count(),
        'contact_methods': supplier.get_contact_methods(),
        'page_title': f'خدمات {supplier.name}',
        'page_icon': 'fas fa-tools',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': supplier.pk})},
            {'title': 'الخدمات المتخصصة', 'active': True}
        ],
    }
    
    return render(request, 'supplier/supplier_services_detail.html', context)


# ===== النظام الديناميكي للخدمات المتخصصة =====

@login_required
def add_specialized_service(request, supplier_id, service_id=None):
    """إضافة/تعديل خدمة متخصصة - النظام الديناميكي الموحد"""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    
    # تحديد ما إذا كان تعديل أم إضافة
    service = None
    is_edit = service_id is not None
    
    if is_edit:
        service = get_object_or_404(SpecializedService, id=service_id, supplier=supplier)
    
    # جلب التصنيفات المتاحة
    categories = SupplierType.objects.filter(is_active=True).order_by('display_order')
    
    # تحديد العنوان والأيقونة
    if is_edit:
        page_title = f'تعديل خدمة - {service.name}'
        page_icon = 'fas fa-edit'
        breadcrumb_title = f'تعديل خدمة - {service.name}'
        selected_category = service.category.code
    else:
        page_title = f'إضافة خدمة متخصصة - {supplier.name}'
        page_icon = 'fas fa-plus-circle'
        breadcrumb_title = 'إضافة خدمة متخصصة'
        selected_category = request.GET.get('category', '')
    
    # تحديد template النموذج حسب نوع الخدمة
    form_template = None
    category_code = None
    
    if is_edit and service:
        category_code = service.category.code
    elif selected_category:
        category_code = selected_category
    
    # تحديد template بناءً على نوع الخدمة
    if category_code:
        if category_code == 'offset_printing':
            form_template = 'supplier/forms/offset_form.html'
        elif category_code == 'digital_printing':
            form_template = 'supplier/forms/digital_form.html'
        elif category_code == 'paper':
            form_template = 'supplier/forms/paper_form.html'
        elif category_code == 'finishing':
            form_template = 'supplier/forms/finishing_form.html'
        elif category_code == 'plates':
            form_template = 'supplier/forms/plates_form.html'
    
    # إضافة form_choices للنماذج
    form_choices = {}
    if category_code == 'plates':
        form_choices = {
            'plate_sizes': [
                ('quarter_sheet', 'ربع (35×50 سم)'),
                ('half_sheet', 'نص (50×70 سم)'),
                ('full_sheet', 'فرخ (70×100 سم)'),
                ('custom', 'مقاس مخصوص'),
            ]
        }
    
    context = {
        'supplier': supplier,
        'service': service,
        'categories': categories,
        'selected_category': selected_category,
        'is_edit': is_edit,
        'page_title': page_title,
        'page_icon': page_icon,
        'form_template': form_template,
        'form_choices': form_choices,
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': supplier.pk})},
            {'title': breadcrumb_title, 'active': True}
        ],
    }
    
    return render(request, 'supplier/dynamic_service_form.html', context)


@login_required
def edit_specialized_service(request, supplier_id, service_id):
    """تعديل خدمة متخصصة - النظام الديناميكي الموحد"""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    service = get_object_or_404(SpecializedService, id=service_id, supplier=supplier)
    
    # إعادة توجيه لنفس view الإضافة مع معامل التعديل
    return add_specialized_service(request, supplier_id, service_id=service_id)


@login_required
def delete_specialized_service(request, supplier_id, service_id):
    """حذف خدمة متخصصة"""
    supplier = get_object_or_404(Supplier, id=supplier_id)
    service = get_object_or_404(SpecializedService, id=service_id, supplier=supplier)
    
    if request.method == 'POST':
        service_name = service.name
        service.delete()
        messages.success(request, f'تم حذف الخدمة "{service_name}" بنجاح')
        return redirect('supplier:supplier_detail', pk=supplier_id)
    
    context = {
        'supplier': supplier,
        'service': service,
        'page_title': f'حذف خدمة - {service.name}',
        'page_icon': 'fas fa-trash',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الموردين', 'url': reverse('supplier:supplier_list'), 'icon': 'fas fa-truck'},
            {'title': supplier.name, 'url': reverse('supplier:supplier_detail', kwargs={'pk': supplier.pk})},
            {'title': f'حذف خدمة - {service.name}', 'active': True}
        ],
    }
    
    return render(request, 'supplier/delete_service_confirm.html', context)


# ===== APIs للنظام الديناميكي =====

# استيراد APIs مع معالجة الأخطاء
try:
    from .api_views import (
        get_category_form_api,
        save_specialized_service_api,
        update_specialized_service_api,
        delete_specialized_service_api,
        get_service_details_api
    )
except ImportError as e:
    # في حالة فشل الاستيراد، إنشاء دوال بديلة
    def get_category_form_api(request):
        return JsonResponse({'error': 'API not available'}, status=500)
    
    def save_specialized_service_api(request):
        return JsonResponse({'error': 'API not available'}, status=500)
    
    def update_specialized_service_api(request, service_id):
        return JsonResponse({'error': 'API not available'}, status=500)
    
    def delete_specialized_service_api(request, service_id):
        return JsonResponse({'error': 'API not available'}, status=500)
    
    def get_service_details_api(request, service_id):
        return JsonResponse({'error': 'API not available'}, status=500)


@login_required
def get_paper_sheet_sizes_api(request):
    """
    API لجلب مقاسات الورق المتاحة للمورد ونوع الورق المحددين
    بغض النظر عن الجرامات، مع ضمان النتائج الفريدة
    """
    try:
        paper_type_id = request.GET.get('paper_type_id')
        paper_supplier_id = request.GET.get('paper_supplier_id')
        
        if not paper_type_id or not paper_supplier_id:
            return JsonResponse({
                'success': False,
                'error': 'مطلوب تحديد نوع الورق والمورد'
            })
        
        # الحصول على نوع الورق
        try:
            from pricing.models import PaperType
            paper_type = PaperType.objects.get(id=paper_type_id)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'نوع الورق غير موجود: {str(e)}'
            })
        
        # الحصول على المورد
        try:
            supplier = Supplier.objects.get(id=paper_supplier_id)
        except Supplier.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'المورد غير موجود'
            })
        
        # البحث في خدمات الورق للمورد المحدد ونوع الورق المحدد
        paper_services = PaperServiceDetails.objects.filter(
            service__supplier=supplier,
            service__is_active=True,
            paper_type__icontains=paper_type.name.lower()
        ).values('sheet_size').distinct().order_by('sheet_size')
        
        # تجميع المقاسات الفريدة
        unique_sizes = []
        seen_sizes = set()
        
        for service in paper_services:
            size_code = service['sheet_size']
            
            if size_code and size_code not in seen_sizes:
                seen_sizes.add(size_code)
                
                # الحصول على اسم المقاس من الـ choices
                size_name = dict(PaperServiceDetails.SHEET_SIZE_CHOICES).get(size_code, size_code)
                
                unique_sizes.append({
                    'id': size_code,
                    'name': size_name
                })
        
        return JsonResponse({
            'success': True,
            'sizes': unique_sizes,
            'count': len(unique_sizes)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب مقاسات الورق: {str(e)}'
        })


@login_required
def get_paper_weights_api(request):
    """
    API لجلب جرامات الورق المتاحة للمورد ونوع الورق والمقاس المحددين
    بغض النظر عن بلد المنشأ، مع ضمان النتائج الفريدة
    """
    try:
        paper_type_id = request.GET.get('paper_type_id')
        paper_supplier_id = request.GET.get('paper_supplier_id')
        paper_sheet_size = request.GET.get('paper_sheet_size')
        
        if not paper_type_id or not paper_supplier_id or not paper_sheet_size:
            return JsonResponse({
                'success': False,
                'error': 'مطلوب تحديد نوع الورق والمورد والمقاس'
            })
        
        # الحصول على نوع الورق
        try:
            from pricing.models import PaperType
            paper_type = PaperType.objects.get(id=paper_type_id)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'نوع الورق غير موجود: {str(e)}'
            })
        
        # الحصول على المورد
        try:
            supplier = Supplier.objects.get(id=paper_supplier_id)
        except Supplier.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'المورد غير موجود'
            })
        
        # البحث في خدمات الورق للمورد المحدد ونوع الورق والمقاس المحددين
        paper_services = PaperServiceDetails.objects.filter(
            service__supplier=supplier,
            service__is_active=True,
            paper_type__icontains=paper_type.name.lower(),
            sheet_size=paper_sheet_size
        ).values('gsm').distinct().order_by('gsm')
        
        # تجميع الجرامات الفريدة
        unique_weights = []
        seen_weights = set()
        
        for service in paper_services:
            weight = service['gsm']
            
            if weight and weight not in seen_weights:
                seen_weights.add(weight)
                unique_weights.append({
                    'id': weight,
                    'name': f'{weight} جم'
                })
        
        return JsonResponse({
            'success': True,
            'weights': unique_weights,
            'count': len(unique_weights)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب جرامات الورق: {str(e)}'
        })


@login_required
def get_paper_origins_api(request):
    """
    API لجلب منشأ الورق المتاح للمورد ونوع الورق والمقاس والجرام المحددين
    مع ضمان النتائج الفريدة
    """
    try:
        paper_type_id = request.GET.get('paper_type_id')
        paper_supplier_id = request.GET.get('paper_supplier_id')
        paper_sheet_size = request.GET.get('paper_sheet_size')
        paper_weight = request.GET.get('paper_weight')
        
        if not paper_type_id or not paper_supplier_id or not paper_sheet_size or not paper_weight:
            return JsonResponse({
                'success': False,
                'error': 'مطلوب تحديد نوع الورق والمورد والمقاس والوزن'
            })
        
        # الحصول على نوع الورق
        try:
            from pricing.models import PaperType
            paper_type = PaperType.objects.get(id=paper_type_id)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'نوع الورق غير موجود: {str(e)}'
            })
        
        # الحصول على المورد
        try:
            supplier = Supplier.objects.get(id=paper_supplier_id)
        except Supplier.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'المورد غير موجود'
            })
        
        # البحث في خدمات الورق للمورد المحدد ونوع الورق والمقاس والوزن المحددين
        paper_services = PaperServiceDetails.objects.filter(
            service__supplier=supplier,
            service__is_active=True,
            paper_type__icontains=paper_type.name.lower(),
            sheet_size=paper_sheet_size,
            gsm=int(paper_weight)
        ).values('country_of_origin').distinct().order_by('country_of_origin')
        
        # تجميع منشأ الورق الفريد
        unique_origins = []
        seen_origins = set()
        
        for service in paper_services:
            origin_name = service['country_of_origin']
            
            if origin_name and origin_name.strip() and origin_name not in seen_origins:
                seen_origins.add(origin_name)
                
                # البحث عن منشأ الورق في النموذج للحصول على الاسم الكامل
                try:
                    from pricing.models import PaperOrigin
                    paper_origin = PaperOrigin.objects.filter(
                        Q(name__icontains=origin_name) | 
                        Q(code__iexact=origin_name)
                    ).first()
                    
                    if paper_origin:
                        display_name = paper_origin.name
                        origin_id = paper_origin.id
                    else:
                        # إذا لم يوجد في النموذج، استخدم الاسم كما هو
                        display_name = origin_name
                        origin_id = origin_name
                        
                except Exception:
                    # في حالة الخطأ، استخدم الاسم كما هو
                    display_name = origin_name
                    origin_id = origin_name
                
                unique_origins.append({
                    'id': origin_id,
                    'name': display_name
                })
        
        return JsonResponse({
            'success': True,
            'origins': unique_origins,
            'count': len(unique_origins)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب منشأ الورق: {str(e)}'
        })


@login_required
def get_paper_price_api(request):
    """
    API لجلب سعر الورق بناءً على جميع المواصفات المحددة
    (نوع الورق، المورد، المقاس، الوزن، المنشأ)
    """
    try:
        paper_type_id = request.GET.get('paper_type_id')
        paper_supplier_id = request.GET.get('paper_supplier_id')
        paper_sheet_size = request.GET.get('paper_sheet_size')
        paper_weight = request.GET.get('paper_weight')
        paper_origin = request.GET.get('paper_origin')
        
        if not all([paper_type_id, paper_supplier_id, paper_sheet_size, paper_weight, paper_origin]):
            return JsonResponse({
                'success': False,
                'error': 'مطلوب تحديد جميع مواصفات الورق (النوع، المورد، المقاس، الوزن، المنشأ)'
            })
        
        # الحصول على نوع الورق
        try:
            from pricing.models import PaperType
            paper_type = PaperType.objects.get(id=paper_type_id)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'نوع الورق غير موجود: {str(e)}'
            })
        
        # الحصول على المورد
        try:
            supplier = Supplier.objects.get(id=paper_supplier_id)
        except Supplier.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'المورد غير موجود'
            })
        
        # البحث عن خدمة الورق بالمواصفات المحددة
        # أولاً نحاول البحث بالـ ID إذا كان رقم
        paper_service = None
        origin_name = paper_origin
        
        try:
            # إذا كان paper_origin رقم، نبحث عن اسم المنشأ
            if paper_origin.isdigit():
                from pricing.models import PaperOrigin
                paper_origin_obj = PaperOrigin.objects.get(id=int(paper_origin))
                origin_name = paper_origin_obj.name
                print(f"تم تحويل ID {paper_origin} إلى اسم: {origin_name}")
            else:
                origin_name = paper_origin
                print(f"استخدام الاسم مباشرة: {origin_name}")
                
            # البحث بالاسم أولاً
            paper_service = PaperServiceDetails.objects.filter(
                service__supplier=supplier,
                service__is_active=True,
                paper_type__icontains=paper_type.name.lower(),
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight),
                country_of_origin__icontains=origin_name
            ).first()
            
            print(f"البحث الأول بالاسم: paper_type={paper_type.name}, sheet_size={paper_sheet_size}, gsm={paper_weight}, origin={origin_name}")
            print(f"نتيجة البحث الأول: {paper_service}")
            
            # إذا لم نجد، نحاول البحث بكود الدولة
            if not paper_service and paper_origin.isdigit():
                try:
                    from pricing.models import PaperOrigin
                    paper_origin_obj = PaperOrigin.objects.get(id=int(paper_origin))
                    origin_code = paper_origin_obj.code if hasattr(paper_origin_obj, 'code') else None
                    
                    if origin_code:
                        paper_service = PaperServiceDetails.objects.filter(
                            service__supplier=supplier,
                            service__is_active=True,
                            paper_type__icontains=paper_type.name.lower(),
                            sheet_size=paper_sheet_size,
                            gsm=int(paper_weight),
                            country_of_origin__iexact=origin_code
                        ).first()
                        print(f"البحث الثاني بكود الدولة: {origin_code}")
                        print(f"نتيجة البحث الثاني: {paper_service}")
                except Exception as e:
                    print(f"خطأ في البحث بكود الدولة: {str(e)}")
            
            # إذا لم نجد، نحاول البحث بالقيمة الأصلية
            if not paper_service:
                paper_service = PaperServiceDetails.objects.filter(
                    service__supplier=supplier,
                    service__is_active=True,
                    paper_type__icontains=paper_type.name.lower(),
                    sheet_size=paper_sheet_size,
                    gsm=int(paper_weight),
                    country_of_origin=paper_origin
                ).first()
                print(f"البحث الثالث بالقيمة الأصلية: {paper_origin}")
                print(f"نتيجة البحث الثالث: {paper_service}")
                
            # البحث الأخير: بدون منشأ الورق (كما نجح في التحليل)
            if not paper_service:
                paper_service = PaperServiceDetails.objects.filter(
                    service__supplier=supplier,
                    service__is_active=True,
                    paper_type__icontains=paper_type.name.lower(),
                    sheet_size=paper_sheet_size,
                    gsm=int(paper_weight)
                ).first()
                print(f"البحث الرابع بدون منشأ الورق")
                print(f"نتيجة البحث الرابع: {paper_service}")
                
        except Exception as e:
            print(f"خطأ في البحث: {str(e)}")
            # في حالة الخطأ، نحاول البحث بالقيمة الأصلية
            paper_service = PaperServiceDetails.objects.filter(
                service__supplier=supplier,
                service__is_active=True,
                paper_type__icontains=paper_type.name.lower(),
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight),
                country_of_origin=paper_origin
            ).first()
            print(f"البحث الاحتياطي: {paper_service}")
            
        # طباعة جميع الخدمات المتاحة للمورد للتشخيص
        all_services = PaperServiceDetails.objects.filter(
            service__supplier=supplier,
            service__is_active=True
        ).values('paper_type', 'sheet_size', 'gsm', 'country_of_origin', 'price_per_sheet')
        print(f"جميع خدمات الورق للمورد {supplier.name}:")
        for service in all_services:
            print(f"  - {service}")
        
        if paper_service:
            # تحضير معلومات السعر
            price_info = {
                'price_per_sheet': float(paper_service.price_per_sheet),
                'currency': 'ريال',  # يمكن تخصيصه حسب النظام
                'supplier_name': supplier.name,
                'paper_type': paper_type.name,
                'sheet_size': dict(PaperServiceDetails.SHEET_SIZE_CHOICES).get(paper_sheet_size, paper_sheet_size),
                'weight': f'{paper_weight} جم',
                'origin': paper_origin,
                'brand': paper_service.brand or 'غير محدد',
                'service_id': paper_service.service.id,
                'last_updated': paper_service.service.updated_at.strftime('%Y-%m-%d') if paper_service.service.updated_at else 'غير محدد'
            }
            
            return JsonResponse({
                'success': True,
                'price_info': price_info,
                'formatted_price': f'{price_info["price_per_sheet"]:.2f} {price_info["currency"]}'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'لا يوجد سعر متاح لهذه المواصفات لدى هذا المورد',
                'suggestion': 'تأكد من أن المورد يوفر هذا النوع من الورق بهذه المواصفات',
                'debug_info': {
                    'searched_for': {
                        'paper_type': paper_type.name,
                        'supplier': supplier.name,
                        'sheet_size': paper_sheet_size,
                        'weight': paper_weight,
                        'origin_id': paper_origin,
                        'origin_name': origin_name
                    },
                    'available_services_count': all_services.count() if 'all_services' in locals() else 0
                }
            })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في جلب سعر الورق: {str(e)}'
        })


@login_required
def debug_paper_services_api(request):
    """
    API للتشخيص - عرض جميع خدمات الورق المتاحة
    """
    try:
        supplier_id = request.GET.get('supplier_id')
        
        if not supplier_id:
            return JsonResponse({
                'success': False,
                'error': 'مطلوب تحديد المورد'
            })
        
        try:
            supplier = Supplier.objects.get(id=supplier_id)
        except Supplier.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'المورد غير موجود'
            })
        
        # جلب جميع خدمات الورق للمورد
        paper_services = PaperServiceDetails.objects.filter(
            service__supplier=supplier,
            service__is_active=True
        ).select_related('service')
        
        services_data = []
        for service in paper_services:
            services_data.append({
                'service_id': service.service.id,
                'service_name': service.service.name,
                'paper_type': service.paper_type,
                'gsm': service.gsm,
                'sheet_size': service.sheet_size,
                'sheet_size_display': dict(PaperServiceDetails.SHEET_SIZE_CHOICES).get(service.sheet_size, service.sheet_size),
                'country_of_origin': service.country_of_origin,
                'brand': service.brand,
                'price_per_sheet': float(service.price_per_sheet),
                'custom_width': float(service.custom_width) if service.custom_width else None,
                'custom_height': float(service.custom_height) if service.custom_height else None,
            })
        
        return JsonResponse({
            'success': True,
            'supplier': {
                'id': supplier.id,
                'name': supplier.name
            },
            'services': services_data,
            'count': len(services_data)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في التشخيص: {str(e)}'
        })


@login_required
def root_cause_analysis_api(request):
    """
    تحليل جذري شامل لمشكلة سعر الورق
    """
    try:
        # البيانات من الطلب
        paper_type_id = request.GET.get('paper_type_id', '2')
        paper_supplier_id = request.GET.get('paper_supplier_id', '3')
        paper_sheet_size = request.GET.get('paper_sheet_size', 'quarter_35x50')
        paper_weight = request.GET.get('paper_weight', '80')
        paper_origin = request.GET.get('paper_origin', '2')
        
        analysis = {
            'request_data': {
                'paper_type_id': paper_type_id,
                'paper_supplier_id': paper_supplier_id,
                'paper_sheet_size': paper_sheet_size,
                'paper_weight': paper_weight,
                'paper_origin': paper_origin
            },
            'database_checks': {},
            'search_attempts': [],
            'final_diagnosis': ''
        }
        
        # 1. فحص نوع الورق
        try:
            from pricing.models import PaperType
            paper_type = PaperType.objects.get(id=paper_type_id)
            analysis['database_checks']['paper_type'] = {
                'found': True,
                'id': paper_type.id,
                'name': paper_type.name,
                'name_lower': paper_type.name.lower()
            }
        except Exception as e:
            analysis['database_checks']['paper_type'] = {
                'found': False,
                'error': str(e)
            }
            
        # 2. فحص المورد
        try:
            supplier = Supplier.objects.get(id=paper_supplier_id)
            analysis['database_checks']['supplier'] = {
                'found': True,
                'id': supplier.id,
                'name': supplier.name
            }
        except Exception as e:
            analysis['database_checks']['supplier'] = {
                'found': False,
                'error': str(e)
            }
            
        # 3. فحص منشأ الورق
        origin_name = paper_origin
        try:
            if paper_origin.isdigit():
                from pricing.models import PaperOrigin
                paper_origin_obj = PaperOrigin.objects.get(id=int(paper_origin))
                origin_name = paper_origin_obj.name
                analysis['database_checks']['paper_origin'] = {
                    'found': True,
                    'id': paper_origin_obj.id,
                    'name': paper_origin_obj.name,
                    'converted_from_id': True
                }
            else:
                analysis['database_checks']['paper_origin'] = {
                    'found': True,
                    'name': paper_origin,
                    'converted_from_id': False
                }
        except Exception as e:
            analysis['database_checks']['paper_origin'] = {
                'found': False,
                'error': str(e),
                'fallback_name': paper_origin
            }
            
        # 4. فحص جميع خدمات الورق للمورد
        all_services = PaperServiceDetails.objects.filter(
            service__supplier_id=paper_supplier_id,
            service__is_active=True
        ).values(
            'service__id', 'service__name', 'paper_type', 'gsm', 
            'sheet_size', 'country_of_origin', 'price_per_sheet', 'brand'
        )
        
        analysis['database_checks']['all_services'] = list(all_services)
        analysis['database_checks']['services_count'] = len(analysis['database_checks']['all_services'])
        
        # 5. محاولات البحث المختلفة
        if analysis['database_checks']['paper_type']['found'] and analysis['database_checks']['supplier']['found']:
            
            # محاولة 1: البحث الدقيق
            search1 = PaperServiceDetails.objects.filter(
                service__supplier_id=paper_supplier_id,
                service__is_active=True,
                paper_type__icontains=analysis['database_checks']['paper_type']['name_lower'],
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight),
                country_of_origin__icontains=origin_name
            ).values('service__name', 'paper_type', 'gsm', 'sheet_size', 'country_of_origin', 'price_per_sheet')
            
            analysis['search_attempts'].append({
                'method': 'البحث الدقيق مع icontains',
                'criteria': {
                    'paper_type__icontains': analysis['database_checks']['paper_type']['name_lower'],
                    'sheet_size': paper_sheet_size,
                    'gsm': int(paper_weight),
                    'country_of_origin__icontains': origin_name
                },
                'results': list(search1),
                'count': len(list(search1))
            })
            
            # محاولة 2: البحث بدون icontains
            search2 = PaperServiceDetails.objects.filter(
                service__supplier_id=paper_supplier_id,
                service__is_active=True,
                paper_type=analysis['database_checks']['paper_type']['name'],
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight),
                country_of_origin=origin_name
            ).values('service__name', 'paper_type', 'gsm', 'sheet_size', 'country_of_origin', 'price_per_sheet')
            
            analysis['search_attempts'].append({
                'method': 'البحث الدقيق بدون icontains',
                'criteria': {
                    'paper_type': analysis['database_checks']['paper_type']['name'],
                    'sheet_size': paper_sheet_size,
                    'gsm': int(paper_weight),
                    'country_of_origin': origin_name
                },
                'results': list(search2),
                'count': len(list(search2))
            })
            
            # محاولة 3: البحث بدون منشأ الورق
            search3 = PaperServiceDetails.objects.filter(
                service__supplier_id=paper_supplier_id,
                service__is_active=True,
                paper_type__icontains=analysis['database_checks']['paper_type']['name_lower'],
                sheet_size=paper_sheet_size,
                gsm=int(paper_weight)
            ).values('service__name', 'paper_type', 'gsm', 'sheet_size', 'country_of_origin', 'price_per_sheet')
            
            analysis['search_attempts'].append({
                'method': 'البحث بدون منشأ الورق',
                'criteria': {
                    'paper_type__icontains': analysis['database_checks']['paper_type']['name_lower'],
                    'sheet_size': paper_sheet_size,
                    'gsm': int(paper_weight)
                },
                'results': list(search3),
                'count': len(list(search3))
            })
        
        # 6. التشخيص النهائي
        successful_searches = [s for s in analysis['search_attempts'] if s['count'] > 0]
        if successful_searches:
            analysis['final_diagnosis'] = f"تم العثور على {len(successful_searches)} طريقة بحث ناجحة"
            analysis['recommended_fix'] = "المشكلة في معايير البحث في الكود الأصلي"
        else:
            analysis['final_diagnosis'] = "لا توجد بيانات تطابق المعايير المطلوبة"
            analysis['recommended_fix'] = "يجب إضافة بيانات جديدة أو تعديل البيانات الموجودة"
        
        return JsonResponse({
            'success': True,
            'analysis': analysis
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'خطأ في التحليل الجذري: {str(e)}'
        })

