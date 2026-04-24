/**
 * ========================================
 * Unified Financial Components JavaScript
 * مكونات JavaScript المالية الموحدة
 * ========================================
 * 
 * مكتبة JavaScript متخصصة للمكونات المالية
 * تتضمن وظائف تنسيق العملة، حسابات الأرصدة، والتقارير المالية
 * 
 * المكونات:
 * 1. Currency Formatter (منسق العملة)
 * 2. Financial Calculator (الحاسبة المالية)
 * 3. Chart Integration (تكامل الرسوم البيانية)
 * 4. Report Generator (مولد التقارير)
 * 5. Dashboard Manager (مدير لوحة التحكم)
 * 6. Transaction Manager (مدير المعاملات)
 * 7. Account Manager (مدير الحسابات)
 * 8. Balance Calculator (حاسبة الأرصدة)
 * ========================================
 */

(function(window, document) {
    'use strict';

    // Namespace for financial components
    window.UnifiedFinancial = window.UnifiedFinancial || {};

    /**
     * ========================================
     * 1. CURRENCY FORMATTER (منسق العملة)
     * ========================================
     */

    class CurrencyFormatter {
        constructor(options = {}) {
            this.options = {
                currency: 'EGP',
                locale: 'en-US',
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
                showSymbol: true,
                showCode: false,
                ...options
            };
            
            this.symbols = {
                'EGP': '£',
                'USD': '$',
                'EUR': '€',
                'SAR': '﷼',
                'AED': 'د.إ',
                'JOD': 'د.أ',
                'KWD': 'د.ك'
            };
        }

        format(amount, options = {}) {
            const opts = { ...this.options, ...options };
            
            if (amount === null || amount === undefined || isNaN(amount)) {
                return this.formatZero(opts);
            }

            const numAmount = parseFloat(amount);
            const isNegative = numAmount < 0;
            const absAmount = Math.abs(numAmount);

            // Format the number
            const formatter = new Intl.NumberFormat(opts.locale, {
                minimumFractionDigits: opts.minimumFractionDigits,
                maximumFractionDigits: opts.maximumFractionDigits
            });

            let formattedAmount = formatter.format(absAmount);

            // Add currency symbol or code
            if (opts.showSymbol && this.symbols[opts.currency]) {
                formattedAmount = `${this.symbols[opts.currency]} ${formattedAmount}`;
            } else if (opts.showCode) {
                formattedAmount = `${formattedAmount} ${opts.currency}`;
            }

            // Handle negative amounts
            if (isNegative) {
                formattedAmount = `(${formattedAmount})`;
            }

            return formattedAmount;
        }

        formatZero(options = {}) {
            const opts = { ...this.options, ...options };
            let zero = '0.00';
            
            if (opts.showSymbol && this.symbols[opts.currency]) {
                zero = `${this.symbols[opts.currency]} ${zero}`;
            } else if (opts.showCode) {
                zero = `${zero} ${opts.currency}`;
            }
            
            return zero;
        }

        formatCompact(amount, options = {}) {
            const opts = { ...this.options, ...options };
            
            if (amount === null || amount === undefined || isNaN(amount)) {
                return this.formatZero(opts);
            }

            const numAmount = parseFloat(amount);
            const absAmount = Math.abs(numAmount);
            
            let formattedAmount;
            let suffix = '';

            if (absAmount >= 1000000000) {
                formattedAmount = (absAmount / 1000000000).toFixed(1);
                suffix = 'مليار';
            } else if (absAmount >= 1000000) {
                formattedAmount = (absAmount / 1000000).toFixed(1);
                suffix = 'مليون';
            } else if (absAmount >= 1000) {
                formattedAmount = (absAmount / 1000).toFixed(1);
                suffix = 'ألف';
            } else {
                return this.format(amount, opts);
            }

            // Remove .0 if present
            formattedAmount = formattedAmount.replace('.0', '');
            
            let result = `${formattedAmount} ${suffix}`;
            
            if (opts.showSymbol && this.symbols[opts.currency]) {
                result = `${this.symbols[opts.currency]} ${result}`;
            } else if (opts.showCode) {
                result = `${result} ${opts.currency}`;
            }

            if (numAmount < 0) {
                result = `(${result})`;
            }

            return result;
        }

        getColorClass(amount) {
            if (amount === null || amount === undefined || isNaN(amount)) {
                return 'zero';
            }
            
            const numAmount = parseFloat(amount);
            
            if (numAmount > 0) return 'positive';
            if (numAmount < 0) return 'negative';
            return 'zero';
        }

        createCurrencyElement(amount, options = {}) {
            const opts = { ...this.options, ...options };
            const element = document.createElement('span');
            
            element.className = `unified-currency ${this.getColorClass(amount)}`;
            
            if (opts.size) {
                element.classList.add(`unified-currency-${opts.size}`);
            }
            
            if (opts.badge) {
                element.classList.add('unified-currency-badge');
            }

            const symbol = document.createElement('span');
            symbol.className = 'unified-currency-symbol';
            
            const amountSpan = document.createElement('span');
            amountSpan.className = 'unified-currency-amount';
            
            if (opts.showSymbol && this.symbols[opts.currency]) {
                symbol.textContent = this.symbols[opts.currency];
                element.appendChild(symbol);
            }
            
            amountSpan.textContent = this.format(amount, { ...opts, showSymbol: false, showCode: false });
            element.appendChild(amountSpan);
            
            if (opts.showCode) {
                const code = document.createElement('span');
                code.className = 'unified-currency-code';
                code.textContent = opts.currency;
                element.appendChild(code);
            }

            return element;
        }
    }

    /**
     * ========================================
     * 2. FINANCIAL CALCULATOR (الحاسبة المالية)
     * ========================================
     */

    class FinancialCalculator {
        static add(...amounts) {
            return amounts.reduce((sum, amount) => {
                const num = parseFloat(amount) || 0;
                return sum + num;
            }, 0);
        }

        static subtract(amount1, amount2) {
            const num1 = parseFloat(amount1) || 0;
            const num2 = parseFloat(amount2) || 0;
            return num1 - num2;
        }

        static multiply(amount, factor) {
            const num = parseFloat(amount) || 0;
            const mult = parseFloat(factor) || 0;
            return num * mult;
        }

        static divide(amount, divisor) {
            const num = parseFloat(amount) || 0;
            const div = parseFloat(divisor) || 1;
            return div !== 0 ? num / div : 0;
        }

        static percentage(amount, percent) {
            const num = parseFloat(amount) || 0;
            const pct = parseFloat(percent) || 0;
            return (num * pct) / 100;
        }

        static percentageChange(oldValue, newValue) {
            const old = parseFloat(oldValue) || 0;
            const newVal = parseFloat(newValue) || 0;
            
            if (old === 0) return newVal === 0 ? 0 : 100;
            
            return ((newVal - old) / Math.abs(old)) * 100;
        }

        static round(amount, decimals = 2) {
            const num = parseFloat(amount) || 0;
            return Math.round(num * Math.pow(10, decimals)) / Math.pow(10, decimals);
        }

        static abs(amount) {
            const num = parseFloat(amount) || 0;
            return Math.abs(num);
        }

        static max(...amounts) {
            const numbers = amounts.map(a => parseFloat(a) || 0);
            return Math.max(...numbers);
        }

        static min(...amounts) {
            const numbers = amounts.map(a => parseFloat(a) || 0);
            return Math.min(...numbers);
        }

        static average(...amounts) {
            const numbers = amounts.map(a => parseFloat(a) || 0);
            return numbers.length > 0 ? this.add(...numbers) / numbers.length : 0;
        }

        static sum(amounts) {
            if (!Array.isArray(amounts)) return 0;
            return amounts.reduce((sum, amount) => sum + (parseFloat(amount) || 0), 0);
        }

        // Financial ratios
        static profitMargin(profit, revenue) {
            const p = parseFloat(profit) || 0;
            const r = parseFloat(revenue) || 0;
            return r !== 0 ? (p / r) * 100 : 0;
        }

        static returnOnInvestment(gain, cost) {
            const g = parseFloat(gain) || 0;
            const c = parseFloat(cost) || 0;
            return c !== 0 ? ((g - c) / c) * 100 : 0;
        }

        static growthRate(startValue, endValue, periods) {
            const start = parseFloat(startValue) || 0;
            const end = parseFloat(endValue) || 0;
            const p = parseFloat(periods) || 1;
            
            if (start === 0 || p === 0) return 0;
            
            return (Math.pow(end / start, 1 / p) - 1) * 100;
        }
    }

    /**
     * ========================================
     * 3. CHART INTEGRATION (تكامل الرسوم البيانية)
     * ========================================
     */

    class FinancialChartManager {
        constructor(container, options = {}) {
            this.container = container;
            this.options = {
                currency: 'EGP',
                locale: 'en-US',
                colors: [
                    '#3b82f6', '#10b981', '#f59e0b', '#ef4444', 
                    '#8b5cf6', '#06b6d4', '#84cc16', '#f97316'
                ],
                ...options
            };
            
            this.formatter = new CurrencyFormatter({
                currency: this.options.currency,
                locale: this.options.locale
            });
            
            this.charts = new Map();
        }

        createPieChart(data, options = {}) {
            const chartId = `chart-${Date.now()}`;
            const chartContainer = this.createChartContainer(chartId, options.title);
            
            // Create canvas for chart
            const canvas = document.createElement('canvas');
            canvas.id = chartId;
            chartContainer.querySelector('.unified-financial-chart-wrapper').appendChild(canvas);
            
            // Chart configuration
            const config = {
                type: 'pie',
                data: {
                    labels: data.map(item => item.label),
                    datasets: [{
                        data: data.map(item => item.value),
                        backgroundColor: this.options.colors,
                        borderWidth: 2,
                        borderColor: '#ffffff'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: (context) => {
                                    const value = context.parsed;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = ((value / total) * 100).toFixed(1);
                                    return `${context.label}: ${this.formatter.format(value)} (${percentage}%)`;
                                }
                            }
                        }
                    }
                }
            };

            // Create legend
            this.createLegend(chartContainer, data);
            
            // Create summary
            this.createChartSummary(chartContainer, data);

            return { chartId, config, container: chartContainer };
        }

        createBarChart(data, options = {}) {
            const chartId = `chart-${Date.now()}`;
            const chartContainer = this.createChartContainer(chartId, options.title);
            
            const canvas = document.createElement('canvas');
            canvas.id = chartId;
            chartContainer.querySelector('.unified-financial-chart-wrapper').appendChild(canvas);
            
            const config = {
                type: 'bar',
                data: {
                    labels: data.map(item => item.label),
                    datasets: [{
                        label: options.datasetLabel || 'القيمة',
                        data: data.map(item => item.value),
                        backgroundColor: this.options.colors[0],
                        borderColor: this.options.colors[0],
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: (value) => this.formatter.formatCompact(value)
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: (context) => {
                                    return `${context.dataset.label}: ${this.formatter.format(context.parsed.y)}`;
                                }
                            }
                        }
                    }
                }
            };

            this.createChartSummary(chartContainer, data);

            return { chartId, config, container: chartContainer };
        }

        createLineChart(data, options = {}) {
            const chartId = `chart-${Date.now()}`;
            const chartContainer = this.createChartContainer(chartId, options.title);
            
            const canvas = document.createElement('canvas');
            canvas.id = chartId;
            chartContainer.querySelector('.unified-financial-chart-wrapper').appendChild(canvas);
            
            const config = {
                type: 'line',
                data: {
                    labels: data.map(item => item.label),
                    datasets: [{
                        label: options.datasetLabel || 'القيمة',
                        data: data.map(item => item.value),
                        borderColor: this.options.colors[0],
                        backgroundColor: this.options.colors[0] + '20',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: (value) => this.formatter.formatCompact(value)
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: false
                        },
                        tooltip: {
                            callbacks: {
                                label: (context) => {
                                    return `${context.dataset.label}: ${this.formatter.format(context.parsed.y)}`;
                                }
                            }
                        }
                    }
                }
            };

            this.createChartSummary(chartContainer, data);

            return { chartId, config, container: chartContainer };
        }

        createChartContainer(chartId, title) {
            const container = document.createElement('div');
            container.className = 'unified-financial-chart-container';
            container.innerHTML = `
                <div class="unified-financial-chart-header">
                    <h5 class="unified-financial-chart-title">${title || 'رسم بياني مالي'}</h5>
                    <div class="unified-financial-chart-controls">
                        <button class="unified-btn unified-btn-ghost unified-btn-sm" onclick="UnifiedFinancial.ChartManager.exportChart('${chartId}')">
                            <i class="fas fa-download"></i>
                        </button>
                    </div>
                </div>
                <div class="unified-financial-chart-wrapper"></div>
                <div class="unified-financial-chart-legend"></div>
                <div class="unified-financial-chart-summary"></div>
            `;
            
            this.container.appendChild(container);
            return container;
        }

        createLegend(container, data) {
            const legend = container.querySelector('.unified-financial-chart-legend');
            
            data.forEach((item, index) => {
                const legendItem = document.createElement('div');
                legendItem.className = 'unified-financial-chart-legend-item';
                legendItem.innerHTML = `
                    <div class="unified-financial-chart-legend-color" style="background-color: ${this.options.colors[index % this.options.colors.length]}"></div>
                    <span>${item.label}</span>
                `;
                legend.appendChild(legendItem);
            });
        }

        createChartSummary(container, data) {
            const summary = container.querySelector('.unified-financial-chart-summary');
            const total = FinancialCalculator.sum(data.map(item => item.value));
            const average = FinancialCalculator.average(...data.map(item => item.value));
            const max = FinancialCalculator.max(...data.map(item => item.value));
            const min = FinancialCalculator.min(...data.map(item => item.value));
            
            summary.innerHTML = `
                <div class="unified-financial-chart-summary-item">
                    <div class="unified-financial-chart-summary-label">الإجمالي</div>
                    <div class="unified-financial-chart-summary-value">${this.formatter.format(total)}</div>
                </div>
                <div class="unified-financial-chart-summary-item">
                    <div class="unified-financial-chart-summary-label">المتوسط</div>
                    <div class="unified-financial-chart-summary-value">${this.formatter.format(average)}</div>
                </div>
                <div class="unified-financial-chart-summary-item">
                    <div class="unified-financial-chart-summary-label">الأعلى</div>
                    <div class="unified-financial-chart-summary-value">${this.formatter.format(max)}</div>
                </div>
                <div class="unified-financial-chart-summary-item">
                    <div class="unified-financial-chart-summary-label">الأقل</div>
                    <div class="unified-financial-chart-summary-value">${this.formatter.format(min)}</div>
                </div>
            `;
        }

        exportChart(chartId) {
            // Implementation for chart export
        }
    }

    /**
     * ========================================
     * 4. DASHBOARD MANAGER (مدير لوحة التحكم)
     * ========================================
     */

    class FinancialDashboard {
        constructor(container, options = {}) {
            this.container = container;
            this.options = {
                currency: 'EGP',
                locale: 'en-US',
                autoRefresh: false,
                refreshInterval: 300000, // 5 minutes
                ...options
            };
            
            this.formatter = new CurrencyFormatter({
                currency: this.options.currency,
                locale: this.options.locale
            });
            
            this.widgets = new Map();
            this.refreshTimer = null;
            
            this.init();
        }

        init() {
            this.createDashboardStructure();
            
            if (this.options.autoRefresh) {
                this.startAutoRefresh();
            }
        }

        createDashboardStructure() {
            this.container.className = 'unified-financial-dashboard';
            this.container.innerHTML = `
                <div class="unified-financial-dashboard-header">
                    <h2 class="unified-financial-dashboard-title">لوحة التحكم المالية</h2>
                    <div class="unified-financial-dashboard-period">الفترة: ${this.getCurrentPeriod()}</div>
                    <div class="unified-financial-dashboard-quick-stats"></div>
                </div>
                <div class="unified-financial-dashboard-grid"></div>
            `;
        }

        addQuickStat(label, value, change = null) {
            const quickStats = this.container.querySelector('.unified-financial-dashboard-quick-stats');
            
            const stat = document.createElement('div');
            stat.className = 'unified-financial-dashboard-quick-stat';
            
            let changeHtml = '';
            if (change !== null) {
                const changeClass = change >= 0 ? 'positive' : 'negative';
                const changeIcon = change >= 0 ? 'fa-arrow-up' : 'fa-arrow-down';
                changeHtml = `
                    <div class="unified-amount-change ${changeClass}">
                        <i class="fas ${changeIcon} unified-amount-change-icon"></i>
                        ${Math.abs(change).toFixed(1)}%
                    </div>
                `;
            }
            
            stat.innerHTML = `
                <div class="unified-financial-dashboard-quick-stat-value">${this.formatter.formatCompact(value)}</div>
                <div class="unified-financial-dashboard-quick-stat-label">${label}</div>
                ${changeHtml}
            `;
            
            quickStats.appendChild(stat);
        }

        addWidget(id, title, content, options = {}) {
            const grid = this.container.querySelector('.unified-financial-dashboard-grid');
            
            const widget = document.createElement('div');
            widget.className = 'unified-financial-dashboard-widget';
            widget.id = `widget-${id}`;
            
            widget.innerHTML = `
                <div class="unified-financial-dashboard-widget-header">
                    <h4 class="unified-financial-dashboard-widget-title">${title}</h4>
                    <div class="unified-financial-dashboard-widget-actions">
                        <button class="unified-btn unified-btn-ghost unified-btn-sm" onclick="UnifiedFinancial.Dashboard.refreshWidget('${id}')">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                        <button class="unified-btn unified-btn-ghost unified-btn-sm" onclick="UnifiedFinancial.Dashboard.exportWidget('${id}')">
                            <i class="fas fa-download"></i>
                        </button>
                    </div>
                </div>
                <div class="unified-financial-dashboard-widget-body">
                    ${content}
                </div>
            `;
            
            grid.appendChild(widget);
            this.widgets.set(id, { element: widget, options });
            
            return widget;
        }

        updateWidget(id, content) {
            const widget = this.widgets.get(id);
            if (widget) {
                const body = widget.element.querySelector('.unified-financial-dashboard-widget-body');
                body.innerHTML = content;
            }
        }

        refreshWidget(id) {
            const widget = this.widgets.get(id);
            if (widget && widget.options.onRefresh) {
                widget.options.onRefresh(id);
            }
        }

        exportWidget(id) {
            const widget = this.widgets.get(id);
            if (widget && widget.options.onExport) {
                widget.options.onExport(id);
            }
        }

        startAutoRefresh() {
            this.refreshTimer = setInterval(() => {
                this.refreshAllWidgets();
            }, this.options.refreshInterval);
        }

        stopAutoRefresh() {
            if (this.refreshTimer) {
                clearInterval(this.refreshTimer);
                this.refreshTimer = null;
            }
        }

        refreshAllWidgets() {
            this.widgets.forEach((widget, id) => {
                this.refreshWidget(id);
            });
        }

        getCurrentPeriod() {
            const now = new Date();
            const year = now.getFullYear();
            // استخدام أسماء الأشهر العربية مع أرقام إنجليزية
            const monthNames = [
                'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
                'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
            ];
            const month = monthNames[now.getMonth()];
            return `${month} ${year}`;
        }

        destroy() {
            this.stopAutoRefresh();
            this.widgets.clear();
            this.container.innerHTML = '';
        }
    }

    /**
     * ========================================
     * 5. TRANSACTION MANAGER (مدير المعاملات)
     * ========================================
     */

    class TransactionManager {
        constructor(container, options = {}) {
            this.container = container;
            this.options = {
                currency: 'EGP',
                locale: 'en-US',
                showEntries: true,
                groupByDate: false,
                ...options
            };
            
            this.formatter = new CurrencyFormatter({
                currency: this.options.currency,
                locale: this.options.locale
            });
            
            this.transactions = [];
        }

        addTransaction(transaction) {
            this.transactions.push({
                id: transaction.id || Date.now(),
                date: new Date(transaction.date),
                description: transaction.description,
                amount: parseFloat(transaction.amount),
                type: transaction.type || 'expense',
                entries: transaction.entries || [],
                ...transaction
            });
            
            this.render();
        }

        removeTransaction(id) {
            this.transactions = this.transactions.filter(t => t.id !== id);
            this.render();
        }

        updateTransaction(id, updates) {
            const index = this.transactions.findIndex(t => t.id === id);
            if (index !== -1) {
                this.transactions[index] = { ...this.transactions[index], ...updates };
                this.render();
            }
        }

        render() {
            this.container.innerHTML = '';
            
            const sortedTransactions = [...this.transactions].sort((a, b) => b.date - a.date);
            
            if (this.options.groupByDate) {
                this.renderGrouped(sortedTransactions);
            } else {
                this.renderFlat(sortedTransactions);
            }
        }

        renderFlat(transactions) {
            transactions.forEach(transaction => {
                const element = this.createTransactionElement(transaction);
                this.container.appendChild(element);
            });
        }

        renderGrouped(transactions) {
            const groups = this.groupTransactionsByDate(transactions);
            
            Object.keys(groups).forEach(date => {
                const groupHeader = document.createElement('div');
                groupHeader.className = 'transaction-group-header';
                groupHeader.innerHTML = `
                    <h5>${date}</h5>
                    <span class="transaction-group-total">${this.formatter.format(this.calculateGroupTotal(groups[date]))}</span>
                `;
                this.container.appendChild(groupHeader);
                
                groups[date].forEach(transaction => {
                    const element = this.createTransactionElement(transaction);
                    this.container.appendChild(element);
                });
            });
        }

        createTransactionElement(transaction) {
            const element = document.createElement('div');
            element.className = 'unified-transaction-item';
            element.dataset.transactionId = transaction.id;
            
            const typeIcon = this.getTransactionIcon(transaction.type);
            const amountClass = transaction.type === 'income' ? 'income' : 'expense';
            
            let entriesHtml = '';
            if (this.options.showEntries && transaction.entries && transaction.entries.length > 0) {
                entriesHtml = `
                    <div class="unified-transaction-entries">
                        ${transaction.entries.map(entry => `
                            <div class="unified-transaction-entry">
                                <span class="unified-transaction-entry-account">${entry.account}</span>
                                <span class="unified-transaction-entry-amount unified-transaction-entry-${entry.type}">
                                    ${this.formatter.format(entry.amount)}
                                </span>
                            </div>
                        `).join('')}
                    </div>
                `;
            }
            
            element.innerHTML = `
                <div class="unified-transaction-header">
                    <div class="unified-transaction-info">
                        <div class="unified-transaction-icon ${transaction.type}">
                            <i class="fas ${typeIcon}"></i>
                        </div>
                        <div class="unified-transaction-details">
                            <div class="unified-transaction-description">${transaction.description}</div>
                            <div class="unified-transaction-meta">
                                <span><i class="fas fa-calendar"></i> ${transaction.date.toLocaleDateString('en-GB')}</span>
                                <span><i class="fas fa-tag"></i> ${this.getTransactionTypeLabel(transaction.type)}</span>
                            </div>
                        </div>
                    </div>
                    <div class="unified-transaction-amount ${amountClass}">
                        ${this.formatter.format(transaction.amount)}
                    </div>
                </div>
                ${entriesHtml}
            `;
            
            return element;
        }

        getTransactionIcon(type) {
            const icons = {
                income: 'fa-arrow-down',
                expense: 'fa-arrow-up',
                transfer: 'fa-exchange-alt'
            };
            return icons[type] || 'fa-circle';
        }

        getTransactionTypeLabel(type) {
            const labels = {
                income: 'إيراد',
                expense: 'مصروف',
                transfer: 'تحويل'
            };
            return labels[type] || 'غير محدد';
        }

        groupTransactionsByDate(transactions) {
            const groups = {};
            
            transactions.forEach(transaction => {
                const dateKey = transaction.date.toLocaleDateString('en-GB');
                if (!groups[dateKey]) {
                    groups[dateKey] = [];
                }
                groups[dateKey].push(transaction);
            });
            
            return groups;
        }

        calculateGroupTotal(transactions) {
            return transactions.reduce((total, transaction) => {
                return total + (transaction.type === 'income' ? transaction.amount : -transaction.amount);
            }, 0);
        }

        getTransactions() {
            return [...this.transactions];
        }

        getTotalIncome() {
            return this.transactions
                .filter(t => t.type === 'income')
                .reduce((total, t) => total + t.amount, 0);
        }

        getTotalExpenses() {
            return this.transactions
                .filter(t => t.type === 'expense')
                .reduce((total, t) => total + t.amount, 0);
        }

        getNetAmount() {
            return this.getTotalIncome() - this.getTotalExpenses();
        }
    }

    /**
     * ========================================
     * 6. UTILITY FUNCTIONS (وظائف مساعدة)
     * ========================================
     */

    const FinancialUtils = {
        // Auto-format currency inputs
        formatCurrencyInput(input, options = {}) {
            const formatter = new CurrencyFormatter(options);
            
            input.addEventListener('input', (e) => {
                let value = e.target.value.replace(/[^\d.-]/g, '');
                if (value) {
                    const numValue = parseFloat(value);
                    if (!isNaN(numValue)) {
                        e.target.value = formatter.format(numValue, { showSymbol: false });
                    }
                }
            });
            
            input.addEventListener('blur', (e) => {
                let value = e.target.value.replace(/[^\d.-]/g, '');
                if (value) {
                    const numValue = parseFloat(value);
                    if (!isNaN(numValue)) {
                        e.target.value = formatter.format(numValue);
                    }
                }
            });
        },

        // Update all currency elements on page
        updateCurrencyElements(currency = 'EGP') {
            const formatter = new CurrencyFormatter({ currency });
            const elements = document.querySelectorAll('[data-currency-amount]');
            
            elements.forEach(element => {
                const amount = parseFloat(element.dataset.currencyAmount);
                if (!isNaN(amount)) {
                    element.textContent = formatter.format(amount);
                    element.className = `unified-currency ${formatter.getColorClass(amount)}`;
                }
            });
        },

        // Create financial summary
        createFinancialSummary(data, container) {
            const formatter = new CurrencyFormatter();
            
            const summary = document.createElement('div');
            summary.className = 'unified-balance-summary';
            
            summary.innerHTML = `
                <div class="unified-balance-summary-header">
                    <h4 class="unified-balance-summary-title">ملخص مالي</h4>
                    <div class="unified-balance-summary-period">${new Date().toLocaleDateString('en-GB')}</div>
                </div>
                <div class="unified-balance-summary-grid">
                    ${Object.keys(data).map(key => `
                        <div class="unified-balance-summary-item">
                            <div class="unified-balance-summary-label">${key}</div>
                            <div class="unified-balance-summary-amount ${formatter.getColorClass(data[key])}">
                                ${formatter.format(data[key])}
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
            
            container.appendChild(summary);
            return summary;
        },

        // Export financial data
        exportToCSV(data, filename = 'financial-data.csv') {
            const headers = Object.keys(data[0] || {});
            const csvContent = [
                headers.join(','),
                ...data.map(row => headers.map(header => row[header] || '').join(','))
            ].join('\n');
            
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
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
    };

    /**
     * ========================================
     * AUTO-INITIALIZATION (التهيئة التلقائية)
     * ========================================
     */

    function autoInitFinancialComponents() {
        // Auto-format currency inputs
        document.querySelectorAll('input[data-currency]').forEach(input => {
            const currency = input.dataset.currency || 'EGP';
            FinancialUtils.formatCurrencyInput(input, { currency });
        });

        // Auto-update currency displays
        document.querySelectorAll('[data-currency-amount]').forEach(element => {
            const amount = parseFloat(element.dataset.currencyAmount);
            const currency = element.dataset.currency || 'EGP';
            const formatter = new CurrencyFormatter({ currency });
            
            if (!isNaN(amount)) {
                element.textContent = formatter.format(amount);
                element.className = `unified-currency ${formatter.getColorClass(amount)}`;
            }
        });

        // Initialize financial dashboards
        document.querySelectorAll('[data-financial-dashboard]').forEach(container => {
            if (!container._financialDashboard) {
                const options = JSON.parse(container.dataset.financialDashboard || '{}');
                container._financialDashboard = new FinancialDashboard(container, options);
            }
        });
    }

    /**
     * ========================================
     * EXPORT TO GLOBAL NAMESPACE
     * ========================================
     */

    window.UnifiedFinancial = {
        CurrencyFormatter,
        Calculator: FinancialCalculator,
        ChartManager: FinancialChartManager,
        Dashboard: FinancialDashboard,
        TransactionManager,
        Utils: FinancialUtils,
        autoInit: autoInitFinancialComponents
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoInitFinancialComponents);
    } else {
        autoInitFinancialComponents();
    }

    // Re-initialize when new content is added
    const observer = new MutationObserver((mutations) => {
        let shouldReinit = false;
        
        mutations.forEach((mutation) => {
            if (mutation.type === 'childList') {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        if (node.querySelector && (
                            node.querySelector('[data-currency]') ||
                            node.querySelector('[data-currency-amount]') ||
                            node.querySelector('[data-financial-dashboard]')
                        )) {
                            shouldReinit = true;
                        }
                    }
                });
            }
        });
        
        if (shouldReinit) {
            setTimeout(autoInitFinancialComponents, 100);
        }
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

})(window, document);