from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Sum, Count, F
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from .models import (
    Product, Category, Warehouse, Stock, StockMovement,
    Brand, Unit, ProductImage, ProductVariant, SupplierProductPrice, PriceHistory
)
from .forms import (
    ProductForm, CategoryForm, WarehouseForm, StockMovementForm,
    BrandForm, UnitForm, ProductImageForm, ProductVariantForm,
    ProductSearchForm
)
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils import timezone
import csv
from io import BytesIO
from xhtml2pdf import pisa
from django.template.loader import get_template
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from django.db.models import Avg, Max, Min

# استيراد نماذج المبيعات والمشتريات للتحقق من الارتباطات
try:
    from sale.models import SaleItem, Sale
    from purchase.models import PurchaseItem
except ImportError:
    # تعامل مع حالة عدم وجود التطبيقات
    SaleItem = None
    Sale = None
    PurchaseItem = None


def get_product_sales_statistics(product):
    """
    حساب إحصائيات المبيعات للمنتج (للفترة المالية الحالية)
    """
    if not SaleItem or not Sale:
        return {
            'total_sold_quantity': 0,
            'total_sales_value': 0,
            'total_sales_count': 0,
            'average_sale_price': 0,
            'last_sales': [],
            'top_customers': [],
            'monthly_sales': [],
            'best_selling_month': None,
            'last_sale_date': None,
            'period_name': None,
        }
    
    try:
        # الحصول على الفترة المالية الحالية
        from financial.models import AccountingPeriod
        current_period = AccountingPeriod.objects.filter(status='open').order_by('-start_date').first()
        
        # الحصول على جميع بنود المبيعات للمنتج من الفواتير المؤكدة
        sale_items = SaleItem.objects.filter(
            product=product,
            sale__status='confirmed'
        ).select_related('sale', 'sale__customer')
        
        # تصفية حسب الفترة المالية الحالية إن وجدت
        if current_period:
            sale_items = sale_items.filter(
                sale__date__gte=current_period.start_date,
                sale__date__lte=current_period.end_date
            )
        
        # إحصائيات أساسية
        total_sold_quantity = sale_items.aggregate(Sum('quantity'))['quantity__sum'] or 0
        total_sales_value = sale_items.aggregate(Sum('total'))['total__sum'] or 0
        total_sales_count = sale_items.count()
        average_sale_price = sale_items.aggregate(Avg('unit_price'))['unit_price__avg'] or 0
        
        # آخر 5 مبيعات
        last_sales = sale_items.order_by('-sale__date', '-sale__created_at')[:5]
        
        # أفضل العملاء (حسب الكمية المشتراة)
        top_customers = (
            sale_items.values('sale__customer__name', 'sale__customer__id')
            .annotate(
                total_quantity=Sum('quantity'),
                total_value=Sum('total'),
                sales_count=Count('sale', distinct=True)
            )
            .order_by('-total_quantity')[:5]
        )
        
        # المبيعات الشهرية (آخر 6 شهور بما فيها الشهر الحالي)
        from dateutil.relativedelta import relativedelta
        
        current_date = timezone.now().date()
        monthly_sales = []
        
        for i in range(5, -1, -1):  # من 5 إلى 0 (آخر 6 شهور)
            target_date = current_date - relativedelta(months=i)
            month_start = target_date.replace(day=1)
            
            # آخر يوم في الشهر
            if target_date.month == 12:
                month_end = target_date.replace(year=target_date.year + 1, month=1, day=1)
            else:
                month_end = target_date.replace(month=target_date.month + 1, day=1)
            
            month_data = sale_items.filter(
                sale__date__gte=month_start,
                sale__date__lt=month_end
            ).aggregate(
                quantity=Sum('quantity'),
                value=Sum('total'),
                count=Count('sale', distinct=True)
            )
            
            monthly_sales.append({
                'month': month_start.strftime('%Y-%m'),
                'month_name': month_start.strftime('%B %Y'),
                'quantity': month_data['quantity'] or 0,
                'value': month_data['value'] or 0,
                'count': month_data['count'] or 0,
            })
        
        # أفضل شهر مبيعات وأقصى كمية للرسم البياني
        best_selling_month = max(monthly_sales, key=lambda x: x['quantity']) if monthly_sales else None
        max_monthly_quantity = max([month['quantity'] for month in monthly_sales]) if monthly_sales else 0
        
        # تاريخ آخر بيعة
        last_sale_date = sale_items.aggregate(Max('sale__date'))['sale__date__max']
        
        return {
            'total_sold_quantity': total_sold_quantity,
            'total_sales_value': total_sales_value,
            'total_sales_count': total_sales_count,
            'average_sale_price': average_sale_price,
            'last_sales': last_sales,
            'top_customers': top_customers,
            'monthly_sales': monthly_sales,
            'max_monthly_quantity': max_monthly_quantity,
            'best_selling_month': best_selling_month,
            'last_sale_date': last_sale_date,
            'period_name': current_period.name if current_period else 'جميع الفترات',
            'period_dates': f"{current_period.start_date.strftime('%Y/%m/%d')} - {current_period.end_date.strftime('%Y/%m/%d')}" if current_period else None,
        }
        
    except Exception as e:
        logging.error(f"خطأ في حساب إحصائيات المبيعات للمنتج {product.id}: {e}")
        return {
            'total_sold_quantity': 0,
            'total_sales_value': 0,
            'total_sales_count': 0,
            'average_sale_price': 0,
            'last_sales': [],
            'top_customers': [],
            'monthly_sales': [],
            'max_monthly_quantity': 0,
            'best_selling_month': None,
            'last_sale_date': None,
            'period_name': None,
            'period_dates': None,
        }

logger = logging.getLogger(__name__)

@login_required
def product_list(request):
    """
    عرض قائمة المنتجات
    """
    try:
        # استرجاع كل المنتجات بطريقة بسيطة
        products = Product.objects.select_related('category', 'brand', 'unit').prefetch_related('stocks').all()
        
        # البحث البسيط
        search_query = request.GET.get('search', '')
        if search_query:
            products = products.filter(name__icontains=search_query)
        
        # تطبيق التصفية
        filter_form = ProductSearchForm(request.GET)
        
        # تعريف أعمدة جدول المنتجات
        product_headers = [
            {'key': 'sku', 'label': 'كود المنتج', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_sku.html', 'width': '120px'},
            {'key': 'name', 'label': 'الاسم', 'sortable': True, 'class': 'text-start'},
            {'key': 'category', 'label': 'التصنيف', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_category.html', 'width': '120px'},
            {'key': 'brand.name', 'label': 'النوع', 'sortable': True, 'class': 'text-center', 'width': '120px'},
            {'key': 'sale_price', 'label': 'سعر البيع', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_price.html', 'width': '120px'},
            {'key': 'current_stock', 'label': 'المخزون', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/stock_level.html', 'width': '120px'},
            {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_status.html', 'width': '90px'},
        ]
        
        context = {
            'products': products,
            'filter_form': filter_form,
            'product_headers': product_headers,
            'primary_key': 'id',  # المفتاح الأساسي للجدول
            'page_title': 'قائمة المنتجات',
            'page_icon': 'fas fa-boxes',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المنتجات', 'active': True}
            ],
        }
        
        return render(request, 'product/product_list.html', context)
    except Exception as e:
        # في حالة حدوث أي خطأ، نعرض صفحة بسيطة مع رسالة الخطأ
        messages.error(request, f"حدث خطأ أثناء تحميل المنتجات: {str(e)}")
        return render(request, 'product/product_list.html', {
            'products': Product.objects.none(),
            'filter_form': ProductSearchForm(),
            'page_title': 'قائمة المنتجات - خطأ',
            'page_icon': 'fas fa-exclamation-triangle',
            'breadcrumb_items': [
                {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
                {'title': 'المنتجات', 'active': True}
            ],
            'error_message': str(e)
        })


@login_required
def product_create(request):
    """
    إضافة منتج جديد
    """
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()
            
            # معالجة الصور
            images = request.FILES.getlist('images')
            for image in images:
                ProductImage.objects.create(
                    product=product,
                    image=image,
                    is_primary=not ProductImage.objects.filter(product=product).exists()
                )
            
            messages.success(request, f'تم إضافة المنتج "{product.name}" بنجاح')
            
            if 'save_and_continue' in request.POST:
                return redirect('product:product_create')
            else:
                return redirect('product:product_list')
    else:
        form = ProductForm()
    
    context = {
        'form': form,
        'page_title': 'إضافة منتج جديد',
        'page_icon': 'fas fa-plus-circle',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
            {'title': 'إضافة منتج', 'active': True}
        ],
    }
    
    return render(request, 'product/product_form.html', context)


@login_required
def product_edit(request, pk):
    """
    تعديل منتج
    """
    product = get_object_or_404(Product, pk=pk)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            product = form.save(commit=False)
            product.updated_by = request.user
            product.save()
            
            # معالجة الصور
            images = request.FILES.getlist('images')
            for image in images:
                ProductImage.objects.create(
                    product=product,
                    image=image,
                    is_primary=not ProductImage.objects.filter(product=product).exists()
                )
            
            messages.success(request, f'تم تحديث المنتج "{product.name}" بنجاح')
            return redirect('product:product_list')
    else:
        form = ProductForm(instance=product)
    
    context = {
        'form': form,
        'product': product,
        'title': f'تعديل المنتج: {product.name}',
        'page_title': f'تعديل المنتج: {product.name}',
        'page_icon': 'fas fa-edit',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
            {'title': f'تعديل: {product.name}', 'active': True}
        ],
    }
    
    return render(request, 'product/product_form.html', context)


@login_required
def product_detail(request, pk):
    """
    عرض تفاصيل المنتج
    """
    product = get_object_or_404(
        Product.objects.select_related('category', 'brand', 'unit', 'default_supplier'), 
        pk=pk
    )
    
    # الحصول على المخزون الحالي للمنتج في كل مستودع
    stock_items = Stock.objects.filter(product=product).select_related('warehouse')
    
    # آخر حركات المخزون
    stock_movements = StockMovement.objects.filter(product=product).select_related(
        'warehouse', 'destination_warehouse', 'created_by'
    ).order_by('-timestamp')[:10]
    
    # إجمالي المخزون
    total_stock = stock_items.aggregate(total=Sum('quantity'))['total'] or 0
    
    # أسعار الموردين (مرتبة حسب السعر)
    try:
        supplier_prices = SupplierProductPrice.objects.filter(
            product=product, 
            is_active=True
        ).select_related('supplier').order_by('cost_price', '-is_default')
    except:
        supplier_prices = []
    
    # إحصائيات المبيعات
    sales_stats = get_product_sales_statistics(product)
    
    context = {
        'product': product,
        'stock_items': stock_items,
        'stock_movements': stock_movements,
        'total_stock': total_stock,
        'supplier_prices': supplier_prices,
        'sales_stats': sales_stats,
        'title': product.name,
    }
    
    return render(request, 'product/product_detail.html', context)


@login_required
def product_delete(request, pk):
    """
    حذف منتج
    """
    product = get_object_or_404(Product, pk=pk)
    
    # التحقق من وجود ارتباطات للمنتج
    has_movements = StockMovement.objects.filter(product=product).exists()
    has_sale_items = SaleItem is not None and SaleItem.objects.filter(product=product).exists()
    has_purchase_items = PurchaseItem is not None and PurchaseItem.objects.filter(product=product).exists()
    
    has_dependencies = has_movements or has_sale_items or has_purchase_items
    
    if request.method == 'POST':
        try:
            name = product.name
            
            if has_dependencies:
                # إذا كان المنتج مرتبطًا بسجلات أخرى، قم بإلغاء تنشيطه فقط
                product.is_active = False
                product.save()
                messages.success(request, f'تم إلغاء تنشيط المنتج "{name}" بنجاح. لم يتم حذفه لارتباطه بعمليات سابقة')
            else:
                # إذا لم يكن مرتبطًا بأي سجلات، يمكن حذفه
                product.delete()
                messages.success(request, f'تم حذف المنتج "{name}" بنجاح')
                
            return redirect('product:product_list')
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء معالجة طلب الحذف: {str(e)}')
    
    context = {
        'product': product,
        'title': f'حذف المنتج: {product.name}',
        'has_dependencies': has_dependencies,
        'object': product,  # لاستخدامه في القالب
        'object_name': 'المنتج',  # لاستخدامه في القالب
    }
    
    return render(request, 'product/product_confirm_delete.html', context)


@login_required
def category_list(request):
    """
    عرض قائمة تصنيفات المنتجات
    """
    categories = Category.objects.all()
    
    # بحث
    search_query = request.GET.get('search', '')
    if search_query:
        categories = categories.filter(name__icontains=search_query)
    
    # التصنيفات حسب الحالة
    status = request.GET.get('status', '')
    if status == 'active':
        categories = categories.filter(is_active=True)
    elif status == 'inactive':
        categories = categories.filter(is_active=False)
    
    # إجمالي التصنيفات والتصنيفات النشطة
    total_categories = Category.objects.count()
    active_categories = Category.objects.filter(is_active=True).count()
    
    # التصنيفات الرئيسية (التي ليس لها أب)
    root_categories = categories.filter(parent__isnull=True)
    
    # ترقيم الصفحات
    paginator = Paginator(categories, 30)
    page = request.GET.get('page')
    
    try:
        categories = paginator.page(page)
    except PageNotAnInteger:
        categories = paginator.page(1)
    except EmptyPage:
        categories = paginator.page(paginator.num_pages)
    
    # تعريف أعمدة جدول الفئات
    category_headers = [
        {'key': 'name', 'label': 'اسم الفئة', 'sortable': True, 'class': 'text-start'},
        {'key': 'description', 'label': 'الوصف', 'sortable': True, 'class': 'text-start'},
        {'key': 'parent.name', 'label': 'الفئة الأب', 'sortable': True, 'class': 'text-center', 'width': '120px'},
        {'key': 'products_count', 'label': 'عدد المنتجات', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/products_count.html', 'width': '120px'},
        {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_status.html', 'width': '90px'},
    ]
    
    # أزرار الإجراءات
    category_actions = [
        {'url': 'product:category_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
        {'url': 'product:category_edit', 'icon': 'fa-edit', 'label': 'تعديل', 'class': 'action-edit'},
        {'url': 'product:category_delete', 'icon': 'fa-trash', 'label': 'حذف', 'class': 'action-delete'},
    ]

    context = {
        'categories': categories,
        'category_headers': category_headers,
        'category_actions': category_actions,
        'primary_key': 'id',
        'root_categories': root_categories,
        'total_categories': total_categories,
        'active_categories': active_categories,
        'search_query': search_query,
        'status': status,
        'page_title': 'تصنيفات المنتجات',
        'page_icon': 'fas fa-tags',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
            {'title': 'التصنيفات', 'active': True}
        ],
    }
    
    return render(request, 'product/category_list.html', context)


@login_required
def category_create(request):
    """
    إضافة فئة منتجات جديدة
    """
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'تم إضافة التصنيف "{category.name}" بنجاح')
            return redirect('product:category_list')
    else:
        form = CategoryForm()
    
    context = {
        'form': form,
        'page_title': 'إضافة فئة جديدة',
        'page_icon': 'fas fa-folder-plus',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
            {'title': 'التصنيفات', 'url': reverse('product:category_list'), 'icon': 'fas fa-tags'},
            {'title': 'إضافة فئة', 'active': True}
        ],
    }
    
    return render(request, 'product/category_form.html', context)


@login_required
def category_edit(request, pk):
    """
    تعديل فئة منتجات
    """
    category = get_object_or_404(Category, pk=pk)
    
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'تم تحديث التصنيف "{category.name}" بنجاح')
            return redirect('product:category_list')
    else:
        form = CategoryForm(instance=category)
    
    context = {
        'form': form,
        'category': category,
        'title': f'تعديل التصنيف: {category.name}',
        'object_type': 'فئة',
        'object_list_name': 'التصنيفات',
        'list_url': reverse('product:category_list'),
        'page_icon': 'fas fa-tags',
    }
    
    return render(request, 'product/category_form.html', context)


@login_required
def category_delete(request, pk):
    """
    حذف فئة منتجات
    """
    category = get_object_or_404(Category, pk=pk)
    
    if request.method == 'POST':
        name = category.name
        category.delete()
        messages.success(request, f'تم حذف التصنيف "{name}" بنجاح')
        return redirect('product:category_list')
    
    context = {
        'category': category,
        'title': f'حذف التصنيف: {category.name}',
    }
    
    return render(request, 'product/category_confirm_delete.html', context)


@login_required
def category_detail(request, pk):
    """
    عرض تفاصيل فئة منتجات
    """
    category = get_object_or_404(Category, pk=pk)
    
    # الحصول على المنتجات في هذا التصنيف
    products = Product.objects.filter(category=category).select_related('brand', 'unit')
    
    # التصنيفات الفرعية
    subcategories = Category.objects.filter(parent=category)
    
    context = {
        'category': category,
        'products': products,
        'subcategories': subcategories,
        'title': category.name,
    }
    
    return render(request, 'product/category_detail.html', context)


@login_required
def brand_list(request):
    """
    عرض قائمة العلامات التجارية
    """
    brands = Brand.objects.all()
    
    # البحث البسيط
    search_query = request.GET.get('search', '')
    if search_query:
        brands = brands.filter(name__icontains=search_query)
    
    # تعريف أعمدة جدول العلامات التجارية
    brand_headers = [
        {'key': 'name', 'label': 'اسم العلامة التجارية', 'sortable': True, 'class': 'text-start'},
        {'key': 'description', 'label': 'الوصف', 'sortable': True, 'class': 'text-start'},
        {'key': 'website', 'label': 'الموقع الإلكتروني', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/website_link.html', 'width': '150px'},
        {'key': 'products_count', 'label': 'عدد المنتجات', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/products_count.html', 'width': '120px'},
        {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_status.html', 'width': '90px'},
    ]
    
    # أزرار الإجراءات
    brand_actions = [
        {'url': 'product:brand_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
        {'url': 'product:brand_edit', 'icon': 'fa-edit', 'label': 'تعديل', 'class': 'action-edit'},
        {'url': 'product:brand_delete', 'icon': 'fa-trash', 'label': 'حذف', 'class': 'action-delete'},
    ]

    context = {
        'brands': brands,
        'brand_headers': brand_headers,
        'brand_actions': brand_actions,
        'primary_key': 'id',
        'page_title': 'العلامات التجارية',
        'page_icon': 'fas fa-copyright',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
            {'title': 'العلامات التجارية', 'active': True}
        ],
    }
    
    return render(request, 'product/brand_list.html', context)


@login_required
def brand_create(request):
    """
    إضافة علامة تجارية جديدة
    """
    if request.method == 'POST':
        form = BrandForm(request.POST, request.FILES)
        if form.is_valid():
            brand = form.save()
            messages.success(request, f'تم إضافة النوع "{brand.name}" بنجاح')
            return redirect('product:brand_list')
    else:
        form = BrandForm()
    
    context = {
        'form': form,
        'page_title': 'إضافة علامة تجارية جديدة',
        'page_icon': 'fas fa-copyright',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
            {'title': 'الأنواع', 'url': reverse('product:brand_list'), 'icon': 'fas fa-copyright'},
            {'title': 'إضافة علامة تجارية', 'active': True}
        ],
    }
    
    return render(request, 'product/brand_form.html', context)


@login_required
def brand_edit(request, pk):
    """
    تعديل علامة تجارية
    """
    brand = get_object_or_404(Brand, pk=pk)
    
    if request.method == 'POST':
        form = BrandForm(request.POST, request.FILES, instance=brand)
        if form.is_valid():
            brand = form.save()
            messages.success(request, f'تم تحديث النوع "{brand.name}" بنجاح')
            return redirect('product:brand_list')
    else:
        form = BrandForm(instance=brand)
    
    context = {
        'form': form,
        'brand': brand,
        'title': f'تعديل النوع: {brand.name}',
    }
    
    return render(request, 'product/brand_form.html', context)


@login_required
def brand_delete(request, pk):
    """
    حذف علامة تجارية
    """
    brand = get_object_or_404(Brand, pk=pk)
    
    if request.method == 'POST':
        name = brand.name
        brand.delete()
        messages.success(request, f'تم حذف النوع "{name}" بنجاح')
        return redirect('product:brand_list')
    
    context = {
        'brand': brand,
        'title': f'حذف النوع: {brand.name}',
    }
    
    return render(request, 'product/brand_confirm_delete.html', context)


@login_required
def brand_detail(request, pk):
    """
    عرض تفاصيل علامة تجارية
    """
    brand = get_object_or_404(Brand, pk=pk)
    
    # الحصول على المنتجات لهذا النوع
    products = Product.objects.filter(brand=brand).select_related('category', 'unit')
    
    # تعريف أعمدة جدول المنتجات
    product_headers = [
        {'key': 'name', 'label': 'اسم المنتج', 'sortable': True, 'class': 'text-start'},
        {'key': 'sku', 'label': 'كود المنتج', 'sortable': True, 'class': 'text-center', 'width': '120px'},
        {'key': 'category.name', 'label': 'الفئة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_category.html', 'width': '120px'},
        {'key': 'unit.name', 'label': 'الوحدة', 'sortable': True, 'class': 'text-center', 'width': '100px'},
        {'key': 'selling_price', 'label': 'سعر البيع', 'sortable': True, 'class': 'text-center', 'format': 'currency', 'width': '100px'},
        {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_status.html', 'width': '90px'},
    ]
    
    # أزرار الإجراءات
    product_actions = [
        {'url': 'product:product_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
    ]
    
    context = {
        'brand': brand,
        'products': products,
        'product_headers': product_headers,
        'product_actions': product_actions,
        'primary_key': 'id',
        'title': brand.name,
        'page_title': f'النوع: {brand.name}',
        'page_icon': 'fas fa-copyright',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
            {'title': 'الأنواع', 'url': reverse('product:brand_list'), 'icon': 'fas fa-copyright'},
            {'title': brand.name, 'active': True}
        ],
    }
    
    return render(request, 'product/brand_detail.html', context)


@login_required
def unit_list(request):
    """
    عرض قائمة وحدات القياس
    """
    units = Unit.objects.all()
    
    # البحث البسيط
    search_query = request.GET.get('search', '')
    if search_query:
        units = units.filter(name__icontains=search_query)
    
    # تعريف أعمدة جدول الوحدات
    unit_headers = [
        {'key': 'name', 'label': 'اسم الوحدة', 'sortable': True, 'class': 'text-start'},
        {'key': 'symbol', 'label': 'الرمز', 'sortable': True, 'class': 'text-center', 'width': '100px'},
        {'key': 'description', 'label': 'الوصف', 'sortable': True, 'class': 'text-start'},
        {'key': 'products_count', 'label': 'عدد المنتجات', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/products_count.html', 'width': '120px'},
        {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_status.html', 'width': '90px'},
    ]
    
    # أزرار الإجراءات
    unit_actions = [
        {'url': 'product:unit_create', 'icon': 'fa-plus', 'label': 'إضافة', 'class': 'action-create'},
    ]
    
    context = {
        'units': units,
        'unit_headers': unit_headers,
        'unit_actions': unit_actions,
        'primary_key': 'id',
        'title': 'وحدات القياس',
        'page_title': 'وحدات القياس',
        'page_icon': 'fas fa-balance-scale',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
            {'title': 'وحدات القياس', 'active': True}
        ],
    }
    
    return render(request, 'product/unit_list.html', context)


@login_required
def unit_create(request):
    """
    إضافة وحدة قياس جديدة
    """
    if request.method == 'POST':
        form = UnitForm(request.POST)
        if form.is_valid():
            unit = form.save()
            messages.success(request, f'تم إضافة وحدة القياس "{unit.name}" بنجاح')
            return redirect('product:unit_list')
    else:
        form = UnitForm()
    
    context = {
        'form': form,
        'page_title': 'إضافة وحدة قياس جديدة',
        'page_icon': 'fas fa-ruler',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-boxes'},
            {'title': 'وحدات القياس', 'url': reverse('product:unit_list'), 'icon': 'fas fa-ruler'},
            {'title': 'إضافة وحدة', 'active': True}
        ],
    }
    
    return render(request, 'product/unit_form.html', context)


@login_required
def unit_edit(request, pk):
    """
    تعديل وحدة قياس
    """
    unit = get_object_or_404(Unit, pk=pk)
    
    if request.method == 'POST':
        form = UnitForm(request.POST, instance=unit)
        if form.is_valid():
            unit = form.save()
            messages.success(request, f'تم تحديث وحدة القياس "{unit.name}" بنجاح')
            return redirect('product:unit_list')
    else:
        form = UnitForm(instance=unit)
    
    context = {
        'form': form,
        'unit': unit,
        'title': f'تعديل وحدة القياس: {unit.name}',
    }
    
    return render(request, 'product/unit_form.html', context)


@login_required
def unit_delete(request, pk):
    """
    حذف وحدة قياس
    """
    unit = get_object_or_404(Unit, pk=pk)
    
    if request.method == 'POST':
        name = unit.name
        unit.delete()
        messages.success(request, f'تم حذف وحدة القياس "{name}" بنجاح')
        return redirect('product:unit_list')
    
    context = {
        'unit': unit,
        'title': f'حذف وحدة القياس: {unit.name}',
    }
    
    return render(request, 'product/unit_confirm_delete.html', context)


@login_required
def unit_detail(request, pk):
    """
    عرض تفاصيل وحدة قياس
    """
    unit = get_object_or_404(Unit, pk=pk)
    
    # الحصول على المنتجات التي تستخدم هذه الوحدة
    products = Product.objects.filter(unit=unit).select_related('category', 'brand')
    
    context = {
        'unit': unit,
        'products': products,
        'title': unit.name,
    }
    
    return render(request, 'product/unit_detail.html', context)


@login_required
def warehouse_list(request):
    """
    عرض قائمة المخازن
    """
    warehouses = Warehouse.objects.all().prefetch_related('stocks')
    
    # بحث
    search_query = request.GET.get('search', '')
    if search_query:
        warehouses = warehouses.filter(
            Q(name__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(location__icontains=search_query)
        )
    
    # الحالة
    status = request.GET.get('status', '')
    if status == 'active':
        warehouses = warehouses.filter(is_active=True)
    elif status == 'inactive':
        warehouses = warehouses.filter(is_active=False)
    
    # إحصائيات
    total_warehouses = Warehouse.objects.count()
    active_warehouses = Warehouse.objects.filter(is_active=True).count()
    
    # تعريف أعمدة جدول المستودعات
    warehouse_headers = [
        {'key': 'code', 'label': 'كود المستودع', 'sortable': True, 'class': 'text-center', 'width': '120px'},
        {'key': 'name', 'label': 'اسم المستودع', 'sortable': True, 'class': 'text-start'},
        {'key': 'location', 'label': 'الموقع', 'sortable': True, 'class': 'text-center', 'width': '150px'},
        {'key': 'manager_name', 'label': 'المدير المسؤول', 'sortable': True, 'class': 'text-center', 'width': '120px'},
        {'key': 'capacity', 'label': 'السعة', 'sortable': True, 'class': 'text-center', 'width': '100px'},
        {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_status.html', 'width': '90px'},
    ]
    
    # أزرار الإجراءات
    warehouse_actions = [
        {'url': 'product:warehouse_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
        {'url': 'product:warehouse_edit', 'icon': 'fa-edit', 'label': 'تعديل', 'class': 'action-edit'},
        {'url': 'product:warehouse_delete', 'icon': 'fa-trash', 'label': 'حذف', 'class': 'action-delete'},
    ]
    
    context = {
        'warehouses': warehouses,
        'warehouse_headers': warehouse_headers,
        'warehouse_actions': warehouse_actions,
        'primary_key': 'id',
        'total_warehouses': total_warehouses,
        'active_warehouses': active_warehouses,
        'page_title': 'المستودعات',
        'page_icon': 'fas fa-warehouse',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المخزون', 'url': '#', 'icon': 'fas fa-boxes'},
            {'title': 'المستودعات', 'active': True}
        ],
    }
    
    return render(request, 'product/warehouse_list.html', context)


@login_required
def warehouse_create(request):
    """
    إضافة مخزن جديد
    """
    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid():
            warehouse = form.save()
            messages.success(request, f'تم إضافة المخزن "{warehouse.name}" بنجاح')
            return redirect('product:warehouse_list')
    else:
        form = WarehouseForm()
    
    context = {
        'form': form,
        'page_title': 'إضافة مخزن جديد',
        'page_icon': 'fas fa-warehouse',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المخزون', 'url': '#', 'icon': 'fas fa-boxes'},
            {'title': 'المخازن', 'url': reverse('product:warehouse_list'), 'icon': 'fas fa-warehouse'},
            {'title': 'إضافة مخزن', 'active': True}
        ],
    }
    
    return render(request, 'product/warehouse_form.html', context)


@login_required
def warehouse_edit(request, pk):
    """
    تعديل مخزن
    """
    warehouse = get_object_or_404(Warehouse, pk=pk)
    
    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=warehouse)
        if form.is_valid():
            warehouse = form.save()
            messages.success(request, f'تم تحديث المخزن "{warehouse.name}" بنجاح')
            return redirect('product:warehouse_list')
    else:
        form = WarehouseForm(instance=warehouse)
    
    context = {
        'form': form,
        'warehouse': warehouse,
        'page_title': f'تعديل المخزن: {warehouse.name}',
        'page_icon': 'fas fa-edit',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المخزون', 'url': '#', 'icon': 'fas fa-boxes'},
            {'title': 'المخازن', 'url': reverse('product:warehouse_list'), 'icon': 'fas fa-warehouse'},
            {'title': f'تعديل: {warehouse.name}', 'active': True}
        ],
    }
    
    return render(request, 'product/warehouse_form.html', context)


@login_required
def warehouse_delete(request, pk):
    """
    حذف مخزن مع معالجة الارتباطات
    """
    warehouse = get_object_or_404(Warehouse, pk=pk)
    
    # التحقق من الارتباطات
    dependencies = _check_warehouse_dependencies(warehouse)
    
    if request.method == 'POST':
        action = request.POST.get('action', 'cancel')
        name = warehouse.name
        
        try:
            if action == 'deactivate':
                # إلغاء تنشيط المخزن
                warehouse.is_active = False
                warehouse.save()
                messages.success(request, f'تم إلغاء تنشيط المخزن "{name}" بنجاح. المخزن لا يزال موجود في النظام لكن غير نشط')
                return redirect('product:warehouse_list')
                
            elif action == 'transfer' and dependencies['has_dependencies']:
                # نقل البيانات إلى مخزن آخر
                target_warehouse_id = request.POST.get('target_warehouse')
                if target_warehouse_id:
                    target_warehouse = get_object_or_404(Warehouse, pk=target_warehouse_id)
                    success = _transfer_warehouse_data(warehouse, target_warehouse, request.user)
                    if success:
                        warehouse.delete()
                        messages.success(request, f'تم نقل بيانات المخزن "{name}" إلى "{target_warehouse.name}" وحذف المخزن بنجاح')
                    else:
                        messages.error(request, f'فشل في نقل بيانات المخزن "{name}". يرجى المحاولة مرة أخرى')
                else:
                    messages.error(request, 'يجب اختيار مخزن لنقل البيانات إليه')
                return redirect('product:warehouse_list')
                
            elif action == 'force_delete':
                # حذف قسري (خطير - يحذف جميع البيانات المرتبطة)
                _force_delete_warehouse(warehouse)
                messages.warning(request, f'تم حذف المخزن "{name}" وجميع البيانات المرتبطة به نهائياً')
                return redirect('product:warehouse_list')
                
            elif action == 'delete' and not dependencies['has_dependencies']:
                # حذف عادي إذا لم توجد ارتباطات
                warehouse.delete()
                messages.success(request, f'تم حذف المخزن "{name}" بنجاح')
                return redirect('product:warehouse_list')
            else:
                messages.error(request, 'إجراء غير صالح')
                
        except Exception as e:
            messages.error(request, f'حدث خطأ أثناء معالجة طلب الحذف: {str(e)}')
    
    # الحصول على المخازن الأخرى للنقل
    other_warehouses = Warehouse.objects.filter(is_active=True).exclude(pk=warehouse.pk)
    
    context = {
        'warehouse': warehouse,
        'dependencies': dependencies,
        'other_warehouses': other_warehouses,
        'page_title': f'حذف المخزن: {warehouse.name}',
        'page_icon': 'fas fa-trash-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المخزون', 'url': '#', 'icon': 'fas fa-boxes'},
            {'title': 'المخازن', 'url': reverse('product:warehouse_list'), 'icon': 'fas fa-warehouse'},
            {'title': f'حذف: {warehouse.name}', 'active': True}
        ],
    }
    
    return render(request, 'product/warehouse_confirm_delete.html', context)


@login_required
def warehouse_detail(request, pk):
    """
    عرض تفاصيل المخزن
    """
    warehouse = get_object_or_404(Warehouse, pk=pk)
    
    # الأرصدة المتاحة في المخزن
    stocks = Stock.objects.filter(warehouse=warehouse).select_related(
        'product', 'product__category', 'product__brand', 'product__unit'
    )
    
    # المنتجات المتاحة للإضافة إلى المخزن
    all_products = Product.objects.filter(is_active=True).select_related('category', 'brand', 'unit')
    
    # المخازن الأخرى للتحويل
    other_warehouses = Warehouse.objects.filter(is_active=True).exclude(pk=warehouse.pk)
    
    # آخر حركات المخزون في هذا المخزن
    recent_movements = StockMovement.objects.filter(
        warehouse=warehouse
    ).select_related(
        'product', 'warehouse', 'destination_warehouse', 'created_by'
    ).order_by('-timestamp')[:10]
    
    # إحصائيات المخزون
    total_products = stocks.count()
    in_stock_products = stocks.filter(quantity__gt=0).count()
    low_stock_products = stocks.filter(
        quantity__gt=0,
        quantity__lt=F('product__min_stock')
    ).count()
    out_of_stock_products = stocks.filter(quantity__lte=0).count()
    
    # إضافة حالة المخزون لكل منتج
    for stock in stocks:
        if stock.quantity <= 0:
            stock.status = 'نفد'
            stock.status_class = 'danger'
        elif stock.quantity < stock.product.min_stock:
            stock.status = 'منخفض'
            stock.status_class = 'warning'
        else:
            stock.status = 'متوفر'
            stock.status_class = 'success'
    
    # إعداد headers للجدول الموحد - تعديل للعمل مع Stock objects
    stock_headers = [
        {'key': 'product.sku', 'label': 'كود المنتج', 'sortable': True},
        {'key': 'product.name', 'label': 'اسم المنتج', 'sortable': True},
        {'key': 'product.category.name', 'label': 'الفئة', 'sortable': True},
        {'key': 'quantity', 'label': 'الكمية', 'sortable': True, 'format': 'number'},
        {'key': 'product.unit.name', 'label': 'الوحدة', 'sortable': False},
        {'key': 'product.min_stock', 'label': 'الحد الأدنى', 'sortable': True, 'format': 'number'},
        {'key': 'status', 'label': 'الحالة', 'sortable': True, 'format': 'status'},
        {'key': 'updated_at', 'label': 'آخر تحديث', 'sortable': True, 'format': 'datetime'},
    ]
    
    # إعداد action buttons (معطلة مؤقتاً لأن الروابط غير جاهزة)
    stock_action_buttons = []
    
    context = {
        'warehouse': warehouse,
        'stocks': stocks,
        'stock_headers': stock_headers,
        'stock_action_buttons': stock_action_buttons,
        'primary_key': 'id',
        'all_products': all_products,
        'other_warehouses': other_warehouses,
        'recent_movements': recent_movements,
        'total_products': total_products,
        'in_stock_products': in_stock_products,
        'low_stock_products': low_stock_products,
        'out_of_stock_products': out_of_stock_products,
        'page_title': f'تفاصيل المخزن: {warehouse.name}',
        'page_icon': 'fas fa-warehouse',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المخزون', 'url': '#', 'icon': 'fas fa-boxes'},
            {'title': 'المخازن', 'url': reverse('product:warehouse_list'), 'icon': 'fas fa-warehouse'},
            {'title': warehouse.name, 'active': True}
        ],
    }
    
    return render(request, 'product/warehouse_detail.html', context)


@login_required
def stock_list(request):
    """
    عرض قائمة المخزون
    """
    stocks = Stock.objects.all().select_related(
        'product', 'product__category', 'product__brand', 'product__unit',
        'warehouse'
    )
    
    # فلترة حسب المخزن
    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        stocks = stocks.filter(warehouse_id=warehouse_id)
    
    # فلترة حسب المنتج
    product_id = request.GET.get('product')
    if product_id:
        stocks = stocks.filter(product_id=product_id)
    
    # فلترة حسب الكمية
    stock_status = request.GET.get('stock_status')
    if stock_status == 'in_stock':
        stocks = stocks.filter(quantity__gt=0)
    elif stock_status == 'out_of_stock':
        stocks = stocks.filter(quantity__lte=0)
    elif stock_status == 'low_stock':
        stocks = stocks.filter(
            quantity__gt=0,
            quantity__lt=F('product__min_stock')
        )
    
    # المخازن والمنتجات لعناصر التصفية
    warehouses = Warehouse.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True).select_related('category')
    
    # ترقيم الصفحات
    paginator = Paginator(stocks, 20)
    page = request.GET.get('page')
    try:
        stocks = paginator.page(page)
    except PageNotAnInteger:
        stocks = paginator.page(1)
    except EmptyPage:
        stocks = paginator.page(paginator.num_pages)
    
    # تعريف أعمدة جدول المخزون
    stock_headers = [
        {'key': 'product.name', 'label': 'المنتج', 'sortable': True, 'class': 'text-start'},
        {'key': 'product.category.name', 'label': 'الفئة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/product_category.html', 'width': '120px'},
        {'key': 'warehouse.name', 'label': 'المستودع', 'sortable': True, 'class': 'text-center', 'width': '120px'},
        {'key': 'quantity', 'label': 'الكمية المتاحة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/stock_quantity.html', 'width': '120px'},
        {'key': 'reserved_quantity', 'label': 'الكمية المحجوزة', 'sortable': True, 'class': 'text-center', 'width': '120px'},
        {'key': 'updated_at', 'label': 'آخر تحديث', 'sortable': True, 'class': 'text-center', 'format': 'datetime_12h', 'width': '150px'},
    ]
    
    # أزرار الإجراءات
    stock_actions = [
        {'url': 'product:stock_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
    ]

    context = {
        'stocks': stocks,
        'stock_headers': stock_headers,
        'stock_actions': stock_actions,
        'primary_key': 'id',
        'warehouses': warehouses,
        'products': products,
        'warehouse_id': warehouse_id,
        'product_id': product_id,
        'stock_status': stock_status,
        'page_title': 'جرد المخزون',
        'page_icon': 'fas fa-clipboard-list',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المخزون', 'url': '#', 'icon': 'fas fa-boxes'},
            {'title': 'جرد المخزون', 'active': True}
        ],
    }
    
    return render(request, 'product/stock_list.html', context)


@login_required
def stock_detail(request, pk):
    """
    عرض تفاصيل المخزون
    """
    stock = get_object_or_404(Stock, pk=pk)
    
    # حركات المخزون
    movements = StockMovement.objects.filter(
        product=stock.product,
        warehouse=stock.warehouse
    ).order_by('-timestamp')
    
    context = {
        'stock': stock,
        'movements': movements,
        'title': f'تفاصيل المخزون: {stock.product.name}',
    }
    
    return render(request, 'product/stock_detail.html', context)


@login_required
def stock_adjust(request, pk):
    """
    تسوية المخزون
    """
    stock = get_object_or_404(Stock, pk=pk)
    
    if request.method == 'POST':
        quantity = request.POST.get('quantity', 0)
        notes = request.POST.get('notes', '')
        
        # إنشاء حركة تسوية
        StockMovement.objects.create(
            product=stock.product,
            warehouse=stock.warehouse,
            movement_type='adjustment',
            quantity=abs(Decimal(quantity)),
            notes=notes,
            created_by=request.user
        )
        
        # تحديث المخزون
        stock.quantity = Decimal(quantity)
        stock.save()
        
        messages.success(request, f'تم تسوية المخزون بنجاح')
        return redirect('product:stock_detail', pk=stock.pk)
    
    context = {
        'stock': stock,
        'title': f'تسوية المخزون: {stock.product.name}',
    }
    
    return render(request, 'product/stock_adjust.html', context)


@login_required
def stock_movement_list(request):
    """
    عرض قائمة حركات المخزون
    """
    movements = StockMovement.objects.all().select_related(
        'product', 'warehouse', 'destination_warehouse', 'created_by'
    ).order_by('-timestamp')
    
    # تصفية حسب البحث
    search_query = request.GET.get('search', '')
    if search_query:
        movements = movements.filter(
            Q(reference__icontains=search_query) |
            Q(product__name__icontains=search_query)
        )
    
    # تصفية حسب المخزن
    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        movements = movements.filter(
            Q(warehouse_id=warehouse_id) | Q(destination_warehouse_id=warehouse_id)
        )
    
    # تصفية حسب المنتج
    product_id = request.GET.get('product')
    if product_id:
        movements = movements.filter(product_id=product_id)
    
    # تصفية حسب نوع الحركة
    movement_type = request.GET.get('movement_type')
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    
    # تصفية حسب التاريخ
    date_from = request.GET.get('date_from')
    if date_from:
        movements = movements.filter(timestamp__date__gte=date_from)
    
    date_to = request.GET.get('date_to')
    if date_to:
        movements = movements.filter(timestamp__date__lte=date_to)
    
    # إحصائيات
    total_movements = movements.count()
    total_quantity = movements.aggregate(total=Sum('quantity'))['total'] or 0
    
    # عدد الحركات حسب نوعها
    in_movements = movements.filter(movement_type='in').count()
    out_movements = movements.filter(movement_type='out').count()
    transfer_movements = movements.filter(movement_type='transfer').count()
    adjustment_movements = movements.filter(movement_type='adjustment').count()
    
    # كل المخازن والمنتجات لقائمة الاختيار
    warehouses = Warehouse.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True).select_related('category', 'brand')
    
    # ترقيم الصفحات
    paginator = Paginator(movements, 30)
    page = request.GET.get('page')
    try:
        movements = paginator.page(page)
    except PageNotAnInteger:
        movements = paginator.page(1)
    except EmptyPage:
        movements = paginator.page(paginator.num_pages)
    
    # تعريف أعمدة جدول حركات المخزون
    movement_headers = [
        {'key': 'id', 'label': '#', 'sortable': True, 'class': 'text-center', 'width': '50px'},
        {'key': 'product.name', 'label': 'المنتج', 'sortable': True, 'class': 'text-start'},
        {'key': 'movement_type', 'label': 'نوع الحركة', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/movement_type.html', 'width': '120px'},
        {'key': 'quantity', 'label': 'الكمية', 'sortable': True, 'class': 'text-center', 'width': '80px'},
        {'key': 'warehouse.name', 'label': 'المخزن', 'sortable': True, 'class': 'text-center', 'width': '120px'},
        {'key': 'timestamp', 'label': 'التاريخ والوقت', 'sortable': True, 'class': 'text-center', 'format': 'datetime_12h', 'width': '150px'},
    ]
    
    # أزرار الإجراءات
    movement_actions = [
        {'url': 'product:stock_movement_detail', 'icon': 'fa-eye', 'label': 'عرض', 'class': 'action-view'},
    ]

    context = {
        'movements': movements,
        'movement_headers': movement_headers,
        'movement_actions': movement_actions,
        'primary_key': 'id',
        'warehouses': warehouses,
        'products': products,
        'total_movements': total_movements,
        'total_quantity': total_quantity,
        'in_movements': in_movements,
        'out_movements': out_movements,
        'transfer_movements': transfer_movements,
        'adjustment_movements': adjustment_movements,
        'page_title': 'حركات المخزون',
        'page_icon': 'fas fa-exchange-alt',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المخزون', 'url': '#', 'icon': 'fas fa-boxes'},
            {'title': 'حركات المخزون', 'active': True}
        ],
    }
    
    return render(request, 'product/stock_movement_list.html', context)


@login_required
def stock_movement_create(request):
    """
    إضافة حركة مخزون جديدة
    """
    if request.method == 'POST':
        form = StockMovementForm(request.POST)
        if form.is_valid():
            movement = form.save(commit=False)
            movement.created_by = request.user
            # تعيين نوع المستند للحركات اليدوية
            movement.document_type = 'other'
            movement.save()
            
            messages.success(request, f'تم إضافة حركة المخزون بنجاح')
            return redirect('product:stock_movement_list')
    else:
        form = StockMovementForm()
    
    context = {
        'form': form,
        'title': 'إضافة حركة مخزون جديدة',
    }
    
    return render(request, 'product/stock_movement_form.html', context)


@login_required
def stock_movement_detail(request, pk):
    """
    عرض تفاصيل حركة المخزون
    """
    movement = get_object_or_404(StockMovement.objects.select_related(
        'product', 'product__category', 'product__brand', 'product__unit',
        'warehouse', 'destination_warehouse', 'created_by'
    ), pk=pk)
    
    # حساب المخزون قبل وبعد الحركة
    if movement.movement_type in ['in', 'transfer_in']:
        previous_stock = movement.quantity_before
        current_stock = movement.quantity_after
    elif movement.movement_type in ['out', 'transfer_out']:
        previous_stock = movement.quantity_before
        current_stock = movement.quantity_after
    else:  # adjustment
        previous_stock = movement.quantity_before
        current_stock = movement.quantity_after
    
    # حركات متعلقة بنفس المنتج في نفس المخزن
    related_movements = StockMovement.objects.filter(
        product=movement.product,
        warehouse=movement.warehouse
    ).select_related(
        'product', 'warehouse', 'destination_warehouse', 'created_by'
    ).order_by('-timestamp')[:10]
    
    context = {
        'movement': movement,
        'previous_stock': previous_stock,
        'current_stock': current_stock,
        'related_movements': related_movements,
        'title': _('تفاصيل حركة المخزون'),
    }
    
    return render(request, 'product/stock_movement_detail.html', context)


@login_required
def stock_movement_delete(request, pk):
    """
    حذف حركة مخزون
    """
    movement = get_object_or_404(StockMovement, pk=pk)
    
    # جمع معلومات العناصر المرتبطة بهذه الحركة
    related_objects = {}
    
    if request.method == 'POST':
        # استرجاع معلومات المخزن والمنتج قبل الحذف
        warehouse = movement.warehouse
        product = movement.product
        
        # الغاء تأثير حركة المخزون
        if movement.movement_type == 'in':
            # إذا كانت حركة إضافة، نقوم بخصم الكمية
            stock = Stock.objects.get(warehouse=warehouse, product=product)
            stock.quantity -= Decimal(movement.quantity)
            stock.save()
        elif movement.movement_type == 'out':
            # إذا كانت حركة سحب، نقوم بإضافة الكمية
            stock = Stock.objects.get(warehouse=warehouse, product=product)
            stock.quantity += Decimal(movement.quantity)
            stock.save()
        elif movement.movement_type == 'transfer' and movement.destination_warehouse:
            # إذا كانت حركة تحويل، نقوم بعكس التحويل
            source_stock = Stock.objects.get(warehouse=warehouse, product=product)
            dest_stock = Stock.objects.get(warehouse=movement.destination_warehouse, product=product)
            
            source_stock.quantity += Decimal(movement.quantity)
            dest_stock.quantity -= Decimal(movement.quantity)
            
            source_stock.save()
            dest_stock.save()
        
        # حذف حركة المخزون
        movement.delete()
        
        messages.success(request, _('تم حذف حركة المخزون بنجاح'))
        return redirect('product:stock_movement_list')
    
    context = {
        'object': movement,
        'related_objects': related_objects,
        'back_url': reverse('product:stock_movement_list'),
        'title': _('حذف حركة المخزون'),
    }
    
    return render(request, 'product/stock_movement_confirm_delete.html', context)


@login_required
@require_POST
def add_stock_movement(request):
    """
    واجهة برمجة لإضافة حركة مخزون (إضافة/سحب/تعديل/تحويل)
    
    معلمات الطلب:
    - product_id: معرف المنتج
    - warehouse_id: معرف المخزن
    - movement_type: نوع الحركة (in, out, adjustment, transfer)
    - quantity: الكمية
    - destination_warehouse: معرف المخزن المستلم (للتحويل فقط)
    - reference_number: رقم المرجع (اختياري)
    - notes: ملاحظات (اختياري)
    
    الاستجابة:
    - success: حالة النجاح (true/false)
    - message: رسالة نجاح أو خطأ
    - movement_id: معرف حركة المخزون الجديدة (في حالة النجاح)
    - current_stock: المخزون الحالي بعد التحديث (في حالة النجاح)
    """
    try:
        # التحقق من وجود المعلمات الأساسية
        product_id = request.POST.get('product_id') or request.POST.get('product')
        warehouse_id = request.POST.get('warehouse_id')
        movement_type = request.POST.get('movement_type')
        quantity = request.POST.get('quantity')
        
        # التحقق من وجود جميع المعلمات المطلوبة
        if not all([product_id, warehouse_id, movement_type, quantity]):
            return JsonResponse({
                'success': False, 
                'error': _('جميع الحقول مطلوبة: product_id, warehouse_id, movement_type, quantity')
            })
        
        # التحقق من صحة البيانات
        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'error': _('المنتج غير موجود')
            })
            
        try:
            warehouse = Warehouse.objects.get(pk=warehouse_id)
        except Warehouse.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'error': _('المخزن غير موجود')
            })
        
        # التحقق من صحة الكمية
        try:
            quantity = Decimal(quantity)
            if quantity <= 0:
                return JsonResponse({
                    'success': False, 
                    'error': _('يجب أن تكون الكمية أكبر من صفر')
                })
        except ValueError:
            return JsonResponse({
                'success': False, 
                'error': _('الكمية يجب أن تكون رقمًا صحيحًا')
            })
        
        # التحقق من نوع الحركة
        if movement_type not in ['in', 'out', 'adjustment', 'transfer']:
            return JsonResponse({
                'success': False, 
                'error': _('نوع الحركة غير صحيح. القيم المقبولة: in, out, adjustment, transfer')
            })
        
        # الحصول على المخزون الحالي أو إنشاء سجل جديد
        stock, created = Stock.objects.get_or_create(
            product=product,
            warehouse=warehouse,
            defaults={'quantity': 0}
        )
        
        # حفظ المخزون الحالي قبل التعديل
        current_stock = stock.quantity
        
        # تنفيذ عملية المخزون
        if movement_type == 'in':
            # إضافة مخزون
            stock.quantity += Decimal(quantity)
            message = _('تمت إضافة {} وحدة من {} إلى المخزون').format(quantity, product.name)
            
        elif movement_type == 'out':
            # سحب مخزون
            if stock.quantity < Decimal(quantity):
                return JsonResponse({
                    'success': False, 
                    'error': _('الكمية غير كافية في المخزون. المتاح حالياً: {}').format(stock.quantity)
                })
            
            stock.quantity -= Decimal(quantity)
            message = _('تم سحب {} وحدة من {} من المخزون').format(quantity, product.name)
            
        elif movement_type == 'adjustment':
            # تعديل المخزون (تعيين قيمة محددة)
            old_quantity = stock.quantity
            stock.quantity = Decimal(quantity)
            message = _('تم تعديل مخزون {} من {} إلى {}').format(
                product.name, old_quantity, quantity
            )
            
        elif movement_type == 'transfer':
            # تحويل مخزون بين المخازن
            destination_warehouse_id = request.POST.get('destination_warehouse')
            
            if not destination_warehouse_id:
                return JsonResponse({
                    'success': False, 
                    'error': _('يجب تحديد المخزن المستلم للتحويل')
                })
            
            if destination_warehouse_id == warehouse_id:
                return JsonResponse({
                    'success': False, 
                    'error': _('لا يمكن التحويل إلى نفس المخزن')
                })
            
            try:
                destination_warehouse = Warehouse.objects.get(pk=destination_warehouse_id)
            except Warehouse.DoesNotExist:
                return JsonResponse({
                    'success': False, 
                    'error': _('المخزن المستلم غير موجود')
                })
            
            # التحقق من كفاية المخزون
            if stock.quantity < Decimal(quantity):
                return JsonResponse({
                    'success': False, 
                    'error': _('الكمية غير كافية للتحويل. المتاح حالياً: {}').format(stock.quantity)
                })
                
            # خصم من المخزن المصدر
            stock.quantity -= Decimal(quantity)
            
            # إضافة إلى المخزن المستلم
            dest_stock, created = Stock.objects.get_or_create(
                product=product,
                warehouse=destination_warehouse,
                defaults={'quantity': Decimal('0')}
            )
            
            dest_before = dest_stock.quantity
            dest_stock.quantity += Decimal(quantity)
            dest_stock.save()
            
            message = _('تم تحويل {} وحدة من {} من {} إلى {}').format(
                quantity, product.name, warehouse.name, destination_warehouse.name
            )
        
        # حفظ التغييرات
        stock.save()
        
        # إنشاء سجل حركة المخزون
        movement = StockMovement.objects.create(
            product=product,
            warehouse=warehouse,
            movement_type=movement_type,
            quantity=quantity,
            quantity_before=current_stock,
            quantity_after=stock.quantity,
            reference_number=request.POST.get('reference_number', ''),
            notes=request.POST.get('notes', ''),
            created_by=request.user
        )
        
        # إذا كانت حركة تحويل، حفظ المخزن المستلم
        if movement_type == 'transfer' and 'destination_warehouse' in locals():
            movement.destination_warehouse = destination_warehouse
            movement.save()
            
            # إنشاء سجل حركة للمخزن المستلم
            StockMovement.objects.create(
                product=product,
                warehouse=destination_warehouse,
                movement_type='transfer_in',
                quantity=quantity,
                quantity_before=dest_before,
                quantity_after=dest_stock.quantity,
                reference_number=request.POST.get('reference_number', ''),
                notes=_('تحويل من مخزن {}').format(warehouse.name),
                created_by=request.user
            )
        
        # تسجيل الحركة في سجل النظام
        logger.info(
            'Stock movement created: %s %s %s units of %s in %s by %s',
            movement_type, 
            quantity, 
            product.name,
            warehouse.name,
            request.user.username
        )
        
        return JsonResponse({
            'success': True, 
            'message': message,
            'movement_id': movement.id,
            'current_stock': stock.quantity
        })
        
    except ValidationError as e:
        logger.warning('Validation error in add_stock_movement: %s', str(e))
        return JsonResponse({
            'success': False, 
            'error': 'خطأ في العملية'
        })
    except Exception as e:
        # سجل الخطأ ولكن لا ترسل تفاصيل للمستخدم
        logger.error('Error in add_stock_movement: %s', str(e), exc_info=True)
        return JsonResponse({
            'success': False, 
            'error': _('حدث خطأ أثناء تنفيذ العملية. يرجى المحاولة مرة أخرى لاحقًا.')
        })


@login_required
def export_stock_movements(request):
    """
    تصدير حركات المخزون كملف CSV أو PDF
    """
    # الحصول على الحركات مع تطبيق الفلاتر
    movements = StockMovement.objects.all().select_related(
        'product', 'product__category', 'product__brand',
        'warehouse', 'destination_warehouse', 'created_by'
    ).order_by('-timestamp')
    
    # تطبيق الفلاتر
    warehouse_id = request.GET.get('warehouse')
    if warehouse_id:
        movements = movements.filter(
            Q(warehouse_id=warehouse_id) | 
            Q(destination_warehouse_id=warehouse_id)
        )
    
    product_id = request.GET.get('product')
    if product_id:
        movements = movements.filter(product_id=product_id)
    
    movement_type = request.GET.get('movement_type')
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    
    date_from = request.GET.get('date_from')
    if date_from:
        movements = movements.filter(timestamp__date__gte=date_from)
    
    date_to = request.GET.get('date_to')
    if date_to:
        movements = movements.filter(timestamp__date__lte=date_to)
    
    # تحديد نوع التصدير
    export_format = request.GET.get('format', 'csv')
    
    if export_format == 'csv':
        # تصدير CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="stock_movements.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'المنتج', 'المخزن', 'النوع', 'الكمية', 
            'المخزون قبل', 'المخزون بعد', 'المخزن المستلم',
            'رقم المرجع', 'ملاحظات', 'التاريخ'
        ])
        
        for movement in movements:
            writer.writerow([
                movement.id,
                movement.product.name,
                movement.warehouse.name,
                movement.get_movement_type_display(),
                movement.quantity,
                movement.quantity_before,
                movement.quantity_after,
                movement.destination_warehouse.name if movement.destination_warehouse else '',
                movement.reference_number,
                movement.notes,
                movement.timestamp.strftime('%Y-%m-%d %H:%M')
            ])
        
        return response
    
    elif export_format == 'pdf':
        # تصدير PDF
        # هنا سنستخدم HTML كوسيط لإنشاء PDF
        template = get_template('product/exports/stock_movements_pdf.html')
        context = {
            'movements': movements,
            'today': timezone.now(),
            'request': request,
        }
        html = template.render(context)
        
        # إنشاء PDF
        result = BytesIO()
        pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
        
        if not pdf.err:
            response = HttpResponse(result.getvalue(), content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="stock_movements.pdf"'
            return response
        
        return HttpResponse('Error generating PDF', status=400)
    
    else:
        # نوع تصدير غير معروف
        return HttpResponse('Invalid export format', status=400)


@login_required
def export_warehouse_inventory_all(request):
    """
    تصدير المخزون من جميع المخازن أو حسب التصفية
    """
    # جلب المخزون
    stocks = Stock.objects.all().select_related('product', 'product__category', 'warehouse')
    
    # التصفية حسب المخزن إذا تم تحديده
    warehouse_id = request.GET.get('warehouse')
    if warehouse_id and warehouse_id.isdigit():
        stocks = stocks.filter(warehouse_id=warehouse_id)
    
    # التصفية حسب المنتج إذا تم تحديده
    product_id = request.GET.get('product')
    if product_id and product_id.isdigit():
        stocks = stocks.filter(product_id=product_id)
    
    # التصفية حسب الكمية
    min_quantity = request.GET.get('min_quantity')
    if min_quantity and min_quantity.isdigit():
        stocks = stocks.filter(quantity__gte=min_quantity)
    
    max_quantity = request.GET.get('max_quantity')
    if max_quantity and max_quantity.isdigit():
        stocks = stocks.filter(quantity__lte=max_quantity)
    
    # تحديد نوع التصدير
    export_format = request.GET.get('format', 'csv')
    
    if export_format == 'csv':
        # تصدير CSV
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="inventory.csv"'
        
        writer = csv.writer(response)
        writer.writerow([
            'رقم المنتج', 'اسم المنتج', 'كود المنتج', 'المخزن', 'التصنيف', 'الكمية', 
            'الحد الأدنى', 'الحد الأقصى', 'حالة المخزون'
        ])
        
        for stock in stocks:
            # تحديد حالة المخزون
            if stock.quantity <= 0:
                status = 'نفذ من المخزون'
            elif stock.quantity < stock.product.min_stock:
                status = 'مخزون منخفض'
            elif stock.quantity > stock.product.max_stock:
                status = 'مخزون زائد'
            else:
                status = 'مخزون جيد'
            
            writer.writerow([
                stock.product.id,
                stock.product.name,
                stock.product.sku,
                stock.warehouse.name,
                stock.product.category.name if stock.product.category else '',
                stock.quantity,
                stock.product.min_stock,
                stock.product.max_stock,
                status
            ])
        
        return response
    
    # يمكن إضافة تصدير PDF هنا لاحقاً
    return redirect('product:stock_list')


@login_required
def export_warehouse_inventory(request, warehouse_id=None):
    """
    تصدير مخزون مخزن معين
    """
    # إذا لم يتم تحديد رقم المخزن، نحاول جلبه من الاستعلام
    if warehouse_id is None:
        warehouse_id = request.GET.get('warehouse')
        if not warehouse_id or not warehouse_id.isdigit():
            # إذا لم يتم تحديد مخزن، نستخدم دالة تصدير كل المخزون
            return export_warehouse_inventory_all(request)
    
    warehouse = get_object_or_404(Warehouse, pk=warehouse_id)
    stocks = Stock.objects.filter(warehouse=warehouse).select_related('product')
    
    # التصفية حسب المنتج إذا تم تحديده
    product_id = request.GET.get('product')
    if product_id and product_id.isdigit():
        stocks = stocks.filter(product_id=product_id)
    
    # تصدير CSV
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{warehouse.name}_inventory.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'رقم المنتج', 'اسم المنتج', 'كود المنتج', 'التصنيف', 'الكمية', 
        'الحد الأدنى', 'الحد الأقصى', 'حالة المخزون'
    ])
    
    for stock in stocks:
        # تحديد حالة المخزون
        if stock.quantity <= 0:
            status = 'نفذ من المخزون'
        elif stock.quantity < stock.product.min_stock:
            status = 'مخزون منخفض'
        elif stock.quantity > stock.product.max_stock:
            status = 'مخزون زائد'
        else:
            status = 'مخزون جيد'
        
        writer.writerow([
            stock.product.id,
            stock.product.name,
            stock.product.sku,
            stock.product.category.name if stock.product.category else '',
            stock.quantity,
            stock.product.min_stock,
            stock.product.max_stock,
            status
        ])
    
    return response


@login_required
def low_stock_products(request):
    """
    عرض المنتجات ذات المخزون المنخفض
    """
    # الحصول على المنتجات ذات المخزون المنخفض
    low_stock_items = Stock.objects.filter(
        quantity__gt=0,
        quantity__lt=F('product__min_stock')
    ).select_related(
        'product', 'product__category', 'product__brand', 'product__unit',
        'warehouse'
    )
    
    context = {
        'low_stock_items': low_stock_items,
        'title': _('المنتجات ذات المخزون المنخفض'),
    }
    
    return render(request, 'product/low_stock.html', context)


@login_required
def add_product_image(request):
    """
    إضافة صورة منتج من خلال AJAX
    """
    if request.method == 'POST':
        try:
            product_id = request.POST.get('product_id')
            image = request.FILES.get('image')
            alt_text = request.POST.get('alt_text', '')
            is_primary = request.POST.get('is_primary') == 'on'
            
            if not product_id or not image:
                return JsonResponse({'success': False, 'error': _('بيانات غير كاملة')})
            
            # التأكد من وجود المنتج
            product = get_object_or_404(Product, pk=product_id)
            
            # إذا كانت الصورة الأساسية، نقوم بإلغاء تحديد الصور الأساسية الأخرى
            if is_primary:
                ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)
            
            # إنشاء صورة جديدة
            product_image = ProductImage.objects.create(
                product=product,
                image=image,
                alt_text=alt_text,
                is_primary=is_primary
            )
            
            return JsonResponse({
                'success': True,
                'id': product_image.id,
                'url': product_image.image.url
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': 'خطأ في العملية'})
            
    return JsonResponse({'success': False, 'error': _('طلب غير صالح')})


@login_required
@csrf_exempt
def delete_product_image(request, pk):
    """
    حذف صورة منتج
    """
    if request.method == 'POST':
        try:
            image = get_object_or_404(ProductImage, pk=pk)
            product_id = image.product.id
            image.delete()
            
            # إذا تم حذف الصورة الرئيسية، اجعل أول صورة أخرى رئيسية
            if image.is_primary:
                first_image = ProductImage.objects.filter(product_id=product_id).first()
                if first_image:
                    first_image.is_primary = True
                    first_image.save()
            
            return JsonResponse({
                'success': True, 
                'message': 'تم حذف الصورة بنجاح'
            })
        except ProductImage.DoesNotExist:
            return JsonResponse({
                'success': False, 
                'error': 'الصورة غير موجودة'
            })
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f'Error in views.py: {str(e)}', exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'حدث خطأ: خطأ في العملية'
            })
    
    # دعم GET للاختبار
    elif request.method == 'GET':
        return JsonResponse({
            'success': False, 
            'error': 'يجب استخدام POST لحذف الصورة'
        })
            
    return JsonResponse({
        'success': False, 
        'error': 'طريقة طلب غير مدعومة'
    })


@login_required
def get_stock_by_warehouse(request):
    """
    API للحصول على المخزون المتاح في مستودع معين
    """
    warehouse_id = request.GET.get('warehouse')
    
    # تسجيل معلومات الطلب للتشخيص
    logger.info(f"طلب API للمخزون - المستودع: {warehouse_id}, الطريقة: {request.method}")
    
    if not warehouse_id:
        logger.warning("API المخزون: لم يتم توفير معرف المستودع")
        return JsonResponse({}, status=400)
    
    try:
        # التحقق من وجود المستودع
        warehouse = get_object_or_404(Warehouse, id=warehouse_id)
        
        # الحصول على المخزون المتاح في المستودع المحدد
        stocks = Stock.objects.filter(warehouse=warehouse).values('product_id', 'quantity')
        
        # بناء قاموس به المنتجات والمخزون المتاح
        stock_data = {}
        for stock in stocks:
            stock_data[str(stock['product_id'])] = stock['quantity']
        
        logger.info(f"API المخزون: تم استرجاع {len(stock_data)} من المنتجات للمستودع {warehouse.name}")
        return JsonResponse(stock_data)
    
    except Exception as e:
        logger.error(f"خطأ في API المخزون: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


# دوال مساعدة لحذف المخزن
def _check_warehouse_dependencies(warehouse):
    """
    التحقق من الارتباطات الموجودة للمخزن
    """
    dependencies = {
        'has_dependencies': False,
        'stock_movements': 0,
        'sales': 0,
        'purchases': 0,
        'stocks': 0,
        'details': []
    }
    
    try:
        # حركات المخزون
        stock_movements = StockMovement.objects.filter(warehouse=warehouse)
        dependencies['stock_movements'] = stock_movements.count()
        if dependencies['stock_movements'] > 0:
            dependencies['has_dependencies'] = True
            dependencies['details'].append(f"{dependencies['stock_movements']} حركة مخزون")
        
        # المبيعات
        try:
            from sale.models import Sale
            sales = Sale.objects.filter(warehouse=warehouse)
            dependencies['sales'] = sales.count()
            if dependencies['sales'] > 0:
                dependencies['has_dependencies'] = True
                dependencies['details'].append(f"{dependencies['sales']} فاتورة مبيعات")
        except ImportError:
            pass
        
        # المشتريات
        try:
            from purchase.models import Purchase
            purchases = Purchase.objects.filter(warehouse=warehouse)
            dependencies['purchases'] = purchases.count()
            if dependencies['purchases'] > 0:
                dependencies['has_dependencies'] = True
                dependencies['details'].append(f"{dependencies['purchases']} فاتورة مشتريات")
        except ImportError:
            pass
        
        # المخزون الحالي
        stocks = Stock.objects.filter(warehouse=warehouse, quantity__gt=0)
        dependencies['stocks'] = stocks.count()
        if dependencies['stocks'] > 0:
            dependencies['has_dependencies'] = True
            dependencies['details'].append(f"{dependencies['stocks']} منتج بمخزون متاح")
            
    except Exception as e:
        logger.error(f"خطأ في فحص ارتباطات المخزن: {str(e)}")
    
    return dependencies


def _transfer_warehouse_data(source_warehouse, target_warehouse, user):
    """
    نقل بيانات المخزن من مخزن إلى آخر
    """
    try:
        from django.db import transaction
        
        with transaction.atomic():
            # نقل المخزون
            stocks = Stock.objects.filter(warehouse=source_warehouse)
            for stock in stocks:
                target_stock, created = Stock.objects.get_or_create(
                    product=stock.product,
                    warehouse=target_warehouse,
                    defaults={'quantity': 0}
                )
                
                if stock.quantity > 0:
                    # إنشاء حركة نقل
                    StockMovement.objects.create(
                        product=stock.product,
                        warehouse=source_warehouse,
                        destination_warehouse=target_warehouse,
                        movement_type='transfer',
                        quantity=stock.quantity,
                        notes=f'نقل من المخزن المحذوف: {source_warehouse.name}',
                        created_by=user,
                        document_type='transfer',
                        reference_number=f'TRANSFER-{source_warehouse.code}-{target_warehouse.code}'
                    )
                    
                    # تحديث المخزون في المخزن المستهدف
                    target_stock.quantity += stock.quantity
                    target_stock.save()
                
                # حذف المخزون من المخزن المصدر
                stock.delete()
            
            # تحديث حركات المخزون القديمة (تغيير المرجع فقط)
            StockMovement.objects.filter(warehouse=source_warehouse).update(
                notes=F('notes') + f' [المخزن الأصلي: {source_warehouse.name} - محذوف]'
            )
            
            # تحديث المبيعات والمشتريات لتشير للمخزن الجديد
            try:
                from sale.models import Sale
                sales_count = Sale.objects.filter(warehouse=source_warehouse).count()
                if sales_count > 0:
                    Sale.objects.filter(warehouse=source_warehouse).update(warehouse=target_warehouse)
                    logger.info(f"تم نقل {sales_count} فاتورة مبيعات من {source_warehouse.name} إلى {target_warehouse.name}")
            except ImportError:
                pass
                
            try:
                from purchase.models import Purchase
                purchases_count = Purchase.objects.filter(warehouse=source_warehouse).count()
                if purchases_count > 0:
                    Purchase.objects.filter(warehouse=source_warehouse).update(warehouse=target_warehouse)
                    logger.info(f"تم نقل {purchases_count} فاتورة مشتريات من {source_warehouse.name} إلى {target_warehouse.name}")
            except ImportError:
                pass
        
        return True
        
    except Exception as e:
        logger.error(f"خطأ في نقل بيانات المخزن: {str(e)}")
        return False


def _force_delete_warehouse(warehouse):
    """
    حذف قسري للمخزن مع جميع البيانات المرتبطة
    تحذير: هذه العملية خطيرة ولا يمكن التراجع عنها
    """
    try:
        from django.db import transaction
        
        with transaction.atomic():
            # حذف المخزون
            Stock.objects.filter(warehouse=warehouse).delete()
            
            # حذف حركات المخزون
            StockMovement.objects.filter(warehouse=warehouse).delete()
            StockMovement.objects.filter(destination_warehouse=warehouse).delete()
            
            # حذف المبيعات والمشتريات المرتبطة بالمخزن
            # بدلاً من تعيين warehouse=None (غير مسموح)، نحذف السجلات نهائياً
            try:
                from sale.models import Sale
                sales_to_delete = Sale.objects.filter(warehouse=warehouse)
                sales_count = sales_to_delete.count()
                if sales_count > 0:
                    logger.warning(f"سيتم حذف {sales_count} فاتورة مبيعات مرتبطة بالمخزن {warehouse.name}")
                    # حذف عناصر المبيعات أولاً
                    try:
                        from sale.models import SaleItem
                        SaleItem.objects.filter(sale__warehouse=warehouse).delete()
                    except ImportError:
                        pass
                    # حذف مدفوعات المبيعات
                    try:
                        from sale.models import SalePayment
                        SalePayment.objects.filter(sale__warehouse=warehouse).delete()
                    except ImportError:
                        pass
                    # حذف فواتير المبيعات
                    sales_to_delete.delete()
            except ImportError:
                pass
                
            try:
                from purchase.models import Purchase
                purchases_to_delete = Purchase.objects.filter(warehouse=warehouse)
                purchases_count = purchases_to_delete.count()
                if purchases_count > 0:
                    logger.warning(f"سيتم حذف {purchases_count} فاتورة مشتريات مرتبطة بالمخزن {warehouse.name}")
                    # حذف عناصر المشتريات أولاً
                    try:
                        from purchase.models import PurchaseItem
                        PurchaseItem.objects.filter(purchase__warehouse=warehouse).delete()
                    except ImportError:
                        pass
                    # حذف مدفوعات المشتريات
                    try:
                        from purchase.models import PurchasePayment
                        PurchasePayment.objects.filter(purchase__warehouse=warehouse).delete()
                    except ImportError:
                        pass
                    # حذف فواتير المشتريات
                    purchases_to_delete.delete()
            except ImportError:
                pass
            
            # حذف المخزن
            warehouse.delete()
            
    except Exception as e:
        logger.error(f"خطأ في الحذف القسري للمخزن: {str(e)}")
        raise e


@login_required
def product_stock_view(request, pk):
    """
    عرض مخزون المنتج في جميع المخازن
    """
    product = get_object_or_404(
        Product.objects.select_related('category', 'brand', 'unit'), 
        pk=pk
    )
    
    # الحصول على المخزون الحالي للمنتج في كل مستودع
    stock_items = Stock.objects.filter(product=product).select_related('warehouse')
    
    # آخر حركات المخزون
    stock_movements = StockMovement.objects.filter(product=product).select_related(
        'warehouse', 'destination_warehouse', 'created_by'
    ).order_by('-timestamp')[:20]
    
    # إجمالي المخزون
    total_stock = stock_items.aggregate(total=Sum('quantity'))['total'] or 0
    
    # المخازن المتاحة لإضافة المخزون
    warehouses = Warehouse.objects.filter(is_active=True)
    
    context = {
        'product': product,
        'stock_items': stock_items,
        'stock_movements': stock_movements,
        'total_stock': total_stock,
        'warehouses': warehouses,
        'page_title': f'مخزون المنتج: {product.name}',
        'page_icon': 'fas fa-boxes',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'المنتجات', 'url': reverse('product:product_list'), 'icon': 'fas fa-box'},
            {'title': product.name, 'url': reverse('product:product_detail', args=[product.pk]), 'icon': 'fas fa-info-circle'},
            {'title': 'المخزون', 'active': True}
        ],
    }
    
    return render(request, 'product/product_stock.html', context)


# ==================== APIs أسعار الموردين ====================

@login_required
@csrf_exempt
@require_POST
def add_supplier_price_api(request):
    """
    API لإضافة سعر مورد جديد لمنتج
    """
    try:
        import json
        from product.services.pricing_service import PricingService
        from supplier.models import Supplier
        
        data = json.loads(request.body)
        product_id = data.get('product_id')
        supplier_id = data.get('supplier_id')
        cost_price = Decimal(str(data.get('cost_price', 0)))
        notes = data.get('notes', '')
        
        # التحقق من صحة البيانات
        if not all([product_id, supplier_id, cost_price]):
            return JsonResponse({
                'success': False,
                'message': 'بيانات مطلوبة مفقودة'
            })
        
        # الحصول على المنتج والمورد
        product = get_object_or_404(Product, pk=product_id)
        supplier = get_object_or_404(Supplier, pk=supplier_id)
        
        # إضافة السعر
        supplier_price = PricingService.update_supplier_price(
            product=product,
            supplier=supplier,
            new_price=cost_price,
            user=request.user,
            reason='manual_update',
            notes=notes
        )
        
        if supplier_price:
            return JsonResponse({
                'success': True,
                'message': f'تم إضافة سعر المورد {supplier.name} بنجاح',
                'data': {
                    'id': supplier_price.id,
                    'supplier_name': supplier.name,
                    'cost_price': float(supplier_price.cost_price),
                    'is_default': supplier_price.is_default,
                    'last_purchase_date': supplier_price.last_purchase_date.strftime('%d/%m/%Y') if supplier_price.last_purchase_date else None
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'فشل في إضافة سعر المورد'
            })
            
    except Exception as e:
        logger.error(f"خطأ في إضافة سعر المورد: {e}")
        return JsonResponse({
            'success': False,
            'message': 'حدث خطأ غير متوقع'
        })


@login_required
@csrf_exempt
@require_POST
def edit_supplier_price_api(request, pk):
    """
    API لتعديل سعر مورد موجود
    """
    try:
        import json
        from product.services.pricing_service import PricingService
        
        # الحصول على سعر المورد
        supplier_price = get_object_or_404(SupplierProductPrice, pk=pk)
        
        data = json.loads(request.body)
        new_price = Decimal(str(data.get('cost_price', 0)))
        notes = data.get('notes', '')
        
        if new_price <= 0:
            return JsonResponse({
                'success': False,
                'message': 'السعر يجب أن يكون أكبر من صفر'
            })
        
        # تحديث السعر
        updated_price = PricingService.update_supplier_price(
            product=supplier_price.product,
            supplier=supplier_price.supplier,
            new_price=new_price,
            user=request.user,
            reason='manual_update',
            notes=notes
        )
        
        if updated_price:
            return JsonResponse({
                'success': True,
                'message': f'تم تحديث سعر المورد {supplier_price.supplier.name} بنجاح',
                'data': {
                    'id': updated_price.id,
                    'cost_price': float(updated_price.cost_price),
                    'is_default': updated_price.is_default
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'فشل في تحديث سعر المورد'
            })
            
    except Exception as e:
        logger.error(f"خطأ في تعديل سعر المورد: {e}")
        return JsonResponse({
            'success': False,
            'message': 'حدث خطأ غير متوقع'
        })


@login_required
@csrf_exempt
@require_POST
def set_default_supplier_api(request, pk):
    """
    API لتعيين مورد كافتراضي
    """
    try:
        from product.services.pricing_service import PricingService
        
        # الحصول على سعر المورد
        supplier_price = get_object_or_404(SupplierProductPrice, pk=pk)
        
        # تعيين المورد كافتراضي
        success = PricingService.set_default_supplier(
            product=supplier_price.product,
            supplier=supplier_price.supplier,
            user=request.user
        )
        
        if success:
            return JsonResponse({
                'success': True,
                'message': f'تم تعيين {supplier_price.supplier.name} كمورد افتراضي',
                'data': {
                    'supplier_id': supplier_price.supplier.id,
                    'supplier_name': supplier_price.supplier.name
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'فشل في تعيين المورد الافتراضي'
            })
            
    except Exception as e:
        logger.error(f"خطأ في تعيين المورد الافتراضي: {e}")
        return JsonResponse({
            'success': False,
            'message': 'حدث خطأ غير متوقع'
        })


@login_required
def supplier_price_history_api(request, pk):
    """
    API لعرض تاريخ أسعار مورد معين
    """
    try:
        from product.services.pricing_service import PricingService
        
        # الحصول على سعر المورد
        supplier_price = get_object_or_404(SupplierProductPrice, pk=pk)
        
        # الحصول على تاريخ الأسعار
        price_history = PricingService.get_price_history(
            product=supplier_price.product,
            supplier=supplier_price.supplier,
            limit=20
        )
        
        history_data = []
        for history in price_history:
            history_data.append({
                'id': history.id,
                'old_price': float(history.old_price) if history.old_price else None,
                'new_price': float(history.new_price),
                'change_amount': float(history.change_amount) if history.change_amount else 0,
                'change_percentage': float(history.change_percentage) if history.change_percentage else 0,
                'change_reason': history.get_change_reason_display(),
                'change_date': history.change_date.strftime('%d/%m/%Y %H:%M'),
                'changed_by': history.changed_by.get_full_name() or history.changed_by.username,
                'purchase_reference': history.purchase_reference,
                'notes': history.notes,
                'is_increase': history.is_price_increase,
                'is_decrease': history.is_price_decrease
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'supplier_name': supplier_price.supplier.name,
                'product_name': supplier_price.product.name,
                'current_price': float(supplier_price.cost_price),
                'history': history_data
            }
        })
        
    except Exception as e:
        logger.error(f"خطأ في عرض تاريخ الأسعار: {e}")
        return JsonResponse({
            'success': False,
            'message': 'حدث خطأ غير متوقع'
        })


@login_required
def product_price_comparison_api(request, product_id):
    """
    API لعرض مقارنة أسعار جميع الموردين لمنتج معين
    """
    try:
        from product.services.pricing_service import PricingService
        
        product = get_object_or_404(Product, pk=product_id)
        
        # الحصول على مقارنة الأسعار
        price_comparison = PricingService.get_price_comparison(product)
        
        comparison_data = []
        for comparison in price_comparison:
            comparison_data.append({
                'supplier_id': comparison['supplier'].id,
                'supplier_name': comparison['supplier'].name,
                'price': float(comparison['price']),
                'is_default': comparison['is_default'],
                'last_purchase_date': comparison['last_purchase_date'].strftime('%d/%m/%Y') if comparison['last_purchase_date'] else None,
                'last_purchase_quantity': comparison['last_purchase_quantity'],
                'price_difference': float(comparison['price_difference']),
                'price_difference_percent': float(comparison['price_difference_percent']),
                'days_since_last_purchase': comparison['days_since_last_purchase'],
                'notes': comparison['notes']
            })
        
        return JsonResponse({
            'success': True,
            'data': {
                'product_name': product.name,
                'product_cost_price': float(product.cost_price),
                'suppliers_count': len(comparison_data),
                'cheapest_price': min([c['price'] for c in comparison_data]) if comparison_data else 0,
                'most_expensive_price': max([c['price'] for c in comparison_data]) if comparison_data else 0,
                'comparison': comparison_data
            }
        })
        
    except Exception as e:
        logger.error(f"خطأ في مقارنة الأسعار: {e}")
        return JsonResponse({
            'success': False,
            'message': 'حدث خطأ غير متوقع'
        })
