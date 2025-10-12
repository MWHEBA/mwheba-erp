/**
 * main.js - ملف التهيئة الرئيسي لنظام التسعير
 */

// التأكد من تحميل جميع الملفات المطلوبة
document.addEventListener('DOMContentLoaded', function() {    
    // التحقق من وجود كائن النظام
    if (typeof PricingSystem === 'undefined') {
        console.error('خطأ: كائن نظام التسعير غير معرف');
        return;
    }
    
    // التحقق من وجود الوحدات الرئيسية
    const requiredModules = [
        { name: 'API', errorMsg: 'وحدة خدمات API غير متوفرة' },
        { name: 'Paper', errorMsg: 'وحدة معالجة الورق غير متوفرة' },
        { name: 'Print', errorMsg: 'وحدة معالجة الطباعة غير متوفرة' },
        { name: 'Montage', errorMsg: 'وحدة معالجة المونتاج غير متوفرة' },
        { name: 'CTP', errorMsg: 'وحدة معالجة الألواح غير متوفرة' },
        { name: 'Finishing', errorMsg: 'وحدة معالجة خدمات ما بعد الطباعة غير متوفرة' },
        { name: 'Pricing', errorMsg: 'وحدة حسابات التسعير غير متوفرة' },
        { name: 'Session', errorMsg: 'وحدة معالجة بيانات الجلسة غير متوفرة' },
        { name: 'UI', errorMsg: 'وحدة واجهة المستخدم غير متوفرة' },
        { name: 'EventBus', errorMsg: 'وحدة ناقل الأحداث غير متوفرة' }
    ];
    
    let missingModules = false;
    requiredModules.forEach(module => {
        if (typeof PricingSystem[module.name] === 'undefined') {
            console.error('خطأ:', module.errorMsg);
            missingModules = true;
        }
    });
    
    if (missingModules) {
        console.error('يرجى التأكد من تحميل جميع ملفات JavaScript المطلوبة');
        // إضافة رسالة خطأ للمستخدم
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger';
        errorDiv.innerHTML = '<strong>خطأ:</strong> فشل تحميل بعض وحدات نظام التسعير. يرجى تحديث الصفحة أو الاتصال بمسؤول النظام.';
        document.body.insertBefore(errorDiv, document.body.firstChild);
        return;
    }
    
    // بدء تهيئة النظام
    try {
        // تهيئة نظام ناقل الأحداث أولاً
        if (PricingSystem.EventBus && typeof PricingSystem.EventBus.init === 'function') {
            PricingSystem.EventBus.init();
        }
        
        // ثم تهيئة بقية النظام
        PricingSystem.init();
        
        // تهيئة واجهة المستخدم بشكل مباشر
        if (PricingSystem.UI && typeof PricingSystem.UI.initUI === 'function') {
            PricingSystem.UI.initUI();
        }
        
        // إعداد أقسام النموذج
        setupSections();
        
        // تهيئة معالجات أحداث وحدات النظام
        initializeModuleEventHandlers();
        
        // إعداد الحفظ التلقائي للنموذج
        if (PricingSystem.Session && typeof PricingSystem.Session.setupSessionEventHandlers === 'function') {
            PricingSystem.Session.setupSessionEventHandlers();
        }
        
        // إعداد مستمعات الأحداث لجميع حقول النموذج إذا كان ناقل الأحداث متاحًا
        if (PricingSystem.EventBus && typeof PricingSystem.EventBus.setupFormListeners === 'function') {
            PricingSystem.EventBus.setupFormListeners();
        }
        
        // استدعاء دالة حساب تكلفة الطباعة بعد تهيئة النظام
        setTimeout(function() {            
            // التحقق من قيمة الكمية وتعيينها إذا كانت فارغة
            const quantityInput = document.getElementById('id_quantity');
            if (quantityInput) {
                const currentValue = parseInt(quantityInput.value) || 0;
                if (currentValue <= 0) {
                    quantityInput.value = '1000';
                    
                    // إطلاق حدث تغيير الكمية عبر ناقل الأحداث
                    if (PricingSystem.EventBus) {
                        PricingSystem.EventBus.fieldChanged('id_quantity', '1000', true);
                    }
                }
            }
            
            // تحديث إجمالي التكلفة عبر ناقل الأحداث
            if (PricingSystem.EventBus) {
                PricingSystem.EventBus.emit('pricing:update', { initialLoad: true });
                
                // إطلاق حدث تحميل النموذج
                PricingSystem.EventBus.emit('form:loaded', { timestamp: new Date().getTime() });
            } else {
                // استخدام الطريقة القديمة إذا لم يكن ناقل الأحداث متاحًا
                if (PricingSystem.Print && typeof PricingSystem.Print.calculatePressCost === 'function') {
                    PricingSystem.Print.calculatePressCost();
                }
                
                if (PricingSystem.Pricing && typeof PricingSystem.Pricing.calculateCost === 'function') {
                    PricingSystem.Pricing.calculateCost();
                }
            }
        }, 1500);
        
        // إضافة مستمع لأحداث تغيير القسم
        document.addEventListener('section:changed', function(event) {
            const fromSection = event.detail.from;
            const toSection = event.detail.to;
                        
            // تحديث التكلفة الإجمالية عند الانتقال إلى قسم التسعير
            if (toSection === 'section-4') {
                // استخدام ناقل الأحداث لتحديث التكلفة
                if (PricingSystem.EventBus) {
                    PricingSystem.EventBus.emit('pricing:update', { 
                        sectionChange: true,
                        toSection: toSection
                    });
                } else {
                    // استخدام الطريقة القديمة إذا لم يكن ناقل الأحداث متاحًا
                    if (PricingSystem.Pricing && typeof PricingSystem.Pricing.updateDesignCost === 'function') {
                        PricingSystem.Pricing.updateDesignCost();
                    }
                    
                    if (PricingSystem.Paper && typeof PricingSystem.Paper.updateTotalPaperCost === 'function') {
                        PricingSystem.Paper.updateTotalPaperCost();
                    }
                    
                    setTimeout(function() {
                        if (PricingSystem.Pricing && typeof PricingSystem.Pricing.calculateCost === 'function') {
                            PricingSystem.Pricing.calculateCost();
                        }
                    }, 300);
                }
            }
        });
        
        // إضافة معالج لزر إعادة ضبط النموذج
        const resetButton = document.getElementById('reset-form');
        if (resetButton) {
            resetButton.addEventListener('click', function(event) {
                event.preventDefault();
                
                // تأكيد إعادة الضبط
                if (confirm('هل أنت متأكد من رغبتك في إعادة ضبط النموذج؟ سيتم مسح جميع البيانات المدخلة.')) {
                    // مسح بيانات الجلسة
                    PricingSystem.Session.clearSessionData();
                    
                    // إعادة تحميل الصفحة
                    window.location.reload();
                }
            });
        }
        
        // إضافة معالج لزر حفظ النموذج
        const saveButton = document.getElementById('save-form');
        if (saveButton) {
            saveButton.addEventListener('click', function(event) {
                event.preventDefault();
                
                // حفظ بيانات النموذج
                PricingSystem.Session.saveFormData();
                
                // إظهار رسالة تأكيد
                alert('تم حفظ بيانات النموذج بنجاح.');
            });
        }
        
        // إضافة معالج لزر طباعة النموذج
        const printButton = document.getElementById('print-form');
        if (printButton) {
            printButton.addEventListener('click', function(event) {
                event.preventDefault();
                
                // حفظ بيانات النموذج قبل الطباعة
                PricingSystem.Session.saveFormData();
                
                // طباعة الصفحة
                window.print();
            });
        }
        
        // إضافة معالج لزر إرسال النموذج
        const submitButton = document.getElementById('submit-form');
        if (submitButton) {
            submitButton.addEventListener('click', function(event) {
                event.preventDefault();
                
                // التحقق من صحة النموذج
                if (validateForm()) {
                    // إرسال النموذج
                    document.getElementById('pricing-form').submit();
                }
            });
        }
        
        /**
         * دالة للتحقق من صحة النموذج قبل الإرسال
         * @returns {boolean} هل النموذج صحيح
         */
        function validateForm() {
            // التحقق من وجود الحقول المطلوبة
            const requiredFields = [
                { id: 'id_client', name: 'العميل' },
                { id: 'id_project_name', name: 'اسم المشروع' },
                { id: 'id_quantity', name: 'الكمية' }
            ];
            
            let isValid = true;
            let errorMessage = 'يرجى ملء الحقول المطلوبة التالية:\n';
            
            requiredFields.forEach(field => {
                const element = document.getElementById(field.id);
                if (!element || !element.value) {
                    errorMessage += `- ${field.name}\n`;
                    isValid = false;
                }
            });
            
            if (!isValid) {
                alert(errorMessage);
            }
            
            return isValid;
        }
        
    } catch (error) {
        console.error('خطأ أثناء تهيئة نظام التسعير:', error);
        // إضافة رسالة خطأ للمستخدم
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger';
        errorDiv.innerHTML = '<strong>خطأ:</strong> حدث خطأ أثناء تهيئة نظام التسعير. يرجى تحديث الصفحة أو الاتصال بمسؤول النظام.';
        document.body.insertBefore(errorDiv, document.body.firstChild);
    }
});
/**
 * دالة تهيئة معالجات أحداث وحدات النظام
 */
function initializeModuleEventHandlers() {
    // تهيئة معالجات أحداث الطباعة
    if (PricingSystem.Press && typeof PricingSystem.Press.setupEventHandlers === 'function') {
        PricingSystem.Press.setupEventHandlers();
    }
    
    // تهيئة معالجات أحداث المكابس
    if (PricingSystem.Press && typeof PricingSystem.Press.init === 'function') {
        PricingSystem.Press.init();
    }
    
    // تهيئة معالجات أحداث الورق
    if (PricingSystem.Paper && typeof PricingSystem.Paper.setupEventHandlers === 'function') {
        PricingSystem.Paper.setupEventHandlers();
    }
    if (PricingSystem.CTP && typeof PricingSystem.CTP.setupEventHandlers === 'function') {
        PricingSystem.CTP.setupEventHandlers();
    }
    
    // تهيئة حقول الزنكات
    if (PricingSystem.CTP && typeof PricingSystem.CTP.init === 'function') {
        PricingSystem.CTP.init();
    }
    
    // تهيئة معالجات أحداث المونتاج
    if (PricingSystem.Montage && typeof PricingSystem.Montage.setupEventHandlers === 'function') {
        PricingSystem.Montage.setupEventHandlers();
    }
    
    // تهيئة معالجات أحداث خدمات ما بعد الطباعة
    if (PricingSystem.Finishing && typeof PricingSystem.Finishing.setupEventHandlers === 'function') {
        PricingSystem.Finishing.setupEventHandlers();
    }
    
    // تهيئة معالجات أحداث التسعير
    if (PricingSystem.Pricing && typeof PricingSystem.Pricing.setupEventHandlers === 'function') {
        PricingSystem.Pricing.setupEventHandlers();
    }
    
    // تهيئة تبعيات الحقول في نظام ناقل الأحداث بعد تهيئة جميع الوحدات
    // هذا يضمن أن جميع الوحدات قد سجلت معالجات الأحداث الخاصة بها قبل إعداد التبعيات
    if (PricingSystem.EventBus && typeof PricingSystem.EventBus.initDependencies === 'function') {
        // تهيئة تبعيات الحقول لتمكين التحديث التلقائي للحقول المترابطة
        PricingSystem.EventBus.initDependencies();
        
        // إطلاق حدث لإعلام جميع الوحدات بأن نظام تبعيات الحقول قد تم تهيئته
        PricingSystem.EventBus.emit('dependencies:initialized', {
            timestamp: new Date().getTime()
        });
        
    }
}

// دالة إعداد أقسام النموذج
function setupSections() {    
    // إظهار القسم الأول وإخفاء باقي الأقسام
    const sections = ['section-1', 'section-2', 'section-3', 'section-4'];
    
    sections.forEach((sectionId, index) => {
        const section = document.getElementById(sectionId);
        if (section) {
            if (index === 0) {
                // إظهار القسم الأول
                section.classList.remove('section-hidden');
                section.style.display = 'block';
            } else {
                // إخفاء باقي الأقسام
                section.classList.add('section-hidden');
                section.style.display = 'none';
            }
        } else {
            console.error(`القسم ${sectionId} غير موجود في الصفحة`);
        }
    });
    
    // تهيئة مؤشر الخطوات
    const steps = ['step-1', 'step-2', 'step-3', 'step-4'];
    steps.forEach((stepId, index) => {
        const step = document.getElementById(stepId);
        if (step) {
            if (index === 0) {
                step.className = 'step active clickable';
            } else {
                step.className = 'step clickable';
            }
        } else {
            console.error(`الخطوة ${stepId} غير موجودة في الصفحة`);
        }
    });
    
    // التحقق من حالة المحتوى الداخلي وتحديث الواجهة
    const hasInternalContent = document.getElementById('id_has_internal_content');
    if (hasInternalContent && typeof PricingSystem.updateSectionsBasedOnInternalContent === 'function') {
        PricingSystem.updateSectionsBasedOnInternalContent(hasInternalContent.checked);
    }
    
} 