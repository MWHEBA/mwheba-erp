/**
 * ui-handlers.js - دالات معالجة واجهة المستخدم
 */

// تعريف كائن عام للمشروع إذا لم يكن موجودًا
window.PricingSystem = window.PricingSystem || {};

// تعريف وحدة معالجة واجهة المستخدم
PricingSystem.UI = {
    /**
     * تهيئة معالجات واجهة المستخدم
     */
    initUI: function() {
        // إعداد معالجات أحداث التنقل بين الأقسام
        this.setupSectionNavigation();
        
        // إعداد معالجات أحداث المحتوى الداخلي
        this.setupInternalContentHandlers();
        
        // إعداد معالجات أحداث حقول المقاس المخصص
        this.setupCustomSizeFields();
        
        // إعداد معالجات أحداث حقول المقاس المفتوح
        this.setupOpenSizeFields();
        
        // إعداد معالجات أحداث نوع الطلب
        this.setupOrderTypeFields();
        
        // تسجيل معالجات الأحداث مع ناقل الأحداث إذا كان متاحًا
        if (PricingSystem.EventBus) {
            this.registerEventHandlers();
        }
    },
    
    /**
     * تسجيل معالجات الأحداث مع ناقل الأحداث
     */
    registerEventHandlers: function() {
        // الاستماع لأحداث تغيير القسم
        PricingSystem.EventBus.on('section:changed', (data) => {
            // تحديث التكلفة الإجمالية عند الانتقال إلى قسم التسعير
            if (data.to === 'section-4') {
                PricingSystem.EventBus.emit('pricing:update', { 
                    sectionChange: true,
                    toSection: data.to
                });
            }
        });
        
        // الاستماع لتغييرات المحتوى الداخلي
        PricingSystem.EventBus.on('field:id_has_internal_content:changed', (data) => {
            // تحديث الأقسام بناءً على حالة المحتوى الداخلي
            if (typeof PricingSystem.updateSectionsBasedOnInternalContent === 'function') {
                PricingSystem.updateSectionsBasedOnInternalContent(data.value);
            }
        });
    },
    
    /**
     * إعداد معالجات أحداث التنقل بين الأقسام
     */
    setupSectionNavigation: function() {
        // تعريف الأقسام والخطوات
        const sections = ['section-1', 'section-2', 'section-3', 'section-4'];
        const steps = ['step-1', 'step-2', 'step-3', 'step-4'];
        
        // التحقق من وجود جميع الأقسام والخطوات
        let allElementsExist = true;
        sections.forEach(section => {
            if (!document.getElementById(section)) {
                console.error(`القسم ${section} غير موجود في الصفحة`);
                allElementsExist = false;
            }
        });
        
        steps.forEach(step => {
            if (!document.getElementById(step)) {
                console.error(`الخطوة ${step} غير موجودة في الصفحة`);
                allElementsExist = false;
            }
        });
        
        if (!allElementsExist) {
            console.error('بعض عناصر التنقل غير موجودة، قد لا تعمل بعض الوظائف بشكل صحيح');
        }
        
        // إضافة معالجات الأحداث لمؤشرات الخطوات
        steps.forEach((stepId, index) => {
            const stepElement = document.getElementById(stepId);
            if (stepElement) {
                stepElement.addEventListener('click', () => {
                    const targetSection = sections[index];
                    
                    // تحقق مما إذا كان قسم المحتوى الداخلي غير ضروري
                    const hasInternalContent = document.getElementById('id_has_internal_content');
                    if (targetSection === 'section-3' && (!hasInternalContent || !hasInternalContent.checked)) {
                        this.showSection('section-4'); // انتقل إلى قسم التسعير مباشرة
                        return;
                    }
                
                    this.showSection(targetSection);
                });
            }
        });
        
        // إضافة معالجات الأحداث لأزرار التنقل
        const navigationButtons = {
            'to-section-1': 'section-1',
            'to-section-2': 'section-2',
            'to-section-3': 'section-3',
            'to-section-4': 'section-4'
        };
        
        Object.keys(navigationButtons).forEach(buttonId => {
            const button = document.getElementById(buttonId);
            if (button) {
                button.addEventListener('click', () => {
                    const targetSection = navigationButtons[buttonId];
                    
                    // تحقق مما إذا كان قسم المحتوى الداخلي غير ضروري
                    const hasInternalContent = document.getElementById('id_has_internal_content');
                    if (targetSection === 'section-3' && (!hasInternalContent || !hasInternalContent.checked)) {
                        this.showSection('section-4'); // انتقل إلى قسم التسعير مباشرة
                        return;
                    }
                    
                    this.showSection(targetSection);
                });
            }
        });
    },
    
    /**
     * إظهار قسم معين وإخفاء باقي الأقسام
     * @param {string} sectionId - معرف القسم المراد إظهاره
     */
    showSection: function(sectionId) {
        // تعريف الأقسام والخطوات
        const sections = ['section-1', 'section-2', 'section-3', 'section-4'];
        const steps = ['step-1', 'step-2', 'step-3', 'step-4'];
        
        // التحقق من وجود القسم المستهدف
        const targetSection = document.getElementById(sectionId);
        if (!targetSection) {
            console.error(`القسم المستهدف ${sectionId} غير موجود`);
            return;
        }
        
        // الحصول على القسم الحالي قبل إخفاء الأقسام
        const currentSection = sections.find(s => {
            const el = document.getElementById(s);
            return el && !el.classList.contains('section-hidden');
        });
        
        // إخفاء جميع الأقسام
        sections.forEach(id => {
            const section = document.getElementById(id);
            if (section) {
                section.classList.add('section-hidden');
                section.style.display = 'none';
            } else {
                console.error(`القسم ${id} غير موجود ولا يمكن إخفاؤه`);
            }
        });
        
        // إظهار القسم المحدد
        targetSection.classList.remove('section-hidden');
        targetSection.style.display = 'block';
                
        // تحديث مؤشر الخطوات
        const currentIndex = sections.indexOf(sectionId);
        if (currentIndex !== -1) {
            steps.forEach((stepId, index) => {
                const stepEl = document.getElementById(stepId);
                if (!stepEl) return;
                
                if (index < currentIndex) {
                    stepEl.className = 'step completed clickable';
                } else if (index === currentIndex) {
                    stepEl.className = 'step active clickable';
                } else {
                    stepEl.className = 'step clickable';
                }
            });
        }
        
        // إطلاق حدث تغيير القسم
        const eventData = { 
            from: currentSection,
            to: sectionId
        };
        
        // استخدام ناقل الأحداث إذا كان متاحًا
        if (PricingSystem.EventBus) {
            PricingSystem.EventBus.emit('section:changed', eventData);
        } else {
            // استخدام CustomEvent كاحتياطي
            const event = new CustomEvent('section:changed', {
                detail: eventData
            });
            document.dispatchEvent(event);
        }
    },
    
    /**
     * إعداد معالجات أحداث المحتوى الداخلي
     */
    setupInternalContentHandlers: function() {
        const hasInternalContent = document.getElementById('id_has_internal_content');
        const internalFields = document.getElementById('internal-fields');
        const internalContentSection = document.getElementById('internal-content-section');
        const step3Element = document.getElementById('step-3');
        const section3Element = document.getElementById('section-3');
        const section2HeaderElement = document.querySelector('#section-2 .section-header h4');
        const step2Element = document.getElementById('step-2');
        
        // التحقق من وجود العناصر المطلوبة
        if (!hasInternalContent) {
            console.error('عنصر id_has_internal_content غير موجود');
            return;
        }
        
        // دالة تحديث الأقسام بناءً على حالة المحتوى الداخلي
        const updateSectionsBasedOnInternalContent = (hasInternal) => {
            
            // إظهار/إخفاء حقول المحتوى الداخلي في القسم الأول
            if (internalFields) {
                internalFields.style.display = hasInternal ? 'block' : 'none';
            }
            
            if (internalContentSection) {
                internalContentSection.style.display = hasInternal ? 'block' : 'none';
            }
            
            // إظهار/إخفاء خطوة المحتوى الداخلي
            if (step3Element) {
                step3Element.style.display = hasInternal ? 'block' : 'none';
            }
            
            if (section3Element) {
                section3Element.style.display = hasInternal ? 'block' : 'none';
            }
            
            // تغيير عنوان القسم الثاني
            if (section2HeaderElement) {
                if (hasInternal) {
                    section2HeaderElement.innerHTML = '🖨️ تفاصيل الغلاف';
                } else {
                    section2HeaderElement.innerHTML = '🖨️ تفاصيل الطباعة';
                }
            }
            
            if (step2Element) {
                if (hasInternal) {
                    step2Element.textContent = 'تفاصيل الغلاف';
                } else {
                    step2Element.textContent = 'تفاصيل الطباعة';
                }
            }
            
            // تحديث معالجات التنقل
            this.updateNavigationForInternalContent(hasInternal);
        };
        
        // إضافة معالج حدث للـ checkbox
        hasInternalContent.addEventListener('change', function() {
            updateSectionsBasedOnInternalContent(this.checked);
        });
        
        // تحديث الواجهة عند التحميل
        updateSectionsBasedOnInternalContent(hasInternalContent.checked);
        
        // حفظ المرجع للاستخدام في دوال أخرى
        this.updateSectionsBasedOnInternalContent = updateSectionsBasedOnInternalContent;
    },
    
    /**
     * تحديث معالجات التنقل للمحتوى الداخلي
     */
    updateNavigationForInternalContent: function(hasInternal) {
        const hasInternalContent = document.getElementById('id_has_internal_content');
        
        // تحديث معالجات الأزرار والخطوات لتخطي القسم الثالث إذا لم يكن مفعلاً
        const navigationButtons = document.querySelectorAll('[data-target="section-3"], #to-section-3');
        const step3 = document.getElementById('step-3');
        
        // معالج للأزرار التي تؤدي للقسم الثالث
        navigationButtons.forEach(button => {
            // إزالة المعالجات القديمة
            const newButton = button.cloneNode(true);
            button.parentNode.replaceChild(newButton, button);
            
            // إضافة معالج جديد
            newButton.addEventListener('click', (e) => {
                e.preventDefault();
                if (!hasInternalContent || !hasInternalContent.checked) {
                    this.showSection('section-4');
                } else {
                    this.showSection('section-3');
                }
            });
        });
        
        // معالج خاص للخطوة الثالثة
        if (step3) {
            const newStep3 = step3.cloneNode(true);
            step3.parentNode.replaceChild(newStep3, step3);
            
            newStep3.addEventListener('click', (e) => {
                e.preventDefault();
                if (!hasInternalContent || !hasInternalContent.checked) {
                    this.showSection('section-4');
                } else {
                    this.showSection('section-3');
                }
            });
        }
    },
    
    /**
     * إعداد معالجات أحداث حقول المقاس المخصص
     */
    setupCustomSizeFields: function() {
        const paperSizeSelect = document.getElementById('id_paper_size');
        const customSizeFields = document.getElementById('custom-size-fields');
        
        if (paperSizeSelect && customSizeFields) {
            // إضافة مستمع حدث لتغيير مقاس الورق
            paperSizeSelect.addEventListener('change', function() {
                // التحقق مما إذا كان المقاس المخصص هو المحدد
                const isCustomSize = this.options[this.selectedIndex].text === 'مقاس مخصص';
                customSizeFields.style.display = isCustomSize ? 'flex' : 'none';
            });
            
            // التحقق عند تحميل الصفحة
            const isCustomSize = paperSizeSelect.options[paperSizeSelect.selectedIndex].text === 'مقاس مخصص';
            customSizeFields.style.display = isCustomSize ? 'flex' : 'none';
        }
    },
    
    /**
     * إعداد معالجات أحداث حقول المقاس المفتوح
     */
    setupOpenSizeFields: function() {
        const useOpenSizeCheckbox = document.getElementById('use-open-size');
        const openSizeFields = document.getElementById('open-size-fields');
        
        if (useOpenSizeCheckbox && openSizeFields) {
            // إضافة مستمع حدث لتغيير حالة المقاس المفتوح
            useOpenSizeCheckbox.addEventListener('change', function() {
                openSizeFields.style.display = this.checked ? 'flex' : 'none';
            });
            
            // التحقق عند تحميل الصفحة
            openSizeFields.style.display = useOpenSizeCheckbox.checked ? 'flex' : 'none';
        }
    },
    
    /**
     * إعداد معالجات أحداث نوع الطلب
     */
    setupOrderTypeFields: function() {
        const orderTypeSelect = document.getElementById('id_order_type');
        const offsetFields = document.getElementById('offset-fields');
        const ctpFields = document.getElementById('ctp-fields');
        
        if (orderTypeSelect && offsetFields && ctpFields) {
            // إضافة مستمع حدث لتغيير نوع الطلب
            orderTypeSelect.addEventListener('change', function() {
                const isOffset = this.value === 'offset';
                offsetFields.style.display = isOffset ? 'block' : 'none';
                // نعرض قسم الزنكات دائمًا بغض النظر عن نوع الطباعة
                ctpFields.style.display = 'block';
            });
            
            // التحقق عند تحميل الصفحة
            const isOffset = orderTypeSelect.value === 'offset';
            offsetFields.style.display = isOffset ? 'block' : 'none';
            ctpFields.style.display = 'block';
        }
        
        // معالجة نوع الطلب للمحتوى الداخلي
        const internalOrderTypeSelect = document.getElementById('id_internal_order_type');
        const internalOffsetFields = document.getElementById('internal-offset-fields');
        const internalCtpFields = document.getElementById('internal-ctp-fields');
        
        if (internalOrderTypeSelect && internalOffsetFields && internalCtpFields) {
            // إضافة مستمع حدث لتغيير نوع الطلب
            internalOrderTypeSelect.addEventListener('change', function() {
                const isOffset = this.value === 'offset';
                internalOffsetFields.style.display = isOffset ? 'block' : 'none';
                // نعرض قسم الزنكات دائمًا بغض النظر عن نوع الطباعة
                internalCtpFields.style.display = 'block';
            });
            
            // التحقق عند تحميل الصفحة
            const isOffset = internalOrderTypeSelect.value === 'offset';
            internalOffsetFields.style.display = isOffset ? 'block' : 'none';
            internalCtpFields.style.display = 'block';
        }
    }
}; 