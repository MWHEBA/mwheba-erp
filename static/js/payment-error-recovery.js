/**
 * نظام استرداد أخطاء المدفوعات
 * Payment Error Recovery System
 */

(function() {
    'use strict';

    class PaymentErrorRecovery {
        constructor() {
            this.retryQueue = new Map();
            this.maxRetries = 3;
            this.retryDelay = 2000;
            this.init();
        }

        init() {
            this.bindErrorEvents();
            this.setupGlobalErrorHandler();
        }

        bindErrorEvents() {
            // مراقبة أخطاء المدفوعات
            document.addEventListener('paymentError', (event) => {
                this.handlePaymentError(event.detail);
            });

            // مراقبة أخطاء الشبكة
            window.addEventListener('offline', () => {
                this.handleNetworkOffline();
            });

            window.addEventListener('online', () => {
                this.handleNetworkOnline();
            });
        }

        setupGlobalErrorHandler() {
            // معالجة الأخطاء العامة
            window.addEventListener('unhandledrejection', (event) => {
                if (this.isPaymentRelatedError(event.reason)) {
                    this.handleUnhandledPaymentError(event.reason);
                    event.preventDefault(); // منع إظهار الخطأ في console
                }
            });
        }

        isPaymentRelatedError(error) {
            const paymentKeywords = [
                'payment', 'دفعة', 'دفع', 'مدفوعات',
                'financial', 'مالي', 'مالية',
                'fee', 'رسوم', 'رسم'
            ];

            const errorMessage = error?.message?.toLowerCase() || '';
            return paymentKeywords.some(keyword => errorMessage.includes(keyword));
        }

        handlePaymentError(errorDetail) {

            const errorType = errorDetail.type || 'unknown';
            const errorMessage = this.getLocalizedErrorMessage(errorType, errorDetail.message);

            // إظهار رسالة خطأ مناسبة
            this.showUserFriendlyError(errorMessage, errorType);

            // محاولة الاسترداد التلقائي إذا أمكن
            if (this.canAutoRecover(errorType)) {
                this.attemptAutoRecovery(errorDetail);
            }
        }

        handleUnhandledPaymentError(error) {
            console.warn('خطأ مدفوعات غير معالج:', error);

            // تحليل نوع الخطأ
            let errorType = 'unknown';
            let message = 'حدث خطأ غير متوقع في المدفوعات';

            if (error.message.includes('fetch')) {
                errorType = 'network_error';
                message = 'خطأ في الاتصال بالخادم';
            } else if (error.message.includes('JSON')) {
                errorType = 'response_parsing_error';
                message = 'خطأ في تحليل استجابة الخادم';
            } else if (error.message.includes('CSRF')) {
                errorType = 'csrf_error';
                message = 'انتهت صلاحية الجلسة';
            }

            this.showUserFriendlyError(message, errorType);
        }

        getLocalizedErrorMessage(errorType, originalMessage) {
            const messages = {
                'network_error': 'خطأ في الاتصال بالشبكة. يرجى التحقق من الاتصال بالإنترنت.',
                'server_error': 'خطأ في الخادم. يرجى المحاولة لاحقاً.',
                'validation_error': 'البيانات المدخلة غير صحيحة. يرجى مراجعة المعلومات.',
                'csrf_error': 'انتهت صلاحية الجلسة. سيتم إعادة تحميل الصفحة.',
                'response_parsing_error': 'خطأ في استجابة الخادم. يرجى المحاولة مرة أخرى.',
                'insufficient_balance': 'الرصيد غير كافي لإتمام العملية.',
                'payment_failed': 'فشل في معالجة الدفعة. يرجى المحاولة مرة أخرى.',
                'timeout_error': 'انتهت مهلة الاتصال. يرجى المحاولة مرة أخرى.',
                'unknown': 'حدث خطأ غير متوقع. يرجى المحاولة مرة أخرى.'
            };

            return messages[errorType] || originalMessage || messages['unknown'];
        }

        canAutoRecover(errorType) {
            const recoverableErrors = [
                'network_error',
                'timeout_error',
                'server_error'
            ];

            return recoverableErrors.includes(errorType);
        }

        async attemptAutoRecovery(errorDetail) {
            const errorId = this.generateErrorId(errorDetail);
            
            if (this.retryQueue.has(errorId)) {
                const retryInfo = this.retryQueue.get(errorId);
                if (retryInfo.attempts >= this.maxRetries) {
                    this.showFinalErrorMessage(errorDetail);
                    return;
                }
                retryInfo.attempts++;
            } else {
                this.retryQueue.set(errorId, { attempts: 1, errorDetail });
            }


            // انتظار قبل إعادة المحاولة
            await this.delay(this.retryDelay);

            // محاولة إعادة تنفيذ العملية
            this.retryOperation(errorDetail);
        }

        retryOperation(errorDetail) {
            // إرسال حدث إعادة المحاولة
            const retryEvent = new CustomEvent('paymentRetry', {
                detail: errorDetail
            });
            document.dispatchEvent(retryEvent);

            // إظهار رسالة إعادة المحاولة
            this.showRetryMessage();
        }

        generateErrorId(errorDetail) {
            return `${errorDetail.type}_${Date.now()}`;
        }

        delay(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }

        handleNetworkOffline() {
            this.showNetworkOfflineMessage();
        }

        handleNetworkOnline() {
            this.showNetworkOnlineMessage();
            this.retryPendingOperations();
        }

        retryPendingOperations() {
            // إعادة محاولة العمليات المعلقة
            this.retryQueue.forEach((retryInfo, errorId) => {
                if (retryInfo.attempts < this.maxRetries) {
                    setTimeout(() => {
                        this.retryOperation(retryInfo.errorDetail);
                    }, 1000);
                }
            });
        }

        showUserFriendlyError(message, errorType) {
            const isRecoverable = this.canAutoRecover(errorType);
            const actionButton = isRecoverable ? 
                '<button type="button" class="btn btn-sm btn-outline-light mt-2" onclick="location.reload()">إعادة المحاولة</button>' : '';

            this.showToast(message + actionButton, 'error', isRecoverable ? 0 : 5000);
        }

        showFinalErrorMessage(errorDetail) {
            const message = `
                فشل في معالجة الدفعة بعد عدة محاولات.
                <br><small>يرجى إعادة تحميل الصفحة أو الاتصال بالدعم الفني.</small>
                <button type="button" class="btn btn-sm btn-outline-light mt-2" onclick="location.reload()">
                    إعادة تحميل الصفحة
                </button>
            `;
            this.showToast(message, 'error', 0);
        }

        showRetryMessage() {
            this.showToast('جاري إعادة المحاولة...', 'info', 2000);
        }

        showNetworkOfflineMessage() {
            this.showToast('انقطع الاتصال بالإنترنت. العمليات المالية معلقة.', 'warning', 0);
        }

        showNetworkOnlineMessage() {
            this.showToast('تم استعادة الاتصال. استئناف العمليات المالية.', 'success', 3000);
        }

        showToast(message, type = 'info', duration = 5000) {
            // استخدام نظام Toast الموجود
            if (window.paymentProcessor && window.paymentProcessor.showToast) {
                window.paymentProcessor.showToast(message, type, duration);
            } else if (window.paymentErrorHandler && window.paymentErrorHandler.showErrorToast) {
                window.paymentErrorHandler.showErrorToast(message, type);
            } else {
                // fallback للعرض البسيط
            }
        }

        // دالة لتنظيف قائمة إعادة المحاولة
        clearRetryQueue() {
            this.retryQueue.clear();
        }

        // دالة للحصول على إحصائيات الأخطاء
        getErrorStats() {
            const stats = {
                totalErrors: this.retryQueue.size,
                errorsByType: {},
                retriesInProgress: 0
            };

            this.retryQueue.forEach((retryInfo) => {
                const errorType = retryInfo.errorDetail.type || 'unknown';
                stats.errorsByType[errorType] = (stats.errorsByType[errorType] || 0) + 1;
                
                if (retryInfo.attempts < this.maxRetries) {
                    stats.retriesInProgress++;
                }
            });

            return stats;
        }
    }

    // تهيئة نظام استرداد الأخطاء
    document.addEventListener('DOMContentLoaded', function() {
        window.paymentErrorRecovery = new PaymentErrorRecovery();
    });

    // تصدير للاستخدام في ملفات أخرى
    window.PaymentErrorRecovery = PaymentErrorRecovery;

})();