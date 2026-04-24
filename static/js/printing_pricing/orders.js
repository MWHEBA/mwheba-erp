/**
 * نظام التسعير المحسن - إدارة الطلبات
 * Printing Pricing System - Orders Management
 */

window.PrintingPricing = window.PrintingPricing || {};

PrintingPricing.Orders = {
    
    // إعدادات الطلبات
    config: {
        autoRefresh: false,
        refreshInterval: 60000, // 1 minute
        bulkActionLimit: 50,
        exportFormats: ['excel', 'pdf', 'csv']
    },

    // متغيرات عامة
    selectedOrders: new Set(),
    currentFilters: {},
    isInitialized: false,

    /**
     * تهيئة إدارة الطلبات
     * Initialize Orders Management
     */
    init: function() {
        if (this.isInitialized) return;

        PrintingPricing.Utils.log('Initializing Orders Management', 'info');

        this.bindEvents();
        this.initializeFilters();
        this.loadSelectedOrders();
        this.updateBulkActionsButton();

        this.isInitialized = true;
        PrintingPricing.Utils.log('Orders Management initialized successfully', 'info');
    },

    /**
     * ربط الأحداث
     * Bind Events
     */
    bindEvents: function() {
        // البحث المباشر
        const searchInput = document.querySelector('.pp-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', PrintingPricing.Utils.debounce((e) => {
                this.performSearch(e.target.value);
            }, 500));
        }

        // فلترة النماذج
        const filterForm = document.getElementById('orders-filter-form');
        if (filterForm) {
            filterForm.addEventListener('change', () => {
                this.applyFilters();
            });
        }

        // تحديد الطلبات
        document.querySelectorAll('.order-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                this.toggleOrderSelection(e.target.value, e.target.checked);
            });
        });

        // تحديد الكل
        const selectAllCheckbox = document.getElementById('select-all-checkbox');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                this.toggleSelectAll(e.target.checked);
            });
        }

        // أحداث لوحة المفاتيح
        document.addEventListener('keydown', (e) => {
            this.handleKeyboardShortcuts(e);
        });

        // تحديث الصفحة
        window.addEventListener('beforeunload', () => {
            this.saveSelectedOrders();
        });
    },

    /**
     * تهيئة الفلاتر
     * Initialize Filters
     */
    initializeFilters: function() {
        const urlParams = new URLSearchParams(window.location.search);
        this.currentFilters = {
            search: urlParams.get('search') || '',
            status: urlParams.get('status') || '',
            order_type: urlParams.get('order_type') || '',
            date_from: urlParams.get('date_from') || '',
            date_to: urlParams.get('date_to') || '',
            ordering: urlParams.get('ordering') || '-created_at'
        };
    },

    /**
     * تطبيق الفلاتر
     * Apply Filters
     */
    applyFilters: function() {
        const form = document.getElementById('orders-filter-form');
        if (!form) return;

        const formData = new FormData(form);
        const params = new URLSearchParams();

        // إضافة المعاملات غير الفارغة
        for (const [key, value] of formData.entries()) {
            if (value.trim()) {
                params.append(key, value);
                this.currentFilters[key] = value;
            }
        }

        // الحفاظ على ترتيب الحالي
        if (this.currentFilters.ordering) {
            params.append('ordering', this.currentFilters.ordering);
        }

        // إعادة توجيه مع الفلاتر الجديدة
        window.location.search = params.toString();
    },

    /**
     * البحث المباشر
     * Live Search
     */
    performSearch: function(query) {
        if (query.length < 2 && query.length > 0) return;

        this.currentFilters.search = query;
        
        // تحديث URL بدون إعادة تحميل الصفحة
        const params = new URLSearchParams(window.location.search);
        if (query) {
            params.set('search', query);
        } else {
            params.delete('search');
        }
        
        const newUrl = `${window.location.pathname}?${params.toString()}`;
        window.history.replaceState({}, '', newUrl);

        // تحديث النتائج
        this.refreshOrdersList();
    },

    /**
     * إزالة فلتر محدد
     * Remove Specific Filter
     */
    removeFilter: function(filterName) {
        const params = new URLSearchParams(window.location.search);
        params.delete(filterName);
        window.location.search = params.toString();
    },

    /**
     * مسح جميع الفلاتر
     * Clear All Filters
     */
    clearAllFilters: function() {
        window.location.href = window.location.pathname;
    },

    /**
     * تحديد/إلغاء تحديد طلب
     * Toggle Order Selection
     */
    toggleOrderSelection: function(orderId, isSelected) {
        if (isSelected) {
            this.selectedOrders.add(orderId);
        } else {
            this.selectedOrders.delete(orderId);
        }

        this.updateBulkActionsButton();
        this.updateSelectAllCheckbox();
        this.saveSelectedOrders();
    },

    /**
     * تحديد/إلغاء تحديد الكل
     * Toggle Select All
     */
    toggleSelectAll: function(selectAll = null) {
        const checkboxes = document.querySelectorAll('.order-checkbox');
        const selectAllCheckbox = document.getElementById('select-all-checkbox');
        
        if (selectAll === null) {
            selectAll = selectAllCheckbox ? selectAllCheckbox.checked : false;
        }

        checkboxes.forEach(checkbox => {
            checkbox.checked = selectAll;
            this.toggleOrderSelection(checkbox.value, selectAll);
        });

        this.updateBulkActionsButton();
    },

    /**
     * تحديد الكل (دالة منفصلة للزر)
     * Select All (Separate function for button)
     */
    selectAll: function() {
        this.toggleSelectAll(true);
    },

    /**
     * تحديث زر الإجراءات المتعددة
     * Update Bulk Actions Button
     */
    updateBulkActionsButton: function() {
        const button = document.getElementById('bulk-actions-btn');
        if (!button) return;

        const selectedCount = this.selectedOrders.size;
        button.disabled = selectedCount === 0;
        
        if (selectedCount > 0) {
            button.innerHTML = `<i class="fas fa-cogs"></i> إجراءات متعددة (${selectedCount})`;
        } else {
            button.innerHTML = `<i class="fas fa-cogs"></i> إجراءات متعددة`;
        }
    },

    /**
     * تحديث صندوق تحديد الكل
     * Update Select All Checkbox
     */
    updateSelectAllCheckbox: function() {
        const selectAllCheckbox = document.getElementById('select-all-checkbox');
        const checkboxes = document.querySelectorAll('.order-checkbox');
        
        if (!selectAllCheckbox || checkboxes.length === 0) return;

        const selectedCount = this.selectedOrders.size;
        const totalCount = checkboxes.length;

        if (selectedCount === 0) {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = false;
        } else if (selectedCount === totalCount) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.indeterminate = false;
        } else {
            selectAllCheckbox.checked = false;
            selectAllCheckbox.indeterminate = true;
        }
    },

    /**
     * حفظ الطلبات المحددة
     * Save Selected Orders
     */
    saveSelectedOrders: function() {
        const ordersArray = Array.from(this.selectedOrders);
        PrintingPricing.Utils.storage.set('selected_orders', ordersArray);
    },

    /**
     * تحميل الطلبات المحددة
     * Load Selected Orders
     */
    loadSelectedOrders: function() {
        const savedOrders = PrintingPricing.Utils.storage.get('selected_orders', []);
        this.selectedOrders = new Set(savedOrders);

        // تحديث واجهة المستخدم
        savedOrders.forEach(orderId => {
            const checkbox = document.querySelector(`.order-checkbox[value="${orderId}"]`);
            if (checkbox) {
                checkbox.checked = true;
            }
        });

        this.updateBulkActionsButton();
        this.updateSelectAllCheckbox();
    },

    /**
     * عرض الإجراءات المتعددة
     * Show Bulk Actions
     */
    bulkActions: function() {
        if (this.selectedOrders.size === 0) {
            PrintingPricing.Utils.showToast('يرجى تحديد طلب واحد على الأقل', 'warning');
            return;
        }

        const actions = [
            { icon: 'check', text: 'اعتماد الطلبات', action: () => this.bulkUpdateStatus('approved'), class: 'success' },
            { icon: 'times', text: 'رفض الطلبات', action: () => this.bulkUpdateStatus('rejected'), class: 'danger' },
            { icon: 'archive', text: 'أرشفة الطلبات', action: () => this.bulkUpdateStatus('completed'), class: 'secondary' },
            { icon: 'copy', text: 'نسخ الطلبات', action: () => this.bulkDuplicate(), class: 'info' },
            { icon: 'download', text: 'تصدير الطلبات', action: () => this.bulkExport(), class: 'primary' },
            { icon: 'trash', text: 'حذف الطلبات', action: () => this.bulkDelete(), class: 'danger' }
        ];

        const actionsHTML = actions.map(action => `
            <button class="pp-btn pp-btn-${action.class} w-100 mb-2" onclick="(${action.action.toString()})()">
                <i class="fas fa-${action.icon}"></i>
                ${action.text} (${this.selectedOrders.size})
            </button>
        `).join('');

        PrintingPricing.Utils.showModal('الإجراءات المتعددة', `
            <div class="pp-bulk-actions">
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i>
                    تم تحديد ${this.selectedOrders.size} طلب
                </div>
                ${actionsHTML}
            </div>
        `);
    },

    /**
     * تحديث حالة متعددة
     * Bulk Status Update
     */
    bulkUpdateStatus: async function(newStatus) {
        const orderIds = Array.from(this.selectedOrders);
        
        try {
            const response = await PrintingPricing.API.post('orders/bulk-update-status/', {
                order_ids: orderIds,
                status: newStatus
            });

            if (response.success) {
                PrintingPricing.Utils.showToast(`تم تحديث حالة ${orderIds.length} طلب بنجاح`, 'success');
                this.refreshOrdersList();
                this.clearSelection();
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.showToast('فشل في تحديث حالة الطلبات', 'error');
            PrintingPricing.Utils.log('Bulk status update failed', 'error', error);
        }
    },

    /**
     * نسخ متعدد
     * Bulk Duplicate
     */
    bulkDuplicate: async function() {
        const orderIds = Array.from(this.selectedOrders);
        
        try {
            const response = await PrintingPricing.API.post('orders/bulk-duplicate/', {
                order_ids: orderIds
            });

            if (response.success) {
                PrintingPricing.Utils.showToast(`تم نسخ ${orderIds.length} طلب بنجاح`, 'success');
                this.refreshOrdersList();
                this.clearSelection();
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.showToast('فشل في نسخ الطلبات', 'error');
            PrintingPricing.Utils.log('Bulk duplicate failed', 'error', error);
        }
    },

    /**
     * تصدير متعدد
     * Bulk Export
     */
    bulkExport: function() {
        const orderIds = Array.from(this.selectedOrders);
        const formats = [
            { value: 'excel', text: 'Excel (.xlsx)', icon: 'file-excel' },
            { value: 'pdf', text: 'PDF (.pdf)', icon: 'file-pdf' },
            { value: 'csv', text: 'CSV (.csv)', icon: 'file-csv' }
        ];

        const formatsHTML = formats.map(format => `
            <button class="pp-btn pp-btn-outline w-100 mb-2" onclick="PrintingPricing.Orders.exportSelected('${format.value}')">
                <i class="fas fa-${format.icon}"></i>
                ${format.text}
            </button>
        `).join('');

        PrintingPricing.Utils.showModal('تصدير الطلبات المحددة', `
            <div class="pp-export-options">
                <p>اختر تنسيق التصدير لـ ${orderIds.length} طلب:</p>
                ${formatsHTML}
            </div>
        `);
    },

    /**
     * تصدير الطلبات المحددة
     * Export Selected Orders
     */
    exportSelected: async function(format) {
        const orderIds = Array.from(this.selectedOrders);
        
        try {
            const response = await PrintingPricing.API.post('orders/bulk-export/', {
                order_ids: orderIds,
                format: format
            });

            if (response.success) {
                // تحميل الملف
                const blob = new Blob([response.data], { 
                    type: this.getContentType(format) 
                });
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `orders_export_${new Date().toISOString().split('T')[0]}.${format}`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);

                PrintingPricing.Utils.showToast('تم تصدير الطلبات بنجاح', 'success');
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.showToast('فشل في تصدير الطلبات', 'error');
            PrintingPricing.Utils.log('Export failed', 'error', error);
        }
    },

    /**
     * حذف متعدد
     * Bulk Delete
     */
    bulkDelete: function() {
        const orderIds = Array.from(this.selectedOrders);
        
        PrintingPricing.Utils.showModal('تأكيد الحذف', `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle"></i>
                هل أنت متأكد من حذف ${orderIds.length} طلب؟
                <br><strong>هذا الإجراء لا يمكن التراجع عنه!</strong>
            </div>
        `, {
            footer: `
                <button class="pp-btn pp-btn-secondary" onclick="this.closest('.pp-modal').remove()">إلغاء</button>
                <button class="pp-btn pp-btn-danger" onclick="PrintingPricing.Orders.confirmBulkDelete()">حذف</button>
            `
        });
    },

    /**
     * تأكيد الحذف المتعدد
     * Confirm Bulk Delete
     */
    confirmBulkDelete: async function() {
        const orderIds = Array.from(this.selectedOrders);
        
        try {
            const response = await PrintingPricing.API.post('orders/bulk-delete/', {
                order_ids: orderIds
            });

            if (response.success) {
                PrintingPricing.Utils.showToast(`تم حذف ${orderIds.length} طلب بنجاح`, 'success');
                this.refreshOrdersList();
                this.clearSelection();
                
                // إغلاق النافذة المنبثقة
                document.querySelectorAll('.pp-modal').forEach(modal => modal.remove());
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.showToast('فشل في حذف الطلبات', 'error');
            PrintingPricing.Utils.log('Bulk delete failed', 'error', error);
        }
    },

    /**
     * نسخ طلب واحد
     * Duplicate Single Order
     */
    duplicateOrder: async function(orderId) {
        try {
            const response = await PrintingPricing.API.post(`orders/${orderId}/duplicate/`);
            
            if (response.success) {
                PrintingPricing.Utils.showToast('تم نسخ الطلب بنجاح', 'success');
                window.location.href = `/printing-pricing/orders/${response.data.id}/`;
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.showToast('فشل في نسخ الطلب', 'error');
            PrintingPricing.Utils.log('Order duplication failed', 'error', error);
        }
    },

    /**
     * حذف طلب واحد
     * Delete Single Order
     */
    deleteOrder: function(orderId) {
        PrintingPricing.Utils.showModal('تأكيد الحذف', `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i>
                هل أنت متأكد من حذف هذا الطلب؟
                <br><strong>هذا الإجراء لا يمكن التراجع عنه!</strong>
            </div>
        `, {
            footer: `
                <button class="pp-btn pp-btn-secondary" onclick="this.closest('.pp-modal').remove()">إلغاء</button>
                <button class="pp-btn pp-btn-danger" onclick="PrintingPricing.Orders.confirmDeleteOrder(${orderId})">حذف</button>
            `
        });
    },

    /**
     * تأكيد حذف طلب واحد
     * Confirm Single Order Delete
     */
    confirmDeleteOrder: async function(orderId) {
        try {
            const response = await PrintingPricing.API.delete(`orders/${orderId}/`);
            
            if (response.success) {
                PrintingPricing.Utils.showToast('تم حذف الطلب بنجاح', 'success');
                this.refreshOrdersList();
                
                // إغلاق النافذة المنبثقة
                document.querySelectorAll('.pp-modal').forEach(modal => modal.remove());
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.showToast('فشل في حذف الطلب', 'error');
            PrintingPricing.Utils.log('Order deletion failed', 'error', error);
        }
    },

    /**
     * تصدير إلى Excel
     * Export to Excel
     */
    exportToExcel: function() {
        this.exportOrders('excel');
    },

    /**
     * تصدير إلى PDF
     * Export to PDF
     */
    exportToPDF: function() {
        this.exportOrders('pdf');
    },

    /**
     * تصدير إلى CSV
     * Export to CSV
     */
    exportToCSV: function() {
        this.exportOrders('csv');
    },

    /**
     * تصدير الطلبات
     * Export Orders
     */
    exportOrders: async function(format) {
        try {
            const params = new URLSearchParams(this.currentFilters);
            params.append('format', format);
            
            const response = await PrintingPricing.API.get('orders/export/', Object.fromEntries(params));
            
            if (response.success) {
                PrintingPricing.Utils.downloadFile(
                    response.data,
                    `orders_${new Date().toISOString().split('T')[0]}.${format}`,
                    this.getContentType(format)
                );
                PrintingPricing.Utils.showToast('تم تصدير الطلبات بنجاح', 'success');
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.showToast('فشل في تصدير الطلبات', 'error');
            PrintingPricing.Utils.log('Export failed', 'error', error);
        }
    },

    /**
     * الحصول على نوع المحتوى
     * Get Content Type
     */
    getContentType: function(format) {
        const types = {
            excel: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            pdf: 'application/pdf',
            csv: 'text/csv'
        };
        return types[format] || 'application/octet-stream';
    },

    /**
     * تحديث قائمة الطلبات
     * Refresh Orders List
     */
    refreshOrdersList: function() {
        // إعادة تحميل الصفحة مع الفلاتر الحالية
        const params = new URLSearchParams(this.currentFilters);
        window.location.search = params.toString();
    },

    /**
     * مسح التحديد
     * Clear Selection
     */
    clearSelection: function() {
        this.selectedOrders.clear();
        document.querySelectorAll('.order-checkbox').forEach(checkbox => {
            checkbox.checked = false;
        });
        this.updateBulkActionsButton();
        this.updateSelectAllCheckbox();
        this.saveSelectedOrders();
    },

    /**
     * معالجة اختصارات لوحة المفاتيح
     * Handle Keyboard Shortcuts
     */
    handleKeyboardShortcuts: function(e) {
        // Ctrl+A - تحديد الكل
        if (e.ctrlKey && e.key === 'a' && !e.target.matches('input, textarea')) {
            e.preventDefault();
            this.selectAll();
        }
        
        // Delete - حذف المحدد
        if (e.key === 'Delete' && this.selectedOrders.size > 0) {
            e.preventDefault();
            this.bulkDelete();
        }
        
        // Escape - مسح التحديد
        if (e.key === 'Escape') {
            this.clearSelection();
        }
    },

    /**
     * تنظيف الموارد
     * Cleanup
     */
    destroy: function() {
        this.saveSelectedOrders();
        this.isInitialized = false;
    }
};

// تنظيف عند مغادرة الصفحة
window.addEventListener('beforeunload', () => {
    PrintingPricing.Orders.destroy();
});
