from decimal import Decimal
from typing import Dict, Any, List, Optional
import logging
from django.utils.translation import gettext_lazy as _
from django.db import transaction
from supplier.models import SupplierService, ServicePriceTier

logger = logging.getLogger(__name__)


class BulkPriceUpdaterService:
    """
    خدمة التحديث المجمع والمفرد لأسعار خامات وخدمات الموردين في MWHEBA ERP.
    تدعم:
    - تحديث سعر الطن price_per_ton للورق مع إعادة احتساب سعر الفرخ المعادل آلياً
    - تحديث سعر الأطقم set_price لماكينات الأوفست وزنكات CTP
    - تحديث السعر الأساسي base_price لباقي الخدمات
    - التحديث بنسبة مئوية مجمعة percentage_change مع تحديث شرائح الكميات التابعة (ServicePriceTier) بالتوازي لمنع الفجوات السعرية
    """

    @classmethod
    def update_single_service(
        cls,
        service: SupplierService,
        *,
        price_per_ton: Optional[Decimal] = None,
        set_price: Optional[Decimal] = None,
        base_price: Optional[Decimal] = None,
        user=None
    ) -> Dict[str, Any]:
        """
        تحديث ذري لسعر خدمة مورد مفردة مع الحفظ التلقائي للحسابات المشتقة.
        """
        update_fields = ['updated_at']

        from django.utils import timezone
        from supplier.models import ServicePriceHistory
        old_snap = service.pricing_snapshot

        if price_per_ton is not None:
            if price_per_ton < Decimal('0.00'):
                raise ValueError(_('سعر الطن لا يمكن أن يكون سالباً'))
            service.price_per_ton = price_per_ton
            update_fields.append('price_per_ton')

        if set_price is not None:
            if set_price < Decimal('0.00'):
                raise ValueError(_('سعر الطقم لا يمكن أن يكون سالباً'))
            service.set_price = set_price
            update_fields.append('set_price')

        if base_price is not None:
            if base_price < Decimal('0.00'):
                raise ValueError(_('السعر الأساسي لا يمكن أن يكون سالباً'))
            service.base_price = base_price
            update_fields.append('base_price')

        service.price_updated_at = timezone.now()
        update_fields.append('price_updated_at')

        # استدعاء save مع تحديث الحقول لإطلاق منطق save() في الموديل
        service.save()

        # توثيق حركة السعر في سجل التاريخ
        ServicePriceHistory.log_price_change(
            service=service,
            user=user,
            source='MANUAL',
            notes='تحديث سريع لسعر الخدمة من مصفوفة الأسعار',
            old_snapshot=old_snap
        )

        # تسجيل حركة التعديل
        if user:
            logger.info(
                f"[AuditLog] Service price updated: ID={service.id}, Name='{service.name}', "
                f"User={user.username}, Fields={update_fields}"
            )

        return {
            'success': True,
            'service': service,
            'effective_sheet_price': service.get_effective_sheet_price(),
        }

    @classmethod
    def bulk_update_supplier_services(
        cls,
        updates: Optional[List[Dict[str, Any]]] = None,
        *,
        service_ids: Optional[List[int]] = None,
        percentage_change: Optional[Decimal] = None,
        user=None
    ) -> Dict[str, Any]:
        """
        تحديث مجمع لأسعار خدمات وخامات الموردين.
        يدعم نمطين:
        1. قائمة تحديثات محددة بالقيم: updates=[{'service_id': 1, 'new_price': 50000, 'field': 'price_per_ton'}, ...]
        2. تحديث بنسبة مئوية مجمعة: service_ids=[1, 2, 3], percentage_change=10.0 (+10%)
        """
        updated_count = 0
        errors = []

        with transaction.atomic():
            # النمط الأول: تحديث بنسبة مئوية مجمعة على قائمة معرفات
            if service_ids is not None and percentage_change is not None:
                factor = Decimal('1.0') + (Decimal(str(percentage_change)) / Decimal('100.0'))
                if factor < Decimal('0.0'):
                    return {'success': False, 'error': _('نسبة التغيير تؤدي إلى أسعار سالبة')}

                services_qs = SupplierService.objects.select_for_update().filter(id__in=service_ids)
                for service in services_qs:
                    try:
                        old_snap = service.pricing_snapshot
                        # 1. تحديث السعر المعني بحسب طبيعة الخدمة
                        if service.pricing_formula == 'PER_TON' and service.price_per_ton:
                            service.price_per_ton = (service.price_per_ton * factor).quantize(Decimal('0.01'))
                        elif service.set_price and service.set_price > Decimal('0.00'):
                            service.set_price = (service.set_price * factor).quantize(Decimal('0.01'))
                            if service.base_price and service.base_price > Decimal('0.00'):
                                service.base_price = (service.base_price * factor).quantize(Decimal('0.01'))
                        else:
                            if service.base_price:
                                service.base_price = (service.base_price * factor).quantize(Decimal('0.01'))

                        from django.utils import timezone
                        service.price_updated_at = timezone.now()
                        service.save()

                        # 2. تحديث شرائح الأسعار التابعة بالتوازي بنفس النسبة المئوية
                        for tier in service.price_tiers.select_for_update().all():
                            tier.price_per_unit = (tier.price_per_unit * factor).quantize(Decimal('0.01'))
                            tier.save(update_fields=['price_per_unit'])

                        # 3. توثيق الحركة في سجل التاريخ
                        from supplier.models import ServicePriceHistory
                        ServicePriceHistory.log_price_change(
                            service=service,
                            user=user,
                            source='BULK_PERCENTAGE',
                            percentage_change=Decimal(str(percentage_change)),
                            notes=f'تحديث مجمع للأسعار بنسبة {percentage_change}%',
                            old_snapshot=old_snap
                        )

                        updated_count += 1
                    except Exception as e:
                        errors.append({'service_id': service.id, 'error': str(e)})

                if user:
                    logger.info(
                        f"[AuditLog] Bulk percentage price update: User={user.username}, "
                        f"Count={updated_count}, Percentage={percentage_change}%"
                    )

                return {
                    'success': updated_count > 0,
                    'updated_count': updated_count,
                    'errors': errors,
                    'message': _('تم تحديث أسعار {} خدمة/خامة وشرائحها بنسبة {}% بنجاح').format(
                        updated_count, percentage_change
                    )
                }

            # النمط الثاني: تحديث بقائمة محددة
            if not updates:
                return {'success': False, 'error': _('قائمة التحديثات فارغة')}

            for item in updates:
                service_id = item.get('service_id')
                new_price = item.get('new_price')
                field_name = item.get('field', 'base_price')

                if not service_id or new_price is None:
                    continue

                try:
                    price_val = Decimal(str(new_price))
                    if price_val < 0:
                        errors.append({'service_id': service_id, 'error': _('السعر لا يمكن أن يكون سالباً')})
                        continue

                    service = SupplierService.objects.select_for_update().get(id=service_id)
                    old_snap = service.pricing_snapshot

                    if field_name == 'price_per_ton' or (service.pricing_formula == 'PER_TON' and field_name != 'base_price'):
                        service.price_per_ton = price_val
                    elif field_name == 'set_price':
                        service.set_price = price_val
                    else:
                        service.base_price = price_val

                    from django.utils import timezone
                    service.price_updated_at = timezone.now()
                    service.save()

                    from supplier.models import ServicePriceHistory
                    ServicePriceHistory.log_price_change(
                        service=service,
                        user=user,
                        source='MANUAL',
                        notes='تحديث مجمع للأسعار بقائمة قيم صريحة',
                        old_snapshot=old_snap
                    )

                    updated_count += 1
                except SupplierService.DoesNotExist:
                    errors.append({'service_id': service_id, 'error': _('الخدمة غير موجودة')})
                except Exception as e:
                    errors.append({'service_id': service_id, 'error': str(e)})

            if user and updated_count > 0:
                logger.info(
                    f"[AuditLog] Bulk explicit price update: User={user.username}, Count={updated_count}"
                )

        return {
            'success': updated_count > 0 or len(errors) == 0,
            'updated_count': updated_count,
            'errors': errors,
            'message': _('تم تحديث {} خدمة بنجاح').format(updated_count)
        }
