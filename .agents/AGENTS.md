# Project Rules for MWHEBA ERP

## 1. Cross-Template & Module Consistency Directive
- Any UI/UX, styling, layout, formatting, calculation, validation, error handling, or feature modification discussed or requested MUST automatically be audited, propagated, and applied across ALL similar and related templates, forms, detail views, print views, and modules (e.g. Sales Invoices, Purchase Invoices, Quotations, Sales Returns, Purchase Returns, Payment Vouchers, Customer & Supplier detail views) throughout the codebase without leaving any gaps.
- **Component-Based DRY Architecture**: Prefer extracting reusable template components into `templates/components/` and including them via `{% include %}` to ensure changes automatically cascade across all modules without code duplication.

## 2. Design & Styling System (Strict UI Rules)
- **Colors**: Use ONLY CSS variables declared in `:root` for all colors. NEVER hardcode hex (`#fff`), `rgb()`, or `hsl()` directly in CSS/HTML templates.
- **No Gradients**: Strictly use flat colors only. Gradients are prohibited to maintain a corporate, calm, and clean look.
- **Typography & Fonts**: NEVER change system fonts or load external/unapproved font families. Preserve existing typography balance.
- **Animations**: Avoid excessive or flashy CSS rules/animations. Keep transitions subtle, semantic, minimal, and professional.
- **UI Components Consistency**: Standardize section containers, card filters, badges, and server-side pagination (SSR Pagination) across all list and detail views.

## 3. Financial & Business Logic Integrity
- **Multi-Currency & IAS 21 Standard**: Preserve precision rounding (`decimal_places=2` for amounts, `decimal_places=6` for rates). Accounts must support dual opening balances (`opening_balance_foreign` & `opening_balance_rate`). Open monetary items must be subject to periodic IAS 21 revaluation via `FXRevaluationService`.
- **Double-Entry & Treasury Balance Rules**: Ensure payment vouchers, prepaid allocations, cross-currency cash transfers (`CashTransferService`), and treasury balance updates mirror correctly across ledger entries without duplication. Realized FX gains/losses must be automatically posted for cross-currency transfers.
- **Penny Difference Handling**: Small precision rounding discrepancies (<= 0.05) during multi-currency conversions must automatically route to `Rounding Differences Account` to maintain strict entry balance.
- **Document Conventions**: Respect established document numbering patterns (Invoices, Quotations, Vouchers, etc.) via `SequenceService`.

## 4. Coding & Language Standards
- **Language Policy**: Use Egyptian Arabic in chat and code comments. Use English in actual source code (variable names, functions, models, classes) and documentation.
- **Code Cleanliness (DRY)**: Re-use common utility functions in `utils/` and custom Django template tags instead of repeating code across modules.
- **No Unrequested Browser Runs**: Never open or launch the browser automatically unless specifically requested by the user.

## 5. Testing & Data Safety
- **Data Preservation**: NEVER issue destructive database operations or drop columns without explicit user approval.
- **Verification**: Always verify changes by running tests (`pytest` / Django checks) before declaring tasks completed.

## 6. Standardized ListView Architecture & Components Pattern
- **Central Page Header & Breadcrumbs**:
  - All module list, form, and detail views MUST use `{% include "shared/page_header.html" %}`.
  - Views MUST explicitly pass a structured `breadcrumb_items` array in the template context starting with Home (`reverse('core:dashboard')`), Section, and ending with Active item (`'active': True`). Example: `[{'title': _('الرئيسية'), 'url': reverse('core:dashboard'), 'icon': 'fa-home'}, {'title': _('الإدارة المالية'), 'url': reverse('financial:chart_of_accounts_list'), 'icon': 'fa-calculator'}, {'title': _('الأرصدة الافتتاحية'), 'active': True}]`.
- **Collapsible Filter Section**:
  - Enclosed inside `.section-container.mb-4`.
  - Section header MUST use `data-bs-toggle="collapse" data-bs-target="#filterSection"`.
  - Dropdown filters MUST use `.select2-filter` with RTL configuration (`dir: "rtl"`, `language: "ar"`).
- **AJAX Dynamic Search (`doSearch`) & URL State Sync**:
  - Form submit and input change handlers MUST invoke `window.doSearch()`.
  - AJAX response MUST dynamically swap `#<module>-table-container` with `data.table_html`, `#pagination-wrapper` with `data.pagination_html`, AND update any financial summary cards or totals wrapper (`data.totals_html` / `data.summary_html`).
  - MUST preserve browser navigation state using `history.replaceState`.
- **Unified Data Table Component**:
  - Tables MUST be rendered via `{% include "components/data_table.html" %}`.
  - Interactive row navigation MUST be attached via `initTableEvents()` excluding action triggers (`.col-actions, .btn, a, button`).
- **SSR Pagination Wrapper**:
  - SSR Pagination MUST be wrapped inside `#pagination-wrapper` using `{% include "partials/pagination.html" %}`.
- **Safe Destructive Action Confirmations**:
  - Deletion and destructive actions MUST use dynamic POST form creation with CSRF tokens (`confirmDelete`).

## 7. Strict UI Section & Card Formatting Rules
- **Statistical KPI Cards (`.stats-card`)**:
  - MUST NEVER be wrapped inside a `.section-container` or `.section-title`.
  - MUST be rendered directly in a grid row: `<div class="row g-3 mb-4">` containing `.stats-card` elements.
  - MUST use standard classes: `.stats-card` (`.stats-card-info`, `.stats-card-warning`, `.stats-card-success`, `.stats-card-danger`), `.stats-card-body`, `.stats-card-icon`, `.stats-card-title`, `.stats-card-value`.
- **Section Headers & Tables (`.section-container`)**:
  - Table and content sections MUST be enclosed inside `.section-container`.
  - Section headers MUST use standard `<h5 class="section-title"><i class="fas fa-... me-2"></i>Title</h5>` directly without wrapper `d-flex` divs or buttons inside the section title header.
  - Action buttons MUST NEVER be placed inside table section title headers; action buttons belong exclusively in `page_header.html` (`header_buttons`).
- **Clickable Table Rows & Actions Column**:
  - Prefer making data table rows clickable (`.clickable-row` with `data-href`) for direct detail navigation, omitting redundant "Actions" columns when primary view is single.
- **Standardized In-Table Button Groups**:
  - Row-level interactive controls MUST use standard `.btn-group.btn-group-sm` with standard outline classes (`btn-outline-secondary`, `btn-outline-danger`) and FontAwesome icons, avoiding custom circular CSS overrides.

## 8. Corporate ERP Unified Modal Architecture Standards
- **Modal Dialog & Positioning**:
  - All modals MUST use centered alignment and standard depth: `<div class="modal-dialog modal-dialog-centered">` (or `modal-lg modal-dialog-centered`).
  - Modal container MUST use borderless clean card styling with large shadow: `<div class="modal-content border-0 shadow-lg">`.
- **Standard Header Styling (`.modal-header`)**:
  - MUST use standard corporate light background and bottom border: `<div class="modal-header bg-light border-bottom px-4 py-3">`.
  - MUST NEVER use solid colored headers like `bg-primary`, `bg-dark`, `bg-success` or `btn-close-white`.
  - Title MUST use `<h5 class="modal-title fw-bold text-dark mb-0">` with a colored FontAwesome icon (e.g. `<i class="fas fa-... text-primary me-2"></i>Title</h5>`).
  - Standard dark close button MUST be used: `<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>`.
- **Standard Body & Footer (`.modal-body` & `.modal-footer`)**:
  - Body MUST use `<div class="modal-body p-4">`.
  - Footer MUST use `<div class="modal-footer bg-light border-top px-4 py-3">`.
  - Action buttons MUST use standard ERP classes (`btn-secondary px-3` for Cancel, `btn-primary px-4 fw-bold` for Submit).
- **Select2 Dropdown Integration Inside Modals**:
  - Select2 dropdowns placed inside Bootstrap modals MUST be initialized with `dropdownParent: $('#modal_id')` to prevent the dropdown menu from opening behind the modal backdrop overlay.

## 9. Enterprise IAS 21 Multi-Currency Governance Architecture
- **FX Revaluation Engine**: Revaluation must use modular DDD services in `financial/fx/services/` (`FXCalculationService`, `FXValidationService`, `FXPostingService`, `FXReversalService`) and domain models in `financial/fx/models/` (`FXRevaluationRun`, `FXRevaluationLine`, `FXRateSnapshot`, `FXApprovalWorkflow`).
- **Period Close Automation**: Automated revaluation and posting MUST be integrated inside `PeriodControlService.close_period` and dated strictly at `period.end_date`.
- **Period Re-open Audit Trail**: Reopening a closed period MUST trigger an audit-compliant reversal entry (`FXReversalService.reverse_run`) to preserve audit trail without hard-deleting posted entries.
- **Idempotency & Concurrency Lock**: Active runs must be guarded by condition-based unique constraints (`VALIDATED`/`POSTED`) and source hashes (`source_hash`) to prevent double-posting or race condition edits.
- **Rate Age Guard**: If an exchange rate age > 7 days, mandatory CFO approval (`RATE_OVERRIDE_APPROVAL`) is required before validation and posting.

## 10. System Unified Toastr & UI Notification Standard
- **System Toast Notification Helper**: For AJAX notifications and dynamic feedback, views MUST use the system unified helper `window.showNotification(message, type, title)` (or `window.showToastr(message, type)`).
- **Toast Delay & Animation Completion**: When initiating a page reload after a Toast notification, `setTimeout` MUST wait at least `3100ms` (3.1 seconds) to allow Toastr's 3-second progress bar animation to complete 100% to the end smoothly before reloading.


