/**
 * مدير جلسة الاستيراد
 * Import Session Manager
 */

class ImportSessionManager {
    constructor(sessionId) {
        this.sessionId = sessionId;
        this.localStorageKey = `import_session_${sessionId}`;
    }
    
    /**
     * حفظ حالة العملية
     */
    saveState(state) {
        const sessionData = {
            ...state,
            timestamp: new Date().toISOString(),
            sessionId: this.sessionId
        };
        
        try {
            localStorage.setItem(this.localStorageKey, JSON.stringify(sessionData));
        } catch (error) {
            console.error('خطأ في حفظ حالة الجلسة:', error);
        }
    }
    
    /**
     * استرجاع حالة العملية
     */
    loadState() {
        try {
            const savedData = localStorage.getItem(this.localStorageKey);
            if (savedData) {
                const parsedData = JSON.parse(savedData);
                return parsedData;
            }
        } catch (error) {
            console.error('خطأ في قراءة البيانات المحفوظة:', error);
        }
        return null;
    }
    
    /**
     * مسح البيانات المحفوظة
     */
    clearState() {
        try {
            localStorage.removeItem(this.localStorageKey);
        } catch (error) {
            console.error('خطأ في مسح حالة الجلسة:', error);
        }
    }
    
    /**
     * التحقق من وجود جلسة متوقفة
     */
    hasPausedSession() {
        const state = this.loadState();
        return state && state.isPaused && state.isProcessing;
    }
    
    /**
     * عرض خيار استكمال الجلسة المتوقفة
     */
    showResumeOption() {
        const state = this.loadState();
        if (!state || !state.isPaused) return;
        
        const resumeAlert = document.createElement('div');
        resumeAlert.className = 'alert alert-info alert-dismissible fade show';
        resumeAlert.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="fas fa-info-circle me-3 fs-4"></i>
                <div class="flex-grow-1">
                    <strong>جلسة متوقفة:</strong> يوجد عملية استيراد متوقفة من ${this.formatDateTime(state.timestamp)}.
                    <br>
                    <small class="text-muted">
                        التقدم: ${state.currentRecord || 0} من ${state.totalRecords || 0} سجل
                        ${state.stats ? `(نجح: ${state.stats.successful || 0}, فشل: ${state.stats.failed || 0})` : ''}
                    </small>
                </div>
                <div class="ms-3">
                    <button type="button" class="btn btn-primary btn-sm me-2" onclick="resumePausedSession()">
                        <i class="fas fa-play"></i> استكمال
                    </button>
                    <button type="button" class="btn btn-outline-secondary btn-sm" onclick="clearPausedSession()">
                        <i class="fas fa-times"></i> بدء جديد
                    </button>
                </div>
            </div>
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // إدراج التنبيه في أعلى الصفحة
        const container = document.querySelector('.container-fluid');
        if (container) {
            container.insertBefore(resumeAlert, container.firstChild);
        }
    }
    
    /**
     * تنسيق التاريخ والوقت
     */
    formatDateTime(isoString) {
        try {
            const date = new Date(isoString);
            return date.toLocaleString('ar-EG', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (error) {
            return 'غير محدد';
        }
    }
    
    /**
     * حفظ إعدادات الاستيراد
     */
    saveImportSettings(settings) {
        const settingsKey = `import_settings_${this.sessionId}`;
        try {
            localStorage.setItem(settingsKey, JSON.stringify(settings));
        } catch (error) {
            console.error('خطأ في حفظ إعدادات الاستيراد:', error);
        }
    }
    
    /**
     * استرجاع إعدادات الاستيراد
     */
    loadImportSettings() {
        const settingsKey = `import_settings_${this.sessionId}`;
        try {
            const savedSettings = localStorage.getItem(settingsKey);
            return savedSettings ? JSON.parse(savedSettings) : null;
        } catch (error) {
            console.error('خطأ في استرجاع إعدادات الاستيراد:', error);
            return null;
        }
    }
    
    /**
     * حفظ إحصائيات العملية
     */
    saveStats(stats) {
        const statsKey = `import_stats_${this.sessionId}`;
        try {
            const statsData = {
                ...stats,
                timestamp: new Date().toISOString()
            };
            localStorage.setItem(statsKey, JSON.stringify(statsData));
        } catch (error) {
            console.error('خطأ في حفظ الإحصائيات:', error);
        }
    }
    
    /**
     * استرجاع إحصائيات العملية
     */
    loadStats() {
        const statsKey = `import_stats_${this.sessionId}`;
        try {
            const savedStats = localStorage.getItem(statsKey);
            return savedStats ? JSON.parse(savedStats) : null;
        } catch (error) {
            console.error('خطأ في استرجاع الإحصائيات:', error);
            return null;
        }
    }
    
    /**
     * مسح جميع البيانات المرتبطة بالجلسة
     */
    clearAllSessionData() {
        const keysToRemove = [
            this.localStorageKey,
            `import_settings_${this.sessionId}`,
            `import_stats_${this.sessionId}`
        ];
        
        keysToRemove.forEach(key => {
            try {
                localStorage.removeItem(key);
            } catch (error) {
                console.error(`خطأ في مسح ${key}:`, error);
            }
        });
    }
    
    /**
     * التحقق من انتهاء صلاحية الجلسة
     */
    isSessionExpired(maxAgeHours = 24) {
        const state = this.loadState();
        if (!state || !state.timestamp) return true;
        
        const sessionTime = new Date(state.timestamp);
        const now = new Date();
        const ageHours = (now - sessionTime) / (1000 * 60 * 60);
        
        return ageHours > maxAgeHours;
    }
    
    /**
     * تنظيف الجلسات المنتهية الصلاحية
     */
    static cleanupExpiredSessions() {
        try {
            const keys = Object.keys(localStorage);
            const sessionKeys = keys.filter(key => key.startsWith('import_session_'));
            
            sessionKeys.forEach(key => {
                try {
                    const data = JSON.parse(localStorage.getItem(key));
                    if (data && data.timestamp) {
                        const sessionTime = new Date(data.timestamp);
                        const now = new Date();
                        const ageHours = (now - sessionTime) / (1000 * 60 * 60);
                        
                        // مسح الجلسات الأقدم من 24 ساعة
                        if (ageHours > 24) {
                            localStorage.removeItem(key);
                        }
                    }
                } catch (error) {
                    // مسح البيانات التالفة
                    localStorage.removeItem(key);
                }
            });
        } catch (error) {
            console.error('خطأ في تنظيف الجلسات المنتهية الصلاحية:', error);
        }
    }
}

/**
 * استكمال الجلسة المتوقفة
 */
function resumePausedSession() {
    if (!window.currentSessionId) {
        console.error('معرف الجلسة غير متوفر');
        return;
    }
    
    const sessionManager = new ImportSessionManager(window.currentSessionId);
    const state = sessionManager.loadState();
    
    if (state && window.importManager) {
        // استعادة حالة المدير
        window.importManager.currentRecord = state.currentRecord || 0;
        window.importManager.totalRecords = state.totalRecords || 0;
        window.importManager.isPaused = false;
        window.importManager.isProcessing = true;
        
        if (state.stats) {
            window.importManager.stats = state.stats;
        }
        
        // تحديث الواجهة
        window.importManager.updateProgress();
        window.importManager.updateUI();
        
        // استكمال المعالجة
        window.importManager.resumeImport();
        
        // إخفاء التنبيه
        const alert = document.querySelector('.alert');
        if (alert) alert.remove();
        
        addLogEntry('تم استكمال الجلسة المتوقفة', 'info');
        showAlert('تم استكمال العملية من حيث توقفت', 'success');
    } else {
        showAlert('لا يمكن استكمال الجلسة - البيانات غير متوفرة', 'error');
    }
}

/**
 * مسح الجلسة المتوقفة وبدء جديدة
 */
function clearPausedSession() {
    if (!window.currentSessionId) {
        console.error('معرف الجلسة غير متوفر');
        return;
    }
    
    const confirmed = confirm('هل أنت متأكد من مسح الجلسة المتوقفة وبدء عملية جديدة؟\nسيتم فقدان التقدم المحفوظ.');
    
    if (confirmed) {
        const sessionManager = new ImportSessionManager(window.currentSessionId);
        sessionManager.clearAllSessionData();
        
        // إخفاء التنبيه
        const alert = document.querySelector('.alert');
        if (alert) alert.remove();
        
        // إعادة تحميل الصفحة لبدء جلسة جديدة
        window.location.reload();
    }
}

/**
 * حفظ حالة الجلسة عند مغادرة الصفحة
 */
function saveSessionOnUnload() {
    if (window.importManager && window.importManager.isProcessing && window.currentSessionId) {
        const sessionManager = new ImportSessionManager(window.currentSessionId);
        sessionManager.saveState({
            currentRecord: window.importManager.currentRecord,
            totalRecords: window.importManager.totalRecords,
            isPaused: window.importManager.isPaused,
            isProcessing: window.importManager.isProcessing,
            stats: window.importManager.stats,
            currentRecordId: window.importManager.currentRecordId
        });
    }
}

// وظائف مساعدة عامة
function showAlert(message, type = 'info') {
    if (typeof toastr !== 'undefined') {
        if (type === 'success') toastr.success(message);
        else if (type === 'error' || type === 'danger') toastr.error(message);
        else if (type === 'warning') toastr.warning(message);
        else toastr.info(message);
    } else {
        // Fallback to Bootstrap alert
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            <i class="fas fa-${getAlertIcon(type)} me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        // إدراج التنبيه
        const container = document.querySelector('.container-fluid');
        if (container) {
            container.insertBefore(alertDiv, container.firstChild);
        }
        
        // إزالة التنبيه تلقائياً بعد 5 ثوان
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.remove();
            }
        }, 5000);
    }
}

function getAlertIcon(type) {
    const icons = {
        'success': 'check-circle',
        'error': 'exclamation-circle',
        'warning': 'exclamation-triangle',
        'info': 'info-circle',
        'danger': 'exclamation-circle'
    };
    return icons[type] || 'info-circle';
}

function showConfirmDialog(title, message) {
    return new Promise((resolve) => {
        const confirmModal = document.getElementById('confirmActionModal');
        if (!confirmModal) {
            // إنشاء نافذة تأكيد بسيطة إذا لم تكن موجودة
            resolve(confirm(`${title}\n\n${message}`));
            return;
        }
        
        document.getElementById('confirm-message').innerHTML = `
            <strong>${title}</strong><br>
            <small class="text-muted">${message}</small>
        `;
        
        const modal = new bootstrap.Modal(confirmModal);
        modal.show();
        
        // معالج الموافقة
        const confirmBtn = document.getElementById('confirm-yes-btn');
        const handleConfirm = () => {
            modal.hide();
            resolve(true);
            confirmBtn.removeEventListener('click', handleConfirm);
        };
        confirmBtn.addEventListener('click', handleConfirm);
        
        // معالج الإلغاء
        const handleCancel = () => {
            resolve(false);
            confirmModal.removeEventListener('hidden.bs.modal', handleCancel);
        };
        confirmModal.addEventListener('hidden.bs.modal', handleCancel, { once: true });
    });
}

function getCurrentRecordId() {
    return window.importManager?.currentRecordId || null;
}

function getCSRFToken() {
    const token = document.querySelector('[name=csrfmiddlewaretoken]');
    return token ? token.value : '';
}

// تهيئة عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    // تنظيف الجلسات المنتهية الصلاحية
    ImportSessionManager.cleanupExpiredSessions();
    
    // حفظ معرف الجلسة الحالي
    const sessionIdElement = document.getElementById('session-id');
    if (sessionIdElement) {
        window.currentSessionId = sessionIdElement.value;
    }
});

// حفظ حالة الجلسة عند مغادرة الصفحة
window.addEventListener('beforeunload', saveSessionOnUnload);

// حفظ حالة الجلسة عند إخفاء الصفحة (للأجهزة المحمولة)
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        saveSessionOnUnload();
    }
});
