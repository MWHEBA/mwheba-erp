/**
 * 🔒 أدوات الأمان المتقدمة للـ JavaScript
 * حماية شاملة من XSS وCode Injection
 */

class SecurityUtils {
    
    /**
     * ✅ تنفيذ آمن للكود JavaScript بدلاً من eval()
     * @param {string} code - الكود المراد تنفيذه
     * @param {object} context - السياق المسموح (اختياري)
     * @returns {any} - نتيجة التنفيذ أو null في حالة الخطأ
     */
    static safeExecute(code, context = {}) {
        try {
            // التحقق من وجود كلمات محظورة
            const forbiddenPatterns = [
                /document\./gi,
                /window\./gi,
                /location\./gi,
                /cookie/gi,
                /localStorage/gi,
                /sessionStorage/gi,
                /XMLHttpRequest/gi,
                /fetch\(/gi,
                /import\(/gi,
                /require\(/gi,
                /process\./gi,
                /global\./gi,
                /__proto__/gi,
                /constructor/gi,
                /prototype/gi
            ];
            
            for (const pattern of forbiddenPatterns) {
                if (pattern.test(code)) {
                    console.error('🚨 كود غير آمن تم رفضه:', code);
                    return null;
                }
            }
            
            // إنشاء Function آمنة مع context محدود
            const safeFunction = new Function(...Object.keys(context), `return (${code})`);
            return safeFunction(...Object.values(context));
            
        } catch (error) {
            console.error('خطأ في تنفيذ الكود الآمن:', error);
            return null;
        }
    }
    
    /**
     * ✅ حساب آمن للصيغ الرياضية
     * @param {string} formula - الصيغة الرياضية
     * @returns {number} - النتيجة أو 0 في حالة الخطأ
     */
    static safeCalculate(formula) {
        try {
            // السماح بالأرقام والعمليات الرياضية الأساسية فقط
            const safeFormula = formula.replace(/[^0-9+\-*/.() ]/g, '');
            
            if (safeFormula !== formula) {
                console.error('🚨 صيغة رياضية غير آمنة:', formula);
                return 0;
            }
            
            // التحقق من عدم وجود أقواس متداخلة بشكل مفرط
            const openParens = (formula.match(/\(/g) || []).length;
            const closeParens = (formula.match(/\)/g) || []).length;
            
            if (openParens !== closeParens || openParens > 10) {
                console.error('🚨 صيغة معقدة جداً أو غير متوازنة');
                return 0;
            }
            
            // تنفيذ آمن
            const calculateFunction = new Function('return ' + safeFormula);
            const result = calculateFunction();
            
            // التحقق من صحة النتيجة
            if (!isFinite(result) || isNaN(result)) {
                console.error('🚨 نتيجة غير صحيحة');
                return 0;
            }
            
            return result;
            
        } catch (error) {
            console.error('خطأ في الحساب الآمن:', error);
            return 0;
        }
    }
    
    /**
     * ✅ تنظيف HTML من العناصر الخطيرة
     * @param {string} html - محتوى HTML
     * @returns {string} - HTML منظف
     */
    static sanitizeHTML(html) {
        const div = document.createElement('div');
        div.textContent = html;
        return div.innerHTML;
    }
    
    /**
     * ✅ التحقق من صحة URL
     * @param {string} url - الرابط
     * @returns {boolean} - true إذا كان آمن
     */
    static isValidURL(url) {
        try {
            const urlObj = new URL(url);
            // السماح بـ HTTP/HTTPS فقط
            return ['http:', 'https:'].includes(urlObj.protocol);
        } catch {
            return false;
        }
    }
    
    /**
     * ✅ حماية من CSRF في AJAX requests
     * @returns {string} - CSRF token
     */
    static getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }
    
    /**
     * ✅ إرسال AJAX request آمن
     * @param {string} url - الرابط
     * @param {object} options - خيارات الطلب
     * @returns {Promise} - Promise للاستجابة
     */
    static secureAjax(url, options = {}) {
        // التحقق من صحة URL
        if (!this.isValidURL(url) && !url.startsWith('/')) {
            return Promise.reject(new Error('URL غير آمن'));
        }
        
        // إضافة CSRF token تلقائياً
        const defaultOptions = {
            method: 'GET',
            headers: {
                'X-CSRFToken': this.getCSRFToken(),
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin'
        };
        
        const finalOptions = { ...defaultOptions, ...options };
        
        // دمج headers
        if (options.headers) {
            finalOptions.headers = { ...defaultOptions.headers, ...options.headers };
        }
        
        return fetch(url, finalOptions);
    }
    
    /**
     * ✅ تسجيل أحداث الأمان
     * @param {string} event - نوع الحدث
     * @param {string} details - التفاصيل
     */
    static logSecurityEvent(event, details) {
        console.warn(`🔒 حدث أمني: ${event}`, details);
        
        // إرسال للخادم (اختياري)
        this.secureAjax('/api/security-log/', {
            method: 'POST',
            body: JSON.stringify({
                event: event,
                details: details,
                timestamp: new Date().toISOString(),
                user_agent: navigator.userAgent,
                url: window.location.href
            })
        }).catch(error => {
            console.error('فشل في إرسال تسجيل الأمان:', error);
        });
    }
}

// تصدير للاستخدام العام
window.SecurityUtils = SecurityUtils;

// حماية من تعديل الكلاس
Object.freeze(SecurityUtils);
Object.freeze(SecurityUtils.prototype);

