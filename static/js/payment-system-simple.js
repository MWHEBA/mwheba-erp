/**
 * نظام المدفوعات المبسط - للاختبار المباشر
 * Simple Payment System - For Direct Testing
 */

(function() {
    'use strict';

    // معالج الأخطاء المبسط
    class SimplePaymentErrorHandler {
        constructor() {
            this.init();
        }

        init() {
        }

        showErrorToast(message, type = 'error') {
            const toastHtml = `
                <div class="toast align-items-center text-white bg-${type === 'error' ? 'danger' : 'warning'} border-0 position-fixed" 
                     style="top: 20px; left: 20px; z-index: 9999; min-width: 350px;" role="alert">
                    <div class="d-flex">
                        <div class="toast-body">
                            <i class="fas fa-${type === 'error' ? 'exclamation-circle' : 'exclamation-triangle'} me-2"></i>
                            ${message}
                        </div>
                        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                    </div>
                </div>
            `;
            
            document.body.insertAdjacentHTML('beforeend', toastHtml);
            
            const toastElement = document.body.lastElementChild;
            // Using toastr library instead
            
            toastElement.addEventListener('hidden.bs.toast', () => {
                toastElement.remove();
            });
        }
    }

    // مراقب الاتصال المبسط
    class SimpleConnectionMonitor {
        constructor() {
            this.isOnline = navigator.onLine;
            this.init();
        }

        init() {
            this.bindEvents();
            this.createStatusIndicator();
        }

        bindEvents() {
            window.addEventListener('online', () => this.handleOnline());
            window.addEventListener('offline', () => this.handleOffline());
        }

        createStatusIndicator() {
            const indicator = document.createElement('div');
            indicator.id = 'connection-indicator';
            indicator.className = 'connection-indicator position-fixed';
            indicator.style.cssText = `
                top: 10px;
                left: 10px;
                z-index: 10000;
                padding: 8px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 500;
                transition: all 0.3s ease;
                display: none;
            `;
            
            document.body.appendChild(indicator);
            this.updateIndicator();
        }

        updateIndicator() {
            const indicator = document.getElementById('connection-indicator');
            if (!indicator) return;

            if (this.isOnline) {
                indicator.innerHTML = '<i class="fas fa-wifi me-1"></i>متصل';
                indicator.style.cssText += 'background-color: #198754; color: white; display: none;';
            } else {
                indicator.innerHTML = '<i class="fas fa-wifi-slash me-1"></i>غير متصل';
                indicator.style.cssText += 'background-color: #dc3545; color: white; display: block;';
            }
        }

        handleOnline() {
            this.isOnline = true;
            this.updateIndicator();
            this.showNotification('تم استعادة الاتصال بالإنترنت', 'success', 3000);
        }

        handleOffline() {
            this.isOnline = false;
            this.updateIndicator();
            this.showNotification('انقطع الاتصال بالإنترنت', 'warning', 0);
        }

        showNotification(message, type = 'info', duration = 5000) {
            if (window.paymentErrorHandler && window.paymentErrorHandler.showErrorToast) {
                window.paymentErrorHandler.showErrorToast(message, type);
            } else {
            }
        }

        checkConnection() {
            const wasOnline = this.isOnline;
            this.isOnline = navigator.onLine;
            
            if (wasOnline !== this.isOnline) {
                if (this.isOnline) {
                    this.handleOnline();
                } else {
                    this.handleOffline();
                }
            }
            
            return this.isOnline;
        }

        getConnectionStatus() {
            return {
                isOnline: this.isOnline,
                navigatorOnline: navigator.onLine
            };
        }
    }

    // معالج المدفوعات المبسط
    class SimplePaymentProcessor {
        constructor() {
            this.init();
        }

        init() {
        }

        showToast(message, type = 'info', duration = 5000) {
            const toastTypes = {
                'success': { icon: 'check-circle', bgClass: 'bg-success' },
                'error': { icon: 'exclamation-circle', bgClass: 'bg-danger' },
                'warning': { icon: 'exclamation-triangle', bgClass: 'bg-warning' },
                'info': { icon: 'info-circle', bgClass: 'bg-info' }
            };
            
            const toastConfig = toastTypes[type] || toastTypes['info'];
            
            const toastHtml = `
                <div class="toast align-items-center text-white ${toastConfig.bgClass} border-0 position-fixed" 
                     style="top: 20px; left: 20px; z-index: 9999; min-width: 350px;" role="alert">
                    <div class="d-flex">
                        <div class="toast-body">
                            <i class="fas fa-${toastConfig.icon} me-2"></i>
                            ${message}
                        </div>
                        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                    </div>
                </div>
            `;
            
            document.body.insertAdjacentHTML('beforeend', toastHtml);
            
            const toastElement = document.body.lastElementChild;
            // Using toastr library instead
            
            toastElement.addEventListener('hidden.bs.toast', () => {
                toastElement.remove();
            });
        }
    }

    // تهيئة النظام المبسط
    function initializeSimpleSystem() {
        try {
            // تهيئة المكونات
            window.paymentErrorHandler = new SimplePaymentErrorHandler();
            window.connectionMonitor = new SimpleConnectionMonitor();
            window.paymentProcessor = new SimplePaymentProcessor();

            // إضافة معالج بسيط لأخطاء الدفعات
            document.addEventListener('paymentError', function(event) {
                if (window.paymentErrorHandler) {
                    const message = event.detail.message || 'حدث خطأ في معالجة الدفعة';
                    window.paymentErrorHandler.showErrorToast(message, 'error');
                }
            });


            // إرسال حدث اكتمال التهيئة
            const event = new CustomEvent('paymentSystemLoaded', {
                detail: {
                    type: 'simple',
                    timestamp: new Date().toISOString()
                }
            });
            document.dispatchEvent(event);

        } catch (error) {
            console.error('❌ خطأ في تهيئة النظام المبسط:', error);
        }
    }

    // بدء التهيئة
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeSimpleSystem);
    } else {
        initializeSimpleSystem();
    }

    // تصدير للاستخدام العام
    window.SimplePaymentSystem = {
        PaymentErrorHandler: SimplePaymentErrorHandler,
        ConnectionMonitor: SimpleConnectionMonitor,
        PaymentProcessor: SimplePaymentProcessor
    };

})();