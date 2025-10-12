"""
خدمة حسابات الطباعة المتخصصة
"""
from decimal import Decimal
from supplier.models import DigitalPrintingDetails, PlateServiceDetails


class PrintCalculatorService:
    """خدمة حسابات الطباعة"""
    
    @staticmethod
    def calculate_digital_printing_cost(supplier_id, paper_size_id, quantity, color_type='color', sides=1):
        """حساب تكلفة الطباعة الرقمية"""
        try:
            # البحث عن خدمة الطباعة الرقمية
            digital_service = DigitalPrintingDetails.objects.filter(
                supplier_id=supplier_id,
                paper_size_id=paper_size_id,
                color_type=color_type,
                is_active=True
            ).first()
            
            if not digital_service:
                return {
                    'success': False,
                    'error': 'لم يتم العثور على سعر للطباعة الرقمية'
                }
            
            # التحقق من الحد الأدنى والأقصى للكمية
            if quantity < digital_service.minimum_quantity:
                return {
                    'success': False,
                    'error': f'الحد الأدنى للكمية هو {digital_service.minimum_quantity}'
                }
            
            if digital_service.maximum_quantity and quantity > digital_service.maximum_quantity:
                return {
                    'success': False,
                    'error': f'الحد الأقصى للكمية هو {digital_service.maximum_quantity}'
                }
            
            # حساب عدد النسخ المطلوبة
            copies_needed = quantity * sides
            
            # حساب التكلفة
            total_cost = copies_needed * digital_service.price_per_copy
            
            return {
                'success': True,
                'total_cost': float(total_cost),
                'price_per_copy': float(digital_service.price_per_copy),
                'copies_needed': copies_needed,
                'color_type': digital_service.get_color_type_display(),
                'supplier_name': digital_service.supplier.name,
                'minimum_quantity': digital_service.minimum_quantity,
                'maximum_quantity': digital_service.maximum_quantity
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في حساب تكلفة الطباعة الرقمية: {str(e)}'
            }
    
    @staticmethod
    def calculate_offset_printing_cost(quantity, colors_front=4, colors_back=0, paper_size_factor=1.0):
        """حساب تكلفة الطباعة الأوفست (حساب تقديري)"""
        try:
            # تكلفة أساسية لكل نسخة
            base_cost_per_copy = Decimal('0.10')
            
            # حساب إجمالي الألوان
            total_colors = colors_front + colors_back
            
            # مضاعف الألوان (كل لون يزيد التكلفة 25%)
            color_multiplier = Decimal('1.0') + (Decimal(str(total_colors)) * Decimal('0.25'))
            
            # مضاعف حجم الورق
            size_multiplier = Decimal(str(paper_size_factor))
            
            # خصم الكمية
            if quantity >= 5000:
                quantity_discount = Decimal('0.7')  # خصم 30%
            elif quantity >= 2000:
                quantity_discount = Decimal('0.8')  # خصم 20%
            elif quantity >= 1000:
                quantity_discount = Decimal('0.9')  # خصم 10%
            else:
                quantity_discount = Decimal('1.0')  # بدون خصم
            
            # حساب التكلفة الإجمالية
            cost_per_copy = base_cost_per_copy * color_multiplier * size_multiplier * quantity_discount
            total_cost = cost_per_copy * Decimal(str(quantity))
            
            # تكلفة الإعداد (Setup Cost)
            setup_cost = Decimal('200.00') * Decimal(str(total_colors))
            
            # التكلفة النهائية
            final_cost = total_cost + setup_cost
            
            return {
                'success': True,
                'total_cost': float(final_cost),
                'cost_per_copy': float(cost_per_copy),
                'setup_cost': float(setup_cost),
                'printing_cost': float(total_cost),
                'total_colors': total_colors,
                'quantity_discount_percent': float((Decimal('1.0') - quantity_discount) * Decimal('100.0')),
                'breakdown': {
                    'base_cost': float(base_cost_per_copy),
                    'color_multiplier': float(color_multiplier),
                    'size_multiplier': float(size_multiplier),
                    'quantity_discount': float(quantity_discount)
                }
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في حساب تكلفة الطباعة الأوفست: {str(e)}'
            }
    
    @staticmethod
    def calculate_plates_cost(supplier_id, plate_size_id, plates_count, transportation_included=True):
        """حساب تكلفة الزنكات"""
        try:
            # البحث عن خدمة الزنكات
            plate_service = PlateServiceDetails.find_plate_service(
                supplier_id=supplier_id,
                plate_size_id=plate_size_id
            )
            
            if not plate_service:
                return {
                    'success': False,
                    'error': 'لم يتم العثور على سعر للزنك المحدد'
                }
            
            # التحقق من الحد الأدنى للكمية
            if plates_count < plate_service.minimum_quantity:
                plates_count = plate_service.minimum_quantity
            
            # حساب التكلفة
            plates_cost = plates_count * plate_service.price_per_plate
            setup_cost = plate_service.setup_cost
            transportation_cost = plate_service.transportation_cost if transportation_included else Decimal('0.00')
            
            total_cost = plates_cost + setup_cost + transportation_cost
            
            return {
                'success': True,
                'total_cost': float(total_cost),
                'plates_cost': float(plates_cost),
                'setup_cost': float(setup_cost),
                'transportation_cost': float(transportation_cost),
                'price_per_plate': float(plate_service.price_per_plate),
                'plates_count': plates_count,
                'minimum_quantity': plate_service.minimum_quantity,
                'supplier_name': plate_service.supplier.name,
                'plate_size_name': plate_service.plate_size.name
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'خطأ في حساب تكلفة الزنكات: {str(e)}'
            }
    
    @staticmethod
    def calculate_colors_needed(colors_front, colors_back, print_sides):
        """حساب عدد الألوان المطلوبة للزنكات"""
        if print_sides in ['وجه واحد', 'single']:
            return colors_front
        elif print_sides in ['وجهين', 'double']:
            return colors_front + colors_back
        elif print_sides in ['طبع وقلب', 'work_and_turn']:
            return max(colors_front, colors_back)
        else:
            return colors_front
    
    @staticmethod
    def get_color_type_from_colors(colors_front, colors_back):
        """تحديد نوع الألوان للطباعة الرقمية"""
        total_colors = colors_front + colors_back
        
        if total_colors == 0:
            return 'bw'  # أبيض وأسود
        elif total_colors == 1:
            return 'bw'  # أبيض وأسود
        else:
            return 'color'  # ملون
    
    @staticmethod
    def get_paper_size_factor(width, height):
        """حساب مضاعف حجم الورق للتسعير"""
        # مساحة الورق بالسنتيمتر المربع
        area = width * height
        
        # مقاسات قياسية ومضاعفاتها
        if area <= 21 * 29.7:  # A4 أو أصغر
            return 1.0
        elif area <= 29.7 * 42:  # A3
            return 1.5
        elif area <= 42 * 59.4:  # A2
            return 2.0
        elif area <= 59.4 * 84.1:  # A1
            return 3.0
        else:  # A0 أو أكبر
            return 4.0
