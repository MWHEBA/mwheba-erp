from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class Category(models.Model):
    """
    نموذج تصنيفات المنتجات
    """

    name = models.CharField(_("اسم التصنيف"), max_length=255)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="children",
        verbose_name=_("التصنيف الأم"),
    )
    description = models.TextField(_("الوصف"), blank=True, null=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("فئة")
        verbose_name_plural = _("التصنيفات")
        ordering = ["name"]

    def __str__(self):
        if self.parent:
            return f"{self.parent} > {self.name}"
        return self.name


class Brand(models.Model):
    """
    نموذج الأنواع
    """

    name = models.CharField(_("اسم النوع"), max_length=255)
    description = models.TextField(_("الوصف"), blank=True, null=True)
    logo = models.ImageField(_("الشعار"), upload_to="brands", blank=True, null=True)
    website = models.URLField(_("الموقع الإلكتروني"), blank=True, null=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("علامة تجارية")
        verbose_name_plural = _("الأنواع")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Unit(models.Model):
    """
    نموذج وحدات القياس
    """

    name = models.CharField(_("اسم الوحدة"), max_length=50)
    symbol = models.CharField(_("الرمز"), max_length=10)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("وحدة قياس")
        verbose_name_plural = _("وحدات القياس")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class Product(models.Model):
    """
    نموذج المنتجات
    """

    name = models.CharField(_("اسم المنتج"), max_length=255)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("التصنيف"),
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("النوع"),
        blank=True,
        null=True,
    )
    description = models.TextField(_("الوصف"), blank=True, null=True)
    sku = models.CharField(_("كود المنتج"), max_length=50, unique=True)
    barcode = models.CharField(_("الباركود"), max_length=50, blank=True, null=True)
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name=_("وحدة القياس"),
    )
    cost_price = models.DecimalField(
        _("سعر التكلفة"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    selling_price = models.DecimalField(
        _("سعر البيع"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    min_stock = models.PositiveIntegerField(_("الحد الأدنى للمخزون"), default=0)
    is_active = models.BooleanField(_("نشط"), default=True)
    is_featured = models.BooleanField(_("مميز"), default=False)
    tax_rate = models.DecimalField(
        _("نسبة الضريبة"),
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    discount_rate = models.DecimalField(
        _("نسبة الخصم"),
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="products_created",
    )

    # المورد الافتراضي
    default_supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("المورد الافتراضي"),
        related_name="default_products",
        help_text=_("المورد الافتراضي لهذا المنتج"),
    )

    class Meta:
        verbose_name = _("منتج")
        verbose_name_plural = _("المنتجات")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def current_stock(self):
        """
        حساب المخزون الحالي في جميع المخازن
        """
        from django.db.models import Sum

        # معالجة حالة عدم وجود مخزون
        stock = self.stocks.aggregate(Sum("quantity"))
        return stock["quantity__sum"] or 0

    @property
    def profit_margin(self):
        """
        حساب هامش الربح
        """
        if self.cost_price > 0:
            return (self.selling_price - self.cost_price) / self.cost_price * 100
        return 0

    def get_supplier_price(self, supplier):
        """
        الحصول على سعر المنتج من مورد معين
        """
        try:
            supplier_price = SupplierProductPrice.objects.get(
                product=self, supplier=supplier, is_active=True
            )
            return supplier_price.cost_price
        except SupplierProductPrice.DoesNotExist:
            return None

    def get_all_supplier_prices(self):
        """
        الحصول على جميع أسعار الموردين لهذا المنتج
        """
        try:
            return (
                SupplierProductPrice.objects.filter(product=self, is_active=True)
                .select_related("supplier")
                .order_by("-is_default", "cost_price")
            )
        except:
            return []

    def get_cheapest_supplier(self):
        """
        الحصول على أرخص مورد لهذا المنتج
        """
        supplier_prices = self.get_all_supplier_prices()
        if supplier_prices:
            return supplier_prices.order_by("cost_price").first()
        return None

    def get_default_supplier_price(self):
        """
        الحصول على سعر المورد الافتراضي
        """
        try:
            default_price = SupplierProductPrice.objects.get(
                product=self, is_default=True, is_active=True
            )
            return default_price
        except SupplierProductPrice.DoesNotExist:
            return None

    def get_primary_image(self):
        """
        الحصول على الصورة الرئيسية للمنتج
        """
        primary_image = self.images.filter(is_primary=True).first()
        if primary_image:
            return primary_image
        # إذا لم توجد صورة رئيسية، إرجاع أول صورة
        return self.images.first()

    def get_all_images(self):
        """
        الحصول على جميع صور المنتج مرتبة (الرئيسية أولاً)
        """
        return self.images.all().order_by("-is_primary", "created_at")

    def get_secondary_images(self):
        """
        الحصول على الصور الثانوية (غير الرئيسية)
        """
        return self.images.filter(is_primary=False).order_by("created_at")

    def has_images(self):
        """
        التحقق من وجود صور للمنتج
        """
        return self.images.exists()

    def images_count(self):
        """
        عدد صور المنتج
        """
        return self.images.count()

    def update_cost_price_from_supplier(
        self, supplier, new_price, user, reason="manual_update", purchase_reference=None
    ):
        """
        تحديث سعر التكلفة من مورد معين
        """
        try:
            from decimal import Decimal

            # الحصول على أو إنشاء سعر المورد
            supplier_price, created = SupplierProductPrice.objects.get_or_create(
                product=self,
                supplier=supplier,
                defaults={
                    "cost_price": new_price,
                    "created_by": user,
                    "is_default": not SupplierProductPrice.objects.filter(
                        product=self
                    ).exists(),
                },
            )

            # إذا كان السعر موجود، سجل التغيير في التاريخ
            if not created and supplier_price.cost_price != new_price:
                PriceHistory.objects.create(
                    supplier_product_price=supplier_price,
                    old_price=supplier_price.cost_price,
                    new_price=new_price,
                    change_reason=reason,
                    purchase_reference=purchase_reference,
                    changed_by=user,
                )

                # تحديث السعر
                supplier_price.cost_price = new_price
                supplier_price.save()

            return supplier_price

        except Exception as e:
            print(f"خطأ في تحديث سعر المورد: {e}")
            return None


class ProductImage(models.Model):
    """
    نموذج صور المنتجات
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name=_("المنتج"),
    )
    image = models.ImageField(_("الصورة"), upload_to="products/%Y/%m/")
    is_primary = models.BooleanField(_("صورة رئيسية"), default=False)
    alt_text = models.CharField(_("نص بديل"), max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)

    class Meta:
        verbose_name = _("صورة منتج")
        verbose_name_plural = _("صور المنتجات")
        ordering = ["-is_primary", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_primary=True),
                name="unique_primary_image_per_product",
            )
        ]

    def save(self, *args, **kwargs):
        # إذا كانت هذه الصورة رئيسية، تأكد من عدم وجود صورة رئيسية أخرى
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)

        # إذا كانت هذه أول صورة للمنتج، اجعلها رئيسية
        elif not self.product.images.exists():
            self.is_primary = True

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # إذا تم حذف الصورة الرئيسية، اجعل أول صورة أخرى رئيسية
        if self.is_primary:
            next_image = self.product.images.exclude(pk=self.pk).first()
            if next_image:
                next_image.is_primary = True
                next_image.save()

        super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.product} - {self.alt_text or 'صورة'}"


class ProductVariant(models.Model):
    """
    نموذج متغيرات المنتج
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="variants",
        verbose_name=_("المنتج"),
    )
    name = models.CharField(_("اسم المتغير"), max_length=255)
    sku = models.CharField(_("رمز المتغير"), max_length=50, unique=True)
    barcode = models.CharField(_("الباركود"), max_length=50, blank=True, null=True)
    cost_price = models.DecimalField(
        _("سعر التكلفة"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    selling_price = models.DecimalField(
        _("سعر البيع"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    stock = models.PositiveIntegerField(_("المخزون"), default=0)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)

    class Meta:
        verbose_name = _("متغير منتج")
        verbose_name_plural = _("متغيرات المنتجات")
        ordering = ["product", "name"]

    def __str__(self):
        return f"{self.product} - {self.name} ({self.sku})"


class Warehouse(models.Model):
    """
    نموذج المخازن
    """

    name = models.CharField(_("اسم المخزن"), max_length=255)
    code = models.CharField(_("كود المخزن"), max_length=20, unique=True)
    location = models.CharField(_("الموقع"), max_length=255, blank=True, null=True)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        verbose_name=_("المدير"),
        null=True,
        blank=True,
        related_name="managed_warehouses",
    )
    description = models.TextField(_("الوصف"), blank=True, null=True)
    is_active = models.BooleanField(_("نشط"), default=True)
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="warehouses_created",
    )

    class Meta:
        verbose_name = _("مخزن")
        verbose_name_plural = _("المخازن")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Stock(models.Model):
    """
    نموذج المخزون
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="stocks",
        verbose_name=_("المنتج"),
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="stocks",
        verbose_name=_("المخزن"),
    )
    quantity = models.PositiveIntegerField(_("الكمية"), default=0)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("أنشئ بواسطة"),
        related_name="stocks_created",
    )

    class Meta:
        verbose_name = _("مخزون")
        verbose_name_plural = _("المخزون")
        unique_together = ("product", "warehouse")

    def __str__(self):
        return f"{self.product} - {self.warehouse} ({self.quantity})"


class StockMovement(models.Model):
    """
    نموذج حركة المخزون
    """

    MOVEMENT_TYPES = (
        ("in", _("وارد")),
        ("out", _("صادر")),
        ("transfer", _("تحويل")),
        ("adjustment", _("تسوية")),
        ("return_in", _("مرتجع وارد")),
        ("return_out", _("مرتجع صادر")),
    )

    # أنواع مستندات الحركة
    DOCUMENT_TYPES = (
        ("purchase", _("شراء")),
        ("purchase_return", _("مرتجع مشتريات")),
        ("sale", _("بيع")),
        ("sale_return", _("مرتجع مبيعات")),
        ("transfer", _("تحويل")),
        ("adjustment", _("جرد")),
        ("opening", _("رصيد")),
        ("other", _("أخرى")),
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name=_("المنتج"),
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name=_("المخزن"),
    )
    movement_type = models.CharField(
        _("نوع الحركة"), max_length=20, choices=MOVEMENT_TYPES
    )
    quantity = models.PositiveIntegerField(_("الكمية"))
    reference_number = models.CharField(
        _("رقم المرجع"), max_length=50, blank=True, null=True
    )
    document_type = models.CharField(
        _("نوع المستند"), max_length=20, choices=DOCUMENT_TYPES, default="other"
    )
    document_number = models.CharField(
        _("رقم المستند"), max_length=50, blank=True, null=True
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)
    timestamp = models.DateTimeField(_("تاريخ الحركة"), auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="stock_movements_created",
    )
    # للتحويلات
    destination_warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        verbose_name=_("المخزن المستلم"),
        related_name="incoming_movements",
        blank=True,
        null=True,
    )

    # حقول لتتبع كمية المخزون قبل وبعد الحركة
    quantity_before = models.PositiveIntegerField(_("الكمية قبل"), default=0)
    quantity_after = models.PositiveIntegerField(_("الكمية بعد"), default=0)

    # خاصية لتخطي تحديث المخزون (للاستخدام الداخلي)
    _skip_update = False

    number = models.CharField(
        _("رقم الحركة"), max_length=50, unique=True, blank=True, null=True
    )

    # ربط بالقيد المحاسبي
    journal_entry = models.ForeignKey(
        "financial.JournalEntry",
        on_delete=models.SET_NULL,
        verbose_name=_("القيد المحاسبي"),
        related_name="stock_movements",
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = _("حركة المخزون")
        verbose_name_plural = _("حركات المخزون")
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.product} - {self.movement_type} - {self.quantity} - {self.timestamp}"

    def _create_journal_entry(self):
        """إنشاء قيد محاسبي لحركة المخزون"""
        try:
            from financial.models import JournalEntry, JournalEntryLine, ChartOfAccounts
            from decimal import Decimal

            # حساب قيمة الحركة
            cost = self.product.cost_price or Decimal("0")
            amount = cost * Decimal(str(self.quantity))

            if amount == 0:
                return  # لا نُنشئ قيد لحركات بدون قيمة

            # الحصول على الحسابات
            try:
                inventory_account = ChartOfAccounts.objects.get(
                    code="1030"
                )  # مخزون البضاعة
                cogs_account = ChartOfAccounts.objects.get(
                    code="5010"
                )  # تكلفة البضاعة المباعة
            except ChartOfAccounts.DoesNotExist:
                print(f"⚠️  حسابات المخزون غير موجودة - لم يتم إنشاء قيد")
                return

            # إنشاء القيد
            journal_entry = JournalEntry.objects.create(
                date=self.timestamp.date()
                if hasattr(self.timestamp, "date")
                else self.timestamp,
                description=f"حركة مخزون - {self.product.name} - {self.get_movement_type_display()}",
                reference_number=self.number,
                status="posted",  # مرحل مباشرة
                created_by=self.created_by,
            )

            # إنشاء بنود القيد حسب نوع الحركة
            if self.movement_type == "in":
                # وارد (شراء): مدين المخزون / دائن الموردين (لكن هنا نفترض نقدي)
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=inventory_account,
                    debit=amount,
                    credit=Decimal("0"),
                    description=f"وارد مخزون - {self.product.name}",
                )
                # ملاحظة: الطرف الدائن يجب أن يُنشأ من فاتورة الشراء

            elif self.movement_type == "out":
                # صادر (بيع): مدين تكلفة البضاعة / دائن المخزون
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=cogs_account,
                    debit=amount,
                    credit=Decimal("0"),
                    description=f"تكلفة بيع - {self.product.name}",
                )
                JournalEntryLine.objects.create(
                    journal_entry=journal_entry,
                    account=inventory_account,
                    debit=Decimal("0"),
                    credit=amount,
                    description=f"صادر مخزون - {self.product.name}",
                )

            # ربط القيد بالحركة
            self.journal_entry = journal_entry
            StockMovement.objects.filter(pk=self.pk).update(journal_entry=journal_entry)

        except Exception as e:
            print(f"❌ خطأ في إنشاء القيد المحاسبي: {e}")

    def save(self, *args, **kwargs):
        """
        حفظ حركة المخزون

        ملاحظة: تحديث المخزون يتم عبر Signal في product/signals.py
        هذا يضمن تحديث المخزون فقط بعد حفظ الحركة بنجاح (Django Best Practice)
        """
        # توليد رقم الحركة إذا لم يكن موجوداً
        if not self.number:
            serial = SerialNumber.objects.get_or_create(
                document_type="stock_movement",
                year=timezone.now().year,
                defaults={"prefix": "MOV"},
            )[0]
            next_number = serial.get_next_number()
            self.number = f"{serial.prefix}{next_number:04d}"

        # حفظ الحركة
        is_new = self.pk is None
        super().save(*args, **kwargs)

        # إنشاء قيد محاسبي تلقائياً (فقط للحركات الجديدة وبدون قيد)
        # ملاحظة: لا نُنشئ قيود لحركات الشراء والبيع لأن القيود تُنشأ من الفواتير
        excluded_types = ["purchase", "sale", "purchase_return", "sale_return"]
        if (
            is_new
            and not self.journal_entry
            and not getattr(self, "_skip_update", False)
            and self.document_type not in excluded_types
        ):
            self._create_journal_entry()


class SerialNumber(models.Model):
    """
    نموذج لتتبع الأرقام التسلسلية للمستندات
    """

    DOCUMENT_TYPES = (
        ("sale", _("فاتورة مبيعات")),
        ("purchase", _("فاتورة مشتريات")),
        ("stock_movement", _("حركة مخزون")),
    )

    document_type = models.CharField(
        _("نوع المستند"), max_length=20, choices=DOCUMENT_TYPES
    )
    last_number = models.PositiveIntegerField(_("آخر رقم"), default=0)
    prefix = models.CharField(_("بادئة"), max_length=10, blank=True)
    year = models.PositiveIntegerField(_("السنة"), null=True, blank=True)

    class Meta:
        verbose_name = _("رقم تسلسلي")
        verbose_name_plural = _("الأرقام التسلسلية")
        unique_together = ["document_type", "year"]

    def get_next_number(self):
        """
        الحصول على الرقم التالي في التسلسل
        """
        # البحث عن آخر رقم مستخدم في هذا النوع من المستندات
        from django.db.models import Max
        from django.apps import apps

        # تحديد النموذج المناسب حسب نوع المستند
        if self.document_type == "sale":
            model = apps.get_model("sale", "Sale")
        elif self.document_type == "purchase":
            model = apps.get_model("purchase", "Purchase")
        else:
            model = apps.get_model("product", "StockMovement")

        # استخراج الرقم من آخر مستند
        last_doc = (
            model.objects.filter(number__startswith=self.prefix)
            .order_by("-number")
            .first()
        )

        if last_doc:
            # استخراج الرقم من آخر مستند
            try:
                last_number = int(last_doc.number.replace(self.prefix, ""))
                self.last_number = max(self.last_number, last_number)
            except ValueError:
                pass

        # زيادة الرقم
        self.last_number += 1
        self.save()
        return self.last_number

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.year} - {self.last_number}"


class SupplierProductPrice(models.Model):
    """
    نموذج أسعار المنتجات حسب المورد
    يربط كل منتج بمورد وسعره الحالي
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="supplier_prices",
        verbose_name=_("المنتج"),
    )
    supplier = models.ForeignKey(
        "supplier.Supplier",
        on_delete=models.CASCADE,
        related_name="product_prices",
        verbose_name=_("المورد"),
    )
    cost_price = models.DecimalField(
        _("سعر التكلفة"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    is_active = models.BooleanField(_("نشط"), default=True)
    is_default = models.BooleanField(
        _("المورد الافتراضي"),
        default=False,
        help_text=_("هل هذا هو المورد الافتراضي لهذا المنتج؟"),
    )
    last_purchase_date = models.DateField(_("تاريخ آخر شراء"), null=True, blank=True)
    last_purchase_quantity = models.PositiveIntegerField(
        _("كمية آخر شراء"), null=True, blank=True
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    # تواريخ التتبع
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True)
    updated_at = models.DateTimeField(_("تاريخ التحديث"), auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("أنشئ بواسطة"),
        related_name="supplier_prices_created",
    )

    class Meta:
        verbose_name = _("سعر المنتج للمورد")
        verbose_name_plural = _("أسعار المنتجات للموردين")
        unique_together = ("product", "supplier")
        ordering = ["-is_default", "-last_purchase_date", "supplier__name"]
        indexes = [
            models.Index(fields=["product", "supplier"]),
            models.Index(fields=["product", "is_default"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        default_text = " (افتراضي)" if self.is_default else ""
        return f"{self.product.name} - {self.supplier.name} - {self.cost_price}{default_text}"

    def save(self, *args, **kwargs):
        """
        حفظ السعر مع التأكد من وجود مورد افتراضي واحد فقط لكل منتج
        """
        # إذا تم تعيين هذا المورد كافتراضي، إلغاء الافتراضي من الموردين الآخرين
        if self.is_default:
            SupplierProductPrice.objects.filter(
                product=self.product, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)

        # إذا لم يكن هناك مورد افتراضي لهذا المنتج، اجعل هذا افتراضي
        elif (
            not SupplierProductPrice.objects.filter(
                product=self.product, is_default=True
            )
            .exclude(pk=self.pk)
            .exists()
        ):
            self.is_default = True

        super().save(*args, **kwargs)

        # تحديث سعر التكلفة الرئيسي للمنتج إذا كان هذا المورد افتراضي
        if self.is_default and self.product.cost_price != self.cost_price:
            Product.objects.filter(pk=self.product.pk).update(
                cost_price=self.cost_price
            )

    @property
    def price_difference_from_main(self):
        """
        الفرق بين سعر هذا المورد وسعر التكلفة الرئيسي للمنتج
        """
        if self.product.cost_price:
            return self.cost_price - self.product.cost_price
        return Decimal("0")

    @property
    def price_difference_percentage(self):
        """
        نسبة الفرق بين سعر هذا المورد وسعر التكلفة الرئيسي للمنتج
        """
        if self.product.cost_price and self.product.cost_price > 0:
            return (
                (self.cost_price - self.product.cost_price) / self.product.cost_price
            ) * 100
        return Decimal("0")

    @property
    def days_since_last_purchase(self):
        """
        عدد الأيام منذ آخر شراء من هذا المورد
        """
        if self.last_purchase_date:
            return (timezone.now().date() - self.last_purchase_date).days
        return None


class PriceHistory(models.Model):
    """
    نموذج تاريخ تغيير أسعار المنتجات للموردين
    يسجل كل تغيير في السعر مع السبب والتاريخ
    """

    CHANGE_REASONS = (
        ("purchase", _("شراء جديد")),
        ("manual_update", _("تحديث يدوي")),
        ("supplier_notification", _("إشعار من المورد")),
        ("market_change", _("تغيير السوق")),
        ("bulk_update", _("تحديث جماعي")),
        ("system_sync", _("مزامنة النظام")),
    )

    supplier_product_price = models.ForeignKey(
        SupplierProductPrice,
        on_delete=models.CASCADE,
        related_name="price_history",
        verbose_name=_("سعر المنتج للمورد"),
    )
    old_price = models.DecimalField(
        _("السعر القديم"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    new_price = models.DecimalField(
        _("السعر الجديد"),
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    change_amount = models.DecimalField(
        _("مقدار التغيير"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    change_percentage = models.DecimalField(
        _("نسبة التغيير"), max_digits=8, decimal_places=4, null=True, blank=True
    )
    change_reason = models.CharField(
        _("سبب التغيير"), max_length=30, choices=CHANGE_REASONS, default="manual_update"
    )
    purchase_reference = models.CharField(
        _("مرجع الشراء"),
        max_length=50,
        null=True,
        blank=True,
        help_text=_("رقم فاتورة الشراء إذا كان التغيير بسبب شراء جديد"),
    )
    notes = models.TextField(_("ملاحظات"), blank=True, null=True)

    # تواريخ التتبع
    change_date = models.DateTimeField(_("تاريخ التغيير"), auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("غُير بواسطة"),
        related_name="price_changes_made",
    )

    class Meta:
        verbose_name = _("تاريخ تغيير السعر")
        verbose_name_plural = _("تاريخ تغيير الأسعار")
        ordering = ["-change_date"]
        indexes = [
            models.Index(fields=["supplier_product_price", "-change_date"]),
            models.Index(fields=["change_reason"]),
            models.Index(fields=["change_date"]),
        ]

    def __str__(self):
        product_name = self.supplier_product_price.product.name
        supplier_name = self.supplier_product_price.supplier.name
        return f"{product_name} - {supplier_name} - {self.old_price} → {self.new_price}"

    def save(self, *args, **kwargs):
        """
        حفظ تاريخ التغيير مع حساب مقدار ونسبة التغيير
        """
        if self.old_price and self.new_price:
            # حساب مقدار التغيير
            self.change_amount = self.new_price - self.old_price

            # حساب نسبة التغيير
            if self.old_price > 0:
                self.change_percentage = (self.change_amount / self.old_price) * 100
            else:
                self.change_percentage = Decimal("0")

        super().save(*args, **kwargs)

    @property
    def is_price_increase(self):
        """
        هل التغيير زيادة في السعر؟
        """
        return self.change_amount and self.change_amount > 0

    @property
    def is_price_decrease(self):
        """
        هل التغيير نقصان في السعر؟
        """
        return self.change_amount and self.change_amount < 0

    @property
    def change_direction_display(self):
        """
        عرض اتجاه التغيير بالعربية
        """
        if self.is_price_increase:
            return "زيادة"
        elif self.is_price_decrease:
            return "نقصان"
        else:
            return "بدون تغيير"
