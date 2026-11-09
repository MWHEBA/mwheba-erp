# -*- coding: utf-8 -*-
from django.urls import path
from real_estate.views import (
    dashboard_views,
    project_views,
    unit_views,
    booking_views,
    contract_views,
    matrix_views,
    pricing_views,
    contractor_views,
    contractor_contract_views,
    broker_views,
    engineering_views,
    service_views,
    operations_views,
    report_views,
    finishing_views,
)

app_name = 'real_estate'

urlpatterns = [
    # Dashboard (لوحة المؤشرات العقارية)
    path('', dashboard_views.RealEstateDashboardView.as_view(), name='dashboard'),

    # Projects (المشروعات العقارية)
    path('projects/', project_views.ProjectListView.as_view(), name='project_list'),
    path('projects/create/', project_views.ProjectCreateView.as_view(), name='project_create'),
    path('projects/<int:pk>/', project_views.ProjectDetailView.as_view(), name='project_detail'),
    path('projects/<int:pk>/edit/', project_views.ProjectUpdateView.as_view(), name='project_update'),

    # Visual Unit Matrix (المصفوفة المعمارية التفاعلية)
    path('projects/<int:project_id>/matrix/', matrix_views.ProjectMatrixView.as_view(), name='project_matrix'),

    # Units (الوحدات العقارية)
    path('units/', unit_views.UnitListView.as_view(), name='unit_list'),
    path('units/create/', unit_views.UnitCreateView.as_view(), name='unit_create'),
    path('units/<int:pk>/', unit_views.UnitDetailView.as_view(), name='unit_detail'),
    path('units/<int:pk>/edit/', unit_views.UnitUpdateView.as_view(), name='unit_update'),

    # Bookings (استمارات الحجز)
    path('bookings/', booking_views.BookingListView.as_view(), name='booking_list'),
    path('bookings/<int:pk>/', booking_views.BookingDetailView.as_view(), name='booking_detail'),
    path('bookings/<int:pk>/print/', booking_views.BookingOfficialPrintView.as_view(), name='booking_print'),
    path('verify-booking/<uuid:token>/', booking_views.BookingPublicVerificationView.as_view(), name='booking_public_verify'),

    # Contracts (عقود البيع الرسمية)
    path('contracts/', contract_views.ContractListView.as_view(), name='contract_list'),
    path('contracts/create/', contract_views.ContractCreateView.as_view(), name='contract_create'),
    path('contracts/<int:pk>/', contract_views.ContractDetailView.as_view(), name='contract_detail'),
    path('contracts/<int:pk>/print/', contract_views.ContractOfficialPrintView.as_view(), name='contract_print'),
    path('contracts/<int:pk>/statement/print/', contract_views.ContractStatementPrintView.as_view(), name='contract_statement_print'),
    path('contracts/<int:pk>/clearance/print/', contract_views.ContractDebtClearancePrintView.as_view(), name='contract_clearance_print'),

    # Brokers & Commissions (الوسطاء والمسوقين العقاريين)
    path('brokers/', broker_views.BrokerListView.as_view(), name='broker_list'),
    path('brokers/create/', broker_views.BrokerCreateView.as_view(), name='broker_create'),
    path('brokers/<int:pk>/', broker_views.BrokerDetailView.as_view(), name='broker_detail'),
    path('brokers/<int:pk>/edit/', broker_views.BrokerUpdateView.as_view(), name='broker_update'),
    path('commissions/', broker_views.BrokerCommissionListView.as_view(), name='commission_list'),
    path('commissions/<int:pk>/evaluate/', broker_views.BrokerCommissionEvaluateView.as_view(), name='commission_evaluate'),
    path('commissions/<int:pk>/payout/', broker_views.BrokerCommissionPayoutView.as_view(), name='commission_payout'),
    path('contracts/<int:contract_id>/assign-broker/', broker_views.BrokerAssignContractView.as_view(), name='contract_assign_broker'),

    # Contractor Subcontracts (عقود مقاولي الباطن والمقايسات)
    path('contractors/contracts/', contractor_contract_views.ContractorContractListView.as_view(), name='contractor_contract_list'),
    path('contractors/contracts/create/', contractor_contract_views.ContractorContractCreateView.as_view(), name='contractor_contract_create'),
    path('contractors/contracts/<int:pk>/', contractor_contract_views.ContractorContractDetailView.as_view(), name='contractor_contract_detail'),
    path('contractors/contracts/<int:pk>/edit/', contractor_contract_views.ContractorContractUpdateView.as_view(), name='contractor_contract_update'),
    path('contractors/contracts/<int:pk>/advance/disburse/', contractor_contract_views.ContractorContractDisburseAdvanceView.as_view(), name='contractor_contract_disburse_advance'),
    path('contractors/contracts/<int:pk>/variations/create/', contractor_contract_views.ContractorContractVariationOrderCreateView.as_view(), name='contractor_contract_variation_create'),
    path('contractors/contracts/<int:pk>/terminate/', contractor_contract_views.ContractorContractTerminateView.as_view(), name='contractor_contract_terminate'),
    path('contractors/contracts/<int:contract_id>/retention/release/', contractor_views.ContractorCertificateRetentionReleaseView.as_view(), name='contractor_retention_release'),
    path('api/contractors/contracts/<int:contract_id>/items/', contractor_contract_views.ApiContractorContractItemsView.as_view(), name='api_contractor_contract_items'),

    # Contractors Progress Certificates (مستخلصات المقاولين الإنشائية)
    path('contractors/certificates/', contractor_views.ContractorCertificateListView.as_view(), name='contractor_list'),
    path('contractors/certificates/create/', contractor_views.ContractorCertificateCreateView.as_view(), name='contractor_create'),
    path('contractors/certificates/<int:pk>/', contractor_views.ContractorCertificateDetailView.as_view(), name='contractor_detail'),
    path('contractors/certificates/<int:pk>/edit/', contractor_views.ContractorCertificateUpdateView.as_view(), name='contractor_update'),
    path('contractors/certificates/<int:pk>/submit/', contractor_views.ContractorCertificateSubmitView.as_view(), name='contractor_submit'),
    path('contractors/certificates/<int:pk>/post-gl/', contractor_views.ContractorCertificatePostGLView.as_view(), name='contractor_post_gl'),
    path('contractors/certificates/<int:pk>/storno-reverse/', contractor_views.ContractorCertificateStornoReverseView.as_view(), name='contractor_storno_reverse'),
    path('contractors/certificates/<int:pk>/import-excel/', contractor_views.ContractorCertificateExcelImportView.as_view(), name='contractor_import_excel'),
    path('contractors/certificates/<int:pk>/excel-import/', contractor_views.ContractorCertificateExcelImportView.as_view(), name='contractor_excel_import'),
    path('contractors/certificates/<int:pk>/print/', contractor_views.ContractorCertificatePrintView.as_view(), name='contractor_print'),
    path('contractors/certificates/installments/<int:installment_id>/settle-cheque/', contractor_views.ContractorCertificateSettleInstallmentView.as_view(), name='contractor_settle_installment'),

    # Engineering (أوامر التعديلات وبنود الفحص)
    path('engineering/variations/', engineering_views.VariationOrderListView.as_view(), name='variation_list'),
    path('engineering/variations/create/', engineering_views.VariationOrderCreateView.as_view(), name='variation_create'),
    path('engineering/variations/<int:pk>/', engineering_views.VariationOrderDetailView.as_view(), name='variation_detail'),
    path('engineering/variations/<int:pk>/edit/', engineering_views.VariationOrderUpdateView.as_view(), name='variation_update'),
    path('engineering/variations/<int:pk>/approve/', engineering_views.VariationOrderApproveView.as_view(), name='variation_approve'),
    path('engineering/variations/<int:pk>/reject/', engineering_views.VariationOrderRejectView.as_view(), name='variation_reject'),
    path('engineering/snags/', engineering_views.SnagItemListView.as_view(), name='snag_list'),
    path('engineering/snags/create/', engineering_views.SnagItemCreateView.as_view(), name='snag_create'),
    path('engineering/snags/<int:pk>/resolve/', engineering_views.SnagItemResolveView.as_view(), name='snag_resolve'),
    path('api/engineering/snags/sync/', engineering_views.ApiSnagSyncView.as_view(), name='api_snag_sync'),

    # Handover & Warranty (محاضر التسليم والضمان)
    path('handovers/', service_views.HandoverReceiptListView.as_view(), name='handover_list'),
    path('handovers/create/', service_views.HandoverReceiptCreateView.as_view(), name='handover_create'),
    path('handovers/<int:pk>/', service_views.HandoverReceiptDetailView.as_view(), name='handover_detail'),
    path('handovers/<int:pk>/edit/', service_views.HandoverReceiptUpdateView.as_view(), name='handover_update'),
    path('handovers/<int:pk>/execute/', service_views.HandoverReceiptExecuteView.as_view(), name='handover_execute'),
    path('handovers/<int:pk>/print/', service_views.HandoverReceiptPrintView.as_view(), name='handover_print'),

    path('warranties/', service_views.WarrantyTicketListView.as_view(), name='warranty_list'),
    path('warranties/create/', service_views.WarrantyTicketCreateView.as_view(), name='warranty_create'),
    path('warranties/<int:pk>/', service_views.WarrantyTicketDetailView.as_view(), name='warranty_detail'),
    path('warranties/<int:pk>/assign/', service_views.WarrantyTicketAssignView.as_view(), name='warranty_assign'),
    path('warranties/<int:pk>/resolve/', service_views.WarrantyTicketResolveView.as_view(), name='warranty_resolve'),
    path('warranties/<int:pk>/debit-retention/', service_views.WarrantyTicketDebitRetentionView.as_view(), name='warranty_debit_retention'),

    # Operations & Facilities (صندوق الصيانة، الإنذارات، الشركاء، التبديلات)
    path('facilities/operations/', operations_views.MaintenanceFundListView.as_view(), name='facility_list'),
    path('facilities/operations/deposit/', operations_views.MaintenanceFundDepositCreateView.as_view(), name='facility_deposit_create'),
    path('facilities/operations/yield/', operations_views.MaintenanceFundYieldCreateView.as_view(), name='facility_yield_create'),
    path('facilities/operations/expense/', operations_views.MaintenanceFundExpenseCreateView.as_view(), name='facility_expense_create'),

    path('legal/notices/', operations_views.LegalNoticeListView.as_view(), name='legal_list'),
    path('legal/notices/create/', operations_views.LegalNoticeCreateView.as_view(), name='legal_create'),
    path('legal/notices/<int:pk>/action/', operations_views.LegalNoticeActionView.as_view(), name='legal_action'),

    path('partnerships/', operations_views.LandownerPartnershipListView.as_view(), name='partnership_list'),
    path('partnerships/create/', operations_views.LandownerPartnershipCreateView.as_view(), name='partnership_create'),
    path('partnerships/<int:pk>/', operations_views.LandownerPartnershipDetailView.as_view(), name='partnership_detail'),
    path('partnerships/<int:pk>/allocate-unit/', operations_views.LandownerUnitAllocateView.as_view(), name='partnership_allocate_unit'),

    path('swaps/', operations_views.UnitSwapListView.as_view(), name='swap_list'),
    path('swaps/create/', operations_views.UnitSwapCreateView.as_view(), name='swap_create'),
    path('swaps/<int:pk>/', operations_views.UnitSwapDetailView.as_view(), name='swap_detail'),
    path('swaps/<int:pk>/execute/', operations_views.UnitSwapExecuteView.as_view(), name='swap_execute'),
    path('swaps/<int:pk>/print/', operations_views.UnitSwapOfficialPrintView.as_view(), name='swap_print'),

    # AJAX APIs for Concurrency Booking & Details
    path('api/units/<int:unit_id>/', matrix_views.ApiUnitDetailView.as_view(), name='api_unit_detail'),
    path('api/units/<int:unit_id>/book/', matrix_views.ApiBookUnitView.as_view(), name='api_book_unit'),
    path('api/bookings/<int:booking_id>/cancel/', matrix_views.ApiCancelBookingView.as_view(), name='api_cancel_booking'),
    path('api/bookings/<int:booking_id>/refund/', matrix_views.ApiRefundBookingView.as_view(), name='api_refund_booking'),

    # Unit Pricing Matrix Engine (Wave 2 Phase 4)
    path('projects/<int:project_id>/pricing/', pricing_views.ProjectPricingView.as_view(), name='project_pricing'),
    path('api/projects/<int:project_id>/pricing/preview/', pricing_views.ApiPreviewPricingView.as_view(), name='api_preview_pricing'),
    path('api/projects/<int:project_id>/pricing/apply/', pricing_views.ApiApplyBulkPricingView.as_view(), name='api_apply_bulk_pricing'),

    # Real Estate Analytics & Financial Reports (Wave 6 - Phase 6.1 & Track 4 Tower Sales Brief)
    path('reports/dual-subledger/', report_views.DualSubledgerReportView.as_view(), name='report_dual_subledger'),
    path('reports/cash-flow/', report_views.CashFlowLiquidityReportView.as_view(), name='report_cash_flow'),
    path('reports/wip-revenue/', report_views.ProjectWIPRevenueReportView.as_view(), name='report_wip_revenue'),
    path('reports/broker-commissions/', report_views.BrokerCommissionReportView.as_view(), name='report_broker_commissions'),
    path('reports/tower-sales-brief/', report_views.TowerSalesBriefReportView.as_view(), name='report_tower_sales_brief'),
    path('reports/tower-sales-brief/print/', report_views.TowerSalesBriefPrintView.as_view(), name='report_tower_sales_brief_print'),
    path('reports/tower-sales-brief/export/', report_views.TowerSalesBriefExportView.as_view(), name='report_tower_sales_brief_export'),

    # Finishing & Variations (Track 2: Finishing Packages & Specs Directory)
    path('finishing/orders/', finishing_views.FinishingOrderListView.as_view(), name='finishing_order_list'),
    path('finishing/orders/create/', finishing_views.FinishingOrderCreateView.as_view(), name='finishing_order_create'),
    path('finishing/orders/kanban/', finishing_views.FinishingOrderKanbanView.as_view(), name='finishing_kanban'),
    path('finishing/orders/<int:pk>/', finishing_views.FinishingOrderDetailView.as_view(), name='finishing_order_detail'),
    path('finishing/orders/<int:pk>/print/', finishing_views.FinishingOrderPrintView.as_view(), name='finishing_order_print'),
    path('finishing/catalog/', finishing_views.FinishingCatalogView.as_view(), name='finishing_catalog'),
    path('api/finishing/orders/<int:pk>/transition/', finishing_views.ApiFinishingStageTransitionView.as_view(), name='api_finishing_stage_transition'),
    path('api/finishing/orders/<int:pk>/hydrostatic-test/', finishing_views.ApiRecordHydrostaticTestView.as_view(), name='api_finishing_hydrostatic_test'),

    # Site Execution & Architectural Matrix (Track 3: WBS & 32-Trade Site Inspection Matrix)
    path('projects/<int:project_id>/wbs/', engineering_views.ProjectWbsTreeView.as_view(), name='project_wbs_tree'),
    path('projects/<int:project_id>/wbs/sync-unit-progress/', engineering_views.ProjectWbsSyncUnitProgressAjaxView.as_view(), name='project_wbs_sync_unit_progress'),
    path('projects/<int:project_id>/wbs/save/', engineering_views.ProjectWbsActivitySaveAjaxView.as_view(), name='project_wbs_activity_save'),
    path('projects/<int:project_id>/wbs/<int:activity_id>/delete/', engineering_views.ProjectWbsActivityDeleteAjaxView.as_view(), name='project_wbs_activity_delete'),
    path('projects/<int:project_id>/evm/', engineering_views.ProjectEvmDashboardView.as_view(), name='project_evm_dashboard'),
    path('api/projects/<int:project_id>/evm/', engineering_views.ProjectEvmApiView.as_view(), name='api_project_evm'),
    path('projects/<int:project_id>/site-report/', engineering_views.SiteProjectReportView.as_view(), name='site_project_report'),
    path('projects/<int:project_id>/site-report/excel/', engineering_views.ExportSiteProgressExcelView.as_view(), name='site_project_report_excel'),
    path('projects/<int:project_id>/site-log/create/', engineering_views.SiteDailyLogCreateView.as_view(), name='site_daily_log_create'),
    path('floors/<int:floor_id>/site-dossier/', engineering_views.SiteFloorInspectionPrintView.as_view(), name='site_floor_inspection_dossier'),
    path('api/site/stages/<int:record_id>/quick-update/', engineering_views.QuickUpdateStageAjaxView.as_view(), name='api_site_stage_quick_update'),
    path('api/site/stages/<int:record_id>/spec-preview/', engineering_views.StageRecordSpecPreviewAjaxView.as_view(), name='api_site_stage_spec_preview'),
    path('api/site/floors/bulk-update/', engineering_views.BulkUpdateFloorStageAjaxView.as_view(), name='api_site_floor_bulk_update'),
    path('api/site/rfi/bulk-update/', engineering_views.BulkUpdateRfiAjaxView.as_view(), name='api_site_rfi_bulk_update'),
    path('api/site/stages/sync/', engineering_views.ApiSiteProgressBatchSyncView.as_view(), name='api_site_stages_sync'),

    # Milestone Collections Bridge (Track 3: Milestone Collection Alerts & Installment Triggers)
    path('milestones/alerts/', engineering_views.MilestoneCollectionAlertsListView.as_view(), name='milestone_collection_alerts'),
    path('api/milestones/alerts/<int:alert_id>/update-status/', engineering_views.MilestoneAlertUpdateStatusAjaxView.as_view(), name='api_milestone_alert_update_status'),
]
