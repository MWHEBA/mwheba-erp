# -*- coding: utf-8 -*-
"""
Real Estate Administration Dashboard Configuration
MWHEBA ERP — Real Estate App Admin
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from real_estate.models import (
    RealEstateProject,
    PropertyBlock,
    PropertyFloor,
    PropertyUnit,
    UnitBooking,
    PropertyContract,
    ContractCoOwner,
    ContractorProgressCertificate,
    LegalNotice,
    RealEstateBroker,
    BrokerCommission,
    UnitPricingMatrixConfig,
    LandownerPartnership,
    LandownerUnitAllocation,
    LandownerRevenueShareAccrual,
    ClientVariationOrder,
    UnitSnagItem,
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


@admin.register(ContractorProgressCertificate)
class ContractorProgressCertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_number', 'project', 'contractor', 'status', 'gross_certified_work', 'net_amount', 'period_end')
    list_filter = ('status', 'project', 'period_end')
    search_fields = ('certificate_number', 'contractor__name', 'project__name')
    readonly_fields = ('approval_snapshot_hash', 'current_period_work', 'retention_amount', 'wht_amount', 'net_amount', 'version')


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
