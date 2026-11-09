# -*- coding: utf-8 -*-
"""
PropertyContractService - خدمة إدارة ومزامنة العقود العقارية وحصص الملكية
"""
import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from real_estate.models.contract import PropertyContract, ContractCoOwner

logger = logging.getLogger(__name__)


class PropertyContractService:
    """
    محرك حوكمة العقود العقارية ومزامنة حصص الملكية للشركاء
    """

    @classmethod
    def sync_contract_ownership(
        cls,
        contract_id: int,
        primary_owner_share: Decimal,
        co_owners_data: List[Dict[str, Any]],
        user=None
    ) -> PropertyContract:
        """
        مزامنة حصص الملكية للمشتري الرئيسي والشركاء المتضامنين داخل معاملة ذرية مع قفل العقد
        """
        with transaction.atomic():
            contract = PropertyContract.objects.select_for_update().get(pk=contract_id)

            primary_share = Decimal(str(primary_owner_share)).quantize(Decimal('0.01'))
            if primary_share < Decimal('0.00') or primary_share > Decimal('100.00'):
                raise ValidationError(
                    _("نسبة ملكية العميل الرئيسي يجب أن تكون بين 0.00%% و 100.00%% (القيمة الحالية: %(p)s%%).") % {
                        'p': primary_share
                    }
                )

            for item in co_owners_data:
                share = Decimal(str(item.get('share_percentage', '0'))).quantize(Decimal('0.01'))
                if share <= Decimal('0.00') or share > Decimal('100.00'):
                    raise ValidationError(
                        _("نسبة ملكية الشريك يجب أن تكون أكبر من 0%% وحتى 100.00%% (القيمة المدخلة: %(c)s%%).") % {
                            'c': share
                        }
                    )

            co_owners_total = sum(
                Decimal(str(item.get('share_percentage', '0'))).quantize(Decimal('0.01'))
                for item in co_owners_data
            )
            total_share = primary_share + co_owners_total
            if total_share != Decimal('100.00'):
                raise ValidationError(
                    _("إجمالي نسب الملكية في العقد يجب أن يساوي 100.00%% بالضبط (المالك الرئيسي: %(p)s%% + الشركاء: %(c)s%% = %(t)s%%).") % {
                        'p': primary_share,
                        'c': co_owners_total,
                        't': total_share
                    }
                )

            contract.primary_owner_share = primary_share
            contract.save(update_fields=['primary_owner_share', 'updated_at'])

            existing_co_owners = {co.co_owner_id: co for co in contract.co_owners.all()}
            processed_customer_ids = set()

            for item in co_owners_data:
                customer = item.get('co_owner') or item.get('customer')
                cust_id = getattr(customer, 'id', None) or item.get('co_owner_id') or item.get('customer_id')
                if not cust_id:
                    raise ValidationError(_("يجب تحديد العميل الشريك لكل سطر ملكية."))

                processed_customer_ids.add(cust_id)
                share = Decimal(str(item.get('share_percentage', '0'))).quantize(Decimal('0.01'))
                is_guarantor = item.get('is_joint_and_several_guarantor', True)
                relationship = item.get('relationship', ContractCoOwner.RelationshipType.BUSINESS_PARTNER)
                notes = item.get('notes', '')

                if cust_id in existing_co_owners:
                    co_owner_obj = existing_co_owners[cust_id]
                    co_owner_obj.share_percentage = share
                    co_owner_obj.is_joint_and_several_guarantor = is_guarantor
                    co_owner_obj.relationship = relationship
                    co_owner_obj.notes = notes
                    co_owner_obj.save(skip_integrity_check=True)
                else:
                    new_co = ContractCoOwner(
                        contract=contract,
                        co_owner_id=cust_id,
                        share_percentage=share,
                        is_joint_and_several_guarantor=is_guarantor,
                        relationship=relationship,
                        notes=notes,
                    )
                    new_co.save(skip_integrity_check=True)

            for cust_id, co_owner_obj in existing_co_owners.items():
                if cust_id not in processed_customer_ids:
                    co_owner_obj.delete(skip_integrity_check=True)

            contract.validate_ownership_integrity()
            logger.info(
                f"✅ [OwnershipSync] تم تحديث ملكية العقد {contract.contract_number}: "
                f"الرئيسي={primary_share}%، الشركاء={len(processed_customer_ids)}"
            )
            return contract
