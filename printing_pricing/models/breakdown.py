"""
نماذج تشريح بنود الشغلانة والماليات
printing_pricing/models/breakdown.py
يشمل: مواصفات الورق والمونتاج، بنود الخامات التموينية، خدمات الورش والموردين، وحسابات وملخص التكاليف (SSOT)
"""
import math
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from .base import BaseModel, PriceUnit, CalculationType
from .order import PrintingOrder


# ==============================================================================
# 1. المواصفات الهندسية ومونتاج الورق (Technical Paper Specification)
# ==============================================================================

class PaperSpecification(BaseModel):
    """
    المرجع الفني والهندسي للورق والمونتاج واستغلال الفرخ
    """
    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="paper_specs",
        verbose_name=_("الطلب")
    )
    paper_type_name = models.CharField(
        max_length=100,
        verbose_name=_("نوع الورق")
    )
    paper_weight = models.PositiveIntegerField(
        verbose_name=_("وزن الورق (جرام)")
    )
    paper_size_name = models.CharField(
        max_length=50,
        verbose_name=_("مقاس الورق")
    )
    sheet_width = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("عرض الفرخ (سم)")
    )
    sheet_height = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("طول الفرخ (سم)")
    )
    sheets_needed = models.PositiveIntegerField(
        verbose_name=_("عدد الأفرخ المطلوبة")
    )
    montage_count = models.PositiveIntegerField(
        default=1,
        verbose_name=_("عدد القطع في الفرخ")
    )

    PIECE_SIZE_CHOICES = [
        ('', '-- اختر مقاس القطع --'),
        ('A4', 'A4 (21×29.7 سم)'),
        ('A5', 'A5 (14.8×21 سم)'),
        ('A6', 'A6 (10.5×14.8 سم)'),
        ('10x15', '10×15 سم'),
        ('15x20', '15×20 سم'),
        ('20x30', '20×30 سم'),
        ('custom', 'مقاس مخصص'),
    ]

    piece_size = models.CharField(
        max_length=50,
        choices=PIECE_SIZE_CHOICES,
        blank=True,
        null=True,
        verbose_name=_("مقاس القطع")
    )
    sheet_cost = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة الفرخ")
    )
    total_paper_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("إجمالي تكلفة الورق")
    )

    class Meta:
        db_table = "printing_pricing_paperspecification"
        verbose_name = _("مواصفات الورق")
        verbose_name_plural = _("مواصفات الأوراق")

    def __str__(self):
        return f"{self.paper_type_name} - {self.order.order_number}"

    def save(self, *args, **kwargs):
        self.calculate_total_cost()
        super().save(*args, **kwargs)

    def calculate_total_cost(self):
        if self.sheets_needed and self.sheet_cost:
            self.total_paper_cost = self.sheets_needed * self.sheet_cost
        else:
            self.total_paper_cost = Decimal('0.00')

    @property
    def sheet_area(self):
        if self.sheet_width and self.sheet_height:
            return self.sheet_width * self.sheet_height
        return Decimal('0.00')

    def calculate_sheets_needed(self, total_pieces, montage_count=None):
        if montage_count:
            self.montage_count = montage_count
        if self.montage_count > 0:
            self.sheets_needed = math.ceil(total_pieces / self.montage_count)
        else:
            self.sheets_needed = total_pieces


# ==============================================================================
# 2. بنود الخامات التموينية (Procurement Materials Breakdown)
# ==============================================================================

class OrderMaterial(BaseModel):
    """
    المرجع المحاسبي والتمويني لبنود المواد الخام لأمر الشغل (ورق، زنكات، أحبار، كرتون)
    يغذي مباشرة خدمة توليد أوامر الشراء للموردين (ProcurementBridgeService)
    """
    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="materials",
        verbose_name=_("الطلب")
    )
    material_type = models.CharField(
        max_length=50,
        verbose_name=_("نوع المادة"),
        help_text=_("ورق، حبر، زنكات، إلخ")
    )
    material_name = models.CharField(
        max_length=200,
        verbose_name=_("اسم المادة")
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name=_("الكمية المطلوبة")
    )
    unit = models.CharField(
        max_length=20,
        choices=PriceUnit.choices,
        verbose_name=_("الوحدة")
    )
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة الوحدة")
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("التكلفة الإجمالية")
    )
    waste_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('5.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("نسبة الهالك (%)")
    )
    supplier_info = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("معلومات المورد"),
        help_text=_("معلومات المورد والأسعار")
    )

    class Meta:
        db_table = "printing_pricing_ordermaterial"
        verbose_name = _("مادة الطلب")
        verbose_name_plural = _("مواد الطلبات")
        ordering = ['material_type', 'material_name']
        indexes = [
            models.Index(fields=['order', 'material_type']),
        ]

    def __str__(self):
        return f"{self.material_name} - {self.order.order_number}"

    def save(self, *args, **kwargs):
        self.calculate_total_cost()
        super().save(*args, **kwargs)

    def calculate_total_cost(self):
        if self.quantity and self.unit_cost:
            base_cost = self.quantity * self.unit_cost
            if self.waste_percentage:
                waste_multiplier = Decimal('1.00') + (self.waste_percentage / Decimal('100.00'))
                self.total_cost = base_cost * waste_multiplier
            else:
                self.total_cost = base_cost
        else:
            self.total_cost = Decimal('0.00')


# ==============================================================================
# 3. خدمات وعمليات الورش والموردين (Order Services Breakdown)
# ==============================================================================

class OrderService(BaseModel):
    """
    نموذج ربط خدمات الطباعة والتشطيب والتجليد بطلبات التسعير
    يدعم الربط المباشر بخدمات الموردين في موديول supplier
    """
    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="services",
        verbose_name=_("الطلب")
    )
    service_category = models.CharField(
        max_length=50,
        choices=[
            ('printing', _('طباعة')),
            ('finishing', _('خدمات الطباعة')),
            ('packaging', _('خدمات التقفيل')),
            ('coating', _('تغطية')),
            ('other', _('أخرى'))
        ],
        verbose_name=_("فئة الخدمة")
    )
    service_name = models.CharField(
        max_length=200,
        verbose_name=_("اسم الخدمة")
    )
    service_description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("وصف الخدمة")
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        validators=[MinValueValidator(Decimal('0.001'))],
        verbose_name=_("الكمية")
    )
    unit = models.CharField(
        max_length=20,
        choices=PriceUnit.choices,
        verbose_name=_("الوحدة")
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("سعر الوحدة")
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("التكلفة الإجمالية")
    )
    setup_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة الإعداد")
    )
    is_optional = models.BooleanField(
        default=False,
        verbose_name=_("خدمة اختيارية")
    )
    supplier_info = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("معلومات المورد"),
        help_text=_("snapshot من بيانات المورد والسعر وقت التسعير")
    )
    supplier_service = models.ForeignKey(
        'supplier.SupplierService',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_services',
        verbose_name=_("خدمة المورد"),
        help_text=_("الخدمة المحددة من المورد لهذا البند")
    )
    finishing_type = models.ForeignKey(
        'printing_pricing.FinishingType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_services',
        verbose_name=_("نوع التشطيب"),
        help_text=_("الربط بنوع التشطيب (سبوت UV، بصمة، كوفراج)")
    )
    coating_type = models.ForeignKey(
        'printing_pricing.CoatingType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_services',
        verbose_name=_("نوع التغطية/السلوفان"),
        help_text=_("الربط بنوع التغطية (سلوفان مط، لميع، كوي)")
    )
    packaging_type = models.ForeignKey(
        'printing_pricing.PackagingType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_services',
        verbose_name=_("نوع التقفيل/التجليد"),
        help_text=_("الربط بنوع التقفيل والتجليد")
    )
    execution_time = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("وقت التنفيذ (ساعات)")
    )

    class Meta:
        db_table = "printing_pricing_orderservice"
        verbose_name = _("خدمة الطلب")
        verbose_name_plural = _("خدمات الطلبات")
        ordering = ['service_category', 'service_name']
        indexes = [
            models.Index(fields=['order', 'service_category']),
        ]

    def __str__(self):
        return f"{self.service_name} - {self.order.order_number}"

    def save(self, *args, **kwargs):
        self.calculate_total_cost()
        super().save(*args, **kwargs)

    def calculate_total_cost(self):
        calculated = (self.quantity * self.unit_price + self.setup_cost) if (self.quantity and self.unit_price) else self.setup_cost
        if self.total_cost and self.total_cost > calculated:
            return
        self.total_cost = calculated

    def update_pricing(self, new_unit_price=None, new_quantity=None, new_setup_cost=None):
        if new_unit_price is not None:
            self.unit_price = new_unit_price
        if new_quantity is not None:
            self.quantity = new_quantity
        if new_setup_cost is not None:
            self.setup_cost = new_setup_cost
        self.calculate_total_cost()
        self.save()


# ==============================================================================
# 4. سجلات تتبع الحسابات اللحظية (Calculation Audit Logs)
# ==============================================================================

class CostCalculation(BaseModel):
    """
    نموذج حفظ سجلات ونتائج حسابات التكلفة اللحظية
    """
    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="calculations",
        verbose_name=_("الطلب")
    )
    calculation_type = models.CharField(
        max_length=20,
        choices=CalculationType.choices,
        verbose_name=_("نوع الحساب")
    )
    base_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("التكلفة الأساسية")
    )
    additional_costs = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("التكاليف الإضافية")
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("إجمالي التكلفة")
    )
    calculation_details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("تفاصيل الحساب"),
        help_text=_("تفاصيل مفصلة عن كيفية الحساب")
    )
    calculation_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("تاريخ الحساب")
    )
    is_current = models.BooleanField(
        default=True,
        verbose_name=_("الحساب الحالي"),
        help_text=_("هل هذا هو الحساب الأحدث لهذا النوع")
    )
    parameters_used = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("المعايير المستخدمة"),
        help_text=_("المعايير والقيم المستخدمة في الحساب")
    )

    class Meta:
        db_table = "printing_pricing_costcalculation"
        verbose_name = _("حساب التكلفة")
        verbose_name_plural = _("حسابات التكلفة")
        ordering = ['-calculation_date']
        indexes = [
            models.Index(fields=['order', 'calculation_type']),
            models.Index(fields=['calculation_date']),
            models.Index(fields=['is_current']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'calculation_type'],
                condition=models.Q(is_current=True),
                name='unique_current_calculation_per_type'
            )
        ]

    def __str__(self):
        return f"{self.get_calculation_type_display()} - {self.order.order_number}"

    def save(self, *args, **kwargs):
        if self.is_current:
            CostCalculation.objects.filter(
                order=self.order,
                calculation_type=self.calculation_type,
                is_current=True
            ).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    def add_detail(self, key, value, description=None):
        if not self.calculation_details:
            self.calculation_details = {}
        self.calculation_details[key] = {
            'value': value,
            'description': description or key,
            'timestamp': str(self.calculation_date or self.created_at)
        }

    def get_detail(self, key, default=None):
        if self.calculation_details and key in self.calculation_details:
            return self.calculation_details[key].get('value', default)
        return default


# ==============================================================================
# 5. المركز المالي الموحد للطلب (Order Summary - SSOT)
# ==============================================================================

class OrderSummary(BaseModel):
    """
    المركز المالي الموحد لطلب التسعير (Single Source of Truth)
    يحوي تفكيك التكاليف، هوامش وصافي الأرباح، والضرائب والرسوم
    """
    order = models.OneToOneField(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="summary",
        verbose_name=_("الطلب")
    )
    material_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة المواد")
    )
    printing_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة الطباعة")
    )
    finishing_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة خدمات الطباعة")
    )
    design_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة التصميم")
    )
    other_costs = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكاليف أخرى")
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("المجموع الفرعي")
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("قيمة الخصم")
    )
    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("قيمة الضريبة")
    )
    rush_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("رسوم الاستعجال")
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("إجمالي التكلفة")
    )
    profit_margin_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("هامش الربح (%)")
    )
    profit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("قيمة الربح")
    )
    final_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("السعر النهائي")
    )
    last_calculated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("آخر حساب")
    )
    calculation_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("ملاحظات الحساب")
    )

    class Meta:
        db_table = "printing_pricing_ordersummary"
        verbose_name = _("ملخص الطلب")
        verbose_name_plural = _("ملخصات الطلبات")

    def __str__(self):
        return f"ملخص - {self.order.order_number}"

    def calculate_all(self):
        self.subtotal = (
            self.material_cost + 
            self.printing_cost + 
            self.finishing_cost + 
            self.design_cost + 
            self.other_costs
        )
        self.total_cost = (
            self.subtotal - 
            self.discount_amount + 
            self.tax_amount + 
            self.rush_fee
        )
        self.profit_amount = self.total_cost * (self.profit_margin_percentage / Decimal('100.0'))
        self.final_price = self.total_cost + self.profit_amount

    def update_from_calculations(self):
        calculations = self.order.calculations.filter(is_current=True)
        for calc in calculations:
            if calc.calculation_type == CalculationType.MATERIAL:
                self.material_cost = calc.total_cost
            elif calc.calculation_type == CalculationType.PRINTING:
                self.printing_cost = calc.total_cost
            elif calc.calculation_type == CalculationType.FINISHING:
                self.finishing_cost = calc.total_cost
            elif calc.calculation_type == CalculationType.DESIGN:
                self.design_cost = calc.total_cost
        self.calculate_all()
        self.save()

    @property
    def cost_breakdown(self):
        if self.subtotal > 0:
            return {
                'material_percentage': float((self.material_cost / self.subtotal) * 100),
                'printing_percentage': float((self.printing_cost / self.subtotal) * 100),
                'finishing_percentage': float((self.finishing_cost / self.subtotal) * 100),
                'design_percentage': float((self.design_cost / self.subtotal) * 100),
                'other_percentage': float((self.other_costs / self.subtotal) * 100),
            }
        return {}


__all__ = [
    'PaperSpecification',
    'OrderMaterial',
    'OrderService',
    'CostCalculation',
    'OrderSummary',
]
