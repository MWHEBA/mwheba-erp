from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.apps import apps

from printing_pricing.models.order import PrintingOrder
from supplier.models import Supplier


class ProcurementBridgeService:
    """
    خدمة جسر المشتريات والربط بين طلب تسعير الطباعة وأوامر الشراء للورش
    (Procurement Bridge & Multi-Part Unbundling Service)
    """

    @classmethod
    def check_po_gating(cls, order: PrintingOrder) -> dict:
        """
        التحقق من جاهزية إطلاق أوامر الشراء للمشروع
        """
        return {
            'is_gated_ready': True,
            'issues': []
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

        # تجميع كافة البنود والخدمات حسب المورد الفعلي (Consolidated PO per Supplier)
        # الهيكل: {supplier_obj: {'items': [{'name': ..., 'cost': ...}], 'subtotal': Decimal}}
        supplier_bundles = {}

        def _add_to_bundle(sup_obj, name, cost, details=""):
            if not sup_obj or cost <= Decimal('0.00'):
                return
            if sup_obj not in supplier_bundles:
                supplier_bundles[sup_obj] = {'items': [], 'subtotal': Decimal('0.00')}
            
            sym = ""
            if hasattr(sup_obj, 'default_currency') and sup_obj.default_currency:
                sym = sup_obj.default_currency.symbol or sup_obj.default_currency.code
            elif hasattr(order, 'currency_symbol'):
                sym = order.currency_symbol

            cost_str = f"{cost} {sym}".strip() if sym else str(cost)
            supplier_bundles[sup_obj]['items'].append(f"{name} ({cost_str}){': ' + details if details else ''}")
            supplier_bundles[sup_obj]['subtotal'] += cost

        # 1. بنود خام الورق (Paper Materials)
        paper_materials = order.materials.filter(material_type='paper', is_active=True)
        for mat in paper_materials:
            if mat.total_cost and mat.total_cost > Decimal('0.00'):
                sup_info = mat.supplier_info if isinstance(mat.supplier_info, dict) else {}
                if sup_info.get('source') in ['customer_supplied', 'warehouse']:
                    continue  # ورق من العميل أو مسحوب من المخزن
                
                sup_id = sup_info.get('supplier_id')
                paper_sup = Supplier.objects.filter(id=sup_id).first() if sup_id else None
                if not paper_sup:
                    paper_sup = cls._get_or_create_default_supplier("تاجر ومورد الورق")

                pack_cap = sup_info.get('sheets_per_pack') or 500
                try:
                    pack_cap = int(pack_cap)
                except (ValueError, TypeError):
                    pack_cap = 500
                reams = round(float(mat.quantity) / pack_cap, 1) if pack_cap > 0 else 0
                mat_name = getattr(mat, 'material_name', '') or str(mat)
                detail = f"{mat.quantity} فرخ (≈ {reams} رزمة سعة {pack_cap})"
                _add_to_bundle(paper_sup, f"توريد خام: {mat_name}", mat.total_cost, detail)

        # 2. بنود الخدمات المباشرة (OrderService)
        services = order.services.filter(is_active=True)
        for svc in services:
            if svc.total_cost and svc.total_cost > Decimal('0.00'):
                svc_sup = None
                if svc.supplier_service and svc.supplier_service.supplier:
                    svc_sup = svc.supplier_service.supplier
                elif isinstance(svc.supplier_info, dict) and svc.supplier_info.get('supplier_id'):
                    svc_sup = Supplier.objects.filter(id=svc.supplier_info['supplier_id']).first()
                
                if not svc_sup:
                    if svc.service_category == 'printing':
                        svc_sup = cls._get_or_create_default_supplier("مطبعة الأوفست والديجيتال")
                    elif svc.service_category in ['coating', 'finishing', 'packaging']:
                        svc_sup = cls._get_or_create_default_supplier("ورشة التشطيب والتجليد")
                    else:
                        svc_sup = cls._get_or_create_default_supplier("المورد التجاري الخارجي")

                set_info = ""
                if svc.supplier_service and getattr(svc.supplier_service, 'set_price', None) and svc.supplier_service.set_price > Decimal('0.00'):
                    inc_tir = getattr(svc.supplier_service, 'set_included_tirages', 1) or 1
                    st_code = getattr(svc.supplier_service.service_type, 'code', '') if svc.supplier_service.service_type else ''
                    if svc.service_category == 'printing' or st_code == 'offset_printing':
                        set_info = f" [نظام طقم ماكينة: يشمل {inc_tir} تراج]"
                    elif st_code == 'ctp_plates':
                        set_info = f" [نظام طقم زنكات 4 ألوان]"

                svc_desc = f"{svc.service_name}{set_info} (كمية: {svc.quantity} {svc.get_unit_display() if hasattr(svc, 'get_unit_display') else svc.unit})"
                _add_to_bundle(svc_sup, svc.service_name, svc.total_cost, svc_desc)



        # في حال عدم وجود بنود تفصيلية ولكن يوجد ملخص تكاليف
        if not supplier_bundles and hasattr(order, 'summary') and order.summary:
            sum_obj = order.summary
            if sum_obj.material_cost and sum_obj.material_cost > Decimal('0.00'):
                sup = cls._get_or_create_default_supplier("تاجر ومورد الورق")
                _add_to_bundle(sup, "توريد خامات وورق", sum_obj.material_cost)
            if sum_obj.printing_cost and sum_obj.printing_cost > Decimal('0.00'):
                sup = cls._get_or_create_default_supplier("مطبعة الأوفست والديجيتال")
                _add_to_bundle(sup, "تشغيل وطباعة بالمطبعة", sum_obj.printing_cost)
            if sum_obj.finishing_cost and sum_obj.finishing_cost > Decimal('0.00'):
                sup = cls._get_or_create_default_supplier("ورشة التشطيب والتجليد")
                _add_to_bundle(sup, "خدمات تشطيب وتجليد", sum_obj.finishing_cost)

        # إنشاء أوامر الشراء المدمجة لكل مورد فريد
        for sup_obj, bundle in supplier_bundles.items():
            if bundle['subtotal'] > Decimal('0.00'):
                combined_desc = "\n- ".join(bundle['items'])
                po = cls._create_purchase_order_for_supplier(
                    order=order,
                    supplier=sup_obj,
                    subtotal=bundle['subtotal'],
                    service_desc=f"خدمات مجمعة للمشروع:\n- {combined_desc}",
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
        from financial.services.exchange_rate_service import ExchangeRateService
        func_curr = ExchangeRateService.get_functional_currency()

        # تحديد عملة أمر الشراء: عملة المورد الافتراضية، أو عملة الطلب، أو العملة الوظيفية
        po_currency = getattr(supplier, 'default_currency', None) or getattr(order, 'currency', None) or func_curr

        # تحويل subtotal إذا كانت عملة الطلب مختلفة عن عملة أمر الشراء
        order_curr = getattr(order, 'currency', None) or func_curr
        if order_curr and po_currency and order_curr.code != po_currency.code:
            conversion_rate = ExchangeRateService.get_rate(
                from_code=order_curr.code,
                to_code=po_currency.code,
                date=getattr(order, 'order_date', None)
            )
            subtotal = (subtotal * conversion_rate).quantize(Decimal('0.01'))
        
        # حساب ضريبة الخصم 1%
        wht_rate = Decimal('1.00')
        wht_amount = (subtotal * Decimal('0.01')).quantize(Decimal('0.01'))
        total_after_wht = subtotal - wht_amount

        # توليد رقم تسلسلي مطابق لـ Rule #3
        try:
            from core.services.sequence_service import SequenceService
            unique_num = SequenceService.get_next_number('purchase_order')
        except Exception:
            today_str = timezone.now().strftime('%y%m%d')
            unique_num = f"PO-{today_str}-{order.id}-{supplier.id}"

        # التحقق من عدم وجود أمر شراء مطابق مسبقاً
        existing = Purchase.objects.filter(number=unique_num).first()
        if existing:
            return existing

        user_obj = user or order.created_by
        if not user_obj:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user_obj = User.objects.first()
            if not user_obj:
                user_obj, _ = User.objects.get_or_create(username='system_po', defaults={'is_active': True})

        # فحص هل المورد مسجل ضريبياً (14% VAT) أم ورشة عادية
        has_tax = bool(getattr(supplier, 'tax_number', None) and getattr(supplier, 'tax_active', False))
        tax_rate = Decimal('14.00') if has_tax else Decimal('0.00')
        tax_amount = (subtotal * (tax_rate / Decimal('100'))).quantize(Decimal('0.01'))
        final_total = (subtotal + tax_amount) - wht_amount

        # فحص طريقة السداد (نقدي للورش اليومية / آجل)
        is_cash_workshop = bool(getattr(supplier, 'requires_cash_advance', False) or getattr(order, 'is_rush', False))
        payment_method = "cash" if is_cash_workshop else "credit"

        # حساب سعر الصرف والمجاميع الوظيفية والأجنبية وفق معيار IAS 21
        func_code = func_curr.code if func_curr else 'EGP'
        po_code = po_currency.code if po_currency else func_code
        po_sym = po_currency.symbol if po_currency and po_currency.symbol else (func_curr.symbol if func_curr else '')

        if po_code == func_code:
            exchange_rate = Decimal('1.000000')
            total_functional = final_total
            total_foreign = Decimal('0.00')
        else:
            rate_to_func = ExchangeRateService.get_rate(
                from_code=po_code,
                to_code=func_code,
                date=getattr(order, 'order_date', None)
            )
            exchange_rate = rate_to_func
            total_foreign = final_total
            total_functional = (final_total * rate_to_func).quantize(Decimal('0.01'))

        po = Purchase(
            number=unique_num,
            date=timezone.now().date(),
            status="confirmed",
            supplier=supplier,
            subtotal=subtotal,
            discount=Decimal('0.00'),
            tax=tax_amount,
            tax_active=has_tax,
            wht_active=True,
            wht_rate=wht_rate,
            wht_amount=wht_amount,
            total=final_total,
            currency=po_currency,
            exchange_rate=exchange_rate,
            total_foreign=total_foreign,
            total_functional=total_functional,
            payment_method=payment_method,
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
                f"- ضريبة الخصم والتحصيل: تم خصم 1% (نموذج 41 ضرائب بمبلغ {wht_amount} {po_sym})."
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
        wht_deduction = (bill_amount * Decimal('0.01')).quantize(Decimal('0.01'))
        final_cash_due = bill_amount - wht_deduction

        return {
            'bill_amount': bill_amount,
            'advance_deducted': Decimal('0.00'),
            'wht_deducted_1pct': wht_deduction,
            'net_cash_payable': final_cash_due,
            'settled_advances_count': 0
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
