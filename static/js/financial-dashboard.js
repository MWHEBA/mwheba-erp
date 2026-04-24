/**
 * Financial Dashboard JavaScript
 * يدير الرسوم البيانية والتفاعلات في لوحة التحكم المالية
 */

class FinancialDashboard {
    constructor(options = {}) {
        this.options = {
            theme: options.theme || 'default',
            academic_year: options.academic_year || '',
            parent_filter: options.parent_filter || '',
            animation: options.animation !== false,
            responsive: options.responsive !== false
        };
        
        this.charts = {};
        this.colors = this.getColorScheme(this.options.theme);
        
        // تكوين Chart.js العام
        Chart.defaults.font.family = 'Cairo, sans-serif';
        Chart.defaults.font.size = 12;
        Chart.defaults.color = '#374151';
        Chart.defaults.borderColor = '#E5E7EB';
        Chart.defaults.backgroundColor = '#F9FAFB';
    }
    
    /**
     * الحصول على نظام الألوان
     */
    getColorScheme(theme) {
        const schemes = {
            default: [
                '#3B82F6', '#10B981', '#F59E0B', '#EF4444',
                '#8B5CF6', '#06B6D4', '#84CC16', '#F97316'
            ],
            professional: [
                '#1E40AF', '#059669', '#D97706', '#DC2626',
                '#7C3AED', '#0891B2', '#65A30D', '#EA580C'
            ],
            colorful: [
                '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4',
                '#FFEAA7', '#DDA0DD', '#98D8C8', '#F7DC6F'
            ]
        };
        
        return schemes[theme] || schemes.default;
    }
    
    /**
     * إنشاء رسم بياني
     */
    initChart(canvasId, chartData) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            console.error(`Canvas element ${canvasId} not found`);
            return null;
        }
        
        const ctx = canvas.getContext('2d');
        
        // تدمير الرسم السابق إذا كان موجوداً
        if (this.charts[canvasId]) {
            this.charts[canvasId].destroy();
        }
        
        // إعداد البيانات
        const config = this.prepareChartConfig(chartData);
        
        // إنشاء الرسم الجديد
        try {
            this.charts[canvasId] = new Chart(ctx, config);
            return this.charts[canvasId];
        } catch (error) {
            console.error(`Error creating chart ${canvasId}:`, error);
            this.showChartError(canvasId);
            return null;
        }
    }
    
    /**
     * إعداد تكوين الرسم البياني
     */
    prepareChartConfig(chartData) {
        const config = {
            type: chartData.chart_type,
            data: {
                labels: chartData.labels,
                datasets: this.prepareDatasets(chartData.datasets, chartData.chart_type)
            },
            options: this.prepareOptions(chartData.options, chartData.chart_type)
        };
        
        return config;
    }
    
    /**
     * إعداد مجموعات البيانات
     */
    prepareDatasets(datasets, chartType) {
        return datasets.map((dataset, index) => {
            const color = this.colors[index % this.colors.length];
            
            // إعداد الألوان حسب نوع الرسم
            if (chartType === 'pie' || chartType === 'doughnut') {
                return {
                    ...dataset,
                    backgroundColor: dataset.backgroundColor || this.colors.map(c => c + '80'),
                    borderColor: dataset.borderColor || this.colors,
                    borderWidth: dataset.borderWidth || 2
                };
            } else {
                return {
                    ...dataset,
                    backgroundColor: dataset.backgroundColor || (color + '80'),
                    borderColor: dataset.borderColor || color,
                    borderWidth: dataset.borderWidth || 2,
                    tension: dataset.tension || 0.4,
                    fill: dataset.fill !== undefined ? dataset.fill : (chartType === 'area')
                };
            }
        });
    }
    
    /**
     * إعداد خيارات الرسم
     */
    prepareOptions(options, chartType) {
        const baseOptions = {
            responsive: this.options.responsive,
            maintainAspectRatio: false,
            animation: {
                duration: this.options.animation ? 1000 : 0,
                easing: 'easeInOutQuart'
            },
            plugins: {
                legend: {
                    display: true,
                    position: chartType === 'pie' || chartType === 'doughnut' ? 'right' : 'top',
                    labels: {
                        usePointStyle: true,
                        padding: 20,
                        font: {
                            family: 'Cairo, sans-serif',
                            size: 12
                        }
                    }
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#ffffff',
                    bodyColor: '#ffffff',
                    borderColor: '#ffffff',
                    borderWidth: 1,
                    cornerRadius: 6,
                    displayColors: true,
                    titleFont: {
                        family: 'Cairo, sans-serif',
                        size: 14,
                        weight: 'bold'
                    },
                    bodyFont: {
                        family: 'Cairo, sans-serif',
                        size: 12
                    },
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            
                            // تنسيق الأرقام
                            const value = context.parsed.y !== undefined ? context.parsed.y : context.parsed;
                            label += new Intl.NumberFormat('en-US').format(value);
                            
                            // إضافة الوحدة حسب السياق
                            if (context.dataset.label && context.dataset.label.includes('جنيه')) {
                                label += ' جنيه';
                            } else if (context.dataset.label && context.dataset.label.includes('%')) {
                                label += '%';
                            }
                            
                            return label;
                        }
                    }
                }
            }
        };
        
        // إضافة المحاور للرسوم التي تحتاجها
        if (chartType === 'bar' || chartType === 'line') {
            baseOptions.scales = {
                x: {
                    grid: {
                        display: true,
                        color: 'rgba(0, 0, 0, 0.1)'
                    },
                    ticks: {
                        font: {
                            family: 'Cairo, sans-serif',
                            size: 11
                        }
                    }
                },
                y: {
                    grid: {
                        display: true,
                        color: 'rgba(0, 0, 0, 0.1)'
                    },
                    ticks: {
                        font: {
                            family: 'Cairo, sans-serif',
                            size: 11
                        },
                        callback: function(value) {
                            return new Intl.NumberFormat('en-US').format(value);
                        }
                    }
                }
            };
        }
        
        // دمج الخيارات المخصصة
        return this.deepMerge(baseOptions, options || {});
    }
    
    /**
     * دمج عميق للكائنات
     */
    deepMerge(target, source) {
        const result = { ...target };
        
        for (const key in source) {
            if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                result[key] = this.deepMerge(result[key] || {}, source[key]);
            } else {
                result[key] = source[key];
            }
        }
        
        return result;
    }
    
    /**
     * عرض خطأ في الرسم البياني
     */
    showChartError(canvasId) {
        const canvas = document.getElementById(canvasId);
        if (canvas) {
            const container = canvas.parentElement;
            container.innerHTML = `
                <div class="chart-error">
                    <i class="fas fa-exclamation-triangle text-warning"></i>
                    <p class="mt-2 mb-0">حدث خطأ في تحميل الرسم البياني</p>
                    <button class="btn btn-sm btn-outline-primary mt-2" onclick="location.reload()">
                        إعادة المحاولة
                    </button>
                </div>
            `;
        }
    }
    
    /**
     * إظهار حالة التحميل
     */
    showLoading(canvasId) {
        const loadingElement = document.getElementById(canvasId + 'Loading');
        if (loadingElement) {
            loadingElement.style.display = 'flex';
        }
    }
    
    /**
     * إخفاء حالة التحميل
     */
    hideLoading(canvasId) {
        const loadingElement = document.getElementById(canvasId + 'Loading');
        if (loadingElement) {
            loadingElement.style.display = 'none';
        }
    }
    
    /**
     * تحديث بيانات الرسم
     */
    updateChart(canvasId, newData) {
        const chart = this.charts[canvasId];
        if (!chart) {
            console.error(`Chart ${canvasId} not found`);
            return;
        }
        
        try {
            // تحديث البيانات
            chart.data.labels = newData.labels;
            chart.data.datasets = this.prepareDatasets(newData.datasets, chart.config.type);
            
            // إعادة رسم الرسم البياني
            chart.update('active');
        } catch (error) {
            console.error(`Error updating chart ${canvasId}:`, error);
        }
    }
    
    /**
     * تحديث جميع البيانات
     */
    async refreshData() {
        try {
            // إظهار حالة التحميل لجميع الرسوم
            Object.keys(this.charts).forEach(canvasId => {
                this.showLoading(canvasId);
            });
            
            // جلب البيانات الجديدة
            const response = await fetch(window.location.href, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (!response.ok) {
                throw new Error('فشل في جلب البيانات');
            }
            
            const data = await response.json();
            
            // تحديث الرسوم البيانية
            if (data.charts_data) {
                Object.keys(data.charts_data).forEach(chartKey => {
                    const canvasId = this.getCanvasIdFromChartKey(chartKey);
                    if (canvasId && this.charts[canvasId]) {
                        this.updateChart(canvasId, data.charts_data[chartKey]);
                    }
                });
            }
            
            // تحديث الإحصائيات
            if (data.dashboard_data) {
                this.updateStatistics(data.dashboard_data);
            }
            
        } catch (error) {
            console.error('خطأ في تحديث البيانات:', error);
            this.showRefreshError();
        } finally {
            // إخفاء حالة التحميل
            Object.keys(this.charts).forEach(canvasId => {
                this.hideLoading(canvasId);
            });
        }
    }
    
    /**
     * تحويل مفتاح الرسم إلى معرف Canvas
     */
    getCanvasIdFromChartKey(chartKey) {
        const mapping = {
            'fee_distribution': 'feeDistributionChart',
            'payment_timeline': 'paymentTimelineChart',
            'overdue_analysis': 'overdueAnalysisChart',
            'collection_efficiency': 'collectionEfficiencyChart',
            'forecast_chart': 'forecastChart',
            'parent_comparison': 'parentComparisonChart'
        };
        
        return mapping[chartKey];
    }
    
    /**
     * تحديث الإحصائيات
     */
    updateStatistics(dashboardData) {
        // تحديث البطاقات الإحصائية
        const statCards = document.querySelectorAll('.stat-card');
        
        if (dashboardData.basic_stats) {
            const stats = dashboardData.basic_stats;
            
            // تحديث القيم
            this.updateStatValue(0, stats.total_fees);
            this.updateStatValue(1, stats.total_paid);
            this.updateStatValue(2, stats.total_outstanding);
        }
        
        // تحديث مؤشرات المخاطر
        if (dashboardData.risk_indicators) {
            this.updateRiskIndicators(dashboardData.risk_indicators);
        }
    }
    
    /**
     * تحديث قيمة إحصائية
     */
    updateStatValue(index, value) {
        const statCards = document.querySelectorAll('.stat-card');
        if (statCards[index]) {
            const valueElement = statCards[index].querySelector('.stat-value');
            if (valueElement) {
                valueElement.textContent = new Intl.NumberFormat('en-US').format(value);
            }
        }
    }
    
    /**
     * تحديث مؤشرات المخاطر
     */
    updateRiskIndicators(riskData) {
        const riskCards = document.querySelectorAll('.risk-card');
        
        const risks = [
            riskData.overall_risk,
            riskData.overdue_risk,
            riskData.concentration_risk,
            riskData.seasonal_risk
        ];
        
        risks.forEach((risk, index) => {
            if (riskCards[index]) {
                const valueElement = riskCards[index].querySelector('.risk-value');
                if (valueElement) {
                    valueElement.textContent = risk.toFixed(1) + '%';
                }
                
                // تحديث لون البطاقة
                riskCards[index].className = riskCards[index].className.replace(/\b(low|medium|high)\b/g, '');
                if (risk < 25) {
                    riskCards[index].classList.add('low');
                } else if (risk < 50) {
                    riskCards[index].classList.add('medium');
                } else {
                    riskCards[index].classList.add('high');
                }
            }
        });
    }
    
    /**
     * عرض خطأ التحديث
     */
    showRefreshError() {
        // يمكن إضافة toast notification هنا
        console.error('فشل في تحديث البيانات');
    }
    
    /**
     * تصدير الرسم البياني كصورة
     */
    exportChart(canvasId, filename) {
        const chart = this.charts[canvasId];
        if (!chart) {
            console.error(`Chart ${canvasId} not found`);
            return;
        }
        
        try {
            const url = chart.toBase64Image();
            const link = document.createElement('a');
            link.download = filename || `chart-${canvasId}.png`;
            link.href = url;
            link.click();
        } catch (error) {
            console.error('خطأ في تصدير الرسم البياني:', error);
        }
    }
    
    /**
     * تصدير جميع الرسوم البيانية
     */
    exportAllCharts() {
        Object.keys(this.charts).forEach(canvasId => {
            this.exportChart(canvasId, `financial-chart-${canvasId}.png`);
        });
    }
    
    /**
     * تدمير جميع الرسوم البيانية
     */
    destroy() {
        Object.values(this.charts).forEach(chart => {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        });
        this.charts = {};
    }
}

// دوال مساعدة عامة
window.FinancialDashboard = FinancialDashboard;

// تصدير البيانات كـ CSV
function exportToCSV(data, filename) {
    const csv = convertToCSV(data);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    
    if (link.download !== undefined) {
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', filename);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
}

// تحويل البيانات إلى CSV
function convertToCSV(data) {
    if (!data || data.length === 0) {
        return '';
    }
    
    const headers = Object.keys(data[0]);
    const csvContent = [
        headers.join(','),
        ...data.map(row => headers.map(header => `"${row[header]}"`).join(','))
    ].join('\n');
    
    return csvContent;
}

// تنسيق الأرقام للعرض
function formatNumber(number, decimals = 0) {
    return new Intl.NumberFormat('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(number);
}

// تنسيق العملة
function formatCurrency(amount) {
    const formattedNumber = new Intl.NumberFormat('en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount);
    return `${formattedNumber} ج.م`;
}