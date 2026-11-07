# -*- coding: utf-8 -*-
"""
Finishing & Architectural Variation Models
MWHEBA ERP — Track 2: Finishing Packages, Specs Directory, and Governed Dual-Speed Workflow
"""
import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class FinishingWorkspace(models.Model):
    """الفراغ / الحيز المعماري المعتمد بالوحدات (ريسبشن، ماستر، مطبخ، حمام، تراس...)"""
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.CASCADE,
        related_name='finishing_workspaces',
        verbose_name=_('المشروع العقاري')
    )
    name = models.CharField(max_length=100, verbose_name=_('اسم الفراغ المعماري'))
    code = models.CharField(max_length=30, verbose_name=_('كود الفراغ المعماري')) # e.g. "REC", "MBR", "KIT", "BTH_GUEST"
    is_wet_area = models.BooleanField(default=False, verbose_name=_('فراغ مبتل يحظر نقله فوق الغرف (حمام/مطبخ)'))
    standard_height_meters = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('2.90'), verbose_name=_('الارتفاع المعماري الصافي (متر)'))
    sort_order = models.PositiveIntegerField(default=1, verbose_name=_('ترتيب الظهور في المقايسة'))
    is_active = models.BooleanField(default=True, verbose_name=_('نشط'))

    class Meta:
        verbose_name = _('فراغ معماري للتشطيب')
        verbose_name_plural = _('فراغات معمارية للتشطيب')
        unique_together = ('project', 'code')
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.project.name} - {self.name} ({self.code})"


class FinishingBrand(models.Model):
    """الماركات التجارية والشركات المصنعة المعتمدة للخامات"""
    name = models.CharField(max_length=100, unique=True, verbose_name=_('اسم الماركة التجارية'))
    brand_logo = models.ImageField(upload_to='finishing/brands/', null=True, blank=True, verbose_name=_('شعار الماركة'))
    country_of_origin = models.CharField(max_length=50, blank=True, default='', verbose_name=_('بلد المنشأ'))
    website = models.URLField(blank=True, verbose_name=_('الموقع الإلكتروني'))
    supplier_partner = models.ForeignKey(
        'supplier.Supplier',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_brands',
        verbose_name=_('المورد / الوكيل المحلي المعتمد')
    )
    is_approved = models.BooleanField(default=True, verbose_name=_('ماركة معتمدة بالمشروع'))

    class Meta:
        verbose_name = _('ماركة خامات تشطيب')
        verbose_name_plural = _('ماركات خامات التشطيب')

    def __str__(self):
        return self.name


class FinishingItemCategory(models.TextChoices):
    FLOORING = 'FLOORING', _('أرضيات وسيراميك وبورسلين وباركية')
    WALL_FINISH = 'WALL_FINISH', _('دهانات وتشطيبات حوائط وتجاليد وديكورات')
    CEILING = 'CEILING', _('أسقف معلقة وجبس بورد وإضاءة مدفونة')
    PLUMBING_FIXTURES = 'PLUMBING_FIXTURES', _('أطقم صحية وخلاطات وشاور ومحابس')
    ELECTRICAL_FIXTURES = 'ELECTRICAL_FIXTURES', _('مفاتيح وإنارة ولوحات وسمارت هوم')
    CARPENTRY_DOORS = 'CARPENTRY_DOORS', _('أبواب ونجارة ودواليب مدمجة وتجاليد خشب')
    ALUMINUM_FACADES = 'ALUMINUM_FACADES', _('ألوميتال وزجاج وواجهات وشترات')
    HVAC_MECHANICAL = 'HVAC_MECHANICAL', _('تكييف وتهوية وتدفئة وتمديدات نحاس')
    CUSTOM_SPECIALTY = 'CUSTOM_SPECIALTY', _('أعمال وتوريدات خاصة ومقطوعيات متخصصة')


class ContractualCreditSchedule(models.Model):
    """جدول فئات استرداد نصف التشطيب المعتمدة تعاقدياً بالمشروع (لحسم نزاعات خصم الخامات)"""
    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.CASCADE,
        related_name='contractual_credit_rates',
        verbose_name=_('المشروع العقاري')
    )
    category = models.CharField(max_length=30, choices=FinishingItemCategory.choices, verbose_name=_('تصنيف البند المسترد'))
    item_title = models.CharField(max_length=150, verbose_name=_('اسم البند التعاقدي بنصف التشطيب'))
    measuring_unit = models.CharField(max_length=20, verbose_name=_('وحدة القياس'))
    contractual_credit_rate = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('فئة الخصم والاسترداد المعتمدة تعاقدياً بالجنيه'))
    pre_execution_credit_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('سعر الاسترداد قبل التنفيذ بالموقع (Pre-Execution Rate)')
    )
    post_execution_credit_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('سعر الاسترداد بعد التنفيذ (Post-Execution Rate)')
    )
    demolition_and_cartage_deduction_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكلفة التكسير ونقل الردميات المخصومة لكل وحدة قياس')
    )
    notes = models.CharField(max_length=255, blank=True, default='', verbose_name=_('ملاحظات والاشتراطات التعاقدية'))

    class Meta:
        verbose_name = _('فئة استرداد نصف تشطيب تعاقدية')
        verbose_name_plural = _('فئات استرداد نصف التشطيب التعاقدية')
        unique_together = ('project', 'category', 'item_title')

    def __str__(self):
        return f"{self.project.name} - {self.item_title} ({self.contractual_credit_rate} ج.م/{self.measuring_unit})"


class FinishingItemSpec(models.Model):
    """كتالوج مواصفات وخامات التشطيب المتاحة للاختيار لكل فراغ"""
    workspace = models.ForeignKey(
        FinishingWorkspace,
        on_delete=models.CASCADE,
        related_name='specifications',
        verbose_name=_('الفراغ المعماري')
    )
    category = models.CharField(
        max_length=30,
        choices=FinishingItemCategory.choices,
        db_index=True,
        verbose_name=_('تصنيف بند التشطيب')
    )
    name = models.CharField(max_length=150, verbose_name=_('اسم البند والمواصفة'))
    brand = models.ForeignKey(
        FinishingBrand,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='specs',
        verbose_name=_('الماركة التجارية')
    )
    model_code = models.CharField(max_length=100, blank=True, default='', verbose_name=_('كود الموديل أو اللون'))
    measuring_unit = models.CharField(max_length=20, verbose_name=_('وحدة القياس (م²، م.ط، عدد، مقطوعية)'))
    
    # Cost & Pricing
    standard_material_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكلفة المواد التقديرية'))
    standard_labor_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكلفة المصنعية والتركيب'))
    scrap_allowance_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('10.00'), verbose_name=_('نسبة الهالك المسموحة (%)'))
    supervision_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('15.00'), verbose_name=_('نسبة أتعاب الإشراف الإداري والهندسي (%)'))
    client_selling_rate = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('سعر بيع المتر/الوحدة للعميل شامل الإشراف'))
    credit_schedule = models.ForeignKey(
        ContractualCreditSchedule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='specs',
        verbose_name=_('بند الاسترداد التعاقدي المقابل')
    )
    # Acoustic Insulation Attributes
    is_acoustic_insulation = models.BooleanField(
        default=False,
        verbose_name=_('بند عزل صوتي متخصص (Acoustic Insulation)')
    )
    noise_reduction_db = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('معامل خفض الضوضاء بالديسيبل (dB)')
    )
    
    # Store Link
    inventory_item = models.ForeignKey(
        'product.Product',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_('الصنف المرتبط بمخزن الخامات')
    )
    is_active = models.BooleanField(default=True, verbose_name=_('ساري في الكتالوج'))

    class Meta:
        verbose_name = _('مواصفة تشطيب بكتالوج الفراغات')
        verbose_name_plural = _('مواصفات تشطيب كتالوج الفراغات')

    def __str__(self):
        return f"{self.workspace.name} - {self.name} ({self.get_category_display()})"


class FinishingPackageTemplate(models.Model):
    """الباقات المعيارية المجهزة للتشطيب (Standard Packages: نصف تشطيب، لوكس، سوبر لوكس، ألترا لوكس)"""
    class PackageLevel(models.TextChoices):
        CORE_SHELL = 'CORE_SHELL', _('نصف تشطيب (محارة وحلوق وتأسيس)')
        ECONOMIC = 'ECONOMIC', _('تشطيب تجاري / اقتصادي')
        DELUXE = 'DELUXE', _('تشطيب لوكس')
        SUPER_DELUXE = 'SUPER_DELUXE', _('تشطيب سوبر لوكس')
        ULTRA_SUPER_LUX = 'ULTRA_SUPER_LUX', _('تشطيب ألترا سوبر لوكس فندقي')
        SMART_LUXURY = 'SMART_LUXURY', _('تشطيب فاخر كامل بأنظمة المنزل الذكي')

    project = models.ForeignKey(
        'real_estate.RealEstateProject',
        on_delete=models.CASCADE,
        related_name='finishing_packages',
        verbose_name=_('المشروع العقاري')
    )
    name = models.CharField(max_length=150, verbose_name=_('اسم الباقة المعمارية'))
    package_level = models.CharField(max_length=30, choices=PackageLevel.choices, default=PackageLevel.SUPER_DELUXE, verbose_name=_('مستوى الباقة'))
    price_per_square_meter = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('سعر المتر الإجمالي للباقة'))
    description = models.TextField(blank=True, default='', verbose_name=_('توصيف كراسة شروط الباقة'))
    is_active = models.BooleanField(default=True, verbose_name=_('متاحة للتعاقد'))

    class Meta:
        verbose_name = _('باقة تشطيب معيارية')
        verbose_name_plural = _('باقات التشطيب المعيارية')

    def __str__(self):
        return f"{self.project.name} - {self.name} ({self.get_package_level_display()})"


class FinishingPackageItem(models.Model):
    """البنود والمواصفات المعمارية النمطية المدرجة داخل الباقة المعيارية"""
    package = models.ForeignKey(FinishingPackageTemplate, on_delete=models.CASCADE, related_name='items', verbose_name=_('الباقة'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.CASCADE, verbose_name=_('الفراغ'))
    spec = models.ForeignKey(FinishingItemSpec, on_delete=models.PROTECT, verbose_name=_('المواصفة المعتمدة'))
    is_included_in_base_price = models.BooleanField(default=True, verbose_name=_('مشمول في سعر المتر النمطي'))

    class Meta:
        verbose_name = _('بند باقة تشطيب')
        verbose_name_plural = _('بنود باقات التشطيب')


class UnitFinishingOrder(models.Model):
    """أمر وطلب تشطيب وتعديل الوحدة العقارية للعميل (المستند المحوري الموحد)"""
    class OrderType(models.TextChoices):
        STANDARD_PACKAGE = 'STANDARD_PACKAGE', _('اختيار باقة تشطيب معيارية كاملة')
        CUSTOM_VARIATION = 'CUSTOM_VARIATION', _('طلب تعديلات معمارية وتشطيبات مخصصة')
        UPGRADE_HYBRID = 'UPGRADE_HYBRID', _('باقة معيارية مع تعديلات وترقيات خاصة')
        SELF_FINISHING = 'SELF_FINISHING', _('تشطيب ذاتي بواسطة مهندس العميل الخاص بتأمين نقدي')

    class PricingMode(models.TextChoices):
        FIXED_PRICE_BOQ = 'FIXED_PRICE_BOQ', _('مقايسة مسعرة بالكميات والفئات الثابتة')
        PACKAGE_LUMP_SUM = 'PACKAGE_LUMP_SUM', _('باقة معيارية مقطوعة بسعر المتر')
        COST_PLUS_OPEN_BOOK = 'COST_PLUS_OPEN_BOOK', _('التكلفة الفعلية المعتمدة + نسبة أتعاب إدارة وإشراف')

    class WorkflowSpeed(models.TextChoices):
        FAST_TRACK = 'FAST_TRACK', _('مسار سريع (تعديلات تجميلية بسيطة لا تتجاوز السقف المالي)')
        MAJOR_GOVERNED = 'MAJOR_GOVERNED', _('مسار سداسي محوكم (باقات وتعديلات معمارية وإنشائية كبرى)')

    class OrderStage(models.TextChoices):
        CUSTOMER_SERVICE = 'CUSTOMER_SERVICE', _('1. خدمة العملاء - تسجيل الطلب واستبيان الرغبات')
        TECHNICAL_OFFICE = 'TECHNICAL_OFFICE', _('2. المكتب الفني - إعداد المقايسة والمخططات As-Built')
        CHANGES_MANAGER = 'CHANGES_MANAGER', _('3. مدير التعديلات - المراجعة الإنشائية والمعمارية')
        COST_ACCOUNTING = 'COST_ACCOUNTING', _('4. حسابات التكاليف - تسعير البنود وتجميد الأسعار')
        FINANCE_CFO = 'FINANCE_CFO', _('5. الإدارة المالية - اعتماد شروط السداد والدفعة والأقساط')
        CLIENT_APPROVAL = 'CLIENT_APPROVAL', _('6. توقيع وموافقة العميل - كراسة المواصفات الرسمية')
        PRICE_EXPIRED = 'PRICE_EXPIRED', _('منتهي الصلاحية - يتطلب إعادة تسعير لتغير الأسعار')
        IN_EXECUTION = 'IN_EXECUTION', _('7. قيد التنفيذ الميداني - أوامر الشغل بالموقع')
        COMPLETED = 'COMPLETED', _('8. مكتمل ومسلم بمحضر استلام نهائي ومخالصة')
        CANCELLED = 'CANCELLED', _('9. ملغى بتسوية تكاليف غارقة')

    order_number = models.CharField(max_length=50, unique=True, db_index=True, verbose_name=_('رقم أمر التشطيب / التعديل'))
    order_type = models.CharField(max_length=30, choices=OrderType.choices, default=OrderType.CUSTOM_VARIATION, verbose_name=_('طبيعة الطلب'))
    pricing_mode = models.CharField(max_length=30, choices=PricingMode.choices, default=PricingMode.FIXED_PRICE_BOQ, verbose_name=_('نمط التسعير والتعاقد'))
    workflow_speed = models.CharField(max_length=30, choices=WorkflowSpeed.choices, default=WorkflowSpeed.MAJOR_GOVERNED, verbose_name=_('مسار سرعة الاعتماد'))
    
    contract = models.ForeignKey('real_estate.PropertyContract', on_delete=models.PROTECT, related_name='finishing_orders', verbose_name=_('العقد العقاري'))
    unit = models.ForeignKey('real_estate.PropertyUnit', on_delete=models.PROTECT, related_name='finishing_orders', verbose_name=_('الوحدة العقارية'))
    customer = models.ForeignKey('customer.Customer', on_delete=models.PROTECT, related_name='finishing_orders', verbose_name=_('العميل'))
    package = models.ForeignKey(FinishingPackageTemplate, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('الباقة الأساسية المختارة (إن وجدت)'))
    
    title = models.CharField(max_length=200, verbose_name=_('عنوان طلب التشطيب / التعديل'))
    current_stage = models.CharField(max_length=30, choices=OrderStage.choices, default=OrderStage.CUSTOMER_SERVICE, db_index=True, verbose_name=_('مرحلة الاعتماد الحالية'))
    request_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ تقديم الطلب'))
    
    # Execution Duration & Contractual Extension Guard
    execution_duration_days = models.PositiveIntegerField(default=90, verbose_name=_('مدة التنفيذ الميداني التقديرية (أيام)'))
    original_contract_delivery_date = models.DateField(null=True, blank=True, verbose_name=_('تاريخ تسليم الوحدة التعاقدي الأصلي'))
    amended_contract_delivery_date = models.DateField(null=True, blank=True, verbose_name=_('تاريخ تسليم الوحدة المعدل بملحق التشطيب'))
    delay_penalty_waiver_signed = models.BooleanField(default=False, verbose_name=_('تم توقيع إقرار إسقاط غرامات التأخير عن فترة التشطيب'))
    
    # Joint Ownership Guard
    all_co_owners_signed = models.BooleanField(default=True, verbose_name=_('تم توقيع كافة الملاك على الشيوع أو تقديم توكيل موثق'))
    co_owners_power_of_attorney_file = models.FileField(upload_to='finishing/poa/', null=True, blank=True, verbose_name=_('التوكيل الرسمي المسجل بالشهر العقاري'))

    # Civil Defense & Building Code Compliance
    civil_defense_approved = models.BooleanField(default=True, verbose_name=_('معتمد ومطابق لاشتراطات الدفاع المدني ورخصة المبنى'))
    civil_defense_approval_notes = models.TextField(blank=True, default='', verbose_name=_('ملاحظات مراجعة رخصة البناء والحرائق'))

    target_handover_date = models.DateField(null=True, blank=True, verbose_name=_('تاريخ التسليم المستهدف للتشطيب'))
    actual_handover_date = models.DateField(null=True, blank=True, verbose_name=_('تاريخ التسليم الميداني الفعلي'))

    # Overdue Installment Lock & CFO Override
    cfo_overdue_override = models.BooleanField(default=False, verbose_name=_('استثناء وتجاوز تعثر الأقساط بموافقة الإدارة المالية'))
    cfo_override_notes = models.TextField(blank=True, default='', verbose_name=_('أسباب ومبررات تجاوز تعثر الأقساط'))

    # Price Freeze & Expiry Radar
    price_freeze_date = models.DateTimeField(null=True, blank=True, verbose_name=_('تاريخ تجميد تسعير المقايسة'))
    offer_validity_days = models.PositiveIntegerField(default=15, verbose_name=_('مهلة صلاحية تسعير العرض (أيام)'))
    offer_expires_at = models.DateField(null=True, blank=True, verbose_name=_('تاريخ انتهاء صلاحية الأسعار'))

    # Financial Breakdown (IFRS 15 Performance Obligation 2)
    material_cost_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي تكلفة المواد والخامات'))
    labor_cost_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي تكلفة المصنعيات والعمالة'))
    demolition_cost_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكلفة التكسير ورفع الرتش'))
    supervision_fee_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('أتعاب الإشراف الإداري والهندسي'))
    core_shell_credit_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قيمة استرداد نصف التشطيب التعاقدية (خصم للعميل)'))
    
    gross_finishing_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي المقايسة قبل الخصم'))
    promotional_discount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قيمة الخصم التجاري المعتمد'))
    net_finishing_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('صافي قيمة المقايسة المطلوب سدادها'))
    
    advance_deposit_required = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('الدفعة المقدمة المشروطة للتنفيذ'))
    total_deposit_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي الدفعات المسددة فعلياً'))
    remaining_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('المبلغ المتبقي للجدولة'))

    # Egyptian Tax Authority (ETA) E-Invoice Compliance
    eta_invoice_uuid = models.CharField(max_length=100, blank=True, default='', verbose_name=_('الرقم التعريفي الفريد للفاتورة الإلكترونية بمصلحة الضرائب (ETA UUID)'))
    eta_submission_date = models.DateTimeField(null=True, blank=True, verbose_name=_('تاريخ إرسال الفاتورة لمنظومة الضرائب المصرية'))
    eta_status = models.CharField(
        max_length=30,
        choices=[('PENDING', _('قيد الإرسال')), ('VALID', _('معتمدة وصحيحة')), ('REJECTED', _('مرفوضة من الضرائب'))],
        default='PENDING',
        verbose_name=_('حالة الفاتورة على منظومة الضرائب')
    )

    # Site Freeze Flag (e.g. from Bounced Cheque)
    is_site_work_frozen = models.BooleanField(default=False, verbose_name=_('تجميد الأعمال الميدانية وصرف الخامات للشقة'))
    freeze_reason = models.TextField(blank=True, default='', verbose_name=_('سبب تجميد الأعمال بالموقع'))

    # Signatures
    client_signature_date = models.DateTimeField(null=True, blank=True, verbose_name=_('تاريخ توقيع العميل على المقايسة والملحق'))
    client_signature_image = models.ImageField(upload_to='finishing_orders/signatures/', null=True, blank=True, verbose_name=_('صورة توقيع العميل'))
    
    # Central Enterprise Governance Link
    approval_request = models.ForeignKey(
        'financial.EnterpriseApprovalRequest',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_orders',
        verbose_name=_('طلب الاعتماد المركزي الموحد')
    )

    # Financial Integration Links (Segregated Legal Architecture)
    finishing_installment_plan = models.OneToOneField(
        'real_estate.FinishingInstallmentPlan',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_order',
        verbose_name=_('خطة أقساط التشطيب المستقلة قانونياً')
    )
    accrual_journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_order_accruals',
        verbose_name=_('قيد استحقاق المقايسة المحاسبي (IFRS 15)')
    )

    # Legacy Compatibility Bridge (ClientVariationOrder)
    legacy_variation_order = models.OneToOneField(
        'real_estate.ClientVariationOrder',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='upgraded_finishing_order',
        verbose_name=_('أمر التعديل القديم المرتبط (للتوافق التاريخي)')
    )

    # Site Utilities & Material Allocation Guards
    utility_surcharge_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('1.50'),
        verbose_name=_('نسبة مقطوعية استهلاك مرافق الموقع %')
    )
    utility_surcharge_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('مبلغ مقطوعية استهلاك المياه والكهرباء بالمشروع')
    )
    is_stock_reserved = models.BooleanField(
        default=False,
        verbose_name=_('تم حجز وتخصيص الخامات بالمخزن (Stock Reserved)')
    )
    # Electrical Load Breaker & Facility Sinking Fund Guards
    calculated_load_kva = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي الحمل الكهربائي المحسوب للتعديلات (kVA)')
    )
    main_breaker_ampere_required = models.PositiveIntegerField(
        default=40,
        verbose_name=_('سعة القاطع الرئيسي المطلوبة بالأمبير (Breaker Ampere)')
    )
    requires_panel_upgrade = models.BooleanField(
        default=False,
        verbose_name=_('يتطلب ترقية صاعد التغذية واللوحة لـ 3 فاز ومقايسة كهرباء')
    )
    facility_fund_adjustment_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('فارق تسوية وديعة الصيانة المعتمد مع إدارة المرافق')
    )
    # Broker Exclusion, Survey Sync & Deemed Handover Guards
    is_broker_commission_excluded = models.BooleanField(
        default=True,
        verbose_name=_('استبعاد قيمة أمر التشطيب كلياً من عمولات الوسطاء (Broker Protection)')
    )
    survey_adjustment = models.ForeignKey(
        'real_estate.AsBuiltSurveyAdjustment',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_orders',
        verbose_name=_('ملحق تسوية الرفع المساحي الفعلي المرتبط')
    )
    deemed_handover_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_('تاريخ الاستلام الحكمي في حال مماطلة العميل')
    )
    caretaking_fee_monthly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('1500.00'),
        verbose_name=_('مصاريف الحراسة والصيانة الشهرية بعد الإنذار القانوني')
    )
    total_caretaking_charged = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي مصاريف الحراسة المحملة على العميل المماطل')
    )
    # Landowner Partnership & Refund Reinstatement Guards
    is_landowner_revenue_share_excluded = models.BooleanField(
        default=True,
        verbose_name=_('عزل إيراد التشطيب كلياً عن اقتسام إيراد مالك الأرض (Landowner Share Excluded)')
    )
    is_landowner_offset = models.BooleanField(
        default=False,
        verbose_name=_('سداد أمر التشطيب بالمقاصة مع مستحقات مالك الأرض (21705)')
    )
    landowner_partnership = models.ForeignKey(
        'real_estate.LandownerPartnership',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_orders',
        verbose_name=_('اتفاقية المشاركة مع مالك الأرض المرتبطة')
    )
    reinstatement_cost_deduction = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكلفة إعادة الوحدة لأصلها النمطي المخصومة عند فسخ العقد')
    )
    is_reinstatement_deducted = models.BooleanField(
        default=False,
        verbose_name=_('تم خصم تكلفة إعادة الوضع النمطي من شيك استرداد العميل (21701)')
    )
    # Gas Safety & Handover Integration Guards
    is_gas_modification_requested = models.BooleanField(
        default=False,
        verbose_name=_('يتضمن الطلب تعديلاً في شبكة الغاز الطبيعي أو المداخن')
    )
    gas_company_approval_file = models.FileField(
        upload_to='finishing/gas_approvals/',
        null=True,
        blank=True,
        verbose_name=_('موافقة شركة الغاز الرسمية وكروكي التعديل المعتمد')
    )
    gas_safety_clearance = models.BooleanField(
        default=False,
        verbose_name=_('تم فحص واعتماد مطابقة شبكة الغاز هندسياً')
    )
    handover_receipt = models.ForeignKey(
        'real_estate.PropertyHandoverReceipt',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_orders',
        verbose_name=_('محضر استلام وتسليم الوحدة الرسمي الموحد (IFRS 15)')
    )
    # Mortgage, GPR Scanning & Debt Clearance Guards
    has_bank_mortgage_lien = models.BooleanField(
        default=False,
        verbose_name=_('الوحدة خاضعة لرهن تمويل عقاري بنكي (CBE Mortgage Lien)')
    )
    mortgage_bank_approval_file = models.FileField(
        upload_to='finishing/mortgage_approvals/',
        null=True,
        blank=True,
        verbose_name=_('موافقة بنك التمويل العقاري الكتابية على التعديل')
    )
    mortgage_clearance_verified = models.BooleanField(
        default=False,
        verbose_name=_('تم التحقق من موافقة البنك الممول على التعديل')
    )
    gpr_scan_report_file = models.FileField(
        upload_to='finishing/gpr_reports/',
        null=True,
        blank=True,
        verbose_name=_('تقرير المسح الراداري للخرسانة قبل الكور (GPR Slab Scan)')
    )
    gpr_scan_verified = models.BooleanField(
        default=False,
        verbose_name=_('تم اعتماد المسح الراداري للبلاطة وتفادي الكابلات')
    )
    is_debt_clearance_blocked = models.BooleanField(
        default=True,
        verbose_name=_('حظر إصدار براءة الذمة للعقد لحين سداد كامل التشطيبات')
    )
    # Pre-Contract Booking Study & WhatsApp Integration
    pre_contract_study = models.OneToOneField(
        'real_estate.BookingPreContractVariationStudy',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='converted_finishing_order',
        verbose_name=_('دراسة جدوى الحجز المسبقة المحولة')
    )
    whatsapp_notifications_enabled = models.BooleanField(
        default=True,
        verbose_name=_('تفعيل إشعارات واتساب Meta Graph API لمراحل التشطيب')
    )
    # Enterprise WorkOrder, HVAC Drain, Noise & Petty Cash Guards
    enterprise_work_order = models.ForeignKey(
        'work_order.WorkOrder',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_orders',
        verbose_name=_('أمر الشغل المؤسسي العام (Enterprise Cost Center)')
    )
    hvac_condensate_drain_verified = models.BooleanField(
        default=False,
        verbose_name=_('تم التحقق من ربط صرف التكييف بالجالتراب المعزول وتفادي الواجهات')
    )
    noise_curfew_agreed = models.BooleanField(
        default=True,
        verbose_name=_('إقرار الالتزام بمواعيد حظر الضوضاء والتكسير الميداني')
    )
    allocated_petty_cash_expenses = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('إجمالي العهد النثرية الطارئة المحملة على أمر التشطيب')
    )

    notes = models.TextField(blank=True, default='', verbose_name=_('ملاحظات واشتراطات خاصة'))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('محرر الطلب'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ التحديث'))

    class Meta:
        verbose_name = _('أمر تشطيب وتعديل وحدة')
        verbose_name_plural = _('أوامر تشطيب وتعديلات الوحدات')
        ordering = ['-id']

    def __str__(self):
        return f"{self.order_number} - {self.unit.unit_number} ({self.customer.name})"


class UnitFinishingOrderItem(models.Model):
    """بند تفصيلي في مقايسة تشطيب وتعديل الوحدة لكل فراغ معماري"""
    class SupplySource(models.TextChoices):
        COMPANY_STORE = 'COMPANY_STORE', _('توريد وتركيب من الشركة والمخزن المعتمد')
        OWNER_SUPPLIED = 'OWNER_SUPPLIED', _('خامات موردة من طرف العميل (مصنعية وإشراف فقط)')

    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='items', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعماري'))
    spec = models.ForeignKey(FinishingItemSpec, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('المواصفة المحددة من الكتالوج'))
    category = models.CharField(max_length=30, choices=FinishingItemCategory.choices, verbose_name=_('تصنيف العمل'))
    supply_source = models.CharField(max_length=30, choices=SupplySource.choices, default=SupplySource.COMPANY_STORE, verbose_name=_('جهة توريد الخامات'))
    
    item_description = models.CharField(max_length=255, verbose_name=_('التوصيف التفصيلي للبند'))
    brand = models.ForeignKey(FinishingBrand, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('الماركة التجارية'))
    model_or_color_code = models.CharField(max_length=100, blank=True, default='', verbose_name=_('كود الموديل / درجة اللون'))
    
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('الكمية الهندسية الصافية التقديرية'))
    scrap_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_('نسبة الهالك (%)'))
    gross_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('الكمية الإجمالية المعتمدة شاملة الهالك المعياري'))
    abnormal_wastage_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('كمية الهالك غير المبرر بالموقع')
    )
    abnormal_wastage_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('تكلفة الهالك غير المبرر المحملة على المقاول')
    )
    measuring_unit = models.CharField(max_length=20, default='M2', verbose_name=_('وحدة القياس'))
    
    unit_selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('فئة بيع الوحدة'))
    total_selling_price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي سعر البيع للعميل'))
    core_shell_credit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('خصم نصف التشطيب المعتمد للبند'))
    
    # Custom Specialty & RFQ Attachment
    is_custom_specialty = models.BooleanField(default=False, verbose_name=_('بند مقطوعية تخصصية خاصة'))
    vendor_rfq_file = models.FileField(upload_to='finishing_orders/rfq/', null=True, blank=True, verbose_name=_('عرض أسعار المورد الخارجي للبند'))
    
    # Store Quota Tracking
    issued_quantity_from_store = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي الكميات المنصرفة فعلياً من المخزن'))
    
    is_demolition_rework = models.BooleanField(default=False, verbose_name=_('بند تكسير أو تعديل على أعمال قائمة'))
    is_executed_on_site = models.BooleanField(default=False, verbose_name=_('تم تنفيذه ميدانياً بالموقع'))
    execution_notes = models.TextField(blank=True, default='', verbose_name=_('ملاحظات التنفيذ الميداني'))

    class Meta:
        verbose_name = _('بند مقايسة تشطيب')
        verbose_name_plural = _('بنود مقايسة التشطيب')

    def save(self, *args, **kwargs):
        if not self.gross_quantity or self.gross_quantity == Decimal('0.00'):
            scrap = self.scrap_rate or Decimal('0.00')
            self.gross_quantity = round(self.quantity * (Decimal('1') + scrap / Decimal('100')), 2)
        if not self.total_selling_price or self.total_selling_price == Decimal('0.00'):
            unit_price = self.unit_selling_price or Decimal('0.00')
            self.total_selling_price = round(self.gross_quantity * unit_price, 2)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.workspace.name} - {self.item_description} ({self.gross_quantity} {self.measuring_unit})"


class ClientSelfFinishingPermit(models.Model):
    """تصريح ومحضر تسليم مؤقت لتشطيبات العميل الذاتية بموقع المشروع وتأمين الديكور"""
    order = models.OneToOneField(UnitFinishingOrder, on_delete=models.CASCADE, related_name='self_finishing_permit', verbose_name=_('أمر التشطيب'))
    permit_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم تصريح التشطيب الذاتي'))
    designer_or_contractor_name = models.CharField(max_length=150, verbose_name=_('اسم مهندس الديكور / المقاول الخارجي للعميل'))
    contractor_national_id = models.CharField(max_length=20, verbose_name=_('الرقم القومي / السجل التجاري'))
    contractor_phone = models.CharField(max_length=30, verbose_name=_('رقم الهاتف للتواصل الميداني'))
    
    # Fit-Out Cash Security Deposit
    fitout_security_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('50000.00'), verbose_name=_('مبلغ تأمين الديكور النقدي المحتجز بالأمانات'))
    deposit_payment = models.ForeignKey('customer.CustomerPayment', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('إيصال تحصيل التأمين النقدي'))
    deposit_refunded = models.BooleanField(default=False, verbose_name=_('تم رد التأمين بعد المعاينة وخلو المرافق المشتركة من الأضرار'))
    
    # Temporary Utilities Charge
    utilities_charge_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('5000.00'), verbose_name=_('مقطوعية استهلاك مياه وإنارة الإنشاءات بالموقع'))
    site_utility_deposit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('5000.00'),
        verbose_name=_('تأمين استهلاك المياه والكهرباء المؤقتة بالمشروع')
    )
    site_utility_deducted_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name=_('المبلغ المستقطع الفعلي للمرافق المؤقتة')
    )
    noise_violation_penalty_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('2000.00'),
        verbose_name=_('غرامة مخالفة مواعيد حظر الضوضاء والتكسير')
    )
    noise_violations_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('عدد مخالفات الضوضاء المرصودة')
    )
    
    permit_start_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ بدء السماح بدخول الموقع'))
    permit_end_date = models.DateField(verbose_name=_('تاريخ انتهاء تصريح التشطيب الذاتي'))
    authorized_worker_count = models.PositiveIntegerField(default=5, verbose_name=_('عدد العمالة المصرح بدخولها'))
    workers_id_roster_file = models.FileField(upload_to='finishing/worker_rosters/', null=True, blank=True, verbose_name=_('كشف بطاقات الرقم القومي للعمالة المصرح لها'))
    
    is_active = models.BooleanField(default=True, verbose_name=_('التصريح سارٍ بالموقع'))
    notes = models.TextField(blank=True, default='', verbose_name=_('ملاحظات واشتراطات الأمن الصناعي والسلامة'))

    class Meta:
        verbose_name = _('تصريح تشطيب ذاتي وتأمين ديكور')
        verbose_name_plural = _('تصاريح التشطيب الذاتي وتأمينات الديكور')


class UnitMergerVariationOrder(models.Model):
    """أمر تعديل دمج وحدتين متجاورتين أو فتح دوبلكس وقص الخرسانات"""
    primary_order = models.OneToOneField(UnitFinishingOrder, on_delete=models.CASCADE, related_name='merger_order', verbose_name=_('أمر التعديل الرئيسي'))
    secondary_unit = models.ForeignKey('real_estate.PropertyUnit', on_delete=models.PROTECT, related_name='merged_secondary_orders', verbose_name=_('الوحدة الثانوية المدمجة'))
    secondary_contract = models.ForeignKey('real_estate.PropertyContract', on_delete=models.PROTECT, related_name='merged_secondary_orders', verbose_name=_('عقد الوحدة الثانوية'))
    
    is_duplex_slab_cut = models.BooleanField(default=False, verbose_name=_('يتطلب فتح سلم داخلي وقص في بلاطة السقف (Core Cutting)'))
    structural_engineer_approval_report = models.FileField(upload_to='finishing/structural_reports/', null=True, blank=True, verbose_name=_('تقرير واعتماد استشاري الخرسانات للسلامة الإنشائية'))
    rebar_rebarring_epoxy_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكلفة تزريع أشاير الحديد والتدعيم الإيبوكسي'))
    
    combined_new_unit_code = models.CharField(max_length=50, blank=True, default='', verbose_name=_('كود الوحدة المدمجة الموحد الجديد'))
    combined_total_area = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('إجمالي المساحة البيعية المدمجة'))
    is_approved_by_city_authority = models.BooleanField(default=False, verbose_name=_('معتمد من جهاز المدينة أو الإدارة الهندسية'))

    class Meta:
        verbose_name = _('أمر دمج وحدات ودوبلكس')
        verbose_name_plural = _('أوامر دمج الوحدات والدوبلكس')


class OwnerSuppliedMaterialInspection(models.Model):
    """محضر فحص واستلام خامات موردة من طرف العميل بالموقع (OSM)"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='owner_material_inspections', verbose_name=_('أمر التشطيب'))
    order_item = models.ForeignKey(UnitFinishingOrderItem, on_delete=models.CASCADE, verbose_name=_('بند المقايسة المرتبط'))
    material_name = models.CharField(max_length=150, verbose_name=_('اسم الخامة الموردة من العميل'))
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('الكمية المستلمة على الطبيعة'))
    measuring_unit = models.CharField(max_length=20, verbose_name=_('وحدة القياس'))
    inspection_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ الفحص والاستلام'))
    inspector_engineer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الموقع الفاحص'))
    
    is_free_from_defects = models.BooleanField(default=True, verbose_name=_('الخامة صالحة وسليمة هندسياً وخالية من التقويس والكسور'))
    defects_observed_notes = models.TextField(blank=True, default='', verbose_name=_('ملاحظات العيوب والتقويس المرصودة إن وجدت'))
    sample_photo = models.ImageField(upload_to='finishing/osm_inspections/', null=True, blank=True, verbose_name=_('صورة عينة الخامة المستلمة'))
    client_signed_disclaimer = models.BooleanField(default=True, verbose_name=_('العميل أقر بأن الضمان يشمل المصنعية فقط ولا يشمل جودة الخامة'))

    class Meta:
        verbose_name = _('محضر فحص خامات عميل (OSM)')
        verbose_name_plural = _('محاضر فحص خامات العميل (OSM)')


class FinishingDrawingRevision(models.Model):
    """سجل إصدارات وتعديلات المخططات التنفيذية والـ Shop Drawings للوحدة"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='drawing_revisions', verbose_name=_('أمر التشطيب'))
    revision_number = models.CharField(max_length=20, default='Rev 0', verbose_name=_('رقم الإصدار (Rev 0, Rev 1...)'))
    title = models.CharField(max_length=200, verbose_name=_('عنوان المخطط المعماري'))
    drawing_file = models.FileField(upload_to='finishing_orders/drawings_revisions/', verbose_name=_('ملف المخطط (PDF/DWG)'))
    webp_thumbnail = models.ImageField(upload_to='finishing/drawings/thumbs/', null=True, blank=True, verbose_name=_('صورة مصغرة مضغوطة للمخطط بصيغة WebP (< 40KB)'))
    is_consultant_approved = models.BooleanField(default=False, verbose_name=_('معتمد من الاستشاري / مهندس التعديلات'))
    consultant_approval_date = models.DateTimeField(null=True, blank=True, verbose_name=_('تاريخ اعتماد الاستشاري'))
    is_client_agreed = models.BooleanField(default=False, verbose_name=_('موافق عليه وموقع من العميل'))
    is_active_approved_rev = models.BooleanField(default=True, verbose_name=_('الإصدار النشط الساري للتنفيذ بالموقع'))
    change_summary = models.TextField(blank=True, default='', verbose_name=_('ملخص التعديلات المعمارية عن الإصدار السابق'))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('إصدار مخطط تنفيذي')
        verbose_name_plural = _('إصدارات المخططات التنفيذية')
        ordering = ['-created_at']


class FinishingMaterialRequisition(models.Model):
    """إذن صرف خامات تشطيب من مخزن المشروع لوحدة وفراغ محدد بكوتة المقايسة واستهلاك طبقات التكلفة"""
    requisition_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم إذن صرف الخامات'))
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='material_requisitions', verbose_name=_('أمر التشطيب'))
    order_item = models.ForeignKey(UnitFinishingOrderItem, on_delete=models.PROTECT, related_name='material_issues', verbose_name=_('بند المقايسة المرتبط'))
    product = models.ForeignKey('product.Product', on_delete=models.PROTECT, verbose_name=_('الصنف المنصرف من المخزن'))
    warehouse = models.ForeignKey('product.Warehouse', on_delete=models.PROTECT, verbose_name=_('المخزن المنصرف منه'))
    contractor = models.ForeignKey('supplier.Supplier', on_delete=models.PROTECT, verbose_name=_('مقاول الباطن المستلم'))
    class TransactionType(models.TextChoices):
        ISSUE = 'ISSUE', _('إذن صرف خامات للموقع')
        RETURN = 'RETURN', _('إذن ارتجاع فائض سليم للمخزن')

    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        default=TransactionType.ISSUE,
        verbose_name=_('نوع الحركة المخزنية')
    )
    quantity_requested = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('الكمية المطلوبة'))
    quantity_issued = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('الكمية المنفذة فعلياً (صرف / ارتجاع)'))
    issue_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ العملية'))
    batch_expiry_date = models.DateField(null=True, blank=True, verbose_name=_('تاريخ انتهاء صلاحية الكيماويات والمواد العازلة'))
    shelf_life_verified = models.BooleanField(default=True, verbose_name=_('تم التحقق من سريان الصلاحية لأكثر من 30 يوماً'))
    return_reason = models.TextField(blank=True, default='', verbose_name=_('سبب الارتجاع وحالة الأصناف السليمة'))
    is_cost_reversed = models.BooleanField(default=False, verbose_name=_('تم عكس قيد التكلفة وتخفيض تكلفة التشطيب'))
    
    # Perpetual Inventory Cost Layer Link
    cost_consumption = models.ForeignKey(
        'product.InventoryCostConsumption',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_('سجل استهلاك طبقة التكلفة بالمخزن')
    )
    stock_movement = models.ForeignKey('product.StockMovement', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('حركة المخزن المرتبطة'))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الموقع الطالب'))

    class Meta:
        verbose_name = _('إذن صرف / ارتجاع خامات تشطيب')
        verbose_name_plural = _('أذون صرف وارتجاع خامات التشطيب')


class FinishingStockAllocation(models.Model):
    """سجل حجز وتخصيص الخامات بالمخزن لأمر التشطيب فور سداد المقدم لحمايتها من فروق الأسعار والتضخم"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='stock_allocations', verbose_name=_('أمر التشطيب'))
    product = models.ForeignKey('product.Product', on_delete=models.PROTECT, verbose_name=_('الصنف المحجوز'))
    warehouse = models.ForeignKey('product.Warehouse', on_delete=models.PROTECT, verbose_name=_('المخزن المحجوز منه'))
    allocated_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('الكمية المحجوزة'))
    is_released = models.BooleanField(default=False, verbose_name=_('تم الإفراج/الصرف للموقع'))
    reserved_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ ووقت الحجز'))

    class Meta:
        verbose_name = _('حجز خامات تشطيب بالمخزن')
        verbose_name_plural = _('حجوزات خامات التشطيب بالمخازن')


class FinishingHydrostaticInspection(models.Model):
    """محضر اختبار ضغط مياه التغذية وغمر العزل المائي للفراغات المبتلة قبل الدفان والسيراميك"""
    class TestType(models.TextChoices):
        PRESSURE_8_BAR = 'PRESSURE_8_BAR', _('اختبار ضغط شبكة التغذية بالباروميتر (8-10 بار)')
        FLOOD_72_HOURS = 'FLOOD_72_HOURS', _('اختبار غمر العزل المائي بالماء (48-72 ساعة)')
        COMBINED = 'COMBINED', _('اختبار مزدوج للضغط والغمر معاً')

    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='hydrostatic_inspections', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المبتل (حمام / مطبخ / بالكونة)'))
    test_type = models.CharField(max_length=30, choices=TestType.choices, default=TestType.COMBINED, verbose_name=_('نوع الاختبار الميداني'))
    pressure_bar = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('8.00'), verbose_name=_('الضغط المسجل بالباروميتر (بار)'))
    duration_hours = models.PositiveIntegerField(default=48, verbose_name=_('مدة بقاء المياه / الضغط بالساعات'))
    is_passed = models.BooleanField(default=False, verbose_name=_('اجتاز الاختبار بنجاح وبدون أي تسريب'))
    pressure_gauge_photo = models.ImageField(upload_to='finishing/pressure_tests/', null=True, blank=True, verbose_name=_('صورة الباروميتر بالموقع'))
    flooding_photo = models.ImageField(upload_to='finishing/flooding_tests/', null=True, blank=True, verbose_name=_('صورة غمر العزل المائي بالموقع'))
    consultant_engineer_name = models.CharField(max_length=150, verbose_name=_('مهندس الاستشاري المشرف القائم بالمعاينة'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ ووقت الفحص'))
    notes = models.TextField(blank=True, default='', verbose_name=_('ملاحظات الفحص وسقف الدور السفلي'))

    class Meta:
        verbose_name = _('محضر فحص ضغط وعزل الفراغ المبتل')
        verbose_name_plural = _('محاضر فحص ضغط وعزل الفراغات المبتلة')


class FinishingHoldPointRule(models.Model):
    """قاعدة التتابع الهندسي الإلزامي بين بنود التشطيب (Hold-Point Dependency)"""
    spec = models.ForeignKey(FinishingItemSpec, on_delete=models.CASCADE, related_name='hold_point_rules', verbose_name=_('البند اللاحق المقيد'))
    preceding_spec = models.ForeignKey(FinishingItemSpec, on_delete=models.CASCADE, related_name='dependent_specs', verbose_name=_('البند السابق المشترط اعتماده أولاً'))
    description = models.CharField(max_length=255, verbose_name=_('سبب التبعية الهندسية (مثال: حظر المحارة قبل استلام السباكة والكهرباء)'))
    is_mandatory = models.BooleanField(default=True, verbose_name=_('إلزامي وحظر الصرف برمجياً'))
    allows_override = models.BooleanField(default=False, verbose_name=_('يسمح بتجاوز مدير المشروع الاستثنائي'))

    class Meta:
        verbose_name = _('قاعدة تتابع هندسي إلزامي')
        verbose_name_plural = _('قواعد التتابع الهندسي الإلزامي')


class FinishingItemWarrantyRecord(models.Model):
    """سجل شهادة ضمان المنتج الصادرة رسمياً من الشركة المصنعة المعتمدة للوحدة"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='warranty_records', verbose_name=_('أمر التشطيب'))
    order_item = models.ForeignKey(UnitFinishingOrderItem, on_delete=models.PROTECT, related_name='warranties', verbose_name=_('بند التشطيب'))
    manufacturer_name = models.CharField(max_length=150, verbose_name=_('الشركة المصنعة المعتمدة (مثال: أكواثيرم، ديورافيت)'))
    certificate_number = models.CharField(max_length=100, unique=True, verbose_name=_('رقم شهادة الضمان الرسمية'))
    warranty_years = models.PositiveIntegerField(default=10, verbose_name=_('مدة سريان الضمان بالسنوات'))
    inspection_pass_code = models.CharField(max_length=100, blank=True, default='', verbose_name=_('كود فحص مندوب المصنع الميداني'))
    certificate_file = models.FileField(upload_to='finishing/warranty_certs/', null=True, blank=True, verbose_name=_('ملف شهادة الضمان المعتمدة المختومة'))
    start_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ بدء سريان الضمان'))
    end_date = models.DateField(verbose_name=_('تاريخ انتهاء سريان الضمان'))

    class Meta:
        verbose_name = _('شهادة ضمان منتج معتمد')
        verbose_name_plural = _('شهادات ضمان المنتجات المعتمدة')


class FinishingAdvanceDeposit(models.Model):
    """دفعة مقدمة مسددة لجدية طلب التعديل / التشطيب"""
    class AllocationTarget(models.TextChoices):
        CASH_DEPOSIT = 'CASH_DEPOSIT', _('دفعة نقدية بالخزينة/البنك')
        ROLL_INTO_INSTALLMENTS = 'ROLL_INTO_INSTALLMENTS', _('ترحيلها وإضافتها لخطة أقساط التشطيب')

    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='deposits', verbose_name=_('أمر التشطيب'))
    receipt_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم إيصال السداد'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('مبلغ الدفعة المسدد'))
    receipt_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ السداد'))
    allocation_target = models.CharField(max_length=30, choices=AllocationTarget.choices, default=AllocationTarget.CASH_DEPOSIT, verbose_name=_('توجيه الدفعة'))
    customer_payment = models.ForeignKey(
        'customer.CustomerPayment',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_advance_deposits',
        verbose_name=_('إيصال دفعة العميل المحصلة')
    )
    journal_entry = models.ForeignKey(
        'financial.JournalEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_advance_deposits',
        verbose_name=_('قيد اليومية المحاسبي')
    )
    notes = models.TextField(blank=True, default='', verbose_name=_('ملاحظات'))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المسجل'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))

    class Meta:
        verbose_name = _('دفعة تشطيب مسددة')
        verbose_name_plural = _('دفعات التشطيب المسددة')


class FinishingInstallmentPlan(models.Model):
    """خطة أقساط التشطيب والتعديلات المستقلة قانونياً عن عقد بيع الوحدة"""
    plan_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم خطة أقساط التشطيب'))
    customer = models.ForeignKey('customer.Customer', on_delete=models.PROTECT, related_name='finishing_installment_plans', verbose_name=_('العميل'))
    unit = models.ForeignKey('real_estate.PropertyUnit', on_delete=models.PROTECT, verbose_name=_('الوحدة'))
    total_finishing_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('إجمالي قيمة التشطيب المجدولة'))
    down_payment_paid = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('الدفعة المقدمة المسددة'))
    scheduled_balance = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('الرصيد المجدول على أقساط'))
    number_of_installments = models.PositiveIntegerField(default=4, verbose_name=_('عدد الأقساط'))
    start_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ بدء الأقساط'))
    status = models.CharField(
        max_length=30,
        choices=[('ACTIVE', _('سارية')), ('SETTLED', _('مسددة بالكامل')), ('DEFAULTED', _('متعثرة ومحالة للمطالبة'))],
        default='ACTIVE',
        verbose_name=_('حالة الخطة')
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المسؤول'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('تاريخ الإنشاء'))

    class Meta:
        verbose_name = _('خطة أقساط تشطيب مستقلة')
        verbose_name_plural = _('خطط أقساط التشطيب المستقلة')


class FinishingInstallmentItem(models.Model):
    """قسط تفصيلي مستحق ضمن خطة أقساط التشطيب المستقلة مربوط بدورة تطبيق الشيكات"""
    plan = models.ForeignKey(FinishingInstallmentPlan, on_delete=models.CASCADE, related_name='items', verbose_name=_('خطة الأقساط'))
    installment_number = models.PositiveIntegerField(verbose_name=_('رقم القسط'))
    due_date = models.DateField(verbose_name=_('تاريخ الاستحقاق'))
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('قيمة القسط'))
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('المبلغ المسدد'))
    is_settled = models.BooleanField(default=False, verbose_name=_('مسدد بالكامل'))
    cheque = models.ForeignKey('cheques.Cheque', null=True, blank=True, on_delete=models.SET_NULL, related_name='finishing_installments', verbose_name=_('الشيك الآجل المرتبط'))
    milestone_trigger_name = models.CharField(max_length=150, blank=True, default='', verbose_name=_('مرحلة التنفيذ الميدانية المشروطة لصرف القسط'))

    class Meta:
        verbose_name = _('قسط تشطيب مستحق')
        verbose_name_plural = _('أقساط تشطيب مستحقة')
        ordering = ['due_date', 'installment_number']


class FinishingWorkOrder(models.Model):
    """أمر شغل تشطيب ميداني صادر لمقاول الموقع (مربوط بالمسار الأول Track 1 مع تأمين الضمان 5%)"""
    class WorkStatus(models.TextChoices):
        ISSUED = 'ISSUED', _('صادر ولم يبدأ')
        IN_PROGRESS = 'IN_PROGRESS', _('قيد العمل بالموقع')
        INSPECTION_REQUESTED = 'INSPECTION_REQUESTED', _('طلب استلام هندسي (WIR)')
        SNAGGING = 'SNAGGING', _('توجد ملاحظات قيد التلافي')
        ACCEPTED = 'ACCEPTED', _('مستلم ومطابق للمواصفات')

    work_order_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم أمر الشغل الميداني'))
    finishing_order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='work_orders', verbose_name=_('طلب التشطيب الرئيسي'))
    contractor = models.ForeignKey(
        'supplier.Supplier',
        on_delete=models.PROTECT,
        related_name='finishing_work_orders',
        verbose_name=_('المقاول المنفذ بالموقع')
    )
    contractor_contract = models.ForeignKey(
        'real_estate.ContractorContract',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='finishing_work_orders',
        verbose_name=_('عقد المقاول بالمسار الأول (Track 1)')
    )
    is_main_contractor_vo = models.BooleanField(
        default=False,
        verbose_name=_('أمر تغيير إلزامي للمقاول العام أثناء مرحلة الهيكل (HSE Protection)')
    )
    trade_category = models.CharField(max_length=30, choices=FinishingItemCategory.choices, verbose_name=_('حرفة التشطيب'))
    
    # Financial & Warranty Retention
    agreed_subcontract_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('قيمة مقاولة الباطن المتفق عليها'))
    retention_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('5.00'), verbose_name=_('نسبة تأمين ضمان الأعمال المحتجزة (%)'))
    retained_warranty_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قيمة تأمين الضمان المحتجزة لمدة سنة'))
    retention_released = models.BooleanField(default=False, verbose_name=_('تم الإفراج عن التأمين بعد انتهاء سنة الضمان'))

    start_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ بدء الأعمال'))
    expected_end_date = models.DateField(verbose_name=_('تاريخ الانتهاء المخطط'))
    actual_end_date = models.DateField(null=True, blank=True, verbose_name=_('تاريخ الانتهاء الفعلي'))
    status = models.CharField(max_length=30, choices=WorkStatus.choices, default=WorkStatus.ISSUED, verbose_name=_('حالة التنفيذ'))
    supervising_engineer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الموقع المشرف'))

    class Meta:
        verbose_name = _('أمر شغل تشطيب ميداني')
        verbose_name_plural = _('أوامر شغل التشطيب الميدانية')


# -------------------------------------------------------------------------------------------------
# 🛡️ المعمارية الموحدة لملاحظات الاستلام الميدانية (Unified Field Snagging)
# بدلاً من تكرار الجداول في قاعدة البيانات وتشتيت مهندس الموقع بين شاشتين، يتم توسيع وتوحيد
# نموذج UnitSnagItem القائم في real_estate/models/engineering.py وربطه بأمر التشطيب وأمر الشغل:
# -------------------------------------------------------------------------------------------------
# في real_estate/models/engineering.py يضاف:
# finishing_order = models.ForeignKey('real_estate.UnitFinishingOrder', null=True, blank=True, on_delete=models.CASCADE, related_name='snag_items', verbose_name=_('أمر التشطيب المرتبط'))
# work_order = models.ForeignKey('real_estate.FinishingWorkOrder', null=True, blank=True, on_delete=models.CASCADE, related_name='snag_items', verbose_name=_('أمر الشغل المرتبط'))
# workspace = models.ForeignKey('real_estate.FinishingWorkspace', null=True, blank=True, on_delete=models.SET_NULL, related_name='snag_items', verbose_name=_('الفراغ المعماري'))
#
# ولدعم التوافق البرمجي العكسي التام (Backward-Compatibility Alias):
from real_estate.models.engineering import UnitSnagItem
FinishingSnagItem = UnitSnagItem  # الاسم المستعار المعتمد لمنع كسر استدعاءات الكود القديمة


class FinishingAsBuiltReconciliation(models.Model):
    """محضر تصفية ومطابقة الحصر الميداني الفعلي للتشطيب قبل التسليم النهائي (As-Built True-Up)"""
    order = models.OneToOneField(UnitFinishingOrder, on_delete=models.PROTECT, related_name='as_built_reconciliation', verbose_name=_('أمر التشطيب'))
    reconciliation_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم محضر التصفية'))
    reconciliation_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ محضر تصفية الحصر'))
    
    estimated_boq_total = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('إجمالي المقايسة التقديرية الأصلية'))
    actual_as_built_total = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('إجمالي الحصر الميداني الفعلي As-Built'))
    variance_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('فارق التصفية (الفعلية - التقديرية)'))
    
    balancing_action = models.CharField(
        max_length=30,
        choices=[
            ('SUPPLEMENTAL_INVOICE', _('قسط تسوية مدين إضافي على العميل')),
            ('CREDIT_NOTE_REFUND', _('إشعار دائن وخصم لصالح العميل')),
            ('ABSORBED_TOLERANCE', _('استيعاب الفارق ضمن هامش المقطوعية المسموح'))
        ],
        verbose_name=_('الإجراء المالي المتبع للتسوية')
    )
    settlement_installment = models.ForeignKey(
        FinishingInstallmentItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_('قسط التسوية الختامي المنشأ')
    )
    is_finalized = models.BooleanField(default=False, verbose_name=_('تم اعتماد التصفية وإغلاق الحساب'))
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المعتمد (مدير الحسابات/CFO)'))

    class Meta:
        verbose_name = _('محضر تصفية حصر تشطيب فعلي')
        verbose_name_plural = _('محاضر تصفية حصر التشطيب الفعلية')


class FinishingCancellationSettlement(models.Model):
    """محضر تصفية إلغاء أمر التشطيب وحساب التكاليف الغارقة والمشتريات المهدرة"""
    order = models.OneToOneField(UnitFinishingOrder, on_delete=models.PROTECT, related_name='cancellation_settlement', verbose_name=_('أمر التشطيب الملغى'))
    settlement_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم محضر تصفية الإلغاء'))
    cancellation_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ طلب الإلغاء'))
    cancellation_reason = models.TextField(verbose_name=_('أسباب ومبررات إلغاء التعديل/التشطيب'))
    
    # Sunk Costs Breakdown
    executed_demolition_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكلفة أعمال التكسير المنفذة بالفعل'))
    custom_materials_scrap_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('تكلفة خامات مخصصة ومقطوعة لا يمكن إرجاعها للمخزن'))
    labor_costs_incurred = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('مصنعيات عمالة منفذة حتى الإلغاء'))
    earned_supervision_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('أتعاب إشراف هندسي مستحقة لتاريخه'))
    total_sunk_costs = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي التكاليف الغارقة والمصروفات غير المستردة'))
    
    deposit_paid = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('إجمالي الدفعة المقدمة المسددة'))
    net_refundable_to_client = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('الصافي المسترد للعميل (في حال الدفعة > التكاليف)'))
    shortfall_due_from_client = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), verbose_name=_('المبلغ المستحق على العميل (في حال التكاليف > الدفعة)'))
    
    refund_payment = models.ForeignKey('customer.CustomerPayment', null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_('إيصال/سند صرف رد المبلغ المتبقي'))
    is_settled_and_closed = models.BooleanField(default=False, verbose_name=_('تم إنهاء التصفية والمخالصة المالية التامة'))
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المعتمد (CFO)'))

    class Meta:
        verbose_name = _('محضر تصفية إلغاء أمر تشطيب')
        verbose_name_plural = _('محاضر تصفية إلغاء أوامر التشطيب')


class FinishingHandoverProtocol(models.Model):
    """محضر الاستلام والتسليم النهائي لأعمال التشطيب والتعديل مع العميل"""
    order = models.OneToOneField(UnitFinishingOrder, on_delete=models.PROTECT, related_name='handover_protocol', verbose_name=_('أمر التشطيب'))
    handover_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم محضر التسليم'))
    handover_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ محضر التسليم'))
    client_attended = models.BooleanField(default=True, verbose_name=_('حضور العميل أو وكيله الرسمي'))
    client_representative_name = models.CharField(max_length=150, blank=True, default='', verbose_name=_('اسم المستلم / الوكيل'))
    is_accepted_without_snags = models.BooleanField(default=True, verbose_name=_('استلام نهائي بدون ملاحظات'))
    warranty_start_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ بدء سريان ضمان التشطيب'))
    warranty_months = models.PositiveIntegerField(default=12, verbose_name=_('مدة ضمان الأعمال المعمارية (شهراً)'))
    client_signed_document = models.FileField(upload_to='finishing/handovers/', verbose_name=_('محضر التسليم الموقع والممسوح ضوئياً'))
    cleared_for_occupancy = models.BooleanField(default=True, verbose_name=_('الوحدة صالحة للسكن وتسليم المفاتيح'))

    class Meta:
        verbose_name = _('محضر تسليم تشطيب نهائي')
        verbose_name_plural = _('محاضر تسليم التشطيب النهائية')


class FinishingSwapSettlement(models.Model):
    """محضر تسوية تشطيبات الوحدة عند استبدال العميل لشقته بوحدة أخرى (Swap Settlement)"""
    swap_record = models.ForeignKey('real_estate.UnitSwapRecord', on_delete=models.CASCADE, related_name='finishing_swap_settlements', verbose_name=_('سجل الاستبدال المرتبط'))
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.PROTECT, related_name='swap_settlements', verbose_name=_('أمر التشطيب للوحدة الأصلية'))
    sunk_cost_demolition = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('التكاليف الغارقة للأعمال غير القابلة للنقل'))
    retained_client_credit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('الرصيد المتبقي المرحل للوحدة الجديدة'))
    upgraded_unit_value_added = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('القيمة المضافة لسعر بيع الوحدة القديمة المعاد طرحها'))
    settlement_notes = models.TextField(blank=True, default='', verbose_name=_('ملاحظات التسوية الفنية والمالية'))

    class Meta:
        verbose_name = _('تسوية تشطيبات استبدال الوحدة')
        verbose_name_plural = _('تسويات تشطيبات استبدال الوحدات')


class FinishingSecureLockUpRecord(models.Model):
    """محضر قفل وتأمين عهدة الشقة والمفاتيح بعد تركيب الباب الخارجي (Lock-Up Milestone)"""
    order = models.OneToOneField(UnitFinishingOrder, on_delete=models.CASCADE, related_name='lockup_record', verbose_name=_('أمر التشطيب'))
    lockup_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ قفل وتأمين الشقة'))
    exterior_door_installed = models.BooleanField(default=True, verbose_name=_('تم تركيب الباب الخارجي والتأكد من الغلق المحكم'))
    key_custody_officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='key_custody_finishing_records', verbose_name=_('مسؤول أمن الموقع المستلم لعهدة المفتاح'))
    key_tag_code = models.CharField(max_length=50, verbose_name=_('كود ميدالية مفاتيح الشقة بخزينة الموقع'))
    access_restricted = models.BooleanField(default=True, verbose_name=_('حظر الدخول إلا بتصريح وسجل زوار معتمد'))
    cylinder_rekeyed_successfully = models.BooleanField(default=False, verbose_name=_('تم تفعيل سلندر المالك وسقوط بلية مفتاح التشطيب المؤقت'))
    builder_key_deactivated = models.BooleanField(default=False, verbose_name=_('تم إبطال مفعول مفتاح الإنشاءات نهائياً'))
    handover_to_client_date = models.DateField(null=True, blank=True, verbose_name=_('تاريخ تسليم المفاتيح للعميل'))

    class Meta:
        verbose_name = _('محضر قفل وتأمين عهدة الشقة')
        verbose_name_plural = _('محاضر قفل وتأمين عهدة الشقق')


class FinishingSampleSubmittalRecord(models.Model):
    """سجل اعتماد لوحة العينات المعمارية وتوقيع العميل والاستشاري المادي (Sample Board Sign-Off)"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='sample_submittals', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعماري'))
    spec = models.ForeignKey(FinishingItemSpec, on_delete=models.PROTECT, verbose_name=_('بند المواصفة'))
    batch_or_dyelot_code = models.CharField(max_length=100, blank=True, default='', verbose_name=_('كود التشغيلة أو صبغة اللون (Batch / Dye-Lot)'))
    sample_board_photo = models.ImageField(upload_to='finishing/samples/', verbose_name=_('صورة لوحة العينة الموقعة من العميل'))
    client_physical_signature = models.BooleanField(default=True, verbose_name=_('تم توقيع العميل خطياً على ظهر العينة المادية'))
    custody_location = models.CharField(max_length=150, default='خزينة مكتب الموقع الرئيسي', verbose_name=_('مقر حفظ العينة بالمشروع'))
    approved_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ ووقت اعتماد العينة'))

    class Meta:
        verbose_name = _('اعتماد عينة تشطيب معمارية')
        verbose_name_plural = _('اعتمادات عينات التشطيب المعمارية')


class FinishingWeatherStoppageLog(models.Model):
    """سجل توقف الأعمال الميدانية للظروف الجوية والقوة القاهرة (Weather & Force Majeure Stoppage)"""
    class WeatherCondition(models.TextChoices):
        HEAVY_RAIN = 'HEAVY_RAIN', _('أمطار وسيول مانعة للعزل والدهانات')
        SANDSTORM = 'SANDSTORM', _('عواصف رملية مانعة لأعمال الواجهات')
        EXCESSIVE_HUMIDITY = 'EXCESSIVE_HUMIDITY', _('رطوبة جوية مفرطة تؤخر جفاف اللياسة')
        OTHER_FORCE_MAJEURE = 'OTHER_FORCE_MAJEURE', _('ظروف قهرية ميدانية أخرى')

    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='weather_stoppages', verbose_name=_('أمر التشطيب'))
    condition = models.CharField(max_length=30, choices=WeatherCondition.choices, verbose_name=_('الظرف المناخي'))
    start_date = models.DateField(verbose_name=_('تاريخ بدء التوقف'))
    end_date = models.DateField(verbose_name=_('تاريخ استئناف العمل'))
    days_lost = models.PositiveIntegerField(verbose_name=_('عدد الأيام المفقودة'))
    consultant_report_file = models.FileField(upload_to='finishing/weather_reports/', verbose_name=_('تقرير الاستشاري المعتمد للتوقف المناخي'))
    is_extension_granted = models.BooleanField(default=True, verbose_name=_('تم ترحيل وتمديد موعد التسليم'))

    class Meta:
        verbose_name = _('سجل توقف مناخي وقوة قاهرة')
        verbose_name_plural = _('سجلات التوقف المناخي والقوة القاهرة')


class FinishingHotWorkPermit(models.Model):
    """تصريح تنفيذ الأعمال الساخنة واللحام واللهب المكشوف بالفراغات المعمارية (Hot-Work Permit)"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='hot_work_permits', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعماري'))
    contractor = models.ForeignKey('supplier.Supplier', on_delete=models.PROTECT, verbose_name=_('مقاول الباطن القائم بالعمل'))
    work_description = models.CharField(max_length=255, verbose_name=_('وصف العمل (لحام حديد / تسخين عزل بيتومين بالبشبوري)'))
    permit_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ التصريح'))
    fire_extinguishers_verified = models.BooleanField(default=False, verbose_name=_('تم التحقق الميداني من وجود طفايات بودرة وCO2 صالحة'))
    combustible_materials_cleared = models.BooleanField(default=False, verbose_name=_('تم إخلاء المواد القابلة للاشتعال من محيط 5 أمتار'))
    safety_officer_signature = models.CharField(max_length=150, verbose_name=_('اسم وتوقيع مسؤول السلامة والصحة المهنية (HSE)'))
    is_approved = models.BooleanField(default=False, verbose_name=_('التصريح معتمد وسارٍ لبدء العمل'))

    class Meta:
        verbose_name = _('تصريح أعمال ساخنة ولحام')
        verbose_name_plural = _('تصاريح الأعمال الساخنة واللحام')


class FinishingDebrisCartageWaybill(models.Model):
    """بوليصة نقل وتشوين ردميات التكسير للمقالب العمومية المرخصة (Debris Cartage Waybill)"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='debris_waybills', verbose_name=_('أمر التشطيب'))
    truck_number = models.CharField(max_length=50, verbose_name=_('رقم لوحة سيارة النقل (القلاب)'))
    driver_name = models.CharField(max_length=150, verbose_name=_('اسم السائق'))
    trip_date = models.DateField(default=timezone.localdate, verbose_name=_('تاريخ النقلة'))
    estimated_volume_m3 = models.DecimalField(max_digits=8, decimal_places=2, verbose_name=_('حجم الردميات المقدر (م³)'))
    official_dump_site_name = models.CharField(max_length=150, default='مقلب المحافظة العمومي المعتمد', verbose_name=_('اسم المقلب المرخص'))
    disposal_receipt_file = models.FileField(upload_to='finishing/debris_receipts/', null=True, blank=True, verbose_name=_('إيصال تفريغ المقلب العمومي'))
    is_verified_by_site_engineer = models.BooleanField(default=False, verbose_name=_('معتمد من مهندس الموقع لمنع غرامات جهاز المدينة'))

    class Meta:
        verbose_name = _('بوليصة نقل ردميات ومخلفات هدم')
        verbose_name_plural = _('بولايص نقل ردميات ومخلفات الهدم')


class BookingPreContractVariationStudy(models.Model):
    """دراسة جدوى التعديلات المعمارية المبدئية أثناء مرحلة الحجز وقبل تحرير العقد النهائي"""
    booking = models.ForeignKey('real_estate.UnitBooking', on_delete=models.CASCADE, related_name='variation_studies', verbose_name=_('الحجز المبدئي المرتبط'))
    unit = models.ForeignKey('real_estate.PropertyUnit', on_delete=models.PROTECT, verbose_name=_('الوحدة المحجوزة'))
    requested_changes_summary = models.TextField(verbose_name=_('ملخص التعديلات المعمارية المطلوبة من العميل'))
    is_architecturally_feasible = models.BooleanField(default=False, verbose_name=_('التعديل مسموح به معمارياً وإنشائياً'))
    rejection_engineering_reason = models.TextField(blank=True, default='', verbose_name=_('سبب الرفض الهندسي في حال عدم الإمكانية'))
    preliminary_estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name=_('التكلفة التقديرية المبدئية'))
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس المكتب الفني الدارس'))
    reviewed_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ الدراسة الفنية'))

    class Meta:
        verbose_name = _('دراسة جدوى تعديل لحجز مبدئي')
        verbose_name_plural = _('دراسات جدوى تعديلات الحجوزات المبدئية')


class PlasterMoistureInspectionRecord(models.Model):
    """محضر فحص نسبة رطوبة المحارة بجهاز القياس الرقمي قبل الدهانات (Moisture Meter Record)"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='moisture_inspections', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعماري'))
    tested_wall_description = models.CharField(max_length=150, verbose_name=_('الحائط المفحوص بالفراغ'))
    moisture_percentage = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_('نسبة الرطوبة المسجلة بالجهاز %'))
    is_passed = models.BooleanField(default=False, verbose_name=_('الرطوبة أقل من 12% ومسموح ببدء الدهان'))
    moisture_meter_photo = models.ImageField(upload_to='finishing/moisture_tests/', verbose_name=_('صورة قراءة شاشة الجهاز الرقمي'))
    site_qa_engineer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس ضبط الجودة القائم بالفحص'))
    tested_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ ووقت الفحص'))

    class Meta:
        verbose_name = _('محضر فحص رطوبة المحارة')
        verbose_name_plural = _('محاضر فحص رطوبة المحارة')


class ApprovedFacadeEnclosureCatalog(models.Model):
    """الكتالوج المعماري المعتمد لتقفيلات الشرفات والستائر والواجهات الخارجية للمشروع"""
    project = models.ForeignKey('real_estate.RealEstateProject', on_delete=models.CASCADE, related_name='facade_catalogs', verbose_name=_('المشروع العقاري'))
    enclosure_type = models.CharField(max_length=50, choices=[('ALUMINUM_BALCONY', _('تقفيل شرفة ألوميتال')), ('MOTORIZED_SHUTTER', _('شيش حصير كهربائي')), ('GLASS_CURTAIN', _('زجاج سيكوريت قابل للطي'))], verbose_name=_('نوع التقفيل'))
    approved_ral_color_code = models.CharField(max_length=50, default='RAL 7016', verbose_name=_('كود لون الدهان المعماري المعتمد'))
    approved_profile_brand = models.CharField(max_length=100, verbose_name=_('قطاع الألوميتال المعتمد (جامبو، تانجو)'))
    is_active = models.BooleanField(default=True, verbose_name=_('سارٍ ومعتمد للواجهة'))

    class Meta:
        verbose_name = _('مواصفة تقفيل واجهة معتمدة')
        verbose_name_plural = _('مواصفات تقفيل الواجهات المعتمدة')


class RecyclablePackagingGatePass(models.Model):
    """تصريح خروج وتدوير مخلفات التغليف والكرتون والبالتات الخشبية (Packaging Gate Pass)"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='packaging_gate_passes', verbose_name=_('أمر التشطيب'))
    gate_pass_number = models.CharField(max_length=50, unique=True, verbose_name=_('رقم تصريح البوابة'))
    materials_description = models.CharField(max_length=255, verbose_name=_('توصيف المواد (كراتين سيراميك، بالتات خشب، فوارغ أسمنت)'))
    quantity_estimate = models.CharField(max_length=100, verbose_name=_('الكمية التقديرية (عدد بالتات / وزن كرتون)'))
    buyer_or_recycler_name = models.CharField(max_length=150, verbose_name=_('جهة الاستلام / مقاول التدوير'))
    security_officer_name = models.CharField(max_length=150, verbose_name=_('مسؤول أمن البوابة المصرح'))
    exit_date = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت الخروج من البوابة'))

    class Meta:
        verbose_name = _('تصريح خروج مخلفات تغليف وتدوير')
        verbose_name_plural = _('تصاريح خروج مخلفات التغليف والتدوير')


class AntiTermiteTreatmentRecord(models.Model):
    """محضر رش ومعالجة رمال الدفان ضد النمل الأبيض وحشرات الأخشاب قبل الباركيه والسيراميك"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='termite_treatments', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعالج'))
    chemical_used = models.CharField(max_length=150, default='مبيد بريبان TC 48% معتمد', verbose_name=_('المبيد الكيميائي المستخدم'))
    treated_area_m2 = models.DecimalField(max_digits=8, decimal_places=2, verbose_name=_('المساحة المعالجة بالرش (م²)'))
    certified_pest_control_company = models.CharField(max_length=150, verbose_name=_('الشركة المتخصصة القائمة بالرش'))
    warranty_certificate_number = models.CharField(max_length=100, verbose_name=_('رقم شهادة ضمان مكافحة الآفات (5 سنوات)'))
    is_verified_by_site_engineer = models.BooleanField(default=False, verbose_name=_('تم التحقق الميداني واعتماد الرش'))
    treated_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت المعالجة'))

    class Meta:
        verbose_name = _('محضر معالجة ومكافحة نمل أبيض')
        verbose_name_plural = _('محاضر معالجة ومكافحة النمل الأبيض')


class BalconyDrainageSlopeInspection(models.Model):
    """محضر فحص واختبار تدفق وميول مياه الأمطار للشرفات والتراسات المكشوفة"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='balcony_slope_inspections', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الشرفة / التراس'))
    is_gravity_flow_successful = models.BooleanField(default=False, verbose_name=_('انسياب المياه ذاتياً نحو البيبة بنسبة 100%'))
    water_ponding_detected = models.BooleanField(default=False, verbose_name=_('تم رصد برك أو ركود مائي (مرفوض)'))
    drainage_slope_percentage = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('1.50'), verbose_name=_('نسبة الميل المقاسة %'))
    test_photo = models.ImageField(upload_to='finishing/slope_tests/', verbose_name=_('صورة اختبار التدفق بالموقع'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الموقع الفاحص'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت الفحص'))

    class Meta:
        verbose_name = _('محضر فحص ميول صرف الشرفة')
        verbose_name_plural = _('محاضر فحص ميول صرف الشرفات')


class FinishingTileBatchBarcodeRecord(models.Model):
    """سجل فحص وتطابق باركود الشيد والكاليبر للسيراميك والبورسلين قبل الصرف"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='tile_barcode_records', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعماري المستهدف'))
    product = models.ForeignKey('product.Product', on_delete=models.PROTECT, verbose_name=_('صنف السيراميك / البورسلين'))
    barcode_scanned = models.CharField(max_length=100, verbose_name=_('الباركود الممسوح للكرتونة'))
    shade_code = models.CharField(max_length=50, verbose_name=_('كود الشيد / الطبخة (Shade Code)'))
    caliber_code = models.CharField(max_length=50, verbose_name=_('كود المعايرة والمقاس (Caliber Code)'))
    scanned_quantity_sqm = models.DecimalField(max_digits=10, decimal_places=2, verbose_name=_('الكمية الممسوحة بالمتر المربع'))
    is_shade_mismatch_detected = models.BooleanField(default=False, verbose_name=_('رصد اختلاف في الشيد أو الكاليبر بالفراغ'))
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('أمين المخزن الفاحص'))
    verified_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت المسح'))

    class Meta:
        verbose_name = _('سجل باركود شيد وكاليبر البلاط')
        verbose_name_plural = _('سجلات باركود شيد وكاليبر البلاط')


class FiberOpticContinuityInspection(models.Model):
    """محضر فحص وقياس استمرارية كابل الفايبر FTTH قبل إغلاق الأسقف والمحارة"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='fiber_continuity_inspections', verbose_name=_('أمر التشطيب'))
    run_point_from = models.CharField(max_length=100, default='Floor Splitter Box', verbose_name=_('نقطة البداية (بوكس الدور)'))
    run_point_to = models.CharField(max_length=100, default='Unit Optical Network Terminal (ONT)', verbose_name=_('نقطة النهاية (شاسيه الوحدة)'))
    optical_loss_db = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_('الفقد الضوئي المقاس (dB)'))
    is_continuity_passed = models.BooleanField(default=False, verbose_name=_('اجتياز اختبار الليزر المرئي VFL بنجاح'))
    bend_radius_compliant = models.BooleanField(default=True, verbose_name=_('مراعاة الحد الأدنى لزاوية الانحناء وعدم وجود ثني حاد'))
    vfl_test_photo = models.ImageField(upload_to='finishing/fiber_tests/', verbose_name=_('صورة اختبار الليزر المرئي VFL'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الاتصالات / الموقع'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ الفحص'))

    class Meta:
        verbose_name = _('محضر فحص استمرارية كابل الفايبر FTTH')
        verbose_name_plural = _('محاضر فحص استمرارية كوابل الفايبر FTTH')


class ElevatorArmorCladdingInspection(models.Model):
    """محضر فحص تصفيح المصعد وضبط حساسات الحمولة قبل نقل خامات التشطيب"""
    project = models.ForeignKey('real_estate.RealEstateProject', on_delete=models.CASCADE, verbose_name=_('المشروع العقاري'))
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='elevator_cladding_inspections', verbose_name=_('أمر التشطيب المرخص له'))
    elevator_identifier = models.CharField(max_length=50, verbose_name=_('رقم / معرّف المصعد في البرج'))
    is_cabin_plywood_cladded = models.BooleanField(default=False, verbose_name=_('تصفيح جدران وأرضية الكابينة بالخشب والمطاط'))
    overload_sensor_tested = models.BooleanField(default=False, verbose_name=_('فحص وتفعيل جهاز استشعار الحمل الزائد (Overload)'))
    max_payload_kg = models.PositiveIntegerField(default=630, verbose_name=_('الحمولة القصوى المصرح بها (كجم)'))
    initial_odometer_trips = models.PositiveIntegerField(default=0, verbose_name=_('قراءة عداد المشاوير المبدئية للمصعد'))
    contractor_pledge_signed = models.BooleanField(default=False, verbose_name=_('توقيع المقاول/الشركة على تعهد تحمل أي تلفيات'))
    cladding_photo = models.ImageField(upload_to='finishing/elevator_cladding/', verbose_name=_('صورة توثيق تصفيح الكابينة'))
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مدير المرافق / مهندس الموقع'))
    approved_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت الفحص'))

    class Meta:
        verbose_name = _('محضر فحص وتصفيح مصعد لتشطيبات')
        verbose_name_plural = _('محاضر فحص وتصفيح المصاعد للتشطيبات')


class StructuralExpansionJointInspection(models.Model):
    """محضر فحص وتوثيق بروفيل فواصل التمدد والهبوط الإنشائي بالتشطيبات"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='expansion_joint_inspections', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعماري'))
    joint_type = models.CharField(
        max_length=30,
        choices=[
            ('SETTLEMENT', _('فاصل هبوط إنشائي')),
            ('EXPANSION', _('فاصل تمدد حراري')),
            ('SEISMIC', _('فاصل زلزالي')),
        ],
        default='EXPANSION',
        verbose_name=_('نوع الفاصل الإنشائي')
    )
    neoprene_profile_installed = models.BooleanField(default=False, verbose_name=_('تركيب بروفيل ألومنيوم بحشو نيوبرين مرن'))
    solid_tiling_over_joint_prevented = models.BooleanField(default=True, verbose_name=_('منع التبليط الصلب المستمر فوق الفاصل'))
    inspection_photo = models.ImageField(upload_to='finishing/expansion_joints/', verbose_name=_('صورة توثيق بروفيل الفاصل'))
    consultant_approved = models.BooleanField(default=False, verbose_name=_('اعتماد الاستشاري الهندسي'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المهندس المشرف'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ الاعتماد'))

    class Meta:
        verbose_name = _('محضر فحص فاصل تمدد إنشائي')
        verbose_name_plural = _('محاضر فحص فواصل التمدد الإنشائي')


class FacadeSleevePenetrationInspection(models.Model):
    """محضر فحص وعزل جلب واختراقات الواجهات الخارجية ونحاس التكييف"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='facade_sleeve_inspections', verbose_name=_('أمر التشطيب'))
    facade_orientation = models.CharField(max_length=50, verbose_name=_('جهة الواجهة / المنور'))
    sleeve_diameter_inches = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal('3.0'), verbose_name=_('قطر فتحة الكور / الجلبة (بوصة)'))
    pvc_sleeve_with_outward_slope = models.BooleanField(default=True, verbose_name=_('تركيب جلبة PVC بميول للخارج'))
    pu_sealant_applied = models.BooleanField(default=False, verbose_name=_('حقن الفراغ الحلقي ببولي يوريثان مقاوم للشمس (PU Sealant)'))
    escutcheon_flashing_installed = models.BooleanField(default=False, verbose_name=_('تركيب طوق تغطية معدني مانع للأمطار'))
    inspection_photo = models.ImageField(upload_to='finishing/facade_sleeves/', verbose_name=_('صورة فحص عزل الجلبة الخارجية'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الموقع الفاحص'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت الفحص'))

    class Meta:
        verbose_name = _('محضر فحص اختراق وعزل الواجهة')
        verbose_name_plural = _('محاضر فحص اختراقات وعزل الواجهات')


class HighValueFixtureReleaseGate(models.Model):
    """بوابة حظر والإفراج عن التركيبات الثمينة والدقيقة (خلاطات دفن، سمارت هوم)"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='high_value_release_gates', verbose_name=_('أمر التشطيب'))
    item_spec = models.ForeignKey(FinishingItemSpec, on_delete=models.PROTECT, verbose_name=_('بند المواصفة عالي القيمة'))
    is_painting_completed = models.BooleanField(default=False, verbose_name=_('اكتمال مرحلة الدهانات والكرانيش بالكامل'))
    is_main_door_securely_locked = models.BooleanField(default=False, verbose_name=_('تركيب وقفل باب الشقة الرئيسي بسلندر مؤمن'))
    warehouse_release_authorized = models.BooleanField(default=False, verbose_name=_('التصريح بالصرف والإنزال الميداني للشقة'))
    authorized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مدير المشروع / مهندس الموقع'))
    authorized_at = models.DateTimeField(null=True, blank=True, verbose_name=_('تاريخ التصريح بالصرف'))

    class Meta:
        verbose_name = _('بوابة صرف بند تشطيب عالي القيمة')
        verbose_name_plural = _('بوابات صرف بنود التشطيب عالية القيمة')


class FinishingContractorCARPolicyRecord(models.Model):
    """سجل بوليصة تأمين أخطار المقاولين الشاملة والمسؤولية المدنية للتشطيبات"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='car_policy_records', verbose_name=_('أمر التشطيب'))
    insurance_company_name = models.CharField(max_length=150, verbose_name=_('شركة التأمين المصدرة للبوليصة'))
    policy_number = models.CharField(max_length=80, verbose_name=_('رقم بوليصة التأمين'))
    coverage_amount = models.DecimalField(max_digits=14, decimal_places=2, verbose_name=_('مبلغ التغطية التأمينية الإجمالي'))
    third_party_liability_covered = models.BooleanField(default=True, verbose_name=_('تغطية المسؤولية المدنية تجاه الغير (TPL)'))
    water_damage_and_fire_covered = models.BooleanField(default=True, verbose_name=_('تغطية أخطار الحريق وتلفيات تسرب المياه'))
    policy_expiry_date = models.DateField(verbose_name=_('تاريخ انتهاء سريان البوليصة'))
    policy_document = models.FileField(upload_to='finishing/car_policies/', verbose_name=_('ملف وثيقة التأمين المعتمدة'))
    is_policy_verified = models.BooleanField(default=False, verbose_name=_('تم التحقق والاعتماد القانوني للبوليصة'))
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المسؤول القانوني / مدير التأمين'))

    class Meta:
        verbose_name = _('سجل بوليصة تأمين أخطار مقاول التشطيب')
        verbose_name_plural = _('سجلات بوالص تأمين أخطار مقاولي التشطيب')


class ElectricalFeederCapacityInspection(models.Model):
    """محضر فحص ومطابقة سعة كابل الصاعد وقاطع الكهرباء للأحمال التراكمية"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='feeder_capacity_inspections', verbose_name=_('أمر التشطيب'))
    total_hvac_tonnage = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_('إجمالي قدرة التكييفات (طن تبريد / حصان)'))
    total_connected_load_kva = models.DecimalField(max_digits=6, decimal_places=2, verbose_name=_('إجمالي الحمل الكهربائي التراكمي (kVA)'))
    allotted_riser_ampacity = models.PositiveIntegerField(verbose_name=_('سعة صاعد الوحدة المعتمدة هندسياً (أمبير)'))
    calculated_running_ampacity = models.DecimalField(max_digits=6, decimal_places=2, verbose_name=_('الأمبير التشغيلي المحسوب'))
    is_riser_upgrade_required = models.BooleanField(default=False, verbose_name=_('اشتراط ترقية كابل الصاعد والقاطع الرئيسي'))
    consultant_approval_letter = models.FileField(upload_to='finishing/electrical_approvals/', null=True, blank=True, verbose_name=_('موافقة الاستشاري على ترقية الصاعد'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الكهرباء الفاحص'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ الفحص'))

    class Meta:
        verbose_name = _('محضر مطابقة سعة صاعد الكهرباء')
        verbose_name_plural = _('محاضر مطابقة سعة صواعد الكهرباء')


class SubsequentTradeFloorProtectionInspection(models.Model):
    """محضر فحص وتوثيق تغليف وحماية الأرضيات قبل دخول الحرف اللاحقة"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='floor_protection_inspections', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعماري'))
    flooring_type = models.CharField(max_length=50, verbose_name=_('نوع الأرضية (رخام، بورسلين، باركيه)'))
    heavy_polyethylene_sheet_installed = models.BooleanField(default=True, verbose_name=_('فرد مشمع بولي إيثيلين سميك عازل'))
    corrugated_cardboard_or_geotextile_installed = models.BooleanField(default=True, verbose_name=_('تركيب كرتون مضلع مشمع أو شيتات حماية مقواة'))
    joints_taped_securely = models.BooleanField(default=True, verbose_name=_('تثبيت الفواصل بإحكام بشريط لاصق مقوى'))
    protection_photo = models.ImageField(upload_to='finishing/floor_protection/', verbose_name=_('صورة توثيق حماية الأرضية'))
    carpentry_painting_entry_permitted = models.BooleanField(default=False, verbose_name=_('التصريح بدخول فرق النجارة والدهان'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الموقع المشرف'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت الفحص'))

    class Meta:
        verbose_name = _('محضر حماية وتغليف الأرضيات')
        verbose_name_plural = _('محاضر حماية وتغليف الأرضيات')


class FinishingTemporaryUtilityRecord(models.Model):
    """سجل قراءات واستهلاك عدادات الكهرباء والمياه المؤقتة أثناء التشطيب"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='temporary_utility_records', verbose_name=_('أمر التشطيب'))
    electric_meter_reading_start = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قراءة عداد الكهرباء المبدئية (kWh)'))
    electric_meter_reading_end = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قراءة عداد الكهرباء النهائية (kWh)'))
    water_meter_reading_start = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قراءة عداد المياه المبدئية (م³)'))
    water_meter_reading_end = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('قراءة عداد المياه النهائية (م³)'))
    total_electric_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي تكلفة استهلاك الكهرباء'))
    total_water_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('إجمالي تكلفة استهلاك المياه'))
    is_settled_from_deposit = models.BooleanField(default=False, verbose_name=_('تمت التسوية والخصم من تأمين الديكور / المقايسة'))
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المسؤول عن تسجيل القراءات'))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_('تاريخ آخر تحديث'))

    class Meta:
        verbose_name = _('سجل استهلاك مرافق التشطيب المؤقتة')
        verbose_name_plural = _('سجلات استهلاك مرافق التشطيب المؤقتة')


class RooftopWaterproofingInspection(models.Model):
    """محضر فحص وعزل أسطح البنتهاوس واختبار شيتات الجذور والغمر 72 ساعة"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='rooftop_waterproofing_inspections', verbose_name=_('أمر التشطيب'))
    area_sqm = models.DecimalField(max_digits=8, decimal_places=2, verbose_name=_('مسطح السطح المعزول (م²)'))
    has_roof_garden_or_planters = models.BooleanField(default=False, verbose_name=_('يحتوي على حدائق معلقة أو أحواض زهور'))
    anti_root_membrane_installed = models.BooleanField(default=False, verbose_name=_('تركيب شيتات عزل جذور معتمدة (Anti-Root Membrane)'))
    flood_test_hours_completed = models.PositiveIntegerField(default=72, verbose_name=_('ساعات اختبار الغمر المائي المكتملة'))
    water_level_gauge_maintained = models.BooleanField(default=True, verbose_name=_('ثبات مسطرة منسوب المياه وخلو السقف السفلي من الترشيح'))
    flood_test_photo = models.ImageField(upload_to='finishing/rooftop_flood_tests/', verbose_name=_('صورة فحص الغمر بمسطرة القياس'))
    consultant_approved = models.BooleanField(default=False, verbose_name=_('اعتماد الاستشاري المشرف'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الموقع الفاحص'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت الفحص'))

    class Meta:
        verbose_name = _('محضر عزل واختبار سطح البنتهاوس')
        verbose_name_plural = _('محاضر عزل واختبار أسطح البنتهاوس')


class HeavyRiggingHoistingPermit(models.Model):
    """تصريح تشغيل أوناش الرفع الهيدروليكية الثقيلة بالكمبوند للمهمات العملاقة"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='heavy_rigging_permits', verbose_name=_('أمر التشطيب'))
    crane_capacity_tons = models.PositiveIntegerField(default=50, verbose_name=_('حمولة الونش الهيدروليكي (طن)'))
    item_description = models.CharField(max_length=200, verbose_name=_('وصف المهمات المرفوعة (جاكوزي، كمرات، زجاج كيرتن وول)'))
    outrigger_pad_distribution_verified = models.BooleanField(default=False, verbose_name=_('فحص وتوزيع أحمال أرجل الونش بفرشات خشب صلبة'))
    underground_utilities_cleared = models.BooleanField(default=False, verbose_name=_('التأكد من خلو المسار من غرف تفتيش الصرف وأسقف البدروم'))
    rigging_slings_certified = models.BooleanField(default=True, verbose_name=_('شهادة صلاحية ومعايرة وايرات وسلاسل الرفع'))
    safety_perimeter_established = models.BooleanField(default=True, verbose_name=_('إغلاق وتأمين مسار الحركة وشريط التحذير'))
    crane_inspection_photo = models.ImageField(upload_to='finishing/heavy_rigging/', verbose_name=_('صورة ارتكاز الونش وموقع الرفع'))
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مدير أمن المشروع / مهندس السلامة'))
    issued_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت صدور التصريح'))

    class Meta:
        verbose_name = _('تصريح رفع بأوناش هيدروليكية ثقيلة')
        verbose_name_plural = _('تصاريح رفع بأوناش هيدروليكية ثقيلة')


class ScreedCuringInspectionLog(models.Model):
    """سجل فحص معالجة لياسة الأرضيات وفترة التصلب الإنشائي (7 أيام)"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='screed_curing_logs', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعماري'))
    screed_pouring_date = models.DateField(verbose_name=_('تاريخ صب اللياسة / مونة التسوية'))
    water_curing_days_completed = models.PositiveIntegerField(default=0, verbose_name=_('أيام المعالجة بالرش المائي المكتملة'))
    moisture_percentage = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('5.0'), verbose_name=_('نسبة الرطوبة المقاسة بالسطح %'))
    is_curing_approved_for_tiling = models.BooleanField(default=False, verbose_name=_('اعتماد اكتمال فترة التصلب والتصريح ببدء التبليط'))
    inspection_photo = models.ImageField(upload_to='finishing/screed_curing/', verbose_name=_('صورة توثيق رش ومعالجة اللياسة'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الجودة بالموقع'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ الفحص'))

    class Meta:
        verbose_name = _('سجل معالجة لياسة الأرضيات')
        verbose_name_plural = _('سجلات معالجة لياسة الأرضيات')


class ApplianceEnergyEfficiencyRecord(models.Model):
    """سجل بطاقة كفاءة الطاقة ومطابقة الأجهزة للمواصفات القياسية المصرية EOS"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='energy_efficiency_records', verbose_name=_('أمر التشطيب'))
    appliance_category = models.CharField(
        max_length=50,
        choices=[
            ('HVAC', _('وحدة تكييف هواء')),
            ('WATER_HEATER', _('سخان مياه')),
            ('PUMP', _('مضخة مياه')),
            ('KITCHEN', _('أجهزة مطبخ بلت إن')),
        ],
        default='HVAC',
        verbose_name=_('تصنيف الجهاز')
    )
    brand_and_model = models.CharField(max_length=150, verbose_name=_('الماركة والموديل'))
    serial_number = models.CharField(max_length=100, unique=True, verbose_name=_('الرقم المسلسل للجهاز (Serial Number)'))
    eos_energy_rating = models.CharField(
        max_length=10,
        choices=[
            ('CLASS_A', _('فئة A (الأعلى كفاءة)')),
            ('CLASS_B', _('فئة B')),
            ('CLASS_C', _('فئة C (غير مطابقة)')),
        ],
        default='CLASS_A',
        verbose_name=_('فئة بطاقة كفاءة الطاقة EOS')
    )
    energy_label_photo = models.ImageField(upload_to='finishing/energy_labels/', verbose_name=_('صورة بطاقة كفاءة الطاقة الملصقة على الجهاز'))
    is_compliant = models.BooleanField(default=True, verbose_name=_('مطابق لاشتراطات كود المباني الخضراء'))
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الكهروميكانيك الفاحص'))
    verified_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ التحقق'))

    class Meta:
        verbose_name = _('سجل كفاءة الطاقة لجهاز كهربائي')
        verbose_name_plural = _('سجلات كفاءة الطاقة للأجهزة الكهربائية')


class HomeownerAsBuiltDossierRecord(models.Model):
    """سجل ملف وتشغيل وصيانة الشقة الرقمي للعميل (Homeowner Dossier)"""
    order = models.OneToOneField(UnitFinishingOrder, on_delete=models.CASCADE, related_name='as_built_dossier', verbose_name=_('أمر التشطيب'))
    dossier_pdf = models.FileField(upload_to='finishing/homeowner_dossiers/', verbose_name=_('ملف الكتالوج الرقمي للوحدة (PDF)'))
    as_built_pipes_photo_count = models.PositiveIntegerField(default=0, verbose_name=_('عدد صور مسارات المواسير والكهرباء الدفينة الموثقة'))
    jotun_color_codes_json = models.JSONField(default=dict, verbose_name=_('أكواد درجات دهانات جوتن المستخدمة بكل فراغ'))
    warranty_certificates_json = models.JSONField(default=list, verbose_name=_('قائمة روابط شهادات الضمان المعتمدة للأجهزة'))
    dossier_generated_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ توليد الكتالوج'))
    is_delivered_to_client_portal = models.BooleanField(default=False, verbose_name=_('تم النشر على بوابة وتطبيق العميل'))

    class Meta:
        verbose_name = _('كتالوج تشغيل وصيانة الشقة الرقمي')
        verbose_name_plural = _('كتالوجات تشغيل وصيانة الشقق الرقمية')


class SubcontractorPenaltySettlementRecord(models.Model):
    """سجل مقاصة وتسوية غرامات التشطيب من المستخلصات الختامية لمقاولي الباطن"""
    contractor = models.ForeignKey('real_estate.ContractorContract', on_delete=models.CASCADE, verbose_name=_('عقد مقاول الباطن'))
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, verbose_name=_('أمر التشطيب المعني'))
    gross_final_certificate_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('إجمالي المستخلص الختامي قبل الخصم'))
    delay_penalties_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('غرامات التأخير المحسومة'))
    safety_violations_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('غرامات مخالفات السلامة والصحة المهنية'))
    debris_and_damages_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name=_('غرامات المخلفات وتلفيات الموقع'))
    total_penalties_netted = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('إجمالي الغرامات المحسومة بالمقاصة'))
    net_payable_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('صافي المبلغ المستحق للصرف'))
    settlement_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('المدير المالي المعتمد'))
    settled_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت التسوية'))

    class Meta:
        verbose_name = _('تسوية ومقاصة غرامات مقاول باطن تشطيبات')
        verbose_name_plural = _('تسويات ومقاصة غرامات مقاولي باطن التشطيبات')


class HVACNitrogenHoldingInspection(models.Model):
    """محضر فحص كبس النيتروجين والفاكيوم لشبكات نحاس التكييف قبل إغلاق الأسقف"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='hvac_nitrogen_inspections', verbose_name=_('أمر التشطيب'))
    system_type = models.CharField(max_length=50, choices=[('CONCEALED', _('كونسيلد سبليت')), ('VRF', _('نظام في آر إف VRF'))], default='CONCEALED', verbose_name=_('نوع نظام التكييف'))
    initial_pressure_psi = models.PositiveIntegerField(default=350, verbose_name=_('ضغط النيتروجين المبدئي (PSI)'))
    final_pressure_psi = models.PositiveIntegerField(default=350, verbose_name=_('ضغط النيتروجين بعد 24 ساعة (PSI)'))
    test_duration_hours = models.PositiveIntegerField(default=24, verbose_name=_('مدة اختبار الكبس (ساعة)'))
    vacuum_micron_reading = models.PositiveIntegerField(default=450, verbose_name=_('قراءة اختبار الفاكيوم (ميكرون < 500)'))
    is_pressure_holding_passed = models.BooleanField(default=False, verbose_name=_('ثبات الضغط واجتياز اختبار الفاكيوم'))
    manometer_gauge_photo = models.ImageField(upload_to='finishing/nitrogen_tests/', verbose_name=_('صورة المانوميتر بعد 24 ساعة'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الكهروميكانيك الفاحص'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ الفحص'))

    class Meta:
        verbose_name = _('محضر كبس نيتروجين شبكة التكييف')
        verbose_name_plural = _('محاضر كبس نيتروجين شبكات التكييف')


class ElectricalEarthingResistanceInspection(models.Model):
    """محضر قياس مقاومة بئر التأريض واستمرارية خط الأرضي للأنظمة الذكية"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='earthing_resistance_inspections', verbose_name=_('أمر التشطيب'))
    measured_earth_resistance_ohms = models.DecimalField(max_digits=5, decimal_places=2, verbose_name=_('مقاومة التأريض المقاسة بالميجر (أوم)'))
    max_allowable_resistance_ohms = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('5.00'), verbose_name=_('الحد الأقصى المسموح به (أوم)'))
    ground_continuity_sockets_verified = models.BooleanField(default=True, verbose_name=_('التحقق من استمرارية سلك الإيرث لكافة البرايز والتكييف'))
    megger_test_photo = models.ImageField(upload_to='finishing/earthing_tests/', verbose_name=_('صورة قراءة جهاز الميجر لبئر التأريض'))
    is_earthing_approved = models.BooleanField(default=False, verbose_name=_('اعتماد سلامة منظومة التأريض والتصريح بالتيار'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الكهرباء الفاحص'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ القياس والاعتماد'))

    class Meta:
        verbose_name = _('محضر قياس مقاومة بئر التأريض')
        verbose_name_plural = _('محاضر قياس مقاومة آبار التأريض')


class TouchUpPaintEscrowRecord(models.Model):
    """سجل استلام وحفظ عبوات دهان الرتوش (1 لتر) بأكواد جوتن للعميل"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='touchup_paint_records', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعماري'))
    paint_brand = models.CharField(max_length=50, default='Jotun', verbose_name=_('ماركة الدهان'))
    color_code = models.CharField(max_length=50, verbose_name=_('كود درجة اللون والصبغة'))
    can_volume_liters = models.DecimalField(max_digits=3, decimal_places=1, default=Decimal('1.0'), verbose_name=_('سعة العبوة (لتر)'))
    is_sealed_and_labeled = models.BooleanField(default=True, verbose_name=_('العبوة محكمة الغلق وعليها استيكر الكود وتاريخ الخلط'))
    handed_over_to_site_escrow = models.BooleanField(default=False, verbose_name=_('تم الاستلام في عهدة الموقع لتسليمها للمالك'))
    can_photo = models.ImageField(upload_to='finishing/touchup_paint/', verbose_name=_('صورة عبوة الدهان بالاستيكر'))
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الجودة المستلم'))
    received_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ الاستلام'))

    class Meta:
        verbose_name = _('سجل عبوة دهان رتوش للعميل')
        verbose_name_plural = _('سجلات عبوات دهان الرتوش للعملاء')


class ExhaustBackdraftDamperInspection(models.Model):
    """محضر فحص واختبار ردادات عدم الرجوع لمداخن الشفاطات بالمطابخ والحمامات"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='backdraft_damper_inspections', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ (مطبخ / حمام)'))
    damper_type = models.CharField(max_length=50, default='Gravity / Spring Flap', verbose_name=_('نوع رداد عدم الرجوع'))
    damper_direction_verified = models.BooleanField(default=True, verbose_name=_('التحقق من صحة اتجاه فتح الشفرات لطرد الهواء فقط'))
    free_blade_movement_tested = models.BooleanField(default=True, verbose_name=_('اختبار الحركة الحرة للشفرات بضغط الهواء'))
    inspection_photo = models.ImageField(upload_to='finishing/backdraft_dampers/', verbose_name=_('صورة فحص الرداد في الدكت'))
    ceiling_closure_permitted = models.BooleanField(default=False, verbose_name=_('التصريح بإغلاق السقف المعلق للفراغ'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الميكانيكا الفاحص'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ الفحص'))

    class Meta:
        verbose_name = _('محضر فحص رداد مدخنة شفاط')
        verbose_name_plural = _('محاضر فحص ردادات مداخن الشفاطات')


class PotableWaterChlorinationInspection(models.Model):
    """محضر تعقيم وتطهير شبكة مياه الشرب بالكلور والغسيل المائي قبل التسليم"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='water_chlorination_inspections', verbose_name=_('أمر التشطيب'))
    chlorine_concentration_ppm = models.PositiveIntegerField(default=50, verbose_name=_('تركيز محلول الكلور (PPM)'))
    holding_time_hours = models.PositiveIntegerField(default=24, verbose_name=_('مدة بقاء المحلول داخل الشبكة (ساعة)'))
    flushing_completed = models.BooleanField(default=True, verbose_name=_('اكتمال الغسيل المائي بالكامل وزوال أثر الكلور'))
    water_sample_clarity_passed = models.BooleanField(default=True, verbose_name=_('صفاء عينة المياه وخلوها من الشوائب والروائح'))
    sanitary_clearance_issued = models.BooleanField(default=False, verbose_name=_('إصدار شهادة الصلاحية الصحية للسكن'))
    test_photo = models.ImageField(upload_to='finishing/water_chlorination/', verbose_name=_('صورة اختبار عينة المياه والتعقيم'))
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الصحي / السلامة'))
    inspected_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ وتوقيت التطهير'))

    class Meta:
        verbose_name = _('محضر تطهير وتعقيم شبكة مياه الشرب')
        verbose_name_plural = _('محاضر تطهير وتعقيم شبكات مياه الشرب')


class FlooringSlipResistanceRatingRecord(models.Model):
    """سجل مطابقة معامل مقاومة الانزلاق لبلاط المناطق المبتلة والشرفات (R10/R11)"""
    order = models.ForeignKey(UnitFinishingOrder, on_delete=models.CASCADE, related_name='slip_resistance_records', verbose_name=_('أمر التشطيب'))
    workspace = models.ForeignKey(FinishingWorkspace, on_delete=models.PROTECT, verbose_name=_('الفراغ المعماري'))
    flooring_spec = models.ForeignKey(FinishingItemSpec, on_delete=models.PROTECT, verbose_name=_('مواصفة بلاط الأرضية'))
    slip_resistance_rating = models.CharField(
        max_length=10,
        choices=[
            ('R9', _('R9 (أملس - غرف جافة فقط)')),
            ('R10', _('R10 (مقاوم للانزلاق - حمامات ومطابخ)')),
            ('R11', _('R11 (مقاوم عالي للانزلاق - شرفات وجاكوزي)')),
            ('R12_R13', _('R12/R13 (صناعي فائق المقاومة)')),
        ],
        default='R10',
        verbose_name=_('تصنيف مقاومة الانزلاق DIN 51130')
    )
    is_wet_area_compliant = models.BooleanField(default=True, verbose_name=_('مطابق لاشتراطات الأمان بالفراغ المبتل'))
    anti_slip_treatment_applied = models.BooleanField(default=False, verbose_name=_('تم تطبيق معالجة نانو مانعة للانزلاق (في حال البورسلين الأملس)'))
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name=_('مهندس الجودة والمطابقة'))
    verified_at = models.DateTimeField(default=timezone.now, verbose_name=_('تاريخ التحقق'))

    class Meta:
        verbose_name = _('سجل مقاومة انزلاق بلاط الأرضيات')
        verbose_name_plural = _('سجلات مقاومة انزلاق بلاط الأرضيات')
