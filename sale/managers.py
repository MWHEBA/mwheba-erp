from django.db import models


class SaleQuerySet(models.QuerySet):
    def with_details(self):
        """
        للاستخدام في شاشات التفاصيل (sale_detail):
        يجيب كل العلاقات والأشجار المرتبطة بالكامل مسبقاً
        """
        from sale.models import SaleItem, SalePayment, SaleReturn
        return self.select_related(
            'customer',
            'warehouse',
            'salesman',
            'created_by',
            'financial_category',
            'journal_entry',
            'quotation',
            'work_order',
        ).prefetch_related(
            models.Prefetch(
                'items',
                queryset=SaleItem.objects.select_related('product', 'product__unit')
            ),
            models.Prefetch(
                'payments',
                queryset=SalePayment.objects.select_related('financial_transaction').order_by('-payment_date')
            ),
            models.Prefetch(
                'returns',
                queryset=SaleReturn.objects.filter(status='confirmed').prefetch_related('items__sale_item')
            ),
        )

    def with_list_details(self):
        """
        للاستخدام في شاشات القوائم والترقيم (sale_list):
        يقتصر على select_related للرابط المباشر فقط دون سحب البنود لتوفير الذاكرة
        """
        return self.select_related(
            'customer',
            'warehouse',
            'salesman',
            'created_by',
        )


class QuotationQuerySet(models.QuerySet):
    def with_details(self):
        """
        للاستخدام في شاشات تفاصيل عرض السعر (quotation_detail)
        """
        from sale.models import QuotationItem
        return self.select_related(
            'customer',
            'warehouse',
            'salesman',
            'created_by',
            'converted_to_sale',
            'work_order',
        ).prefetch_related(
            models.Prefetch(
                'items',
                queryset=QuotationItem.objects.select_related('product', 'product__unit')
            ),
        )

    def with_list_details(self):
        """
        للاستخدام في شاشات قوائم عروض الأسعار
        """
        return self.select_related(
            'customer',
            'warehouse',
            'salesman',
            'created_by',
        )


SaleManager = models.Manager.from_queryset(SaleQuerySet)
QuotationManager = models.Manager.from_queryset(QuotationQuerySet)
