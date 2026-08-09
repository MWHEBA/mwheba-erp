from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from financial.models.currency import Currency


@receiver([post_save, post_delete], sender=Currency)
def invalidate_currency_cache(sender, instance, **kwargs):
    """
    إشارة آمنة لتفريغ كاش العملات والمعلومات المرتبطة بها فور تعديل أي عملة في النظام
    """
    cache.delete("default_currency_symbol")
    cache.delete("default_currency_symbol_en")
    cache.delete("company_info_v1")
