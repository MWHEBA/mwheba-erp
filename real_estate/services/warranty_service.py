# -*- coding: utf-8 -*-
"""
WarrantyDefectService - محرك إدارة تذاكر الضمان وخصم تأمينات المقاولين
MWHEBA ERP — Real Estate Wave 3 (Phase 12: Warranty Claims & Contractor Retention Debits)
"""
import logging
from decimal import Decimal
from datetime import timedelta
from typing import Dict, Any, Optional

from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from financial.models import ChartOfAccounts, JournalEntry
from financial.services.role_registry import AccountRoleNames, AccountRoleRegistry
from governance.services.accounting_gateway import AccountingGateway, JournalEntryLineData

from real_estate.models.unit import PropertyUnit
from real_estate.models.contract import PropertyContract
from real_estate.models.contractor import ContractorProgressCertificate
from real_estate.models.warranty import WarrantyTicket

logger = logging.getLogger(__name__)


class WarrantyDefectService:
    """
    محرك إدارة ضمان ما بعد التسليم ومحاسبة تقاعس المقاولين:
    - فحص سريان فترات الضمان القانوني (سنة على التشطيبات / 10 سنوات ضمان عشري)
    - إسناد البلاغات لمقاولي الباطن وتحديد مهل الإصلاح (SLA)
    - الخصم الآلي لتكاليف الإصلاح الفعلي من حساب تأمين ضمان أعمال المقاول (Contractor Retention 21310)
    - العزل التام لقائمة الدخل (Zero P&L Impact) حيث يتم تمويل الإصلاح بالكامل من تأمين المقاول
    """

    @classmethod
    def get_contractor_retention_balance(
        cls,
        contractor,
        project
    ) -> Decimal:
        """
        احتساب رصيد تأمين حسن التنفيذ المتاح للمقاول في المشروع المحدد:
        الرصيد المتاح = إجمالي الاستقطاعات المحتجزة بالمستخلصات المعتمدة - إجمالي الخصومات المنفذة بتذاكر الضمان
        """
        # 1. إجمالي الاستقطاعات المحتجزة من مستخلصات المقاول المعتمدة والمدفوعة
        total_withheld = ContractorProgressCertificate.objects.filter(
            project=project,
            contractor=contractor,
            status__in=[
                ContractorProgressCertificate.CertificateStatus.APPROVED,
                ContractorProgressCertificate.CertificateStatus.PAID
            ]
        ).aggregate(total=models.Sum('retention_amount'))['total'] or Decimal("0.00")

        # 2. إجمالي المبالغ المخصومة سابقاً من تأمين المقاول على هذا المشروع
        total_debited = WarrantyTicket.objects.filter(
            responsible_contractor=contractor,
            unit__project=project,
            status=WarrantyTicket.TicketStatus.CLOSED_DEBITED
        ).aggregate(total=models.Sum('actual_repair_cost'))['total'] or Decimal("0.00")

        available_balance = total_withheld - total_debited
        return max(Decimal("0.00"), available_balance)

    @classmethod
    @transaction.atomic
    def create_warranty_ticket(
        cls,
        unit: PropertyUnit,
        contract: PropertyContract,
        customer,
        category: str,
        title: str,
        description: str,
        priority: str = WarrantyTicket.TicketPriority.MEDIUM,
        warranty_type: str = WarrantyTicket.WarrantyType.FINISHING_ONE_YEAR,
        responsible_contractor=None,
        created_by=None
    ) -> WarrantyTicket:
        """
        إنشاء بلاغ عيب وضمان جديد لوحدة عقارية مسلمة
        """
        ticket = WarrantyTicket(
            unit=unit,
            contract=contract,
            customer=customer,
            category=category,
            priority=priority,
            warranty_type=warranty_type,
            title=title,
            description=description,
            responsible_contractor=responsible_contractor,
            status=WarrantyTicket.TicketStatus.REPORTED,
            created_by=created_by
        )
        ticket.full_clean()
        ticket.save()

        logger.info(f"Created warranty ticket {ticket.ticket_number} for unit {unit.unit_code}")
        return ticket

    @classmethod
    @transaction.atomic
    def inspect_and_assign_contractor(
        cls,
        ticket: WarrantyTicket,
        responsible_contractor,
        priority: Optional[str] = None,
        engineer_notes: str = "",
        sla_days: int = 7,
        inspected_by=None
    ) -> WarrantyTicket:
        """
        معاينة العيب وإسناد المسؤولية لمقاول الباطن وتحديد مهلة الـ SLA
        """
        if ticket.status in [WarrantyTicket.TicketStatus.CLOSED_DEBITED, WarrantyTicket.TicketStatus.RESOLVED_BY_CONTRACTOR]:
            raise ValidationError(_("لا يمكن تعديل تذكرة ضمان تم إغلاقها أو تسويتها بالفعل."))

        today = timezone.localdate()
        ticket.responsible_contractor = responsible_contractor
        ticket.contractor_notification_date = today
        ticket.contractor_sla_deadline = today + timedelta(days=sla_days)
        ticket.status = WarrantyTicket.TicketStatus.CONTRACTOR_NOTIFIED
        ticket.inspected_by = inspected_by
        ticket.inspected_at = timezone.now()

        if priority:
            ticket.priority = priority
        if engineer_notes:
            ticket.engineer_notes = engineer_notes

        ticket.save()
        logger.info(
            f"Warranty ticket {ticket.ticket_number} assigned to contractor {responsible_contractor.name} "
            f"with SLA deadline {ticket.contractor_sla_deadline}"
        )
        return ticket

    @classmethod
    @transaction.atomic
    def resolve_by_contractor(
        cls,
        ticket: WarrantyTicket,
        resolution_notes: str = "",
        user=None
    ) -> WarrantyTicket:
        """
        إغلاق التذكرة بعد قيام المقاول بالإصلاح على نفقته الخاصة (Zero Cost / Zero Journal Entry)
        """
        if ticket.status in [WarrantyTicket.TicketStatus.CLOSED_DEBITED, WarrantyTicket.TicketStatus.RESOLVED_BY_CONTRACTOR]:
            raise ValidationError(_("تذكرة الضمان معالجة أو مغلقة بالفعل."))

        ticket.status = WarrantyTicket.TicketStatus.RESOLVED_BY_CONTRACTOR
        ticket.closure_notes = resolution_notes
        ticket.closed_by = user
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=['status', 'closure_notes', 'closed_by', 'closed_at', 'updated_at'])

        logger.info(f"Warranty ticket {ticket.ticket_number} resolved by contractor successfully.")
        return ticket

    @classmethod
    @transaction.atomic
    def execute_contractor_default_and_debit_retention(
        cls,
        ticket: WarrantyTicket,
        repair_cost: Decimal,
        settlement_account: ChartOfAccounts,
        user=None,
        closure_notes: str = ""
    ) -> WarrantyTicket:
        """
        إثبات تقاعس المقاول وتنفيذ الإصلاح المباشر وخصم التكلفة من تأمين المقاول:
        - فحص كفاية رصيد تأمين أعمال المقاول في المشروع
        - ترحيل القيد المحاسبي:
          Dr: Contractor Retentions Payable (21310) [تخفيض التزام تأمين المقاول المحتجز]
          Cr: Settlement Account (11110 نقدية / 11160 بنك / 21110 مورد الصيانة البديل)
        - حماية قائمة دخل المطور بنسبة 100% (Zero P&L Impact)
        """
        if ticket.status in [WarrantyTicket.TicketStatus.CLOSED_DEBITED, WarrantyTicket.TicketStatus.RESOLVED_BY_CONTRACTOR]:
            raise ValidationError(_("تذكرة الضمان مغلقة بالفعل."))

        contractor = ticket.responsible_contractor
        if not contractor:
            raise ValidationError(_("يلزم إسناد التذكرة لمقاول مسؤول قبل إجراء الخصم من التأمين."))

        cost_dec = Decimal(str(repair_cost))
        if cost_dec <= Decimal("0.00"):
            raise ValidationError(_("تكلفة الإصلاح الفعلي يجب أن تكون أكبر من الصفر."))

        project = ticket.unit.project

        # فحص رصيد التأمين المتاح للمقاول
        available_retention = cls.get_contractor_retention_balance(contractor=contractor, project=project)
        if cost_dec > available_retention:
            raise ValidationError(
                _("رصيد تأمين أعمال المقاول %(contractor)s في مشروع %(project)s غير كافٍ. "
                  "المتاح: %(available)s ج.م، المطلوب خصمه: %(cost)s ج.م.") % {
                    'contractor': contractor.name,
                    'project': project.name,
                    'available': available_retention,
                    'cost': cost_dec
                }
            )

        # استرجاع حساب تأمين أعمال المقاولين (21310)
        retention_acc = AccountRoleRegistry.get_account(
            AccountRoleNames.REAL_ESTATE_CONTRACTOR_RETENTIONS_PAYABLE.value
        )
        if not retention_acc:
            retention_acc = ChartOfAccounts.objects.filter(code="21310", is_active=True).first()
        if not retention_acc or not retention_acc.is_active:
            raise ValidationError(_("حساب تأمينات مقاولي الباطن المحتجزة (21310) غير معرف أو غير نشط."))

        proj_code = project.code
        currency_str = getattr(ticket.contract.currency, 'code', 'EGP') if ticket.contract.currency else 'EGP'

        desc = (
            f"خصم تكاليف إصلاح عيب بالوحدة {ticket.unit.unit_code} من تأمين المقاول {contractor.name} "
            f"- تذكرة {ticket.ticket_number}"
        )

        # قيد محاسبي معزول تماماً عن الأرباح والخسائر:
        # مدين: تخفيض التزام تأمين المقاول
        # دائن: حساب السداد المنصرف منه (خزينة/بنك/مورد بديل)
        lines = [
            JournalEntryLineData(
                account_code=retention_acc.code,
                debit=cost_dec,
                credit=Decimal("0.00"),
                currency=currency_str,
                description=desc,
                project=proj_code
            ),
            JournalEntryLineData(
                account_code=settlement_account.code,
                debit=Decimal("0.00"),
                credit=cost_dec,
                currency=currency_str,
                description=f"سداد تكلفة إصلاح العيب المنفذ لتذكرة {ticket.ticket_number}",
                project=proj_code
            )
        ]

        idempotency_key = AccountingGateway.generate_idempotency_key(
            module='real_estate',
            model='WarrantyTicket',
            object_id=ticket.id,
            operation='retention_debit'
        )

        gateway = AccountingGateway()
        entry = gateway.create_journal_entry(
            source_module='real_estate',
            source_model='WarrantyTicket',
            source_id=ticket.id,
            lines=lines,
            idempotency_key=idempotency_key,
            user=user,
            entry_type='vendor_payment',
            description=desc,
            reference=ticket.ticket_number,
            date=timezone.localdate()
        )

        ticket.actual_repair_cost = cost_dec
        ticket.retention_journal_entry = entry
        ticket.settlement_account = settlement_account
        ticket.status = WarrantyTicket.TicketStatus.CLOSED_DEBITED
        ticket.closure_notes = closure_notes or f"تم الإصلاح المباشر وخصم {cost_dec} ج.م من تأمين المقاول {contractor.name}"
        ticket.closed_by = user
        ticket.closed_at = timezone.now()
        ticket.save()

        logger.info(
            f"Successfully debited {cost_dec} EGP from contractor {contractor.name} retention. "
            f"JE: {entry.number}"
        )
        return ticket
