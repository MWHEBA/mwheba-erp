/**
 * إعدادات معالج الأخطاء - محسن للمدفوعات
 * Error Handler Configuration - Enhanced for Payments
 */

class PaymentErrorHandler {
    constructor() {
        this.init();
    }

    init() {
        // معالجة أخطاء الشبكة العامة
        this.setupNetworkErrorHandling();
        
        // معالجة أخطاء المدفوعات المحددة
        this.setupPaymentErrorHandling();
        
        // معالجة أخطاء CSRF
        this.setupCSRFErrorHandling();
    }

    setupNetworkErrorHandling() {
        // معالجة أخطاء fetch العامة
        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            try {
                const response = await originalFetch(...args);
                
                // التحقق من حالة الاستجابة
                if (!response.ok) {
                    this.handleHTTPError(response, args[0]);
                }
                
                return response;
            } catch (error) {
                this.handleNetworkError(error, args[0]);
                throw error;
            }
        };
    }

    setupPaymentErrorHandling() {
        // معالجة أخطاء المدفوعات المحددة
        document.addEventListener('paymentError', (event) => {
            this.handlePaymentError(event.detail);
        });
    }

    setupCSRFErrorHandling() {
        // معالجة أخطاء CSRF
        document.addEventListener('ajaxError', (event) => {
            if (event.detail && event.detail.status === 403) {
                this.handleCSRFError();
            }
        });
    }

    handleNetworkError(error, url) {
        console.error('خطأ في الشبكة:', error);
        
        // إظهار رسالة خطأ مناسبة للمستخدم
        if (url && url.includes('payment')) {
            this.showPaymentNetworkError();
        } else {
            this.showGenericNetworkError();
        }
    }

    handleHTTPError(response, url) {
        console.error(`خطأ HTTP ${response.status}:`, url);
        
        switch (response.status) {
            case 400:
                this.showBadRequestError();
                break;
            case 403:
                this.showPermissionError();
                break;
            case 404:
                this.showNotFoundError();
                break;
            case 500:
                this.showServerError();
                break;
            default:
                this.showGenericError(response.status);
        }
    }

    handlePaymentError(errorDetail) {
        console.error('خطأ في المدفوعات:', errorDetail);
        
        const errorMessage = this.getPaymentErrorMessage(errorDetail);
        this.showErrorToast(errorMessage, 'error');
    }

    handleCSRFError() {
        console.error('خطأ CSRF - إعادة تحميل الصفحة');
        
        this.showErrorToast('انتهت صلاحية الجلسة. سيتم إعادة تحميل الصفحة...', 'warning');
        
        setTimeout(() => {
            window.location.reload();
        }, 2000);
    }

    showPaymentNetworkError() {
        this.showErrorToast('حدث خطأ في الاتصال أثناء معالجة الدفعة. يرجى المحاولة مرة أخرى.', 'error');
    }

    showGenericNetworkError() {
        this.showErrorToast('حدث خطأ في الاتصال. يرجى التحقق من الاتصال بالإنترنت.', 'error');
    }

    showBadRequestError() {
        this.showErrorToast('البيانات المرسلة غير صحيحة. يرجى مراجعة المعلومات المدخلة.', 'error');
    }

    showPermissionError() {
        this.showErrorToast('ليس لديك صلاحية لتنفيذ هذه العملية.', 'error');
    }

    showNotFoundError() {
        this.showErrorToast('الصفحة أو الخدمة المطلوبة غير موجودة.', 'error');
    }

    showServerError() {
        this.showErrorToast('حدث خطأ في الخادم. يرجى المحاولة لاحقاً أو الاتصال بالدعم الفني.', 'error');
    }

    showGenericError(status) {
        this.showErrorToast(`حدث خطأ غير متوقع (${status}). يرجى المحاولة مرة أخرى.`, 'error');
    }

    getPaymentErrorMessage(errorDetail) {
        const errorMessages = {
            'insufficient_balance': 'الرصيد غير كافي لإتمام العملية',
            'invalid_amount': 'المبلغ المدخل غير صحيح',
            'payment_failed': 'فشل في معالجة الدفعة',
            'connection_timeout': 'انتهت مهلة الاتصال',
            'server_error': 'خطأ في الخادم',
            'validation_error': 'خطأ في التحقق من البيانات',
            'response_parsing_error': 'خطأ في استجابة الخادم - يرجى المحاولة لاحقاً',
            'csrf_error': 'انتهت صلاحية الجلسة - سيتم إعادة التحميل',
            'network_error': 'خطأ في الاتصال بالشبكة'
        };
        
        return errorMessages[errorDetail.type] || errorDetail.message || 'حدث خطأ في معالجة الدفعة';
    }

    showErrorToast(message, type = 'error') {
        // إنشاء toast للأخطاء
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
        
        // إزالة العنصر بعد الإخفاء
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }

    // دالة للتحقق من حالة الاتصال
    checkConnection() {
        return navigator.onLine;
    }

    // دالة لإعادة المحاولة التلقائية
    async retryRequest(requestFn, maxRetries = 3, delay = 1000) {
        for (let i = 0; i < maxRetries; i++) {
            try {
                return await requestFn();
            } catch (error) {
                if (i === maxRetries - 1) throw error;
                
                await new Promise(resolve => setTimeout(resolve, delay));
                delay *= 2; // زيادة التأخير مع كل محاولة
            }
        }
    }
}

// تهيئة معالج الأخطاء
document.addEventListener('DOMContentLoaded', function() {
    window.paymentErrorHandler = new PaymentErrorHandler();
});

// تصدير للاستخدام في ملفات أخرى
window.PaymentErrorHandler = PaymentErrorHandler;