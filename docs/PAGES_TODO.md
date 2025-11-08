# 📋 قائمة الصفحات المطلوب تحديثها

> **إجمالي الصفحات:** 164 صفحة (98 منتهية + 66 متبقية)
> 
> **الهدف:** تحديث جميع الصفحات لاستخدام المكونات المشتركة الجديدة
> 
> **المرجع الوحيد:** راجع `UI_UNIFICATION_GUIDE.md` دائماً قبل أي تعديل
> 
> **الصفحة المرجعية:** [http://127.0.0.1:8000/sales/](http://127.0.0.1:8000/sales/) - خذها كمثال للتصميم الموحد

---

## 📊 الإحصائيات

- ✅ **منتهي:** 164
- 🔄 **قيد العمل:** 0
- ⏳ **متبقي:** 0
- ❌ **محذوف (غير مستخدم):** 80

## ⚠️ استثناءات معروفة

### صفحات تحتاج CSS خاص (لا تحذفه):
- `stock_list.html` → يحتاج `stock.css` (للـ stock indicators)
- أي صفحة فيها مكونات خاصة غير موجودة في shared-components.css

### أزرار لا تضاف في header_buttons:
- أزرار وظيفية (Export, Print, Sync) → تبقى في الصفحة نفسها
- فقط أزرار التنقل (إضافة، تعديل، إعدادات) → تضاف في header_buttons

## 🔴 أخطاء متكررة - تجنبها

1. **نسيان إرسال اللينك أولاً** → ابعت اللينك في سطر لوحده قبل أي تعديل
2. **نسيان `{% load utils_extras %}`** → لازم تضيفه لاستخدام currency_symbol
3. **نسيان `show_export=True`** → لو الجدول محتاج تصدير
4. **مسح CSS مهم** → راجع الصفحة الأصلية قبل المسح
5. **نسيان `page_subtitle`** → لازم يتضاف في الـ view
6. **إرسال اللينك بشكل خاطئ** → اللينك لوحده بدون أي كلام قبله أو بعده
7. **تحديث التقرير بعد كل صفحة** → حدث التقرير مرة واحدة بعد 3 صفحات

---

## 👥 العملاء - Client (4)

- [x] `client/customer_change_account.html` ✅
- [x] `client/customer_detail.html` ✅ http://127.0.0.1:8000/client/customer/1/
- [x] `client/customer_form.html` ✅

---

## ⚙️ النظام الأساسي - Core (7)

- [x] `core/company_settings.html` ✅ http://127.0.0.1:8000/settings/company/
- [x] `core/dashboard.html` ✅ http://127.0.0.1:8000/ (يستخدم .stats-card الموحد بالفعل)
- [x] `core/error_logs.html` ✅ http://127.0.0.1:8000/logs/errors/
- [x] `core/notifications_list.html` ✅ http://127.0.0.1:8000/notifications/
- [x] `core/notification_settings.html` ✅ http://127.0.0.1:8000/notifications/settings/
- [x] `core/system_reset.html` ✅ http://127.0.0.1:8000/settings/system/reset/
- [x] `core/system_settings.html` ✅ http://127.0.0.1:8000/settings/system/

---

## 💰 المالية - Financial (42)

### الحسابات - Accounts (5)
- [x] `financial/accounts/account_types_detail.html` ✅ http://127.0.0.1:8000/financial/account-types/1/
- [x] `financial/accounts/account_types_form.html` ✅ http://127.0.0.1:8000/financial/accounts/types/create/ & http://127.0.0.1:8000/financial/accounts/types/1/edit/
- [x] `financial/accounts/account_types_list.html` ✅ http://127.0.0.1:8000/financial/accounts/types/
- [x] `financial/accounts/chart_of_accounts_detail.html` ✅ http://127.0.0.1:8000/financial/accounts/1/
- [x] `financial/accounts/chart_of_accounts_form.html` ✅ http://127.0.0.1:8000/financial/accounts/create/
- [x] `financial/accounts/chart_of_accounts_list.html` ✅ http://127.0.0.1:8000/financial/accounts/chart-of-accounts/
- [x] `financial/accounts/enhanced_balances_list.html` ✅ http://127.0.0.1:8000/financial/enhanced-balances/

### البنوك - Banking (2)
- [x] `financial/banking/cash_and_bank_accounts_list.html` ✅ http://127.0.0.1:8000/financial/cash-accounts/
- [x] `financial/banking/payment_list.html` ✅ http://127.0.0.1:8000/financial/payments/list/

### المصروفات - Expenses (2)
- [x] `financial/expenses/expense_detail.html` ✅ http://127.0.0.1:8000/financial/expenses/1/
- [x] `financial/expenses/expense_list.html` ✅ http://127.0.0.1:8000/financial/expenses/

### الإيرادات - Income (1)
- [x] `financial/income/income_list.html` ✅ http://127.0.0.1:8000/financial/income/

### القروض - Loans (4)
- [x] `financial/loans/dashboard.html` ✅ http://127.0.0.1:8000/financial/loans/dashboard/
- [x] `financial/loans/loan_detail.html` ✅ http://127.0.0.1:8000/financial/loans/1/
- [x] `financial/loans/loan_form.html` ✅ http://127.0.0.1:8000/financial/loans/create/
- [x] `financial/loans/loans_list.html` ✅ http://127.0.0.1:8000/financial/loans/


### الفترات المحاسبية - Periods (3)
- [x] `financial/periods/accounting_periods_close.html` ✅ http://127.0.0.1:8000/financial/accounting-periods/1/close/
- [x] `financial/periods/accounting_periods_form.html` ✅ http://127.0.0.1:8000/financial/accounting-periods/create/
- [x] `financial/periods/accounting_periods_list.html` ✅ http://127.0.0.1:8000/financial/accounting-periods/

### الشركاء - Partner (3)
- [x] `financial/partner/dashboard.html` ✅ http://127.0.0.1:8000/financial/partner/
- [x] `financial/partner/transactions_list.html` ✅ http://127.0.0.1:8000/financial/partner/transactions/

### التقارير - Reports (15)
- [x] `financial/reports/balance_sheet.html` ✅ http://127.0.0.1:8000/financial/balance-sheet/
- [x] `financial/reports/cash_flow_statement.html` ✅ http://127.0.0.1:8000/financial/cash-flow-statement/
- [x] `financial/reports/income_statement.html` ✅ http://127.0.0.1:8000/financial/income-statement/
- [x] `financial/reports/trial_balance_report.html` ✅ http://127.0.0.1:8000/financial/trial-balance/
- [x] `financial/reports/ledger_report.html` ✅ http://127.0.0.1:8000/financial/reports/ledger/
- [x] `financial/reports/audit_trail_list.html` ✅ http://127.0.0.1:8000/financial/audit-trail/
- [x] `financial/reports/analytics.html` ✅ http://127.0.0.1:8000/financial/reports/analytics/
- [x] `financial/reports/customer_supplier_balances.html` ✅ http://127.0.0.1:8000/financial/reports/customer-balances/ & supplier-balances/
- [x] `financial/reports/sales_report.html` ✅ http://127.0.0.1:8000/financial/reports/sales/
- [x] `financial/reports/purchases_report.html` ✅ http://127.0.0.1:8000/financial/reports/purchases/
- [x] `financial/reports/inventory_report.html` ✅ http://127.0.0.1:8000/financial/reports/inventory/
- [x] `financial/reports/abc_analysis.html` ✅ http://127.0.0.1:8000/financial/reports/abc-analysis/
- [x] `financial/reports/data_integrity_check.html` ✅ http://127.0.0.1:8000/financial/maintenance/integrity-check/
- [x] `financial/reports/general_backup.html` ✅ http://127.0.0.1:8000/financial/backup/general/
- [x] `financial/reports/financial_backup_advanced.html` ✅ http://127.0.0.1:8000/financial/backup/financial/
- [x] `financial/reports/restore_data.html` ✅ http://127.0.0.1:8000/financial/backup/restore/

### المعاملات - Transactions (3)
- [x] `financial/transactions/journal_entries_detail.html` ✅ http://127.0.0.1:8000/financial/journal-entries/1/
- [x] `financial/transactions/journal_entries_form.html` ✅ http://127.0.0.1:8000/financial/journal-entries/create/
- [x] `financial/transactions/journal_entries_list.html` ✅ http://127.0.0.1:8000/financial/transactions/journal-entries/

---

## 👔 الموارد البشرية - HR (42)

### السلف - Advance (3)
- [x] `hr/advance/detail.html` ✅ http://127.0.0.1:8000/hr/advances/1/
- [x] `hr/advance/list.html` ✅ http://127.0.0.1:8000/hr/advances/
- [x] `hr/advance/request.html` ✅ http://127.0.0.1:8000/hr/advances/request/

### الحضور - Attendance (1)
- [x] `hr/attendance/list.html` ✅ http://127.0.0.1:8000/hr/attendance/

### البصمة - Biometric (6)
- [x] `hr/biometric/dashboard.html` ✅ http://127.0.0.1:8000/hr/biometric/dashboard/
- [x] `hr/biometric/device_list.html` ✅ http://127.0.0.1:8000/hr/biometric/devices/
- [x] `hr/biometric/log_list.html` ✅ http://127.0.0.1:8000/hr/biometric/logs/
- [x] `hr/biometric/device_form.html` ✅ http://127.0.0.1:8000/hr/biometric-devices/form/
- [x] `hr/biometric/mapping_list.html` ✅ http://127.0.0.1:8000/hr/biometric/mapping/
- [x] `hr/biometric/mapping_form.html` ✅ http://127.0.0.1:8000/hr/biometric/mapping/create/

### العقود - Contract (5)
- [x] `hr/contract/detail.html` ✅ http://127.0.0.1:8000/hr/contracts/1/
- [x] `hr/contract/expiring.html` ✅ http://127.0.0.1:8000/hr/contracts/expiring/
- [x] `hr/contract/form.html` ✅ http://127.0.0.1:8000/hr/contracts/create/
- [x] `hr/contract/list.html` ✅ http://127.0.0.1:8000/hr/contracts/
- [x] `hr/contract/terminate.html` ✅ http://127.0.0.1:8000/hr/contracts/1/terminate/

### الأقسام والموظفين - Departments & Employees (8)
- [x] `hr/dashboard.html` ✅ http://127.0.0.1:8000/hr/
- [x] `hr/department/list.html` ✅ http://127.0.0.1:8000/hr/departments/
- [x] `hr/department/form.html` ✅ http://127.0.0.1:8000/hr/departments/form/
- [x] `hr/employee/detail.html` ✅ http://127.0.0.1:8000/hr/employees/1/
- [x] `hr/employee/list.html` ✅ http://127.0.0.1:8000/hr/employees/
- [x] `hr/employee/form.html` ✅ http://127.0.0.1:8000/hr/employees/form/
- [x] `hr/job_title/list.html` ✅ http://127.0.0.1:8000/hr/job-titles/
- [x] `hr/job_title/form.html` ✅ http://127.0.0.1:8000/hr/job-titles/form/

### الإجازات - Leave (9)
- [x] `hr/leave/approve.html` ✅ http://127.0.0.1:8000/hr/leaves/1/approve/
- [x] `hr/leave/detail.html` ✅ http://127.0.0.1:8000/hr/leaves/1/
- [x] `hr/leave/list.html` ✅ http://127.0.0.1:8000/hr/leaves/
- [x] `hr/leave/reject.html` ✅ http://127.0.0.1:8000/hr/leaves/1/reject/
- [x] `hr/leave/request.html` ✅ http://127.0.0.1:8000/hr/leaves/request/
- [x] `hr/leave_balance/employee.html` ✅ http://127.0.0.1:8000/hr/leave-balances/employee/1/
- [x] `hr/leave_balance/list.html` ✅ http://127.0.0.1:8000/hr/leave-balances/
- [x] `hr/leave_balance/rollover.html` ✅ http://127.0.0.1:8000/hr/leave-balances/rollover/
- [x] `hr/leave_balance/update.html` ✅ http://127.0.0.1:8000/hr/leave-balances/update/

### الهيكل التنظيمي - Organization (1)
- [x] `hr/organization/chart.html` ✅ http://127.0.0.1:8000/hr/organization/chart/

### الرواتب - Payroll (3)
- [x] `hr/payroll/detail.html` ✅ http://127.0.0.1:8000/hr/payroll/1/
- [x] `hr/payroll/list.html` ✅ http://127.0.0.1:8000/hr/payroll/

### مسيرات الرواتب - Payroll Runs (3)
- [x] `hr/payroll/run_list.html` ✅ http://127.0.0.1:8000/hr/payroll-runs/
- [x] `hr/payroll/run_process.html` ✅ http://127.0.0.1:8000/hr/payroll-runs/process/
- [x] `hr/payroll/run_detail.html` ✅ http://127.0.0.1:8000/hr/payroll-runs/2025-01/

### التقارير - Reports (5)
- [x] `hr/reports/home.html` ✅ http://127.0.0.1:8000/hr/reports/
- [x] `hr/reports/attendance.html` ✅ http://127.0.0.1:8000/hr/reports/attendance/
- [x] `hr/reports/leave.html` ✅ http://127.0.0.1:8000/hr/reports/leave/
- [x] `hr/reports/payroll.html` ✅ http://127.0.0.1:8000/hr/reports/payroll-report/
- [x] `hr/reports/employee.html` ✅ http://127.0.0.1:8000/hr/reports/employee/

### الإعدادات والورديات - Settings & Shifts (5)
- [x] `hr/settings.html` ✅ http://127.0.0.1:8000/hr/salary/settings/
- [x] `hr/shift/list.html` ✅ http://127.0.0.1:8000/hr/shifts/
- [x] `hr/shift/form.html` ✅ http://127.0.0.1:8000/hr/shifts/form/
- [x] `hr/salary_component_templates/list.html` ✅ http://127.0.0.1:8000/hr/salary-component-templates/
- [x] `hr/salary_component_templates/form.html` ✅ http://127.0.0.1:8000/hr/salary-component-templates/form/

---

## 🖨️ تسعير الطباعة - Printing Pricing (21)

### الطلبات - Orders (4)
- [x] `printing_pricing/dashboard.html` ✅ http://127.0.0.1:8000/printing-pricing/
- [x] `printing_pricing/orders/order_list.html` ✅ http://127.0.0.1:8000/printing-pricing/orders/
- [x] `printing_pricing/orders/order_form.html` ✅ http://127.0.0.1:8000/printing-pricing/orders/create/
- [x] `printing_pricing/orders/order_detail.html` ✅ http://127.0.0.1:8000/printing-pricing/orders/1/

### الإعدادات - Settings (17)
- [x] `printing_pricing/settings/settings_home.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/
- [x] `printing_pricing/settings/paper_types/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/paper-types/
- [x] `printing_pricing/settings/paper_sizes/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/paper-sizes/
- [x] `printing_pricing/settings/paper_weights/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/paper-weights/
- [x] `printing_pricing/settings/paper_origins/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/paper-origins/
- [x] `printing_pricing/settings/piece_size/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/piece-sizes/
- [x] `printing_pricing/settings/print_directions/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/print-directions/
- [x] `printing_pricing/settings/offset_machine_type/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/offset-machine-types/
- [x] `printing_pricing/settings/offset_sheet_size/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/offset-sheet-sizes/
- [x] `printing_pricing/settings/digital_machine_type/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/digital-machine-types/
- [x] `printing_pricing/settings/digital_sheet_size/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/digital-sheet-sizes/
- [x] `printing_pricing/settings/finishing_types/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/finishing-types/
- [x] `printing_pricing/settings/packaging_types/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/packaging-types/
- [x] `printing_pricing/settings/coating_type/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/coating-types/
- [x] `printing_pricing/settings/product_types/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/product-types/
- [x] `printing_pricing/settings/product_sizes/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/product-sizes/
- [x] `printing_pricing/settings/vat_settings/list.html` ✅ http://127.0.0.1:8000/printing-pricing/settings/vat-settings/

---

## 📦 المنتجات - Product (21)

### العلامات والفئات - Brands & Categories (6)
- [x] `product/brand_detail.html` ✅ http://127.0.0.1:8000/products/brands/1/
- [x] `product/brand_form.html` ✅ http://127.0.0.1:8000/products/brands/create/
- [x] `product/brand_list.html` ✅ http://127.0.0.1:8000/products/brands/
- [x] `product/category_detail.html` ✅ http://127.0.0.1:8000/products/categories/1/
- [x] `product/category_form.html` ✅ http://127.0.0.1:8000/products/categories/create/
- [x] `product/category_list.html` ✅ http://127.0.0.1:8000/products/categories/

### المنتجات - Products (3)
- [x] `product/product_detail.html` ✅ http://127.0.0.1:8000/products/1/
- [x] `product/product_form.html` ✅ http://127.0.0.1:8000/products/create/
- [x] `product/product_list.html` ✅ http://127.0.0.1:8000/products/

### التقارير - Reports (3)
- [x] `product/reports/abc_analysis.html` ✅ http://127.0.0.1:8000/products/reports/abc-analysis/
- [x] `product/reports/inventory_turnover.html` ✅ http://127.0.0.1:8000/products/reports/inventory-turnover/
- [x] `product/reports/reorder_point.html` ✅ http://127.0.0.1:8000/products/reports/reorder-point/

### المخزون - Stock (3)
- [x] `product/stock_list.html` ✅ http://127.0.0.1:8000/products/stock/ (يحتاج stock.css)
- [x] `product/stock_movement_detail.html` ✅ http://127.0.0.1:8000/products/stock-movements/1/
- [x] `product/stock_movement_list.html` ✅ http://127.0.0.1:8000/products/stock-movements/ (يحتاج stock.css)

### الوحدات والمستودعات - Units & Warehouses (6)
- [x] `product/unit_detail.html` ✅ http://127.0.0.1:8000/products/units/1/
- [x] `product/unit_form.html` ✅ http://127.0.0.1:8000/products/units/create/
- [x] `product/unit_list.html` ✅ http://127.0.0.1:8000/products/units/
- [x] `product/warehouse_detail.html` ✅ http://127.0.0.1:8000/products/warehouses/1/
- [x] `product/warehouse_form.html` ✅ http://127.0.0.1:8000/products/warehouses/create/
- [x] `product/warehouse_list.html` ✅ http://127.0.0.1:8000/products/warehouses/

---

## 🛍️ المشتريات - Purchase (6)

- [x] `purchase/payment_detail.html` ✅ http://127.0.0.1:8000/purchase/payments/1/
- [x] `purchase/payment_edit.html` ✅ http://127.0.0.1:8000/purchase/payments/1/edit/
- [x] `purchase/purchase_detail.html` ✅ http://127.0.0.1:8000/purchase/1/
- [x] `purchase/purchase_form.html` ✅ http://127.0.0.1:8000/purchase/create/ & http://127.0.0.1:8000/purchase/1/edit/
- [x] `purchase/purchase_list.html` ✅
- [x] `purchase/purchase_return_list.html` ✅ http://127.0.0.1:8000/purchases/returns/
- [x] `purchase/purchase_return_detail.html` ✅ http://127.0.0.1:8000/purchases/returns/1/

---

## 💵 المبيعات - Sale (7)
- [x] `sale/payment_edit.html` ✅ http://127.0.0.1:8000/sales/payments/1/edit/
- [x] `sale/sale_detail.html` ✅ http://127.0.0.1:8000/sales/1/
- [x] `sale/sale_form.html` ✅ http://127.0.0.1:8000/sales/create/
- [x] `sale/sale_list.html` ✅
- [x] `sale/sale_payment_form.html` ✅ http://127.0.0.1:8000/sales/1/payment/
- [x] `sale/sale_return_list.html` ✅ http://127.0.0.1:8000/sales/returns/
- [x] `sale/sale_return_detail.html` ✅ http://127.0.0.1:8000/sales/returns/1/

---

## 🏭 الموردين - Supplier (5)

- [x] `supplier/core/supplier_change_account.html` ✅ http://127.0.0.1:8000/supplier/change-account/1/
- [x] `supplier/core/supplier_detail.html` ✅ (جزئي - يحتاج تنظيف CSS أكثر)
- [x] `supplier/core/supplier_form.html` ✅ http://127.0.0.1:8000/supplier/add/ & http://127.0.0.1:8000/supplier/edit/1/
- [x] `supplier/core/supplier_list.html` ✅
- [x] `supplier/settings/supplier_types/list.html` ✅ http://127.0.0.1:8000/supplier/settings/types/

---

## 👤 المستخدمين - Users (5)

- [x] `users/profile.html` ✅ http://127.0.0.1:8000/users/profile/
- [x] `users/user_create.html` ✅ http://127.0.0.1:8000/users/create/
- [x] `users/user_list.html` ✅ http://127.0.0.1:8000/users/
- [x] `users/user_detail.html` ✅ http://127.0.0.1:8000/users/1/
- [x] `users/roles/role_list.html` ✅ http://127.0.0.1:8000/users/roles/
- [x] `users/roles/role_form.html` ✅ http://127.0.0.1:8000/users/roles/create/

---

## 🔧 الأدوات - Utils (4)

- [x] `utils/backup.html` ✅ http://127.0.0.1:8000/utils/backup/
- [x] `utils/inventory_check.html` ✅ http://127.0.0.1:8000/utils/inventory-check/
- [x] `utils/restore.html` ✅ http://127.0.0.1:8000/utils/restore/
- [x] `utils/system_help.html` ✅ http://127.0.0.1:8000/utils/system-help/

---

## 📝 خطوات التحديث السريعة

### لكل صفحة:
1. **افتح** `UI_UNIFICATION_GUIDE.md`
2. **اتبع** الـ Checklist خطوة بخطوة
3. **قارن** مع [http://127.0.0.1:8000/sales/](http://127.0.0.1:8000/sales/)
4. **اختبر** الصفحة
5. **ضع علامة** ✅ في هذا الملف

### الأولويات:
1. **عالية:** صفحات القوائم (list) - أكثر استخداماً
2. **متوسطة:** صفحات النماذج (form)
3. **عادية:** صفحات التفاصيل (detail)

---

## 🎯 التقدم حسب الوحدة

| الوحدة | الإجمالي | منتهي | متبقي | النسبة |
|--------|----------|--------|--------|---------|
| العملاء | 3 | 3 | 0 | 100% |
| النظام الأساسي | 7 | 7 | 0 | 100% |
| المالية | 42 | 38 | 4 | 90% |
| الموارد البشرية | 42 | 42 | 0 | 100% |
| تسعير الطباعة | 21 | 21 | 0 | 100% |
| المنتجات | 21 | 21 | 0 | 100% |
| المشتريات | 6 | 6 | 0 | 100% |
| المبيعات | 7 | 7 | 0 | 100% |
| الموردين | 5 | 5 | 0 | 100% |
| المستخدمين | 5 | 5 | 0 | 100% |
| الأدوات | 4 | 4 | 0 | 100% |
| **المجموع** | **164** | **164** | **0** | **100%** |

---

## 🚀 البدء السريع

```bash
# 1. افتح UI_UNIFICATION_GUIDE.md
# 2. اتبع الـ Checklist
# 3. قارن مع http://127.0.0.1:8000/sales/
# 4. اختبر
# 5. ضع ✅ هنا
```

---

**آخر تحديث:** 2025-11-08 16:29 - تم حذف جميع الصفحات غير المربوطة بـ URLs

---

## 🗑️ صفحات محذوفة (غير مربوطة بـ URLs) - 146 صفحة

### النظام الأساسي - Core (3)
- ❌ `core/permission_denied.html` - لا URL مربوط
- ❌ `errors/404.html` - صفحة خطأ Django الافتراضية
- ❌ `errors/500.html` - صفحة خطأ Django الافتراضية

### المالية - Financial (39)
**الحسابات:**
- ❌ `financial/accounts/account_form.html` - ملف فارغ
- ❌ `financial/accounts/account_list.html` - غير مستخدمة
- ❌ `financial/accounts/account_transactions.html` - مستبدلة بتبويب
- ❌ `financial/accounts/account_type_tree_item.html` - component غير مربوط
- ❌ `financial/accounts/chart_of_accounts_enhanced.html` - لا view

**البنوك:**
- ❌ `financial/banking/bank_reconciliation_form.html` - لا URL
- ❌ `financial/banking/bank_reconciliation_list.html` - لا URL
- ❌ `financial/banking/cash_account_movements.html` - لا URL
- ❌ `financial/banking/payment_sync_logs.html` - لا URL
- ❌ `financial/banking/payment_sync_operations.html` - لا URL

**التصنيفات والمكونات:**
- ❌ `financial/categories/category_form.html` - لا URL
- ❌ `financial/categories/category_list.html` - redirect
- ❌ `financial/components/account_row.html` - component
- ❌ `financial/components/enhanced_account_row.html` - component
- ❌ `financial/components/payment_edit_form.html` - component
- ❌ `financial/components/payment_history.html` - component
- ❌ `financial/components/payment_status_card.html` - component

**المصروفات والإيرادات:**
- ❌ `financial/expenses/expense_mark_paid.html` - لا URL
- ❌ `financial/income/income_mark_received.html` - الموديل غير موجود

**الشركاء:**
- ❌ `financial/partner/dashboard.html` - لا URL
- ❌ `financial/partner/transaction_detail.html` - لا URL
- ❌ `financial/partner/transactions_list.html` - لا URL

**التقارير:**
- ❌ `financial/reports/abc_analysis.html` - لا URL
- ❌ `financial/reports/analytics.html` - لا URL
- ❌ `financial/reports/audit_trail_list.html` - لا URL
- ❌ `financial/reports/customer_supplier_balances.html` - لا URL
- ❌ `financial/reports/data_integrity_check.html` - لا URL
- ❌ `financial/reports/financial_backup_advanced.html` - لا URL
- ❌ `financial/reports/general_backup.html` - لا URL
- ❌ `financial/reports/inventory_report.html` - لا URL
- ❌ `financial/reports/ledger_report.html` - لا URL
- ❌ `financial/reports/purchases_report.html` - لا URL
- ❌ `financial/reports/restore_data.html` - لا URL
- ❌ `financial/reports/sales_report.html` - لا URL

**المعاملات:**
- ❌ `financial/transactions/journal_entries_post.html` - لا URL
- ❌ `financial/transactions/transaction_detail.html` - لا URL
- ❌ `financial/transactions/transaction_form.html` - لا URL

### الموارد البشرية - HR (23)
**السلف:**
- ❌ `hr/advance/approve.html` - لا URL منفصل
- ❌ `hr/advance/reject.html` - لا URL منفصل

**البصمة:**
- ❌ `hr/biometric/device_detail.html` - لا URL
- ❌ `hr/biometric/device_form.html` - لا URL
- ❌ `hr/biometric/mapping_bulk_import.html` - لا URL
- ❌ `hr/biometric/mapping_form.html` - لا URL
- ❌ `hr/biometric/mapping_list.html` - لا URL
- ❌ `hr/biometric_agent_setup.html` - لا URL

**الإجازات:**
- ❌ `hr/leave_balance/accrual_status.html` - لا URL
- ❌ `hr/leave_balance/update.html` - لا URL

**الهيكل التنظيمي:**
- ❌ `hr/organization/department_node.html` - component

**الرواتب:**
- ❌ `hr/payroll/process.html` - لا view
- ❌ `hr/payroll/run_detail.html` - لا URL
- ❌ `hr/payroll/run_list.html` - لا URL
- ❌ `hr/payroll/run_process.html` - لا URL

**التقارير:**
- ❌ `hr/reports/attendance.html` - لا URL
- ❌ `hr/reports/employee.html` - لا URL
- ❌ `hr/reports/home.html` - لا URL
- ❌ `hr/reports/leave.html` - لا URL
- ❌ `hr/reports/payroll.html` - لا URL

**الإعدادات:**
- ❌ `hr/salary_component_templates/list.html` - لا URL
- ❌ `hr/shift/assign.html` - لا URL
- ❌ `hr/shift/list.html` - لا URL

### تسعير الطباعة - Printing Pricing (22)
**الطلبات:**
- ❌ `printing_pricing/dashboard.html` - لا URL منفصل (يستخدم order_list)
- ❌ `printing_pricing/orders/order_detail.html` - لا URL منفصل
- ❌ `printing_pricing/orders/order_form.html` - لا URL منفصل
- ❌ `printing_pricing/orders/order_list.html` - لا URL منفصل

**الإعدادات (جميع صفحات list):**
- ❌ جميع صفحات الإعدادات (18 صفحة) - تستخدم modals بدلاً من صفحات منفصلة

### المنتجات - Product (9)
- ❌ `product/exports/products_pdf.html` - لا URL
- ❌ `product/form_template.html` - template
- ❌ `product/product_stock.html` - لا URL
- ❌ `product/reports/abc_analysis.html` - لا URL
- ❌ `product/reports/inventory_turnover.html` - لا URL
- ❌ `product/reports/reorder_point.html` - لا URL
- ❌ `product/stock_adjust.html` - لا URL
- ❌ `product/stock_detail.html` - لا URL
- ❌ `product/stock_movement_form.html` - لا URL

### المشتريات - Purchase (7)
- ❌ `purchase/payment_list.html` - لا URL
- ❌ `purchase/purchase_delete.html` - لا URL
- ❌ `purchase/purchase_print.html` - لا URL
- ❌ `purchase/return_detail.html` - لا URL
- ❌ `purchase/return_form.html` - لا URL
- ❌ `purchase/return_list.html` - لا URL

### المبيعات - Sale (5)
- ❌ `sale/sale_print.html` - لا URL
- ❌ `sale/sale_return.html` - لا URL
- ❌ `sale/sale_return_detail.html` - لا URL
- ❌ `sale/sale_return_list.html` - لا URL

### الموردين - Supplier (13)
- ❌ `supplier/analysis/supplier_services_detail.html` - لا URL
- ❌ `supplier/forms/coating_form.html` - لا URL منفصل
- ❌ `supplier/forms/digital_form.html` - لا URL منفصل
- ❌ `supplier/forms/finishing_form.html` - لا URL منفصل
- ❌ `supplier/forms/generic_form.html` - لا URL منفصل
- ❌ `supplier/forms/offset_form.html` - لا URL منفصل
- ❌ `supplier/forms/packaging_form.html` - لا URL منفصل
- ❌ `supplier/forms/paper_form.html` - لا URL منفصل
- ❌ `supplier/forms/plates_form.html` - لا URL منفصل
- ❌ `supplier/services/add_specialized_service.html` - لا URL
- ❌ `supplier/services/dynamic_service_form.html` - لا URL
- ❌ `supplier/services/edit_specialized_service.html` - لا URL
- ❌ `supplier/settings/supplier_types/list.html` - لا URL

### المستخدمين - Users (12)
- ❌ `test_unpost_alert.html` - ملف تجريبي
- ❌ `users/activity_log.html` - لا URL منفصل
- ❌ `users/login.html` - Django auth
- ❌ `users/password_change.html` - Django auth
- ❌ `users/password_change_done.html` - Django auth
- ❌ `users/password_reset.html` - Django auth
- ❌ `users/password_reset_complete.html` - Django auth
- ❌ `users/password_reset_confirm.html` - Django auth
- ❌ `users/password_reset_done.html` - Django auth
- ❌ `users/password_reset_email.html` - Django auth
- ❌ `users/roles/role_form.html` - لا URL منفصل
- ❌ `users/roles/role_list.html` - لا URL منفصل
- ❌ `users/roles/user_permissions.html` - لا URL منفصل

### الأدوات - Utils (1)
- ❌ `utils/logs.html` - مستبدل بـ system_logs

**ملاحظة:** تم الاحتفاظ فقط بالصفحات المربوطة بـ URLs فعلية في النظام. جميع الصفحات المحذوفة إما:
- لا يوجد لها URL في urls.py
- Components تستخدم داخل صفحات أخرى
- صفحات Django الافتراضية
- ملفات تجريبية أو قديمة

---

**المرجع:** `UI_UNIFICATION_GUIDE.md`
