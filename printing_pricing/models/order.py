from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from decimal import Decimal
import uuid

from .base import BaseModel, PricingStatus, OrderType, ProductionStage
from customer.models import Customer


class PrintingOrder(BaseModel):
    """
    نموذج طلب التسعير المحسن
    """
    # معلومات أساسية
    order_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("رقم الطلب"),
        help_text=_("رقم فريد للطلب")
    )
    
    work_order = models.ForeignKey(
        "work_order.WorkOrder",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="printing_orders",
        verbose_name=_("أمر الشغل المرتبط")
    )
    
    currency = models.ForeignKey(
        "financial.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("العملة"),
        related_name="printing_orders"
    )
    
    exchange_rate = models.DecimalField(
        _("سعر الصرف"),
        max_digits=18,
        decimal_places=6,
        default=Decimal("1.000000")
    )
    
    delivery_address_snapshot = models.TextField(
        _("لقطة عنوان وهاتف التسليم"),
        blank=True,
        null=True
    )
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="printing_orders",
        verbose_name=_("العميل")
    )
    
    title = models.CharField(
        max_length=200,
        verbose_name=_("عنوان الطلب")
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("وصف الطلب")
    )
    
    order_type = models.CharField(
        max_length=20,
        choices=OrderType.choices,
        verbose_name=_("نوع الطلب")
    )

    product_type = models.ForeignKey(
        'ProductType',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="printing_orders",
        verbose_name=_("نوع المطبوع")
    )

    product_size = models.ForeignKey(
        'ProductSize',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="printing_orders",
        verbose_name=_("مقاس المطبوع")
    )

    print_orientation = models.CharField(
        max_length=20,
        choices=[
            ('portrait', _('طولي (رأسي)')),
            ('landscape', _('عرضي (أفقي)'))
        ],
        default='portrait',
        verbose_name=_("اتجاه الطباعة")
    )
    
    status = models.CharField(
        max_length=20,
        choices=PricingStatus.choices,
        default=PricingStatus.DRAFT,
        verbose_name=_("حالة الطلب")
    )

    current_stage = models.CharField(
        max_length=30,
        choices=ProductionStage.choices,
        default=ProductionStage.PREPRESS,
        verbose_name=_("مرحلة الإنتاج الحالية (الشغل فين؟)"),
        blank=True,
        null=True
    )

    current_workshop = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="active_printing_orders",
        verbose_name=_("الموقع / الورشة المتواجد بها الشغل حالياً")
    )
    
    # معلومات الكمية والمواصفات
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("الكمية")
    )
    
    pages_count = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("عدد الصفحات")
    )
    
    copies_count = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("عدد النسخ")
    )
    
    # معلومات الأبعاد
    width = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name=_("العرض (سم)")
    )
    
    height = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name=_("الارتفاع (سم)")
    )
    
    print_orientation = models.CharField(
        max_length=20,
        choices=[
            ('portrait', _('طولي (رأسي)')),
            ('landscape', _('عرضي (أفقي)')),
        ],
        default='portrait',
        verbose_name=_("اتجاه الطباعة")
    )
    
    is_closed_size = models.BooleanField(
        default=False,
        verbose_name=_("المقاس المدخل مقفول (مطوي)")
    )
    
    open_direction = models.CharField(
        max_length=20,
        choices=[
            ('right', _('عربي (يمين)')),
            ('left', _('إنجليزي (يسار)')),
            ('top', _('من أعلى (رأسي)')),
        ],
        default='right',
        verbose_name=_("جهة الفتح والتجليد")
    )
    
    # تقنيات الطباعة الهجينة
    cover_printing_type = models.CharField(
        max_length=20,
        choices=[
            ('offset', _('أوفست')),
            ('digital', _('ديجيتال')),
            ('digital_banner', _('خامات كبيرة')),
            ('screen', _('سلك سكرين')),
            ('none', _('بدون طباعة')),
        ],
        default='offset',
        verbose_name=_("نوع الطباعة")
    )
    
    print_sides_mode = models.CharField(
        max_length=20,
        choices=[
            ('single', _('وجه واحد')),
            ('work_sheet', _('وجهين')),
            ('work_turn', _('طبع وقلب')),
        ],
        default='single',
        verbose_name=_("عدد الأوجه")
    )
    
    digital_color_mode = models.CharField(
        max_length=20,
        choices=[
            ('4_0', _('وجه واحد ألوان (4/0)')),
            ('1_0', _('وجه واحد أسود (1/0)')),
            ('4_4', _('وجهين ألوان (4/4)')),
            ('4_1', _('وجه ألوان + ظهر أسود (4/1)')),
            ('1_1', _('وجهين أسود (1/1)')),
        ],
        default='4_0',
        verbose_name=_("نمط نقرات الديجيتال")
    )
    
    spot_colors_front = models.PositiveIntegerField(
        default=0,
        verbose_name=_("عدد الألوان المخصوصة (الوجه)")
    )
    
    spot_colors_back = models.PositiveIntegerField(
        default=0,
        verbose_name=_("عدد الألوان المخصوصة (الظهر)")
    )
    
    banner_sqm_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('50.00'),
        verbose_name=_("سعر المتر المربع للخامات الكبيرة")
    )
    
    has_white_ink = models.BooleanField(
        default=False,
        verbose_name=_("طباعة طبقة حبر أبيض للشفافيات والـ UV")
    )
    
    inner_printing_type = models.CharField(
        max_length=20,
        choices=[
            ('offset', _('أوفست')),
            ('digital', _('ديجيتال')),
        ],
        default='offset',
        verbose_name=_("نوع طباعة الداخلي")
    )
    
    inner_print_sides_mode = models.CharField(
        max_length=20,
        choices=[
            ('single', _('وجه واحد')),
            ('work_sheet', _('وجهين')),
            ('work_turn', _('طبع وقلب')),
        ],
        default='work_sheet',
        verbose_name=_("عدد أوجه الداخلي")
    )
    
    inner_color_mode = models.CharField(
        max_length=20,
        choices=[
            ('all_color', _('ملون بالكامل 4/4')),
            ('all_bw', _('أبيض وأسود نصوص 1/1')),
            ('mixed', _('مختلط (ألوان + أسود)')),
        ],
        default='all_color',
        verbose_name=_("نمط ألوان الداخلي")
    )
    
    inner_spot_colors = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("عدد الألوان المخصوصة (الداخلي)")
    )
    
    inner_color_pages = models.PositiveIntegerField(
        default=0,
        verbose_name=_("عدد الصفحات الملونة بالداخلي")
    )
    
    inner_bw_pages = models.PositiveIntegerField(
        default=0,
        verbose_name=_("عدد الصفحات الأبيض والأسود بالداخلي")
    )
    
    inner_signatures_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("إجمالي عدد الملازم")
    )
    
    binding_type = models.CharField(
        max_length=30,
        choices=[
            ('staple', _('دبوس فرنسي سرج')),
            ('perfect_binding', _('غراء حراري كعب مربع (PUR)')),
            ('hardcover', _('كرتون مقوى فاخر (Hardcover)')),
            ('wire_o', _('سلك لولبي دبل')),
            ('pad_glue', _('بلوك تكعيب غراء من أعلى (نوت بوك / روشتات)')),
            ('sewing_binding', _('خياطة ملازم وتجليد فاخر')),
        ],
        default='staple',
        verbose_name=_("نوع التجليد والتقفيل")
    )
    
    spine_thickness = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_("سمك الكعب (مم)")
    )
    
    inner_paper_type = models.CharField(
        max_length=50,
        default='couche',
        verbose_name=_("نوع ورق الداخلي")
    )
    
    inner_paper_weight = models.CharField(
        max_length=10,
        default='135',
        verbose_name=_("جراماج ورق الداخلي")
    )
    
    inner_coating_type = models.CharField(
        max_length=30,
        default='none',
        verbose_name=_("سلوفان الداخلي")
    )
    
    # حقول دفاتر الفواتير NCR
    ncr_sets_count = models.PositiveSmallIntegerField(
        default=2,
        verbose_name=_("عدد الصور في الطقم")
    )
    
    ncr_book_capacity = models.PositiveIntegerField(
        default=50,
        verbose_name=_("سعة الدفتر (مجموعة)")
    )
    
    ncr_serial_start = models.PositiveIntegerField(
        default=1001,
        verbose_name=_("بداية الترقيم")
    )
    
    ncr_serial_end = models.PositiveIntegerField(
        default=1000,
        verbose_name=_("نهاية الترقيم")
    )
    
    # حقول جيوب الفولدرات
    folder_pocket_type = models.CharField(
        max_length=30,
        default='same_sheet',
        verbose_name=_("نوع الجيب")
    )
    
    folder_card_slit = models.BooleanField(
        default=True,
        verbose_name=_("فتحة كارت شخصي")
    )
    
    folder_pocket_height = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('7.5'),
        verbose_name=_("ارتفاع الجيب (سم)")
    )
    
    # معلومات التكلفة
    estimated_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("التكلفة المقدرة")
    )
    
    final_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("السعر النهائي")
    )
    
    # إضافة حقل sale_price للتوافق مع النظام القديم
    sale_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("سعر البيع")
    )
    
    profit_margin = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('20.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("هامش الربح (%)")
    )
    
    # تواريخ مهمة
    due_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ التسليم المطلوب")
    )
    
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ الاعتماد")
    )
    
    # حقول التوافق مع النظام القديم
    product_type = models.ForeignKey(
        'ProductType',
        on_delete=models.PROTECT,
        related_name="printing_orders",
        verbose_name=_("نوع المنتج"),
        null=True,
        blank=True
    )
    
    paper_type = models.ForeignKey(
        'PaperType',
        on_delete=models.PROTECT,
        related_name="printing_orders",
        verbose_name=_("نوع الورق"),
        null=True,
        blank=True
    )
    
    product_size = models.ForeignKey(
        'ProductSize',
        on_delete=models.PROTECT,
        related_name="printing_orders",
        verbose_name=_("مقاس المنتج"),
        null=True,
        blank=True
    )
    
    supplier = models.ForeignKey(
        'supplier.Supplier',
        on_delete=models.PROTECT,
        related_name="printing_orders",
        verbose_name=_("المورد"),
        null=True,
        blank=True
    )
    
    press = models.CharField(
        max_length=100,
        verbose_name=_("المطبعة"),
        null=True,
        blank=True
    )
    
    colors_front = models.PositiveIntegerField(
        default=1,
        verbose_name=_("ألوان الوجه")
    )
    
    colors_back = models.PositiveIntegerField(
        default=0,
        verbose_name=_("ألوان الظهر")
    )
    
    print_sides = models.CharField(
        max_length=20,
        choices=[
            ('single', _('وجه واحد')),
            ('double', _('وجهين'))
        ],
        default='single',
        verbose_name=_("جوانب الطباعة")
    )
    
    print_direction = models.ForeignKey(
        'PrintDirection',
        on_delete=models.PROTECT,
        related_name="printing_orders",
        verbose_name=_("اتجاه الطباعة"),
        null=True,
        blank=True
    )
    
    coating_type = models.ForeignKey(
        'CoatingType',
        on_delete=models.PROTECT,
        related_name="printing_orders",
        verbose_name=_("نوع التغطية"),
        null=True,
        blank=True
    )
    
    coating_service = models.CharField(
        max_length=100,
        verbose_name=_("خدمة التغطية"),
        null=True,
        blank=True
    )
    
    has_internal_content = models.BooleanField(
        default=False,
        verbose_name=_("يحتوي على محتوى داخلي")
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
    
    extra_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("تكلفة إضافية")
    )

    # معلومات إضافية
    priority = models.CharField(
        max_length=10,
        choices=[
            ('low', _('منخفضة')),
            ('medium', _('متوسطة')),
            ('high', _('عالية')),
            ('urgent', _('عاجلة'))
        ],
        default='medium',
        verbose_name=_("الأولوية")
    )
    
    is_rush_order = models.BooleanField(
        default=False,
        verbose_name=_("طلب عاجل")
    )
    
    rush_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("رسوم الاستعجال")
    )
    
    # خدمات التصميم والإبداع
    design_service_type = models.CharField(
        max_length=20,
        choices=(
            ("CUSTOMER_READY", _("تصميم جاهز للطباعة من العميل")),
            ("PREPRESS_EDIT", _("تعديل فني ومونتاج وفصل ألوان")),
            ("NEW_CONCEPT", _("تصميم إبداعي جديد بالكامل")),
        ),
        default="CUSTOMER_READY",
        verbose_name=_("خدمة التصميم")
    )
    design_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("أتعاب التصميم")
    )
    
    # عمولات المبيعات
    sales_rep = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="printing_sales_orders",
        verbose_name=_("مسؤول المبيعات")
    )
    sales_commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("نسبة عمولة المبيعات %")
    )
    sales_commission_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name=_("مبلغ عمولة المبيعات")
    )
    
    # الهالك التراكمي للورش
    cumulative_waste_sheets = models.PositiveIntegerField(
        default=0,
        verbose_name=_("إجمالي أفرخ الهالك التراكمي")
    )

    class Meta:
        verbose_name = _("طلب تسعير")
        verbose_name_plural = _("طلبات التسعير")
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['order_number']),
            models.Index(fields=['customer', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['due_date']),
        ]

    def __str__(self):
        return f"{self.order_number} - {self.title}"

    def get_dimensions_display(self):
        """عرض المقاس والاتجاه بشكل منسق ومحمي من الـ None"""
        orientation_label = _("طولي") if self.print_orientation == 'portrait' else _("عرضي")
        if self.product_size:
            return f"{self.product_size.name} ({self.width or 0}×{self.height or 0} سم) - {orientation_label}"
        elif self.width and self.height:
            return f"{_('مقاس مخصص')} ({self.width}×{self.height} سم) - {orientation_label}"
        return _("غير محدد")

    def save(self, *args, **kwargs):
        """
        حفظ محسن مع توليد رقم الطلب والربط بأمر الشغل وتجميد لقطة العميل
        """
        if not self.order_number:
            self.order_number = self.generate_order_number()
            
        # المزامنة التوافقية بين final_price و sale_price
        if self.final_price and not self.sale_price:
            self.sale_price = self.final_price
        elif self.sale_price and not self.final_price:
            self.final_price = self.sale_price
            
        # الربط التلقائي بأمر الشغل إذا تُرك فارغاً
        if not self.work_order and self.customer:
            try:
                from work_order.models import WorkOrder
                user = kwargs.get('user') or getattr(self, 'created_by', None)
                self.work_order = WorkOrder.objects.create(
                    customer=self.customer,
                    created_by=user,
                    notes=f"أمر شغل تلقائي لطلب التسعير {self.title or self.order_number}"
                )
            except Exception:
                pass
                
        # تجميد لقطة عنوان وهاتف العميل
        if self.customer and not self.delivery_address_snapshot:
            phone = getattr(self.customer, 'phone_primary', None) or getattr(self.customer, 'phone', '') or ''
            addr = getattr(self.customer, 'address', '') or ''
            self.delivery_address_snapshot = f"{self.customer.name} | هاتف: {phone} | عنوان: {addr}"
            
        super().save(*args, **kwargs)

    def generate_order_number(self):
        """
        توليد رقم طلب فريد عبر الخدمة المركزية الموحدة للترقيم (SequenceService)
        """
        try:
            from core.services.sequence_service import SequenceService
            from core.enums.document_types import DocumentType
            return SequenceService.get_next_number(
                document_type=DocumentType.PRINTING_REQUEST,
                user=getattr(self, 'created_by', None)
            )
        except Exception:
            # آلية بديلة آمنة في حالة عدم توفر الجداول
            from django.utils import timezone
            now = timezone.now()
            year = now.year
            last_order = PrintingOrder.objects.filter(
                order_number__startswith=f"PR-{year}-"
            ).order_by('-order_number').first()
            
            if last_order:
                try:
                    last_seq = int(last_order.order_number.split('-')[-1])
                    new_seq = last_seq + 1
                except Exception:
                    new_seq = 1
            else:
                new_seq = 1
                
            return f"PR-{year}-{new_seq:04d}"

    @property
    def total_pages(self):
        """
        إجمالي عدد الصفحات (الصفحات × النسخ)
        """
        return self.pages_count * self.copies_count

    @property
    def total_items(self):
        """
        إجمالي عدد القطع
        """
        return self.quantity * self.copies_count

    def calculate_final_price(self):
        """
        حساب السعر النهائي مع هامش الربح
        """
        if self.estimated_cost:
            margin_amount = self.estimated_cost * (self.profit_margin / 100)
            return self.estimated_cost + margin_amount + self.rush_fee
        return Decimal('0.00')

    def update_status(self, new_status, user=None):
        """
        تحديث حالة الطلب مع تسجيل المستخدم
        """
        old_status = self.status
        self.status = new_status
        
        if new_status == PricingStatus.APPROVED:
            from django.utils import timezone
            self.approved_at = timezone.now()
            
        if user:
            self.updated_by = user
            
        self.save()
        
        # يمكن إضافة signal هنا لتسجيل تغيير الحالة
        return old_status, new_status

    def get_open_dimensions(self):
        """حساب المقاس المفتوح الفعلي على ماكينة الطباعة بناءً على نوع المطبوع وحالة الطي وجهة الفتح والتجليد"""
        w = Decimal(str(self.width or 21))
        h = Decimal(str(self.height or 29.7))
        
        if not self.is_closed_size:
            return w, h
            
        archetype = self.product_type.base_archetype if self.product_type else (self.order_type or 'flyer')
        direction = self.open_direction or 'right'
        
        # مضاعف البوابات: 3 للبروشورات و 2 للكتالوجات والفولدرات والمطويات
        multiplier = Decimal('3') if archetype in ['brochure', 'brochures'] else Decimal('2')
        
        # حساب سمك كعب الغلاف (Spine) للكتالوجات والكتب
        spine = Decimal('0.0')
        if archetype in ['catalog', 'book', 'magazine', 'book_catalog']:
            pages = Decimal(str(self.pages_count or 0))
            if pages > 4:
                spine = ((pages / Decimal('2')) * Decimal('0.012')).quantize(Decimal('0.1'))
        
        if direction == 'top':
            open_w = w
            open_h = (h * multiplier) + spine
        else:  # right or left
            open_w = (w * multiplier) + spine
            open_h = h
            
        return open_w, open_h

    def get_dimensions_display(self):
        """عرض منسق للأبعاد ومقاس المطبوع والاتجاه وحالة الطي وجهة الفتح"""
        orient = self.get_print_orientation_display() if hasattr(self, 'get_print_orientation_display') else ('عرضي (أفقي)' if self.print_orientation == 'landscape' else 'طولي (رأسي)')
        w = float(self.width) if self.width is not None else 0
        h = float(self.height) if self.height is not None else 0
        w_str = f"{w:.1f}".rstrip('0').rstrip('.') if w else '0'
        h_str = f"{h:.1f}".rstrip('0').rstrip('.') if h else '0'

        fold_info = ""
        if self.is_closed_size:
            dir_label = self.get_open_direction_display() if hasattr(self, 'get_open_direction_display') else ('من أعلى (رأسي)' if self.open_direction == 'top' else ('إنجليزي (يسار)' if self.open_direction == 'left' else 'عربي (يمين)'))
            fold_info = f" (مقفول) [فتح: {dir_label}]"

        if self.product_size:
            return f"{self.product_size.name} ({w_str}×{h_str} سم){fold_info} - {orient}"
        return f"مقاس مخصص ({w_str}×{h_str} سم){fold_info} - {orient}"



class PriceAuditLog(BaseModel):
    """
    سجل تدقيق وتاريخ التعديلات المالية على أمر التسعير
    """
    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="price_audit_logs",
        verbose_name=_("أمر التسعير")
    )
    field_name = models.CharField(
        max_length=100,
        verbose_name=_("اسم الحقل المعدل")
    )
    old_value = models.CharField(
        max_length=255,
        verbose_name=_("القيمة السابقة")
    )
    new_value = models.CharField(
        max_length=255,
        verbose_name=_("القيمة الجديدة")
    )
    change_reason = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("سبب التعديل")
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("المستخدم المنفذ للتعديل")
    )

    class Meta:
        verbose_name = _("سجل تدقيق السعر")
        verbose_name_plural = _("سجلات تدقيق الأسعار")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.order_number} - {self.field_name}: {self.old_value} -> {self.new_value}"


class OrderVendorAdvance(BaseModel):
    """
    تتبع عرابين ودفعات الورش والموردين المقدمة تحت أمر الشغل وأمر التسعير
    """
    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="vendor_advances",
        verbose_name=_("أمر التسعير")
    )
    work_order = models.ForeignKey(
        "work_order.WorkOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vendor_advances",
        verbose_name=_("أمر الشغل المرتبط")
    )
    supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.PROTECT,
        related_name="printing_advances",
        verbose_name=_("المورد / الورشة")
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name=_("مبلغ العربون / الدفعة")
    )
    payment_method = models.CharField(
        max_length=50,
        default="CASH",
        verbose_name=_("طريقة الدفع")
    )
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("رقم الإيصال / السند")
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("ملاحظات")
    )
    is_settled = models.BooleanField(
        default=False,
        verbose_name=_("تمت التسوية مع الفاتورة")
    )
    settled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ التسوية")
    )

    class Meta:
        verbose_name = _("عربون مورد / ورشة")
        verbose_name_plural = _("عرابين الموردين والورش")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.supplier.name} - {self.amount} ج ({self.order.order_number})"


class ProofSignOff(BaseModel):
    """
    الاعتماد الرقمي للبروفة (Digital Proof Sign-Off)
    """
    class ProofStatus(models.TextChoices):
        PENDING = "PENDING", _("بانتظار مراجعة العميل")
        APPROVED = "APPROVED", _("معتمد من العميل")
        REJECTED = "REJECTED", _("مرفوض مع ملاحظات")

    order = models.OneToOneField(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="proof_signoff",
        verbose_name=_("أمر التسعير")
    )
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name=_("رمز التحقق الآمن")
    )
    proof_file = models.FileField(
        upload_to="printing_proofs/%Y/%m/",
        blank=True,
        null=True,
        verbose_name=_("ملف البروفة الرقمية")
    )
    status = models.CharField(
        max_length=20,
        choices=ProofStatus.choices,
        default=ProofStatus.PENDING,
        verbose_name=_("حالة الاعتماد")
    )
    client_feedback = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("ملاحظات العميل")
    )
    approved_by_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name=_("اسم الشخص المعتمد")
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("تاريخ الاعتماد")
    )
    client_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name=_("عنوان IP للعميل")
    )

    class Meta:
        verbose_name = _("اعتماد بروفة رقمية")
        verbose_name_plural = _("اعتمادات البروفات الرقمية")

    def __str__(self):
        return f"بروفة {self.order.order_number} - {self.get_status_display()}"


class DieMouldCustody(BaseModel):
    """
    أرشيف وعهدة فورمات التكسير وكليشيهات البصمة والزنكات (Die/Mould Custody Archive)
    """
    class MouldType(models.TextChoices):
        DIE_CUT = "DIE_CUT", _("فورمة تكسير وريجة")
        FOIL_STAMP = "FOIL_STAMP", _("كليشيه بصمة حراري")
        EMBOSSING = "EMBOSSING", _("كليشيه كوفراج بارز")
        SPOT_UV = "SPOT_UV", _("شابلونة سبوت يوفي")

    class MouldStatus(models.TextChoices):
        ACTIVE = "ACTIVE", _("صالحة وجاهزة للتشغيل")
        MAINTENANCE = "MAINTENANCE", _("تحتاج صيانة / تغيير حشايا")
        ARCHIVED = "ARCHIVED", _("مؤرشفة في مخزن الوكالة")

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("كود الفورمة / الكليشيه")
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("اسم وتوصيف الفورمة")
    )
    mould_type = models.CharField(
        max_length=20,
        choices=MouldType.choices,
        default=MouldType.DIE_CUT,
        verbose_name=_("نوع الأداة")
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custom_moulds",
        verbose_name=_("العميل المالك (إن وجد)")
    )
    current_workshop = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hosted_moulds",
        verbose_name=_("الورشة الحاضنة للفورمة حالياً")
    )
    storage_location = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name=_("موقع التخزين والرف")
    )
    dimensions = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("الأبعاد والمقاس")
    )
    hit_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("إجمالي عدد الضربات والسحبات")
    )
    last_used_order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_moulds",
        verbose_name=_("آخر أمر شغل تم استخدامها فيه")
    )
    status = models.CharField(
        max_length=20,
        choices=MouldStatus.choices,
        default=MouldStatus.ACTIVE,
        verbose_name=_("الحالة الفنية")
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("ملاحظات فنية")
    )

    class Meta:
        verbose_name = _("عهدة فورمة / كليشيه")
        verbose_name_plural = _("أرشيف وعهدة الفورمات والكليشيهات")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name} ({self.get_mould_type_display()})"


class QCSignoff(BaseModel):
    """
    بوابة فحص مراقبة الجودة الرقمية (QC Sign-off Gateway)
    """
    class QCStatus(models.TextChoices):
        PASSED = "PASSED", _("مطابق ومعتمد 100%")
        CONDITIONAL_PASS = "CONDITIONAL_PASS", _("قبول مشروط بتسامح مقبول")
        REJECTED = "REJECTED", _("مرفوض - توالف وإعادة تشغيل")

    order = models.OneToOneField(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="qc_signoff",
        verbose_name=_("أمر التسعير")
    )
    inspector_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name=_("اسم مسؤول فحص الجودة")
    )
    inspected_at = models.DateTimeField(
        verbose_name=_("تاريخ ووقت الفحص")
    )
    bleed_verified = models.BooleanField(
        default=False,
        verbose_name=_("فحص خلوص ومسافة الخروج (Bleed 3mm) سليم")
    )
    barcode_scannable = models.BooleanField(
        default=False,
        verbose_name=_("فحص قراءة الباركود والـ QR بالماسح الضوئي سليم")
    )
    color_registration_passed = models.BooleanField(
        default=False,
        verbose_name=_("فحص تطابق ألوان الطباعة والأوفست سليم")
    )
    physical_swatch_matched = models.BooleanField(
        default=False,
        verbose_name=_("فحص مطابقة عينة الألوان المادية المرفقة")
    )
    lamination_adhesion_passed = models.BooleanField(
        default=False,
        verbose_name=_("فحص ثبات وقوة التصاق السلوفان سليم")
    )
    ncr_sequence_verified = models.BooleanField(
        default=False,
        verbose_name=_("فحص تسلسل وترتيب أرقام الفواتير NCR سليم")
    )
    sample_vault_archived = models.BooleanField(
        default=False,
        verbose_name=_("تم تحريز 5-10 عينات في خزانة الجودة لمدة 90 يوماً")
    )
    sample_vault_ref = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name=_("رقم حرز خزانة العينات")
    )
    net_quantity_approved = models.PositiveIntegerField(
        verbose_name=_("الكمية الصافية المعتمدة للتسليم")
    )
    defect_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_("عدد التوالف والمرفوضات")
    )
    status = models.CharField(
        max_length=20,
        choices=QCStatus.choices,
        default=QCStatus.PASSED,
        verbose_name=_("قرار الجودة النهائي")
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("ملاحظات تقرير الجودة")
    )

    class Meta:
        verbose_name = _("تقرير فحص جودة QC")
        verbose_name_plural = _("تقارير فحص الجودة QC")

    def __str__(self):
        return f"جودة {self.order.order_number} - {self.get_status_display()}"


class SupplementalRemake(BaseModel):
    """
    أمر إعادة تشغيل تكميلي للمرتجعات الجزئية (Supplemental Remake Order)
    """
    class FaultParty(models.TextChoices):
        VENDOR_FAULT = "VENDOR_FAULT", _("خطأ مورد / ورشة تشغيل")
        AGENCY_FAULT = "AGENCY_FAULT", _("خطأ داخلي بالوكالة")
        CLIENT_FAULT = "CLIENT_FAULT", _("تعديل أو خطأ من العميل")

    class RemakeStatus(models.TextChoices):
        PENDING = "PENDING", _("قيد الدراسة والموافقة")
        IN_PROGRESS = "IN_PROGRESS", _("قيد إعادة التشغيل بالورش")
        COMPLETED = "COMPLETED", _("تمت إعادة التشغيل والتسليم")
        CANCELLED = "CANCELLED", _("ملغي")

    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="remakes",
        verbose_name=_("أمر التسعير الأصلي")
    )
    remake_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("رقم أمر التعويض")
    )
    defective_quantity = models.PositiveIntegerField(
        verbose_name=_("الكمية المعيبة المرتجعة")
    )
    fault_allocation = models.CharField(
        max_length=20,
        choices=FaultParty.choices,
        default=FaultParty.VENDOR_FAULT,
        verbose_name=_("الطرف المسؤول عن العيب")
    )
    responsible_supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attributed_remakes",
        verbose_name=_("الورشة / المورد المتسبب")
    )
    estimated_copq = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("تكلفة الهادر الغارق (COPQ)")
    )
    reason = models.TextField(
        verbose_name=_("سبب العيب والمطالبة")
    )
    status = models.CharField(
        max_length=20,
        choices=RemakeStatus.choices,
        default=RemakeStatus.PENDING,
        verbose_name=_("حالة أمر التعويض")
    )

    class Meta:
        verbose_name = _("أمر إعادة تشغيل تكميلي")
        verbose_name_plural = _("أوامر إعادة التشغيل التكميلية")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.remake_number} ({self.order.order_number}) - {self.defective_quantity} قطعة"


class OrderTransportLog(BaseModel):
    """
    سجل حركة ونقل الشغل بين الورش والمطابع (بدون أي توقيعات أو أوراق)
    يوثق: مين اللي نقل، من مكان كذا إلى مكان كذا، وأجرة النقل
    """
    order = models.ForeignKey(
        PrintingOrder,
        on_delete=models.CASCADE,
        related_name="transport_logs",
        verbose_name=_("أمر التسعير")
    )
    from_location = models.CharField(
        max_length=200,
        verbose_name=_("نقل من (المكان / الورشة السابقة)")
    )
    to_location = models.CharField(
        max_length=200,
        verbose_name=_("نقل إلى (المكان / الورشة التالية)")
    )
    transporter = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transport_tasks",
        verbose_name=_("المكلف بالنقل (السائق / المشوارجي / شركة الشحن)")
    )
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("أجرة النقل / المشوار")
    )
    transfer_date = models.DateTimeField(
        verbose_name=_("تاريخ ووقت النقل")
    )

    class Meta:
        verbose_name = _("سجل حركة ونقل الشغل")
        verbose_name_plural = _("سجلات حركة ونقل الشغل")
        ordering = ["-transfer_date"]

    def __str__(self):
        courier_name = self.transporter.name if self.transporter else "غير محدد"
        return f"{self.order.order_number}: من {self.from_location} إلى {self.to_location} بواسطة {courier_name}"


__all__ = [
    'PrintingOrder',
    'PriceAuditLog',
    'OrderVendorAdvance',
    'ProofSignOff',
    'DieMouldCustody',
    'QCSignoff',
    'SupplementalRemake',
    'OrderTransportLog'
]



