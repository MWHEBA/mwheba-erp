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

from django.db.models import Sum, Count, Q
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

            if is_delivered:
                revenue_status = 'RECOGNIZED'
                recognized_rev = contract.final_contract_price
                deferred_liab = Decimal('0.00')
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
            recognized_revenue = sum(
                (h.contract.final_contract_price for h in executed_handovers),
                Decimal('0.00')
            )
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
