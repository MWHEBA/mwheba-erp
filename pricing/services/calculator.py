"""
خدمة الحسابات الرئيسية للتسعير
"""
from decimal import Decimal
from django.conf import settings
from ..models import PricingOrder
from supplier.models import PaperServiceDetails, DigitalPrintingDetails, PlateServiceDetails


class PricingCalculatorService:
    """خدمة حسابات التسعير الرئيسية"""
    
    def __init__(self, pricing_order):
        self.order = pricing_order
        
    def calculate_all_costs(self):
        """حساب جميع التكاليف"""
        try:
            # حساب تكلفة المواد
            material_cost = self.calculate_material_cost()
            
            # حساب تكلفة الطباعة
            printing_cost = self.calculate_printing_cost()
            
            # حساب تكلفة الزنكات
            plates_cost = self.calculate_plates_cost()
            
            # حساب تكلفة التشطيب
            finishing_cost = self.calculate_finishing_cost()
            
            # حساب التكلفة الإجمالية
            total_cost = (
                material_cost + 
                printing_cost + 
                plates_cost + 
                finishing_cost + 
                self.order.extra_cost
            )
            
            # حساب سعر البيع
            sale_price = self.calculate_sale_price(total_cost)
            
            # تحديث النموذج
            self.order.material_cost = material_cost
            self.order.printing_cost = printing_cost
            self.order.plates_cost = plates_cost
            self.order.finishing_cost = finishing_cost
            self.order.total_cost = total_cost
            self.order.sale_price = sale_price
            
            return {
                'material_cost': material_cost,
                'printing_cost': printing_cost,
                'plates_cost': plates_cost,
                'finishing_cost': finishing_cost,
                'total_cost': total_cost,
                'sale_price': sale_price,
                'success': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def calculate_material_cost(self):
        """حساب تكلفة المواد"""
        if not self.order.paper_type or not self.order.paper_size:
            return Decimal('0.00')
        
        try:
            # البحث عن خدمة الورق
            paper_service = PaperServiceDetails.find_paper_service(
                supplier_id=self.order.supplier.id if self.order.supplier else None,
                paper_type_id=self.order.paper_type.id,
                paper_size_id=self.order.paper_size.id,
                weight=self.order.paper_weight
            )
            
            if paper_service:
                # حساب عدد الأوراق المطلوبة
                sheets_needed = self.calculate_sheets_needed()
                
                # حساب التكلفة
                if paper_service.sheet_type == 'sheet':
                    cost = sheets_needed * paper_service.price_per_sheet
                else:  # roll
                    # حساب الوزن المطلوب
                    paper_area = self.order.paper_size.width * self.order.paper_size.height / 10000  # متر مربع
                    weight_needed = sheets_needed * paper_area * self.order.paper_weight / 1000  # كيلو
                    cost = weight_needed * paper_service.price_per_kg
                
                return cost
                
        except Exception as e:
            print(f"خطأ في حساب تكلفة المواد: {e}")
        
        return Decimal('0.00')
    
    def calculate_sheets_needed(self):
        """حساب عدد الأوراق المطلوبة"""
        sheets = self.order.quantity
        
        # إضافة أوراق المحتوى الداخلي
        if self.order.has_internal_content and hasattr(self.order, 'internal_content'):
            internal_sheets = self.order.quantity * self.order.internal_content.page_count
            sheets += internal_sheets
        
        # إضافة نسبة الهدر (5%)
        waste_percentage = Decimal('0.05')
        sheets_with_waste = sheets * (Decimal('1.0') + waste_percentage)
        
        return int(sheets_with_waste)
    
    def calculate_printing_cost(self):
        """حساب تكلفة الطباعة"""
        if not self.order.supplier:
            return Decimal('0.00')
        
        try:
            if self.order.order_type == 'digital':
                return self._calculate_digital_printing_cost()
            elif self.order.order_type == 'offset':
                return self._calculate_offset_printing_cost()
        except Exception as e:
            print(f"خطأ في حساب تكلفة الطباعة: {e}")
        
        return Decimal('0.00')
    
    def _calculate_digital_printing_cost(self):
        """حساب تكلفة الطباعة الرقمية"""
        # البحث عن خدمة الطباعة الرقمية
        color_type = 'color' if (self.order.colors_front + self.order.colors_back) > 1 else 'bw'
        
        digital_service = DigitalPrintingDetails.objects.filter(
            supplier=self.order.supplier,
            paper_size=self.order.paper_size,
            color_type=color_type
        ).first()
        
        if digital_service:
            copies_needed = self.order.quantity
            
            # مضاعفة العدد للطباعة على الوجهين
            if hasattr(self.order.print_sides, 'name') and self.order.print_sides.name in ['وجهين', 'double']:
                copies_needed *= 2
            
            cost = copies_needed * digital_service.price_per_copy
            return cost
        
        return Decimal('0.00')
    
    def _calculate_offset_printing_cost(self):
        """حساب تكلفة الطباعة الأوفست"""
        # حساب مبسط للطباعة الأوفست
        base_cost = Decimal('0.10')  # تكلفة أساسية لكل نسخة
        
        # مضاعف الألوان
        total_colors = self.order.colors_front + self.order.colors_back
        color_multiplier = Decimal('1.0') + (total_colors * Decimal('0.25'))
        
        # خصم الكمية
        if self.order.quantity >= 1000:
            quantity_discount = Decimal('0.8')  # خصم 20%
        elif self.order.quantity >= 500:
            quantity_discount = Decimal('0.9')  # خصم 10%
        else:
            quantity_discount = Decimal('1.0')  # بدون خصم
        
        cost = base_cost * color_multiplier * quantity_discount * self.order.quantity
        return cost
    
    def calculate_plates_cost(self):
        """حساب تكلفة الزنكات"""
        if self.order.order_type != 'offset':
            return Decimal('0.00')
        
        total_cost = Decimal('0.00')
        
        try:
            # جمع تكاليف جميع الزنكات المرتبطة
            ctp_plates = self.order.ctp_plates.all()
            for plate in ctp_plates:
                total_cost += plate.total_cost
        except Exception as e:
            print(f"خطأ في حساب تكلفة الزنكات: {e}")
        
        return total_cost
    
    def calculate_finishing_cost(self):
        """حساب تكلفة التشطيب"""
        total_cost = Decimal('0.00')
        
        try:
            # جمع تكاليف خدمات التشطيب
            finishing_services = self.order.finishing_services.all()
            for service in finishing_services:
                total_cost += service.total_price
            
            # إضافة تكلفة التغطية
            if self.order.coating_service:
                coating_cost = self.order.coating_service.unit_price * self.order.quantity
                total_cost += coating_cost
                
        except Exception as e:
            print(f"خطأ في حساب تكلفة التشطيب: {e}")
        
        return total_cost
    
    def calculate_sale_price(self, total_cost):
        """حساب سعر البيع"""
        if self.order.profit_margin <= 0:
            return total_cost
        
        # حساب السعر مع هامش الربح
        sale_price = total_cost * (Decimal('1.0') + (self.order.profit_margin / Decimal('100.0')))
        
        # إضافة ضريبة القيمة المضافة إن وجدت
        vat_setting = getattr(settings, 'VAT_ENABLED', False)
        if vat_setting:
            vat_rate = getattr(settings, 'VAT_PERCENTAGE', 15) / 100
            sale_price = sale_price * (Decimal('1.0') + Decimal(str(vat_rate)))
        
        return sale_price
    
    def get_cost_breakdown(self):
        """الحصول على تفصيل التكاليف"""
        return {
            'material_cost': self.order.material_cost,
            'printing_cost': self.order.printing_cost,
            'plates_cost': self.order.plates_cost,
            'finishing_cost': self.order.finishing_cost,
            'extra_cost': self.order.extra_cost,
            'total_cost': self.order.total_cost,
            'profit_margin': self.order.profit_margin,
            'profit_amount': self.order.sale_price - self.order.total_cost,
            'sale_price': self.order.sale_price,
            'unit_price': self.order.sale_price / self.order.quantity if self.order.quantity > 0 else Decimal('0.00')
        }
    
    @staticmethod
    def calculate_order_costs(order_id):
        """حساب تكاليف طلب معين"""
        try:
            order = PricingOrder.objects.get(id=order_id)
            calculator = PricingCalculatorService(order)
            return calculator.calculate_all_costs()
        except PricingOrder.DoesNotExist:
            return {'success': False, 'error': 'الطلب غير موجود'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
