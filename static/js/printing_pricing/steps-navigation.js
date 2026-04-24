/**
 * نظام التنقل بين الخطوات للتسعير الجديد
 * نسخة منظفة ومبسطة
 */

const PrintingPricingSteps = {
    // المتغيرات الأساسية
    currentStep: 1,
    totalSteps: 4,
    steps: null,
    sections: null,
    nextButtons: null,
    prevButtons: null,

    /**
     * تهيئة نظام الخطوات
     */
    init: function() {
        this.initElements();
        this.bindEvents();
        this.showSection(1);
    },

    /**
     * تهيئة العناصر
     */
    initElements: function() {
        this.steps = document.querySelectorAll('.step');
        this.sections = document.querySelectorAll('.form-section');
        this.nextButtons = document.querySelectorAll('.btn-next');
        this.prevButtons = document.querySelectorAll('.btn-prev');
        
        if (this.steps.length === 0) {
            return false;
        }
        return true;
    },

    /**
     * ربط الأحداث
     */
    bindEvents: function() {
        // أحداث النقر على مؤشر الخطوات
        this.steps.forEach((step, index) => {
            step.addEventListener('click', (e) => {
                e.preventDefault();
                const targetStep = index + 1;
                this.navigateToStep(targetStep);
            });
        });

        // أحداث أزرار التالي
        this.nextButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                this.nextStep();
            });
        });

        // أحداث أزرار السابق
        this.prevButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                this.prevStep();
            });
        });
    },

    /**
     * الانتقال لخطوة محددة
     */
    navigateToStep: function(stepNumber) {
        if (stepNumber < 1 || stepNumber > this.totalSteps) {
            return;
        }

        if (stepNumber <= this.currentStep || this.validateCurrentSection()) {
            this.showSection(stepNumber);
        }
    },

    /**
     * الانتقال للخطوة التالية
     */
    nextStep: function() {
        if (this.validateCurrentSection() && this.currentStep < this.totalSteps) {
            this.showSection(this.currentStep + 1);
        }
    },

    /**
     * الانتقال للخطوة السابقة
     */
    prevStep: function() {
        if (this.currentStep > 1) {
            this.showSection(this.currentStep - 1);
        }
    },

    /**
     * إظهار قسم معين
     */
    showSection: function(stepNumber) {
        // إخفاء جميع الأقسام
        this.sections.forEach((section, index) => {
            section.classList.remove('active');
            section.style.display = 'none';
        });

        // إظهار القسم المطلوب
        const targetSection = document.querySelector(`[data-section="${stepNumber}"]`);
        
        if (targetSection) {
            targetSection.classList.add('active');
            targetSection.style.display = 'block';
        }

        // تحديث مؤشر الخطوات
        this.updateStepIndicator(stepNumber);

        // تحديث الخطوة الحالية
        this.currentStep = stepNumber;

        // تمرير سلس لأعلى الصفحة
        window.scrollTo({ top: 0, behavior: 'smooth' });
    },

    /**
     * تحديث مؤشر الخطوات
     */
    updateStepIndicator: function(activeStep) {
        this.steps.forEach((step, index) => {
            const stepNumber = index + 1;
            step.classList.remove('active', 'completed');

            if (stepNumber === activeStep) {
                step.classList.add('active');
            } else if (stepNumber < activeStep) {
                step.classList.add('completed');
            }
        });
    },

    /**
     * التحقق من صحة القسم الحالي
     */
    validateCurrentSection: function() {
        // استخدام نظام التحقق من field-handlers إذا كان متوفراً
        if (typeof PrintingFieldHandlers !== 'undefined' && PrintingFieldHandlers.validateSection) {
            return PrintingFieldHandlers.validateSection(this.currentStep);
        }
        
        // النظام التقليدي كـ fallback
        const currentSection = document.querySelector(`[data-section="${this.currentStep}"]`) || document.querySelector('form');
        if (!currentSection) {
            return true;
        }

        const requiredFields = currentSection.querySelectorAll('input[required], select[required], textarea[required]');
        let isValid = true;

        requiredFields.forEach(field => {
            const fieldValue = field.value ? field.value.trim() : '';
            
            if (!fieldValue) {
                field.classList.add('is-invalid');
                isValid = false;
            } else {
                field.classList.remove('is-invalid');
            }
        });

        return isValid;
    }
};


/**
 * معالج مفتاح Enter للانتقال للصفحة التالية
 */
function setupEnterKeyNavigation() {
    // معالج مفتاح Enter العام
    document.addEventListener('keydown', function(event) {
        // التحقق من أن المفتاح المضغوط هو Enter
        if (event.key === 'Enter' || event.keyCode === 13) {
            // التحقق من أن العنصر المركز عليه ليس textarea أو button
            const activeElement = document.activeElement;
            const tagName = activeElement.tagName.toLowerCase();
            
            // السماح بـ Enter في textarea و button
            if (tagName === 'textarea' || tagName === 'button') {
                return;
            }
            
            // منع السلوك الافتراضي (إرسال النموذج)
            event.preventDefault();
            event.stopPropagation();
            
            // الانتقال للصفحة التالية
            if (typeof PrintingPricingSteps !== 'undefined' && PrintingPricingSteps.nextStep) {
                PrintingPricingSteps.nextStep();
            } else {
                // بديل إذا لم يكن نظام الخطوات متوفراً
                const nextButton = document.querySelector('.btn-next:not([style*="display: none"])');
                if (nextButton) {
                    nextButton.click();
                }
            }
        }
    });
    
    // منع إرسال النموذج عند الضغط على Enter في الحقول
    const formInputs = document.querySelectorAll('input, select');
    formInputs.forEach(input => {
        input.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' || event.keyCode === 13) {
                // منع إرسال النموذج
                event.preventDefault();
                
                // الانتقال للحقل التالي أو الصفحة التالية
                const nextInput = getNextInput(input);
                if (nextInput) {
                    nextInput.focus();
                } else {
                    // إذا لم يوجد حقل تالي، انتقل للصفحة التالية
                    if (typeof PrintingPricingSteps !== 'undefined' && PrintingPricingSteps.nextStep) {
                        PrintingPricingSteps.nextStep();
                    }
                }
            }
        });
    });
}

/**
 * الحصول على الحقل التالي في النموذج
 */
function getNextInput(currentInput) {
    const allInputs = Array.from(document.querySelectorAll('input:not([type="hidden"]), select, textarea'));
    const visibleInputs = allInputs.filter(input => {
        const style = window.getComputedStyle(input);
        const parentStyle = window.getComputedStyle(input.parentElement);
        return style.display !== 'none' && 
               style.visibility !== 'hidden' && 
               parentStyle.display !== 'none' &&
               !input.disabled &&
               !input.readOnly;
    });
    
    const currentIndex = visibleInputs.indexOf(currentInput);
    if (currentIndex >= 0 && currentIndex < visibleInputs.length - 1) {
        return visibleInputs[currentIndex + 1];
    }
    
    return null;
}

/**
 * تهيئة تلقائية للنظام عند تحميل الصفحة
 */
document.addEventListener('DOMContentLoaded', function() {
    // تهيئة نظام الخطوات
    if (PrintingPricingSteps.initElements()) {
        PrintingPricingSteps.init();
    }
    
    // تهيئة معالج مفتاح Enter
    setupEnterKeyNavigation();
});

// تصدير الكائن للاستخدام العام
window.PrintingPricingSteps = PrintingPricingSteps;
