from decimal import Decimal
from typing import Dict, Any, List
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from supplier.models import SupplierService


class BulkPriceUpdaterService:
    """
    خدمة التحديث المجمع لأسعار خدمات الورش والمطابع وأسعار الورق
    """

    @classmethod
    def bulk_update_supplier_services(
        cls,
        updates: List[Dict[str, Any]],
        user=None
    ) -> Dict[str, Any]:
        """
        تحديث مجمع لأسعار خدمات الموردين (سحب مطابع، سلوفان، تكسير، زنكات، يوفي)
        """
        if not updates:
            return {'success': False, 'error': _('قائمة التحديثات فارغة')}

        updated_count = 0
        errors = []

        with transaction.atomic():
            for item in updates:
                service_id = item.get('service_id')
                new_price = item.get('new_price')

                if not service_id or new_price is None:
                    continue

                try:
                    price_val = Decimal(str(new_price))
                    if price_val < 0:
                        errors.append({'service_id': service_id, 'error': _('السعر لا يمكن أن يكون سالباً')})
                        continue

                    service = SupplierService.objects.select_for_update().get(id=service_id)
                    old_price = service.base_price
                    service.base_price = price_val
                    if user:
                        service.updated_by = user
                    service.save(update_fields=['base_price', 'updated_at'])
                    updated_count += 1
                except SupplierService.DoesNotExist:
                    errors.append({'service_id': service_id, 'error': _('الخدمة غير موجودة')})
                except Exception as e:
                    errors.append({'service_id': service_id, 'error': str(e)})

        return {
            'success': updated_count > 0 or len(errors) == 0,
            'updated_count': updated_count,
            'errors': errors,
            'message': _('تم تحديث {} خدمة بنجاح').format(updated_count)
        }
