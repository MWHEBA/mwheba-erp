from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg
from django.urls import reverse
from supplier.models import SupplierType, SpecializedService, Supplier


@login_required
def services_home(request):
    """
    الصفحة الرئيسية للخدمات - عرض جميع أنواع الخدمات
    """
    # جلب جميع أنواع الموردين النشطة مع إحصائيات الخدمات
    service_types = SupplierType.objects.filter(
        is_active=True
    ).annotate(
        services_count=Count('specializedservice', filter=Q(specializedservice__is_active=True)),
        suppliers_count=Count('specializedservice__supplier', filter=Q(specializedservice__is_active=True, specializedservice__supplier__is_active=True), distinct=True),
        avg_price=Avg('specializedservice__setup_cost', filter=Q(specializedservice__is_active=True))
    ).filter(
        services_count__gt=0  # فقط الأنواع التي لها خدمات
    ).order_by('display_order', 'name')
    
    # إحصائيات عامة
    total_services = SpecializedService.objects.filter(is_active=True).count()
    total_suppliers = Supplier.objects.filter(is_active=True, specialized_services__is_active=True).distinct().count()
    total_categories = service_types.count()
    
    # متوسط التقييم العام
    avg_rating = 0
    active_services = SpecializedService.objects.filter(is_active=True).select_related('supplier')
    if active_services.exists():
        ratings = [s.supplier.supplier_rating for s in active_services if s.supplier.supplier_rating and s.supplier.supplier_rating > 0]
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
    context = {
        'service_types': service_types,
        'total_services': total_services,
        'total_suppliers': total_suppliers,
        'total_categories': total_categories,
        'avg_rating': round(avg_rating, 1) if avg_rating else 0,
        'page_title': 'الخدمات المتخصصة',
        'page_icon': 'fas fa-cogs',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الخدمات المتخصصة', 'active': True, 'icon': 'fas fa-cogs'}
        ],
    }
    
    return render(request, 'services/services_home.html', context)


@login_required
def category_detail(request, slug):
    """
    عرض تفاصيل نوع خدمة معين مع جدول الخدمات
    """
    # جلب نوع الخدمة
    category = get_object_or_404(SupplierType, slug=slug, is_active=True)
    
    # فلترة الخدمات
    supplier_filter = request.GET.get('supplier', '')
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    
    # استعلام الخدمات الأساسي
    services = SpecializedService.objects.filter(
        is_active=True,
        category=category
    ).select_related('supplier', 'category').order_by('name')
    
    # تطبيق الفلاتر
    if supplier_filter:
        services = services.filter(supplier_id=supplier_filter)
    
    if min_price:
        try:
            min_price_val = float(min_price)
            services = services.filter(setup_cost__gte=min_price_val)
        except (ValueError, TypeError):
            pass
    
    if max_price:
        try:
            max_price_val = float(max_price)
            services = services.filter(setup_cost__lte=max_price_val)
        except (ValueError, TypeError):
            pass
    
    # إحصائيات الفئة
    services_count = services.count()
    suppliers_count = services.values('supplier').distinct().count()
    avg_price = services.aggregate(avg=Avg('setup_cost'))['avg']
    
    # متوسط التقييم
    avg_rating = 0
    if services.exists():
        ratings = [s.supplier.supplier_rating for s in services if s.supplier.supplier_rating and s.supplier.supplier_rating > 0]
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
    
    # قائمة الموردين للفلترة
    suppliers = Supplier.objects.filter(
        is_active=True,
        specialized_services__category=category,
        specialized_services__is_active=True
    ).distinct().order_by('name')
    
    # تعريف headers للجدول حسب نوع الفئة
    if category.code == 'offset_printing':
        category_service_headers = [
            {'key': 'name', 'label': 'اسم الماكينة', 'sortable': True, 'class': 'text-start', 'width': '30%'},
            {'key': 'supplier.name', 'label': 'المورد', 'sortable': True, 'format': 'link', 'url': 'supplier:supplier_detail', 'width': '25%'},
            {'key': 'impression_cost', 'label': 'سعر التراج', 'sortable': True, 'class': 'text-center', 'template': 'components/cells/offset_impression_cost.html', 'width': '20%'},
            {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'format': 'status', 'width': '10%'},
            {'key': 'actions', 'label': 'الإجراءات', 'sortable': False, 'class': 'text-center', 'template': 'components/cells/service_actions_crud.html', 'width': '15%'},
        ]
    else:
        # Headers افتراضية للفئات الأخرى
        category_service_headers = [
            {'key': 'name', 'label': 'اسم الخدمة', 'sortable': True, 'class': 'text-start', 'width': '40%'},
            {'key': 'supplier.name', 'label': 'المورد', 'sortable': True, 'format': 'link', 'url': 'supplier:supplier_detail', 'width': '35%'},
            {'key': 'is_active', 'label': 'الحالة', 'sortable': True, 'class': 'text-center', 'format': 'status', 'width': '10%'},
            {'key': 'actions', 'label': 'الإجراءات', 'sortable': False, 'class': 'text-center', 'template': 'components/cells/service_actions_crud.html', 'width': '15%'},
        ]
    
    # تعريف actions للجدول (فارغة لأننا نستخدم القالب المخصص)
    category_service_actions = []
    
    context = {
        'category': category,
        'services': services,
        'suppliers': suppliers,
        'services_count': services_count,
        'suppliers_count': suppliers_count,
        'avg_price': avg_price,
        'avg_rating': round(avg_rating, 1) if avg_rating else 0,
        'category_service_headers': category_service_headers,
        'category_service_actions': category_service_actions,
        'primary_key': 'id',  # إضافة المفتاح الأساسي المطلوب للجدول الموحد
        'page_title': f'خدمات {category.name}',
        'page_icon': category.icon or 'fas fa-cogs',
        'breadcrumb_items': [
            {'title': 'الرئيسية', 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': 'الخدمات المتخصصة', 'url': reverse('services:services_home'), 'icon': 'fas fa-cogs'},
            {'title': category.name, 'active': True, 'icon': category.icon or 'fas fa-cogs'}
        ],
    }
    
    return render(request, 'services/category_detail.html', context)
