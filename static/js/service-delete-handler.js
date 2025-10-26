/**
 * معالج حذف الخدمات الموحد
 * يدعم جميع أنواع الخدمات المتخصصة
 * @version 1.0.0
 */

class ServiceDeleteHandler {
    constructor() {
        this.modalElement = document.getElementById('deleteServiceModal');
        this.modal = null;
        this.serviceId = null;
        this.serviceName = null;
        this.serviceCategory = null;
        this.supplierId = null;
        
        this.initModal();
        this.attachEventListeners();
    }
    
    /**
     * تهيئة Bootstrap Modal
     */
    initModal() {
        if (this.modalElement) {
            this.modal = new bootstrap.Modal(this.modalElement);
        } else {
            console.error('❌ Modal element not found: #deleteServiceModal');
        }
    }
    
    /**
     * ربط الأحداث
     */
    attachEventListeners() {
        const confirmBtn = document.getElementById('confirmDeleteBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', () => this.confirmDelete());
        }
        
        // إعادة تعيين عند إغلاق Modal
        if (this.modalElement) {
            this.modalElement.addEventListener('hidden.bs.modal', () => this.reset());
        }
    }
    
    /**
     * عرض Modal الحذف
     * @param {number} serviceId - معرف الخدمة
     * @param {string} serviceName - اسم الخدمة
     * @param {string} serviceCategory - فئة الخدمة
     * @param {object} serviceDetails - تفاصيل الخدمة (اختياري)
     */
    show(serviceId, serviceName, serviceCategory, serviceDetails = {}) {
        if (!this.modal) {
            console.error('❌ Modal not initialized');
            return;
        }
        
        this.serviceId = serviceId;
        this.serviceName = serviceName;
        this.serviceCategory = serviceCategory;
        this.supplierId = serviceDetails.supplier_id;
        
        // عرض معلومات الخدمة
        this.renderServiceInfo(serviceDetails);
        
        // عرض Modal
        this.modal.show();
        
        console.log(`🗑️ عرض modal حذف الخدمة: ${serviceName} (ID: ${serviceId})`);
    }
    
    /**
     * عرض معلومات الخدمة في Modal
     */
    renderServiceInfo(details) {
        const infoContainer = document.getElementById('service-delete-info');
        if (!infoContainer) return;
        
        const html = `
            <div class="row g-3">
                <div class="col-md-6">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-tag text-primary me-2"></i>
                        <div>
                            <small class="text-muted d-block">اسم الخدمة</small>
                            <strong>${this.serviceName}</strong>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-folder text-info me-2"></i>
                        <div>
                            <small class="text-muted d-block">نوع الخدمة</small>
                            <strong>${this.serviceCategory || 'غير محدد'}</strong>
                        </div>
                    </div>
                </div>
                ${details.price ? `
                <div class="col-md-6">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-money-bill-wave text-success me-2"></i>
                        <div>
                            <small class="text-muted d-block">السعر</small>
                            <strong>${details.price} ر.س</strong>
                        </div>
                    </div>
                </div>
                ` : ''}
                ${details.is_active !== undefined ? `
                <div class="col-md-6">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-toggle-${details.is_active ? 'on text-success' : 'off text-secondary'} me-2"></i>
                        <div>
                            <small class="text-muted d-block">الحالة</small>
                            <span class="badge bg-${details.is_active ? 'success' : 'secondary'}">
                                ${details.is_active ? 'نشط' : 'غير نشط'}
                            </span>
                        </div>
                    </div>
                </div>
                ` : ''}
            </div>
        `;
        
        infoContainer.innerHTML = html;
    }
    
    /**
     * تأكيد الحذف
     */
    async confirmDelete() {
        if (!this.serviceId) {
            console.error('❌ Service ID not set');
            return;
        }
        
        // عرض حالة التحميل
        this.setLoadingState(true);
        
        try {
            console.log(`🗑️ بدء حذف الخدمة ID: ${this.serviceId}`);
            
            const response = await fetch(`/supplier/api/universal/delete-service/${this.serviceId}/`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': this.getCsrfToken(),
                    'Content-Type': 'application/json'
                }
            });
            
            const data = await response.json();
            
            if (response.ok && data.success) {
                console.log('✅ تم حذف الخدمة بنجاح');
                
                // إخفاء Modal
                this.modal.hide();
                
                // عرض رسالة نجاح
                this.showSuccessMessage(data.message || 'تم حذف الخدمة بنجاح');
                
                // إعادة تحميل الصفحة بعد ثانية
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
                
            } else {
                throw new Error(data.error || 'فشل حذف الخدمة');
            }
            
        } catch (error) {
            console.error('❌ خطأ في حذف الخدمة:', error);
            this.showErrorMessage(error.message || 'حدث خطأ أثناء حذف الخدمة');
            this.setLoadingState(false);
        }
    }
    
    /**
     * تعيين حالة التحميل
     */
    setLoadingState(isLoading) {
        const confirmBtn = document.getElementById('confirmDeleteBtn');
        const buttonText = document.getElementById('deleteButtonText');
        const buttonSpinner = document.getElementById('deleteButtonSpinner');
        
        if (confirmBtn) {
            confirmBtn.disabled = isLoading;
        }
        
        if (buttonText && buttonSpinner) {
            if (isLoading) {
                buttonText.classList.add('d-none');
                buttonSpinner.classList.remove('d-none');
            } else {
                buttonText.classList.remove('d-none');
                buttonSpinner.classList.add('d-none');
            }
        }
    }
    
    /**
     * عرض رسالة نجاح
     */
    showSuccessMessage(message) {
        // استخدام Toastr إذا كان متاحاً
        if (typeof toastr !== 'undefined') {
            toastr.success(message, 'نجح الحذف', {
                closeButton: true,
                progressBar: true,
                positionClass: 'toast-top-left',
                timeOut: 3000
            });
        } else {
            alert(message);
        }
    }
    
    /**
     * عرض رسالة خطأ
     */
    showErrorMessage(message) {
        // استخدام Toastr إذا كان متاحاً
        if (typeof toastr !== 'undefined') {
            toastr.error(message, 'خطأ في الحذف', {
                closeButton: true,
                progressBar: true,
                positionClass: 'toast-top-left',
                timeOut: 5000
            });
        } else {
            alert('خطأ: ' + message);
        }
    }
    
    /**
     * الحصول على CSRF Token
     */
    getCsrfToken() {
        // 1. محاولة الحصول من input hidden
        const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenInput && tokenInput.value) {
            console.log('✅ CSRF Token من input:', tokenInput.value.substring(0, 10) + '...');
            return tokenInput.value;
        }
        
        // 2. محاولة الحصول من meta tag
        const tokenMeta = document.querySelector('meta[name="csrf-token"]');
        if (tokenMeta && tokenMeta.content) {
            console.log('✅ CSRF Token من meta:', tokenMeta.content.substring(0, 10) + '...');
            return tokenMeta.content;
        }
        
        // 3. محاولة الحصول من الكوكيز
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
            
        if (cookieValue) {
            console.log('✅ CSRF Token من cookie:', cookieValue.substring(0, 10) + '...');
            return cookieValue;
        }
        
        console.error('❌ لم يتم العثور على CSRF Token!');
        return '';
    }
    
    /**
     * إعادة تعيين الحالة
     */
    reset() {
        this.serviceId = null;
        this.serviceName = null;
        this.serviceCategory = null;
        this.supplierId = null;
        this.setLoadingState(false);
        
        // مسح المحتوى
        const infoContainer = document.getElementById('service-delete-info');
        if (infoContainer) {
            infoContainer.innerHTML = '';
        }
    }
}

// إنشاء instance عام
let serviceDeleteHandler;

// تهيئة عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    serviceDeleteHandler = new ServiceDeleteHandler();
    console.log('✅ ServiceDeleteHandler initialized');
});

/**
 * دالة عامة لحذف الخدمة (تُستدعى من HTML)
 */
function deleteService(serviceId, serviceName, serviceCategory, serviceDetails = {}) {
    if (serviceDeleteHandler) {
        serviceDeleteHandler.show(serviceId, serviceName, serviceCategory, serviceDetails);
    } else {
        console.error('❌ ServiceDeleteHandler not initialized');
    }
}
