/**
 * مولد QR Code محلي - بديل للمكتبات الخارجية
 * يستخدم Backend APIs لتوليد QR Codes بدلاً من JavaScript
 */

class QRGenerator {
    constructor() {
        this.baseUrl = window.location.origin;
        this.cache = new Map();
        this.retryCount = 3;
        this.retryDelay = 1000;
    }

    /**
     * إنشاء QR Code باستخدام Backend API
     * @param {string} token - رمز QR Code
     * @param {HTMLElement} container - العنصر المراد عرض QR Code فيه
     * @param {Object} options - خيارات التخصيص
     */
    async generateQR(token, container, options = {}) {
        const defaultOptions = {
            size: 200,
            format: 'json',
            showUrl: false,
            showToken: false,
            errorMessage: 'خطأ في تحميل QR Code',
            loadingMessage: 'جاري تحميل QR Code...',
            retryButton: true
        };

        const config = { ...defaultOptions, ...options };
        
        if (!container) {
            console.error('QRGenerator: Container element is required');
            return false;
        }

        // عرض رسالة التحميل
        this.showLoading(container, config.loadingMessage);

        try {
            const qrData = await this.fetchQRData(token, config);
            if (qrData.success) {
                this.renderQR(container, qrData, config);
                return true;
            } else {
                throw new Error(qrData.error || 'فشل في إنشاء QR Code');
            }
        } catch (error) {
            console.error('QRGenerator Error:', error);
            this.showError(container, config.errorMessage, config.retryButton, () => {
                this.generateQR(token, container, options);
            });
            return false;
        }
    }

    /**
     * جلب بيانات QR Code من Backend
     */
    async fetchQRData(token, config) {
        const cacheKey = `${token}_${config.size}_${config.format}`;
        
        // التحقق من الكاش
        if (this.cache.has(cacheKey)) {
            return this.cache.get(cacheKey);
        }

        const url = `${this.baseUrl}/qr-applications/qr-image/${token}/json/?size=${config.size}`;
        
        for (let attempt = 1; attempt <= this.retryCount; attempt++) {
            try {
                const response = await fetch(url, {
                    method: 'GET',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json'
                    },
                    credentials: 'same-origin'
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const data = await response.json();
                
                // حفظ في الكاش
                this.cache.set(cacheKey, data);
                return data;

            } catch (error) {
                console.warn(`QRGenerator: Attempt ${attempt} failed:`, error.message);
                
                if (attempt < this.retryCount) {
                    await this.delay(this.retryDelay * attempt);
                } else {
                    throw error;
                }
            }
        }
    }

    /**
     * عرض QR Code في الحاوية
     */
    renderQR(container, qrData, config) {
        const qrWrapper = document.createElement('div');
        qrWrapper.className = 'qr-wrapper text-center';
        
        // إنشاء صورة QR
        const qrImage = document.createElement('img');
        qrImage.src = qrData.data_url;
        qrImage.alt = 'QR Code';
        qrImage.className = 'qr-image img-fluid';
        qrImage.style.maxWidth = `${config.size}px`;
        qrImage.style.height = 'auto';
        
        qrWrapper.appendChild(qrImage);

        // عرض URL إذا كان مطلوباً
        if (config.showUrl && qrData.url) {
            const urlDiv = document.createElement('div');
            urlDiv.className = 'qr-url mt-2 small text-muted';
            urlDiv.innerHTML = `<code>${qrData.url}</code>`;
            qrWrapper.appendChild(urlDiv);
        }

        // عرض Token إذا كان مطلوباً
        if (config.showToken && qrData.token) {
            const tokenDiv = document.createElement('div');
            tokenDiv.className = 'qr-token mt-1 small text-muted';
            tokenDiv.innerHTML = `الرمز: <code>${qrData.token.substring(0, 8)}...</code>`;
            qrWrapper.appendChild(tokenDiv);
        }

        // إضافة أزرار التحميل
        if (config.downloadButtons) {
            const buttonsDiv = this.createDownloadButtons(qrData.token);
            qrWrapper.appendChild(buttonsDiv);
        }

        // استبدال محتوى الحاوية
        container.innerHTML = '';
        container.appendChild(qrWrapper);
    }

    /**
     * إنشاء أزرار التحميل
     */
    createDownloadButtons(token) {
        const buttonsDiv = document.createElement('div');
        buttonsDiv.className = 'qr-download-buttons mt-3';

        const pngButton = document.createElement('a');
        pngButton.href = `${this.baseUrl}/qr-applications/qr-image/${token}/png/?size=400`;
        pngButton.className = 'btn btn-sm btn-outline-primary me-2';
        pngButton.innerHTML = '<i class="fas fa-download me-1"></i>PNG';
        pngButton.download = `qr_${token.substring(0, 8)}.png`;

        const svgButton = document.createElement('a');
        svgButton.href = `${this.baseUrl}/qr-applications/qr-image/${token}/svg/`;
        svgButton.className = 'btn btn-sm btn-outline-secondary';
        svgButton.innerHTML = '<i class="fas fa-download me-1"></i>SVG';
        svgButton.download = `qr_${token.substring(0, 8)}.svg`;

        buttonsDiv.appendChild(pngButton);
        buttonsDiv.appendChild(svgButton);

        return buttonsDiv;
    }

    /**
     * عرض رسالة التحميل
     */
    showLoading(container, message) {
        container.innerHTML = `
            <div class="qr-loading text-center p-3">
                <div class="spinner-border spinner-border-sm text-primary mb-2" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <div class="text-muted small">${message}</div>
            </div>
        `;
    }

    /**
     * عرض رسالة خطأ
     */
    showError(container, message, showRetry = true, retryCallback = null) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'qr-error text-center p-3';
        
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger mb-2';
        alertDiv.innerHTML = `<i class="fas fa-exclamation-triangle me-2"></i>${message}`;
        
        errorDiv.appendChild(alertDiv);

        if (showRetry && retryCallback) {
            const retryButton = document.createElement('button');
            retryButton.className = 'btn btn-sm btn-outline-primary';
            retryButton.innerHTML = '<i class="fas fa-redo me-1"></i>إعادة المحاولة';
            retryButton.onclick = retryCallback;
            errorDiv.appendChild(retryButton);
        }

        container.innerHTML = '';
        container.appendChild(errorDiv);
    }

    /**
     * تأخير لإعادة المحاولة
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * مسح الكاش
     */
    clearCache() {
        this.cache.clear();
    }

    /**
     * تحميل QR Code مباشرة
     */
    downloadQR(token, format = 'png', size = 400) {
        const url = `${this.baseUrl}/qr-applications/qr-image/${token}/${format}/?size=${size}`;
        const link = document.createElement('a');
        link.href = url;
        link.download = `qr_${token.substring(0, 8)}.${format}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
}

// إنشاء instance عام
window.QRGenerator = new QRGenerator();

// دالة مساعدة للتوافق مع الكود القديم
window.generateQRCode = function(token, containerId, options = {}) {
    const container = typeof containerId === 'string' 
        ? document.getElementById(containerId) 
        : containerId;
    
    if (!container) {
        console.error('generateQRCode: Container not found:', containerId);
        return;
    }

    // استخراج token من URL إذا لم يتم تمريره
    if (!token) {
        const urlParts = window.location.pathname.split('/');
        const tokenIndex = urlParts.indexOf('qr-codes') + 1;
        if (tokenIndex > 0 && urlParts[tokenIndex]) {
            token = urlParts[tokenIndex];
        }
    }

    if (!token) {
        console.error('generateQRCode: Token is required');
        return;
    }

    return window.QRGenerator.generateQR(token, container, options);
};

// Auto-initialize عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    // البحث عن عناصر QR Code وتهيئتها تلقائياً
    const qrContainers = document.querySelectorAll('[data-qr-token]');
    qrContainers.forEach(container => {
        const token = container.getAttribute('data-qr-token');
        const size = parseInt(container.getAttribute('data-qr-size')) || 200;
        const showUrl = container.getAttribute('data-qr-show-url') === 'true';
        const showToken = container.getAttribute('data-qr-show-token') === 'true';
        const downloadButtons = container.getAttribute('data-qr-download') === 'true';

        window.QRGenerator.generateQR(token, container, {
            size,
            showUrl,
            showToken,
            downloadButtons
        });
    });
});
