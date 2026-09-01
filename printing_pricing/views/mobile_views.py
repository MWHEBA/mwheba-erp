from decimal import Decimal
import urllib.parse
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _

from customer.models import Customer
from django.urls import reverse
from django.db import transaction
from ..models.base import OrderType, ProductionStage
from ..models.order import PrintingOrder
from ..models.calculations import OrderSummary
from ..services.pdf_sanitizer_service import CustomerPDFSanitizerService



class MobilePricingView(LoginRequiredMixin, TemplateView):
    """
    واجهة التسعير السريع الميداني للموبايل مع مشاركة فورية على الواتساب
    """
    template_name = "printing_pricing/orders/mobile_pricing_mode.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['customers'] = Customer.objects.filter(is_active=True).order_by('name')[:100]
        context['page_title'] = _('التسعير الميداني السريع (موبايل)')
        context['page_subtitle'] = _('حاسبة تسعير فورية ومشاركة عروض الأسعار على الواتساب')
        context['page_icon'] = 'fas fa-mobile-alt'
        context['breadcrumb_items'] = [
            {'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fas fa-home'},
            {'title': _('تسعير المطبوعات'), 'url': reverse('printing_pricing:order_list'), 'icon': 'fas fa-print'},
            {'title': _('التسعير الميداني (موبايل)'), 'active': True},
        ]
        context['header_buttons'] = [
            {
                'url': reverse('printing_pricing:order_list'),
                'icon': 'fa-arrow-right',
                'text': _('قائمة المقايسات'),
                'class': 'btn-secondary',
            },
        ]
        return context


def generate_mobile_whatsapp_link(request, order_id):
    """
    توليد رابط الواتساب المشفر لعرض السعر النظيف
    """
    order = get_object_or_404(PrintingOrder, pk=order_id)
    text = CustomerPDFSanitizerService.generate_whatsapp_quote_text(order)
    
    # رقم هاتف العميل
    phone = order.customer.phone or order.customer.mobile if hasattr(order.customer, 'mobile') else ''
    clean_phone = ''.join(c for c in str(phone) if c.isdigit())
    if clean_phone.startswith('01'):
        clean_phone = '2' + clean_phone  # إضافة كود مصر الدولي

    encoded_text = urllib.parse.quote(text)
    whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_text}"

    return JsonResponse({
        'success': True,
        'order_number': order.order_number,
        'customer_name': order.customer.name,
        'whatsapp_url': whatsapp_url,
        'quote_text': text
    })


@transaction.atomic
def save_quick_mobile_quote(request):
    """
    حفظ المقايسة السريعة كطلب تسعير رسمي في النظام من الموبايل
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': _('طريقة غير مسموحة')}, status=405)

    import json
    try:
        data = json.loads(request.body.decode('utf-8'))
        customer_id = data.get('customer_id')
        product_type = data.get('product_type', 'flyer')
        quantity = int(data.get('quantity', 1000))
        price = Decimal(str(data.get('price', '0.00')))
        title = data.get('title') or f"مقايسة سريعة ({product_type}) - {quantity} قطعة"

        if not customer_id:
            return JsonResponse({'success': False, 'error': _('يرجى اختيار العميل')}, status=400)

        customer = get_object_or_404(Customer, pk=customer_id)

        # توليد رقم تسلسلي
        import uuid
        order_number = f"ORD-MOB-{uuid.uuid4().hex[:6].upper()}"

        order = PrintingOrder.objects.create(
            order_number=order_number,
            customer=customer,
            title=title,
            order_type=product_type if product_type in [c[0] for c in OrderType.choices] else 'commercial',
            quantity=quantity,
            final_price=price,
            estimated_cost=price * Decimal('0.70'),
            current_stage=ProductionStage.PREPRESS,
            created_by=request.user,
            updated_by=request.user
        )

        OrderSummary.objects.create(
            order=order,
            subtotal=price / Decimal('1.14'),
            tax_amount=price - (price / Decimal('1.14')),
            final_price=price
        )

        return JsonResponse({
            'success': True,
            'order_id': order.pk,
            'order_number': order.order_number,
            'detail_url': reverse('printing_pricing:order_detail', kwargs={'pk': order.pk}),
            'message': _('تم حفظ المقايسة بنجاح برقم {}').format(order.order_number)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

