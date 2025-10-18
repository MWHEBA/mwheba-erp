/**
 * نظام التسعير المحسن - خدمات API
 * Printing Pricing System - API Services
 */

window.PrintingPricing = window.PrintingPricing || {};

PrintingPricing.API = {
    
    /**
     * إعدادات الطلبات
     * Request Configuration
     */
    defaultOptions: {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin'
    },

    /**
     * الحصول على CSRF Token
     * Get CSRF Token
     */
    getCSRFToken: function() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    },

    /**
     * إنشاء URL كامل
     * Build Full URL
     */
    buildURL: function(endpoint) {
        const baseURL = PrintingPricing.Config.API.BASE_URL;
        return baseURL + endpoint;
    },

    /**
     * طلب HTTP عام
     * Generic HTTP Request
     */
    request: async function(endpoint, options = {}) {
        const url = this.buildURL(endpoint);
        const config = {
            ...this.defaultOptions,
            ...options,
            headers: {
                ...this.defaultOptions.headers,
                ...options.headers
            }
        };

        // Add CSRF token for non-GET requests
        if (config.method !== 'GET') {
            config.headers['X-CSRFToken'] = this.getCSRFToken();
        }

        // Log API call if debugging is enabled
        if (PrintingPricing.Config.DEBUG.LOG_API_CALLS) {
            PrintingPricing.Utils.log(`API Call: ${config.method} ${url}`, 'debug', config);
        }

        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type');
            let data;

            if (contentType && contentType.includes('application/json')) {
                data = await response.json();
            } else {
                data = await response.text();
            }

            // Log successful response
            if (PrintingPricing.Config.DEBUG.LOG_API_CALLS) {
                PrintingPricing.Utils.log(`API Response: ${config.method} ${url}`, 'debug', data);
            }

            return {
                success: true,
                data: data,
                status: response.status,
                headers: response.headers
            };

        } catch (error) {
            PrintingPricing.Utils.log(`API Error: ${config.method} ${url}`, 'error', error);
            
            return {
                success: false,
                error: error.message,
                status: error.status || 0
            };
        }
    },

    /**
     * طلبات GET
     * GET Requests
     */
    get: function(endpoint, params = {}) {
        const url = new URL(this.buildURL(endpoint), window.location.origin);
        Object.keys(params).forEach(key => {
            if (params[key] !== null && params[key] !== undefined) {
                url.searchParams.append(key, params[key]);
            }
        });

        return this.request(url.pathname + url.search);
    },

    /**
     * طلبات POST
     * POST Requests
     */
    post: function(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },

    /**
     * طلبات PUT
     * PUT Requests
     */
    put: function(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },

    /**
     * طلبات PATCH
     * PATCH Requests
     */
    patch: function(endpoint, data = {}) {
        return this.request(endpoint, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    },

    /**
     * طلبات DELETE
     * DELETE Requests
     */
    delete: function(endpoint) {
        return this.request(endpoint, {
            method: 'DELETE'
        });
    },

    /**
     * رفع الملفات
     * File Upload
     */
    upload: function(endpoint, formData) {
        return this.request(endpoint, {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': this.getCSRFToken()
                // Don't set Content-Type for FormData, let browser set it
            }
        });
    },

    /**
     * خدمات API متخصصة
     * Specialized API Services
     */

    // حساب التكلفة
    calculateCost: async function(orderData) {
        const endpoint = PrintingPricing.Config.API.ENDPOINTS.CALCULATE_COST;
        const response = await this.post(endpoint, orderData);
        
        if (PrintingPricing.Config.DEBUG.LOG_CALCULATIONS) {
            PrintingPricing.Utils.log('Cost Calculation', 'debug', { orderData, response });
        }
        
        return response;
    },

    // الحصول على سعر المادة
    getMaterialPrice: function(materialData) {
        const endpoint = PrintingPricing.Config.API.ENDPOINTS.MATERIAL_PRICE;
        return this.post(endpoint, materialData);
    },

    // الحصول على سعر الخدمة
    getServicePrice: function(serviceData) {
        const endpoint = PrintingPricing.Config.API.ENDPOINTS.SERVICE_PRICE;
        return this.post(endpoint, serviceData);
    },

    // التحقق من صحة الطلب
    validateOrder: function(orderData) {
        const endpoint = PrintingPricing.Config.API.ENDPOINTS.VALIDATE_ORDER;
        return this.post(endpoint, orderData);
    },

    // الحصول على ملخص الطلب
    getOrderSummary: function(orderId) {
        const endpoint = PrintingPricing.Config.API.ENDPOINTS.ORDER_SUMMARY + orderId + '/';
        return this.get(endpoint);
    },

    // إدارة الطلبات
    orders: {
        list: function(params = {}) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.ORDERS, params);
        },

        get: function(id) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.ORDERS + id + '/');
        },

        create: function(data) {
            return PrintingPricing.API.post(PrintingPricing.Config.API.ENDPOINTS.ORDERS, data);
        },

        update: function(id, data) {
            return PrintingPricing.API.put(PrintingPricing.Config.API.ENDPOINTS.ORDERS + id + '/', data);
        },

        patch: function(id, data) {
            return PrintingPricing.API.patch(PrintingPricing.Config.API.ENDPOINTS.ORDERS + id + '/', data);
        },

        delete: function(id) {
            return PrintingPricing.API.delete(PrintingPricing.Config.API.ENDPOINTS.ORDERS + id + '/');
        }
    },

    // إدارة المواد
    materials: {
        list: function(params = {}) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.MATERIALS, params);
        },

        get: function(id) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.MATERIALS + id + '/');
        },

        search: function(query) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.MATERIALS, { search: query });
        }
    },

    // إدارة الخدمات
    services: {
        list: function(params = {}) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.SERVICES, params);
        },

        get: function(id) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.SERVICES + id + '/');
        },

        search: function(query) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.SERVICES, { search: query });
        }
    },

    // إدارة الحسابات
    calculations: {
        list: function(params = {}) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.CALCULATIONS, params);
        },

        get: function(id) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.CALCULATIONS + id + '/');
        },

        history: function(orderId) {
            return PrintingPricing.API.get(PrintingPricing.Config.API.ENDPOINTS.CALCULATIONS, { order: orderId });
        }
    },

    /**
     * معالجة الأخطاء المتقدمة
     * Advanced Error Handling
     */
    handleError: function(error, context = '') {
        let message = PrintingPricing.Config.MESSAGES.ERROR.NETWORK_ERROR;
        
        if (error.status === 400) {
            message = PrintingPricing.Config.MESSAGES.ERROR.VALIDATION_ERROR;
        } else if (error.status === 401) {
            message = 'غير مصرح لك بالوصول';
        } else if (error.status === 403) {
            message = 'ليس لديك صلاحية للقيام بهذا الإجراء';
        } else if (error.status === 404) {
            message = 'العنصر المطلوب غير موجود';
        } else if (error.status === 500) {
            message = 'خطأ في الخادم';
        }

        if (context) {
            message = `${context}: ${message}`;
        }

        PrintingPricing.Utils.showToast(message, 'error');
        PrintingPricing.Utils.log(`API Error in ${context}`, 'error', error);

        return message;
    },

    /**
     * إعادة المحاولة التلقائية
     * Automatic Retry
     */
    retry: async function(apiCall, maxRetries = 3, delay = 1000) {
        for (let attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                const result = await apiCall();
                if (result.success) {
                    return result;
                }
                
                if (attempt === maxRetries) {
                    throw new Error(result.error || 'Max retries reached');
                }
            } catch (error) {
                if (attempt === maxRetries) {
                    throw error;
                }
                
                PrintingPricing.Utils.log(`API retry attempt ${attempt}/${maxRetries}`, 'warn', error);
                await new Promise(resolve => setTimeout(resolve, delay * attempt));
            }
        }
    },

    /**
     * تجميع الطلبات
     * Batch Requests
     */
    batch: async function(requests) {
        const promises = requests.map(req => {
            if (typeof req === 'function') {
                return req();
            } else {
                return this.request(req.endpoint, req.options);
            }
        });

        try {
            const results = await Promise.allSettled(promises);
            return results.map((result, index) => ({
                index,
                success: result.status === 'fulfilled',
                data: result.status === 'fulfilled' ? result.value : null,
                error: result.status === 'rejected' ? result.reason : null
            }));
        } catch (error) {
            PrintingPricing.Utils.log('Batch request error', 'error', error);
            throw error;
        }
    }
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PrintingPricing.API;
}
