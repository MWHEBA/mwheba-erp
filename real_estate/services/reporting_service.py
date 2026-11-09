# -*- coding: utf-8 -*-
"""
RealEstateReportingService - محرك التقارير المالية والتحليلية وكشوف الحساب المزدوجة
MWHEBA ERP — Real Estate Wave 6 (Phase 6.1: Dual-Perspective Subledger, Cash Flow Radar, WIP & IFRS 15, Broker Radar)
"""
import logging
from decimal import Decimal
from datetime import date
from typing import Dict, Any, List, Optional
from collections import defaultdict

from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone

from real_estate.models import (
    RealEstateProject,
    PropertyUnit,
    PropertyContract,
    PropertyHandoverReceipt,
    ContractorProgressCertificate,
    ClientVariationOrder,
    RealEstateBroker,
    BrokerCommission,
    InfrastructureApportionmentLine,
)
from real_estate.services.clearance_service import ContractDebtClearanceService
from sale.models.installments import InstallmentItem
from cheques.models.allocation import ChequeInvoiceAllocation
from cheques.models.cheque import ChequeStatus

logger = logging.getLogger(__name__)


class RealEstateReportingService:
    """
    محرك التقارير التحليلية والمحاسبية لقطاع التطوير والاستثمار العقاري:
    1. كشف الحساب المزدوج (Dual-Perspective Subledger): المنظور التعاقدي مقابل المنظور المالي والشيكات وIFRS 15.
    2. رادار التدفقات النقدية ومطابقة السيولة (Cash Flow & Liquidity Matching Radar).
    3. تقرير تكاليف المشروعات تحت التنفيذ والاعتراف بالإيراد (Project WIP Costing & IFRS 15 Revenue).
    4. رادار أداء الوسطاء العقاريين واستحقاقات العمولات المرحلية (Broker Attribution & Staged Commissions).
    """

    @classmethod
    def get_dual_subledger_report(
        cls,
        project_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        status: Optional[str] = None,
        clearance_filter: Optional[str] = None,
        search_query: str = ""
    ) -> Dict[str, Any]:
        """
        بناء تقرير كشف الحساب المزدوج للعقود والعملاء (تعاقدي vs مالي/شيكات/إيراد IFRS 15)
        """
        qs = PropertyContract.objects.select_related(
            'project', 'unit', 'customer', 'currency', 'installment_plan'
        ).order_by('-contract_date', '-id')

        if project_id:
            qs = qs.filter(project_id=project_id)
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        if status:
            qs = qs.filter(status=status)
        if search_query:
            qs = qs.filter(
                Q(contract_number__icontains=search_query) |
                Q(customer__name__icontains=search_query) |
                Q(unit__unit_code__icontains=search_query) |
                Q(project__name__icontains=search_query)
            )

        today = timezone.localdate()
        rows: List[Dict[str, Any]] = []

        total_contractual_value = Decimal('0.00')
        total_verified_collected = Decimal('0.00')
        total_cheques_in_vault = Decimal('0.00')
        total_remaining_contractual = Decimal('0.00')
        total_deferred_liability = Decimal('0.00')
        total_recognized_revenue = Decimal('0.00')

        vault_statuses = [
            ChequeStatus.IN_PORTFOLIO,
            ChequeStatus.UNDER_COLLECTION,
        ]
        bounced_statuses = [
            ChequeStatus.BOUNCED,
            ChequeStatus.LEGAL_ACTION,
            ChequeStatus.ENDORSED_BOUNCED,
        ]

        for contract in qs:
            verified_dp = ContractDebtClearanceService.get_verified_down_payment(contract)

            plan = contract.installment_plan
            scheduled_installments_total = Decimal('0.00')
            paid_installments_amount = Decimal('0.00')
            overdue_installments_count = 0
            overdue_amount = Decimal('0.00')
            cheques_in_vault = Decimal('0.00')
            cheques_collected = Decimal('0.00')
            cheques_bounced = Decimal('0.00')
            bounced_count = 0

            if plan:
                items = list(plan.items.all())
                for item in items:
                    scheduled_installments_total += Decimal(str(item.total_amount))
                    paid_installments_amount += Decimal(str(item.paid_amount))
                    rem_item = max(Decimal('0.00'), Decimal(str(item.total_amount)) - Decimal(str(item.paid_amount)))
                    if rem_item > Decimal('0.00') and item.due_date < today:
                        overdue_installments_count += 1
                        overdue_amount += rem_item

                allocations = ChequeInvoiceAllocation.objects.filter(
                    installment_item__plan=plan,
                    allocation_status='APPLIED'
                ).select_related('cheque')

                for alloc in allocations:
                    chq = alloc.cheque
                    alloc_amt = Decimal(str(alloc.allocated_amount))
                    if chq.status in vault_statuses:
                        cheques_in_vault += alloc_amt
                    elif chq.status == ChequeStatus.COLLECTED:
                        cheques_collected += alloc_amt
                    elif chq.status in bounced_statuses:
                        cheques_bounced += alloc_amt
                        bounced_count += 1

            total_paid = verified_dp + paid_installments_amount
            remaining_balance = max(Decimal('0.00'), contract.final_contract_price - total_paid)
            unbacked_balance = max(Decimal('0.00'), remaining_balance - cheques_in_vault)

            is_delivered = PropertyHandoverReceipt.objects.filter(
                contract=contract,
                status=PropertyHandoverReceipt.HandoverStatus.EXECUTED
            ).exists()

            prior_rec = contract.recognized_revenue_amount or Decimal('0.00')

            if prior_rec > Decimal('0.00'):
                recognized_rev = min(prior_rec, contract.final_contract_price)
                if recognized_rev >= contract.final_contract_price:
                    revenue_status = 'RECOGNIZED'
                else:
                    revenue_status = 'PARTIAL_DELIVERY' if is_delivered else 'POC_PARTIAL'
                deferred_liab = max(Decimal('0.00'), total_paid - recognized_rev)
            elif is_delivered:
                rec_with_rev = PropertyHandoverReceipt.objects.filter(
                    contract=contract,
                    status=PropertyHandoverReceipt.HandoverStatus.EXECUTED
                ).filter(Q(revenue_journal_entry__isnull=False) | Q(recognized_revenue_amount__gt=0)).first()
                if rec_with_rev:
                    recognized_rev = min(rec_with_rev.recognized_revenue_amount or contract.final_contract_price, contract.final_contract_price)
                    revenue_status = 'RECOGNIZED' if recognized_rev >= contract.final_contract_price else 'PARTIAL_DELIVERY'
                    deferred_liab = max(Decimal('0.00'), total_paid - recognized_rev)
                else:
                    revenue_status = 'DEFERRED'
                    recognized_rev = Decimal('0.00')
                    deferred_liab = total_paid
            else:
                revenue_status = 'DEFERRED'
                recognized_rev = Decimal('0.00')
                deferred_liab = total_paid

            is_cleared = (
                remaining_balance <= Decimal('0.05') and
                bounced_count == 0
            )

            if clearance_filter == 'CLEARED' and not is_cleared:
                continue
            elif clearance_filter == 'OPEN_BALANCE' and is_cleared:
                continue
            elif clearance_filter == 'BOUNCED' and bounced_count == 0:
                continue

            collection_rate = Decimal('0.00')
            if contract.final_contract_price > Decimal('0.00'):
                collection_rate = ((total_paid / contract.final_contract_price) * Decimal('100.00')).quantize(Decimal('0.01'))

            row_data = {
                'contract': contract,
                'final_contract_price': contract.final_contract_price,
                'down_payment': contract.down_payment,
                'verified_down_payment': verified_dp,
                'scheduled_installments_total': scheduled_installments_total,
                'paid_installments_amount': paid_installments_amount,
                'total_paid': total_paid,
                'remaining_balance': remaining_balance,
                'unbacked_balance': unbacked_balance,
                'collection_rate': collection_rate,
                'overdue_installments_count': overdue_installments_count,
                'overdue_amount': overdue_amount,
                'cheques_in_vault': cheques_in_vault,
                'cheques_collected': cheques_collected,
                'cheques_bounced': cheques_bounced,
                'bounced_count': bounced_count,
                'revenue_status': revenue_status,
                'recognized_revenue': recognized_rev,
                'deferred_liability': deferred_liab,
                'is_cleared': is_cleared,
                'is_delivered': is_delivered,
            }
            rows.append(row_data)

            total_contractual_value += contract.final_contract_price
            total_verified_collected += total_paid
            total_cheques_in_vault += cheques_in_vault
            total_remaining_contractual += remaining_balance
            total_deferred_liability += deferred_liab
            total_recognized_revenue += recognized_rev

        return {
            'rows': rows,
            'total_contracts_count': len(rows),
            'total_contractual_value': total_contractual_value,
            'total_verified_collected': total_verified_collected,
            'total_cheques_in_vault': total_cheques_in_vault,
            'total_remaining_contractual': total_remaining_contractual,
            'total_deferred_liability': total_deferred_liability,
            'total_recognized_revenue': total_recognized_revenue,
        }

    @classmethod
    def get_cash_flow_liquidity_report(
        cls,
        project_id: Optional[int] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        بناء رادار التدفقات النقدية العقارية ومطابقة السيولة الشهرية:
        يقارن الأقساط العقارية المستحقة والمغطاة بشيكات مقابل التزامات مستخلصات المقاولين
        """
        installments_qs = InstallmentItem.objects.filter(
            plan__property_contract__isnull=False,
            plan__property_contract__status__in=[
                PropertyContract.ContractStatus.ACTIVE,
                PropertyContract.ContractStatus.COMPLETED,
            ]
        ).select_related(
            'plan__property_contract__project',
            'plan__property_contract__unit',
            'plan__property_contract__customer',
        ).order_by('due_date', 'installment_number')

        certificates_qs = ContractorProgressCertificate.objects.filter(
            status__in=[
                ContractorProgressCertificate.CertificateStatus.APPROVED,
                ContractorProgressCertificate.CertificateStatus.PENDING_APPROVAL,
                ContractorProgressCertificate.CertificateStatus.PAID,
            ]
        ).select_related('project', 'contractor').order_by('period_end')

        if project_id:
            installments_qs = installments_qs.filter(plan__property_contract__project_id=project_id)
            certificates_qs = certificates_qs.filter(project_id=project_id)

        if date_from:
            installments_qs = installments_qs.filter(due_date__gte=date_from)
            certificates_qs = certificates_qs.filter(period_end__gte=date_from)

        if date_to:
            installments_qs = installments_qs.filter(due_date__lte=date_to)
            certificates_qs = certificates_qs.filter(period_end__lte=date_to)

        vault_statuses = [
            ChequeStatus.IN_PORTFOLIO,
            ChequeStatus.UNDER_COLLECTION,
        ]

        monthly_buckets: Dict[str, Dict[str, Decimal]] = defaultdict(lambda: {
            'scheduled_inflow': Decimal('0.00'),
            'collected_inflow': Decimal('0.00'),
            'expected_remaining_inflow': Decimal('0.00'),
            'cheque_backed_inflow': Decimal('0.00'),
            'unbacked_inflow': Decimal('0.00'),
            'contractor_outflow': Decimal('0.00'),
            'net_liquidity': Decimal('0.00'),
        })

        total_scheduled_inflows = Decimal('0.00')
        total_collected_inflows = Decimal('0.00')
        total_expected_remaining = Decimal('0.00')
        total_cheque_backed = Decimal('0.00')
        total_contractor_outflows = Decimal('0.00')

        installment_rows: List[Dict[str, Any]] = []
        today = timezone.localdate()

        for item in installments_qs:
            contract = item.plan.property_contract
            month_key = item.due_date.strftime('%Y-%m')
            total_amt = Decimal(str(item.total_amount))
            paid_amt = Decimal(str(item.paid_amount))
            rem_amt = max(Decimal('0.00'), total_amt - paid_amt)

            allocs = ChequeInvoiceAllocation.objects.filter(
                installment_item=item,
                allocation_status='APPLIED',
                cheque__status__in=vault_statuses
            )
            chq_backed = sum((Decimal(str(a.allocated_amount)) for a in allocs), Decimal('0.00'))
            chq_backed = min(rem_amt, chq_backed)
            unbacked = max(Decimal('0.00'), rem_amt - chq_backed)

            bucket = monthly_buckets[month_key]
            bucket['scheduled_inflow'] += total_amt
            bucket['collected_inflow'] += paid_amt
            bucket['expected_remaining_inflow'] += rem_amt
            bucket['cheque_backed_inflow'] += chq_backed
            bucket['unbacked_inflow'] += unbacked

            total_scheduled_inflows += total_amt
            total_collected_inflows += paid_amt
            total_expected_remaining += rem_amt
            total_cheque_backed += chq_backed

            installment_rows.append({
                'item': item,
                'contract': contract,
                'project': contract.project,
                'unit': contract.unit,
                'customer': contract.customer,
                'due_date': item.due_date,
                'total_amount': total_amt,
                'paid_amount': paid_amt,
                'remaining_amount': rem_amt,
                'cheque_backed_amount': chq_backed,
                'unbacked_amount': unbacked,
                'is_overdue': rem_amt > Decimal('0.00') and item.due_date < today,
            })

        for cert in certificates_qs:
            month_key = cert.period_end.strftime('%Y-%m')
            net_amt = Decimal(str(cert.net_amount))
            monthly_buckets[month_key]['contractor_outflow'] += net_amt
            total_contractor_outflows += net_amt

        monthly_summary: List[Dict[str, Any]] = []
        for month_key in sorted(monthly_buckets.keys()):
            b = monthly_buckets[month_key]
            inflow_total = b['collected_inflow'] + b['expected_remaining_inflow']
            b['net_liquidity'] = inflow_total - b['contractor_outflow']
            monthly_summary.append({
                'month': month_key,
                **b
            })

        net_liquidity_gap = (total_collected_inflows + total_expected_remaining) - total_contractor_outflows

        return {
            'monthly_summary': monthly_summary,
            'installment_rows': installment_rows,
            'total_scheduled_inflows': total_scheduled_inflows,
            'total_collected_inflows': total_collected_inflows,
            'total_expected_remaining': total_expected_remaining,
            'total_cheque_backed': total_cheque_backed,
            'total_contractor_outflows': total_contractor_outflows,
            'net_liquidity_gap': net_liquidity_gap,
        }

    @classmethod
    def get_project_wip_revenue_report(
        cls,
        project_id: Optional[int] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        تقرير تكاليف المشروعات تحت التنفيذ (WIP Costing) والاعتراف بالإيراد وفق معيار IFRS 15
        """
        projects_qs = RealEstateProject.objects.filter(is_archived=False).order_by('code')
        if project_id:
            projects_qs = projects_qs.filter(pk=project_id)
        if status:
            projects_qs = projects_qs.filter(status=status)

        project_rows: List[Dict[str, Any]] = []

        grand_contracted_sales = Decimal('0.00')
        grand_recognized_revenue = Decimal('0.00')
        grand_deferred_revenue = Decimal('0.00')
        grand_wip_cost = Decimal('0.00')
        grand_interim_cogs = Decimal('0.00')

        for project in projects_qs:
            units = PropertyUnit.objects.filter(project=project)
            total_units = units.count()
            available_units = units.filter(status=PropertyUnit.UnitStatus.AVAILABLE).count()
            sold_units = units.filter(
                status__in=[
                    PropertyUnit.UnitStatus.CONTRACTED,
                    PropertyUnit.UnitStatus.DELIVERED,
                    PropertyUnit.UnitStatus.DELIVERED_DEEMED,
                ]
            ).count()

            active_contracts = PropertyContract.objects.filter(
                project=project,
                status__in=[
                    PropertyContract.ContractStatus.ACTIVE,
                    PropertyContract.ContractStatus.COMPLETED,
                ]
            )
            contracted_sales = active_contracts.aggregate(
                s=Sum('final_contract_price')
            )['s'] or Decimal('0.00')

            executed_handovers = PropertyHandoverReceipt.objects.filter(
                contract__project=project,
                status=PropertyHandoverReceipt.HandoverStatus.EXECUTED
            ).select_related('contract')

            delivered_units_count = executed_handovers.count()

            # حصر الإيراد المحقق والمثبت دفترياً (يشمل نسب الإنجاز التراكمية POC والتسليمات المعتمدة)
            contract_recognized_map = {
                c.id: (c.recognized_revenue_amount or Decimal('0.00'))
                for c in active_contracts
            }
            # دعم محاضر التسليم المنفذة ذات قيود الإيراد أو المبالغ المعتمدة
            for h in executed_handovers:
                if h.contract_id in contract_recognized_map:
                    if contract_recognized_map[h.contract_id] == Decimal('0.00'):
                        if h.revenue_journal_entry_id or (h.recognized_revenue_amount and h.recognized_revenue_amount > Decimal('0.00')):
                            contract_recognized_map[h.contract_id] = h.recognized_revenue_amount or h.contract.final_contract_price
                else:
                    rec_amt = h.contract.recognized_revenue_amount or Decimal('0.00')
                    if rec_amt == Decimal('0.00'):
                        if h.revenue_journal_entry_id or (h.recognized_revenue_amount and h.recognized_revenue_amount > Decimal('0.00')):
                            rec_amt = h.recognized_revenue_amount or h.contract.final_contract_price
                    contract_recognized_map[h.contract_id] = rec_amt

            recognized_revenue = sum(contract_recognized_map.values(), Decimal('0.00'))
            interim_cogs = executed_handovers.aggregate(
                s=Sum('interim_cogs_amount')
            )['s'] or Decimal('0.00')

            deferred_revenue = max(Decimal('0.00'), contracted_sales - recognized_revenue)

            # تكاليف المقاولين المعتمدة (WIP)
            approved_certs = ContractorProgressCertificate.objects.filter(
                project=project,
                status__in=[
                    ContractorProgressCertificate.CertificateStatus.APPROVED,
                    ContractorProgressCertificate.CertificateStatus.PAID,
                ]
            )
            cert_work = approved_certs.aggregate(s=Sum('current_period_work'))['s'] or Decimal('0.00')
            cert_materials = approved_certs.aggregate(s=Sum('materials_on_site'))['s'] or Decimal('0.00')
            direct_contractor_wip = cert_work + cert_materials

            # نصيب المشروع من تكاليف البنية التحتية المشتركة المرحلة
            infra_wip = InfrastructureApportionmentLine.objects.filter(
                beneficiary_project=project,
                apportionment__status='POSTED'
            ).aggregate(s=Sum('allocated_amount'))['s'] or Decimal('0.00')

            # أوامر التعديل المعماري المعتمدة
            variation_value = ClientVariationOrder.objects.filter(
                contract__project=project,
                status__in=['APPROVED', 'EXECUTED']
            ).aggregate(s=Sum('total_cost'))['s'] or Decimal('0.00')

            total_wip_cost = direct_contractor_wip + infra_wip
            remaining_wip_inventory = max(Decimal('0.00'), total_wip_cost - interim_cogs)
            gross_profit_recognized = recognized_revenue - interim_cogs

            cost_per_sqm = Decimal('0.00')
            if project.gross_built_area and project.gross_built_area > Decimal('0.00'):
                cost_per_sqm = (total_wip_cost / project.gross_built_area).quantize(Decimal('0.01'))

            absorption_rate = Decimal('0.00')
            if total_units > 0:
                absorption_rate = ((Decimal(str(sold_units)) / Decimal(str(total_units))) * Decimal('100.00')).quantize(Decimal('0.01'))

            project_rows.append({
                'project': project,
                'total_units': total_units,
                'available_units': available_units,
                'sold_units': sold_units,
                'delivered_units_count': delivered_units_count,
                'absorption_rate': absorption_rate,
                'contracted_sales': contracted_sales,
                'recognized_revenue': recognized_revenue,
                'deferred_revenue': deferred_revenue,
                'direct_contractor_wip': direct_contractor_wip,
                'infra_wip': infra_wip,
                'variation_value': variation_value,
                'total_wip_cost': total_wip_cost,
                'interim_cogs': interim_cogs,
                'remaining_wip_inventory': remaining_wip_inventory,
                'gross_profit_recognized': gross_profit_recognized,
                'cost_per_sqm': cost_per_sqm,
            })

            grand_contracted_sales += contracted_sales
            grand_recognized_revenue += recognized_revenue
            grand_deferred_revenue += deferred_revenue
            grand_wip_cost += total_wip_cost
            grand_interim_cogs += interim_cogs

        return {
            'project_rows': project_rows,
            'grand_contracted_sales': grand_contracted_sales,
            'grand_recognized_revenue': grand_recognized_revenue,
            'grand_deferred_revenue': grand_deferred_revenue,
            'grand_wip_cost': grand_wip_cost,
            'grand_interim_cogs': grand_interim_cogs,
        }

    @classmethod
    def get_broker_commission_report(
        cls,
        broker_id: Optional[int] = None,
        project_id: Optional[int] = None,
        tranche_status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        تقرير أداء الوسطاء العقاريين واستحقاقات العمولات المرحلية (50% تعاقد / 50% تحصيل)
        """
        commissions_qs = BrokerCommission.objects.select_related(
            'broker', 'contract__project', 'contract__unit', 'contract__customer'
        ).order_by('-created_at', '-id')

        if broker_id:
            commissions_qs = commissions_qs.filter(broker_id=broker_id)
        if project_id:
            commissions_qs = commissions_qs.filter(contract__project_id=project_id)
        if tranche_status:
            commissions_qs = commissions_qs.filter(
                Q(tranche_1_status=tranche_status) | Q(tranche_2_status=tranche_status)
            )

        commission_rows: List[Dict[str, Any]] = []
        broker_summary_map: Dict[int, Dict[str, Any]] = {}

        total_brokered_sales = Decimal('0.00')
        total_commissions_amount = Decimal('0.00')
        total_released_commissions = Decimal('0.00')
        total_retained_commissions = Decimal('0.00')

        for comm in commissions_qs:
            paid_amt = Decimal('0.00')
            if comm.tranche_1_status == BrokerCommission.TrancheStatus.PAID:
                paid_amt += comm.staged_tranche_1_amount
            if comm.tranche_2_status == BrokerCommission.TrancheStatus.PAID:
                paid_amt += comm.staged_tranche_2_amount

            retained_amt = max(Decimal('0.00'), comm.total_commission_amount - paid_amt - comm.clawback_amount)
            contract_price = comm.contract.final_contract_price

            commission_rows.append({
                'commission': comm,
                'broker': comm.broker,
                'contract': comm.contract,
                'contract_price': contract_price,
                'paid_amount': paid_amt,
                'retained_amount': retained_amt,
            })

            total_brokered_sales += contract_price
            total_commissions_amount += comm.total_commission_amount
            total_released_commissions += paid_amt
            total_retained_commissions += retained_amt

            b_id = comm.broker_id
            if b_id not in broker_summary_map:
                broker_summary_map[b_id] = {
                    'broker': comm.broker,
                    'contracts_count': 0,
                    'brokered_sales': Decimal('0.00'),
                    'total_commission': Decimal('0.00'),
                    'released_commission': Decimal('0.00'),
                    'retained_commission': Decimal('0.00'),
                    'clawback_amount': Decimal('0.00'),
                }
            b_entry = broker_summary_map[b_id]
            b_entry['contracts_count'] += 1
            b_entry['brokered_sales'] += contract_price
            b_entry['total_commission'] += comm.total_commission_amount
            b_entry['released_commission'] += paid_amt
            b_entry['retained_commission'] += retained_amt
            b_entry['clawback_amount'] += comm.clawback_amount

        return {
            'commission_rows': commission_rows,
            'broker_summaries': list(broker_summary_map.values()),
            'total_brokered_sales': total_brokered_sales,
            'total_commissions_amount': total_commissions_amount,
            'total_released_commissions': total_released_commissions,
            'total_retained_commissions': total_retained_commissions,
        }

    @classmethod
    def get_tower_sales_brief_report(
        cls,
        block_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        تقرير الموقف التنفيذي ومصفوفة مبيعات الأبراج (Tower Sales Brief Report)
        المحاور الرئيسية الثلاثة:
        1. الملخص التنفيذي ونسبة الإنجاز الميداني واستيعاب المخزون
        2. المحفظة البيعية بالعملة الوظيفية (EGP) والعملات الأجنبية المعزولة
        3. مصفوفة أداء فريق المبيعات وإغلاق الصفقات (Closer Matrix)
        """
        from real_estate.models import PropertyBlock, UnitBooking
        from financial.models.currency import Currency
        from cheques.models.allocation import ChequeInvoiceAllocation
        from cheques.models.cheque import ChequeStatus

        block = None
        project = None

        if block_id:
            block = PropertyBlock.objects.select_related('project').filter(pk=block_id).first()
            if block:
                project = block.project
                units_qs = PropertyUnit.objects.filter(block=block, is_active=True).select_related(
                    'floor', 'block', 'project'
                ).order_by('floor__floor_number', 'unit_code')
            else:
                units_qs = PropertyUnit.objects.none()
        elif project_id:
            project = RealEstateProject.objects.filter(pk=project_id).first()
            if project:
                units_qs = PropertyUnit.objects.filter(project=project, is_active=True).select_related(
                    'floor', 'block', 'project'
                ).order_by('block__name', 'floor__floor_number', 'unit_code')
            else:
                units_qs = PropertyUnit.objects.none()
        else:
            units_qs = PropertyUnit.objects.filter(is_active=True).select_related(
                'floor', 'block', 'project'
            ).order_by('project__name', 'block__name', 'floor__floor_number', 'unit_code')

        # 1. نسبة الإنجاز الإنشائي الميداني (Construction Progress)
        if block:
            construction_progress = block.construction_progress_percentage or Decimal('0.00')
        elif project:
            construction_progress = project.blocks.aggregate(avg=Avg('construction_progress_percentage'))['avg'] or Decimal('0.00')
        else:
            construction_progress = PropertyBlock.objects.aggregate(avg=Avg('construction_progress_percentage'))['avg'] or Decimal('0.00')
        construction_progress = Decimal(str(construction_progress)).quantize(Decimal('0.01'))

        # 2. حصر المخزون العقاري (Inventory Breakdown)
        total_units_count = units_qs.count()
        total_units_area = units_qs.aggregate(s=Sum('gross_area'))['s'] or Decimal('0.00')

        available_units = units_qs.filter(status=PropertyUnit.UnitStatus.AVAILABLE)
        available_count = available_units.count()
        available_area = available_units.aggregate(s=Sum('gross_area'))['s'] or Decimal('0.00')

        reserved_units = units_qs.filter(status=PropertyUnit.UnitStatus.RESERVED)
        reserved_count = reserved_units.count()
        reserved_area = reserved_units.aggregate(s=Sum('gross_area'))['s'] or Decimal('0.00')

        contracted_statuses = [
            PropertyUnit.UnitStatus.CONTRACTED,
            PropertyUnit.UnitStatus.DELIVERED,
            PropertyUnit.UnitStatus.DELIVERED_DEEMED
        ]
        contracted_units = units_qs.filter(status__in=contracted_statuses)
        contracted_count = contracted_units.count()
        contracted_area = contracted_units.aggregate(s=Sum('gross_area'))['s'] or Decimal('0.00')

        blocked_statuses = [
            PropertyUnit.UnitStatus.BLOCKED,
            PropertyUnit.UnitStatus.LANDOWNER_ALLOCATED
        ]
        blocked_units = units_qs.filter(status__in=blocked_statuses)
        blocked_count = blocked_units.count()
        blocked_area = blocked_units.aggregate(s=Sum('gross_area'))['s'] or Decimal('0.00')

        total_units_dec = Decimal(total_units_count) if total_units_count > 0 else Decimal('1')
        absorption_rate = (Decimal(contracted_count) / total_units_dec * Decimal('100.00')).quantize(Decimal('0.01')) if total_units_count > 0 else Decimal('0.00')
        reservation_rate = (Decimal(reserved_count) / total_units_dec * Decimal('100.00')).quantize(Decimal('0.01')) if total_units_count > 0 else Decimal('0.00')
        available_rate = (Decimal(available_count) / total_units_dec * Decimal('100.00')).quantize(Decimal('0.01')) if total_units_count > 0 else Decimal('0.00')

        # 3. المحفظة البيعية والمالية (Functional Currency & Foreign Isolations)
        contracts_qs = PropertyContract.objects.filter(
            unit__in=units_qs,
            status__in=[
                PropertyContract.ContractStatus.ACTIVE,
                PropertyContract.ContractStatus.COMPLETED,
            ]
        ).select_related('unit', 'customer', 'currency', 'created_by', 'visit_specialist')

        bookings_qs = UnitBooking.objects.filter(
            unit__in=units_qs,
            status=UnitBooking.BookingStatus.ACTIVE
        ).select_related('unit', 'customer', 'currency', 'created_by', 'visit_specialist')

        func_currency = Currency.objects.filter(is_functional=True).first()
        func_currency_code = func_currency.code if func_currency else 'EGP'

        total_contracted_sales_func = Decimal('0.00')
        total_down_payments_collected_func = Decimal('0.00')
        total_installments_collected_func = Decimal('0.00')
        total_active_holding_deposits_func = Decimal('0.00')
        total_cheques_in_vault_func = Decimal('0.00')

        foreign_currencies_map: Dict[str, Dict[str, Any]] = {}
        closers_map: Dict[Any, Dict[str, Any]] = {}

        def get_closer_entry(user_obj):
            key = user_obj.id if user_obj else 0
            if key not in closers_map:
                name = (user_obj.get_full_name() or user_obj.username) if user_obj else "غير محدد / بيع مباشر"
                username = user_obj.username if user_obj else "-"
                closers_map[key] = {
                    'user_id': key,
                    'name': name,
                    'username': username,
                    'contracts_count': 0,
                    'active_bookings_count': 0,
                    'total_sales_volume': Decimal('0.00'),
                    'total_collected': Decimal('0.00'),
                    'avg_deal_size': Decimal('0.00'),
                    'contribution_percentage': Decimal('0.00'),
                }
            return closers_map[key]

        vault_statuses = [ChequeStatus.IN_PORTFOLIO, ChequeStatus.UNDER_COLLECTION]

        # معالجة العقود السارية
        contracts_by_unit_id: Dict[int, PropertyContract] = {}
        for contract in contracts_qs:
            contracts_by_unit_id[contract.unit_id] = contract

            c_curr = contract.currency
            is_foreign = (c_curr is not None and not c_curr.is_functional)
            rate = c_curr.current_rate if is_foreign else Decimal('1.000000')

            price = contract.final_contract_price
            price_func = price * rate
            total_contracted_sales_func += price_func

            # المقدم المحصل المعتمد
            dp = ContractDebtClearanceService.get_verified_down_payment(contract)
            dp_func = dp * rate
            total_down_payments_collected_func += dp_func

            # الأقساط المحصلة
            inst_paid = Decimal('0.00')
            if contract.installment_plan_id:
                inst_paid = InstallmentItem.objects.filter(
                    plan_id=contract.installment_plan_id,
                    paid_amount__gt=Decimal('0.00')
                ).aggregate(s=Sum('paid_amount'))['s'] or Decimal('0.00')
            inst_paid_func = inst_paid * rate
            total_installments_collected_func += inst_paid_func

            # شيكات بالحافظة / برسم التحصيل
            chqs_val = Decimal('0.00')
            if contract.installment_plan_id:
                chqs_val = ChequeInvoiceAllocation.objects.filter(
                    installment_item__plan_id=contract.installment_plan_id,
                    cheque__status__in=vault_statuses
                ).aggregate(s=Sum('allocated_amount'))['s'] or Decimal('0.00')
            chqs_val_func = chqs_val * rate
            total_cheques_in_vault_func += chqs_val_func

            # تجميع أداء الـ Closer
            closer_user = contract.visit_specialist or contract.created_by
            closer_entry = get_closer_entry(closer_user)
            closer_entry['contracts_count'] += 1
            closer_entry['total_sales_volume'] += price_func
            closer_entry['total_collected'] += (dp_func + inst_paid_func)

            # عزل العملات الأجنبية
            if is_foreign:
                code = c_curr.code
                if code not in foreign_currencies_map:
                    foreign_currencies_map[code] = {
                        'currency_code': code,
                        'currency_name': c_curr.name,
                        'symbol': c_curr.symbol,
                        'exchange_rate': rate,
                        'contracts_count': 0,
                        'bookings_count': 0,
                        'foreign_contracted_amount': Decimal('0.00'),
                        'foreign_collected_amount': Decimal('0.00'),
                        'foreign_remaining_amount': Decimal('0.00'),
                        'functional_equivalent_sales': Decimal('0.00'),
                    }
                f_entry = foreign_currencies_map[code]
                f_entry['contracts_count'] += 1
                f_entry['foreign_contracted_amount'] += price
                f_entry['foreign_collected_amount'] += (dp + inst_paid)
                f_entry['foreign_remaining_amount'] += max(Decimal('0.00'), price - dp - inst_paid)
                f_entry['functional_equivalent_sales'] += price_func

        # معالجة استمارات الحجز السارية
        bookings_by_unit_id: Dict[int, UnitBooking] = {}
        for booking in bookings_qs:
            bookings_by_unit_id[booking.unit_id] = booking

            b_curr = booking.currency
            is_b_foreign = (b_curr is not None and not b_curr.is_functional)
            b_rate = b_curr.current_rate if is_b_foreign else Decimal('1.000000')

            deposit = booking.holding_deposit
            deposit_func = deposit * b_rate
            total_active_holding_deposits_func += deposit_func

            closer_user = booking.visit_specialist or booking.created_by
            closer_entry = get_closer_entry(closer_user)
            closer_entry['active_bookings_count'] += 1
            closer_entry['total_collected'] += deposit_func

            if is_b_foreign:
                code = b_curr.code
                if code not in foreign_currencies_map:
                    foreign_currencies_map[code] = {
                        'currency_code': code,
                        'currency_name': b_curr.name,
                        'symbol': b_curr.symbol,
                        'exchange_rate': b_rate,
                        'contracts_count': 0,
                        'bookings_count': 0,
                        'foreign_contracted_amount': Decimal('0.00'),
                        'foreign_collected_amount': Decimal('0.00'),
                        'foreign_remaining_amount': Decimal('0.00'),
                        'functional_equivalent_sales': Decimal('0.00'),
                    }
                f_entry = foreign_currencies_map[code]
                f_entry['bookings_count'] += 1
                f_entry['foreign_collected_amount'] += deposit

        total_collected_liquidity_func = (
            total_down_payments_collected_func +
            total_active_holding_deposits_func +
            total_installments_collected_func
        )
        total_remaining_receivables_func = max(
            Decimal('0.00'),
            total_contracted_sales_func - total_down_payments_collected_func - total_installments_collected_func
        )
        total_pipeline_value_func = total_contracted_sales_func + total_active_holding_deposits_func
        collection_efficiency_rate = (
            (total_collected_liquidity_func / total_pipeline_value_func * Decimal('100.00')).quantize(Decimal('0.01'))
            if total_pipeline_value_func > Decimal('0.00') else Decimal('0.00')
        )

        # حساب متوسط حجم الصفقة ونسبة المساهمة لفريق المبيعات
        closer_matrix = list(closers_map.values())
        for c in closer_matrix:
            if c['contracts_count'] > 0:
                c['avg_deal_size'] = (c['total_sales_volume'] / Decimal(c['contracts_count'])).quantize(Decimal('0.01'))
            if total_contracted_sales_func > Decimal('0.00'):
                c['contribution_percentage'] = (c['total_sales_volume'] / total_contracted_sales_func * Decimal('100.00')).quantize(Decimal('0.01'))
        closer_matrix.sort(key=lambda x: x['total_sales_volume'], reverse=True)

        # 4. بناء مصفوفة الوحدات التفصيلية (Unit Matrix Grid)
        unit_rows: List[Dict[str, Any]] = []
        for unit in units_qs:
            contract_obj = contracts_by_unit_id.get(unit.id)
            booking_obj = bookings_by_unit_id.get(unit.id)

            customer_name = "-"
            doc_number = "-"
            deal_date = None
            closer_display = "-"
            deal_value = Decimal('0.00')

            if contract_obj:
                customer_name = contract_obj.customer.name
                doc_number = contract_obj.contract_number
                deal_date = contract_obj.contract_date
                deal_value = contract_obj.final_contract_price
                c_u = contract_obj.visit_specialist or contract_obj.created_by
                closer_display = (c_u.get_full_name() or c_u.username) if c_u else "-"
            elif booking_obj:
                customer_name = booking_obj.customer.name
                doc_number = booking_obj.booking_number
                deal_date = booking_obj.booking_date
                deal_value = booking_obj.holding_deposit
                b_u = booking_obj.visit_specialist or booking_obj.created_by
                closer_display = (b_u.get_full_name() or b_u.username) if b_u else "-"

            unit_rows.append({
                'unit': unit,
                'unit_code': unit.unit_code,
                'block_name': unit.block.name if unit.block else "-",
                'floor_name': unit.floor.name if unit.floor else f"الدور {unit.floor.floor_number}" if unit.floor else "-",
                'unit_type': unit.get_unit_type_display(),
                'net_area': unit.net_area,
                'gross_area': unit.gross_area,
                'base_price': unit.base_price,
                'status': unit.status,
                'status_display': unit.get_status_display(),
                'customer_name': customer_name,
                'doc_number': doc_number,
                'deal_date': deal_date,
                'deal_value': deal_value,
                'closer_name': closer_display,
            })

        return {
            'target_block': block,
            'target_project': project,
            'construction_progress': construction_progress,
            'func_currency_code': func_currency_code,

            # إحصائيات المخزون
            'total_units_count': total_units_count,
            'total_units_area': total_units_area,
            'available_count': available_count,
            'available_area': available_area,
            'available_rate': available_rate,
            'reserved_count': reserved_count,
            'reserved_area': reserved_area,
            'reservation_rate': reservation_rate,
            'contracted_count': contracted_count,
            'contracted_area': contracted_area,
            'absorption_rate': absorption_rate,
            'blocked_count': blocked_count,
            'blocked_area': blocked_area,

            # المؤشرات المالية بالعملة الوظيفية
            'total_contracted_sales_func': total_contracted_sales_func,
            'total_down_payments_collected_func': total_down_payments_collected_func,
            'total_active_holding_deposits_func': total_active_holding_deposits_func,
            'total_installments_collected_func': total_installments_collected_func,
            'total_cheques_in_vault_func': total_cheques_in_vault_func,
            'total_collected_liquidity_func': total_collected_liquidity_func,
            'total_remaining_receivables_func': total_remaining_receivables_func,
            'total_pipeline_value_func': total_pipeline_value_func,
            'collection_efficiency_rate': collection_efficiency_rate,

            # العملات الأجنبية وفريق البيع
            'foreign_currencies': list(foreign_currencies_map.values()),
            'closer_matrix': closer_matrix,
            'unit_rows': unit_rows,
        }
