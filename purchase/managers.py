from django.db import models


class PurchaseQuerySet(models.QuerySet):
    def with_details(self):
        """
        للاستخدام في شاشات التفاصيل (purchase_detail):
        يجيب كل العلاقات والأشجار المرتبطة بالكامل مسبقاً
        """
        from purchase.models import PurchaseItem, PurchasePayment
        return self.select_related(
            'supplier',
            'warehouse',
            'created_by',
            'financial_category',
            'journal_entry',
            'work_order',
        ).prefetch_related(
            models.Prefetch(
                'items',
                queryset=PurchaseItem.objects.select_related('product', 'product__unit')
            ),
            models.Prefetch(
                'payments',
                queryset=PurchasePayment.objects.select_related('financial_transaction').order_by('-created_at')
            ),
        )

    def with_list_details(self):
        """
        للاستخدام في شاشات القوائم (purchase_list)
        """
        return self.select_related(
            'supplier',
            'warehouse',
            'financial_category',
            'created_by',
        )


PurchaseManager = models.Manager.from_queryset(PurchaseQuerySet)
