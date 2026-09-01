from decimal import Decimal
from django.utils.translation import gettext_lazy as _
from printing_pricing.models.order import PrintingOrder


class CustomerPDFSanitizerService:
    """
    خدمة تطهير وعزل الأسرار التجارية والتكاليف الداخلية عن عروض الأسعار وملفات الـ PDF والواتساب
    (Trade Secret & Pricing Data Sanitizer Service)
    """

    @classmethod
    def sanitize_order_context(cls, order: PrintingOrder) -> dict:
        """
        توليد سياق نظيف تماماً وخالي 100% من أسماء الورش، تكاليف الخدمات الأولية،
        وهوامش الأرباح، لإرساله بأمان للعميل.
        """
        summary = getattr(order, 'summary', None)
        subtotal = getattr(summary, 'subtotal', Decimal('0.00')) if summary else Decimal('0.00')
        tax_amount = getattr(summary, 'tax_amount', Decimal('0.00')) if summary else Decimal('0.00')
        discount_amount = getattr(summary, 'discount_amount', Decimal('0.00')) if summary else Decimal('0.00')
        final_price = (subtotal + tax_amount - discount_amount).quantize(Decimal('0.01'))
        
        if hasattr(summary, 'unit_price'):
            unit_price = summary.unit_price
        elif order.quantity and order.quantity > 0:
            unit_price = (subtotal / Decimal(str(order.quantity))).quantize(Decimal('0.01'))
        else:
            unit_price = Decimal('0.00')

        # تجهيز بنود مجمعة نظيفة للعميل
        items = []
        if (order.order_type in ['catalog', 'book', 'book_catalog', 'BOOKS'] or (order.pages_count and order.pages_count > 1)):
            item_desc = f"{order.title} ({order.pages_count} صفحة)"
        else:
            item_desc = f"{order.title}"

        items.append({
            'index': 1,
            'description': item_desc,
            'quantity': order.quantity,
            'unit_price': unit_price,
            'total_price': subtotal,
        })

        # البنود الإضافية مثل الهدايا
        giveaway_mgr = getattr(order, 'giveaway_items', None)
        if giveaway_mgr and hasattr(giveaway_mgr, 'all'):
            giveaway_items = giveaway_mgr.all()
            for idx, g_item in enumerate(giveaway_items, start=2):
                items.append({
                    'index': idx,
                    'description': f"{getattr(g_item, 'item_name', 'صنف إضافي')} (شامل الطباعة والتخصيص)",
                    'quantity': getattr(g_item, 'quantity', 1),
                    'unit_price': getattr(g_item, 'unit_client_price', Decimal('0.00')),
                    'total_price': getattr(g_item, 'total_client_price', Decimal('0.00')),
                })

        # الشروط والأحكام القانونية المعتمدة
        terms = [
            "يسري هذا العرض لمدة 5 أيام عمل من تاريخ إصداره.",
            "الأسعار خاضعة لضريبة القيمة المضافة 14% وفقاً لأحكام القانون المصري.",
            "الدفعة المقدمة 50% لازمة لبدء تجهيز الخامات وإطلاق أوامر التشغيل.",
            "إقرار الألوان: تقر الوكالة بتفاوت طبيعي بنسبة 5-8% بين ألوان شاشات العرض (RGB) وألوان أحبار الطباعة (CMYK).",
            "سياسة أرشفة الملفات: تلتزم الوكالة بحفظ ملفات التصميم الأصلية لمدة 6 أشهر من تاريخ التسليم.",
            "نسبة التسامح في التسليم: تخضع الكميات الموردة لنسبة تسامح مقبولة صناعياً (±5%) وتسوى قيمتها بالفاتورة النهائية.",
        ]

        return {
            'order_number': order.order_number,
            'title': order.title,
            'customer_name': order.customer.name,
            'customer_phone': getattr(order.customer, 'phone', ''),
            'customer_tax_number': getattr(order.customer, 'tax_number', ''),
            'currency_code': order.currency.code if order.currency else 'EGP',
            'order_date': order.created_at.date(),
            'items': items,
            'subtotal': subtotal,
            'discount_amount': discount_amount,
            'tax_amount': tax_amount,
            'final_total': final_price,
            'terms_and_conditions': terms,
        }

    @classmethod
    def generate_whatsapp_quote_message(cls, order: PrintingOrder) -> str:
        """
        توليد رسالة واتساب أنيقة وموجزة ومطهرة تماماً من أي تسريب للتكاليف الداخلية
        """
        context = cls.sanitize_order_context(order)
        curr = context['currency_code']

        msg = (
            f"مرحباً بك أ/ {context['customer_name']}\n\n"
            f"يسعدنا تقديم عرض السعر المعتمد لمشروعكم: *{context['title']}*\n"
            f"رقم العرض: *{context['order_number']}*\n"
            f"الكمية: *{order.quantity:,} قطعة*\n"
            f"سعر الوحدة: *{context['items'][0]['unit_price']:,.2f} {curr}*\n"
            f"الإجمالي: *{context['final_total']:,.2f} {curr}*\n\n"
            f"📌 الشروط:\n"
            f"- الدفعة المقدمة: 50% لبدء التشغيل.\n"
            f"- العرض ساري لمدة 5 أيام.\n\n"
            f"شكراً لثقتكم بنا، ونتطلع لبدء العمل معاً! ✨"
        )
        return msg

    @classmethod
    def generate_whatsapp_quote_text(cls, order: PrintingOrder) -> str:
        """Alias for generate_whatsapp_quote_message"""
        return cls.generate_whatsapp_quote_message(order)

