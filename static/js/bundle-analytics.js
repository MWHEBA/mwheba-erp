/**
 * JavaScript لوحة تحليلات المنتجات المجمعة
 */

const BundleAnalytics = {
    charts: {},
    
    /**
     * تهيئة جميع الرسوم البيانية
     */
    initializeCharts: function() {
        this.initializeBundleDistributionChart();
        this.initializeBundleCreationTrendChart();
    },
    
    /**
     * رسم بياني لتوزيع المنتجات المجمعة
     */
    initializeBundleDistributionChart: function() {
        const ctx = document.getElementById('bundleDistributionChart');
        if (!ctx) return;
        
        // بيانات وهمية للعرض
        const data = {
            labels: ['منتجات نشطة', 'منتجات غير نشطة', 'منتجات بمخزون منخفض'],
            datasets: [{
                data: [65, 25, 10],
                backgroundColor: [
                    'rgba(40, 167, 69, 0.8)',
                    'rgba(108, 117, 125, 0.8)',
                    'rgba(255, 193, 7, 0.8)'
                ],
                borderColor: [
                    'rgba(40, 167, 69, 1)',
                    'rgba(108, 117, 125, 1)',
                    'rgba(255, 193, 7, 1)'
                ],
                borderWidth: 2
            }]
        };
        
        this.charts.distribution = new Chart(ctx, {
            type: 'doughnut',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            usePointStyle: true
                        }
                    }
                }
            }
        });
    },
    
    /**
     * رسم بياني لاتجاه إنشاء المنتجات المجمعة
     */
    initializeBundleCreationTrendChart: function() {
        const ctx = document.getElementById('bundleCreationTrendChart');
        if (!ctx) return;
        
        // بيانات وهمية للعرض
        const data = {
            labels: ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو'],
            datasets: [{
                label: 'منتجات مجمعة جديدة',
                data: [5, 8, 12, 15, 10, 18],
                borderColor: 'rgba(0, 123, 255, 1)',
                backgroundColor: 'rgba(0, 123, 255, 0.1)',
                borderWidth: 3,
                fill: true,
                tension: 0.4
            }]
        };
        
        this.charts.trend = new Chart(ctx, {
            type: 'line',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 5
                        }
                    }
                }
            }
        });
    },
    
    /**
     * تحديث البيانات من API
     */
    refreshData: function() {
        // يمكن إضافة استدعاءات API هنا لاحقاً
    }
};

// تهيئة عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    if (typeof Chart !== 'undefined') {
        BundleAnalytics.initializeCharts();
    }
});