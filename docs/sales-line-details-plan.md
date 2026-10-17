# Configurable Sales and Purchasing Line Details: Implementation Plan

Date: 2026-10-16  
Revised: 2026-10-17  
Status: Proposed; implementation has not started.  
Evidence: Static inspection of the current local source. No application browser, database migration, production operation, or runtime acceptance test was performed.

Review integration: The strict source-based review is incorporated throughout this revision and tracked in section 11. All necessary existing scope, validation, conversion, output, testing, and recovery requirements are retained. Superseded behavior is identified explicitly rather than left as contradictory implementation instructions. The user resolved historical reprinting on 2026-10-17: historical documents retain their snapshots; settings changes must not rewrite historical output.

Second review integration: Section 12 adds five remaining implementation gaps: actual snapshot storage, issuance/correction behavior, dispatcher output parity, attachment-cache invalidation, and incomplete-PDF rejection. The historical snapshot decision remains accepted. The issuance boundary and correction behavior are pending product choices; adding this review does not authorize either freezing all currently editable documents or silently changing historical snapshots.

Third review integration: Hidden snapshot content, warehouse-split lineage, a concrete print-layout acceptance fixture, explicit renderer completion status, and an executable task map are integrated into their functional sections below. Sections 11-12 retain the rationale and evidence; they are not a separate backlog. No necessary scope or verification requirement is removed.

## 1. Objective and assumed meaning

Add an optional **Details** field to each quotation, sales order, sales invoice, purchase order, and purchase invoice line. It describes the particular transaction line, such as dimensions, material, color, finishing, or delivery specifications. Sales details are customer-facing; purchasing details describe specifications agreed with the supplier. The Arabic UI label is `تفاصيل`; the English label is `Details`.

Each of the five document types has an independent visibility setting, grouped under **Line Details**, with Sales and Purchasing subsections. One setting per document controls entry, detail-screen display, and new/unissued print/PDF output together. Historical reprints retain their issuance snapshot under section 11. There is no persistent master switch. Storage and copying remain independent of visibility. These decisions incorporate the follow-up product discussion. Presentation settings do not alter the API data contract.

This plan assumes a description column within document lines, rather than an action column linking to another screen. That interpretation is a product assumption, not an existing system contract.

The product name remains the product name. Document-level notes remain document-level notes. Product descriptions, custom fields, and pricing snapshots must not be repurposed as line details.

Example: two lines using the same product can have different details and must remain separate:

| Product | Details | Quantity |
|---|---|---:|
| Business cards | Matte finish, front and back, Ahmed artwork | 1,000 |
| Business cards | Gloss finish, front only, Mona artwork | 500 |

## 2. Current architecture and evidence

Paths below are relative to the repository root. Line references describe the inspected revision and can move during implementation.

| Area | Current evidence | Consequence for this change |
|---|---|---|
| Quotation lines | `sale/models/quotation_item.py:7`: `QuotationItem` has product, quantity, price, tax, discount, and `price_snapshot`; no line description field. | A real persisted field is required. |
| Main invoice lines | `sale/models/sale_item.py:7`: `SaleItem` has warehouse and cost center as well as financial fields; no line description field. | Store details on each invoice line without affecting warehouse selection. |
| Intermediate orders | `sale/models/sales_models.py:195`: `SalesOrderItem` has no line description field. | Details must survive this intermediate document. |
| Alternate invoice model | `sale/models/sales_models.py:315` and `sale/services/sales_service.py:448`: `SalesInvoiceItem` is created from an order line. | Supporting only `SaleItem` would leave another invoice creation path uncovered. |
| Main invoice service | `sale/services/sale_service.py:207`, `:269`: `_add_sale_item` constructs `SaleItem`; `:507` deletes and recreates lines during update. | Every create/update payload must carry details; a model field alone will lose data on edit. |
| Text-only invoice edits | `sale/services/sale_service.py:433`, `:507`, `:522`, `:536`: the current general update restores stock, recreates lines, and produces accounting/stock updates. | A details-only edit needs an explicit branch within the permitted update flow that preserves line IDs and creates no financial or stock events. |
| Quotation writes | `sale/quotation_views.py:168`, `:253`, `:444`, `:531`: parallel POST arrays, explicit create calls, deletion and recreation on edit. | Both quotation write paths need parsing, validation, and persistence. |
| Invoice input | `sale/views.py:50`, `:283`, `:1478`: posted-line extraction and separate create/edit payload construction. | Include details in error redisplay as well as successful writes. |
| Direct conversion | `sale/quotation_views.py:1153`: an explicit mapping copies quotation lines into `SaleService.create_sale`. | Add details to this mapping. |
| Order conversion | `sale/sales_order_views.py:1191`, `sale/views.py:421`: order prefill and order-based invoice initialization contain separate mappings. | Verify the actual receiving path; changing an unused prefill dictionary is insufficient. |
| Delivery conversion | `sale/delivery_note_views.py:370`: delivery conversion builds a session payload and redirects with `from_dn`. | End-to-end source consumption needs verification before claiming delivery conversion preserves details. |
| Invoice duplication | `sale/views.py:2134`: duplicate lines are serialized explicitly into JSON. | Copy details into the new invoice, independently of the original. |
| Dynamic rows | `static/js/product_picker.js:113`, `:279`: the shared product picker creates and rebuilds rows for multiple document types. | Add field support with explicit document scoping and preservation rules. |
| Ambiguous input identity | `static/js/product_picker.js:112` falls back from `item_id` to generic `id`; `sale/views.py:100` onward and `:2134` use product IDs in serialized `id` fields. | Define separate product, current-line, and source-line identities before implementing hidden-data preservation. |
| Detail screens | `templates/sale/quotation_detail.html:550`, `templates/sale/sale_detail.html` render line tables. | Add a conditionally visible details column; include the sales order intermediary. |
| Print layout | `templates/shared/print_base.html:704` defines the common table header; child templates supply body cells. | Header and body must change together; avoid adding a header to unrelated documents. |
| Shared print consumers | Quotation, sale, sales order, delivery note, and purchase print templates extend `shared/print_base.html`. | Unconditional shared-template changes would affect other documents. |
| PDF output | `sale/views.py:1301`, `sale/quotation_views.py:1002`, `utils/pdf_utils.py:477`: HTML output and a separate ReportLab fallback. | Both normal and fallback document output must preserve details. |
| Snapshot implementation evidence | Inspected sales/purchase print and download paths read live document/items; line `price_snapshot` fields describe pricing, not a complete issued-document copy. | Do not infer that the accepted historical snapshot policy is already implemented. Inventory actual stored artifacts or add the minimum required feature snapshot support. |
| Independent dispatch output | `core/services/document_dispatcher.py:782` builds PDFs separately; its PO path uses `order` and `doc_type="po"`, while `purchase/views/po_views.py:751` uses `po` and `purchase_order`. | Download fixes alone do not cover dispatched attachments. Normalize feature-specific context/type handling across both paths. |
| Attachment cache | `core/services/document_dispatcher.py:1085` keys cached media by document identity and integer-second header `updated_at`. | A line-only edit can leave a stale attachment cache entry. Track the effective output revision/content rather than assuming line saves update the header. |
| Last-resort PDF | `utils/pdf_utils.py:606` can return a minimal PDF with only document/company/total, or a skeletal PDF, after richer rendering fails. | A PDF response is not proof of complete output. Do not accept or dispatch an incomplete artifact as a valid copy of an in-scope document. |
| Narrow receipts | `templates/sale/sale_print_thermal.html` has an independent layout. | Show details beneath the item name rather than squeezing in another narrow column. |
| Purchasing lines | `purchase/models/purchase_item.py:7`, `purchase/models/procurement_models.py:137`, `:301`: `PurchaseItem`, `PurchaseOrderItem`, and `SupplierBillItem` have no dedicated details field. | Cover the main purchasing UI and the alternate supplier-billing path. |
| Purchase invoice writes | `purchase/views/purchase_views.py:453`, `:994`, `:1043`, `:1094`: explicit arrays, update-or-create keyed by purchase/product, and deletion of removed lines; `purchase/services/purchase_service.py:123` creates lines independently. | Update both views and service entry points; purchase/product identity cannot distinguish repeated-product lines. |
| Purchase order writes | `purchase/views/po_views.py:222`, `:428`, `:284`, `:503`; `purchase/services/procurement_service.py:135`. | Cover both order views and the procurement service. |
| Purchase conversions/copy | `purchase/views/purchase_views.py:315` onward maps orders and GRNs into invoice prefill; `:1549` serializes duplicates; `purchase/views/po_views.py:799` starts order duplication. | Preserve details across both prefill paths and both duplication workflows. |
| Goods receipt association | `purchase/models/procurement_models.py:232`: `GoodsReceivedNoteItem.po_item` is optional; `purchase/services/procurement_service.py:350` onward creates supplier bill lines from receipts. | Resolve the exact source line and handle receipts without an order explicitly; product ID alone is insufficient. |
| Purchase output | `templates/purchase/purchase_print.html` extends the shared print base; `templates/purchase/po_print.html` is standalone; `purchase/views/po_views.py:751` requests PDF type `purchase_order`. | Update the standalone order header/body and verify PDF context/type dispatch separately. |
| Operations settings | `core/views/main_views.py:453`, `:498`; `core/forms.py`; `templates/core/operations_settings.html`; `core/models.py:176`, `:216`. | Extend the existing settings form, initial values, save path, typed boolean lookup, and cache invalidation. |

`sale/services/sales_document_service.py` aliases `SalesService`. The main `Sale` UI uses the separate `SaleService` in `sale/services/sale_service.py`. These services must not be confused or consolidated as part of this feature.

The inspected `api/serializers.py` and `api/viewsets.py` do not expose dedicated sale/quotation serializers. Purchasing does have `PurchaseItemSerializer` nested read-only in `PurchaseDetailSerializer`: add details to the existing supported read contract under its existing authorization, independently of UI visibility flags. The field's presence and value must not change when an administrator hides a column. This supersedes the earlier proposal to filter the purchasing response by document visibility. Do not create a new public endpoint or nested-write API solely for this feature. Recheck actual integration entry points when implementing.

## 3. Recommended data contract

Use one consistent field name, `details`, on:

1. `QuotationItem`.
2. `SalesOrderItem`.
3. `SaleItem`.
4. `SalesInvoiceItem`, as an independent invoice snapshot for the alternate service path.
5. `PurchaseOrderItem`.
6. `PurchaseItem`.
7. `SupplierBillItem`, as an independent snapshot for the procurement-service billing path.

Recommended definition: `TextField(blank=True, default="", max_length=2000)` with a shared server-side validator/normalizer. The 2,000-character limit is a proposed product limit. It should be the same across all seven core models, forms, services, and UI inputs.

If the optional goods-receipt extension in section 10 is implemented, add an eighth snapshot field to `GoodsReceivedNoteItem`. Do not require a receipt field merely to copy order details into a supplier invoice: the core path can resolve the associated `po_item` and snapshot it at invoice creation. Receipt specifications at the time of receiving require the optional receipt snapshot rather than a live order lookup.

Validation rules:

- Missing key or `None` becomes the empty string for new lines and legacy callers.
- Accept plain strings only; reject arrays, objects, or numeric values with a clear validation error.
- Normalize line endings; preserve meaningful internal spacing and line breaks.
- Remove outer whitespace consistently; reject unsupported control characters.
- Reject overlong content without silent truncation and identify the line with the error.
- Apply validation in the server entry points and service paths. `max_length` on a Django `TextField` does not make direct ORM `.create()` run model validation.
- Keep the field out of price, discount, tax, inventory, and accounting formulas.

Existing rows start empty. Do not backfill from the current product description: it would invent historical specifications that were never recorded on those documents. No index or uniqueness constraint is needed.

Use additive migrations after the actual current migration leaves in both apps. The inspected sale migration directory ends at `0007_salereturnitem_warehouse_alter_salereturn_warehouse`; purchase ends at `0003_initial`. Verify both leaves again before generating migrations.

### Separate stored data, visibility, and issued output

Maintain three distinct concepts within the existing document design:

| Layer | Required contents and behavior |
|---|---|
| Line data and captured line data | Preserve every line's details, including hidden text, with stable line/source associations and ordering. Capturing a document must not filter stored details by visibility. |
| Visibility choice | Record whether the column appears for that document/representation, independently of the stored text. The five settings and historical snapshot policy determine the effective choice. |
| Issued output | Render or retain the authorized issued representation, showing text only when its captured visibility allows it. A PDF with hidden details is not a replacement for the underlying line-data capture used for conversion. |

This clarifies the earlier phrase "details included in the issued output": it describes presentation, not permission to discard hidden text. Example: quotation details visible, sales order details hidden, invoice details visible must preserve the text through order capture and subsequent conversion. Capture text even when the order PDF has no details column. Do not send hidden text to browser initialization JSON merely to preserve it; authorized server-side data resolution remains responsible for copying it.

## 4. Lifecycle and ownership rules

| Operation | Required behavior |
|---|---|
| Create a quotation or direct invoice | Save exactly the details attached to each submitted line. |
| Edit a document | Reload existing details; update details-only edits in place. Preserve text through any still-required general line recreation; failed submissions retain submitted text. |
| Quotation to invoice | Copy quotation line details into the new invoice line. |
| Quotation to sales order | Copy details into order lines and expose them in the intermediate form so they cannot be silently discarded. |
| Sales order to invoice | Copy the relevant order line details, including partial invoicing. |
| Delivery note to invoice | Resolve details from the correct `so_item`; preserve the actual delivered-line association. |
| Alternate invoice service | Default from `so_item.details` when omitted; store a snapshot on `SalesInvoiceItem`. |
| Duplicate invoice | Copy details; subsequent changes to either document do not mutate the other. |
| Create/edit a purchase order or invoice | Save and reload supplier-facing details using the shared validation contract in both views and services. |
| Purchase order to purchase invoice | Copy details from the matching order line, including partial quantities. |
| Goods receipt to purchase invoice or supplier bill | Use the receipt snapshot when the optional extension is enabled; otherwise copy from the exact associated order line. With no source, use explicit new-line input or empty text. |
| Duplicate purchase order or invoice | Copy details into independent new lines, including when visibility is disabled. |
| Purchasing to sales | Never copy supplier-facing details automatically into customer-facing sales documents. |
| Disable or re-enable a document setting | Hide or restore entry/display/output without clearing or rewriting stored details. Conversion continues copying hidden details. |
| Same product repeated | Preserve separate descriptions by row identity/index; never map solely by product ID. |
| Change quantity, price, tax, warehouse, or customer | Preserve the line's typed details through recalculation or refresh. |
| Replace product in a row | If details are populated, require an explicit Keep details / Clear details choice before replacing the product. Cancel leaves the row unchanged. Refreshing or reselecting the same product preserves text without prompting. Do not automatically seed product descriptions. |
| Split a line across warehouses | Preserve verified source lineage and copy details server-side into every resulting line even when the column is hidden. Existing originals retain their IDs; new split lines receive new IDs. |
| Delete a line | Delete its details with that line; prevent details shifting to an adjacent row. |

The recommended contract does not add standalone description-only lines without a product. A trailing row with text but no product should produce a validation message rather than being silently removed by `sanitizeTrailingEmptyRows`.

For backward compatibility, distinguish an omitted `details` key from an explicit empty string when updating existing lines. Existing details must not disappear when an older caller omits the field. Preserve omitted values using a verified existing line ID. If a caller cannot identify the existing line unambiguously, require a complete supported payload instead of guessing by product ID. Browser forms should submit a details entry for every line, including empty entries.

Required purchasing dependency: `purchase_update` currently calls `PurchaseItem.objects.update_or_create(purchase=purchase, product=product, ...)`, and its stock comparison bookkeeping uses product-keyed dictionaries. Before supporting repeated products with different specifications, replace line matching with verified document-owned line IDs and account for quantities by product when computing stock deltas. Keep separate lines for details; aggregate only where inventory calculations require it. Regression-test existing duplicate-product data, edits, removals, and rollback. This dependency is part of feature correctness, not an unrelated procurement redesign, and can affect the effort estimate.

Existing document permissions and status restrictions continue to govern edits. This feature does not create an alternative endpoint for editing confirmed or posted financial documents. Copying details must not change the source document.

Visibility is not an authorization boundary. An authorized backend caller may preserve or submit details while their UI is hidden; ordinary document permissions and validation still apply. A hidden form must omit the details key rather than submit empty hidden inputs that clear existing values. Existing-line identity is therefore required for preservation through destructive updates. Test unrelated edits made while details are hidden.

### Explicit line identity and preservation procedure

- Use `product_id` only for the product; use an explicit `item_id` for an existing line of the document being edited. Never derive a line ID from generic `id`, product ID, or array position.
- Keep source associations separate (`source_item_id` plus source document/type, or the existing typed relationships such as `so_item_id` / `po_item_id`). A source line is not a target line authorized for update.
- On new or duplicated target documents, target `item_id` must be empty. Copy the source details into new lines server-side when hidden; do not depend on descriptions having been sent in browser initialization JSON.
- Validate every supplied current line ID against the current document and allowed user scope. Reject foreign, duplicate, stale, or ambiguous IDs; do not silently match by product.
- Before any destructive write, load existing lines and resolve omitted details by verified current-line ID. Capture this mapping before deletion, then build the complete validated target payload.
- Preserve omitted text only where line identity and product continuity are verified. A product replacement must carry the explicit keep/clear decision; an omitted text value alone is not consent to attach old specifications to a different product.
- Carry IDs and submitted details correctly through initial forms, dynamic rows, error redisplay, reorder, deletion, and warehouse split. Keep target IDs distinct when one source creates multiple new lines.

### Warehouse split: explicit lineage and hidden-text resolution

`templates/sale/sale_form.html:1324` builds `cloneItemData` manually before passing it to `ProductPicker.renderRow`. Updating the shared picker alone will not propagate details or source identity through that producer.

- Add lineage to the split payload: a verified existing source-line association when available, or a stable source-row key for a parent created within the same submitted form. A local row key identifies a submitted row; it never authorizes access to a database line.
- For a saved parent, resolve omitted hidden text on the server from the verified parent/source association. For an unsaved parent, resolve from the validated parent row in the same submission, or its verified upstream document source. Do not use product ID to recover the text.
- Preserve the parent's permitted current details for the children. Explicit validated child edits are allowed only within the ordinary edit rules; omitted child details inherit, whereas explicit empty text retains the established clear-value semantics.
- Keep the original existing line ID on the remaining original row; every newly created split row has no target `item_id` until persistence. Source identity and target identity must not be conflated.
- Validate all lineage before writes; reject foreign, missing, or cyclic parent references rather than silently dropping or misassigning text. Preserve the existing governed quantity/warehouse validation.
- Verify saved and unsaved parents, two equal-product parents with different details, repeated splitting, deletion/reorder, and hidden-column submission. Details preservation must not require exposing hidden text in HTML or JSON.

### Details-only update behavior

Within the existing authorized update service/view flow, detect a details-only edit by comparing the complete normalized persisted document and line inputs, not by trusting a client-side flag. Product/line membership, quantity, price, discounts, taxes, warehouse, currency, customer/supplier, and any other field that changes financial or inventory behavior must be unchanged.

For a verified details-only change, update only the text on existing lines in one transaction, preserving line IDs, source associations, and existing journal/movement records. Do not call the general stock reversal/recreation or journal creation path. Keep existing document permissions, paid/closed/cancelled restrictions, and other status guards; this is not a new permission or a route around existing locks. Apply the same no-financial-side-effects requirement to purchase documents and any other supported details-only edit path.

For mixed edits, retain the applicable governed general update flow, with the identity/preservation rules above. Relevant comparison and writes must use a consistent transactional view of the document; an intervening financial change must not be overwritten through the text-only branch.

The text-only branch applies only where editing is permitted under existing restrictions and the issuance/correction policy to be resolved in section 12. It must not overwrite an issued snapshot. A permitted line-only change that affects draft/current output must also invalidate or advance the effective output/cache revision without invoking the general financial update flow.

## 5. UI and output design

### Entry forms

- When the relevant setting is enabled, add a labeled, optional, two-row textarea adjacent to the product area of each line in all five core document forms; on small screens it spans the row width.
- Preserve usable widths for quantity, unit price, and totals. The current forms use Bootstrap row layouts, rather than a literal table that only needs one extra `th`.
- Add the field to both server-rendered initial/edit rows and `ProductPicker.renderRow` / `renderItems`.
- Pass an explicit per-document visibility option into the shared picker. Include sales orders, purchase orders, and purchase invoices; the picker's broad `purchase` type alone cannot distinguish the two purchasing settings.
- Update `SaleItemForm` if it remains a supported entry point; do not rely on it to validate the separate array-based views.
- Ensure empty details still submit a position in `details[]`; validate array alignment before mutating documents. Legacy requests may omit the whole details array; malformed partial arrays must not shift values to another line.
- Distinguish explicit product replacement from same-product stock/pricing refresh. Offer Keep details / Clear details only for a real replacement with populated text; avoid silent loss or accidental reuse of old specifications.

### Detail screens and printing

- Add a dedicated **Details** column after Product/Service in all five core document line tables when the corresponding setting is enabled. Disabled output must omit the header, cells, and any details text rather than hide them with CSS.
- Use a neutral dash for empty details on screen. Keep the table structure consistent across empty and populated lines.
- For A4 output, enable the extra header and matching cells only for document contexts that implement it. Prefer a small overridable header block or an explicit context flag over a global unconditional column.
- Update `sale_print.html`, `quotation_print.html`, `sales_order_print.html`, `purchase_print.html`, standalone `po_print.html`, and the ReportLab table path together. Make fallback headers, cell counts, context resolution, and widths conditional on the document type and its setting.
- Verify fallback handling for both order types explicitly: the current generic fallback looks up `sale`, `quotation`, or `purchase`, whereas purchase-order PDF uses `purchase_order` with a PO context. A successful HTTP/PDF response alone does not prove the order lines or details were rendered.
- Keep the narrow thermal layout stacked: product name, details, then the existing numeric presentation. Respect the sales-invoice setting.
- Preserve line breaks, wrap long words, and do not clip or ellipsize contractual details in customer output. Avoid forcing very long rows into an unbreakable page region.
- Preserve Arabic/English labels and RTL/LTR support. Existing fonts must never change.
- Reuse existing semantic classes and CSS variables declared in `:root`. No new hardcoded colors, gradients, decorative effects, or unnecessary animation.
- Treat sales details as customer-visible and purchasing details as supplier-visible. Never automatically populate them from internal pricing snapshots, supplier costs, margin breakdowns, or production secrets.
- Include independently generated dispatcher attachments in output scope, not just print/download views. Reuse the same effective details content, visibility, and source snapshot selection across channels as specified in section 12.
- For the five document types, reject incomplete generated PDFs as successful customer/supplier output. Reuse a valid matching saved artifact if available; otherwise return an explicit generation failure and prevent attachment dispatch. Keep the existing complete ReportLab fallback where it satisfies the content requirements.

### Print-layout acceptance fixture

The shared A4 header already assigns fixed widths to code, quantity, price, discount, and total. Do not append another fixed-width column and assume that product names and details will remain readable.

Before accepting the layout, generate an offline representative fixture with code and discount enabled, a long product name, Arabic multiline details up to the proposed limit, a long unbroken token, English text, repeated products, and enough rows to cross a page. Allocate the remaining printable width between product and details, adjusting the affected column proportions rather than shrinking existing typography or changing fonts. Record the chosen widths/proportions and rendered evidence as implementation deliverables; numerical values are not approved by this plan alone.

Acceptance requires visible unclipped names/details, aligned headers and cells, readable numeric columns, deliberate page breaks without overlapping totals, and correct Arabic/English flow. Test both column-enabled and disabled output, primary and complete fallback PDFs. Keep the thermal stacked layout and existing font choices. Use offline rendering for review; browser execution still requires an explicit user request.

### Safe text handling

- Use Django's escaped text rendering; never apply `safe` to details.
- Pass Python structures through Django `json_script` for affected form initialization paths rather than embedding unescaped JSON into script tags. Existing `|safe` payloads must not become the transport for arbitrary details text.
- Populate textareas through `.val()` and ordinary text through `.text()` / `textContent`; do not interpolate details into generated HTML strings.
- Escape text before constructing ReportLab `Paragraph` markup, then translate line breaks deliberately.
- Include `</script>`, `</textarea>`, angle brackets, ampersands, quotes, and Arabic multiline content in verification.

## 6. Implementation phases and completion gates

| Phase | Deliverable | Completion gate |
|---|---|---|
| 0. Verify prerequisites | Trace actual conversions; define identities; reproduce repeated-product purchase behavior; inventory actual snapshots; map lifecycle/correction behavior and download/dispatcher/cache paths. | No conversion or snapshot storage is assumed operational without evidence; required repairs and estimate impact are explicit. Issuance/correction choices are recorded before dependent implementation; the accepted historical snapshot rule remains intact. |
| 1. Contract and schema | Seven core fields, shared validation, additive migrations, source-line identity contract, five setting keys. | Old rows and old creation callers remain valid; invalid details fail explicitly. |
| 2. Identity, persistence, and settings | Verified current/source line IDs; purchasing repeated-product fix; text-only update branch; sales/purchasing views/services; alternate invoices/bills; settings form and cache handling. | Supported backend paths round-trip details; text-only edits create no financial/stock events; settings persist independently; hidden details survive unrelated edits. |
| 3. Conversion and recovery | Sales conversions, PO/GRN-to-invoice mapping, both purchasing duplication paths, validation-error redisplay. | Exact text remains attached to its source line; sales and purchasing descriptions stay separate. |
| 4. UI and documents | Five forms/detail screens, shared picker, conditional headers, standalone PO print, A4/complete PDF fallback, thermal receipt, unified feature-output selection for dispatch and media cache. | Applicable current/snapshot policy is consistent across channels; stale or incomplete attachments cannot pass as valid output; unrelated consumers remain correct. |
| 5. Verification and rollout | Focused regression tests, migration verification on a disposable database, representative output artifacts. | Functional checks pass; visual acceptance is separately recorded. |

Do not release a schema-and-form-only implementation while conversion or fallback output still drops details.

Phase 0 must distinguish UI-reachable paths, service-only supported paths, and test-only usage. Preserve the seven-model data coverage unless source evidence justifies an explicit scope revision, but do not invent alternate invoice/bill screens merely because their models exist. Resolve required financial/source-identity prerequisites before building their dependent UI behavior.

### Executable task map and reading order

Sections 3-5 define the operative data, lifecycle, and presentation requirements; this table connects them to implementation locations and acceptance gates. Section 7 remains the complete verification matrix. Sections 11-12 retain review rationale and evidence and must be read through the corresponding tasks, not implemented again as duplicate work. Earlier wording about capturing only visible text is clarified by section 3's three-layer contract. The issuance/correction decision remains open; the accepted historical snapshot rule is not reopened.

| Task | Implementation locations | Required result and acceptance gate |
|---|---|---|
| T01. Resolve prerequisites | Sales/purchase model states; conversion views and receivers; existing artifact storage | Verified path/issuance inventory, explicitly recorded correction decision before dependent behavior, and assessed repair scope. |
| T02. Store text and captures | Seven line models and migrations; minimal verified snapshot producer/reader | Shared validation; hidden text, line associations/order, and visibility stored independently; existing historical artifacts unchanged. |
| T03. Preserve identities and split lineage | `static/js/product_picker.js`; all affected server/dynamic form rows and parsers; `templates/sale/sale_form.html` split producer | Explicit product/current/source identities; server-side hidden-text preservation; safe splitting of saved/unsaved rows and duplicate products. |
| T04. Update without financial side effects | Sales/purchase update services/views and relevant save hooks | Permitted text-only edits preserve line IDs and create zero financial/stock events; output/cache bookkeeping stays current. |
| T05. Repair purchasing row matching | `purchase/views/purchase_views.py`; related persistence and stock-delta handling | Separate repeated-product lines with correct aggregate quantity effects and transaction rollback. |
| T06. Propagate through lifecycle | Quotation/order/delivery/purchase/GRN conversion mappings and receivers; duplication; alternate invoice/bill services | Correct target line details through all supported paths, including a hidden intermediate document and captured hidden source text. |
| T07. Configure independently | `core/forms.py`; `core/views/main_views.py`; operations settings template and typed settings/cache handling | Five independent controls; missing/disabled module inputs preserved; API data unaffected; optional Apply to all remains only a form action. |
| T08. Render consistently | Five core forms/detail screens; shared and standalone print templates; thermal; `DocumentDispatcher` contexts | Shared effective feature-output selection, historical policy respected, and the representative layout fixture passes offline review. |
| T09. Handle PDF completion and media reuse | `utils/pdf_utils.py`; affected view/dispatcher adapters and media cache | Explicit complete/incomplete/failed generation result for in-scope callers; no summary-only dispatch; fresh attachments after permitted edits. |
| T10. Verify and release together | Section 7 test suites; disposable migration database; offline output artifacts | All required sales/purchasing contracts pass; visual limits and unresolved dependencies reported honestly; no partial release marketed as the full feature. |

Build a complete quotation-to-sales-order-to-invoice scenario first to verify the shared design, then complete purchasing and the remaining paths. This is an implementation order, not a reduced deliverable: all five core document types and their necessary coverage remain required before full release. Keep the goods-receipt extension optional.

## 7. Verification matrix

| Group | Required acceptance cases |
|---|---|
| Validation | Missing, empty, `None`, Arabic, English, multiline, exactly 2,000 characters, 2,001 characters, invalid types, control characters. |
| Persistence | Create/edit/reload all five core documents; direct service calls; alternate sales invoice and supplier bill creation. |
| Recovery | Invalid document form, rejected line validation, server redisplay, deleted middle row, trailing row with details but no product, old caller omitting details. |
| Identity | Two rows for one product with different details; deletion and reorder; warehouse splitting; partial invoicing and delivery association. |
| Identity rejection | Product ID mistaken for line ID; line ID from another document; duplicate/stale IDs; source ID used as target ID; duplicate/new documents with inherited target IDs. Fail before mutation and leave data unchanged. |
| Product replacement | Real replacement with populated details requires keep/clear choice; cancel preserves the row; same-product refresh does not prompt or erase text. |
| Conversion | Quotation to invoice; quotation to order to invoice; delivery to invoice; PO/GRN to purchase invoice; GRN to supplier bill; invoice/order duplication; source changes after copying do not affect snapshots. |
| Financial invariants | With identical financial inputs, varying only details leaves totals, taxes, discounts, journal values, customer balance deltas, and stock quantities identical. Verify within existing fixtures rather than redesigning financial behavior. |
| Text-only event invariants | Details-only edits preserve line IDs and existing journal/movement links and create zero journal entries, reversals, stock movements, or balance/subledger events. Unchanged final totals alone do not satisfy this gate. Verify mixed financial/text edits still use the governed general path. |
| Access | Existing denied-read/denied-edit rules still apply to the new field and document outputs. |
| Text safety | Script/textarea terminators, markup-like strings, quotes, ampersands; verify literal text and valid JSON/HTML output. |
| Output | Normal print, primary PDF, forced ReportLab fallback, thermal output, Arabic/English, long text, multiple pages, code visible/hidden, discount visible/hidden, price-restricted views. |
| Settings | Each of the five flags independently controls its form/detail/print/PDF output; all off, all on, and mixed combinations; missing keys use the documented default; typed false strings remain false; save/reload/cache invalidation work. |
| Hidden-data preservation | Enable, enter details, disable, edit another field, convert/copy, re-enable: exact details remain. A target document can show details even when the source and intermediate document hide them. |
| Hidden snapshot propagation | Capture an intermediate order while its details are hidden, then convert into a details-enabled invoice: the exact source text survives. The capture contains hidden line data; the hidden PDF/HTML/initialization JSON does not expose it. |
| Split lineage | Saved and unsaved parent rows; hidden details; repeated-product parents with distinct text; repeated splits, reorder, and deletion. Original IDs remain correct, child target IDs are new, and invalid lineage fails before writes. |
| Permission/module regression | Unauthorized users cannot modify settings; disabled module fields are preserved rather than reset by unchecked or missing inputs. Visibility flags do not enable modules or bypass existing permissions. |
| Shared regressions | All five core output tables stay aligned for enabled/disabled flags; delivery/receipt output remains unchanged unless its optional extension is selected. Shared picker calculations and warehouse behavior remain correct. |
| Purchasing isolation | Varying details leaves GRNI, price variances, matching quantities/amounts, supplier balances, and inventory posting unchanged; no automatic purchasing-to-sales copying. |
| Purchasing repeated products | Two lines for the same product retain separate details and IDs through edit/delete/reorder. Quantity changes use correct aggregate stock deltas. A failed update rolls back both text and financial/stock changes. |
| API stability | Purchasing details remain available in the existing authorized read contract whether the UI flag is on or off; flag changes do not remove fields or blank stored values in API output. |
| Historical output | Test stored PDFs separately from regenerated output; implement the selected policy from section 11 and verify toggling settings after document issuance. No historical behavior is accepted by assumption. |
| Snapshot evidence and lifecycle | Verify actual storage/readback of captured details, visibility, line association/order, and capture metadata; no dependency on live product text. Exercise issuance, permitted edits, post-issuance corrections, conversions, and missing legacy artifacts under section 12's resolved contract. |
| Dispatch parity | For each supported in-scope document, compare effective detail content and visibility in print/download and dispatcher-generated attachments, including purchase-order context/type normalization and exceptions. Mock external delivery; do not send messages. |
| Attachment cache freshness | Generate/cache an attachment, make a permitted text-only edit, then generate again: the effective new output must not reuse stale media. Include two edits within one second, unchanged-output reuse, and historical snapshot reuse. Mock upload/cache dependencies. |
| Complete-output failure | Force primary rendering failure, then complete fallback failure. A valid matching saved artifact may be reused; otherwise generation reports failure and dispatch does not treat the minimal/skeletal PDF as a successful document. Verify full line/details coverage for any fallback accepted as complete. |
| Renderer status contract | Complete primary/fallback results are accepted; explicit incomplete/failed results are not promoted to success by any affected adapter or exception handler. Verify generated content in tests rather than introducing a general runtime PDF analyzer. |
| Print-layout fixture | Long product name, code/discount on, Arabic multiline/long-token details, English, multiple pages, enabled/disabled column, primary/complete fallback. Existing typography remains readable without font changes or shrink-to-fit. |
| Migration | Apply the real migration on old-schema sample data in an isolated database and verify existing lines become empty without changing financial fields. |

Extend existing suites where appropriate: `sale/tests/test_quotations.py`, `test_sale_service.py`, `test_sales_order_and_delivery_views.py`, `test_enterprise_sales_lifecycle.py`, `test_multi_warehouse_sales_views.py`, and the quotation/order feature-toggle tests. Add a focused `test_line_details.py` for new cross-path contracts rather than scattering duplicate assertions.

For purchasing, extend `purchase/tests/test_purchase_orders_workflow.py`, `test_purchase_service.py`, `test_purchase_system_unified.py`, and `test_sprint6_procurement_engine.py`; add focused line-details tests for purchasing views, service creation, copying, and source identity. Extend operations-settings tests under `core/tests` and the existing purchasing API read tests where applicable.

The repository's `pytest.ini` sets `--no-migrations` and `--reuse-db`. Passing its normal suites does not validate the migration. Run migration checks separately against a disposable database; never reuse the working ERP database for this purpose.

Example focused command after implementation:

```powershell
python -m pytest sale/tests/test_line_details.py sale/tests/test_quotations.py sale/tests/test_sale_service.py sale/tests/test_sales_order_and_delivery_views.py tests/test_quotations_feature_toggle.py tests/test_sales_orders_feature_toggle.py
```

Use repository test settings and isolated fixtures. Do not send emails, WhatsApp messages, or production requests as part of verification. Inspect generated attachment output locally and use mocked dispatcher/upload calls to verify parity, cache freshness, and failure blocking.

Browser execution requires an explicit user request under the project instructions. Until then, use static inspection, request/template tests, and offline output checks. Record browser interaction and final visual acceptance as pending when they have not actually been performed.

## 8. Rollout and recovery

1. Review the final diff and confirm its scope against this plan.
2. Validate the additive migration on representative old data in an isolated database, preferably matching the deployment database engine.
3. Back up the target database through the existing operational process before any separately authorized deployment.
4. Apply the schema before activating application code that reads the new fields; account for worker restart and static-asset versioning for `product_picker.js`.
5. Verify one new quotation, sales order, sales conversion, sales invoice edit, purchase order, purchase invoice, procurement conversion, duplicate workflow, and each output path in the deployment acceptance environment. Verify independent settings and hidden-data preservation before enabling the feature for a business.
6. If rollback is needed, retain the additive columns and their content while reverting application code. Do not reverse the migration after details have been entered without exporting that data and explicitly accepting its loss.

Local implementation and tests do not certify production readiness. Database-engine lock duration, deployed PDF dependencies, and browser layout require environment-specific evidence.

## 9. Scope boundaries and estimate

The core scope is the five sales and purchasing document line lifecycles, independent visibility settings, and the alternate invoice/bill models that would otherwise lose details. Sales order display is included. Goods-receipt display/snapshot is the optional extension in section 10; sales-delivery display, search by details, product descriptions, rich text, attachments, tax integration payload changes, and general sales/procurement redesign remain separate enhancements.

Do not add a separate details column to top-level document lists: a document contains many lines, so there is no single unambiguous value for such a list column.

Previous indicative effort for one developer: **5-8 working days** for the five core document types, plus approximately **1-2 additional working days** for the optional goods-receipt extension. These figures are retained as the earlier planning baseline, not a reliable delivery commitment. Re-estimate after phase 0 establishes conversion repair needs, repeated-product purchase changes, verified identity handling, text-only update work, and the selected historical reprint policy. Do not confirm a delivery date before those dependencies are assessed. Unavailable output dependencies can also require additional work; document findings explicitly rather than expanding the feature silently.

The revised estimate must also account for actual snapshot-storage gaps, the selected issuance/correction contract, shared feature-output selection in dispatcher paths, media-cache freshness, and incomplete-output rejection. These are feature dependencies; they are not permission to redesign general document archiving or external delivery integrations.

Final acceptance: details remain editable and readable on permitted documents according to their independent visibility settings, survive every supported conversion/copy/edit path even while hidden, appear in the applicable customer/supplier outputs when enabled, and do not change financial or inventory results.

## 10. Independent visibility settings and optional goods receipts

### Core settings

Add one **Line Details** group inside the existing operations settings, split into Sales and Purchasing. Arabic UI labels below are intentional user-interface copy; implementation documentation remains English.

| Subsection | UI label | Proposed boolean key | Controls |
|---|---|---|---|
| Sales | عروض الأسعار | `show_quotation_line_details` | Quotation entry, detail screen, print/PDF. |
| Sales | أوامر البيع | `show_sales_order_line_details` | Sales order entry, detail screen, print/PDF. |
| Sales | فواتير البيع | `show_sale_invoice_line_details` | Main and alternate sales-invoice presentation, print/PDF, thermal output. |
| Purchasing | أوامر الشراء | `show_purchase_order_line_details` | Purchase order entry, detail screen, standalone print/PDF. |
| Purchasing | فواتير المشتريات | `show_purchase_invoice_line_details` | Purchase invoice and any existing alternate supplier-bill presentation, print/PDF. API data remains independent. |

Recommended initial rollout default: **all five disabled**, preserving the installation's current layout until the business enables the relevant documents. This is a proposed default because no enabled/disabled default was specified in the discussion. A new installation or business preset can explicitly enable any combination; no industry-specific defaults should be invented.

Use the existing `SystemSetting` store and its typed boolean handling, not a separate configuration table. Do not use raw `bool("false")`. Resolve settings once per request/context and pass them explicitly to templates, picker options, and PDF contexts. Keep API data independent of these presentation flags. Use the existing cache invalidation path so saved changes appear on subsequent requests without waiting for the cache TTL. Resolve historical print visibility according to the selected policy in section 11.

The inspected settings save loop currently writes all operations settings with group `sales`. Add the five keys through that existing mechanism or deliberately extend its grouping logic; the UI Sales/Purchasing grouping must not accidentally change behavior of existing settings. Verify `OperationsSettingsForm`, view initial values, form submission serialization, and the actual settings template together.

Keep the existing settings authorization. Hidden or unavailable module controls must not overwrite saved flags with false when an unrelated setting is saved. These flags do not enable disabled sales/purchase modules, modify permissions, or make an unavailable document accessible.

There is **no persistent global on/off switch**. An optional **Apply to all** action may set the five visible switches together, but it must only edit form values until the user saves. Individual switches remain authoritative afterward. This helper is optional convenience, not a sixth stored policy and not required for acceptance.

### Shared behavior rules

1. A document's flag controls input visibility, detail-screen rendering, and new/unissued print/PDF together. Historical print/PDF follows its issuance snapshot, not today's setting. Do not add separate internal/output switches in the first release.
2. Turning a flag off does not erase data, stop copying, or remove columns from the database. Hidden input is omitted and stored values are preserved server-side using source-line identity.
3. Source visibility does not constrain target visibility. Example: quotation on, sales order off, invoice on must still carry and show the original details on the invoice.
4. Sales and purchasing flags are fully independent. Details from purchasing never become sales descriptions automatically, even if both sets of flags are enabled.
5. When disabled, omit details from user-facing HTML and initialization JSON; omit them from print/PDF subject to the selected historical reprint policy. Authorized internal services retain/copy them. The purchasing API remains stable and governed by existing permissions; visibility is a presentation policy, not secrecy enforcement.
6. An existing stored/exported PDF does not change when settings change. Historical output retains its issuance snapshot, including whether details appeared and the text included. Never regenerate it from today's visibility setting or current product text. Section 11 records the accepted policy and legacy handling.
7. A later need for employees to see details while customers/suppliers do not can be handled by a separately scoped internal-versus-print visibility policy. It is not part of the initial five-switch design.

### Goods-receipt extension

Goods receipts exist in this codebase and can be created without `po_item`. They can benefit from details when warehouse staff must verify received specifications, but the discussion did not make receipt display mandatory for every business.

Include this as an explicit optional work package:

- Add `GoodsReceivedNoteItem.details` as a receipt-time snapshot; inherit from the exact purchase order line when present, or accept validated receipt-line text for direct receipts.
- Add a sixth independent control, `show_goods_receipt_line_details`, only when the relevant receipt workflow is available; recommended default remains disabled.
- Update `templates/purchase/grn_form.html`, `grn_detail.html`, receiving/application services, and any actually supported receipt output discovered during implementation. Do not invent a GRN print endpoint.
- Supplier invoices and bills inherit the receipt snapshot when available, preserving specifications at receiving time. Later order edits must not rewrite the receipt or invoice snapshot.
- Keep the free-text details field separate from quality acceptance, discrepancy reasons, stock posting, or three-way matching rules.
- Verify partial receipts, repeated products with different specifications, direct receipts without an order, hidden details, and subsequent invoicing.

The core five-document release must still copy details correctly through existing GRN-to-invoice paths using exact source associations; making receipt display optional does not make that propagation optional.

## 11. Strict review: required corrections and accepted snapshot policy

This section records the constructive review and its implementation consequences. It complements the requirements above; it does not remove financial integrity, permission checks, hidden-data retention, five independent settings, seven-model persistence coverage, normal/fallback/thermal output, migration verification, or the optional goods-receipt package.

| Review item | Concrete evidence or failure example | Required disposition |
|---|---|---|
| Details-only edits invoke financial work | The current sale update restores stock, recreates lines, then creates journal/stock updates even though a text edit should not affect those records. | Add the guarded in-place text-only branch in section 4; assert zero additional financial/stock events and unchanged line identities. |
| Product and line IDs are ambiguous | Picker fallback accepts generic `id`, while error/duplicate payloads use it for product IDs. | Define explicit product/current/source IDs, validate ownership, snapshot omitted details before deletion, and clear target IDs on duplication. |
| Repeated products cannot be treated as one purchase line | Purchase update matches on purchase/product; stock comparison dictionaries also key by product. | Separate line updates by verified line ID; aggregate quantities only for stock deltas; finish focused regression coverage before relying on purchase details. |
| Product replacement can attach stale specifications | Preserving a different product's material/size text silently creates a misleading document. | Replace the earlier unconditional-retention rule with explicit Keep/Clear choice for real product replacement; preserve on same-product refresh. |
| Historical output policy was assumed | Turning a setting off could remove specifications from a newly generated copy of an already-issued invoice. | Resolved by the user: preserve historical issuance snapshots; current settings apply to new/unissued output. |
| UI flags should not change integration data | A screen preference would make the authorized purchasing API omit or blank the field. | Supersede that proposal: keep the API read contract independent of visibility flags. |
| Prefill payloads do not prove working conversion | Delivery conversion writes `prefill_sale_data` and redirects with `from_dn`, but no consumer for either was found in the inspected `sale/views.py`. | Trace the actual receiver and persisted target in phase 0; treat this as a static finding until verified in isolated request/service tests. Scope any necessary repair explicitly. |

### Historical reprint policy: snapshot preservation accepted

User decision, 2026-10-17: historical documents retain their snapshots. The alternative of applying today's visibility flag to historical reprints is rejected. This resolves the product decision; checking actual snapshot support remains implementation work.

- Existing historical PDFs/snapshots remain authoritative and unchanged. Reuse the existing document snapshot/output mechanism where available; do not migrate or rewrite historical text merely to add this column.
- New/unissued documents follow their document-type setting. At issuance, retain the effective details visibility and the exact details included in the issued output. Later flag changes must not add, hide, or replace those historical specifications.
- Define the actual issuance event for each supported document type from its existing lifecycle; do not assume that creation, approval, and first printing are interchangeable.
- Issuance events and allowed corrections after capture remain pending as detailed in section 12. The accepted historical snapshot decision does not implicitly choose them or close every currently editable confirmed/sent document.
- Use the saved snapshot/artifact for historical print, PDF, and any applicable thermal reprint. If output is rendered again from structured data, use captured content and visibility rather than live line/product text or current settings. A boolean visibility snapshot alone is insufficient to preserve text.
- For legacy records with no saved snapshot/artifact, do not fabricate a historical capture or claim an exact reproduction. Preserve the pre-feature output without introducing the new details column, identify that fallback in implementation evidence, and verify it independently. Check for existing artifacts before taking this fallback.
- Duplicating or converting a historical document creates a new target document. Copy its applicable source details using the lifecycle rules, but do not copy the source's issuance identity or frozen visibility as the new target's setting. The target uses its own current policy until issuance.
- Test the sequence: issue with details on, switch off, reprint; issue with details off, switch on, reprint. In both cases the historical snapshot remains unchanged. New documents follow the newly selected setting. Also test source text/product changes and primary/fallback output consistency.

No extra internal-versus-output switches or comprehensive layout-versioning subsystem is required by this decision. Inspect and extend only the snapshot support needed for this feature; record any missing prerequisite before confirming scope and estimate.

### Revised execution priority

1. Verify conversion consumers and current/source line identity; isolate the repeated-product purchasing prerequisite.
2. Verify the existing snapshot mechanism and issuance events, then implement the accepted historical snapshot policy without rewriting old output.
3. Implement shared validation, necessary schema additions, and identity-safe persistence, including text-only updates and hidden-data preservation.
4. Complete conversion/copy propagation, five independent settings, supported API read addition, and all scoped forms/output paths.
5. Verify event-level financial invariants, normal/fallback output parity, migration behavior, and the chosen historical-output policy before release.

Keep the goods-receipt extension optional. These corrections must not expand into a general financial, procurement, API, or permissions redesign.

## 12. Second strict review: snapshot execution and output reliability

This review adds requirements without removing sections 1-11. The five independent settings, seven-model persistence coverage, identity handling, purchasing prerequisites, text-only financial invariants, API stability, complete output paths, migration checks, and optional receipt package remain necessary.

### 12.1 Verify snapshot storage rather than assuming it

The reviewed print/download paths build output from live models. Pricing snapshots do not prove that issued line text or a historical PDF is retained. Existing attachment facilities are not evidence of automatic issuance capture unless a producer, saved artifact, association, and reader can be traced for the document type.

Produce a small inventory for each of the five core document types: current output producer, actual saved snapshot/artifact if any, capture event, historical reader, and missing capability. Reuse proven mechanisms. If support is absent, add only the snapshot data necessary for this feature: captured details text, effective visibility, stable association and ordering of captured lines, and capture identity/time needed to retrieve the correct output. Choose concrete storage after that inventory; do not pretend that adding the `details` columns alone implements historical reproduction.

Existing saved historical output remains authoritative. For legacy documents without a capture, retain section 11's explicit pre-feature fallback and limitation; do not manufacture a claim of exact historical reproduction. Snapshotting this feature does not freeze every unrelated field or promise pixel-identical restoration of all historical document content. Preserve hidden line text in the structured feature capture even when the retained output does not display it, as required by section 3; future conversion must not try to reconstruct hidden details from a rendered PDF.

### 12.2 Issuance and post-issuance corrections: product decision pending

Static evidence shows different lifecycle semantics: main sales/purchase invoices default to `confirmed`; quotations have `draft`/`sent`/`accepted`; order approval and confirmation states differ. A sent quotation is not automatically blocked by the inspected accepted/converted guard, and existing confirmed sales invoices are not all forbidden from editing. Therefore, creation, confirmation, first print, and external sending cannot be treated as one universal issuance event.

Before implementing freeze behavior, record for each core document:

1. The concrete lifecycle event that captures details/visibility.
2. Which details edits remain allowed before that event under existing permissions/status restrictions.
3. Whether post-issuance corrections are disallowed on that issued copy or create an explicitly identifiable corrected copy while retaining the earlier capture.
4. Which permitted current/captured representation appears on the screen, is printed, and supplies details during conversion into a new document.

Recommended discussion direction, not an approved rule: editable drafts; captured issued details remain fixed; a permitted correction retains the earlier issued capture and clearly identifies the corrected output. The user has not yet chosen whether corrections use the same document or a new copy. Do not silently implement a new lock, new correction workflow, or unrestricted overwrite of snapshots merely because this review was added.

Do not create snapshots as a side effect of an ordinary preview/GET request without a justified lifecycle contract. Keep any required correction bookkeeping limited to the line-details feature and reuse existing lifecycle/audit mechanisms where available. Independent schema, identity, and output investigation may continue while this decision is pending.

### 12.3 One effective feature-output source across channels

Print/download views and `DocumentDispatcher.render_document_pdf_bytes` currently build contexts separately. The purchase-order paths also disagree on context key (`po` versus `order`) and PDF type (`purchase_order` versus `po`). Adding a column only to download contexts leaves dispatch behavior uncovered.

Provide a shared, narrowly scoped resolver for the effective details representation: document type, current or captured line text, ordering/identity, visibility, and output revision. Use it in print/download, dispatcher generation, complete fallback generation, and thermal reprints where supported. Normalize the affected PO context/type mapping without rewriting the general dispatcher or changing unrelated documents. Preserve existing access checks and price/cost visibility when selecting or serving saved artifacts.

### 12.4 Prevent stale attachment reuse after permitted edits

The inspected media cache uses document identity and integer-second header `updated_at`, without checking PDF content. Saving line text alone does not necessarily update that header; even header timestamp changes within one second can share the same cache key.

Use an effective output revision or content-derived fingerprint for the affected cached attachments, including the selected snapshot/representation. Select the concrete approach after inspecting current cache callers. A permitted current/draft details edit must invalidate the relevant attachment identity; an unchanged historical capture may reuse its existing attachment identity. Do not invalidate or overwrite historical output simply because today's global setting changed.

Perform cache/revision maintenance as part of the supported text-only workflow without invoking financial reposting. If header bookkeeping is needed, inspect its save hooks so cache maintenance does not introduce financial/subledger side effects. Verify freshness through mocked local calls, not live messages or media uploads.

### 12.5 Do not accept incomplete PDFs as successful documents

`generate_guaranteed_pdf_response` can fall through to document/company/total-only output and then a skeletal PDF. Neither satisfies the feature's full-line output contract. A successful status, nonempty bytes, and `application/pdf` are insufficient acceptance evidence.

For the five in-scope document types:

- Prefer the valid saved artifact for the selected historical capture when it exists and is authorized for that output.
- Otherwise permit the primary renderer or a complete fallback that preserves the required lines, details, visibility, and source snapshot.
- When neither can produce a valid complete document, return a clear generation failure and block the affected attachment dispatch. Do not silently send a summary-only file as the document or allow dispatch exception handlers to bypass this check.
- Retain existing complete fallback capability. Scope the completeness/failure handling to these document paths rather than altering every PDF-producing subsystem.

The precise failure response should follow existing application conventions. Verify failure handling and user-visible behavior in isolated request/service tests; no external communication is authorized by this plan update.

Use a small explicit generation outcome for affected callers, such as complete, incomplete, or failed, with the returned artifact and its applicable document/output identity. An adapter may preserve existing helper signatures for unrelated consumers. The renderer knows whether it took the full or emergency-summary branch; use that provenance rather than building a generic runtime PDF parser or completeness-classification subsystem. A complete status is not a substitute for the content assertions and rendered fixtures in section 7. Ensure affected exception handlers cannot turn an incomplete result back into a successful document response.
