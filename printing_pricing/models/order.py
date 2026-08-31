from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from decimal import Decimal

from .base import BaseModel, PricingStatus, OrderType
from client.models import Customer


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
    
    # إضافة حقل client للتوافق مع النظام القديم
    client = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="client_printing_orders",
        verbose_name=_("العميل (client)"),
        null=True,
        blank=True
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
            ("CLIENT_READY", _("تصميم جاهز للطباعة من العميل")),
            ("PREPRESS_EDIT", _("تعديل فني ومونتاج وفصل ألوان")),
            ("NEW_CONCEPT", _("تصميم إبداعي جديد بالكامل")),
        ),
        default="CLIENT_READY",
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

    def save(self, *args, **kwargs):
        """
        حفظ محسن مع توليد رقم الطلب والربط بأمر الشغل وتجميد لقطة العميل
        """
        if not self.order_number:
            self.order_number = self.generate_order_number()
            
        # المزامنة التوافقية بين customer و client
        if self.customer and not self.client:
            self.client = self.customer
        elif self.client and not self.customer:
            self.customer = self.client
            
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


__all__ = ['PrintingOrder']
