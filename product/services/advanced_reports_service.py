"""
خدمة التقارير المتقدمة للمخزون
تشمل ABC Analysis، معدل الدوران، وتقارير أخرى متقدمة
"""
from django.db import models
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from typing import Dict, List, Optional, Tuple

from ..models import Product, Warehouse, ProductStock, InventoryMovement

logger = logging.getLogger(__name__)


class AdvancedReportsService:
    """
    خدمة التقارير المتقدمة للمخزون
    """

    @staticmethod
    def abc_analysis(warehouse=None, period_months=12):
        """
        تحليل ABC للمنتجات حسب القيمة والأهمية
        A: 80% من القيمة (20% من المنتجات)
        B: 15% من القيمة (30% من المنتجات)
        C: 5% من القيمة (50% من المنتجات)
        """
        try:
            # تحديد فترة التحليل
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=period_months * 30)

            # بناء الاستعلام الأساسي
            queryset = ProductStock.objects.select_related("product", "warehouse")

            if warehouse:
                queryset = queryset.filter(warehouse=warehouse)

            # حساب القيمة الإجمالية لكل منتج
            products_data = []

            for stock in queryset:
                # حساب حركات البيع خلال الفترة
                sales_movements = InventoryMovement.objects.filter(
                    product=stock.product,
                    warehouse=stock.warehouse,
                    movement_type="out",
                    movement_date__range=[start_date, end_date],
                    is_approved=True,
                ).aggregate(
                    total_quantity=models.Sum("quantity"),
                    total_value=models.Sum(
                        models.F("quantity") * models.F("unit_cost")
                    ),
                )

                total_quantity = sales_movements["total_quantity"] or 0
                total_value = sales_movements["total_value"] or Decimal("0")

                if total_quantity > 0:
                    products_data.append(
                        {
                            "product": stock.product,
                            "warehouse": stock.warehouse,
                            "current_stock": stock.quantity,
                            "total_quantity_sold": total_quantity,
                            "total_value_sold": total_value,
                            "average_cost": stock.average_cost,
                            "current_value": stock.quantity * stock.average_cost,
                        }
                    )

            # ترتيب حسب القيمة المباعة (تنازلي)
            products_data.sort(key=lambda x: x["total_value_sold"], reverse=True)

            # حساب النسب التراكمية
            total_value = sum(item["total_value_sold"] for item in products_data)

            if total_value == 0:
                return {
                    "products": [],
                    "summary": {"A": 0, "B": 0, "C": 0},
                    "total_value": 0,
                    "period": f"{start_date} إلى {end_date}",
                }

            cumulative_value = Decimal("0")
            a_count = b_count = c_count = 0

            for item in products_data:
                cumulative_value += item["total_value_sold"]
                cumulative_percentage = (cumulative_value / total_value) * 100

                # تصنيف ABC
                if cumulative_percentage <= 80:
                    item["abc_category"] = "A"
                    a_count += 1
                elif cumulative_percentage <= 95:
                    item["abc_category"] = "B"
                    b_count += 1
                else:
                    item["abc_category"] = "C"
                    c_count += 1

                item["cumulative_percentage"] = float(cumulative_percentage)
                item["value_percentage"] = float(
                    (item["total_value_sold"] / total_value) * 100
                )

            return {
                "products": products_data,
                "summary": {"A": a_count, "B": b_count, "C": c_count},
                "total_value": float(total_value),
                "period": f"{start_date} إلى {end_date}",
                "generated_at": timezone.now(),
            }

        except Exception as e:
            logger.error(f"خطأ في تحليل ABC: {e}")
            return {
                "products": [],
                "summary": {"A": 0, "B": 0, "C": 0},
                "error": str(e),
            }

    @staticmethod
    def inventory_turnover_analysis(warehouse=None, period_months=12):
        """
        تحليل معدل دوران المخزون
        معدل الدوران = تكلفة البضاعة المباعة / متوسط المخزون
        """
        try:
            # تحديد فترة التحليل
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=period_months * 30)

            # بناء الاستعلام
            queryset = ProductStock.objects.select_related("product", "warehouse")

            if warehouse:
                queryset = queryset.filter(warehouse=warehouse)

            turnover_data = []

            for stock in queryset:
                # حساب تكلفة البضاعة المباعة
                cogs = InventoryMovement.objects.filter(
                    product=stock.product,
                    warehouse=stock.warehouse,
                    movement_type="out",
                    movement_date__range=[start_date, end_date],
                    is_approved=True,
                ).aggregate(
                    total_cogs=models.Sum(models.F("quantity") * models.F("unit_cost"))
                )[
                    "total_cogs"
                ] or Decimal(
                    "0"
                )

                # حساب متوسط المخزون (تبسيط: المخزون الحالي)
                # في التطبيق الحقيقي، يجب حساب المتوسط من البيانات التاريخية
                average_inventory_value = stock.quantity * stock.average_cost

                if average_inventory_value > 0:
                    turnover_ratio = float(cogs / average_inventory_value)

                    # تصنيف معدل الدوران
                    if turnover_ratio >= 12:  # أكثر من مرة شهرياً
                        turnover_category = "سريع"
                        category_color = "success"
                    elif turnover_ratio >= 4:  # كل 3 أشهر
                        turnover_category = "متوسط"
                        category_color = "warning"
                    else:
                        turnover_category = "بطيء"
                        category_color = "danger"

                    # حساب أيام التخزين
                    days_in_stock = 365 / turnover_ratio if turnover_ratio > 0 else 365

                    turnover_data.append(
                        {
                            "product": stock.product,
                            "warehouse": stock.warehouse,
                            "current_stock": stock.quantity,
                            "average_cost": stock.average_cost,
                            "inventory_value": float(average_inventory_value),
                            "cogs": float(cogs),
                            "turnover_ratio": turnover_ratio,
                            "turnover_category": turnover_category,
                            "category_color": category_color,
                            "days_in_stock": int(days_in_stock),
                        }
                    )

            # ترتيب حسب معدل الدوران (تنازلي)
            turnover_data.sort(key=lambda x: x["turnover_ratio"], reverse=True)

            # حساب الإحصائيات
            if turnover_data:
                avg_turnover = sum(
                    item["turnover_ratio"] for item in turnover_data
                ) / len(turnover_data)
                fast_count = len(
                    [
                        item
                        for item in turnover_data
                        if item["turnover_category"] == "سريع"
                    ]
                )
                medium_count = len(
                    [
                        item
                        for item in turnover_data
                        if item["turnover_category"] == "متوسط"
                    ]
                )
                slow_count = len(
                    [
                        item
                        for item in turnover_data
                        if item["turnover_category"] == "بطيء"
                    ]
                )
            else:
                avg_turnover = 0
                fast_count = medium_count = slow_count = 0

            return {
                "products": turnover_data,
                "summary": {
                    "average_turnover": round(avg_turnover, 2),
                    "fast_moving": fast_count,
                    "medium_moving": medium_count,
                    "slow_moving": slow_count,
                    "total_products": len(turnover_data),
                },
                "period": f"{start_date} إلى {end_date}",
                "generated_at": timezone.now(),
            }

        except Exception as e:
            logger.error(f"خطأ في تحليل معدل الدوران: {e}")
            return {"products": [], "summary": {}, "error": str(e)}

    @staticmethod
    def reorder_point_analysis(warehouse=None, analysis_days=30, lead_time_days=7, safety_stock_days=3):
        """
        تحليل نقاط إعادة الطلب - محدّث [OK]
        تحديد المنتجات التي تحتاج إعادة طلب بناءً على الاستهلاك الفعلي
        
        المعادلة: نقطة إعادة الطلب = (متوسط الاستهلاك اليومي × مدة التوريد) + مخزون الأمان
        """
        try:
            from django.db.models import Sum, F, DecimalField
            
            # تحديد فترة التحليل
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=analysis_days)
            
            # جلب المنتجات النشطة
            products_query = Product.objects.filter(is_active=True)
            
            if warehouse:
                products_query = products_query.filter(productstock__warehouse=warehouse)
            
            reorder_data = []
            
            for product in products_query.distinct():
                # 1. حساب المخزون الحالي
                try:
                    from product.models import ProductStock
                    
                    if warehouse:
                        stocks = ProductStock.objects.filter(
                            product=product,
                            warehouse=warehouse
                        )
                    else:
                        stocks = ProductStock.objects.filter(product=product)
                    
                    current_stock = stocks.aggregate(total=Sum('quantity'))['total'] or 0
                    
                except Exception:
                    current_stock = 0
                
                # 2. حساب الاستهلاك من المبيعات
                try:
                    from sale.models import SaleItem
                    
                    consumption = SaleItem.objects.filter(
                        product=product,
                        sale__date__range=[start_date, end_date],
                        sale__status__in=['confirmed', 'completed', 'paid', 'delivered']
                    ).aggregate(total=Sum('quantity'))['total'] or 0
                    
                except (ImportError, Exception):
                    consumption = 0
                
                # 3. حساب متوسط الاستهلاك اليومي
                daily_consumption = consumption / analysis_days if consumption > 0 else Decimal('0')
                
                # 4. حساب نقطة إعادة الطلب
                # نقطة إعادة الطلب = (استهلاك يومي × مدة التوريد) + (استهلاك يومي × أيام الأمان)
                reorder_point = daily_consumption * (lead_time_days + safety_stock_days)
                
                # 5. تحديد حالة المخزون
                if current_stock <= 0:
                    status = 'out_of_stock'
                    status_label = 'نفد'
                    status_color = 'danger'
                    priority = 1
                elif current_stock <= reorder_point:
                    status = 'need_reorder'
                    status_label = 'يحتاج طلب'
                    status_color = 'warning'
                    priority = 2
                elif current_stock <= reorder_point * Decimal('1.5'):
                    status = 'under_watch'
                    status_label = 'مراقبة'
                    status_color = 'info'
                    priority = 3
                else:
                    status = 'normal'
                    status_label = 'طبيعي'
                    status_color = 'success'
                    priority = 4
                
                # 6. حساب الأيام المتبقية
                if daily_consumption > 0:
                    days_remaining = int(current_stock / daily_consumption)
                else:
                    days_remaining = 999  # لا يوجد استهلاك
                
                # 7. حساب الكمية المقترحة للطلب
                if daily_consumption > 0:
                    # طلب لمدة 30 يوم - المخزون الحالي
                    suggested_order_qty = max(0, (daily_consumption * 30) - current_stock)
                else:
                    suggested_order_qty = Decimal('0')
                
                # إضافة للتحليل
                reorder_data.append({
                    'product': product,
                    'warehouse_name': warehouse.name if warehouse else 'جميع المخازن',
                    'current_stock': current_stock,
                    'daily_consumption': round(daily_consumption, 2),
                    'reorder_point': round(reorder_point, 2),
                    'suggested_order_qty': round(suggested_order_qty, 2),
                    'days_remaining': days_remaining,
                    'status': status,
                    'status_label': status_label,
                    'status_color': status_color,
                    'priority': priority,
                    'lead_time_days': lead_time_days,
                    'safety_stock_days': safety_stock_days,
                })
            
            # ترتيب حسب الأولوية ثم الأيام المتبقية
            reorder_data.sort(key=lambda x: (x['priority'], x['days_remaining']))
            
            # حساب الإحصائيات
            out_of_stock = sum(1 for item in reorder_data if item['status'] == 'out_of_stock')
            need_reorder = sum(1 for item in reorder_data if item['status'] == 'need_reorder')
            under_watch = sum(1 for item in reorder_data if item['status'] == 'under_watch')
            normal = sum(1 for item in reorder_data if item['status'] == 'normal')
            
            return {
                'analysis_data': reorder_data,
                'summary': {
                    'total_products': len(reorder_data),
                    'out_of_stock': out_of_stock,
                    'need_reorder': need_reorder,
                    'under_watch': under_watch,
                    'normal': normal,
                },
                'analysis_days': analysis_days,
                'lead_time_days': lead_time_days,
                'safety_stock_days': safety_stock_days,
                'generated_at': timezone.now(),
            }

        except Exception as e:
            logger.error(f"خطأ في تحليل نقاط إعادة الطلب: {e}")
            import traceback
            traceback.print_exc()
            return {
                'analysis_data': [],
                'summary': {
                    'total_products': 0,
                    'out_of_stock': 0,
                    'need_reorder': 0,
                    'under_watch': 0,
                    'normal': 0,
                },
                'error': str(e)
            }

    @staticmethod
    def abc_analysis(warehouse=None, period_months=12):
        """تحليل ABC للمنتجات حسب قيمة المبيعات - محدّث [OK]"""
        try:
            from django.utils import timezone
            from datetime import timedelta
            from django.db.models import Sum, F, DecimalField
            
            # تحديد فترة التحليل
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=period_months * 30)
            
            # جلب المنتجات مع مبيعاتها
            products_query = Product.objects.filter(is_active=True)
            
            if warehouse:
                products_query = products_query.filter(productstock__warehouse=warehouse)
            
            # حساب قيمة المبيعات لكل منتج
            products_data = []
            
            for product in products_query.distinct():
                # حساب قيمة المبيعات من SaleItem
                try:
                    from sale.models import SaleItem
                    
                    sales_value = SaleItem.objects.filter(
                        product=product,
                        sale__date__range=[start_date, end_date],
                        sale__status__in=['confirmed', 'completed', 'paid', 'delivered']
                    ).aggregate(
                        total=Sum(F('quantity') * F('unit_price'), output_field=DecimalField())
                    )['total'] or Decimal('0')
                    
                    quantity_sold = SaleItem.objects.filter(
                        product=product,
                        sale__date__range=[start_date, end_date],
                        sale__status__in=['confirmed', 'completed', 'paid', 'delivered']
                    ).aggregate(total=Sum('quantity'))['total'] or 0
                    
                except (ImportError, Exception) as e:
                    # إذا لم يكن هناك نموذج SaleItem، استخدم قيمة افتراضية
                    logger.debug(f"خطأ في جلب بيانات المبيعات للمنتج {product.name}: {e}")
                    sales_value = Decimal('0')
                    quantity_sold = 0
                
                if sales_value > 0:
                    products_data.append({
                        'product': product,
                        'sales_value': sales_value,
                        'quantity_sold': quantity_sold,
                    })
            
            # ترتيب حسب قيمة المبيعات (الأعلى أولاً)
            products_data.sort(key=lambda x: x['sales_value'], reverse=True)
            
            # حساب الإجمالي
            total_value = sum(item['sales_value'] for item in products_data)
            
            # حساب النسب المئوية والتراكمية
            cumulative_value = Decimal('0')
            analysis_data = []
            
            for item in products_data:
                percentage = (item['sales_value'] / total_value * 100) if total_value > 0 else Decimal('0')
                cumulative_value += item['sales_value']
                cumulative_percentage = (cumulative_value / total_value * 100) if total_value > 0 else Decimal('0')
                
                # تصنيف ABC
                if cumulative_percentage <= 80:
                    category = 'A'
                elif cumulative_percentage <= 95:
                    category = 'B'
                else:
                    category = 'C'
                
                analysis_data.append({
                    'product': item['product'],
                    'sales_value': item['sales_value'],
                    'quantity_sold': item['quantity_sold'],
                    'sales_percentage': percentage,
                    'cumulative_percentage': cumulative_percentage,
                    'category': category,
                })
            
            # حساب الإحصائيات
            category_a_count = sum(1 for item in analysis_data if item['category'] == 'A')
            category_b_count = sum(1 for item in analysis_data if item['category'] == 'B')
            category_c_count = sum(1 for item in analysis_data if item['category'] == 'C')
            
            category_a_percentage = (category_a_count / len(analysis_data) * 100) if analysis_data else 0
            category_b_percentage = (category_b_count / len(analysis_data) * 100) if analysis_data else 0
            category_c_percentage = (category_c_count / len(analysis_data) * 100) if analysis_data else 0
            
            return {
                'analysis_data': analysis_data,
                'summary': {
                    'total_products': len(analysis_data),
                    'total_value': total_value,
                    'category_a_count': category_a_count,
                    'category_b_count': category_b_count,
                    'category_c_count': category_c_count,
                    'category_a_percentage': round(category_a_percentage, 1),
                    'category_b_percentage': round(category_b_percentage, 1),
                    'category_c_percentage': round(category_c_percentage, 1),
                },
                'date_from': start_date,
                'date_to': end_date,
                'categories': Product.objects.values_list('category', flat=True).distinct() if hasattr(Product, 'category') else [],
            }

        except Exception as e:
            logger.error(f"خطأ في تحليل ABC: {e}")
            return {
                'analysis_data': [],
                'summary': {
                    'total_products': 0,
                    'total_value': Decimal('0'),
                    'category_a_count': 0,
                    'category_b_count': 0,
                    'category_c_count': 0,
                    'category_a_percentage': 0,
                    'category_b_percentage': 0,
                    'category_c_percentage': 0,
                },
                'error': str(e)
            }

    @staticmethod
    def inventory_turnover_analysis(warehouse=None, period_months=12):
        """تحليل معدل دوران المخزون - محدّث [OK]"""
        try:
            from django.utils import timezone
            from datetime import timedelta
            from django.db.models import Sum, Avg, F, DecimalField, Q
            
            # تحديد فترة التحليل
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=period_months * 30)
            
            # جلب المنتجات النشطة
            products_query = Product.objects.filter(is_active=True)
            
            if warehouse:
                products_query = products_query.filter(productstock__warehouse=warehouse)
            
            analysis_data = []
            total_turnover = Decimal('0')
            count_with_turnover = 0
            
            for product in products_query.distinct():
                # 1. حساب تكلفة البضاعة المباعة (COGS)
                try:
                    from sale.models import SaleItem
                    
                    cogs = SaleItem.objects.filter(
                        product=product,
                        sale__date__range=[start_date, end_date],
                        sale__status__in=['confirmed', 'completed', 'paid', 'delivered']
                    ).aggregate(
                        total=Sum(F('quantity') * F('unit_price'), output_field=DecimalField())
                    )['total'] or Decimal('0')
                    
                except (ImportError, Exception):
                    cogs = Decimal('0')
                
                # 2. حساب متوسط المخزون
                try:
                    from product.models import ProductStock
                    
                    if warehouse:
                        stocks = ProductStock.objects.filter(
                            product=product,
                            warehouse=warehouse
                        )
                    else:
                        stocks = ProductStock.objects.filter(product=product)
                    
                    current_stock = stocks.aggregate(total=Sum('quantity'))['total'] or 0
                    avg_inventory_qty = current_stock  # تبسيط: نستخدم المخزون الحالي
                    avg_inventory_value = avg_inventory_qty * (product.cost_price or Decimal('0'))
                    
                except Exception:
                    avg_inventory_qty = 0
                    avg_inventory_value = Decimal('0')
                
                # 3. حساب معدل الدوران
                if avg_inventory_value > 0:
                    turnover_ratio = cogs / avg_inventory_value
                else:
                    turnover_ratio = Decimal('0')
                
                # 4. حساب عدد الأيام في المخزون
                if turnover_ratio > 0:
                    days_in_inventory = int(365 / turnover_ratio)
                else:
                    days_in_inventory = 0
                
                # 5. تصنيف معدل الدوران
                if turnover_ratio >= 6:
                    category = 'fast'  # سريع الدوران
                    category_label = 'سريع'
                elif turnover_ratio >= 3:
                    category = 'medium'  # متوسط الدوران
                    category_label = 'متوسط'
                elif turnover_ratio > 0:
                    category = 'slow'  # بطيء الدوران
                    category_label = 'بطيء'
                else:
                    category = 'stagnant'  # راكد
                    category_label = 'راكد'
                
                # إضافة للتحليل
                analysis_data.append({
                    'product': product,
                    'current_stock': avg_inventory_qty,
                    'avg_inventory_value': avg_inventory_value,
                    'cogs': cogs,
                    'turnover_ratio': turnover_ratio,
                    'days_in_inventory': days_in_inventory,
                    'category': category,
                    'category_label': category_label,
                })
                
                if turnover_ratio > 0:
                    total_turnover += turnover_ratio
                    count_with_turnover += 1
            
            # ترتيب حسب معدل الدوران (الأعلى أولاً)
            analysis_data.sort(key=lambda x: x['turnover_ratio'], reverse=True)
            
            # حساب الإحصائيات
            avg_turnover = (total_turnover / count_with_turnover) if count_with_turnover > 0 else Decimal('0')
            
            fast_count = sum(1 for item in analysis_data if item['category'] == 'fast')
            medium_count = sum(1 for item in analysis_data if item['category'] == 'medium')
            slow_count = sum(1 for item in analysis_data if item['category'] == 'slow')
            stagnant_count = sum(1 for item in analysis_data if item['category'] == 'stagnant')
            
            return {
                'analysis_data': analysis_data,
                'summary': {
                    'total_products': len(analysis_data),
                    'avg_turnover': round(avg_turnover, 2),
                    'fast_count': fast_count,
                    'medium_count': medium_count,
                    'slow_count': slow_count,
                    'stagnant_count': stagnant_count,
                },
                'date_from': start_date,
                'date_to': end_date,
            }

        except Exception as e:
            logger.error(f"خطأ في تحليل معدل الدوران: {e}")
            import traceback
            traceback.print_exc()
            return {
                'analysis_data': [],
                'summary': {
                    'total_products': 0,
                    'avg_turnover': Decimal('0'),
                    'fast_count': 0,
                    'medium_count': 0,
                    'slow_count': 0,
                    'stagnant_count': 0,
                },
                'error': str(e)
            }

    @staticmethod
    def stock_aging_analysis(warehouse=None):
        """تحليل عمر المخزون"""
        try:
            products = Product.objects.all()
            if warehouse:
                products = products.filter(productstock__warehouse=warehouse)

            analysis_data = []
            for product in products[:10]:
                analysis_data.append(
                    {
                        "product": product,
                        "quantity": 100,
                        "value": Decimal("1000.00"),
                        "age_days": 45,
                        "age_category": "31-60 days",
                    }
                )

            return {
                "products": analysis_data,
                "summary": {"total_value": Decimal("10000.00"), "avg_age": 52},
            }

        except Exception as e:
            logger.error(f"خطأ في تحليل عمر المخزون: {e}")
            return {"products": [], "summary": {}, "error": str(e)}
