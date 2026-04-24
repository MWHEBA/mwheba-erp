/**
 * Enhanced Message System
 * نظام الرسائل المحسن
 */

// تجنب التعريف المكرر
if (typeof window.MessageSystem !== 'undefined') {
    console.warn('MessageSystem already defined, skipping redefinition');
} else {

class MessageSystem {
    constructor() {
        this.messageQueue = [];
        this.activeMessages = new Map();
        this.messageHistory = [];
        this.config = {
            maxMessages: 5,
            defaultDuration: 5000,
            animationDuration: 300,
            stackSpacing: 10,
            position: 'top-left', // top-left, top-right, bottom-left, bottom-right
            rtl: true
        };
        this.messageTypes = {
            success: {
                icon: 'fas fa-check-circle',
                color: 'var(--success-color)',
                bgColor: 'var(--success-soft)',
                borderColor: 'var(--success-color)'
            },
            error: {
                icon: 'fas fa-exclamation-circle',
                color: 'var(--danger-color)',
                bgColor: 'var(--danger-soft)',
                borderColor: 'var(--danger-color)'
            },
            warning: {
                icon: 'fas fa-exclamation-triangle',
                color: 'var(--warning-color)',
                bgColor: 'var(--warning-soft)',
                borderColor: 'var(--warning-color)'
            },
            info: {
                icon: 'fas fa-info-circle',
                color: 'var(--info-color)',
                bgColor: 'var(--info-soft)',
                borderColor: 'var(--info-color)'
            },
            loading: {
                icon: 'fas fa-spinner fa-spin',
                color: 'var(--primary-color)',
                bgColor: 'var(--primary-soft)',
                borderColor: 'var(--primary-color)'
            }
        };
        
        this.init();
    }

    init() {
        this.createContainer();
        this.setupEventListeners();
        this.loadSavedMessages();
    }

    createContainer() {
        // Remove existing container
        const existing = document.getElementById('message-container');
        if (existing) {
            existing.remove();
        }

        // Create new container
        this.container = document.createElement('div');
        this.container.id = 'message-container';
        this.container.className = `message-container position-${this.config.position}`;
        this.container.setAttribute('aria-live', 'polite');
        this.container.setAttribute('aria-label', 'رسائل النظام');
        
        document.body.appendChild(this.container);
    }

    setupEventListeners() {
        // ⚠️ تم تعطيل التحويل التلقائي - toastr-system.js هو المسؤول الوحيد
        // MessageSystem يستخدم فقط للـ custom events المباشرة
        
        // Listen for custom message events ONLY (not Django messages)
        document.addEventListener('showMessage', (event) => {
            const { message, type, options } = event.detail;
            this.show(message, type, options);
        });

        // Listen for form validation events
        document.addEventListener('formValidationError', (event) => {
            const { errors } = event.detail;
            this.showValidationErrors(errors);
        });

        // Listen for network events
        document.addEventListener('networkError', (event) => {
            const { error } = event.detail;
            this.showNetworkError(error);
        });

        // Listen for save events
        document.addEventListener('dataSaved', (event) => {
            const { message } = event.detail;
            this.showSuccess(message || 'تم الحفظ بنجاح');
        });

        // Keyboard shortcuts
        document.addEventListener('keydown', (event) => {
            // Escape to close all messages
            if (event.key === 'Escape') {
                this.clearAll();
            }
            
            // Ctrl+M to show message history
            if (event.ctrlKey && event.key === 'm') {
                event.preventDefault();
                this.showHistory();
            }
        });
    }

    show(message, type = 'info', options = {}) {
        const messageObj = {
            id: this.generateId(),
            message: message,
            type: type,
            timestamp: Date.now(),
            duration: options.duration || this.config.defaultDuration,
            persistent: options.persistent || false,
            actions: options.actions || [],
            progress: options.progress || false,
            html: options.html || false,
            priority: options.priority || 'normal'
        };

        // Add to queue if too many messages
        if (this.activeMessages.size >= this.config.maxMessages) {
            if (messageObj.priority === 'high') {
                // Remove oldest low priority message
                this.removeOldestLowPriority();
            } else {
                this.messageQueue.push(messageObj);
                return messageObj.id;
            }
        }

        this.displayMessage(messageObj);
        this.addToHistory(messageObj);
        
        return messageObj.id;
    }

    displayMessage(messageObj) {
        const messageElement = this.createMessageElement(messageObj);
        this.container.appendChild(messageElement);
        this.activeMessages.set(messageObj.id, { ...messageObj, element: messageElement });

        // Animate in
        requestAnimationFrame(() => {
            messageElement.classList.add('show');
        });

        // Auto-remove if not persistent
        if (!messageObj.persistent && messageObj.duration > 0) {
            setTimeout(() => {
                this.remove(messageObj.id);
            }, messageObj.duration);
        }

        // Update positions
        this.updatePositions();
    }

    createMessageElement(messageObj) {
        const element = document.createElement('div');
        element.className = 'message-item';
        element.setAttribute('data-message-id', messageObj.id);
        element.setAttribute('data-type', messageObj.type); // إضافة نوع الرسالة
        element.setAttribute('role', 'alert');
        element.setAttribute('aria-live', 'assertive');

        const typeConfig = this.messageTypes[messageObj.type] || this.messageTypes.info;
        
        element.innerHTML = `
            <div class="message-content">
                <div class="message-icon">
                    <i class="${typeConfig.icon}"></i>
                </div>
                <div class="message-body">
                    <div class="message-text">
                        ${messageObj.html ? messageObj.message : this.escapeHtml(messageObj.message)}
                    </div>
                    ${messageObj.progress ? '<div class="message-progress"><div class="progress-bar"></div></div>' : ''}
                    ${messageObj.actions.length > 0 ? this.createActionsHtml(messageObj.actions) : ''}
                </div>
                <div class="message-controls">
                    ${messageObj.persistent ? '' : '<div class="message-timer"></div>'}
                    <button type="button" class="message-close" aria-label="إغلاق الرسالة">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        `;

        // Apply styles
        element.style.setProperty('--message-color', typeConfig.color);
        element.style.setProperty('--message-bg', typeConfig.bgColor);
        element.style.setProperty('--message-border', typeConfig.borderColor);

        // Add event listeners
        this.addMessageEventListeners(element, messageObj);

        return element;
    }

    createActionsHtml(actions) {
        return `
            <div class="message-actions">
                ${actions.map(action => `
                    <button type="button" 
                            class="message-action-btn ${action.class || ''}" 
                            data-action="${action.action}">
                        ${action.icon ? `<i class="${action.icon}"></i>` : ''}
                        ${action.text}
                    </button>
                `).join('')}
            </div>
        `;
    }

    addMessageEventListeners(element, messageObj) {
        // Close button
        const closeBtn = element.querySelector('.message-close');
        closeBtn.addEventListener('click', () => {
            this.remove(messageObj.id);
        });

        // Action buttons
        const actionBtns = element.querySelectorAll('.message-action-btn');
        actionBtns.forEach(btn => {
            btn.addEventListener('click', (event) => {
                const actionName = event.target.getAttribute('data-action');
                const action = messageObj.actions.find(a => a.action === actionName);
                
                if (action && action.handler) {
                    action.handler(messageObj.id, messageObj);
                }
                
                // Auto-close unless specified otherwise
                if (!action || action.autoClose !== false) {
                    this.remove(messageObj.id);
                }
            });
        });

        // Timer animation
        if (!messageObj.persistent && messageObj.duration > 0) {
            const timer = element.querySelector('.message-timer');
            if (timer) {
                timer.style.animationDuration = `${messageObj.duration}ms`;
                timer.classList.add('animate');
            }
        }

        // Hover to pause timer
        element.addEventListener('mouseenter', () => {
            element.classList.add('paused');
        });

        element.addEventListener('mouseleave', () => {
            element.classList.remove('paused');
        });
    }

    remove(messageId) {
        const messageData = this.activeMessages.get(messageId);
        if (!messageData) return;

        const element = messageData.element;
        
        // Animate out
        element.classList.add('removing');
        
        setTimeout(() => {
            if (element.parentNode) {
                element.parentNode.removeChild(element);
            }
            this.activeMessages.delete(messageId);
            this.updatePositions();
            this.processQueue();
        }, this.config.animationDuration);
    }

    updatePositions() {
        const messages = Array.from(this.container.children);
        messages.forEach((message, index) => {
            const offset = index * (message.offsetHeight + this.config.stackSpacing);
            
            if (this.config.position.includes('top')) {
                message.style.transform = `translateY(${offset}px)`;
            } else {
                message.style.transform = `translateY(-${offset}px)`;
            }
        });
    }

    processQueue() {
        if (this.messageQueue.length > 0 && this.activeMessages.size < this.config.maxMessages) {
            const nextMessage = this.messageQueue.shift();
            this.displayMessage(nextMessage);
        }
    }

    removeOldestLowPriority() {
        for (const [id, messageData] of this.activeMessages) {
            if (messageData.priority !== 'high') {
                this.remove(id);
                break;
            }
        }
    }

    // Convenience methods
    showSuccess(message, options = {}) {
        return this.show(message, 'success', options);
    }

    showError(message, options = {}) {
        return this.show(message, 'error', { duration: 8000, ...options });
    }

    showWarning(message, options = {}) {
        return this.show(message, 'warning', { duration: 6000, ...options });
    }

    showInfo(message, options = {}) {
        return this.show(message, 'info', options);
    }

    showLoading(message, options = {}) {
        return this.show(message, 'loading', { persistent: true, ...options });
    }

    showValidationErrors(errors) {
        if (Array.isArray(errors)) {
            errors.forEach(error => {
                this.showError(error);
            });
        } else if (typeof errors === 'object') {
            Object.entries(errors).forEach(([field, messages]) => {
                const fieldMessages = Array.isArray(messages) ? messages : [messages];
                fieldMessages.forEach(message => {
                    this.showError(`${field}: ${message}`);
                });
            });
        } else {
            this.showError(errors);
        }
    }

    showNetworkError(error) {
        let message = 'حدث خطأ في الاتصال';
        
        if (error.status) {
            switch (error.status) {
                case 400:
                    message = 'خطأ في البيانات المرسلة';
                    break;
                case 401:
                    message = 'انتهت صلاحية الجلسة، يرجى تسجيل الدخول مرة أخرى';
                    break;
                case 403:
                    message = 'ليس لديك صلاحية للوصول لهذه البيانات';
                    break;
                case 404:
                    message = 'البيانات المطلوبة غير موجودة';
                    break;
                case 500:
                    message = 'خطأ في الخادم، يرجى المحاولة لاحقاً';
                    break;
                default:
                    message = `خطأ في الشبكة (${error.status})`;
            }
        }

        return this.showError(message, {
            actions: [
                {
                    text: 'إعادة المحاولة',
                    action: 'retry',
                    icon: 'fas fa-redo',
                    handler: () => {
                        if (error.retry) {
                            error.retry();
                        }
                    }
                }
            ]
        });
    }

    updateProgress(messageId, progress) {
        const messageData = this.activeMessages.get(messageId);
        if (!messageData) return;

        const progressBar = messageData.element.querySelector('.progress-bar');
        if (progressBar) {
            progressBar.style.width = `${Math.min(100, Math.max(0, progress))}%`;
        }
    }

    updateMessage(messageId, newMessage, newType) {
        const messageData = this.activeMessages.get(messageId);
        if (!messageData) return;

        const textElement = messageData.element.querySelector('.message-text');
        if (textElement) {
            textElement.textContent = newMessage;
        }

        if (newType && newType !== messageData.type) {
            const typeConfig = this.messageTypes[newType] || this.messageTypes.info;
            const element = messageData.element;
            
            element.style.setProperty('--message-color', typeConfig.color);
            element.style.setProperty('--message-bg', typeConfig.bgColor);
            element.style.setProperty('--message-border', typeConfig.borderColor);
            
            const icon = element.querySelector('.message-icon i');
            if (icon) {
                icon.className = typeConfig.icon;
            }
            
            messageData.type = newType;
        }
    }

    clearAll() {
        const messageIds = Array.from(this.activeMessages.keys());
        messageIds.forEach(id => this.remove(id));
        this.messageQueue = [];
        
        // تنظيف فوري للحاوي إذا لزم الأمر
        if (this.container) {
            const remainingMessages = this.container.querySelectorAll('.message-item');
            remainingMessages.forEach(element => {
                if (element.parentNode) {
                    element.parentNode.removeChild(element);
                }
            });
        }
        
        // تنظيف الخريطة
        this.activeMessages.clear();
    }

    clearType(type) {
        const messageIds = Array.from(this.activeMessages.entries())
            .filter(([id, data]) => data.type === type)
            .map(([id]) => id);
        
        messageIds.forEach(id => this.remove(id));
    }

    addToHistory(messageObj) {
        this.messageHistory.unshift({
            ...messageObj,
            element: null // Don't store DOM elements in history
        });

        // Keep only last 50 messages
        if (this.messageHistory.length > 50) {
            this.messageHistory = this.messageHistory.slice(0, 50);
        }

        // Save to sessionStorage
        try {
            const historyToSave = this.messageHistory.slice(0, 10); // Save only last 10
            sessionStorage.setItem('messageHistory', JSON.stringify(historyToSave));
        } catch (error) {
            console.warn('Failed to save message history:', error);
        }
    }

    loadSavedMessages() {
        try {
            const saved = sessionStorage.getItem('messageHistory');
            if (saved) {
                this.messageHistory = JSON.parse(saved);
            }
        } catch (error) {
            console.warn('Failed to load message history:', error);
        }
    }

    showHistory() {
        if (this.messageHistory.length === 0) {
            this.showInfo('لا توجد رسائل في السجل');
            return;
        }

        const historyHtml = this.messageHistory.slice(0, 10).map(msg => `
            <div class="history-item">
                <div class="history-time">${new Date(msg.timestamp).toLocaleTimeString('en-GB')}</div>
                <div class="history-type">${this.getTypeLabel(msg.type)}</div>
                <div class="history-message">${this.escapeHtml(msg.message)}</div>
            </div>
        `).join('');

        this.show(`
            <div class="message-history">
                <h6>سجل الرسائل</h6>
                <div class="history-list">${historyHtml}</div>
            </div>
        `, 'info', {
            html: true,
            duration: 10000,
            persistent: false
        });
    }

    getTypeLabel(type) {
        const labels = {
            success: 'نجاح',
            error: 'خطأ',
            warning: 'تحذير',
            info: 'معلومات',
            loading: 'تحميل'
        };
        return labels[type] || type;
    }

    // Utility methods
    generateId() {
        return 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Configuration methods
    setPosition(position) {
        this.config.position = position;
        this.container.className = `message-container position-${position}`;
        this.updatePositions();
    }

    setMaxMessages(max) {
        this.config.maxMessages = max;
    }

    setDefaultDuration(duration) {
        this.config.defaultDuration = duration;
    }

    // Public API
    getActiveMessages() {
        return Array.from(this.activeMessages.values()).map(data => ({
            id: data.id,
            message: data.message,
            type: data.type,
            timestamp: data.timestamp
        }));
    }

    getHistory() {
        return [...this.messageHistory];
    }

    isActive(messageId) {
        return this.activeMessages.has(messageId);
    }

    destroy() {
        this.clearAll();
        if (this.container && this.container.parentNode) {
            this.container.parentNode.removeChild(this.container);
        }
    }
}

// Initialize message system
document.addEventListener('DOMContentLoaded', function() {
    // ⚠️ MessageSystem معطل افتراضياً - toastr هو النظام الأساسي
    // لتفعيله يدوياً: window.messageSystem = new MessageSystem();
    
    // تجنب التهيئة المكررة
    if (window.messageSystem) {
        console.warn('MessageSystem already initialized');
        return;
    }
    
    // ❌ لا نهيئ MessageSystem تلقائياً - فقط نخليه متاح للاستخدام اليدوي
    // window.messageSystem = new MessageSystem();
    
    // ❌ لا نعرف global functions - toastr-system.js هو المسؤول
    // Global convenience functions are handled by toastr-system.js
});

// Handle page unload
window.addEventListener('beforeunload', function() {
    if (window.messageSystem) {
        window.messageSystem.destroy();
    }
});

// Export for use in other modules
window.MessageSystem = MessageSystem;

} // إغلاق شرط التعريف المكرر