/**
 * Integrated Payroll System - JavaScript
 * نظام معالجة الرواتب المتكامل - الجافا سكريبت
 * 
 * يوفر التفاعلية والوظائف الديناميكية للنظام
 */

(function() {
    'use strict';

    /**
     * Payroll Dashboard Manager
     * مدير لوحة التحكم
     */
    const PayrollDashboard = {
        /**
         * تهيئة لوحة التحكم
         */
        init: function() {
            this.setupMonthSelector();
            this.setupFormSubmissions();
            this.setupAutoRefresh();
            this.setupConfirmations();
        },

        /**
         * إعداد اختيار الشهر
         */
        setupMonthSelector: function() {
            const monthSelect = document.getElementById('month-select');
            if (monthSelect) {
                monthSelect.addEventListener('change', function() {
                    const selectedMonth = this.value;
                    window.location.href = '?month=' + selectedMonth;
                });
            }
        },

        /**
         * إعداد إرسال النماذج
         */
        setupFormSubmissions: function() {
            // نموذج حساب ملخصات الحضور
            const calculateSummariesForm = document.getElementById('calculate-summaries-form');
            if (calculateSummariesForm) {
                calculateSummariesForm.addEventListener('submit', function(e) {
                    const btn = document.getElementById('calculate-summaries-btn');
                    if (btn) {
                        btn.disabled = true;
                        btn.innerHTML = '<span class="payroll-spinner"></span><span>جاري الحساب...</span>';
                    }
                });
            }

            // نموذج معالجة الرواتب
            const processPayrollsForm = document.getElementById('process-payrolls-form');
            if (processPayrollsForm) {
                processPayrollsForm.addEventListener('submit', function(e) {
                    if (!confirm('هل أنت متأكد من معالجة رواتب جميع الموظفين المتبقيين؟')) {
                        e.preventDefault();
                        return;
                    }
                    const btn = document.getElementById('process-payrolls-btn');
                    if (btn) {
                        btn.disabled = true;
                        btn.innerHTML = '<span class="payroll-spinner"></span><span>جاري المعالجة...</span>';
                    }
                });
            }
        },

        /**
         * إعداد التحديث التلقائي
         */
        setupAutoRefresh: function() {
            // تحديث تلقائي كل 30 ثانية إذا كانت هناك معالجة جارية
            const remainingCount = document.querySelector('[data-remaining-count]');
            const payrollsCount = document.querySelector('[data-payrolls-count]');
            
            if (remainingCount && payrollsCount) {
                const remaining = parseInt(remainingCount.dataset.remainingCount);
                const processed = parseInt(payrollsCount.dataset.payrollsCount);
                
                if (remaining > 0 && processed > 0) {
                    setTimeout(function() {
                        location.reload();
                    }, 30000);
                }
            }
        },

        /**
         * إعداد رسائل التأكيد
         */
        setupConfirmations: function() {
            // تأكيد حذف أو إعادة حساب
            const confirmButtons = document.querySelectorAll('[data-confirm]');
            confirmButtons.forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    const message = this.dataset.confirm;
                    if (!confirm(message)) {
                        e.preventDefault();
                    }
                });
            });
        }
    };

    /**
     * Payroll Detail Manager
     * مدير تفاصيل القسيمة
     */
    const PayrollDetail = {
        /**
         * تهيئة صفحة التفاصيل
         */
        init: function() {
            this.setupPrintButton();
            this.setupApprovalForm();
            this.highlightSources();
        },

        /**
         * إعداد زر الطباعة
         */
        setupPrintButton: function() {
            const printButtons = document.querySelectorAll('[data-print]');
            printButtons.forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    window.print();
                });
            });
        },

        /**
         * إعداد نموذج الاعتماد
         */
        setupApprovalForm: function() {
            const approvalForms = document.querySelectorAll('[data-approval-form]');
            approvalForms.forEach(function(form) {
                form.addEventListener('submit', function(e) {
                    if (!confirm('هل أنت متأكد من اعتماد هذه القسيمة؟')) {
                        e.preventDefault();
                    }
                });
            });
        },

        /**
         * تمييز المصادر
         */
        highlightSources: function() {
            const sourceFilters = document.querySelectorAll('[data-source-filter]');
            sourceFilters.forEach(function(filter) {
                filter.addEventListener('click', function() {
                    const source = this.dataset.sourceFilter;
                    const items = document.querySelectorAll('[data-source]');
                    
                    items.forEach(function(item) {
                        if (source === 'all' || item.dataset.source === source) {
                            item.style.display = '';
                        } else {
                            item.style.display = 'none';
                        }
                    });
                });
            });
        }
    };

    /**
     * Attendance Summary Manager
     * مدير ملخص الحضور
     */
    const AttendanceSummary = {
        /**
         * تهيئة صفحة الملخص
         */
        init: function() {
            this.setupApprovalButton();
            this.setupRecalculateButton();
            this.calculatePercentages();
        },

        /**
         * إعداد زر الاعتماد
         */
        setupApprovalButton: function() {
            const approveBtn = document.querySelector('[data-approve-summary]');
            if (approveBtn) {
                approveBtn.addEventListener('click', function(e) {
                    if (!confirm('هل أنت متأكد من اعتماد ملخص الحضور؟')) {
                        e.preventDefault();
                    }
                });
            }
        },

        /**
         * إعداد زر إعادة الحساب
         */
        setupRecalculateButton: function() {
            const recalcBtn = document.querySelector('[data-recalculate-summary]');
            if (recalcBtn) {
                recalcBtn.addEventListener('click', function(e) {
                    if (!confirm('هل أنت متأكد من إعادة حساب الملخص؟ سيتم إلغاء الاعتماد الحالي.')) {
                        e.preventDefault();
                    }
                });
            }
        },

        /**
         * حساب النسب المئوية
         */
        calculatePercentages: function() {
            const percentageElements = document.querySelectorAll('[data-calculate-percentage]');
            percentageElements.forEach(function(el) {
                const value = parseFloat(el.dataset.value);
                const total = parseFloat(el.dataset.total);
                
                if (total > 0) {
                    const percentage = ((value / total) * 100).toFixed(1);
                    el.textContent = percentage + '%';
                } else {
                    el.textContent = '0%';
                }
            });
        }
    };

    /**
     * Utilities
     * الأدوات المساعدة
     */
    const Utils = {
        /**
         * تنسيق الأرقام
         */
        formatNumber: function(number, decimals = 2) {
            return parseFloat(number).toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        },

        /**
         * عرض رسالة نجاح
         */
        showSuccess: function(message) {
            this.showAlert(message, 'success');
        },

        /**
         * عرض رسالة خطأ
         */
        showError: function(message) {
            this.showAlert(message, 'danger');
        },

        /**
         * عرض رسالة تحذير
         */
        showWarning: function(message) {
            this.showAlert(message, 'warning');
        },

        /**
         * عرض رسالة
         */
        showAlert: function(message, type) {
            const alertContainer = document.querySelector('.payroll-alerts');
            if (!alertContainer) return;

            const alert = document.createElement('div');
            alert.className = 'payroll-alert payroll-alert-' + type;
            alert.innerHTML = '<span>' + message + '</span>';
            
            alertContainer.appendChild(alert);

            // إزالة الرسالة بعد 5 ثوان
            setTimeout(function() {
                alert.style.opacity = '0';
                setTimeout(function() {
                    alert.remove();
                }, 300);
            }, 5000);
        },

        /**
         * تحميل البيانات عبر AJAX
         */
        loadData: function(url, callback) {
            fetch(url)
                .then(response => response.json())
                .then(data => callback(data))
                .catch(error => {
                    console.error('Error loading data:', error);
                    this.showError('حدث خطأ أثناء تحميل البيانات');
                });
        },

        /**
         * إرسال نموذج عبر AJAX
         */
        submitForm: function(form, callback) {
            const formData = new FormData(form);
            const url = form.action;

            fetch(url, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => callback(data))
            .catch(error => {
                console.error('Error submitting form:', error);
                this.showError('حدث خطأ أثناء إرسال النموذج');
            });
        }
    };

    /**
     * تهيئة النظام عند تحميل الصفحة
     */
    document.addEventListener('DOMContentLoaded', function() {
        // تهيئة المكونات بناءً على الصفحة الحالية
        const body = document.body;

        if (body.classList.contains('payroll-dashboard')) {
            PayrollDashboard.init();
        }

        if (body.classList.contains('payroll-detail')) {
            PayrollDetail.init();
        }

        if (body.classList.contains('attendance-summary')) {
            AttendanceSummary.init();
        }

        // تهيئة الأدوات المساعدة دائماً
        window.PayrollUtils = Utils;
    });

    /**
     * تصدير الوحدات للاستخدام الخارجي
     */
    window.PayrollDashboard = PayrollDashboard;
    window.PayrollDetail = PayrollDetail;
    window.AttendanceSummary = AttendanceSummary;

})();

