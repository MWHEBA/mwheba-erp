/**
 * نظام التسعير المحسن - تفاصيل الطلب
 * Printing Pricing System - Order Detail
 */

window.PrintingPricing = window.PrintingPricing || {};

PrintingPricing.OrderDetail = {
    
    // إعدادات التفاصيل
    config: {
        orderId: null,
        orderNumber: '',
        status: '',
        autoRefresh: false,
        refreshInterval: 60000 // 1 minute
    },

    // متغيرات عامة
    refreshTimer: null,
    isInitialized: false,

    /**
     * تهيئة تفاصيل الطلب
     * Initialize Order Detail
     */
    init: function(options = {}) {
        if (this.isInitialized) return;

        PrintingPricing.Utils.log('Initializing Order Detail', 'info');

        // دمج الإعدادات
        Object.assign(this.config, options);

        this.bindEvents();
        this.loadActivityHistory();
        
        if (this.config.autoRefresh) {
            this.startAutoRefresh();
        }

        this.isInitialized = true;
        PrintingPricing.Utils.log('Order Detail initialized successfully', 'info');
    },

    /**
     * ربط الأحداث
     * Bind Events
     */
    bindEvents: function() {
        // أحداث لوحة المفاتيح
        document.addEventListener('keydown', (e) => {
            this.handleKeyboardShortcuts(e);
        });

        // تحديث التكلفة عند تغيير البيانات
        document.addEventListener('orderUpdated', () => {
            this.refreshOrderData();
        });
    },

    /**
     * نسخ الطلب
     * Duplicate Order
     */
    duplicateOrder: async function() {
        try {
            const response = await PrintingPricing.API.post(`orders/${this.config.orderId}/duplicate/`);
            
            if (response.success) {
                PrintingPricing.Utils.showToast('تم نسخ الطلب بنجاح', 'success');
                setTimeout(() => {
                    window.location.href = `/printing-pricing/orders/${response.data.id}/edit/`;
                }, 1500);
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.log('Order duplication failed', 'error', error);
            PrintingPricing.Utils.showToast('فشل في نسخ الطلب', 'error');
        }
    },

    /**
     * اعتماد الطلب
     * Approve Order
     */
    approveOrder: function() {
        PrintingPricing.Utils.showModal('تأكيد الاعتماد', `
            <div class="alert alert-success">
                <i class="fas fa-check-circle"></i>
                هل أنت متأكد من اعتماد هذا الطلب؟
                <br><strong>سيتم تغيير حالة الطلب إلى "معتمد"</strong>
            </div>
        `, {
            footer: `
                <button class="pp-btn pp-btn-secondary" onclick="this.closest('.pp-modal').remove()">إلغاء</button>
                <button class="pp-btn pp-btn-success" onclick="PrintingPricing.OrderDetail.confirmApproval()">اعتماد</button>
            `
        });
    },

    /**
     * تأكيد الاعتماد
     * Confirm Approval
     */
    confirmApproval: async function() {
        try {
            const response = await PrintingPricing.API.orders.patch(this.config.orderId, {
                status: 'approved'
            });

            if (response.success) {
                PrintingPricing.Utils.showToast('تم اعتماد الطلب بنجاح', 'success');
                this.addActivityItem('approve', 'تم اعتماد الطلب');
                this.updateOrderStatus('approved');
                
                // إغلاق النافذة المنبثقة
                document.querySelectorAll('.pp-modal').forEach(modal => modal.remove());
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.log('Order approval failed', 'error', error);
            PrintingPricing.Utils.showToast('فشل في اعتماد الطلب', 'error');
        }
    },

    /**
     * رفض الطلب
     * Reject Order
     */
    rejectOrder: function() {
        PrintingPricing.Utils.showModal('رفض الطلب', `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i>
                هل أنت متأكد من رفض هذا الطلب؟
            </div>
            <div class="pp-form-group">
                <label class="pp-form-label">سبب الرفض (اختياري)</label>
                <textarea class="pp-form-control" id="rejection-reason" rows="3" placeholder="أدخل سبب رفض الطلب..."></textarea>
            </div>
        `, {
            footer: `
                <button class="pp-btn pp-btn-secondary" onclick="this.closest('.pp-modal').remove()">إلغاء</button>
                <button class="pp-btn pp-btn-danger" onclick="PrintingPricing.OrderDetail.confirmRejection()">رفض الطلب</button>
            `
        });
    },

    /**
     * تأكيد الرفض
     * Confirm Rejection
     */
    confirmRejection: async function() {
        try {
            const reason = document.getElementById('rejection-reason').value;
            
            const response = await PrintingPricing.API.orders.patch(this.config.orderId, {
                status: 'rejected',
                rejection_reason: reason
            });

            if (response.success) {
                PrintingPricing.Utils.showToast('تم رفض الطلب', 'success');
                this.addActivityItem('reject', `تم رفض الطلب${reason ? ': ' + reason : ''}`);
                this.updateOrderStatus('rejected');
                
                // إغلاق النافذة المنبثقة
                document.querySelectorAll('.pp-modal').forEach(modal => modal.remove());
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.log('Order rejection failed', 'error', error);
            PrintingPricing.Utils.showToast('فشل في رفض الطلب', 'error');
        }
    },

    /**
     * حذف الطلب
     * Delete Order
     */
    deleteOrder: function() {
        PrintingPricing.Utils.showModal('تأكيد الحذف', `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle"></i>
                هل أنت متأكد من حذف هذا الطلب؟
                <br><strong>هذا الإجراء لا يمكن التراجع عنه!</strong>
            </div>
            <div class="pp-form-group">
                <label class="pp-form-label">اكتب "حذف" للتأكيد</label>
                <input type="text" class="pp-form-control" id="delete-confirmation" placeholder="حذف">
            </div>
        `, {
            footer: `
                <button class="pp-btn pp-btn-secondary" onclick="this.closest('.pp-modal').remove()">إلغاء</button>
                <button class="pp-btn pp-btn-danger" onclick="PrintingPricing.OrderDetail.confirmDeletion()" id="confirm-delete-btn" disabled>حذف الطلب</button>
            `
        });

        // تفعيل زر الحذف عند كتابة "حذف"
        const confirmInput = document.getElementById('delete-confirmation');
        const confirmBtn = document.getElementById('confirm-delete-btn');
        
        if (confirmInput && confirmBtn) {
            confirmInput.addEventListener('input', (e) => {
                confirmBtn.disabled = e.target.value !== 'حذف';
            });
        }
    },

    /**
     * تأكيد الحذف
     * Confirm Deletion
     */
    confirmDeletion: async function() {
        try {
            const response = await PrintingPricing.API.orders.delete(this.config.orderId);
            
            if (response.success) {
                PrintingPricing.Utils.showToast('تم حذف الطلب بنجاح', 'success');
                setTimeout(() => {
                    window.location.href = '/printing-pricing/orders/';
                }, 1500);
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.log('Order deletion failed', 'error', error);
            PrintingPricing.Utils.showToast('فشل في حذف الطلب', 'error');
        }
    },

    /**
     * إعادة حساب التكلفة
     * Recalculate Cost
     */
    recalculateCost: async function() {
        try {
            const response = await PrintingPricing.API.post(`orders/${this.config.orderId}/recalculate/`);
            
            if (response.success) {
                PrintingPricing.Utils.showToast('تم إعادة حساب التكلفة بنجاح', 'success');
                this.updateCostDisplay(response.data);
                this.addActivityItem('update', 'تم إعادة حساب التكلفة');
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.log('Cost recalculation failed', 'error', error);
            PrintingPricing.Utils.showToast('فشل في إعادة حساب التكلفة', 'error');
        }
    },

    /**
     * تصدير إلى PDF
     * Export to PDF
     */
    exportToPDF: async function() {
        try {
            const response = await PrintingPricing.API.get(`orders/${this.config.orderId}/export/pdf/`);
            
            if (response.success) {
                // تحميل ملف PDF
                const blob = new Blob([response.data], { type: 'application/pdf' });
                const url = window.URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = `order_${this.config.orderNumber}.pdf`;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                window.URL.revokeObjectURL(url);

                PrintingPricing.Utils.showToast('تم تصدير الطلب بنجاح', 'success');
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.log('PDF export failed', 'error', error);
            PrintingPricing.Utils.showToast('فشل في تصدير الطلب', 'error');
        }
    },

    /**
     * طباعة الطلب
     * Print Order
     */
    printOrder: function() {
        // إخفاء العناصر غير المرغوب فيها في الطباعة
        const elementsToHide = document.querySelectorAll('.pp-btn, .dropdown-toggle, .pp-page-actions');
        elementsToHide.forEach(el => el.style.display = 'none');

        // طباعة الصفحة
        window.print();

        // إعادة إظهار العناصر
        elementsToHide.forEach(el => el.style.display = '');
    },

    /**
     * نسخ رقم الطلب
     * Copy Order Number
     */
    copyOrderNumber: function() {
        PrintingPricing.Utils.copyToClipboard(this.config.orderNumber)
            .then(() => {
                PrintingPricing.Utils.showToast('تم نسخ رقم الطلب', 'success');
            })
            .catch(() => {
                PrintingPricing.Utils.showToast('فشل في نسخ رقم الطلب', 'error');
            });
    },

    /**
     * تحميل سجل الأنشطة
     * Load Activity History
     */
    loadActivityHistory: async function() {
        try {
            const response = await PrintingPricing.API.get(`orders/${this.config.orderId}/activities/`);
            
            if (response.success && response.data.length > 0) {
                this.updateActivityTimeline(response.data);
            }
        } catch (error) {
            PrintingPricing.Utils.log('Failed to load activity history', 'error', error);
        }
    },

    /**
     * تحديث الجدول الزمني للأنشطة
     * Update Activity Timeline
     */
    updateActivityTimeline: function(activities) {
        const timeline = document.getElementById('activity-timeline');
        if (!timeline) return;

        // مسح الأنشطة الحالية (عدا الأنشطة الأساسية)
        const existingItems = timeline.querySelectorAll('.pp-activity-item');
        existingItems.forEach((item, index) => {
            if (index > 1) { // الاحتفاظ بأول عنصرين (الإنشاء والتحديث)
                item.remove();
            }
        });

        // إضافة الأنشطة الجديدة
        activities.forEach(activity => {
            this.addActivityItem(activity.type, activity.description, activity.created_at, activity.user);
        });
    },

    /**
     * إضافة عنصر نشاط
     * Add Activity Item
     */
    addActivityItem: function(type, description, timestamp = null, user = null) {
        const timeline = document.getElementById('activity-timeline');
        if (!timeline) return;

        const activityItem = PrintingPricing.Utils.createElement('div', {
            className: 'pp-activity-item'
        }, `
            <div class="pp-activity-icon pp-activity-${type}">
                <i class="fas fa-${this.getActivityIcon(type)}"></i>
            </div>
            <div class="pp-activity-content">
                <div class="pp-activity-text">${description}</div>
                <div class="pp-activity-time">${timestamp || new Date().toLocaleString('ar-EG')}</div>
                ${user ? `<div class="pp-activity-user">بواسطة: ${user}</div>` : ''}
            </div>
        `);

        // إضافة العنصر في المقدمة
        timeline.insertBefore(activityItem, timeline.firstChild);

        // تحريك العنصر الجديد
        activityItem.style.opacity = '0';
        activityItem.style.transform = 'translateY(-20px)';
        
        setTimeout(() => {
            activityItem.style.transition = 'all 0.3s ease';
            activityItem.style.opacity = '1';
            activityItem.style.transform = 'translateY(0)';
        }, 100);
    },

    /**
     * الحصول على أيقونة النشاط
     * Get Activity Icon
     */
    getActivityIcon: function(type) {
        const icons = {
            create: 'plus',
            update: 'edit',
            approve: 'check',
            reject: 'times',
            delete: 'trash',
            calculate: 'calculator',
            export: 'download',
            print: 'print'
        };
        return icons[type] || 'info';
    },

    /**
     * تحديث حالة الطلب
     * Update Order Status
     */
    updateOrderStatus: function(newStatus) {
        this.config.status = newStatus;
        
        // تحديث شارات الحالة
        document.querySelectorAll('.pp-status-badge').forEach(badge => {
            badge.className = `pp-status-badge pp-status-${newStatus}`;
            badge.textContent = this.getStatusDisplayName(newStatus);
        });

        // تحديث الأزرار المتاحة
        this.updateAvailableActions();
    },

    /**
     * الحصول على اسم عرض الحالة
     * Get Status Display Name
     */
    getStatusDisplayName: function(status) {
        const statusNames = {
            draft: 'مسودة',
            pending: 'قيد المراجعة',
            approved: 'معتمد',
            rejected: 'مرفوض',
            completed: 'مكتمل',
            cancelled: 'ملغي'
        };
        return statusNames[status] || status;
    },

    /**
     * تحديث الإجراءات المتاحة
     * Update Available Actions
     */
    updateAvailableActions: function() {
        const approveBtn = document.querySelector('[onclick*="approveOrder"]');
        const rejectBtn = document.querySelector('[onclick*="rejectOrder"]');

        if (approveBtn && rejectBtn) {
            const shouldShow = this.config.status === 'draft' || this.config.status === 'pending';
            approveBtn.style.display = shouldShow ? '' : 'none';
            rejectBtn.style.display = shouldShow ? '' : 'none';
        }
    },

    /**
     * تحديث عرض التكلفة
     * Update Cost Display
     */
    updateCostDisplay: function(costData) {
        const costElements = {
            'material_cost': costData.material_cost,
            'printing_cost': costData.printing_cost,
            'services_cost': costData.services_cost,
            'total_cost': costData.total_cost
        };

        Object.keys(costElements).forEach(key => {
            const elements = document.querySelectorAll(`[data-cost="${key}"], .pp-cost-value`);
            elements.forEach(element => {
                if (element.textContent.includes('تكلفة') || element.textContent.includes('إجمالي')) {
                    element.textContent = PrintingPricing.Utils.formatCurrency(costElements[key]);
                }
            });
        });
    },

    /**
     * تحديث بيانات الطلب
     * Refresh Order Data
     */
    refreshOrderData: async function() {
        try {
            const response = await PrintingPricing.API.orders.get(this.config.orderId);
            
            if (response.success) {
                // تحديث البيانات المعروضة
                this.updateOrderDisplay(response.data);
                this.loadActivityHistory();
            }
        } catch (error) {
            PrintingPricing.Utils.log('Failed to refresh order data', 'error', error);
        }
    },

    /**
     * تحديث عرض الطلب
     * Update Order Display
     */
    updateOrderDisplay: function(orderData) {
        // تحديث الحقول القابلة للتحديث
        const updatableFields = [
            'title', 'customer', 'quantity', 'description',
            'total_cost', 'material_cost', 'printing_cost', 'services_cost'
        ];

        updatableFields.forEach(field => {
            const elements = document.querySelectorAll(`[data-field="${field}"]`);
            elements.forEach(element => {
                if (orderData[field] !== undefined) {
                    element.textContent = orderData[field];
                }
            });
        });

        // تحديث الحالة
        if (orderData.status !== this.config.status) {
            this.updateOrderStatus(orderData.status);
        }
    },

    /**
     * بدء التحديث التلقائي
     * Start Auto Refresh
     */
    startAutoRefresh: function() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }

        this.refreshTimer = setInterval(() => {
            this.refreshOrderData();
        }, this.config.refreshInterval);
    },

    /**
     * إيقاف التحديث التلقائي
     * Stop Auto Refresh
     */
    stopAutoRefresh: function() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    },

    /**
     * معالجة اختصارات لوحة المفاتيح
     * Handle Keyboard Shortcuts
     */
    handleKeyboardShortcuts: function(e) {
        // Ctrl+P - طباعة
        if (e.ctrlKey && e.key === 'p') {
            e.preventDefault();
            this.printOrder();
        }
        
        // Ctrl+D - نسخ الطلب
        if (e.ctrlKey && e.key === 'd') {
            e.preventDefault();
            this.duplicateOrder();
        }
        
        // Ctrl+E - تحرير الطلب
        if (e.ctrlKey && e.key === 'e') {
            e.preventDefault();
            window.location.href = `/printing-pricing/orders/${this.config.orderId}/edit/`;
        }
    },

    /**
     * تنظيف الموارد
     * Cleanup
     */
    destroy: function() {
        this.stopAutoRefresh();
        this.isInitialized = false;
    }
};

// تنظيف عند مغادرة الصفحة
window.addEventListener('beforeunload', () => {
    PrintingPricing.OrderDetail.destroy();
});
