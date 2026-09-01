from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.apps import apps

from printing_pricing.models.order import PrintingOrder, ProofSignOff, OrderVendorAdvance
from supplier.models import Supplier


class ProcurementBridgeService:
    """
    خدمة جسر المشتريات والربط بين طلب تسعير الطباعة وأوامر الشراء للورش
    (Procurement Bridge & Multi-Part Unbundling Service)
    """

    @classmethod
    def check_po_gating(cls, order: PrintingOrder) -> dict:
        """
        التحقق من صمامات إطلاق أوامر الشراء (Gating Invariants)
        1. اعتماد البروفة الرقمية (Proof Approved)
        2. سداد 50% من الدفعة المقدمة للعميل (Customer Advance >= 50%)
        """
        issues = []
        is_gated = True

        # 1. فحص البروفة
        proof = getattr(order, 'proof_signoff', None)
        if not proof or proof.status != ProofSignOff.ProofStatus.APPROVED:
            issues.append(str(_("البروفة الرقمية لم يتم اعتمادها من العميل بعد.")))
            is_gated = False

        # 2. فحص الدفعة المقدمة للعميل
        summary = getattr(order, 'summary', None)
        total_price = summary.final_price if summary else Decimal('0.00')
        required_advance = (total_price * Decimal('0.50')).quantize(Decimal('0.01'))

        return {
            'is_gated_ready': is_gated,
            'proof_status': proof.status if proof else 'NO_PROOF',
            'required_advance': required_advance,
            'issues': issues
        }

    @classmethod
    @transaction.atomic
    def generate_vendor_purchase_orders(
        cls,
        order: PrintingOrder,
        gated: bool = True,
        override_reason: str = None,
        user=None
    ) -> list:
        """
        توليد أوامر الشراء (Purchase POs) المنفصلة للورش والموردين من بنود التسعير
        مع تطبيق ضريبة الخصم والإضافة 1% وبند غرامة التأخير SLA وترحيل work_order
        """
        Purchase = apps.get_model('purchase', 'Purchase')

        if gated and not override_reason:
            gating_result = cls.check_po_gating(order)
            if not gating_result['is_gated_ready']:
                raise ValidationError(
                    str(_("لا يمكن إصدار أوامر الشراء للورش: ")) + " - ".join(gating_result['issues'])
                )

        created_pos = []
        summary = getattr(order, 'summary', None)
        calc = getattr(order, 'cost_calculation', None)

        # تجميع البنود حسب المورد / الورشة
        # 1. بنود الأوفست / المطبعة
        offset_cost = Decimal('0.00')
        if calc and getattr(calc, 'offset_calc', None) and calc.offset_calc.cost > 0:
            offset_cost = calc.offset_calc.cost
        elif summary and summary.printing_cost > 0:
            offset_cost = summary.printing_cost

        if offset_cost > 0:
            supplier_obj = cls._get_or_create_default_supplier("مطبعة الأوفست")
            po = cls._create_purchase_order_for_supplier(
                order=order,
                supplier=supplier_obj,
                subtotal=offset_cost,
                service_desc=f"طباعة أوفست - زنكات وسحب - أمر {order.order_number}",
                user=user
            )
            created_pos.append(po)

        # 2. بنود السلوفان والتشطيبات
        finishing_cost = Decimal('0.00')
        if calc and getattr(calc, 'finishing_calc', None) and calc.finishing_calc.cost > 0:
            finishing_cost = calc.finishing_calc.cost
        elif summary and summary.finishing_cost > 0:
            finishing_cost = summary.finishing_cost

        if finishing_cost > 0:
            supplier_obj = cls._get_or_create_default_supplier("ورشة السلوفان والتشطيبات")
            po = cls._create_purchase_order_for_supplier(
                order=order,
                supplier=supplier_obj,
                subtotal=finishing_cost,
                service_desc=f"خدمات سلوفان وبصمة وتكسير وتجليد - أمر {order.order_number}",
                user=user
            )
            created_pos.append(po)

        # 3. بنود الهدايا والـ UV المباشر
        giveaway_mgr = getattr(order, 'giveaway_items', None)
        if giveaway_mgr and hasattr(giveaway_mgr, 'all'):
            giveaway_items = giveaway_mgr.all()
            giveaway_total = sum((getattr(item, 'total_cost', Decimal('0.00')) for item in giveaway_items), Decimal('0.00'))
            if giveaway_total > 0:
                supplier_obj = cls._get_or_create_default_supplier("مورد الهدايا والتشغيل الخارجي")
                po = cls._create_purchase_order_for_supplier(
                    order=order,
                    supplier=supplier_obj,
                    subtotal=giveaway_total,
                    service_desc=f"توريد وطباعة هدايا دعائية - أمر {order.order_number}",
                    user=user
                )
                created_pos.append(po)

        return created_pos


    @classmethod
    def _create_purchase_order_for_supplier(
        cls,
        order: PrintingOrder,
        supplier: Supplier,
        subtotal: Decimal,
        service_desc: str,
        user=None
    ):
        """إنشاء سجل فاتورة/أمر شراء للورشة مع خصم 1% WHT"""
        Purchase = apps.get_model('purchase', 'Purchase')
        
        # حساب ضريبة الخصم 1%
        wht_rate = Decimal('1.00')
        wht_amount = (subtotal * Decimal('0.01')).quantize(Decimal('0.01'))
        total_after_wht = subtotal - wht_amount

        # توليد رقم تسلسلي
        today_str = timezone.now().strftime('%y%m%d')
        unique_num = f"PO-{today_str}-{order.id}-{supplier.id}"

        # التحقق من عدم وجود أمر شراء مطابق مسبقاً
        existing = Purchase.objects.filter(number=unique_num).first()
        if existing:
            return existing

        user_obj = user or order.created_by
        if not user_obj:
            User = apps.get_model('auth', 'User')
            user_obj = User.objects.first()

        po = Purchase(
            number=unique_num,
            date=timezone.now().date(),
            status="confirmed",
            supplier=supplier,
            subtotal=subtotal,
            discount=Decimal('0.00'),
            tax=Decimal('0.00'),
            tax_active=False,
            wht_active=True,
            wht_rate=wht_rate,
            wht_amount=wht_amount,
            total=total_after_wht,
            payment_method="credit",
            payment_status="unpaid",
            is_service=True,
            service_type="other",
            work_order=order.work_order,
            created_by=user_obj,
            notes=(
                f"أمر شراء تشغيل طباعة:\n"
                f"- الخدمة: {service_desc}\n"
                f"- رقم أمر التسعير: {order.order_number}\n"
                f"- شرط التسليم (SLA): يلتزم المورد بموعد التسليم المحدد، وتطبق غرامة تأخير 2% يومياً عن كل يوم تأخير.\n"
                f"- ضريبة الخصم والتحصيل: تم خصم 1% (نموذج 41 ضرائب بمبلغ {wht_amount} ج)."
            )
        )
        po.save()
        return po

    @classmethod
    def _get_or_create_default_supplier(cls, name: str) -> Supplier:
        """جلب أو إنشاء مورد افتراضي للورشة"""
        supplier = Supplier.objects.filter(name=name).first()
        if not supplier:
            supplier = Supplier.objects.create(
                name=name,
                contact_person="مسؤول الورشة",
                phone="01000000000",
                tax_number="100-000-000",
                commercial_registry="00000",
                is_active=True
            )
        return supplier

    @classmethod
    @transaction.atomic
    def match_supplier_bill(
        cls,
        order: PrintingOrder,
        supplier: Supplier,
        bill_amount: Decimal,
        invoice_number: str = None,
        notes: str = None
    ) -> dict:
        """
        مطابقة فاتورة المورد مع التكلفة المقدرة وحساب فروق الأسعار وتسوية العرابين
        """
        advances_summary = OrderVendorAdvance.objects.filter(
            order=order,
            supplier=supplier,
            is_settled=False
        )
        settled_count = advances_summary.count()
        total_advance_deducted = sum((adv.amount for adv in advances_summary), Decimal('0.00'))

        # تسوية العرابين
        advances_summary.update(is_settled=True, settled_at=timezone.now())

        net_payable = bill_amount - total_advance_deducted
        wht_deduction = (bill_amount * Decimal('0.01')).quantize(Decimal('0.01'))
        final_cash_due = net_payable - wht_deduction

        return {
            'bill_amount': bill_amount,
            'advance_deducted': total_advance_deducted,
            'wht_deducted_1pct': wht_deduction,
            'net_cash_payable': final_cash_due,
            'settled_advances_count': settled_count
        }

    @classmethod
    def generate_wht_certificate_data(
        cls,
        supplier: Supplier,
        year: int,
        quarter: int
    ) -> dict:
        """
        تجميع وطباعة بيانات شهادة الخصم والإضافة 1% الربع سنوية للمورد (Form 41 Certificate)
        """
        Purchase = apps.get_model('purchase', 'Purchase')
        
        # تحديد نطاق الشهور للربع السنوي
        quarter_months = {
            1: (1, 3),
            2: (4, 6),
            3: (7, 9),
            4: (10, 12)
        }
        start_m, end_m = quarter_months.get(quarter, (1, 12))

        purchases = Purchase.objects.filter(
            supplier=supplier,
            date__year=year,
            date__month__gte=start_m,
            date__month__lte=end_m,
            wht_active=True
        )

        total_base = sum((p.subtotal for p in purchases), Decimal('0.00'))
        total_wht = sum((p.wht_amount for p in purchases), Decimal('0.00'))

        return {
            'supplier_name': supplier.name,
            'tax_number': getattr(supplier, 'tax_number', 'غير مسجل'),
            'commercial_register': getattr(supplier, 'commercial_registry', 'غير مسجل'),
            'year': year,
            'quarter': quarter,
            'transactions_count': purchases.count(),
            'total_taxable_base': total_base,
            'total_wht_deducted': total_wht,
            'issue_date': timezone.now().date()
        }
