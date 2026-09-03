from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.conf import settings
from decimal import Decimal
import uuid

from .base import BaseModel, PricingStatus, OrderType
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
    
    order_date = models.DateField(
        _("تاريخ الطلب"),
        default=timezone.now,
        db_index=True,
        help_text=_("تاريخ استلام وتسجيل طلب التسعير الفعلي")
    )
    
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="printing_orders",
        verbose_name=_("العميل المسجل")
    )
    
    customer_name = models.CharField(
        _("اسم العميل"),
        max_length=200,
        blank=True,
        null=True,
        help_text=_("اسم العميل للتسعيرات السريعة دون الحاجة لتسجيله في الدليل")
    )
    
    title = models.CharField(
        max_length=200,
        verbose_name=_("وصف الطلب")
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_("ملاحظات الطلب")
    )
    
    order_type = models.CharField(
        max_length=20,
        choices=OrderType.choices,
        verbose_name=_("نوع الطلب")
    )

    product_type = models.ForeignKey(
        'ProductType',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="printing_orders",
        verbose_name=_("نوع المطبوع")
    )

    product_size = models.ForeignKey(
        'ProductSize',
        on_delete=models.PROTECT,
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
        حفظ محسن مع توليد رقم الطلب وتثبيت العملة الوظيفية
        """
        if not self.order_number:
            self.order_number = self.generate_order_number()

        # تثبيت العملة الوظيفية للمؤسسة افتراضياً
        if not self.currency_id:
            try:
                from financial.services.exchange_rate_service import ExchangeRateService
                self.currency = ExchangeRateService.get_functional_currency()
                self.exchange_rate = Decimal("1.000000")
            except Exception:
                pass

        # مزامنة اسم العميل تلقائياً من العميل المسجل إذا لم يكن مكتوباً
        if self.customer and not self.customer_name:
            self.customer_name = self.customer.name

        # مزامنة order_type من نوع المطبوع تلقائياً إذا توفر
        if self.product_type and hasattr(self.product_type, 'base_archetype') and self.product_type.base_archetype:
            if not self.order_type or self.order_type != self.product_type.base_archetype:
                self.order_type = self.product_type.base_archetype
                
        super().save(*args, **kwargs)

    def create_work_order(self, user=None):
        """
        توليد أمر شغل تنفيذي لصالة الإنتاج بعد اعتماد الطلب أو تحويله
        """
        if not self.work_order:
            from work_order.models import WorkOrder
            customer_display = self.customer_name or (self.customer.name if self.customer else '')
            notes_text = f"أمر شغل معتمد لطلب التسعير {self.order_number} - {self.title or ''}"
            if customer_display:
                notes_text += f" | العميل: {customer_display}"

            self.work_order = WorkOrder.objects.create(
                customer=self.customer,
                created_by=user or getattr(self, 'created_by', None),
                delivery_date=self.due_date.date() if self.due_date else None,
                notes=notes_text
            )
            self.save(update_fields=['work_order'])
        return self.work_order

    def generate_order_number(self):
        """
        توليد رقم طلب فريد عبر الخدمة المركزية الموحدة للترقيم (SequenceService)
        مع مراعاة سنة تاريخ الطلب الفعلي
        """
        order_dt = self.order_date or timezone.now().date()
        try:
            from core.services.sequence_service import SequenceService
            from core.enums.document_types import DocumentType
            return SequenceService.get_next_number(
                document_type=DocumentType.PRINTING_REQUEST,
                date=order_dt,
                user=getattr(self, 'created_by', None)
            )
        except Exception:
            # آلية بديلة آمنة في حالة عدم توفر الجداول
            year = order_dt.year if hasattr(order_dt, 'year') else timezone.now().year
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

    @property
    def customer_display_name(self):
        """اسم العميل للعرض الموحد في الجداول"""
        if self.customer:
            return self.customer.name
        return self.customer_name or "-"

    @property
    def product_type_name(self):
        """اسم نوع المطبوع للعرض الموحد في الجداول"""
        if self.product_type:
            return self.product_type.name
        return self.get_order_type_display() or "-"


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


__all__ = [
    "PrintingOrder"
]
