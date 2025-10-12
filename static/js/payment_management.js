/**
 * إدارة الدفعات - JavaScript للتفاعل مع واجهة المستخدم
 */

class PaymentManager {
    constructor() {
        this.csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        this.initializeEventListeners();
    }

    initializeEventListeners() {
        // تهيئة tooltips
        this.initializeTooltips();
        
        // تهيئة modals
        this.initializeModals();
    }

    initializeTooltips() {
        // تفعيل Bootstrap tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }

    initializeModals() {
        // إنشاء modals ديناميكية إذا لم تكن موجودة
        if (!document.getElementById('paymentEditModal')) {
            this.createEditModal();
        }
        
        if (!document.getElementById('paymentHistoryModal')) {
            this.createHistoryModal();
        }
        
        if (!document.getElementById('confirmationModal')) {
            this.createConfirmationModal();
        }
    }

    createEditModal() {
        const modalHtml = `
            <div class="modal fade" id="paymentEditModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-edit me-2"></i>
                                تعديل الدفعة
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div id="editPaymentContent">
                                <div class="text-center">
                                    <div class="spinner-border text-primary" role="status">
                                        <span class="visually-hidden">جاري التحميل...</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">إلغاء</button>
                            <button type="button" class="btn btn-primary" id="savePaymentBtn">
                                <i class="fas fa-save me-1"></i>
                                حفظ التغييرات
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    createHistoryModal() {
        const modalHtml = `
            <div class="modal fade" id="paymentHistoryModal" tabindex="-1">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-history me-2"></i>
                                تاريخ تغييرات الدفعة
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div id="paymentHistoryContent">
                                <div class="text-center">
                                    <div class="spinner-border text-primary" role="status">
                                        <span class="visually-hidden">جاري التحميل...</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">إغلاق</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    createConfirmationModal() {
        const modalHtml = `
            <div class="modal fade" id="confirmationModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-exclamation-triangle me-2 text-warning"></i>
                                تأكيد العملية
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div id="confirmationMessage"></div>
                            <div class="mt-3">
                                <label for="confirmationReason" class="form-label">سبب العملية (اختياري):</label>
                                <textarea class="form-control" id="confirmationReason" rows="3" 
                                         placeholder="اكتب سبب هذه العملية..."></textarea>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">إلغاء</button>
                            <button type="button" class="btn btn-danger" id="confirmActionBtn">
                                <i class="fas fa-check me-1"></i>
                                تأكيد
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }

    // تعديل الدفعة
    async editPayment(paymentId) {
        try {
            const modal = new bootstrap.Modal(document.getElementById('paymentEditModal'));
            const content = document.getElementById('editPaymentContent');
            
            // إظهار المودال مع مؤشر التحميل
            modal.show();
            
            // جلب نموذج التعديل
            const response = await fetch(`/financial/payments/${paymentId}/edit/`, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                }
            });
            
            if (response.ok) {
                const html = await response.text();
                content.innerHTML = html;
                
                // ربط حدث الحفظ
                document.getElementById('savePaymentBtn').onclick = () => {
                    this.savePaymentChanges(paymentId);
                };
            } else {
                content.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        خطأ في تحميل نموذج التعديل
                    </div>
                `;
            }
        } catch (error) {
            console.error('خطأ في تعديل الدفعة:', error);
            this.showAlert('خطأ في تحميل نموذج التعديل', 'danger');
        }
    }

    // حفظ تغييرات الدفعة
    async savePaymentChanges(paymentId) {
        try {
            const form = document.querySelector('#paymentEditModal form');
            const formData = new FormData(form);
            
            const response = await fetch(`/financial/payments/${paymentId}/edit/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.csrfToken,
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: formData
            });
            
            const result = await response.json();
            
            if (result.success) {
                // إغلاق المودال
                bootstrap.Modal.getInstance(document.getElementById('paymentEditModal')).hide();
                
                // إظهار رسالة نجاح
                this.showAlert(result.message, 'success');
                
                // إعادة تحميل الصفحة أو تحديث البيانات
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            } else {
                // إظهار أخطاء النموذج
                this.displayFormErrors(result.errors);
            }
        } catch (error) {
            console.error('خطأ في حفظ التغييرات:', error);
            this.showAlert('خطأ في حفظ التغييرات', 'danger');
        }
    }

    // إلغاء ترحيل الدفعة
    async unpostPayment(paymentId) {
        const message = `
            <div class="alert alert-warning">
                <h6><i class="fas fa-exclamation-triangle me-2"></i>تحذير مهم</h6>
                <p>سيتم إلغاء ترحيل هذه الدفعة وحذف القيد المحاسبي المرتبط بها.</p>
                <p><strong>هذه العملية لا يمكن التراجع عنها!</strong></p>
            </div>
            <p>هل أنت متأكد من أنك تريد إلغاء ترحيل هذه الدفعة؟</p>
        `;
        
        this.showConfirmation(message, async (reason) => {
            try {
                const response = await fetch(`/financial/payments/${paymentId}/unpost/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body: JSON.stringify({ reason: reason })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    this.showAlert(result.message, 'success');
                    setTimeout(() => {
                        window.location.reload();
                    }, 1500);
                } else {
                    this.showAlert(result.message, 'danger');
                }
            } catch (error) {
                console.error('خطأ في إلغاء الترحيل:', error);
                this.showAlert('خطأ في إلغاء ترحيل الدفعة', 'danger');
            }
        });
    }

    // عرض تاريخ الدفعة
    async showPaymentHistory(paymentId) {
        try {
            const modal = new bootstrap.Modal(document.getElementById('paymentHistoryModal'));
            const content = document.getElementById('paymentHistoryContent');
            
            // إظهار المودال مع مؤشر التحميل
            modal.show();
            
            // جلب تاريخ الدفعة
            const response = await fetch(`/financial/payments/${paymentId}/history/`, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                }
            });
            
            if (response.ok) {
                const html = await response.text();
                content.innerHTML = html;
            } else {
                content.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        خطأ في تحميل تاريخ الدفعة
                    </div>
                `;
            }
        } catch (error) {
            console.error('خطأ في عرض التاريخ:', error);
            this.showAlert('خطأ في تحميل تاريخ الدفعة', 'danger');
        }
    }

    // حذف الدفعة
    async deletePayment(paymentId) {
        const message = `
            <div class="alert alert-danger">
                <h6><i class="fas fa-trash me-2"></i>حذف الدفعة</h6>
                <p>سيتم حذف هذه الدفعة نهائياً من النظام.</p>
                <p><strong>هذه العملية لا يمكن التراجع عنها!</strong></p>
            </div>
            <p>هل أنت متأكد من أنك تريد حذف هذه الدفعة؟</p>
        `;
        
        this.showConfirmation(message, async (reason) => {
            try {
                const response = await fetch(`/financial/payments/${paymentId}/delete/`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.csrfToken,
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body: JSON.stringify({ reason: reason })
                });
                
                const result = await response.json();
                
                if (result.success) {
                    this.showAlert(result.message, 'success');
                    setTimeout(() => {
                        window.location.reload();
                    }, 1500);
                } else {
                    this.showAlert(result.message, 'danger');
                }
            } catch (error) {
                console.error('خطأ في حذف الدفعة:', error);
                this.showAlert('خطأ في حذف الدفعة', 'danger');
            }
        });
    }

    // إظهار مودال التأكيد
    showConfirmation(message, onConfirm) {
        const modal = new bootstrap.Modal(document.getElementById('confirmationModal'));
        const messageDiv = document.getElementById('confirmationMessage');
        const reasonTextarea = document.getElementById('confirmationReason');
        const confirmBtn = document.getElementById('confirmActionBtn');
        
        messageDiv.innerHTML = message;
        reasonTextarea.value = '';
        
        // ربط حدث التأكيد
        confirmBtn.onclick = () => {
            const reason = reasonTextarea.value.trim();
            modal.hide();
            onConfirm(reason);
        };
        
        modal.show();
    }

    // إظهار رسالة تنبيه
    showAlert(message, type = 'info') {
        // إنشاء alert ديناميكي
        const alertHtml = `
            <div class="alert alert-${type} alert-dismissible fade show position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999; min-width: 300px;">
                <i class="fas fa-${this.getAlertIcon(type)} me-2"></i>
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', alertHtml);
        
        // إزالة التنبيه تلقائياً بعد 5 ثوان
        setTimeout(() => {
            const alerts = document.querySelectorAll('.alert.position-fixed');
            alerts.forEach(alert => {
                if (alert.parentNode) {
                    alert.remove();
                }
            });
        }, 5000);
    }

    getAlertIcon(type) {
        const icons = {
            'success': 'check-circle',
            'danger': 'exclamation-triangle',
            'warning': 'exclamation-triangle',
            'info': 'info-circle'
        };
        return icons[type] || 'info-circle';
    }

    // عرض أخطاء النموذج
    displayFormErrors(errors) {
        // إزالة أخطاء سابقة
        document.querySelectorAll('.is-invalid').forEach(el => {
            el.classList.remove('is-invalid');
        });
        document.querySelectorAll('.invalid-feedback').forEach(el => {
            el.remove();
        });
        
        // إضافة أخطاء جديدة
        for (const [field, messages] of Object.entries(errors)) {
            const input = document.querySelector(`[name="${field}"]`);
            if (input) {
                input.classList.add('is-invalid');
                
                const feedback = document.createElement('div');
                feedback.className = 'invalid-feedback';
                feedback.textContent = messages.join(', ');
                
                input.parentNode.appendChild(feedback);
            }
        }
    }
}

// تهيئة مدير الدفعات عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    window.paymentManager = new PaymentManager();
});

// دوال عامة للاستخدام في templates
function editPayment(paymentId) {
    window.paymentManager.editPayment(paymentId);
}

function unpostPayment(paymentId) {
    window.paymentManager.unpostPayment(paymentId);
}

function showPaymentHistory(paymentId) {
    window.paymentManager.showPaymentHistory(paymentId);
}

function deletePayment(paymentId) {
    window.paymentManager.deletePayment(paymentId);
}
