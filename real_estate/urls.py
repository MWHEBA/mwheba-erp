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
    broker_views,
    engineering_views,
    service_views,
    operations_views,
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

    # Contracts (عقود البيع الرسمية)
    path('contracts/', contract_views.ContractListView.as_view(), name='contract_list'),
    path('contracts/create/', contract_views.ContractCreateView.as_view(), name='contract_create'),
    path('contracts/<int:pk>/', contract_views.ContractDetailView.as_view(), name='contract_detail'),
    path('contracts/<int:pk>/clearance/print/', contract_views.ContractDebtClearancePrintView.as_view(), name='contract_clearance_print'),

    # Brokers & Commissions (الوسطاء والمسوقين العقاريين)
    path('brokers/', broker_views.BrokerListView.as_view(), name='broker_list'),
    path('commissions/', broker_views.BrokerCommissionListView.as_view(), name='commission_list'),

    # Contractors (مستخلصات المقاولين الإنشائية)
    path('contractors/certificates/', contractor_views.ContractorCertificateListView.as_view(), name='contractor_list'),

    # Engineering (أوامر التعديلات وبنود الفحص)
    path('engineering/variations/', engineering_views.VariationOrderListView.as_view(), name='variation_list'),
    path('engineering/snags/', engineering_views.SnagItemListView.as_view(), name='snag_list'),

    # Handover & Warranty (محاضر التسليم والضمان)
    path('handovers/', service_views.HandoverReceiptListView.as_view(), name='handover_list'),
    path('warranties/', service_views.WarrantyTicketListView.as_view(), name='warranty_list'),

    # Operations & Facilities (صندوق الصيانة، الإنذارات، الشركاء، التبديلات)
    path('facilities/operations/', operations_views.MaintenanceFundListView.as_view(), name='facility_list'),
    path('legal/notices/', operations_views.LegalNoticeListView.as_view(), name='legal_list'),
    path('partnerships/', operations_views.LandownerPartnershipListView.as_view(), name='partnership_list'),
    path('swaps/', operations_views.UnitSwapListView.as_view(), name='swap_list'),

    # AJAX APIs for Concurrency Booking & Details
    path('api/units/<int:unit_id>/', matrix_views.ApiUnitDetailView.as_view(), name='api_unit_detail'),
    path('api/units/<int:unit_id>/book/', matrix_views.ApiBookUnitView.as_view(), name='api_book_unit'),
    path('api/bookings/<int:booking_id>/cancel/', matrix_views.ApiCancelBookingView.as_view(), name='api_cancel_booking'),
    path('api/bookings/<int:booking_id>/refund/', matrix_views.ApiRefundBookingView.as_view(), name='api_refund_booking'),

    # Unit Pricing Matrix Engine (Wave 2 Phase 4)
    path('projects/<int:project_id>/pricing/', pricing_views.ProjectPricingView.as_view(), name='project_pricing'),
    path('api/projects/<int:project_id>/pricing/preview/', pricing_views.ApiPreviewPricingView.as_view(), name='api_preview_pricing'),
    path('api/projects/<int:project_id>/pricing/apply/', pricing_views.ApiApplyBulkPricingView.as_view(), name='api_apply_bulk_pricing'),
]
