# -*- coding: utf-8 -*-
"""
Real Estate Administration Dashboard Configuration
MWHEBA ERP — Real Estate App Admin
"""
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
    PropertyContract,
    ContractCoOwner,
    MilestoneInstallmentLink,
    MilestoneCollectionAlert,
    ContractorProgressCertificate,
    ProjectMasterBOQItem,
    ContractorContract,
    SectionalHandoverRecord,
    ContractorContractItem,
    ContractVariationOrder,
    ContractVariationOrderItem,
    ContractorDefaultNotice,
    ContractorCertificateItem,
    EquipmentHoistingLog,
    SiteDebrisClearanceLog,
    ContractorMaterialOnSite,
    ContractorMOSCustodyReceipt,
    ContractorBackcharge,
    ConcreteBatchDelivery,
    ConcreteBatchReconciliation,
    ContractorMaterialDeduction,
    RebarConsumptionLog,
    ContractorScaffoldingLog,
    DewateringPumpingLog,
    ContractorSupplierLienAssignment,
    ThirdPartyLabTestLog,
    ContractorSuspensionClaim,
    JointTerminationSurveyProtocol,
    RockExcavationSurveyLog,
    HydrostaticTestFailureLog,
    CertificatePaymentInstallmentSchedule,
    LegalNotice,
    RealEstateBroker,
    BrokerCommission,
    UnitPricingMatrixConfig,
    LandownerPartnership,
    LandownerUnitAllocation,
    LandownerRevenueShareAccrual,
    ClientVariationOrder,
    UnitSnagItem,
    ProjectActivity,
    SiteDailyLog,
    UnitSiteProgressRecord,
    SiteProgressAuditLog,
    PropertyHandoverReceipt,
    BuildingFacilitySubledger,
    MaintenanceFundOperation,
    SupplementalLevyApportionment,
    WarrantyTicket,
    UnitSwapRecord,
    ContractAssignmentEndorsement,
    SharedInfrastructureAsset,
    SharedInfrastructureApportionment,
    InfrastructureApportionmentLine,
    AsBuiltSurveyAdjustment,
    ResaleContingentRefund,
)


@admin.register(RealEstateProject)
class RealEstateProjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'project_type', 'status', 'start_date', 'expected_completion_date', 'is_archived')
    list_filter = ('project_type', 'status', 'is_archived')
    search_fields = ('code', 'name')
    date_hierarchy = 'start_date'


@admin.register(PropertyBlock)
class PropertyBlockAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'project', 'total_floors', 'is_active')
    list_filter = ('project', 'is_active')
    search_fields = ('code', 'name')


@admin.register(PropertyFloor)
class PropertyFloorAdmin(admin.ModelAdmin):
    list_display = ('floor_number', 'name', 'block', 'floor_type')
    list_filter = ('floor_type', 'block__project')
    search_fields = ('name', 'block__name')


@admin.register(PropertyUnit)
class PropertyUnitAdmin(admin.ModelAdmin):
    list_display = ('unit_code', 'project', 'unit_type', 'status', 'gross_area', 'meter_price', 'total_price')
    list_filter = ('status', 'unit_type', 'project')
    search_fields = ('unit_code', 'project__name')


@admin.register(UnitBooking)
class UnitBookingAdmin(admin.ModelAdmin):
    list_display = ('booking_number', 'unit', 'customer', 'status', 'booking_date', 'expiry_date', 'holding_deposit')
    list_filter = ('status', 'booking_date')
    search_fields = ('booking_number', 'customer__name', 'unit__unit_code')


class ContractCoOwnerInline(admin.TabularInline):
    model = ContractCoOwner
    extra = 1


@admin.register(PropertyContract)
class PropertyContractAdmin(admin.ModelAdmin):
    list_display = ('contract_number', 'project', 'unit', 'customer', 'status', 'final_contract_price', 'contract_date')
    list_filter = ('status', 'revenue_recognition_method', 'contract_date')
    search_fields = ('contract_number', 'customer__name', 'unit__unit_code')
    inlines = [ContractCoOwnerInline]


# ==============================================================================
# CONTRACTOR & CONSTRUCTION CONTRACT ADMIN
# ==============================================================================

class ContractorContractItemInline(admin.TabularInline):
    model = ContractorContractItem
    extra = 0


class ContractVariationOrderInline(admin.TabularInline):
    model = ContractVariationOrder
    extra = 0


@admin.register(ProjectMasterBOQItem)
class ProjectMasterBOQItemAdmin(admin.ModelAdmin):
    list_display = ('item_code', 'project', 'block', 'wbs_group', 'description', 'unit', 'master_budget_quantity', 'unit_rate_estimate', 'total_budget_cost')
    list_filter = ('project', 'wbs_group')
    search_fields = ('item_code', 'description')


@admin.register(ContractorContract)
class ContractorContractAdmin(admin.ModelAdmin):
    list_display = ('contract_number', 'title', 'project', 'contractor', 'contract_type', 'initial_contract_value', 'revised_contract_value', 'status', 'start_date', 'completion_date')
    list_filter = ('status', 'contract_type', 'project', 'is_assigned_to_bank', 'is_garnished_by_court')
    search_fields = ('contract_number', 'title', 'contractor__name', 'project__name')
    inlines = [ContractorContractItemInline, ContractVariationOrderInline]


@admin.register(SectionalHandoverRecord)
class SectionalHandoverRecordAdmin(admin.ModelAdmin):
    list_display = ('contract', 'section_name', 'handover_date', 'warranty_start_date', 'warranty_end_date', 'is_warranty_completed')
    list_filter = ('is_warranty_completed', 'handover_date')
    search_fields = ('section_name', 'contract__contract_number')


class ContractVariationOrderItemInline(admin.TabularInline):
    model = ContractVariationOrderItem
    extra = 0


@admin.register(ContractVariationOrder)
class ContractVariationOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'contract', 'variation_type', 'net_value_impact', 'approved_additional_days', 'status', 'created_at')
    list_filter = ('status', 'variation_type', 'created_at')
    search_fields = ('order_number', 'contract__contract_number', 'description')
    inlines = [ContractVariationOrderItemInline]


@admin.register(ContractorDefaultNotice)
class ContractorDefaultNoticeAdmin(admin.ModelAdmin):
    list_display = ('notice_number', 'contract', 'notice_date', 'cure_deadline', 'is_cured', 'is_penalty_authorized')
    list_filter = ('is_cured', 'is_penalty_authorized', 'notice_date')
    search_fields = ('notice_number', 'contract__contract_number')


class ContractorCertificateItemInline(admin.TabularInline):
    model = ContractorCertificateItem
    extra = 0


class CertificatePaymentInstallmentScheduleInline(admin.TabularInline):
    model = CertificatePaymentInstallmentSchedule
    extra = 0


@admin.register(ContractorProgressCertificate)
class ContractorProgressCertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_number', 'project', 'contractor', 'status', 'certificate_type', 'gross_certified_work', 'net_amount', 'period_end')
    list_filter = ('status', 'certificate_type', 'project', 'period_end')
    search_fields = ('certificate_number', 'contractor__name', 'project__name')
    readonly_fields = ('approval_snapshot_hash', 'current_period_work', 'retention_amount', 'wht_amount', 'net_amount', 'version')
    inlines = [ContractorCertificateItemInline, CertificatePaymentInstallmentScheduleInline]


@admin.register(EquipmentHoistingLog)
class EquipmentHoistingLogAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'equipment_code', 'equipment_name', 'operating_date', 'operating_hours', 'hourly_rate', 'total_charge')
    list_filter = ('operating_date',)
    search_fields = ('equipment_code', 'equipment_name')


@admin.register(SiteDebrisClearanceLog)
class SiteDebrisClearanceLogAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'trip_ticket_number', 'clearance_date', 'truck_capacity_m3', 'trip_cost', 'total_clearance_charge')
    list_filter = ('clearance_date',)
    search_fields = ('trip_ticket_number',)


@admin.register(ContractorMaterialOnSite)
class ContractorMaterialOnSiteAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'item_name', 'unit', 'surveyed_quantity', 'invoice_unit_cost', 'total_material_value', 'advance_financing_rate', 'approved_advance_amount', 'is_fully_unwound')
    list_filter = ('is_fully_unwound',)
    search_fields = ('item_name',)


@admin.register(ContractorMOSCustodyReceipt)
class ContractorMOSCustodyReceiptAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'mos_item', 'vesting_date', 'is_vested_in_employer', 'gate_exit_locked')
    list_filter = ('is_vested_in_employer', 'gate_exit_locked', 'vesting_date')
    search_fields = ('receipt_number',)


@admin.register(ContractorBackcharge)
class ContractorBackchargeAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'beneficiary_contractor', 'reason', 'memo_reference', 'amount')
    search_fields = ('memo_reference', 'reason')


@admin.register(ConcreteBatchDelivery)
class ConcreteBatchDeliveryAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'delivery_note_number', 'delivery_date', 'casting_location', 'batch_volume_m3', 'is_batch_rejected', 'is_sample_passed')
    list_filter = ('is_batch_rejected', 'is_sample_passed', 'delivery_date')
    search_fields = ('delivery_note_number', 'casting_location')


@admin.register(ConcreteBatchReconciliation)
class ConcreteBatchReconciliationAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'casting_subcontractor', 'element_description', 'surveyed_as_built_volume_m3', 'actual_batch_delivered_volume_m3', 'excess_waste_volume_m3', 'excess_waste_backcharge_amount')
    list_filter = ('casting_subcontractor',)
    search_fields = ('element_description',)


@admin.register(ContractorMaterialDeduction)
class ContractorMaterialDeductionAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'store_issue_voucher', 'issue_date', 'item_name', 'quantity', 'total_deduction', 'pricing_policy', 'material_price_variance_amount')
    list_filter = ('pricing_policy', 'is_excess_scrap_penalty', 'issue_date')
    search_fields = ('store_issue_voucher', 'item_name')


@admin.register(RebarConsumptionLog)
class RebarConsumptionLogAdmin(admin.ModelAdmin):
    list_display = ('project', 'contract', 'element_name', 'rebar_diameter_mm', 'bbs_theoretical_weight_tons', 'actual_delivered_weight_tons', 'excess_waste_weight_tons', 'excess_waste_backcharge_amount')
    list_filter = ('project', 'contract')
    search_fields = ('element_name',)


@admin.register(ContractorScaffoldingLog)
class ContractorScaffoldingLogAdmin(admin.ModelAdmin):
    list_display = ('contract', 'certificate', 'equipment_type', 'delivered_quantity', 'returned_good_quantity', 'damaged_quantity', 'total_damage_deduction', 'log_date')
    list_filter = ('log_date',)
    search_fields = ('equipment_type',)


@admin.register(DewateringPumpingLog)
class DewateringPumpingLogAdmin(admin.ModelAdmin):
    list_display = ('contract', 'certificate', 'log_date', 'pumps_operating_count', 'daily_running_hours', 'breakdown_hours', 'total_stoppage_penalty', 'diesel_total_backcharge')
    list_filter = ('log_date',)


@admin.register(ContractorSupplierLienAssignment)
class ContractorSupplierLienAssignmentAdmin(admin.ModelAdmin):
    list_display = ('agreement_reference', 'contract', 'contractor', 'material_supplier', 'total_lien_amount', 'remaining_balance', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('agreement_reference', 'material_supplier__name')


@admin.register(ThirdPartyLabTestLog)
class ThirdPartyLabTestLogAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'contract', 'lab_name', 'invoice_number', 'test_type', 'test_date', 'is_test_passed', 'total_invoice_amount', 'is_backcharged_to_contractor')
    list_filter = ('test_type', 'is_test_passed', 'is_backcharged_to_contractor', 'test_date')
    search_fields = ('lab_name', 'invoice_number', 'tested_element')


@admin.register(ContractorSuspensionClaim)
class ContractorSuspensionClaimAdmin(admin.ModelAdmin):
    list_display = ('suspension_order_reference', 'contract', 'certificate', 'start_date', 'end_date', 'idle_days_count', 'total_approved_claim_amount', 'is_approved_by_cfo')
    list_filter = ('is_approved_by_cfo',)
    search_fields = ('suspension_order_reference',)


@admin.register(JointTerminationSurveyProtocol)
class JointTerminationSurveyProtocolAdmin(admin.ModelAdmin):
    list_display = ('protocol_reference', 'contract', 'survey_date', 'as_built_completed_value', 'uninstalled_materials_value', 'snag_and_remedial_costs', 'site_vacated_and_handed_over')
    list_filter = ('site_vacated_and_handed_over', 'survey_date')
    search_fields = ('protocol_reference', 'court_expert_minutes_number')


@admin.register(RockExcavationSurveyLog)
class RockExcavationSurveyLogAdmin(admin.ModelAdmin):
    list_display = ('grid_location_reference', 'contract', 'certificate', 'survey_date', 'solid_rock_volume_m3', 'breaker_operating_hours')
    list_filter = ('survey_date',)
    search_fields = ('grid_location_reference',)


@admin.register(HydrostaticTestFailureLog)
class HydrostaticTestFailureLogAdmin(admin.ModelAdmin):
    list_display = ('network_segment', 'contract', 'certificate', 'test_date', 'tested_pressure_bar', 'pressure_drop_bar', 'total_remedial_backcharge')
    list_filter = ('test_date',)
    search_fields = ('network_segment', 'leak_location')


@admin.register(LegalNotice)
class LegalNoticeAdmin(admin.ModelAdmin):
    list_display = ('notice_number', 'contract', 'customer', 'stage', 'channel', 'status', 'total_demanded_amount', 'sent_at')
    list_filter = ('stage', 'channel', 'status')
    search_fields = ('notice_number', 'customer__name', 'contract__contract_number')
    readonly_fields = ('verification_token', 'meta_payload', 'meta_message_id', 'total_demanded_amount')


@admin.register(RealEstateBroker)
class RealEstateBrokerAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'broker_type', 'default_commission_rate', 'is_active')
    list_filter = ('broker_type', 'is_active')
    search_fields = ('code', 'name', 'phone')


@admin.register(BrokerCommission)
class BrokerCommissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'broker', 'contract', 'commission_rate', 'total_commission_amount', 'tranche_1_status', 'tranche_2_status')
    list_filter = ('tranche_1_status', 'tranche_2_status')
    search_fields = ('broker__name', 'contract__contract_number')


@admin.register(UnitPricingMatrixConfig)
class UnitPricingMatrixConfigAdmin(admin.ModelAdmin):
    list_display = ('project', 'base_meter_price', 'floor_rise_rate', 'is_active')
    list_filter = ('is_active', 'project')


class LandownerUnitAllocationInline(admin.TabularInline):
    model = LandownerUnitAllocation
    extra = 1


@admin.register(LandownerPartnership)
class LandownerPartnershipAdmin(admin.ModelAdmin):
    list_display = ('partnership_number', 'project', 'partner_name', 'partnership_type', 'revenue_share_percentage', 'status')
    list_filter = ('partnership_type', 'status', 'project')
    search_fields = ('partnership_number', 'partner_name', 'project__name')
    inlines = [LandownerUnitAllocationInline]


@admin.register(LandownerUnitAllocation)
class LandownerUnitAllocationAdmin(admin.ModelAdmin):
    list_display = ('partnership', 'unit', 'handover_status', 'allocated_at')
    list_filter = ('handover_status', 'partnership__project')
    search_fields = ('partnership__partner_name', 'unit__unit_code')


@admin.register(LandownerRevenueShareAccrual)
class LandownerRevenueShareAccrualAdmin(admin.ModelAdmin):
    list_display = ('accrual_number', 'partnership', 'contract', 'collected_amount', 'share_percentage', 'accrued_amount', 'status')
    list_filter = ('status', 'partnership')
    search_fields = ('accrual_number', 'partnership__partner_name', 'contract__contract_number')
    readonly_fields = ('accrued_amount', 'accrual_number')


@admin.register(ClientVariationOrder)
class ClientVariationOrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'unit', 'contract', 'variation_type', 'stage_at_request', 'total_cost', 'status')
    list_filter = ('status', 'variation_type', 'stage_at_request')
    search_fields = ('order_number', 'unit__unit_code', 'contract__contract_number', 'title')
    readonly_fields = ('total_cost',)


@admin.register(UnitSnagItem)
class UnitSnagItemAdmin(admin.ModelAdmin):
    list_display = ('snag_code', 'unit', 'room_location', 'category', 'severity', 'status', 'created_at')
    list_filter = ('status', 'severity', 'category')
    search_fields = ('snag_code', 'unit__unit_code', 'room_location', 'description')
    readonly_fields = ('client_snag_uuid', 'snag_code')


@admin.register(PropertyHandoverReceipt)
class PropertyHandoverReceiptAdmin(admin.ModelAdmin):
    list_display = (
        'receipt_number',
        'unit',
        'contract',
        'handover_type',
        'status',
        'handover_date',
        'recognized_revenue_amount',
        'interim_cogs_amount',
    )
    list_filter = ('status', 'handover_type', 'handover_date')
    search_fields = (
        'receipt_number',
        'unit__unit_code',
        'contract__contract_number',
        'client_signatory_name',
    )
    readonly_fields = (
        'receipt_number',
        'verification_hash',
        'public_token',
        'executed_at',
        'created_at',
        'updated_at',
    )



@admin.register(BuildingFacilitySubledger)
class BuildingFacilitySubledgerAdmin(admin.ModelAdmin):
    list_display = (
        'project',
        'current_fund_balance',
        'total_collected_deposits',
        'total_yield_accumulated',
        'total_expenses_disbursed',
        'is_active',
    )
    list_filter = ('is_active',)
    search_fields = ('project__name', 'project__code')
    readonly_fields = (
        'current_fund_balance',
        'total_collected_deposits',
        'total_yield_accumulated',
        'total_expenses_disbursed',
        'created_at',
        'updated_at',
    )


@admin.register(MaintenanceFundOperation)
class MaintenanceFundOperationAdmin(admin.ModelAdmin):
    list_display = (
        'operation_number',
        'subledger',
        'operation_type',
        'amount',
        'operation_date',
        'expense_category',
        'bank_certificate_number',
    )
    list_filter = ('operation_type', 'expense_category', 'operation_date')
    search_fields = ('operation_number', 'subledger__project__name', 'description')
    readonly_fields = ('operation_number', 'created_at', 'updated_at')


@admin.register(SupplementalLevyApportionment)
class SupplementalLevyApportionmentAdmin(admin.ModelAdmin):
    list_display = (
        'operation',
        'unit',
        'customer',
        'unit_gross_area',
        'share_percentage',
        'apportioned_amount',
        'is_settled',
    )
    list_filter = ('is_settled', 'operation__operation_date')
    search_fields = ('unit__unit_code', 'customer__name', 'operation__operation_number')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WarrantyTicket)
class WarrantyTicketAdmin(admin.ModelAdmin):
    list_display = (
        'ticket_number',
        'unit',
        'category',
        'priority',
        'status',
        'responsible_contractor',
        'actual_repair_cost',
        'contractor_sla_deadline',
        'created_at',
    )
    list_filter = ('status', 'priority', 'category', 'warranty_type')
    search_fields = (
        'ticket_number',
        'unit__unit_code',
        'responsible_contractor__name',
        'title',
    )
    readonly_fields = (
        'ticket_number',
        'inspected_at',
        'closed_at',
        'created_at',
        'updated_at',
    )


@admin.register(UnitSwapRecord)
class UnitSwapRecordAdmin(admin.ModelAdmin):
    list_display = (
        'swap_number',
        'contract',
        'customer',
        'old_unit',
        'new_unit',
        'price_difference',
        'administrative_fee',
        'status',
        'swap_date',
    )
    list_filter = ('status', 'settlement_method', 'swap_date')
    search_fields = (
        'swap_number',
        'contract__contract_number',
        'customer__name',
        'old_unit__unit_code',
        'new_unit__unit_code',
    )
    readonly_fields = (
        'swap_number',
        'price_difference',
        'executed_at',
        'created_at',
        'updated_at',
    )



@admin.register(ContractAssignmentEndorsement)
class ContractAssignmentEndorsementAdmin(admin.ModelAdmin):
    list_display = (
        'assignment_number',
        'contract',
        'assignor_customer',
        'assignee_customer',
        'paid_amount_at_assignment',
        'administrative_fee',
        'status',
        'assignment_date',
    )
    list_filter = ('status', 'fee_payer', 'assignment_date')
    search_fields = (
        'assignment_number',
        'contract__contract_number',
        'assignor_customer__name',
        'assignee_customer__name',
        'verification_token',
    )
    readonly_fields = (
        'assignment_number',
        'verification_token',
        'paid_amount_at_assignment',
        'remaining_balance_at_assignment',
        'executed_at',
        'created_at',
        'updated_at',
    )


class InfrastructureApportionmentLineInline(admin.TabularInline):
    model = InfrastructureApportionmentLine
    extra = 0


@admin.register(SharedInfrastructureAsset)
class SharedInfrastructureAssetAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'infrastructure_type', 'total_capacity_load', 'accumulated_wip_cost', 'apportioned_wip_cost', 'is_active')
    list_filter = ('infrastructure_type', 'is_active')
    search_fields = ('code', 'name', 'compound_name')


@admin.register(SharedInfrastructureApportionment)
class SharedInfrastructureApportionmentAdmin(admin.ModelAdmin):
    list_display = ('apportionment_number', 'infrastructure_asset', 'allocation_basis', 'total_apportioned_amount', 'status', 'apportionment_date')
    list_filter = ('allocation_basis', 'status', 'apportionment_date')
    search_fields = ('apportionment_number', 'infrastructure_asset__name')
    inlines = [InfrastructureApportionmentLineInline]


@admin.register(AsBuiltSurveyAdjustment)
class AsBuiltSurveyAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('adjustment_number', 'unit', 'contract_gross_area', 'surveyed_gross_area', 'area_variance', 'financial_variance', 'adjustment_type', 'status')
    list_filter = ('adjustment_type', 'status')
    search_fields = ('adjustment_number', 'unit__unit_code', 'contract__contract_number')


@admin.register(ResaleContingentRefund)
class ResaleContingentRefundAdmin(admin.ModelAdmin):
    list_display = ('refund_number', 'customer', 'unit', 'total_paid_before_cancellation', 'cancellation_penalty_amount', 'net_refundable_amount', 'status')
    list_filter = ('status',)
    search_fields = ('refund_number', 'customer__name', 'unit__unit_code')


# ==============================================================================
# Track 3: إدارات شجرة WBS ويوميات الموقع ومصفوفة البنود وسجلات التدقيق
# ==============================================================================

@admin.register(ProjectActivity)
class ProjectActivityAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'project', 'block', 'weight_percentage', 'progress_percentage', 'activity_type', 'is_milestone', 'auto_sync_progress', 'is_baseline_locked')
    list_filter = ('project', 'activity_type', 'trade_category', 'is_milestone', 'auto_sync_progress', 'is_baseline_locked')
    search_fields = ('code', 'name', 'project__name')
    ordering = ('project', 'code')


@admin.register(SiteDailyLog)
class SiteDailyLogAdmin(admin.ModelAdmin):
    list_display = ('project', 'log_date', 'weather', 'total_manpower_count', 'stoppage_reason', 'delays_recorded_hours', 'recorded_by')
    list_filter = ('weather', 'stoppage_reason', 'log_date', 'project')
    search_fields = ('project__name', 'notes')
    date_hierarchy = 'log_date'


@admin.register(UnitSiteProgressRecord)
class UnitSiteProgressRecordAdmin(admin.ModelAdmin):
    list_display = ('unit', 'trade_stage', 'status', 'completion_percentage', 'contractor', 'rfi_number', 'is_billed', 'version')
    list_filter = ('status', 'trade_stage', 'is_billed', 'is_applicable')
    search_fields = ('unit__unit_code', 'rfi_number', 'notes')


@admin.register(SiteProgressAuditLog)
class SiteProgressAuditLogAdmin(admin.ModelAdmin):
    list_display = ('unit_code_snapshot', 'trade_stage', 'previous_percentage', 'new_percentage', 'previous_status', 'new_status', 'changed_by', 'timestamp')
    list_filter = ('trade_stage', 'timestamp')
    search_fields = ('unit_code_snapshot', 'defect_notes')
    readonly_fields = (
        'unit',
        'unit_code_snapshot',
        'trade_stage',
        'previous_percentage',
        'new_percentage',
        'previous_status',
        'new_status',
        'defect_notes',
        'changed_by',
        'timestamp',
    )

    def delete_queryset(self, request, queryset):
        raise ValidationError(_('سجلات تدقيق متابعة الموقع غير قابلة للحذف نهائياً (Audit Trail Immutable).'))

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MilestoneInstallmentLink)
class MilestoneInstallmentLinkAdmin(admin.ModelAdmin):
    list_display = ('contract', 'installment_item', 'milestone_activity', 'is_triggered', 'triggered_at', 'created_at')
    list_filter = ('is_triggered', 'created_at')
    search_fields = ('contract__contract_number', 'milestone_activity__name', 'milestone_activity__code')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MilestoneCollectionAlert)
class MilestoneCollectionAlertAdmin(admin.ModelAdmin):
    list_display = ('contract', 'customer', 'milestone_activity', 'installment_amount', 'due_date', 'status', 'notified_at')
    list_filter = ('status', 'notified_at')
    search_fields = ('contract__contract_number', 'customer__name', 'milestone_activity__name')
    readonly_fields = ('notified_at', 'updated_at')


