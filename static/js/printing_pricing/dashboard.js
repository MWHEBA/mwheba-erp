/**
 * نظام التسعير المحسن - لوحة التحكم
 * Printing Pricing System - Dashboard
 */

window.PrintingPricing = window.PrintingPricing || {};

PrintingPricing.Dashboard = {
    
    // إعدادات لوحة التحكم
    config: {
        refreshInterval: 30000, // 30 seconds
        chartColors: {
            primary: '#2c3e50',
            secondary: '#3498db',
            success: '#27ae60',
            warning: '#f39c12',
            danger: '#e74c3c'
        }
    },

    // متغيرات عامة
    charts: {},
    refreshTimer: null,
    isInitialized: false,

    /**
     * تهيئة لوحة التحكم
     * Initialize Dashboard
     */
    init: function() {
        if (this.isInitialized) return;

        PrintingPricing.Utils.log('Initializing Dashboard', 'info');

        this.bindEvents();
        this.loadStatistics();
        this.initializeCharts();
        this.loadRecentActivities();
        this.startAutoRefresh();

        this.isInitialized = true;
        PrintingPricing.Utils.log('Dashboard initialized successfully', 'info');
    },

    /**
     * ربط الأحداث
     * Bind Events
     */
    bindEvents: function() {
        // تحديث الإحصائيات عند النقر
        document.querySelectorAll('.pp-stat-card').forEach(card => {
            card.addEventListener('click', () => {
                this.animateStatCard(card);
            });
        });

        // تحديث البيانات
        const refreshBtn = document.getElementById('refresh-dashboard');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.refreshData();
            });
        }

        // البحث السريع
        const quickSearch = document.getElementById('quick-search');
        if (quickSearch) {
            quickSearch.addEventListener('input', PrintingPricing.Utils.debounce((e) => {
                this.performQuickSearch(e.target.value);
            }, 300));
        }

        // إغلاق النوافذ المنبثقة عند الضغط على Escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModals();
            }
        });
    },

    /**
     * تحميل الإحصائيات
     * Load Statistics
     */
    loadStatistics: async function() {
        try {
            const response = await PrintingPricing.API.get('dashboard/stats/');
            
            if (response.success) {
                this.updateStatistics(response.data);
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.log('Failed to load statistics', 'error', error);
            PrintingPricing.Utils.showToast('فشل في تحميل الإحصائيات', 'error');
        }
    },

    /**
     * تحديث الإحصائيات
     * Update Statistics
     */
    updateStatistics: function(stats) {
        const elements = {
            'total-orders': stats.total_orders || 0,
            'pending-orders': stats.pending_orders || 0,
            'completed-orders': stats.completed_orders || 0,
            'total-revenue': PrintingPricing.Utils.formatCurrency(stats.total_revenue || 0)
        };

        Object.keys(elements).forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                this.animateNumber(element, elements[id]);
            }
        });
    },

    /**
     * تحريك الأرقام
     * Animate Numbers
     */
    animateNumber: function(element, targetValue) {
        const isNumeric = !isNaN(targetValue);
        const startValue = isNumeric ? parseInt(element.textContent) || 0 : 0;
        const target = isNumeric ? parseInt(targetValue) : targetValue;
        
        if (!isNumeric) {
            element.textContent = target;
            return;
        }

        const duration = 1000;
        const startTime = performance.now();
        
        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            const currentValue = Math.floor(startValue + (target - startValue) * progress);
            element.textContent = currentValue.toLocaleString();
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        };
        
        requestAnimationFrame(animate);
    },

    /**
     * تحريك بطاقة الإحصائية
     * Animate Stat Card
     */
    animateStatCard: function(card) {
        card.style.transform = 'scale(0.95)';
        setTimeout(() => {
            card.style.transform = 'scale(1)';
        }, 150);
    },

    /**
     * تهيئة الرسوم البيانية
     * Initialize Charts
     */
    initializeCharts: function() {
        this.initOrderStatusChart();
        this.initRevenueChart();
    },

    /**
     * رسم بياني لحالة الطلبات
     * Order Status Chart
     */
    initOrderStatusChart: function() {
        const canvas = document.getElementById('orders-status-chart');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        
        // Mock data - replace with real data from API
        const data = {
            labels: ['مسودة', 'قيد المراجعة', 'معتمد', 'مكتمل', 'مرفوض'],
            datasets: [{
                data: [12, 19, 8, 25, 3],
                backgroundColor: [
                    this.config.chartColors.secondary,
                    this.config.chartColors.warning,
                    this.config.chartColors.success,
                    this.config.chartColors.primary,
                    this.config.chartColors.danger
                ],
                borderWidth: 2,
                borderColor: '#fff'
            }]
        };

        // Simple pie chart implementation
        this.drawPieChart(ctx, data, canvas.width, canvas.height);
    },

    /**
     * رسم دائري بسيط
     * Simple Pie Chart
     */
    drawPieChart: function(ctx, data, width, height) {
        const centerX = width / 2;
        const centerY = height / 2;
        const radius = Math.min(width, height) / 2 - 20;
        
        const total = data.datasets[0].data.reduce((sum, value) => sum + value, 0);
        let currentAngle = -Math.PI / 2;

        data.datasets[0].data.forEach((value, index) => {
            const sliceAngle = (value / total) * 2 * Math.PI;
            
            // Draw slice
            ctx.beginPath();
            ctx.moveTo(centerX, centerY);
            ctx.arc(centerX, centerY, radius, currentAngle, currentAngle + sliceAngle);
            ctx.closePath();
            ctx.fillStyle = data.datasets[0].backgroundColor[index];
            ctx.fill();
            ctx.strokeStyle = data.datasets[0].borderColor || '#fff';
            ctx.lineWidth = data.datasets[0].borderWidth || 1;
            ctx.stroke();

            // Draw label
            const labelAngle = currentAngle + sliceAngle / 2;
            const labelX = centerX + Math.cos(labelAngle) * (radius * 0.7);
            const labelY = centerY + Math.sin(labelAngle) * (radius * 0.7);
            
            ctx.fillStyle = '#fff';
            ctx.font = '12px Arial';
            ctx.textAlign = 'center';
            ctx.fillText(value.toString(), labelX, labelY);

            currentAngle += sliceAngle;
        });

        // Draw legend
        this.drawChartLegend(ctx, data, width, height);
    },

    /**
     * رسم مفتاح الرسم البياني
     * Draw Chart Legend
     */
    drawChartLegend: function(ctx, data, width, height) {
        const legendY = height - 60;
        const legendItemWidth = width / data.labels.length;
        
        data.labels.forEach((label, index) => {
            const x = index * legendItemWidth + 10;
            
            // Draw color box
            ctx.fillStyle = data.datasets[0].backgroundColor[index];
            ctx.fillRect(x, legendY, 12, 12);
            
            // Draw label
            ctx.fillStyle = '#333';
            ctx.font = '10px Arial';
            ctx.textAlign = 'left';
            ctx.fillText(label, x + 16, legendY + 10);
        });
    },

    /**
     * رسم بياني للإيرادات
     * Revenue Chart
     */
    initRevenueChart: function() {
        const canvas = document.getElementById('revenue-chart');
        if (!canvas) return;

        // Implementation for revenue chart
        // This would typically use a charting library like Chart.js
    },

    /**
     * تحميل الأنشطة الحديثة
     * Load Recent Activities
     */
    loadRecentActivities: async function() {
        try {
            const response = await PrintingPricing.API.get('dashboard/activities/');
            
            if (response.success) {
                this.updateActivitiesFeed(response.data);
            }
        } catch (error) {
            PrintingPricing.Utils.log('Failed to load activities', 'error', error);
        }
    },

    /**
     * تحديث تغذية الأنشطة
     * Update Activities Feed
     */
    updateActivitiesFeed: function(activities) {
        const feed = document.getElementById('activity-feed');
        if (!feed) return;

        if (activities.length === 0) {
            feed.innerHTML = `
                <div class="text-center text-muted py-3">
                    <i class="fas fa-history fa-2x mb-2"></i><br>
                    لا توجد أنشطة حديثة
                </div>
            `;
            return;
        }

        const activitiesHTML = activities.map(activity => `
            <div class="pp-activity-item">
                <div class="pp-activity-icon pp-activity-${activity.type}">
                    <i class="fas fa-${activity.icon}"></i>
                </div>
                <div class="pp-activity-content">
                    <div class="pp-activity-text">${activity.description}</div>
                    <div class="pp-activity-time">${this.formatTimeAgo(activity.created_at)}</div>
                </div>
            </div>
        `).join('');

        feed.innerHTML = activitiesHTML;
    },

    /**
     * تنسيق الوقت المنقضي
     * Format Time Ago
     */
    formatTimeAgo: function(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffInSeconds = Math.floor((now - date) / 1000);

        if (diffInSeconds < 60) {
            return 'منذ لحظات';
        } else if (diffInSeconds < 3600) {
            const minutes = Math.floor(diffInSeconds / 60);
            return `منذ ${minutes} دقيقة`;
        } else if (diffInSeconds < 86400) {
            const hours = Math.floor(diffInSeconds / 3600);
            return `منذ ${hours} ساعة`;
        } else {
            const days = Math.floor(diffInSeconds / 86400);
            return `منذ ${days} يوم`;
        }
    },

    /**
     * البحث السريع
     * Quick Search
     */
    performQuickSearch: async function(query) {
        if (!query || query.length < 2) return;

        try {
            const response = await PrintingPricing.API.get('search/', { q: query });
            
            if (response.success) {
                this.displaySearchResults(response.data);
            }
        } catch (error) {
            PrintingPricing.Utils.log('Search failed', 'error', error);
        }
    },

    /**
     * عرض نتائج البحث
     * Display Search Results
     */
    displaySearchResults: function(results) {
        // Implementation for displaying search results
        console.log('Search results:', results);
    },

    /**
     * عرض الإجراءات السريعة
     * Show Quick Actions
     */
    showQuickActions: function() {
        const actions = [
            { icon: 'plus', text: 'طلب جديد', action: () => window.location.href = '/printing-pricing/orders/create/' },
            { icon: 'copy', text: 'نسخ طلب', action: () => this.showCopyOrderModal() },
            { icon: 'calculator', text: 'حاسبة سريعة', action: () => this.showQuickCalculator() },
            { icon: 'download', text: 'تصدير البيانات', action: () => this.exportData() }
        ];

        const actionsHTML = actions.map(action => `
            <button class="pp-quick-action-item" onclick="(${action.action.toString()})()">
                <i class="fas fa-${action.icon}"></i>
                <span>${action.text}</span>
            </button>
        `).join('');

        PrintingPricing.Utils.showModal('الإجراءات السريعة', `
            <div class="pp-quick-actions-grid">
                ${actionsHTML}
            </div>
        `);
    },

    /**
     * عرض نافذة نسخ الطلب
     * Show Copy Order Modal
     */
    showCopyOrderModal: function() {
        PrintingPricing.Utils.showModal('نسخ طلب موجود', `
            <div class="pp-form-group">
                <label class="pp-form-label">رقم الطلب المراد نسخه</label>
                <input type="text" class="pp-form-control" id="copy-order-number" placeholder="أدخل رقم الطلب">
            </div>
        `, {
            footer: `
                <button class="pp-btn pp-btn-secondary" onclick="this.closest('.pp-modal').remove()">إلغاء</button>
                <button class="pp-btn pp-btn-primary" onclick="PrintingPricing.Dashboard.copyOrder()">نسخ الطلب</button>
            `
        });
    },

    /**
     * نسخ طلب
     * Copy Order
     */
    copyOrder: async function() {
        const orderNumber = document.getElementById('copy-order-number').value;
        if (!orderNumber) {
            PrintingPricing.Utils.showToast('يرجى إدخال رقم الطلب', 'warning');
            return;
        }

        try {
            const response = await PrintingPricing.API.post('orders/copy/', { order_number: orderNumber });
            
            if (response.success) {
                PrintingPricing.Utils.showToast('تم نسخ الطلب بنجاح', 'success');
                window.location.href = `/printing-pricing/orders/${response.data.id}/`;
            } else {
                throw new Error(response.error);
            }
        } catch (error) {
            PrintingPricing.Utils.showToast('فشل في نسخ الطلب', 'error');
        }
    },

    /**
     * عرض الحاسبة السريعة
     * Show Quick Calculator
     */
    showQuickCalculator: function() {
        PrintingPricing.Utils.showModal('حاسبة سريعة', `
            <div class="pp-quick-calculator">
                <div class="row">
                    <div class="col-md-6">
                        <div class="pp-form-group">
                            <label class="pp-form-label">الكمية</label>
                            <input type="number" class="pp-form-control" id="calc-quantity" value="1000">
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="pp-form-group">
                            <label class="pp-form-label">سعر الوحدة</label>
                            <input type="number" class="pp-form-control" id="calc-unit-price" step="0.01">
                        </div>
                    </div>
                </div>
                <div class="pp-calculation-result">
                    <div class="pp-result-label">التكلفة الإجمالية:</div>
                    <div class="pp-result-value" id="calc-total">0.00 جنيه</div>
                </div>
            </div>
        `);

        // Bind calculation events
        ['calc-quantity', 'calc-unit-price'].forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('input', this.updateQuickCalculation);
            }
        });
    },

    /**
     * تحديث الحساب السريع
     * Update Quick Calculation
     */
    updateQuickCalculation: function() {
        const quantity = parseFloat(document.getElementById('calc-quantity').value) || 0;
        const unitPrice = parseFloat(document.getElementById('calc-unit-price').value) || 0;
        const total = quantity * unitPrice;
        
        const resultElement = document.getElementById('calc-total');
        if (resultElement) {
            resultElement.textContent = PrintingPricing.Utils.formatCurrency(total);
        }
    },

    /**
     * تصدير البيانات
     * Export Data
     */
    exportData: async function() {
        try {
            const response = await PrintingPricing.API.get('dashboard/export/');
            
            if (response.success) {
                PrintingPricing.Utils.downloadFile(
                    response.data,
                    `dashboard_export_${new Date().toISOString().split('T')[0]}.csv`,
                    'text/csv'
                );
                PrintingPricing.Utils.showToast('تم تصدير البيانات بنجاح', 'success');
            }
        } catch (error) {
            PrintingPricing.Utils.showToast('فشل في تصدير البيانات', 'error');
        }
    },

    /**
     * تحديث البيانات
     * Refresh Data
     */
    refreshData: function() {
        PrintingPricing.Utils.showToast('جاري تحديث البيانات...', 'info');
        
        Promise.all([
            this.loadStatistics(),
            this.loadRecentActivities()
        ]).then(() => {
            PrintingPricing.Utils.showToast('تم تحديث البيانات بنجاح', 'success');
        }).catch(() => {
            PrintingPricing.Utils.showToast('فشل في تحديث البيانات', 'error');
        });
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
            this.loadStatistics();
            this.loadRecentActivities();
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
     * إغلاق النوافذ المنبثقة
     * Close Modals
     */
    closeModals: function() {
        document.querySelectorAll('.pp-modal').forEach(modal => {
            modal.remove();
        });
    },

    /**
     * تنظيف الموارد
     * Cleanup
     */
    destroy: function() {
        this.stopAutoRefresh();
        this.closeModals();
        this.isInitialized = false;
    }
};

// تنظيف عند مغادرة الصفحة
window.addEventListener('beforeunload', () => {
    PrintingPricing.Dashboard.destroy();
});
