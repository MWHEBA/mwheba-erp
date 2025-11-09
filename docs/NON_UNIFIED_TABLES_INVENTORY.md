# جرد الجداول غير الموحدة في النظام

هذا الملف يحتوي على قائمة شاملة بجميع الصفحات التي تحتوي على جداول HTML لا تستخدم الجدول الموحد `data_table.html`.

## ملخص إحصائي

- **إجمالي الصفحات التي تحتوي على جداول**: 103 صفحة
- **الصفحات التي تستخدم الجدول الموحد**: 31 صفحة
- **الصفحات التي لا تستخدم الجدول الموحد**: 103 صفحة

---

## 1. Core Module (النظام الأساسي)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Dashboard | `/` | 2 |

---

## 2. Financial Module (النظام المالي)

### 2.1 Banking (البنوك والخزن)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Cash Account Movements | `/financial/cash-accounts/<int:pk>/movements/` | 2 |
| Bank Reconciliation List | غير محدد | 1 |
| Payment Sync Logs | `/financial/payment-sync/logs/` | 1 |
| Payment Sync Operations | `/financial/payment-sync/operations/` | 1 |

### 2.2 Accounts (الحسابات)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Chart of Accounts List | `/financial/accounts/` | 1 |
| Chart of Accounts Detail | `/financial/accounts/<int:pk>/` | 3 |
| Enhanced Balances List | `/financial/enhanced-balances/` | 1 |

### 2.3 Expenses & Income

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Expense Detail | `/financial/expenses/<int:pk>/` | 1 |

### 2.4 Loans (القروض)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Loans List | `/financial/loans/list/` | 1 |
| Loan Detail | `/financial/loans/<int:pk>/` | 4 |

### 2.5 Partner Transactions

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Partner Transactions List | `/financial/partner/transactions/` | 1 |
| Partner Transaction Detail | `/financial/partner/transactions/<int:pk>/` | 1 |

### 2.6 Accounting Periods

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Accounting Periods List | `/financial/accounting-periods/` | 1 |

### 2.7 Reports (التقارير)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| ABC Analysis | `/financial/reports/abc-analysis/` | 1 |
| Customer Supplier Balances | `/financial/reports/balances/<str:account_type>/` | 1 |
| Data Integrity Check | `/financial/maintenance/integrity-check/` | 2 |
| Inventory Report | `/financial/reports/inventory/` | 1 |
| Ledger Report | `/financial/reports/ledger/` | 2 |
| Purchases Report | `/financial/reports/purchases/` | 1 |
| Sales Report | `/financial/reports/sales/` | 1 |
| Trial Balance Report | `/financial/reports/trial-balance/` | 1 |

### 2.8 Journal Entries

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Journal Entries Detail | `/financial/journal-entries/<int:pk>/` | 1 |
| Journal Entries Form | `/financial/journal-entries/create/` | 1 |
| Journal Entries Post | `/financial/journal-entries/<int:pk>/post/` | 2 |
| Journal Entry Delete Confirm | `/financial/journal-entries/<int:pk>/delete/` | 1 |
| Journal Entry Reverse Confirm | غير محدد | 2 |
| Transaction Detail | `/financial/transactions/<int:pk>/` | 1 |

---

## 3. HR Module (الموارد البشرية)

### 3.1 Advances (السلف)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Advance List | `/hr/advances/` | 1 |
| Advance Detail | `/hr/advances/<int:pk>/` | 1 |
| Advance Approve | `/hr/advances/<int:pk>/approve/` | 1 |
| Advance Reject | `/hr/advances/<int:pk>/reject/` | 1 |

### 3.2 Biometric (البصمة)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Device Delete | `/hr/biometric-devices/<int:pk>/delete/` | 1 |
| Device Test Modal | `/hr/biometric-devices/<int:pk>/test/` | 1 |
| Mapping List | `/hr/biometric/mapping/` | 1 |
| Mapping Delete | `/hr/biometric/mapping/<int:pk>/delete/` | 1 |

### 3.3 Contracts (العقود)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Contract Form | `/hr/contracts/form/` | 2 |
| Contract Expiring | `/hr/contracts/expiring/` | 1 |
| Contract Terminate | `/hr/contracts/<int:pk>/terminate/` | 1 |

### 3.4 Departments

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Department List | `/hr/departments/` | 1 |

### 3.5 Employees

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Employee Detail | `/hr/employees/<int:pk>/` | 1 |

### 3.6 Job Titles

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Job Title List | `/hr/job-titles/` | 1 |
| Job Title Delete | `/hr/job-titles/<int:pk>/delete/` | 1 |

### 3.7 Leaves (الإجازات)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Leave List | `/hr/leaves/` | 1 |
| Leave Request | `/hr/leaves/request/` | 1 |

### 3.8 Leave Balance

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Leave Balance List | `/hr/leave-balances/` | 1 |
| Leave Balance Employee | `/hr/leave-balances/employee/<int:employee_id>/` | 2 |
| Leave Balance Accrual Status | `/hr/leave-balances/accrual-status/<int:employee_id>/` | 1 |

### 3.9 Payroll (الرواتب)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Payroll List | `/hr/payroll/` | 1 |
| Payroll Detail | `/hr/payroll/<int:pk>/` | 2 |
| Payroll Run List | `/hr/payroll-runs/` | 1 |
| Payroll Run Detail | `/hr/payroll-runs/<str:month>/` | 1 |

### 3.10 Salary Component Templates

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Salary Component Templates List | `/hr/salary-component-templates/` | 2 |

### 3.11 Shifts (الورديات)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Shift List | `/hr/shifts/` | 1 |
| Shift Assign | `/hr/shifts/<int:pk>/assign/` | 1 |
| Shift Delete | `/hr/shifts/<int:pk>/delete/` | 1 |

### 3.12 Reports

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Attendance Report | `/hr/reports/attendance/` | 1 |
| Employee Report | `/hr/reports/employee/` | 1 |
| Leave Report | `/hr/reports/leave/` | 1 |
| Payroll Report | `/hr/reports/payroll-report/` | 1 |

---

## 4. Printing Pricing Module

### 4.1 Dashboard & Orders

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Dashboard | `/printing-pricing/` | 1 |
| Order List | `/printing-pricing/orders/` | 1 |

### 4.2 Settings (17 صفحة)

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Coating Type List | `/printing-pricing/settings/coating-types/` | 1 |
| Digital Machine Type List | `/printing-pricing/settings/digital-machine-types/` | 1 |
| Digital Sheet Size List | `/printing-pricing/settings/digital-sheet-sizes/` | 1 |
| Finishing Types List | `/printing-pricing/settings/finishing-types/` | 1 |
| Offset Machine Type List | `/printing-pricing/settings/offset-machine-types/` | 1 |
| Offset Sheet Size List | `/printing-pricing/settings/offset-sheet-sizes/` | 1 |
| Packaging Types List | `/printing-pricing/settings/packaging-types/` | 1 |
| Paper Origins List | `/printing-pricing/settings/paper-origins/` | 1 |
| Paper Sizes List | `/printing-pricing/settings/paper-sizes/` | 1 |
| Paper Types List | `/printing-pricing/settings/paper-types/` | 1 |
| Paper Weights List | `/printing-pricing/settings/paper-weights/` | 1 |
| Piece Size List | `/printing-pricing/settings/piece-sizes/` | 1 |
| Print Directions List | `/printing-pricing/settings/print-directions/` | 1 |
| Print Side List | `/printing-pricing/settings/print-sides/` | 1 |
| Product Sizes List | `/printing-pricing/settings/product-sizes/` | 1 |
| Product Types List | `/printing-pricing/settings/product-types/` | 1 |
| VAT Settings List | `/printing-pricing/settings/vat-settings/` | 1 |

---

## 5. Product Module

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Product Detail | `/product/<int:pk>/` | 4 |
| Product Stock | `/product/products/stock/<int:pk>/` | 1 |
| Category Detail | `/product/categories/<int:pk>/` | 1 |
| Unit Detail | `/product/units/<int:pk>/` | 1 |
| Stock Detail | `/product/stock/<int:pk>/` | 1 |
| ABC Analysis Report | `/product/reports/abc-analysis/` | 1 |
| Inventory Turnover Report | `/product/reports/inventory-turnover/` | 1 |
| Reorder Point Report | `/product/reports/reorder-point/` | 1 |
| Products PDF Export | تصدير PDF | 1 |

---

## 6. Purchase Module

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Purchase Detail | `/purchase/<int:pk>/` | 3 |
| Purchase Print | `/purchase/<int:pk>/print/` | 2 |
| Purchase Return | `/purchase/<int:pk>/return/` | 2 |
| Purchase Return Detail | `/purchase/returns/<int:pk>/` | 4 |
| Purchase Confirm Delete | `/purchase/<int:pk>/delete/` | 1 |

---

## 7. Sale Module

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Sale Detail | `/sale/<int:pk>/` | 3 |
| Sale Print | `/sale/<int:pk>/print/` | 2 |
| Sale Return | `/sale/<int:pk>/return/` | 1 |
| Sale Return Detail | `/sale/returns/<int:pk>/` | 2 |

---

## 8. Supplier Module

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Supplier Types List | `/supplier/settings/types/` | 1 |

---

## 9. Users Module

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Activity Log | `/users/activity-log/` | 1 |

---

## 10. Utils Module

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Inventory Check | `/utils/inventory-check/` | 2 |

---

## 11. Emails

| الصفحة | الرابط | عدد الجداول |
|--------|--------|-------------|
| Invoice Email | قالب بريد إلكتروني | 3 |

---

## ملاحظات مهمة

### أولويات التحويل

**أولوية عالية** (صفحات رئيسية):
- Financial Reports (8 صفحات)
- HR Reports (4 صفحات)
- Product Reports (3 صفحات)
- Purchase & Sale Details (6 صفحات)

**أولوية متوسطة** (صفحات إعدادات):
- Printing Pricing Settings (17 صفحة)
- HR Management Pages (15 صفحة)

**أولوية منخفضة** (صفحات نادرة الاستخدام):
- Delete Confirmations
- Email Templates
- Print Views

### فوائد التوحيد

1. **تناسق واجهة المستخدم** - جميع الجداول بنفس الشكل والسلوك
2. **سهولة الصيانة** - تعديل واحد يؤثر على جميع الجداول
3. **ميزات موحدة** - بحث، ترتيب، تصدير، pagination
4. **تحسين الأداء** - كود محسّن ومختبر
5. **استجابة أفضل** - دعم كامل للموبايل

### خطة العمل المقترحة

1. البدء بالتقارير المالية (أكثر استخداماً)
2. ثم صفحات HR الرئيسية
3. ثم صفحات المنتجات والمخزون
4. ثم صفحات الإعدادات
5. أخيراً الصفحات النادرة الاستخدام
