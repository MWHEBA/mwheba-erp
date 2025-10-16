from django.urls import path
from . import views, supplier_apis
from .views import (
    PricingOrderListView,
    PricingOrderCreateView,
    PricingOrderUpdateView,
    PricingOrderDetailView,
    PricingOrderDeleteView,
    PricingOrderPDFView,
    # النماذج الجديدة
    OrderSupplierListView,
    OrderSupplierCreateView,
    PricingQuotationListView,
    PricingQuotationDetailView,
    PricingQuotationCreateView,
    PricingQuotationUpdateView,
    PricingApprovalWorkflowListView,
    PricingApprovalWorkflowCreateView,
    PricingApprovalListView,
    PricingApprovalDetailView,
    PricingReportListView,
    PricingKPIListView,
)
from . import enhanced_pricing_views
from . import api_views

app_name = "pricing"

urlpatterns = [
    # الصفحة الرئيسية للتسعير - إعادة توجيه للوحة التحكم
    path("", views.pricing_dashboard, name="pricing_dashboard"),
    # طلبات التسعير
    path("orders/", views.PricingOrderListView.as_view(), name="pricing_order_list"),
    path(
        "orders/create/",
        views.PricingOrderCreateView.as_view(),
        name="pricing_order_create",
    ),
    path(
        "add/", views.PricingOrderCreateView.as_view(), name="pricing_add"
    ),  # إضافة الرابط المفقود
    path("<int:pk>/", views.PricingOrderDetailView.as_view(), name="pricing_detail"),
    path("<int:pk>/edit/", views.PricingOrderUpdateView.as_view(), name="pricing_edit"),
    path(
        "<int:pk>/delete/",
        views.PricingOrderDeleteView.as_view(),
        name="pricing_delete",
    ),
    path(
        "<int:pk>/approve/",
        views.PricingOrderApproveView.as_view(),
        name="pricing_approve",
    ),
    path(
        "<int:pk>/execute/",
        views.PricingOrderExecuteView.as_view(),
        name="pricing_execute",
    ),
    path("<int:pk>/pdf/", views.PricingOrderPDFView.as_view(), name="pricing_pdf"),
    path(
        "<int:pk>/internal/",
        views.InternalContentCreateView.as_view(),
        name="internal_content_add",
    ),
    path(
        "internal/<int:pk>/edit/",
        views.InternalContentUpdateView.as_view(),
        name="internal_content_edit",
    ),
    path(
        "<int:pk>/finishing/add/",
        views.OrderFinishingCreateView.as_view(),
        name="order_finishing_add",
    ),
    path(
        "finishing/<int:pk>/edit/",
        views.OrderFinishingUpdateView.as_view(),
        name="order_finishing_edit",
    ),
    path(
        "finishing/<int:pk>/delete/",
        views.OrderFinishingDeleteView.as_view(),
        name="order_finishing_delete",
    ),
    path(
        "<int:pk>/expense/add/",
        views.ExtraExpenseCreateView.as_view(),
        name="extra_expense_add",
    ),
    path(
        "expense/<int:pk>/edit/",
        views.ExtraExpenseUpdateView.as_view(),
        name="extra_expense_edit",
    ),
    path(
        "expense/<int:pk>/delete/",
        views.ExtraExpenseDeleteView.as_view(),
        name="extra_expense_delete",
    ),
    path(
        "<int:pk>/comment/add/",
        views.OrderCommentCreateView.as_view(),
        name="order_comment_add",
    ),
    path("calculate-cost/", views.calculate_cost, name="calculate_cost"),
    path("api/plate-price/", views.get_plate_price, name="get_plate_price"),
    path("api/plate-sizes/", views.get_plate_sizes, name="get_plate_sizes"),
    path("api/press-size/", views.get_press_size, name="get_press_size"),
    path("api/paper-weights/", views.get_paper_weights, name="get_paper_weights"),
    path(
        "api/paper-sheet-types/",
        views.get_paper_sheet_types,
        name="get_paper_sheet_types",
    ),
    path("api/paper-origins/", views.get_paper_origins, name="get_paper_origins"),
    path("api/paper-price/", views.get_paper_price, name="get_paper_price"),
    path(
        "api/suppliers-by-service/",
        views.get_suppliers_by_service,
        name="get_suppliers_by_service",
    ),
    path(
        "clear-form-data/",
        views.clear_pricing_form_data,
        name="clear_pricing_form_data",
    ),
    path(
        "api/coating-services/", views.coating_services_api, name="coating_services_api"
    ),
    path(
        "api/coating-services-by-supplier/", views.get_coating_services_by_supplier, name="get_coating_services_by_supplier"
    ),
    path(
        "api/coating-service-price/", views.get_coating_service_price, name="get_coating_service_price"
    ),
    path(
        "api/folding-services/", views.folding_services_api, name="folding_services_api"
    ),
    path(
        "api/die-cut-services/", views.die_cut_services_api, name="die_cut_services_api"
    ),
    path(
        "api/spot-uv-services/", views.spot_uv_services_api, name="spot_uv_services_api"
    ),
    # مسارات API لمعلومات المطبعة
    path("api/presses/", views.get_presses, name="get_presses"),
    path("api/press-price/", views.get_press_price, name="get_press_price"),
    path("api/press-details/", views.get_press_details, name="get_press_details"),
    path("api/press-size/", views.get_press_size, name="get_press_size"),
    path(
        "api/paper-size-dimensions/",
        views.get_paper_size_dimensions,
        name="get_paper_size_dimensions",
    ),
    path(
        "api/convert-sheet-type-to-dimensions/",
        views.convert_sheet_type_to_dimensions,
        name="convert_sheet_type_to_dimensions",
    ),
    # مسارات API لتصفية الموردين
    path(
        "api/printing-suppliers/",
        supplier_apis.get_printing_suppliers_api,
        name="get_printing_suppliers_api",
    ),
    path(
        "api/ctp-suppliers/",
        supplier_apis.get_ctp_suppliers_api,
        name="get_ctp_suppliers_api",
    ),
    path("api/paper-suppliers/", views.get_paper_suppliers, name="get_paper_suppliers"),
    path("api/paper-types/", views.get_paper_types, name="get_paper_types"),
    path("api/get-paper-price/", views.get_paper_price, name="get_paper_price_alt"),
    path("api/get-press-price/", views.get_press_price, name="get_press_price_alt"),
    path("api/get-plate-price/", views.get_plate_price, name="get_plate_price_alt"),
    path("api/calculate-cost/", views.calculate_cost_api, name="calculate_cost_api"),
    # Enhanced APIs - محسنة
    path(
        "api/enhanced/paper-price/",
        enhanced_pricing_views.enhanced_paper_price_api,
        name="enhanced_paper_price_api",
    ),
    path(
        "api/enhanced/press-price/",
        enhanced_pricing_views.enhanced_press_price_api,
        name="enhanced_press_price_api",
    ),
    path(
        "api/enhanced/plate-price/",
        enhanced_pricing_views.enhanced_plate_price_api,
        name="enhanced_plate_price_api",
    ),
    path(
        "api/enhanced/total-cost/",
        enhanced_pricing_views.enhanced_total_cost_api,
        name="enhanced_total_cost_api",
    ),
    path(
        "api/enhanced/suppliers-by-service/",
        enhanced_pricing_views.enhanced_suppliers_by_service_api,
        name="enhanced_suppliers_by_service_api",
    ),
    path(
        "api/enhanced/test/",
        enhanced_pricing_views.pricing_calculator_test_api,
        name="pricing_calculator_test_api",
    ),
    # ===== APIs الجديدة للحسابات التلقائية =====
    path("enhanced/", views.enhanced_pricing_form, name="enhanced_pricing_form"),
    path("api/v2/calculate-cost/", api_views.calculate_cost, name="api_calculate_cost"),
    path("api/v2/paper-price/", api_views.get_paper_price, name="api_paper_price"),
    path("api/v2/plate-price/", api_views.get_plate_price, name="api_plate_price"),
    path(
        "api/v2/digital-printing-price/",
        api_views.get_digital_printing_price,
        name="api_digital_printing_price",
    ),
    path(
        "api/v2/finishing-cost/",
        api_views.calculate_finishing_cost,
        name="api_finishing_cost",
    ),
    path("api/v2/paper-types/", api_views.get_paper_types, name="api_paper_types"),
    path(
        "api/v2/paper-sizes/", api_views.get_paper_sizes, name="api_paper_sizes"
    ),  # يجلب مقاسات المنتجات الآن
    path("api/v2/suppliers/", api_views.get_suppliers, name="api_suppliers"),
    path(
        "api/v2/order-summary/<int:order_id>/",
        api_views.get_order_summary,
        name="api_order_summary",
    ),
    # مسارات جديدة للقائمة الجانبية
    # عروض الأسعار
    path("quotations/", views.quotation_list, name="quotation_list"),
    path("quotations/create/", views.quotation_create, name="quotation_create"),
    # إدارة الأسعار
    path(
        "supplier-pricing/", views.supplier_pricing_list, name="supplier_pricing_list"
    ),
    path("price-comparison/", views.price_comparison, name="price_comparison"),
    # التقارير والتحليلات
    path("dashboard/", views.pricing_dashboard, name="pricing_dashboard"),
    path(
        "reports/profitability/",
        views.profitability_report,
        name="profitability_report",
    ),
    path("analytics/", views.pricing_analytics, name="pricing_analytics"),
    # الإعدادات (الرابط الموجود مسبقاً)
    path("settings/", views.settings_home, name="settings_home"),
    # إعدادات أنواع الورق
    path("settings/paper-types/", views.paper_type_list, name="paper_type_list"),
    path("settings/paper-types/add/", views.paper_type_create, name="paper_type_add"),
    path(
        "settings/paper-types/create/",
        views.paper_type_create,
        name="paper_type_create",
    ),
    path(
        "settings/paper-types/<int:pk>/edit/",
        views.paper_type_edit,
        name="paper_type_edit",
    ),
    path(
        "settings/paper-types/<int:pk>/delete/",
        views.paper_type_delete,
        name="paper_type_delete",
    ),
    # إعدادات أحجام الورق
    path("settings/paper-sizes/", views.paper_size_list, name="paper_size_list"),
    path("settings/paper-sizes/add/", views.paper_size_create, name="paper_size_add"),
    path(
        "settings/paper-sizes/create/",
        views.paper_size_create,
        name="paper_size_create",
    ),
    path(
        "settings/paper-sizes/<int:pk>/edit/",
        views.paper_size_edit,
        name="paper_size_edit",
    ),
    path(
        "settings/paper-sizes/<int:pk>/delete/",
        views.paper_size_delete,
        name="paper_size_delete",
    ),
    # إعدادات أوزان الورق
    path("settings/paper-weights/", views.paper_weight_list, name="paper_weight_list"),
    path(
        "settings/paper-weights/add/",
        views.paper_weight_create,
        name="paper_weight_add",
    ),
    path(
        "settings/paper-weights/create/",
        views.paper_weight_create,
        name="paper_weight_create",
    ),
    path(
        "settings/paper-weights/<int:pk>/edit/",
        views.paper_weight_edit,
        name="paper_weight_edit",
    ),
    path(
        "settings/paper-weights/<int:pk>/delete/",
        views.paper_weight_delete,
        name="paper_weight_delete",
    ),
    # إعدادات منشأ الورق
    path("settings/paper-origins/", views.paper_origin_list, name="paper_origin_list"),
    path(
        "settings/paper-origins/add/",
        views.paper_origin_create,
        name="paper_origin_add",
    ),
    path(
        "settings/paper-origins/create/",
        views.paper_origin_create,
        name="paper_origin_create",
    ),
    path(
        "settings/paper-origins/<int:pk>/edit/",
        views.paper_origin_edit,
        name="paper_origin_edit",
    ),
    path(
        "settings/paper-origins/<int:pk>/delete/",
        views.paper_origin_delete,
        name="paper_origin_delete",
    ),
    # إعدادات اتجاهات الطباعة
    path(
        "settings/print-directions/",
        views.print_direction_list,
        name="print_direction_list",
    ),
    path(
        "settings/print-directions/create/",
        views.print_direction_create,
        name="print_direction_create",
    ),
    path(
        "settings/print-directions/<int:pk>/edit/",
        views.print_direction_edit,
        name="print_direction_edit",
    ),
    path(
        "settings/print-directions/<int:pk>/delete/",
        views.print_direction_delete,
        name="print_direction_delete",
    ),
    # إعدادات جوانب الطباعة
    path("settings/print-sides/", views.print_side_list, name="print_side_list"),
    path(
        "settings/print-sides/create/",
        views.print_side_create,
        name="print_side_create",
    ),
    path(
        "settings/print-sides/<int:pk>/edit/",
        views.print_side_edit,
        name="print_side_edit",
    ),
    path(
        "settings/print-sides/<int:pk>/delete/",
        views.print_side_delete,
        name="print_side_delete",
    ),
    # إعدادات أنواع التغطية
    path("settings/coating-types/", views.coating_type_list, name="coating_type_list"),
    path("api/coating-types/", views.coating_types_api, name="coating_types_api"),
    path(
        "settings/coating-types/add/",
        views.coating_type_create,
        name="coating_type_add",
    ),
    path(
        "settings/coating-types/create/",
        views.coating_type_create,
        name="coating_type_create",
    ),
    path(
        "settings/coating-types/<int:pk>/edit/",
        views.coating_type_edit,
        name="coating_type_edit",
    ),
    path(
        "settings/coating-types/<int:pk>/delete/",
        views.coating_type_delete,
        name="coating_type_delete",
    ),
    # إعدادات أنواع خدمات ما بعد الطباعة
    path(
        "settings/finishing-types/",
        views.finishing_type_list,
        name="finishing_type_list",
    ),
    path(
        "settings/finishing-types/add/",
        views.finishing_type_create,
        name="finishing_type_add",
    ),
    path(
        "settings/finishing-types/create/",
        views.finishing_type_create,
        name="finishing_type_create",
    ),
    path(
        "settings/finishing-types/<int:pk>/edit/",
        views.finishing_type_edit,
        name="finishing_type_edit",
    ),
    path(
        "settings/finishing-types/<int:pk>/delete/",
        views.finishing_type_delete,
        name="finishing_type_delete",
    ),
    # إعدادات عامة
    path("settings/vat/", views.vat_settings, name="vat_settings"),
    path("settings/system/", views.system_settings_list, name="system_settings_list"),
    # ===== URLs للنماذج الجديدة =====
    # موردي الطلبات
    path(
        "orders/<int:order_id>/suppliers/",
        OrderSupplierListView.as_view(),
        name="order_suppliers_list",
    ),
    path(
        "orders/<int:order_id>/suppliers/add/",
        OrderSupplierCreateView.as_view(),
        name="order_supplier_add",
    ),
    # عروض الأسعار الجديدة
    path("quotations-new/", PricingQuotationListView.as_view(), name="quotations_list"),
    path(
        "quotations-new/<int:pk>/",
        PricingQuotationDetailView.as_view(),
        name="quotation_detail",
    ),
    path(
        "quotations-new/create/",
        PricingQuotationCreateView.as_view(),
        name="quotation_create_new",
    ),
    path(
        "quotations-new/<int:pk>/edit/",
        PricingQuotationUpdateView.as_view(),
        name="quotation_edit",
    ),
    # تدفقات الموافقة
    path(
        "approval-workflows/",
        PricingApprovalWorkflowListView.as_view(),
        name="approval_workflows_list",
    ),
    path(
        "approval-workflows/create/",
        PricingApprovalWorkflowCreateView.as_view(),
        name="approval_workflow_create",
    ),
    # الموافقات
    path("approvals/", PricingApprovalListView.as_view(), name="approvals_list"),
    path(
        "approvals/<int:pk>/",
        PricingApprovalDetailView.as_view(),
        name="approval_detail",
    ),
    path(
        "approvals/<int:approval_id>/approve/",
        views.approve_pricing_request,
        name="approve_pricing_request",
    ),
    # التقارير ومؤشرات الأداء
    path("reports-new/", PricingReportListView.as_view(), name="reports_list"),
    path("kpis/", PricingKPIListView.as_view(), name="kpis_list"),
    # إعدادات أنواع ماكينات الأوفست
    path(
        "settings/offset-machine-types/",
        views.offset_machine_type_list,
        name="offset_machine_type_list",
    ),
    path(
        "settings/offset-machine-types/create/",
        views.offset_machine_type_create,
        name="offset_machine_type_create",
    ),
    path(
        "settings/offset-machine-types/<int:pk>/edit/",
        views.offset_machine_type_edit,
        name="offset_machine_type_edit",
    ),
    path(
        "settings/offset-machine-types/<int:pk>/delete/",
        views.offset_machine_type_delete,
        name="offset_machine_type_delete",
    ),
    # إعدادات مقاسات ماكينات الأوفست
    path(
        "settings/offset-sheet-sizes/",
        views.offset_sheet_size_list,
        name="offset_sheet_size_list",
    ),
    path(
        "settings/offset-sheet-sizes/create/",
        views.offset_sheet_size_create,
        name="offset_sheet_size_create",
    ),
    path(
        "settings/offset-sheet-sizes/<int:pk>/edit/",
        views.offset_sheet_size_edit,
        name="offset_sheet_size_edit",
    ),
    path(
        "settings/offset-sheet-sizes/<int:pk>/delete/",
        views.offset_sheet_size_delete,
        name="offset_sheet_size_delete",
    ),
    # إعدادات أنواع ماكينات الديجيتال
    path(
        "settings/digital-machine-types/",
        views.digital_machine_type_list,
        name="digital_machine_type_list",
    ),
    path(
        "settings/digital-machine-types/create/",
        views.digital_machine_type_create,
        name="digital_machine_type_create",
    ),
    path(
        "settings/digital-machine-types/<int:pk>/edit/",
        views.digital_machine_type_edit,
        name="digital_machine_type_edit",
    ),
    path(
        "settings/digital-machine-types/<int:pk>/delete/",
        views.digital_machine_type_delete,
        name="digital_machine_type_delete",
    ),
    # إعدادات مقاسات ماكينات الديجيتال
    path(
        "settings/digital-sheet-sizes/",
        views.digital_sheet_size_list,
        name="digital_sheet_size_list",
    ),
    path(
        "settings/digital-sheet-sizes/create/",
        views.digital_sheet_size_create,
        name="digital_sheet_size_create",
    ),
    path(
        "settings/digital-sheet-sizes/<int:pk>/edit/",
        views.digital_sheet_size_edit,
        name="digital_sheet_size_edit",
    ),
    path(
        "settings/digital-sheet-sizes/<int:pk>/delete/",
        views.digital_sheet_size_delete,
        name="digital_sheet_size_delete",
    ),
    # إعدادات أنواع المنتجات
    path("settings/product-types/", views.product_type_list, name="product_type_list"),
    path(
        "settings/product-types/create/",
        views.product_type_create,
        name="product_type_create",
    ),
    path(
        "settings/product-types/<int:pk>/edit/",
        views.product_type_edit,
        name="product_type_edit",
    ),
    path(
        "settings/product-types/<int:pk>/delete/",
        views.product_type_delete,
        name="product_type_delete",
    ),
    # إعدادات مقاسات المنتجات
    path("settings/product-sizes/", views.product_size_list, name="product_size_list"),
    path(
        "settings/product-sizes/create/",
        views.product_size_create,
        name="product_size_create",
    ),
    path(
        "settings/product-sizes/<int:pk>/edit/",
        views.product_size_edit,
        name="product_size_edit",
    ),
    path(
        "settings/product-sizes/<int:pk>/delete/",
        views.product_size_delete,
        name="product_size_delete",
    ),
    # إعدادات مقاسات الزنكات
    path("settings/plate-sizes/", views.plate_size_list, name="plate_size_list"),
    path(
        "settings/plate-sizes/create/",
        views.plate_size_create,
        name="plate_size_create",
    ),
    path(
        "settings/plate-sizes/<int:pk>/edit/",
        views.plate_size_edit,
        name="plate_size_edit",
    ),
    path(
        "settings/plate-sizes/<int:pk>/delete/",
        views.plate_size_delete,
        name="plate_size_delete",
    ),
]
