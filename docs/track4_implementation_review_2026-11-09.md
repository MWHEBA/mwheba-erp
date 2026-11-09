# Track 4 implementation review — 2026-11-09

## Decision

**Not approved as a completed implementation.** The new accounting primitives pass the supplied tests, but the live application paths are not consistently routed through them. A duplicate refund was reproduced through the existing HTTP refund endpoint after the new settlement service had already disbursed the same deposit.

Reviewed the current uncommitted working tree against the accepted V14 executive plan at `C:/Users/UTD/.gemini/antigravity/brain/d466971c-0ea3-4e43-9e22-d92157d655d9/track_4_executive_implementation_plan.md`. No runtime source was modified by this review. Added only this report and `scratch/test_track4_review_2026_11_09.py`.

## Validation and limits

- Supplied Track 4 tests: **39 passed**.
- Broader `real_estate/tests` and `cheques/tests`: **627 passed**. The 39 Track 4 tests are a subset, not an additional 39 to add to this total.
- Review diagnostics: **9 failed**, each asserting an expected business invariant; the failures below were reproduced against real local services, without mocking the accounting gateway.
- All runs used `tests.settings`, isolated in-memory SQLite and disabled migrations. They do not establish MySQL/MariaDB lock correctness, a successful historical database upgrade, production readiness, browser behavior or provider delivery.
- The migration diagnostic invokes the migration's data function against isolated test records. It proves the flag update performed by that function; it is not a full MigrationExecutor upgrade test.

Commands:

```powershell
python -m pytest real_estate/tests cheques/tests --create-db --maxfail=10
python -m pytest scratch/test_track4_review_2026_11_09.py -o addopts='--import-mode=importlib --tb=short --no-migrations --ds=tests.settings -q' --create-db
```

## Findings

### F1 — P1: Old and new refund paths can disburse the same deposit twice

Sources: `real_estate/services/booking_service.py:540-594`, `real_estate/views/matrix_views.py:325`, `real_estate/services/accounting_service.py:473`, `real_estate/services/booking_service.py:441-537`.

Reproduction: collect a 1,000 EGP booking deposit; cancel into pending refund; create and attach a Track 4 settlement; disburse its full 1,000 EGP using `RealEstateAccountingService.disburse_refund`; POST to the existing `api_refund_booking` endpoint. The HTTP endpoint returns **200**, and bank credit lines total **2,000 EGP**. Its service checks the booking's pending status and deposit flag, not the active settlement's exhausted balance or disbursements. The new service does not close the old route's eligibility. The accounting idempotency namespaces are different, so each route posts a distinct refund.

Also, an ordinary paid cancellation does not create or attach a Track 4 settlement at all. The new refund tests manually create it, concealing the application wiring gap. Existing cancellation/refund forms still use the legacy service; they do not execute the new settlement/cheque lifecycle.

Diagnostics: `test_legacy_refund_cannot_pay_already_disbursed_settlement`, `test_cancellation_creates_active_settlement`.

Required correction: make cancellation and all refund entry points share one locked settlement and disbursement authority. Retire or adapt legacy posting paths; synchronize booking state and settlement state. Cover both operation orders, partial refunds and retries through HTTP, not just isolated service calls.

### F2 — P1: Booking conversion creates an active contract without an installment plan

Source: `real_estate/services/booking_service.py:383-438`.

The accepted conversion succeeds and posts the deposit transfer, but `contract.installment_plan_id` remains `None`. No schedule generation, binding-service call or allocation of the transferred deposit to the down-payment item occurs. This leaves the active contract outside the intended installment collection lifecycle.

Diagnostic: `test_conversion_generates_required_installment_plan`.

Required correction: create/select the intended plan, bind it via the existing binding service, and record the down-payment allocation within the conversion transaction. Test resulting installment balances and collection eligibility.

### F3 — P1: Historical-data migration fabricates both audit approvals

Source: `real_estate/migrations/0029_contractcoowner_notes_contractcoowner_relationship_and_more.py:16-21`.

`populate_legacy_bookings_data` sets `is_legacy_pre_audit=True`, **and** sets `is_reviewed_sales=True` and `is_confirmed_audit=True` for active historical bookings, without reviewer/approver actors or timestamps. The accepted plan explicitly replaced this behavior with the legacy flag alone. The diagnostic confirms both approvals become true on an originally unreviewed booking.

Diagnostic: `test_legacy_data_migration_does_not_fabricate_audits`.

Required correction: migrate only the explicit legacy classification and UUIDs; preserve actual audit evidence. Exercise the real historical-state upgrade before deployment.

### F4 — P1: Dual audit is represented by mutable fields, not an enforced workflow

Sources: `real_estate/models/booking.py:312-394`, `real_estate/services/booking_service.py:287`, `real_estate/admin.py:104-110`.

No booking review/confirmation action service or view is implemented, and the planned review/confirm/bypass permission codenames are not declared on UnitBooking. Audit fields are editable in the admin before confirmation. Setting both signatures to the booking creator succeeds, and conversion accepts that booking. The immutability guard only checks a previously confirmed row; it does not validate the first confirmation, actor separation, sequencing or complete signatures.

Diagnostic: `test_creator_cannot_supply_both_audit_signatures`.

Required correction: implement explicit locked review, confirmation and bypass actions with permissions and actor separation; expose their controls; make audit evidence readonly outside those actions. The same creator/reviewer/approver scenario must be rejected.

### F5 — P1: Parking/storage collision checks stop protecting completed sales

Source: `real_estate/services/booking_service.py:119-154`.

Collision checks query contracts only in `ACTIVE`. After the first contract is marked `COMPLETED`, a booking for another unit can take its parking code in the same project. Completion does not release a sold accessory. The storage check has the same status filter.

Diagnostic: `test_completed_contract_keeps_parking_reserved` reproduces the parking case.

Required correction: define all ownership-bearing contract states and include them in both guards. Preserve the accessory reservation through delivery/completion and release it only through an explicit valid reversal/disposal process.

### F6 — P1: Cash refund service accepts an expense account as its payout account

Source: `real_estate/services/accounting_service.py:530-535` and its cash/bank posting branch.

Passing the existing FX loss expense account (`54300`) as `payment_account` for a 1,000 EGP CASH refund succeeds. It credits the expense account, records a cleared refund and consumes the customer's entitlement without crediting an actual cash/bank account. The UI dropdown filtering does not protect this service boundary.

Diagnostic: `test_cash_refund_rejects_expense_account`.

Required correction: validate active leaf cash/bank eligibility, payment method and account currency on the server before posting; also enforce the same validation through the legacy HTTP paths until they are consolidated.

### F7 — P2: Split finishing creates flags without the execution/payment documents

Source: `real_estate/services/booking_service.py:377-438`.

Selecting `SPLIT_SPA_FINISHING_ANNEX` sets `has_decoupled_finishing` and copies the amount, but does not create a `UnitFinishingOrder` or its independent finishing payment plan. Reproduction with a 50,000 EGP finishing amount finds no finishing order for the resulting contract.

Diagnostic: `test_split_finishing_creates_order_and_independent_plan`.

Required correction: connect the selected package/amount to the existing finishing-order and segregated-installment services atomically, with explicit ownership of which amounts remain in the sale contract.

### F8 — P2: Tower financial portfolio drops completed contracts

Source: `real_estate/services/reporting_service.py:685-688` and `:863-877`.

The inventory counts contracted/delivered units, but the financial contract query includes only `ACTIVE`. Completing a contract makes its row lose its contract number/customer/value and removes its contribution from the financial aggregation. Reproduction changes an existing sale to `COMPLETED`; the tower row displays `doc_number='-'`.

Diagnostic: `test_completed_sale_stays_in_tower_financial_portfolio`.

Required correction: define the report's included lifecycle states consistently across inventory, financial totals and unit detail rows; completed valid sales should remain represented.

## Additional incomplete plan connections

These are static scope observations, separate from the nine runtime diagnostic failures:

- `ApiBookUnitView` still forwards only the original booking parameters. Matrix accessory/finishing/sales-team inputs are not connected to the expanded service.
- ContractCreateView does not parse or forward `co_owners_data`; the modal only exposes the primary percentage, not a complete co-buyer batch.
- Normal booking and contract service paths still supply UUID-based document numbers, bypassing the newly added model-level sequence fallback.
- No `settle_booking_cancellation` or `reinstate_cancelled_booking` implementation exists in the booking accounting service.
- WhatsApp changes add a payload builder, event key and status choices. There is no booking/refund event dispatch connection or worker lease/uncertain-send recovery implementation. Creating an IN_FLIGHT row in a test does not establish delivery governance.
- The contract model and migration retain the unconditional tax-exemption wording that the accepted design removed. This is a mismatch with the agreed configurable contractual terminology, not a tax determination by this review.
- Supplied concurrency-named tests do not establish target-engine concurrency correctness under the default SQLite/no-migrations runner.

## Remediation order

1. Unify cancellation/refund entry points and close the duplicate payout; validate payout accounts.
2. Correct the historical migration and implement the dual-audit workflow with evidence and permissions.
3. Complete installment/finishing integration and preserve sold accessory ownership through completed contracts.
4. Correct report lifecycle coverage and complete matrix/co-buyer/numbering/notification connections.
5. Re-run supplied suites and these diagnostics, then verify migrations and concurrent transactions on the intended deployment database.
