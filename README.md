# MWHEBA ERP — Modular Enterprise Platform
## Comprehensive Technical Documentation & Architecture Reference

<div align="center">

![Django](https://img.shields.io/badge/Django-4.2%20LTS-092E20?style=for-the-badge&logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-Production%20Ready-4479A1?style=for-the-badge&logo=mysql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-Caching%20%26%20Celery-DC382D?style=for-the-badge&logo=redis&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3%20RTL-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)
![Architecture](https://img.shields.io/badge/Architecture-Modular%20Dual--Layer-blue?style=for-the-badge)
![Security](https://img.shields.io/badge/RBAC-NIST%20Enterprise%20Level%202-success?style=for-the-badge)
![Accounting](https://img.shields.io/badge/Accounting-IAS%2021%20Compliant-orange?style=for-the-badge)

**A high-performance, modular, multi-tenant enterprise resource planning (ERP) platform built on Django 4.2 LTS. Designed to power complex industrial and commercial operations — from high-volume commercial printing and packaging plants to advertising agencies, wholesale trading conglomerates, and contracting firms.**

[Executive Summary](#1-executive-summary) · [Multi-Industry Modularity](#2-multi-industry-operational-profiles) · [Dual-Layer Architecture](#3-the-dual-layer-governance-architecture) · [Deep Module Breakdown](#4-deep-module-breakdown--service-layer) · [RBAC & Security](#5-rbac--security-governance) · [Middleware Pipeline](#6-middleware-pipeline-architecture) · [Database & Caching](#7-database-transactions--caching-architecture) · [Installation & Setup](#8-installation--environment-setup) · [Testing & QA](#9-automated-testing--verification-suite) · [Deployment](#10-production-deployment--maintenance)

</div>

---

## 1. Executive Summary

**MWHEBA ERP** is an enterprise-grade ERP system engineered to solve the operational, manufacturing, and financial complexities of multi-business enterprises. Unlike monolithic, rigid ERP solutions that impose uniform workflows across all clients, MWHEBA ERP operates as a **dynamically configurable modular platform**.

### Core Value Propositions
* **Multi-Business Operational Agility**: Tailors functionality per company profile (e.g., toggling off industrial manufacturing modules for advertising agencies or trading houses, while providing full offset sheet and machine calculators for packaging plants).
* **Zero-Technical-Debt Pure Django Authorization**: NIST Enterprise RBAC Level 2 implementation using a standard Django `ModelBackend` derivative (`RolePermissionBackend`) providing $O(1)$ in-memory request-level permission caching.
* **Strict Double-Entry Financial Core (IAS 21)**: Full multi-currency general ledger, automated currency revaluation (`FXRevaluationService`), treasury and banking controls, automated partner advance allocations, and reconciliation engines.
* **Segregated Production & Margin Privacy**: Complete decoupling of floor job tickets from commercial pricing margins. Machine operators receive technical production instructions without exposure to raw material costs, customer sale prices, or company profits.
* **High-Concurrency Scalability**: Built with `ATOMIC_REQUESTS = True`, connection pooling, Redis distributed caching, Celery task workers, and bulk SQL optimization eliminating N+1 query bottlenecks.

---

## 2. Multi-Industry Operational Profiles

MWHEBA ERP dynamically configures its operational landscape based on the enterprise profile:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Enterprise Industry Profile Matrix                              │
├──────────────────────┬──────────────────────────────────┬──────────────────────────────┤
│ Industry Profile     │ Active Feature Modules           │ Primary Operational Focus    │
├──────────────────────┼──────────────────────────────────┼──────────────────────────────┤
│ Commercial Printing  │ Core, Financial, Sales, Purchase,│ Raw paper sheet imposition,  │
│ & Packaging Plants   │ Inventory, HR, Governance,       │ plate consumption, ink,      │
│                      │ printing_pricing, work_order     │ lamination, machine stages,  │
│                      │                                  │ waste %, floor job tickets.  │
├──────────────────────┼──────────────────────────────────┼──────────────────────────────┤
│ Advertising & Media  │ Core, Financial, Sales, Purchase,│ Campaign budgeting, creative │
│ Production Agencies  │ Inventory (Services), HR, CRM,   │ services, wide-format digital│
│                      │ Quotations, Governance           │ print, promotional items,    │
│                      │                                  │ direct client invoicing.     │
├──────────────────────┼──────────────────────────────────┼──────────────────────────────┤
│ Wholesale Trading &  │ Core, Financial, Sales, Purchase,│ Multi-warehouse inventory,   │
│ Distribution Houses  │ Multi-Warehouse Inventory, CRM,  │ FIFO valuation, price lists  │
│                      │ PriceLists, Governance           │ (Wholesale/VIP), GRN, POs.   │
├──────────────────────┼──────────────────────────────────┼──────────────────────────────┤
│ Contracting &        │ Core, Financial, Cost Centers,   │ Project cost tracking,       │
│ Professional Services│ Sales, Expenses, Treasury,       │ partner advance settlements, │
│                      │ HR, Governance                   │ service milestones, banking. │
└──────────────────────┴──────────────────────────────────┴──────────────────────────────┘
```

---

## 3. The Dual-Layer Governance Architecture

To balance enterprise multi-business flexibility with zero-trust internal security, MWHEBA ERP operates across **two distinct, decoupled access control layers**:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   Layer 1: Enterprise Module Feature Control Layer                     │
│                        (SystemModule & Feature Toggle Engine)                          │
│         Controls which functional applications are active for this company profile     │
│                 ▼ ENABLED                                  ▼ DISABLED                  │
│                 │                                          │                           │
│                 ▼                                          ▼                           │
│  ┌────────────────────────────────────────┐     Module is completely silenced from UI, │
│  │    Layer 2: User Role-Based Access     │     sidebar, and navigation. Core operates │
│  │ (RolePermissionBackend - O(1) Memory)  │     as lightweight standalone platform.    │
│  │ User role dictates operational perms:  │                                            │
│  │ (sale.view_sale, hr.approve_leave...)  │                                            │
│  └────────────────────────────────────────┘                                            │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Layer 1: Enterprise Module Licensing (`core.SystemModule`)
* Governed by `SystemModule` and globally cached via `enabled_modules_dict_v2`.
* Modules (e.g., `printing_pricing`, `work_order`, `purchase_orders`, `quotations`, `biometric_hr`) can be toggled on or off per installation profile.
* When a module is disabled:
  - Its menus, submenus, and action triggers vanish completely from the sidebar and header via context processor caching (`enabled_modules_dict_v2`).
  - No database queries or heavy calculations for that module are loaded into memory.

### Layer 2: NIST Enterprise RBAC Level 2 (`users.RolePermissionBackend`)
* Operates strictly within standard Django authorization contracts (`app_label.codename`).
* **Single Source of Truth**: User identity and operational scope derive strictly from `User.role` and `is_superuser`.
* **Zero Database Loops**: During a single HTTP request, all user permissions are cached in memory on `request.user._cached_permissions`, delivering instant $O(1)$ lookups across dozens of UI element checks.

---

## 4. Deep Module Breakdown & Service Layer

```
mwheba-erp/
├── core/                  # Engine Core: Feature Toggles, DMS, Central Settings, Audit
├── users/                 # RBAC Engine: 10 Enterprise Roles, RolePermissionBackend
├── financial/             # Accounting: General Ledger, IAS 21 Multi-Currency, Treasury
├── sale/                  # Sales Pipeline: Invoices, Quotations, Orders, PriceLists
├── purchase/              # Procurement: POs, GRN, Landed Costs, Vendor Invoices
├── customer/              # CRM: Customer Ledger, Aging Reports, Advance Balances
├── supplier/              # Supplier Directory, Performance Evaluation, Price Tiers
├── product/               # Inventory: Multi-Warehouse, FIFO Valuation, Bundles, Batches
├── work_order/            # Manufacturing: Job Costing, Machine Stages, Floor Job Tickets
├── printing_pricing/      # Industrial Print Estimator: Offset Imposition, Plates, Waste
├── hr/                    # HCM: Biometric Attendance, Shift Rotations, Payroll Batches
├── governance/            # Integrity: AccountingGateway, Idempotency, Source Linkage
├── api/                   # Zero-Trust REST API: JWT Authentication, Model Permissions
├── templates/             # Semantic RTL UI: Bootstrap 5, CSS Variables, Strict Rule 2
└── static/                # Design Tokens, Production JavaScript Modules, Assets
```

---

### 4.1 Core System & DMS (`core`)
* **`SystemSetting`**: Centralized key-value configuration system with type-safety (`string`, `integer`, `decimal`, `boolean`, `json`, `date`). Cached globally via Redis/LocMem (`global_settings_dict_v2`).
* **`SystemModule`**: Module feature toggle engine with dependency resolution (e.g., `sales_orders` requires `customers_sales`).
* **Enterprise DMS (Document Management System)**:
  - File attachments stored with SHA-256 hash deduplication.
  - Secure tenant-isolated storage path: `companies/<company_id>/attachments/%Y/%m/<hash>_<random>.dat`.
  - Directory traversal and MIME-type validation.
* **Notification Engine (`NotificationService`)**: Multi-channel user notifications with WebSocket / polling support.

---

### 4.2 Financial & Accounting Core (`financial`)
A strictly audited double-entry accounting engine fully compliant with international accounting standards:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Double-Entry Accounting Architecture                            │
│                                                                                        │
│   Operational Action (Sale / Purchase / Cash Receipt / Payroll / FX Revaluation)       │
│                                           │                                            │
│                                           ▼                                            │
│                             governance.AccountingGateway                               │
│                     (Idempotency Guard + Source Hash Verification)                     │
│                                           │                                            │
│                                           ▼                                            │
│                              financial.JournalEntry                                    │
│                     (Draft ──► Validated ──► Posted ──► Reversible)                    │
│                                           │                                            │
│                 ┌─────────────────────────┴─────────────────────────┐                  │
│                 ▼                                                   ▼                  │
│    Debit Lines (Dr. Account)                            Credit Lines (Cr. Account)     │
│    Currency + Rate + Functional Amount                  Currency + Rate + Functional   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Key Capabilities & Models
* **`ChartOfAccounts`**: 5-level hierarchical chart of accounts (Assets, Liabilities, Equity, Revenues, Expenses) supporting multi-currency denominations.
* **`JournalEntry` & `JournalEntryLine`**: Strict double-entry integrity where $\sum \text{Debit} = \sum \text{Credit}$ enforced via model validation and database transactions.
* **Multi-Currency & IAS 21 Standard**:
  - Functional currency vs. foreign transaction currencies.
  - `FXRevaluationService`: Automated period-end revaluation of open monetary items with auto-posting of unrealized exchange gains/losses.
  - `ExchangeRateService`: Daily rate tracking with strict rate-age guards (>7 days requires executive CFO approval).
* **Penny Difference Handling**: Conversions resulting in fractional rounding discrepancies ($\le 0.05$) automatically route to `Rounding Differences Account`.
* **Treasury & Banking (`AccountHelperService`)**: Real-time cash and bank account balances, cash transfers with automated currency conversion, and bank reconciliations.
* **Automated Financial Reporting**:
  - Trial Balance (`TrialBalanceService`)
  - Income Statement / P&L (`IncomeStatementService`)
  - Balance Sheet (`BalanceSheetService`)
  - Statement of Cash Flows & General Ledger extracts

---

### 4.3 Sales & Commercial Pipeline (`sale`)
Covers the entire commercial customer journey:

```
[Quotation] ──► [Sales Order] ──► [Delivery Note] ──► [Tax Invoice] ──► [Receipt Voucher]
```

* **Smart Pipeline-Wide Price Protection**:
  - Prevents browser-level unit price tampering (`sale.change_unit_price`).
  - Validates item prices against active customer price lists (`PriceListItem`) and approved printing orders (`PrintingOrder.final_price`) in a single bulk $O(1)$ query.
* **Customer Price Lists (`PriceList`)**: Multiple active price lists (Wholesale, Retail, Corporate VIP) with validity date ranges and currency denominations.
* **Payment Integration**: Supports cash, credit, advance partner deductions (`PartnerAdvanceService`), and down payments.
* **Sales Return Workflow**: Reversible stock movements and credit note journal entries.

---

### 4.4 Procurement & Landed Cost (`purchase`)
* **Purchase Orders (PO)**: Supplier ordering pipeline with status tracking (`draft`, `sent`, `confirmed`, `received`, `cancelled`).
* **Goods Received Notes (GRN)**: Physical warehouse receiving decoupled from vendor financial invoicing to handle partial deliveries.
* **Landed Cost Allocation (`LandedCostService`)**: Prorates international shipping, customs, clearance, and freight across purchased inventory items based on weight or value, updating true product inventory cost.
* **Supplier Debit Notes**: Vendor returns with automatic stock adjustment and ledger reversal.

---

### 4.5 Inventory & Warehouse Management (`product`)
* **Valuation Methods**: Configurable per product or category: FIFO (First-In, First-Out) and Moving Average Cost.
* **Multi-Warehouse Topology**: Track stock per warehouse with inter-warehouse stock transfer orders (`StockTransfer`).
* **Bundled & Composite Products (`BundleManager`)**: Dynamically computes bundle stock based on the minimum available quantities of its subcomponents.
* **Stock Movement Audit (`StockMovement`)**: Every inward or outward quantity change records document source, user, timestamp, previous balance, and new balance.

---

### 4.6 Production & Manufacturing (`work_order`)
* **Job Costing & Profitability**: Tracks direct materials (paper, plates, chemicals), outside services (lamination, UV, stamping), and machine hourly costs against project revenues.
* **Segregated Machine Floor Job Tickets**:
  - Floor printouts contain purely technical specifications (sheet size, grain direction, number of plates, ink formulas, finishing sequence, delivery counts, waste allowances).
  - Commercial numbers (sale price, margin, client discounts) are strictly hidden from machine operators.
* **Production Status Stages**: `pending` $\rightarrow$ `in_prep` $\rightarrow$ `in_production` $\rightarrow$ `quality_check` $\rightarrow$ `completed`.
* **Workflow State Guards**: Automatically locks sales invoice modification when linked work orders enter physical production on the floor.

---

### 4.7 Industrial Printing & Packaging Estimator (`printing_pricing`)
Algorithmic estimation engine specialized for offset and digital print manufacturing:
* **Sheet Imposition & Layout Calculator**: Calculates optimal cut layouts from standard raw sheets (70x100, 66x96, 68x100) to target product sizes.
* **Plate & Color Engine**: Resolves plate requirements based on front/back color counts (e.g., 4/4, 4/0, 5/5 with spot PMS).
* **Paper Waste Formulas**: Calculates progressive setup waste and running waste percentages based on run length and finishing passes.
* **Finishing Operations**: Automatic cost calculations for gloss/matte thermal lamination, spot UV, hot foil stamping, embossing, die-cutting, gluing, and box assembly.
* **Machine Hourly Rates**: Machine capacity scheduling with hourly depreciation and labor rates.

---

### 4.8 Human Capital Management & Payroll (`hr`)
* **Biometric Attendance Device Sync (`BiometricService`)**: Ingests raw biometric punch logs from networked devices (e.g., ZKTeco), linking logs to employee shifts and detecting overtime, late arrivals, and early departures.
* **Multi-Component Contract Engine**: Base salary, housing allowances, transport allowances, variable performance bonuses, and statutory insurance deductions.
* **Automated Payroll Engine (`PayrollService`)**: Monthly payroll batch processing with attendance penalties, approved leave compensations, loan installments, and automated journal voucher posting.
* **Leave Management (`LeaveAccrualService`)**: Annual leaves, sick leaves, and work-permit requests with multi-tier approval workflows.

---

### 4.9 Governance, Idempotency & Reconciliation (`governance`)
* **`AccountingGateway`**: Single point of entry for all financial mutation requests. Enforces idempotency via unique request tokens (`idempotency_key`), preventing duplicate journal postings during network retries.
* **`AuditTrail`**: Logs model changes with before-and-after snapshots, IP addresses, user agent, and session signatures.
* **Daily Reconciliation Engine (`DataReconciliationService`)**: Automated nightly verification jobs validating that subledger totals (customers, suppliers, stock) perfectly match balance sheet GL accounts.

---

### 4.10 Zero-Trust REST API (`api`)
* **Authentication**: SimpleJWT with access tokens (15m validity) and refresh tokens (24h validity) with token blacklisting on logout.
* **Rate Limiting & Throttling**: Protects token issuance and resource-heavy calculation endpoints against brute-force or denial-of-service attempts.
* **`RoleBasedModelPermissions`**: Enforces strict permission checks on `SAFE_METHODS` (`GET`, `HEAD`), ensuring unprivileged tokens cannot access general ledger entries or chart of accounts.

---

## 5. RBAC & Security Governance

MWHEBA ERP strictly implements **NIST Enterprise RBAC Level 2** standard:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Enterprise Role Hierarchy Matrix                                │
├──────────────────────┬────────────────────────┬────────────────────────────────────────┤
│ Role Identifier      │ Arabic Role Title      │ Primary Operational Responsibilities   │
├──────────────────────┼────────────────────────┼────────────────────────────────────────┤
│ admin                │ مدير النظام             │ Unrestricted access across all modules │
│ financial_manager    │ مدير مالي              │ General ledger, period close, IAS 21,  │
│                      │                        │ profit margin audits, cash oversight   │
│ accountant           │ محاسب                  │ Journal entries, receipts, payments,   │
│                      │                        │ bank reconciliations, invoice audits   │
│ sales_manager        │ مشرف مبيعات            │ Full team visibility, price overrides, │
│                      │                        │ discount approvals, commission audits  │
│ sales_rep            │ مندوب مبيعات           │ Personal quotations & orders, customer │
│                      │                        │ service (margins & formulas protected) │
│ procurement_officer  │ مسؤول مشتريات          │ Vendor POs, supplier negotiations,     │
│                      │                        │ raw material delivery coordination     │
│ inventory_manager    │ أمين مخزن              │ GRN inspection, stock adjustments,     │
│                      │                        │ inter-warehouse transfers, scrap audit │
│ production_supervisor│ مسؤول تشغيل وإنتاج     │ Work orders, machine floor scheduling, │
│                      │                        │ job tickets (financials hidden)        │
│ hr_officer           │ مسؤول موارد بشرية      │ Personnel records, biometric sync,     │
│                      │                        │ contracts, leave approvals, payroll    │
│ viewer               │ مستخدم استعلام فقط     │ Read-only visibility across operational│
│                      │                        │ modules with zero mutation rights      │
└──────────────────────┴────────────────────────┴────────────────────────────────────────┘
```

---

## 6. Middleware Pipeline Architecture

Requests traverse an optimized, defense-in-depth pipeline of **11 active middleware components** (performance-tuned in `corporate_erp/settings.py`):

```
1.  SecurityMiddleware                  # Django core security layer
2.  WhiteNoiseMiddleware                # High-performance static assets delivery
3.  SessionMiddleware                   # Encrypted server-side session management
4.  CommonMiddleware                    # URL normalization & standard headers
5.  CsrfViewMiddleware                  # Strict CSRF token validation on POST/PUT/DELETE
6.  AuthenticationMiddleware            # Maps authenticated user to request.user
7.  MessageMiddleware                   # Flash notification message framework
8.  XFrameOptionsMiddleware             # Clickjacking defense (DENY / SAMEORIGIN)
9.  CurrentUserMiddleware               # Thread-local user storage for audit triggers
10. AdvancedSecurityHeadersMiddleware   # Enforces CSP, HSTS, X-Content-Type-Options
11. CorsMiddleware                      # CORS headers for authorized external clients
```

---

## 7. Database Transactions & Caching Architecture

### Atomic Request Guarantee
```python
# corporate_erp/settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql', # or sqlite3 in dev
        'ATOMIC_REQUESTS': True,              # Entire HTTP request runs in a transaction
        'CONN_MAX_AGE': 0,                    # Prevents Command Out of Sync on shared hosting
        'CONN_HEALTH_CHECKS': True,           # Verify connection health before reuse
    }
}
```
If an unhandled exception occurs during a complex multi-step operation (e.g., creating a sales invoice, decrementing warehouse stock, and posting a double-entry journal voucher), the entire request rolls back cleanly, ensuring zero orphan financial records.

### Multi-Tier Caching
* **Tier 1 (Request Memory Cache)**: Request-scoped `$O(1)$` dictionary storing user permissions and system settings. Zero SQL queries on subsequent checks within the same request.
* **Tier 2 (Distributed Redis Cache)**: Stores global system settings, company info, and enabled modules dictionary with smart cache invalidation on save/delete signals.

---

## 8. Installation & Environment Setup

### System Prerequisites
* Python 3.9+
* Database: MySQL 8.0+ (Production) or SQLite 3 (Development)
* Redis 6.0+ (Recommended for caching and background tasks)
* Git

### Step-by-Step Setup

```bash
# 1. Clone the repository
git clone https://github.com/MWHEBA/mwheba-erp.git
cd mwheba-erp

# 2. Initialize virtual environment
python -m venv venv

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
# Linux / macOS
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Environment Configuration
cp .env.example .env
# Edit .env with your database credentials, SECRET_KEY, and cache settings

# 5. Execute Database Migrations
python manage.py migrate

# 6. Seed the 10 Clean Enterprise Roles
python manage.py seed_clean_roles

# 7. Create Superuser (Admin)
python manage.py createsuperuser

# 8. Start Local Development Server
python manage.py runserver
```

Open browser at `http://127.0.0.1:8000`.

---

## 9. Automated Testing & Verification Suite

MWHEBA ERP strictly standardizes on **Pytest** for all unit, integration, and security test execution.

```powershell
# Run the Clean Enterprise RBAC Architecture Suite
pytest users/tests/test_clean_rbac_architecture.py -v

# Run Complete Users & Authorization Test Suite (44+ tests)
pytest users/tests/ -v

# Run Full Sales, Pricing & Commission Engine Suite (118+ tests)
pytest sale/tests/ -v

# Run All Financial & Accounting Ledger Tests
pytest financial/tests/ -v

# Run Full Project Test Suite with Coverage
pytest --cov=. --cov-report=term-missing

# Execute Comprehensive Django System Diagnostics
python manage.py check
```

---

## 10. Production Deployment & Maintenance

### Web Server Deployment (Linux / cPanel)
MWHEBA ERP supports deployment on standard Linux servers via Gunicorn/Nginx or cPanel environments via Phusion Passenger:
* **Entry Point**: `passenger_wsgi.py` / `corporate_erp/wsgi.py`
* **Static Assets**: Collected via `python manage.py collectstatic --noinput` and served with compression via WhiteNoise.

### Celery Background Worker
```bash
# Start Celery Worker for asynchronous tasks and notifications
celery -A corporate_erp worker -l info

# Start Celery Beat for scheduled reconciliation and maintenance jobs
celery -A corporate_erp beat -l info
```

---

## 📐 Design & UI/UX Standards

MWHEBA ERP adheres to corporate UI/UX directives outlined in `.agents/AGENTS.md`:
* **Colors**: Exclusively referenced via CSS variables declared in `:root` (zero hardcoded hex/rgb).
* **Flat Corporate Aesthetics**: Gradients are strictly prohibited to ensure a focused, uncluttered corporate dashboard.
* **Typography**: Clean, native Arabic typography with balanced line heights and unified hierarchy.
* **Component Architecture**: Standardized DRY template partials (`page_header.html`, `data_table.html`, `pagination.html`, and Rule 8 compliant centered modals).

---

## 📄 License & Intellectual Property

Proprietary Enterprise Software. Copyright © **MWHEBA Printing, Packaging & Advertising Group**. All rights reserved.
Unauthorized duplication, distribution, or reverse engineering is strictly prohibited.
