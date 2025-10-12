"""
Views إدارة المخزون والتنبيهات
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Sum, Count, F
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from datetime import datetime, timedelta
import json

from ..models import Product, Category, Warehouse, Stock, StockMovement
# استيراد آمن للنماذج الجديدة
try:
    from ..models.warehouse import ProductStock, StockTransfer, StockSnapshot
    from ..models.inventory_movement import InventoryMovement, InventoryAdjustment, InventoryAdjustmentItem
except ImportError:
    # في حالة عدم توفر النماذج، استخدم None
    ProductStock = StockTransfer = StockSnapshot = None
    InventoryMovement = InventoryAdjustment = InventoryAdjustmentItem = None
# استيراد آمن للخدمات
try:
    from ..services.inventory_service import InventoryService
    from ..services.advanced_reports_service import AdvancedReportsService
except ImportError:
    InventoryService = AdvancedReportsService = None
from core.services.notification_service import NotificationService


# تم تعطيل لوحة تحكم المخزون - مكررة مع جرد المخزون
# @login_required
def inventory_dashboard_disabled(request):
    """
    لوحة تحكم المخزون
    """
    try:
        # إحصائيات عامة
        total_products = Product.objects.filter(is_active=True).count()
        total_warehouses = Warehouse.objects.filter(is_active=True).count()
        
        # إحصائيات المخزون
        stock_stats = ProductStock.objects.aggregate(
            total_items=Count('id'),
            total_value=Sum(F('quantity') * F('average_cost')),
            low_stock_count=Count(
                'id', 
                filter=Q(quantity__lte=F('product__min_stock'))
            ),
            out_of_stock_count=Count('id', filter=Q(quantity=0))
        )
        
        # حركات اليوم
        today = timezone.now().date()
        today_movements = InventoryMovement.objects.filter(
            date__date=today
        ).aggregate(
            total_movements=Count('id'),
            total_in=Sum(
                'quantity', 
                filter=Q(movement_type__in=['in', 'return_in'])
            ),
            total_out=Sum(
                'quantity', 
                filter=Q(movement_type__in=['out', 'return_out', 'damage', 'expired'])
            )
        )
        
        # المنتجات منخفضة المخزون
        low_stock_products = ProductStock.objects.filter(
            quantity__lte=F('product__min_stock'),
            product__is_active=True
        ).select_related('product', 'warehouse')[:10]
        
        # آخر الحركات
        recent_movements = InventoryMovement.objects.select_related(
            'product', 'warehouse', 'created_by'
        ).order_by('-created_at')[:10]
        
        context = {
            'total_products': total_products,
            'total_warehouses': total_warehouses,
            'stock_stats': stock_stats,
            'today_movements': today_movements,
            'low_stock_products': low_stock_products,
            'recent_movements': recent_movements,
        }
        
        return render(request, 'product/inventory_dashboard.html', context)
        
    except Exception as e:
        messages.error(request, f'خطأ في تحميل لوحة تحكم المخزون: {e}')
        return redirect('core:dashboard')


@login_required
def inventory_report(request):
    """
    تقرير المخزون الشامل
    """
    # فلاتر البحث
    warehouse_id = request.GET.get('warehouse')
    category_id = request.GET.get('category')
    low_stock_only = request.GET.get('low_stock_only') == '1'
    search = request.GET.get('search', '').strip()
    
    # الحصول على التقرير
    warehouse = None
    if warehouse_id:
        warehouse = get_object_or_404(Warehouse, id=warehouse_id)
    
    category = None
    if category_id:
        category = get_object_or_404(Category, id=category_id)
    
    report_data = InventoryService.get_inventory_report(
        warehouse=warehouse,
        category=category,
        low_stock_only=low_stock_only
    )
    
    stocks = report_data['stocks']
    
    # فلترة البحث
    if search:
        stocks = [
            stock for stock in stocks 
            if search.lower() in stock.product.name.lower() or 
               search.lower() in stock.product.sku.lower()
        ]
    
    # ترقيم الصفحات
    paginator = Paginator(stocks, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'stats': report_data['stats'],
        'warehouses': Warehouse.objects.filter(is_active=True),
        'categories': Category.objects.filter(is_active=True),
        'filters': {
            'warehouse_id': warehouse_id,
            'category_id': category_id,
            'low_stock_only': low_stock_only,
            'search': search,
        }
    }
    
    return render(request, 'product/inventory_report.html', context)


@login_required
def movement_report(request):
    """
    تقرير حركات المخزون
    """
    # فلاتر البحث
    product_id = request.GET.get('product')
    warehouse_id = request.GET.get('warehouse')
    movement_type = request.GET.get('movement_type')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # تحويل التواريخ
    date_from_obj = None
    date_to_obj = None
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            pass
    
    # الحصول على التقرير
    product = None
    if product_id:
        product = get_object_or_404(Product, id=product_id)
    
    warehouse = None
    if warehouse_id:
        warehouse = get_object_or_404(Warehouse, id=warehouse_id)
    
    report_data = InventoryService.get_movement_report(
        product=product,
        warehouse=warehouse,
        date_from=date_from_obj,
        date_to=date_to_obj,
        movement_type=movement_type
    )
    
    # ترقيم الصفحات
    movements = report_data['movements']
    paginator = Paginator(movements, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'stats': report_data['stats'],
        'products': Product.objects.filter(is_active=True).order_by('name'),
        'warehouses': Warehouse.objects.filter(is_active=True),
        'movement_types': InventoryMovement.MOVEMENT_TYPES,
        'filters': {
            'product_id': product_id,
            'warehouse_id': warehouse_id,
            'movement_type': movement_type,
            'date_from': date_from,
            'date_to': date_to,
        }
    }
    
    return render(request, 'product/movement_report.html', context)


@login_required
@permission_required('product.add_inventoryadjustment', raise_exception=True)
def create_adjustment(request):
    """
    إنشاء تسوية مخزون
    """
    if request.method == 'POST':
        try:
            product_id = request.POST.get('product')
            warehouse_id = request.POST.get('warehouse')
            adjustment_type = request.POST.get('adjustment_type')
            expected_quantity = float(request.POST.get('expected_quantity', 0))
            actual_quantity = float(request.POST.get('actual_quantity', 0))
            reason = request.POST.get('reason', '').strip()
            
            if not all([product_id, warehouse_id, adjustment_type, reason]):
                messages.error(request, 'جميع الحقول مطلوبة')
                return redirect('product:create_adjustment')
            
            product = get_object_or_404(Product, id=product_id)
            warehouse = get_object_or_404(Warehouse, id=warehouse_id)
            
            # إنشاء التسوية
            adjustment = InventoryService.create_adjustment(
                product=product,
                warehouse=warehouse,
                expected_quantity=expected_quantity,
                actual_quantity=actual_quantity,
                adjustment_type=adjustment_type,
                reason=reason,
                user=request.user
            )
            
            messages.success(request, f'تم إنشاء تسوية المخزون بنجاح: {adjustment}')
            return redirect('product:inventory_report')
            
        except Exception as e:
            messages.error(request, f'خطأ في إنشاء تسوية المخزون: {e}')
    
    context = {
        'products': Product.objects.filter(is_active=True).order_by('name'),
        'warehouses': Warehouse.objects.filter(is_active=True),
        'adjustment_types': InventoryAdjustment.ADJUSTMENT_TYPES,
    }
    
    return render(request, 'product/create_adjustment.html', context)


@login_required
@permission_required('product.add_stocktransfer', raise_exception=True)
def create_transfer(request):
    """
    إنشاء تحويل مخزون
    """
    if request.method == 'POST':
        try:
            product_id = request.POST.get('product')
            from_warehouse_id = request.POST.get('from_warehouse')
            to_warehouse_id = request.POST.get('to_warehouse')
            quantity = float(request.POST.get('quantity', 0))
            notes = request.POST.get('notes', '').strip()
            
            if not all([product_id, from_warehouse_id, to_warehouse_id]):
                messages.error(request, 'جميع الحقول مطلوبة')
                return redirect('product:create_transfer')
            
            if from_warehouse_id == to_warehouse_id:
                messages.error(request, 'لا يمكن التحويل لنفس المستودع')
                return redirect('product:create_transfer')
            
            if quantity <= 0:
                messages.error(request, 'الكمية يجب أن تكون أكبر من صفر')
                return redirect('product:create_transfer')
            
            product = get_object_or_404(Product, id=product_id)
            from_warehouse = get_object_or_404(Warehouse, id=from_warehouse_id)
            to_warehouse = get_object_or_404(Warehouse, id=to_warehouse_id)
            
            # إنشاء التحويل
            transfer = InventoryService.transfer_stock(
                product=product,
                from_warehouse=from_warehouse,
                to_warehouse=to_warehouse,
                quantity=quantity,
                user=request.user,
                notes=notes
            )
            
            messages.success(request, f'تم تحويل المخزون بنجاح: {transfer}')
            return redirect('product:inventory_report')
            
        except Exception as e:
            messages.error(request, f'خطأ في تحويل المخزون: {e}')
    
    context = {
        'products': Product.objects.filter(is_active=True).order_by('name'),
        'warehouses': Warehouse.objects.filter(is_active=True),
    }
    
    return render(request, 'product/create_transfer.html', context)


@login_required
@require_http_methods(["GET"])
def get_product_stock_api(request, product_id):
    """
    API للحصول على مخزون منتج في جميع المستودعات
    """
    try:
        product = get_object_or_404(Product, id=product_id)
        
        stocks = ProductStock.objects.filter(
            product=product
        ).select_related('warehouse').values(
            'warehouse__id',
            'warehouse__name',
            'quantity',
            'available_quantity',
            'average_cost',
            'reorder_point'
        )
        
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'min_stock': float(product.min_stock),
                'unit': product.unit.symbol
            },
            'stocks': list(stocks)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def check_alerts_api(request):
    """
    API لفحص التنبيهات يدوياً
    """
    try:
        alert_type = request.POST.get('type', 'all')
        
        notifications = []
        
        if alert_type in ['stock', 'all']:
            stock_alerts = NotificationService.check_low_stock_alerts()
            notifications.extend(stock_alerts)
        
        if alert_type in ['invoices', 'all']:
            invoice_alerts = NotificationService.check_due_invoices_alerts()
            notifications.extend(invoice_alerts)
        
        return JsonResponse({
            'success': True,
            'message': f'تم فحص التنبيهات بنجاح',
            'alerts_created': len(notifications),
            'alerts': [
                {
                    'title': notif.title,
                    'type': notif.type,
                    'created_at': notif.created_at.isoformat()
                }
                for notif in notifications[:10]  # أول 10 تنبيهات فقط
            ]
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def notifications_list(request):
    """
    قائمة الإشعارات للمستخدم
    """
    notifications = NotificationService.get_user_notifications(
        user=request.user,
        limit=50
    )
    
    # إحصائيات الإشعارات
    stats = NotificationService.get_notification_stats(user=request.user)
    
    # ترقيم الصفحات
    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'stats': stats,
    }
    
    return render(request, 'core/notifications_list.html', context)


@login_required
@require_http_methods(["POST"])
def mark_notifications_read(request):
    """
    تعليم الإشعارات كمقروءة
    """
    try:
        notification_ids = request.POST.getlist('notification_ids')
        
        if not notification_ids:
            return JsonResponse({
                'success': False,
                'error': 'لم يتم تحديد أي إشعارات'
            })
        
        updated_count = NotificationService.mark_as_read(
            notification_ids=notification_ids,
            user=request.user
        )
        
        return JsonResponse({
            'success': True,
            'message': f'تم تعليم {updated_count} إشعار كمقروء',
            'updated_count': updated_count
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def abc_analysis_report(request):
    """
    تقرير تحليل ABC للمنتجات
    """
    if not AdvancedReportsService:
        messages.error(request, 'خدمة التقارير المتقدمة غير متاحة')
        return redirect('product:inventory_dashboard')
    
    # فلاتر البحث
    warehouse_id = request.GET.get('warehouse')
    period_months = int(request.GET.get('period_months', 12))
    
    warehouse = None
    if warehouse_id:
        warehouse = get_object_or_404(Warehouse, id=warehouse_id)
    
    # الحصول على التقرير
    report_data = AdvancedReportsService.abc_analysis(
        warehouse=warehouse,
        period_months=period_months
    )
    
    # ترقيم الصفحات
    products = report_data.get('products', [])
    paginator = Paginator(products, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'summary': report_data.get('summary', {}),
        'total_value': report_data.get('total_value', 0),
        'period': report_data.get('period', ''),
        'warehouses': Warehouse.objects.filter(is_active=True),
        'filters': {
            'warehouse_id': warehouse_id,
            'period_months': period_months,
        },
        'error': report_data.get('error')
    }
    
    return render(request, 'product/reports/abc_analysis.html', context)


@login_required
def inventory_turnover_report(request):
    """
    تقرير معدل دوران المخزون - باستخدام البيانات الفعلية
    """
    try:
        # فلاتر البحث
        warehouse_id = request.GET.get('warehouse')
        period_months = int(request.GET.get('period_months', 12))
        
        warehouse = None
        if warehouse_id:
            warehouse = get_object_or_404(Warehouse, id=warehouse_id)
        
        # تحديد فترة التحليل
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=period_months * 30)
        
        # جلب المنتجات مع المخزون
        products_query = Product.objects.filter(is_active=True)
        
        if warehouse:
            products_query = products_query.filter(stocks__warehouse=warehouse)
        
        products_data = []
        
        for product in products_query.distinct():
            # حساب المخزون الحالي
            if warehouse:
                current_stock = product.stocks.filter(warehouse=warehouse).aggregate(
                    total=Sum('quantity'))['total'] or 0
                avg_cost_obj = product.stocks.filter(warehouse=warehouse).first()
                avg_cost = avg_cost_obj.quantity * product.cost_price if avg_cost_obj else product.cost_price
            else:
                current_stock = product.stocks.aggregate(
                    total=Sum('quantity'))['total'] or 0
                avg_cost = product.cost_price
            
            # حساب تكلفة البضاعة المباعة (COGS)
            cogs_movements = StockMovement.objects.filter(
                product=product,
                movement_type='out',
                timestamp__date__range=[start_date, end_date]
            )
            
            if warehouse:
                cogs_movements = cogs_movements.filter(warehouse=warehouse)
            
            # حساب COGS باستخدام تكلفة المنتج
            total_out_quantity = cogs_movements.aggregate(total=Sum('quantity'))['total'] or 0
            cogs = total_out_quantity * avg_cost
            
            # متوسط قيمة المخزون (تبسيط: المخزون الحالي × متوسط التكلفة)
            avg_inventory_value = current_stock * avg_cost
            
            # حساب معدل الدوران
            if avg_inventory_value > 0:
                turnover_ratio = float(cogs / avg_inventory_value)
            else:
                turnover_ratio = 0
            
            # تصنيف معدل الدوران
            if turnover_ratio >= 6:
                category = 'سريع'
                category_class = 'success'
            elif turnover_ratio >= 3:
                category = 'متوسط'
                category_class = 'warning'
            elif turnover_ratio >= 1:
                category = 'بطيء'
                category_class = 'danger'
            else:
                category = 'راكد'
                category_class = 'dark'
            
            # حساب أيام التخزين
            days_in_stock = int(365 / turnover_ratio) if turnover_ratio > 0 else 365
            
            # إضافة المنتج للتقرير حتى لو لم يكن له مبيعات
            products_data.append({
                'product': product,
                'current_stock': current_stock,
                'avg_inventory_value': avg_inventory_value,
                'average_inventory': avg_inventory_value,  # للتوافق مع Template
                'cogs': cogs,
                'turnover_ratio': round(turnover_ratio, 2),
                'days_in_stock': days_in_stock,
                'category': category,
                'category_class': category_class,
                'warehouse_name': warehouse.name if warehouse else 'جميع المستودعات'
            })
        
        # ترتيب حسب معدل الدوران (تنازلي)
        products_data.sort(key=lambda x: x['turnover_ratio'], reverse=True)
        
        # حساب الإحصائيات
        if products_data:
            avg_turnover = sum(p['turnover_ratio'] for p in products_data) / len(products_data)
            fast_count = len([p for p in products_data if p['category'] == 'سريع'])
            medium_count = len([p for p in products_data if p['category'] == 'متوسط'])
            slow_count = len([p for p in products_data if p['category'] == 'بطيء'])
            stagnant_count = len([p for p in products_data if p['category'] == 'راكد'])
        else:
            avg_turnover = 0
            fast_count = medium_count = slow_count = stagnant_count = 0
        
        summary = {
            'avg_turnover': round(avg_turnover, 2),
            'fast_count': fast_count,
            'medium_count': medium_count,
            'slow_count': slow_count,
            'stagnant_count': stagnant_count,
            'total_products': len(products_data)
        }
        
        # ترقيم الصفحات
        paginator = Paginator(products_data, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'page_obj': page_obj,
            'turnover_data': products_data,  # للتوافق مع Template
            'summary': summary,
            'period': f"{start_date} إلى {end_date}",
            'warehouses': Warehouse.objects.filter(is_active=True),
            'filters': {
                'warehouse_id': warehouse_id,
                'period_months': period_months,
            },
            'selected_warehouse': warehouse
        }
        
        return render(request, 'product/reports/inventory_turnover.html', context)
        
    except Exception as e:
        messages.error(request, f'خطأ في تحميل تقرير معدل الدوران: {e}')
        return redirect('product:product_list')


@login_required
def stock_aging_report(request):
    """
    تقرير عمر المخزون - باستخدام البيانات الفعلية
    """
    try:
        # فلاتر البحث
        warehouse_id = request.GET.get('warehouse')
        
        warehouse = None
        if warehouse_id:
            warehouse = get_object_or_404(Warehouse, id=warehouse_id)
        
        # جلب المنتجات مع المخزون
        products_query = Product.objects.filter(is_active=True)
        
        if warehouse:
            products_query = products_query.filter(stocks__warehouse=warehouse)
        
        aging_data = []
        today = timezone.now().date()
        
        for product in products_query.distinct():
            # حساب المخزون الحالي
            if warehouse:
                stocks = product.stocks.filter(warehouse=warehouse, quantity__gt=0)
            else:
                stocks = product.stocks.filter(quantity__gt=0)
            
            for stock in stocks:
                # البحث عن آخر حركة دخول لهذا المنتج
                last_in_movement = StockMovement.objects.filter(
                    product=product,
                    warehouse=stock.warehouse,
                    movement_type='in'
                ).order_by('-timestamp').first()
                
                # حساب عمر المخزون
                if last_in_movement:
                    entry_date = last_in_movement.timestamp.date()
                    age_days = (today - entry_date).days
                else:
                    # إذا لم توجد حركة، استخدم تاريخ إنشاء المنتج
                    entry_date = product.created_at.date()
                    age_days = (today - entry_date).days
                
                # تحديد فئة العمر
                if age_days <= 30:
                    age_category = 'جديد'
                    category_class = 'success'
                elif age_days <= 90:
                    age_category = 'جيد'
                    category_class = 'info'
                elif age_days <= 180:
                    age_category = 'تحذير'
                    category_class = 'warning'
                elif age_days <= 365:
                    age_category = 'خطر'
                    category_class = 'danger'
                else:
                    age_category = 'حرج'
                    category_class = 'dark'
                
                # حساب تاريخ انتهاء الصلاحية (افتراضي: سنة من تاريخ الدخول)
                expiry_date = entry_date + timedelta(days=365) if entry_date else None
                days_until_expiry = (expiry_date - today).days if expiry_date else None
                
                # قيمة المخزون
                total_value = stock.quantity * product.cost_price
                
                aging_data.append({
                    'product': product,
                    'warehouse': stock.warehouse,
                    'quantity': stock.quantity,
                    'entry_date': entry_date,
                    'age_days': age_days,
                    'expiry_date': expiry_date,
                    'days_until_expiry': days_until_expiry,
                    'total_value': total_value,
                    'age_category': age_category,
                    'category_class': category_class
                })
        
        # ترتيب حسب عمر المخزون (تنازلي)
        aging_data.sort(key=lambda x: x['age_days'], reverse=True)
        
        # حساب الإحصائيات
        if aging_data:
            fresh_count = len([item for item in aging_data if item['age_category'] == 'جديد'])
            good_count = len([item for item in aging_data if item['age_category'] == 'جيد'])
            warning_count = len([item for item in aging_data if item['age_category'] == 'تحذير'])
            danger_count = len([item for item in aging_data if item['age_category'] == 'خطر'])
            critical_count = len([item for item in aging_data if item['age_category'] == 'حرج'])
            
            total_value = sum(item['total_value'] for item in aging_data)
            critical_value = sum(item['total_value'] for item in aging_data if item['age_category'] == 'حرج')
        else:
            fresh_count = good_count = warning_count = danger_count = critical_count = 0
            total_value = critical_value = 0
        
        summary = {
            'fresh_count': fresh_count,
            'good_count': good_count,
            'warning_count': warning_count,
            'danger_count': danger_count,
            'critical_count': critical_count,
            'total_items': len(aging_data),
            'total_value': total_value,
            'critical_value': critical_value,
            'critical_percentage': round((critical_value / total_value * 100), 2) if total_value > 0 else 0
        }
        
        # ترقيم الصفحات
        paginator = Paginator(aging_data, 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'page_obj': page_obj,
            'aging_data': aging_data,  # للرسوم البيانية
            'summary': summary,
            'warehouses': Warehouse.objects.filter(is_active=True),
            'filters': {
                'warehouse_id': warehouse_id,
            },
            'selected_warehouse': warehouse
        }
        
        return render(request, 'product/reports/stock_aging.html', context)
        
    except Exception as e:
        messages.error(request, f'خطأ في تحميل تقرير عمر المخزون: {e}')
        return redirect('product:product_list')


@login_required
def reorder_point_report(request):
    """
    تقرير نقاط إعادة الطلب - باستخدام البيانات الفعلية
    """
    try:
        # فلاتر البحث
        warehouse_id = request.GET.get('warehouse')
        
        warehouse = None
        if warehouse_id:
            warehouse = get_object_or_404(Warehouse, id=warehouse_id)
        
        # جلب المنتجات مع المخزون
        products_query = Product.objects.filter(is_active=True)
        
        if warehouse:
            products_query = products_query.filter(stocks__warehouse=warehouse)
        
        products_data = []
        
        for product in products_query.distinct():
            # حساب إجمالي المخزون
            if warehouse:
                current_stock = product.stocks.filter(warehouse=warehouse).aggregate(
                    total=Sum('quantity'))['total'] or 0
            else:
                current_stock = product.stocks.aggregate(
                    total=Sum('quantity'))['total'] or 0
            
            # حساب متوسط الاستهلاك من حركات المخزون (آخر 30 يوم)
            thirty_days_ago = timezone.now().date() - timedelta(days=30)
            
            consumption = StockMovement.objects.filter(
                product=product,
                movement_type='out',
                timestamp__date__gte=thirty_days_ago
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            daily_consumption = consumption / 30 if consumption > 0 else 0
            
            # حساب نقطة إعادة الطلب
            lead_time_days = 7  # مهلة التوريد
            safety_days = 3     # مخزون الأمان
            reorder_point = daily_consumption * (lead_time_days + safety_days)
            
            # تحديد الحالة
            if current_stock <= 0:
                status = 'نفد المخزون'
                urgency = 'critical'
            elif current_stock <= reorder_point:
                status = 'يحتاج طلب'
                urgency = 'high'
            elif current_stock <= reorder_point * 1.5:
                status = 'مراقبة'
                urgency = 'medium'
            else:
                status = 'طبيعي'
                urgency = 'low'
            
            # الكمية المقترحة للطلب
            suggested_qty = max(0, (daily_consumption * 30) - current_stock) if daily_consumption > 0 else 0
            
            # الأيام المتبقية
            days_remaining = int(current_stock / daily_consumption) if daily_consumption > 0 else 999
            
            # إضافة البيانات مع جميع الحقول المطلوبة للـ template
            item_data = {
                'product': product,
                'current_stock': current_stock,
                'reorder_point': round(reorder_point, 1),
                'daily_consumption': round(daily_consumption, 2),
                'suggested_quantity': round(suggested_qty, 1),
                'days_remaining': days_remaining,
                'status': status,
                'urgency': urgency,
                'warehouse_name': warehouse.name if warehouse else 'جميع المستودعات',
                # حقول إضافية للتوافق مع Template
                'max_stock': current_stock * 2,  # افتراضي
                'stock_percentage': min(100, (current_stock / max(reorder_point * 2, 1)) * 100),
                'days_supply': days_remaining if days_remaining < 999 else None,
                'reorder_point_threshold': reorder_point * 1.5,
                'unit': product.unit if hasattr(product, 'unit') else None,
                'supplier': None
            }
            
            products_data.append(item_data)
        
        # ترتيب حسب الأولوية
        products_data.sort(key=lambda x: (0 if x['urgency'] == 'critical' else 
                                        1 if x['urgency'] == 'high' else 
                                        2 if x['urgency'] == 'medium' else 3, 
                                        x['days_remaining']))
        
        # حساب الإحصائيات
        summary = {
            'critical_count': len([p for p in products_data if p['urgency'] == 'critical']),
            'low_count': len([p for p in products_data if p['urgency'] == 'high']),
            'watch_count': len([p for p in products_data if p['urgency'] == 'medium']),
            'normal_count': len([p for p in products_data if p['urgency'] == 'low']),
            'total_products': len(products_data)
        }
        
        # فصل البيانات للعرض السريع
        critical_items = [p for p in products_data if p['urgency'] == 'critical'][:5]
        low_stock_items = [p for p in products_data if p['urgency'] == 'high'][:5]
        
        context = {
            'reorder_data': products_data,
            'summary': summary,
            'critical_items': critical_items,
            'low_stock_items': low_stock_items,
            'warehouses': Warehouse.objects.filter(is_active=True),
            'filters': {
                'warehouse_id': warehouse_id,
            },
            'selected_warehouse': warehouse
        }
        
        return render(request, 'product/reports/reorder_point.html', context)
        
    except Exception as e:
        messages.error(request, f'خطأ في تحميل تقرير نقاط إعادة الطلب: {e}')
        return redirect('product:product_list')


# تم تعطيل نظام الحجوزات - غير مطلوب في النظام التجاري
# @login_required
def reservation_dashboard_disabled(request):
    """
    لوحة تحكم الحجوزات
    """
    try:
        from ..services.reservation_service import ReservationService
        from ..models.reservation_system import StockReservation
        
        # فلاتر البحث
        warehouse_id = request.GET.get('warehouse')
        
        warehouse = None
        if warehouse_id:
            warehouse = get_object_or_404(Warehouse, id=warehouse_id)
        
        # الحصول على ملخص الحجوزات
        summary = ReservationService.get_reservation_summary(warehouse)
        
        # الحصول على الحجوزات الحديثة
        recent_reservations = StockReservation.objects.select_related(
            'product', 'warehouse', 'reserved_by'
        ).filter(
            warehouse=warehouse if warehouse else models.Q()
        ).order_by('-reserved_at')[:10]
        
        # الحصول على المنتجات منخفضة المخزون مع الحجوزات
        low_stock_data = ReservationService.get_low_stock_with_reservations(warehouse)
        
        context = {
            'summary': summary,
            'recent_reservations': recent_reservations,
            'low_stock_data': low_stock_data[:10],  # أول 10 فقط
            'warehouses': Warehouse.objects.filter(is_active=True),
            'selected_warehouse': warehouse,
        }
        
        return render(request, 'product/reservations/dashboard.html', context)
        
    except Exception as e:
        messages.error(request, f'خطأ في تحميل لوحة تحكم الحجوزات: {e}')
        return redirect('product:inventory_dashboard')


# تم تعطيل قائمة الحجوزات - غير مطلوب
# @login_required
def reservation_list_disabled(request):
    """
    قائمة الحجوزات
    """
    try:
        from ..models.reservation_system import StockReservation
        
        # فلاتر البحث
        warehouse_id = request.GET.get('warehouse')
        status = request.GET.get('status', 'active')
        reservation_type = request.GET.get('reservation_type')
        search = request.GET.get('search')
        
        # بناء الاستعلام
        queryset = StockReservation.objects.select_related(
            'product', 'warehouse', 'reserved_by'
        )
        
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)
        
        if status:
            queryset = queryset.filter(status=status)
        
        if reservation_type:
            queryset = queryset.filter(reservation_type=reservation_type)
        
        if search:
            queryset = queryset.filter(
                models.Q(product__name__icontains=search) |
                models.Q(batch_number__icontains=search) |
                models.Q(reference_number__icontains=search)
            )
        
        # ترقيم الصفحات
        paginator = Paginator(queryset.order_by('-reserved_at'), 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'page_obj': page_obj,
            'warehouses': Warehouse.objects.filter(is_active=True),
            'filters': {
                'warehouse_id': warehouse_id,
                'status': status,
                'reservation_type': reservation_type,
                'search': search,
            }
        }
        
        return render(request, 'product/reservations/list.html', context)
        
    except Exception as e:
        messages.error(request, f'خطأ في تحميل قائمة الحجوزات: {e}')
        return redirect('product:reservation_dashboard')


# تم تعطيل نظام انتهاء الصلاحية - غير مطلوب للمنتجات العادية
# @login_required
def expiry_dashboard_disabled(request):
    """
    لوحة تحكم انتهاء الصلاحية
    """
    try:
        from ..services.expiry_service import ExpiryService
        from ..models.expiry_tracking import ProductBatch, ExpiryAlert
        
        # فلاتر البحث
        warehouse_id = request.GET.get('warehouse')
        days_ahead = int(request.GET.get('days_ahead', 90))
        
        warehouse = None
        if warehouse_id:
            warehouse = get_object_or_404(Warehouse, id=warehouse_id)
        
        # الحصول على تقرير انتهاء الصلاحية
        expiry_report = ExpiryService.get_expiry_report(warehouse, days_ahead)
        
        # الحصول على التنبيهات الحديثة غير المقروءة
        recent_alerts = ExpiryAlert.objects.select_related(
            'batch__product', 'batch__warehouse'
        ).filter(
            is_acknowledged=False,
            batch__warehouse=warehouse if warehouse else models.Q()
        ).order_by('-created_at')[:10]
        
        context = {
            'expiry_report': expiry_report,
            'recent_alerts': recent_alerts,
            'warehouses': Warehouse.objects.filter(is_active=True),
            'filters': {
                'warehouse_id': warehouse_id,
                'days_ahead': days_ahead,
            }
        }
        
        return render(request, 'product/expiry/dashboard.html', context)
        
    except Exception as e:
        messages.error(request, f'خطأ في تحميل لوحة تحكم انتهاء الصلاحية: {e}')
        return redirect('product:inventory_dashboard')


# تم تعطيل إدارة الدفعات - غير مطلوب في النظام التجاري
# @login_required
def batch_list_disabled(request):
    """
    قائمة دفعات المنتجات
    """
    try:
        from ..models.expiry_tracking import ProductBatch
        
        # فلاتر البحث
        warehouse_id = request.GET.get('warehouse')
        status = request.GET.get('status', 'active')
        expiry_status = request.GET.get('expiry_status')
        search = request.GET.get('search')
        
        # بناء الاستعلام
        queryset = ProductBatch.objects.select_related(
            'product', 'warehouse', 'supplier'
        )
        
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)
        
        if status:
            queryset = queryset.filter(status=status)
        
        if search:
            queryset = queryset.filter(
                models.Q(product__name__icontains=search) |
                models.Q(batch_number__icontains=search) |
                models.Q(supplier_batch_number__icontains=search)
            )
        
        # فلترة حسب حالة انتهاء الصلاحية
        if expiry_status:
            today = timezone.now().date()
            if expiry_status == 'expired':
                queryset = queryset.filter(expiry_date__lt=today)
            elif expiry_status == 'critical':
                queryset = queryset.filter(
                    expiry_date__gte=today,
                    expiry_date__lte=today + timedelta(days=7)
                )
            elif expiry_status == 'warning':
                queryset = queryset.filter(
                    expiry_date__gt=today + timedelta(days=7),
                    expiry_date__lte=today + timedelta(days=30)
                )
        
        # ترقيم الصفحات
        paginator = Paginator(queryset.order_by('expiry_date', 'batch_number'), 25)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'page_obj': page_obj,
            'warehouses': Warehouse.objects.filter(is_active=True),
            'filters': {
                'warehouse_id': warehouse_id,
                'status': status,
                'expiry_status': expiry_status,
                'search': search,
            }
        }
        
        return render(request, 'product/expiry/batch_list.html', context)
        
    except Exception as e:
        messages.error(request, f'خطأ في تحميل قائمة الدفعات: {e}')
        return redirect('product:expiry_dashboard')


# تم تعطيل API إنشاء الحجوزات - غير مطلوب
# @login_required
def create_reservation_api_disabled(request):
    """
    API لإنشاء حجز جديد
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'طريقة غير مدعومة'})
    
    try:
        from ..services.reservation_service import ReservationService
        
        # استخراج البيانات
        product_id = request.POST.get('product_id')
        warehouse_id = request.POST.get('warehouse_id')
        quantity = int(request.POST.get('quantity'))
        reservation_type = request.POST.get('reservation_type', 'manual')
        expires_in_days = int(request.POST.get('expires_in_days', 7))
        priority = int(request.POST.get('priority', 5))
        notes = request.POST.get('notes')
        
        # التحقق من البيانات
        product = get_object_or_404(Product, id=product_id)
        warehouse = get_object_or_404(Warehouse, id=warehouse_id)
        
        # إنشاء الحجز
        reservation = ReservationService.create_reservation(
            product=product,
            warehouse=warehouse,
            quantity=quantity,
            reservation_type=reservation_type,
            user=request.user,
            expires_in_days=expires_in_days,
            priority=priority,
            notes=notes
        )
        
        return JsonResponse({
            'success': True,
            'message': f'تم إنشاء الحجز بنجاح - {reservation.reservation_id}',
            'reservation_id': str(reservation.reservation_id)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


# تم تعطيل API تنبيهات انتهاء الصلاحية - غير مطلوب
# @login_required
def acknowledge_expiry_alert_api_disabled(request):
    """
    API للاطلاع على تنبيه انتهاء الصلاحية
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'طريقة غير مدعومة'})
    
    try:
        from ..models.expiry_tracking import ExpiryAlert
        
        alert_id = request.POST.get('alert_id')
        action_taken = request.POST.get('action_taken')
        
        alert = get_object_or_404(ExpiryAlert, id=alert_id)
        alert.acknowledge(request.user, action_taken)
        
        return JsonResponse({
            'success': True,
            'message': 'تم الاطلاع على التنبيه بنجاح'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
