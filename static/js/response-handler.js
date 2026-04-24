/**
 * معالج الاستجابات الموحد
 * Unified Response Handler
 */

class ResponseHandler {
    /**
     * معالجة استجابة fetch بشكل آمن
     * @param {Response} response - استجابة fetch
     * @param {string} context - سياق العملية للتسجيل
     * @returns {Promise<Object>} - البيانات المحللة أو خطأ
     */
    static async handleResponse(response, context = 'Unknown') {
        
        // التحقق من حالة الاستجابة
        if (!response.ok) {
            console.error(`[${context}] HTTP error:`, response.status, response.statusText);
            
            // محاولة قراءة رسالة الخطأ من الخادم
            try {
                const errorText = await response.text();
                console.error(`[${context}] Error response:`, errorText);
                
                // إذا كانت الاستجابة JSON، حاول تحليلها
                if (response.headers.get('content-type')?.includes('application/json')) {
                    try {
                        const errorData = JSON.parse(errorText);
                        throw new Error(errorData.message || errorData.error || `HTTP ${response.status}`);
                    } catch (parseError) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                } else {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
            } catch (error) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
        }
        
        // التحقق من نوع المحتوى
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            console.error(`[${context}] Response is not JSON:`, contentType);
            
            // محاولة قراءة المحتوى للتشخيص
            const responseText = await response.text();
            console.error(`[${context}] Response content:`, responseText.substring(0, 200));
            
            throw new Error('الاستجابة ليست بتنسيق JSON صحيح');
        }
        
        // تحليل JSON بشكل آمن
        try {
            const data = await response.json();
            return data;
        } catch (parseError) {
            console.error(`[${context}] JSON parse error:`, parseError);
            throw new Error('فشل في تحليل استجابة الخادم');
        }
    }
    
    /**
     * إرسال طلب POST بشكل آمن
     * @param {string} url - رابط الطلب
     * @param {Object} data - البيانات المرسلة
     * @param {string} context - سياق العملية
     * @returns {Promise<Object>} - البيانات المحللة
     */
    static async postRequest(url, data, context = 'POST Request') {
        try {
            
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(data)
            });
            
            return await this.handleResponse(response, context);
        } catch (error) {
            console.error(`[${context}] Request failed:`, error);
            throw error;
        }
    }
    
    /**
     * إرسال طلب GET بشكل آمن
     * @param {string} url - رابط الطلب
     * @param {string} context - سياق العملية
     * @returns {Promise<Object>} - البيانات المحللة
     */
    static async getRequest(url, context = 'GET Request') {
        try {
            
            const response = await fetch(url, {
                method: 'GET',
                headers: {
                    'X-CSRFToken': this.getCSRFToken()
                }
            });
            
            return await this.handleResponse(response, context);
        } catch (error) {
            console.error(`[${context}] Request failed:`, error);
            throw error;
        }
    }
    
    /**
     * الحصول على CSRF token
     * @returns {string} - CSRF token
     */
    static getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
                     document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
                     '';
        
        if (!token) {
            console.warn('CSRF token not found');
        }
        
        return token;
    }
    
    /**
     * معالجة الأخطاء الشائعة
     * @param {Error} error - الخطأ
     * @param {string} context - سياق العملية
     * @returns {string} - رسالة خطأ مفهومة للمستخدم
     */
    static getErrorMessage(error, context = 'العملية') {
        console.error(`Error in ${context}:`, error);
        
        if (error.message.includes('JSON')) {
            return 'حدث خطأ في تحليل استجابة الخادم';
        } else if (error.message.includes('HTTP 500')) {
            return 'حدث خطأ في الخادم. يرجى المحاولة مرة أخرى لاحقاً';
        } else if (error.message.includes('HTTP 404')) {
            return 'الصفحة المطلوبة غير موجودة';
        } else if (error.message.includes('HTTP 403')) {
            return 'ليس لديك صلاحية للوصول لهذه العملية';
        } else if (error.message.includes('Network')) {
            return 'مشكلة في الاتصال بالخادم';
        } else {
            return error.message || 'حدث خطأ غير متوقع';
        }
    }
}

// تصدير الكلاس للاستخدام العام
window.ResponseHandler = ResponseHandler;