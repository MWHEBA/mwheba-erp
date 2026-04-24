/**
 * نظام التسعير المحسن - الأدوات المساعدة
 * Printing Pricing System - Utilities
 */

window.PrintingPricing = window.PrintingPricing || {};

PrintingPricing.Utils = {
    
    /**
     * تنسيق الأرقام والعملة
     * Number and Currency Formatting
     */
    formatCurrency: function(amount, currency = 'EGP', precision = 2) {
        if (isNaN(amount)) return '0.00';
        
        const formatted = parseFloat(amount).toFixed(precision);
        const parts = formatted.split('.');
        parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        
        return `${parts.join('.')} ${currency}`;
    },

    formatNumber: function(number, precision = 2) {
        if (isNaN(number)) return '0';
        return parseFloat(number).toFixed(precision);
    },

    parseCurrency: function(currencyString) {
        if (!currencyString) return 0;
        return parseFloat(currencyString.replace(/[^\d.-]/g, '')) || 0;
    },

    /**
     * التحقق من صحة البيانات
     * Data Validation
     */
    validateEmail: function(email) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    },

    validatePhone: function(phone) {
        const phoneRegex = /^[\+]?[1-9][\d]{0,15}$/;
        return phoneRegex.test(phone.replace(/\s/g, ''));
    },

    validateRequired: function(value) {
        return value !== null && value !== undefined && value.toString().trim() !== '';
    },

    validateNumber: function(value, min = null, max = null) {
        const num = parseFloat(value);
        if (isNaN(num)) return false;
        if (min !== null && num < min) return false;
        if (max !== null && num > max) return false;
        return true;
    },

    /**
     * معالجة التواريخ
     * Date Handling
     */
    formatDate: function(date, format = 'YYYY-MM-DD') {
        if (!date) return '';
        
        const d = new Date(date);
        if (isNaN(d.getTime())) return '';
        
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        const hours = String(d.getHours()).padStart(2, '0');
        const minutes = String(d.getMinutes()).padStart(2, '0');
        
        switch (format) {
            case 'DD/MM/YYYY':
                return `${day}/${month}/${year}`;
            case 'MM/DD/YYYY':
                return `${month}/${day}/${year}`;
            case 'YYYY-MM-DD HH:mm':
                return `${year}-${month}-${day} ${hours}:${minutes}`;
            case 'DD/MM/YYYY HH:mm':
                return `${day}/${month}/${year} ${hours}:${minutes}`;
            default:
                return `${year}-${month}-${day}`;
        }
    },

    parseDate: function(dateString) {
        if (!dateString) return null;
        const date = new Date(dateString);
        return isNaN(date.getTime()) ? null : date;
    },

    /**
     * معالجة النصوص
     * String Handling
     */
    slugify: function(text) {
        return text
            .toString()
            .toLowerCase()
            .trim()
            .replace(/\s+/g, '-')
            .replace(/[^\w\-]+/g, '')
            .replace(/\-\-+/g, '-')
            .replace(/^-+/, '')
            .replace(/-+$/, '');
    },

    truncate: function(text, length = 100, suffix = '...') {
        if (!text || text.length <= length) return text;
        return text.substring(0, length) + suffix;
    },

    capitalize: function(text) {
        if (!text) return '';
        return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
    },

    /**
     * معالجة DOM
     * DOM Manipulation
     */
    createElement: function(tag, attributes = {}, content = '') {
        const element = document.createElement(tag);
        
        Object.keys(attributes).forEach(key => {
            if (key === 'className') {
                element.className = attributes[key];
            } else if (key === 'dataset') {
                Object.keys(attributes[key]).forEach(dataKey => {
                    element.dataset[dataKey] = attributes[key][dataKey];
                });
            } else {
                element.setAttribute(key, attributes[key]);
            }
        });
        
        if (content) {
            element.innerHTML = content;
        }
        
        return element;
    },

    addClass: function(element, className) {
        if (element && className) {
            element.classList.add(className);
        }
    },

    removeClass: function(element, className) {
        if (element && className) {
            element.classList.remove(className);
        }
    },

    toggleClass: function(element, className) {
        if (element && className) {
            element.classList.toggle(className);
        }
    },

    hasClass: function(element, className) {
        return element && className && element.classList.contains(className);
    },

    /**
     * معالجة الأحداث
     * Event Handling
     */
    debounce: function(func, wait, immediate = false) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                timeout = null;
                if (!immediate) func.apply(this, args);
            };
            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            if (callNow) func.apply(this, args);
        };
    },

    throttle: function(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    /**
     * التخزين المحلي
     * Local Storage
     */
    storage: {
        set: function(key, value) {
            try {
                localStorage.setItem(key, JSON.stringify(value));
                return true;
            } catch (e) {
                console.warn('Failed to save to localStorage:', e);
                return false;
            }
        },

        get: function(key, defaultValue = null) {
            try {
                const item = localStorage.getItem(key);
                return item ? JSON.parse(item) : defaultValue;
            } catch (e) {
                console.warn('Failed to read from localStorage:', e);
                return defaultValue;
            }
        },

        remove: function(key) {
            try {
                localStorage.removeItem(key);
                return true;
            } catch (e) {
                console.warn('Failed to remove from localStorage:', e);
                return false;
            }
        },

        clear: function() {
            try {
                localStorage.clear();
                return true;
            } catch (e) {
                console.warn('Failed to clear localStorage:', e);
                return false;
            }
        }
    },

    /**
     * معالجة الأخطاء والرسائل
     * Error and Message Handling
     */
    showToast: function(message, type = 'info', duration = 5000) {
        const toast = this.createElement('div', {
            className: `pp-toast pp-toast-${type}`,
            dataset: { duration: duration }
        }, `
            <div class="pp-toast-content">
                <i class="pp-toast-icon fas fa-${this.getToastIcon(type)}"></i>
                <span class="pp-toast-message">${message}</span>
                <button class="pp-toast-close" onclick="this.parentElement.parentElement.remove()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `);

        // Add to toast container or create one
        let container = document.querySelector('.pp-toast-container');
        if (!container) {
            container = this.createElement('div', { className: 'pp-toast-container' });
            document.body.appendChild(container);
        }

        container.appendChild(toast);

        // Auto remove after duration
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, duration);

        return toast;
    },

    getToastIcon: function(type) {
        const icons = {
            success: 'check-circle',
            error: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };
        return icons[type] || 'info-circle';
    },

    showModal: function(title, content, options = {}) {
        const modal = this.createElement('div', {
            className: 'pp-modal',
            id: options.id || 'pp-modal-' + Date.now()
        }, `
            <div class="pp-modal-backdrop"></div>
            <div class="pp-modal-dialog">
                <div class="pp-modal-content">
                    <div class="pp-modal-header">
                        <h5 class="pp-modal-title">${title}</h5>
                        <button class="pp-modal-close" onclick="this.closest('.pp-modal').remove()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="pp-modal-body">
                        ${content}
                    </div>
                    ${options.footer ? `<div class="pp-modal-footer">${options.footer}</div>` : ''}
                </div>
            </div>
        `);

        document.body.appendChild(modal);

        // Close on backdrop click
        modal.querySelector('.pp-modal-backdrop').addEventListener('click', () => {
            modal.remove();
        });

        return modal;
    },

    /**
     * أدوات متنوعة
     * Miscellaneous Utilities
     */
    generateId: function(prefix = 'pp') {
        return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    },

    copyToClipboard: function(text) {
        if (navigator.clipboard) {
            return navigator.clipboard.writeText(text);
        } else {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            return Promise.resolve();
        }
    },

    downloadFile: function(data, filename, type = 'text/plain') {
        const blob = new Blob([data], { type });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    },

    /**
     * سجل الأخطاء والتشخيص
     * Logging and Debugging
     */
    log: function(message, level = 'info', data = null) {
        if (!PrintingPricing.Config.DEBUG.ENABLED) return;

        const timestamp = new Date().toISOString();
        const logMessage = `[${timestamp}] [${level.toUpperCase()}] ${message}`;

        switch (level) {
            case 'debug':
                console.debug(logMessage, data);
                break;
            case 'info':
                console.info(logMessage, data);
                break;
            case 'warn':
                console.warn(logMessage, data);
                break;
            case 'error':
                console.error(logMessage, data);
                break;
            default:
                console.log(logMessage, data);
        }
    }
};

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PrintingPricing.Utils;
}
