/**
 * نظام معالجة النماذج الموحد
 * يوفر واجهة موحدة لجميع نماذج الخدمات المتخصصة
 * @version 2.1.0
 */

class UniversalFormHandler {
    constructor(serviceType, serviceId = null, supplierId = null) {
        this.serviceType = serviceType;
        this.serviceId = serviceId;
        this.supplierId = supplierId;
        this.isEditMode = serviceId !== null && serviceId !== undefined;
        this.fieldMapping = null;
        this.serviceData = null;
        
    }
    
    /**
     * تهيئة النظام
     */
    async initialize() {
        try {
            // جلب خريطة الحقول
            await this.loadFieldMapping();
            
            // إنشاء النموذج ديناميكياً من field_mapping
            this.createFormFromMapping();
            
            // تحميل بيانات الخدمة إذا كان في وضع التعديل
            if (this.isEditMode) {
                await this.loadServiceData();
                if (this.serviceData) {
                    this.populateFields();
                } else {
                    console.error('فشل في تحميل بيانات الخدمة!');
                }
            } else {
            }
            
            // ربط أحداث النموذج
            this.bindFormEvents();
            
            
            // حفظ instance للاستخدام العام
            window.currentFormHandler = this;
            
            return true; // إرجاع نجاح التهيئة
        } catch (error) {
            console.error('خطأ في تهيئة النظام:', error);
            return false; // إرجاع فشل التهيئة
        }
    }
    
    /**
     * جلب خريطة الحقول من الخادم
     */
    async loadFieldMapping() {
        try {
            const response = await fetch(`/supplier/api/universal/get-field-mapping/${this.serviceType}/`);
            const result = await response.json();
            
            if (result.success) {
                this.fieldMapping = result.field_mapping;
            } else {
                throw new Error(result.error || 'فشل في جلب خريطة الحقول');
            }
            
        } catch (error) {
            console.error('خطأ في جلب خريطة الحقول:', error);
            throw error;
        }
    }
    
    /**
     * تحميل بيانات الخدمة للتعديل
     */
    async loadServiceData() {
        if (!this.serviceId) return;
        
        try {
            const url = `/supplier/api/universal/get-service-data/${this.serviceId}/`;
            const response = await fetch(url);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            
            if (result.success) {
                this.serviceData = result.service_data;
                // تم تحميل بيانات الخدمة بنجاح
            } else {
                throw new Error(result.error || 'فشل في تحميل بيانات الخدمة');
            }
            
        } catch (error) {
            console.error('خطأ في تحميل بيانات الخدمة:', error);
            throw error;
        }
    }
    
    /**
     * إنشاء النموذج ديناميكياً من field_mapping
     */
    createFormFromMapping() {
        if (!this.fieldMapping) return;
                
        // البحث عن الحقول الموجودة وإضافة data-field-id لها
        for (const [fieldName, fieldConfig] of Object.entries(this.fieldMapping)) {
            // البحث عن الحقل بطرق مختلفة
            const possibleSelectors = [
                `[name="${fieldName}"]`,
                `#${fieldName}`,
                `#${fieldName.replace('_', '-')}`,
                `#${fieldName.replace('_', '')}`
            ];
            
            let fieldElement = null;
            for (const selector of possibleSelectors) {
                fieldElement = document.querySelector(selector);
                if (fieldElement) break;
            }
            
            if (fieldElement) {
                // إضافة data-field-id للحقل
                fieldElement.setAttribute('data-field-id', `${this.serviceType}:${fieldName}`);
                
                // إضافة الخيارات للقوائم المنسدلة
                if (fieldConfig.input_type === 'select' && fieldConfig.choices) {
                    this.populateSelectOptions(fieldElement, fieldConfig.choices);
                }
            } else {
                console.warn(`لم يتم العثور على الحقل في DOM: ${fieldName}`);
            }
        }
        
        
        // إنشاء الشرائح السعرية الافتراضية إذا لم تكن موجودة
        this.ensureDefaultPriceTiers();
    }
    
    /**
     * ضمان وجود شرائح سعرية افتراضية
     */
    ensureDefaultPriceTiers() {
        const container = document.getElementById('price-tiers-container');
        if (!container) return;
        
        // التحقق من وجود شرائح سعرية
        const existingTiers = container.querySelectorAll('.tier-row');
        if (existingTiers.length === 0) {
            
            // إنشاء الشريحة الافتراضية
            const defaultTierHtml = `
                <div class="tier-row border rounded-3 p-3 mb-3 bg-light shadow-sm" data-tier="1">
                    <div class="row g-3 align-items-end">
                        <div class="col-md-2">
                            <label class="form-label fw-bold text-muted small">من الكمية</label>
                            <input type="number" class="form-control text-center" name="tier_1_min_quantity" 
                                   value="1" min="1" required readonly>
                        </div>
                        <div class="col-md-2">
                            <label class="form-label fw-bold text-muted small">إلى الكمية</label>
                            <input type="number" class="form-control text-center" name="tier_1_max_quantity" 
                                   value="50" min="1" required>
                        </div>
                        <div class="col-md-1"></div>
                        <div class="col-md-2">
                            <label class="form-label fw-bold text-muted small">السعر للقطعة (ج.م)</label>
                            <input type="number" class="form-control text-center" name="tier_1_price" 
                                   min="0" placeholder="0.00" required>
                        </div>
                        <div class="col-md-2">
                            <label class="form-label fw-bold text-muted small">السعر للأرضيات</label>
                            <input type="number" class="form-control text-center" name="tier_1_floor_price" 
                                   min="0" placeholder="0.00">
                        </div>
                        <div class="col"></div>
                        <div class="col-auto">
                            <label class="form-label fw-bold text-muted small">الإجراءات</label>
                            <div>
                                <button type="button" class="btn btn-outline-success btn-sm" disabled>
                                    <i class="fas fa-lock me-1"></i>محمية
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            container.innerHTML = defaultTierHtml;
        }
    }
    
    /**
     * ملء خيارات القائمة المنسدلة
     */
    populateSelectOptions(selectElement, choices) {
        // التحقق من وجود خيارات في الـ select من Django
        const existingOptions = selectElement.querySelectorAll('option:not([value=""])');
        
        // إذا كان الـ select عنده options من Django (أكثر من الخيار الافتراضي)، لا نمسحهم
        if (existingOptions.length > 0) {
            console.log(`✅ الـ select عنده ${existingOptions.length} options من Django - نتركهم`);
            return;
        }
        
        // إذا كان الـ select فاضي، نملأه من fieldMapping
        const defaultOption = selectElement.querySelector('option[value=""]');
        selectElement.innerHTML = '';
        
        // إعادة إضافة الخيار الافتراضي
        if (defaultOption) {
            selectElement.appendChild(defaultOption);
        }
        
        // إضافة الخيارات الجديدة
        choices.forEach(([value, label]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            selectElement.appendChild(option);
        });
    }
    
    /**
     * ملء الحقول بالبيانات المحملة
     */
    populateFields() {
        if (!this.serviceData) {
            console.warn('⚠️ لا توجد بيانات لملء الحقول');
            return;
        }
        
        console.log('📝 بدء ملء الحقول بالبيانات:', this.serviceData);
        
        for (const [fieldName, fieldValue] of Object.entries(this.serviceData)) {
            if (fieldValue !== null && fieldValue !== undefined) {
                console.log(`  ✏️ ملء ${fieldName} = ${fieldValue}`);
                this.setFieldValue(fieldName, fieldValue);
            }
        }
        
        // تحميل الشرائح السعرية إذا وجدت (للخدمات التي تدعمها)
        if (this.serviceData.price_tiers && this.serviceData.price_tiers.length > 0) {
            this.populatePriceTiers(this.serviceData.price_tiers);
        } else if (this.serviceType === 'digital_printing' || this.serviceType === 'offset_printing') {
            console.warn('لا توجد شرائح سعرية في البيانات المحملة');
        }
        
        console.log('✅ تم ملء جميع الحقول');
    }
    
    /**
     * تعيين قيمة حقل معين
     */
    setFieldValue(fieldName, value) {
        // البحث عن الحقل بطرق متعددة
        let fieldElement = document.querySelector(`[data-field-id="${this.serviceType}:${fieldName}"]`);
        
        // إذا لم يُعثر عليه، ابحث بالاسم مباشرة
        if (!fieldElement) {
            fieldElement = document.querySelector(`[name="${fieldName}"]`);
        }
        
        // إذا لم يُعثر عليه، ابحث بالـ ID
        if (!fieldElement) {
            const idVariations = [
                fieldName,
                fieldName.replace(/_/g, '-'),
                fieldName.replace(/_/g, '')
            ];
            
            for (const id of idVariations) {
                fieldElement = document.getElementById(id);
                if (fieldElement) break;
            }
        }
        
        if (fieldElement) {
            const fieldConfig = this.fieldMapping ? this.fieldMapping[fieldName] : null;
            const inputType = fieldConfig?.input_type || fieldElement.type;
            
            switch (inputType) {
                case 'checkbox':
                    fieldElement.checked = Boolean(value);
                    break;
                case 'select':
                case 'select-one':
                    fieldElement.value = value;
                    // إطلاق حدث التغيير للـ select
                    fieldElement.dispatchEvent(new Event('change', { bubbles: true }));
                    break;
                default:
                    fieldElement.value = value;
                    // إطلاق حدث الإدخال
                    fieldElement.dispatchEvent(new Event('input', { bubbles: true }));
                    break;
            }
        } else {
            // تجاهل التحذيرات للحقول غير المطلوبة في بعض الأنواع
            const ignoredFields = {
                'plates': ['description', 'setup_cost', 'price_tiers'],
                'paper': ['price_tiers'],
                'finishing': ['price_tiers', 'description', 'setup_time_minutes', 'turnaround_time_hours'],
                'coating': ['price_tiers', 'description', 'setup_time_minutes', 'turnaround_time_hours']
            };
            
            const shouldIgnore = ignoredFields[this.serviceType]?.includes(fieldName);
            if (!shouldIgnore) {
                console.log(`⚠️ لم يتم العثور على الحقل: ${fieldName}`);
            }
        }
    }
    
    /**
     * جمع بيانات النموذج
     */
    collectFormData() {
        const formData = {};
        
        console.log('🔍 بدء جمع البيانات...');
        console.log('fieldMapping موجود؟', !!this.fieldMapping);
        console.log('عدد حقول fieldMapping:', this.fieldMapping ? Object.keys(this.fieldMapping).length : 0);
        
        // جمع البيانات من الحقول المسجلة في fieldMapping
        if (this.fieldMapping && Object.keys(this.fieldMapping).length > 0) {
            console.log('✅ استخدام fieldMapping');
            for (const fieldName of Object.keys(this.fieldMapping)) {
                const value = this.getFieldValue(fieldName);
                console.log(`  - ${fieldName}: ${value}`);
                if (value !== null && value !== undefined) {
                    formData[fieldName] = value;
                }
            }
        } else {
            // إذا لم يكن fieldMapping موجود أو فارغ، جمع جميع حقول النموذج
            console.log('⚠️ fieldMapping غير موجود أو فارغ - جمع الحقول مباشرة من النموذج');
            
            const form = document.getElementById('dynamic-service-form');
            if (form) {
                const inputs = form.querySelectorAll('input, select, textarea');
                console.log(`📝 عدد الحقول الموجودة: ${inputs.length}`);
                
                inputs.forEach(input => {
                    if (input.name && !input.name.startsWith('tier_') && !input.name.startsWith('csrf')) {
                        const value = this.getFieldValue(input.name);
                        console.log(`  - ${input.name}: ${value}`);
                        if (value !== null && value !== undefined && value !== '') {
                            formData[input.name] = value;
                        }
                    }
                });
            } else {
                console.error('❌ لم يتم العثور على النموذج #dynamic-service-form');
            }
        }
        
        // إضافة البيانات الأساسية
        formData.service_type = this.serviceType;
        if (this.supplierId) {
            formData.supplier_id = this.supplierId;
        }
        if (this.serviceId) {
            formData.service_id = this.serviceId;
        }
        
        // جمع بيانات الشرائح السعرية
        const priceTiers = this.collectPriceTiers();
        if (priceTiers.length > 0) {
            formData.price_tiers = priceTiers;
        }
        
        console.log('📦 البيانات المجمعة:', formData);
        
        return formData;
    }
    
    /**
     * جلب قيمة حقل معين
     */
    getFieldValue(fieldName) {
        // البحث عن الحقل بطرق متعددة
        let fieldElement = document.querySelector(`[data-field-id="${this.serviceType}:${fieldName}"]`);
        
        // إذا لم يُعثر عليه، ابحث بالاسم مباشرة
        if (!fieldElement) {
            fieldElement = document.querySelector(`[name="${fieldName}"]`);
        }
        
        // إذا لم يُعثر عليه، ابحث بالـ ID
        if (!fieldElement) {
            const idVariations = [
                fieldName,
                fieldName.replace(/_/g, '-'),
                fieldName.replace(/_/g, '')
            ];
            
            for (const id of idVariations) {
                fieldElement = document.getElementById(id);
                if (fieldElement) break;
            }
        }
        
        if (fieldElement) {
            const fieldConfig = this.fieldMapping ? this.fieldMapping[fieldName] : null;
            
            // تحديد نوع الحقل
            const inputType = fieldConfig?.input_type || fieldElement.type;
            
            switch (inputType) {
                case 'checkbox':
                    return fieldElement.checked;
                case 'number':
                    return fieldElement.value ? parseFloat(fieldElement.value) : null;
                default:
                    return fieldElement.value || null;
            }
        }
        
        console.warn(`لم يتم العثور على الحقل: ${fieldName}`);
        return null;
    }
    
    /**
     * جمع بيانات الشرائح السعرية
     */
    collectPriceTiers() {
        const tiers = [];
        const tierRows = document.querySelectorAll('.tier-row');
        
        tierRows.forEach((row, index) => {
            const tierNumber = index + 1;
            const minQuantity = row.querySelector(`[name*="tier_${tierNumber}_min_quantity"], [name*="min_quantity"]`)?.value;
            const maxQuantity = row.querySelector(`[name*="tier_${tierNumber}_max_quantity"], [name*="max_quantity"]`)?.value;
            const price = row.querySelector(`[name*="tier_${tierNumber}_price"], [name*="price"]`)?.value;
            const floorPrice = row.querySelector(`[name*="tier_${tierNumber}_floor_price"], [name*="floor_price"]`)?.value;
            
            if (minQuantity && price) {
                tiers.push({
                    tier_name: `${minQuantity}-${maxQuantity || '∞'}`,
                    min_quantity: parseInt(minQuantity),
                    max_quantity: maxQuantity ? parseInt(maxQuantity) : null,
                    price_per_unit: parseFloat(price),
                    floor_price: floorPrice ? parseFloat(floorPrice) : null,
                    discount_percentage: 0
                });
            }
        });
        
        return tiers;
    }
    
    /**
     * ملء الشرائح السعرية في النموذج
     */
    populatePriceTiers(tiers) {
        const container = document.getElementById('price-tiers-container');
        if (!container) {
            console.error('لم يتم العثور على price-tiers-container');
            return;
        }
        
        
        // مسح الشرائح الموجودة
        container.innerHTML = '';
        
        tiers.forEach((tier, index) => {
            const tierNumber = index + 1;
            const isFirst = index === 0;
            
            const tierHtml = `
                <div class="tier-row border rounded-3 p-3 mb-3 ${isFirst ? 'bg-light' : ''} shadow-sm" data-tier="${tierNumber}">
                    <div class="row g-3 align-items-end">
                        <div class="col-md-2">
                            <label class="form-label fw-bold text-muted small">من الكمية</label>
                            <input type="number" class="form-control text-center" name="tier_${tierNumber}_min_quantity" 
                                   value="${tier.min_quantity}" min="1" required ${isFirst ? 'readonly' : ''}>
                        </div>
                        <div class="col-md-2">
                            <label class="form-label fw-bold text-muted small">إلى الكمية</label>
                            <input type="number" class="form-control text-center" name="tier_${tierNumber}_max_quantity" 
                                   value="${tier.max_quantity || ''}" min="1" ${tier.max_quantity ? 'required' : ''}>
                        </div>
                        <div class="col-md-1"></div>
                        <div class="col-md-2">
                            <label class="form-label fw-bold text-muted small">السعر للقطعة (ج.م)</label>
                            <input type="number" class="form-control text-center" name="tier_${tierNumber}_price" 
                                   value="${tier.price_per_unit}" min="0" required>
                        </div>
                        <div class="col-md-2">
                            <label class="form-label fw-bold text-muted small">السعر للأرضيات</label>
                            <input type="number" class="form-control text-center" name="tier_${tierNumber}_floor_price" 
                                   value="${tier.floor_price || ''}" min="0">
                        </div>
                        <div class="col"></div>
                        <div class="col-auto">
                            <label class="form-label fw-bold text-muted small">الإجراءات</label>
                            <div>
                                ${isFirst ? 
                                    `<button type="button" class="btn btn-outline-success btn-sm" disabled>
                                        <i class="fas fa-lock me-1"></i>محمية
                                    </button>` :
                                    `<button type="button" class="btn btn-outline-danger btn-sm" onclick="removeTier(${tierNumber})">
                                        <i class="fas fa-trash me-1"></i>حذف
                                    </button>`
                                }
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            container.insertAdjacentHTML('beforeend', tierHtml);
        });
        
        // تحديث عداد الشرائح
        if (typeof window.tierCount !== 'undefined') {
            window.tierCount = tiers.length;
        }
        
        
        // التحقق من أن الحقول تم إنشاؤها بشكل صحيح
        const createdInputs = container.querySelectorAll('input[name*="tier_"]');
        
    }
    
    /**
     * حفظ البيانات
     */
    async saveData() {
        try {
            const formData = this.collectFormData();
            
            // تحديد الـ API المناسب
            const apiUrl = this.isEditMode 
                ? `/supplier/api/universal/update-service-data/${this.serviceId}/`
                : '/supplier/api/universal/save-service-data/';
            
            
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: JSON.stringify(formData)
            });
            
            const result = await response.json();
            
            if (result.success) {
                const operationType = this.isEditMode ? 'تم تحديث الخدمة بنجاح!' : 'تم حفظ الخدمة بنجاح!';
                
                // الانتقال لصفحة المورد
                if (result.redirect_url) {
                    window.location.href = result.redirect_url;
                } else if (this.supplierId) {
                    window.location.href = `/supplier/${this.supplierId}/detail/`;
                }
                
                return true;
            } else {
                throw new Error(result.error || 'حدث خطأ غير متوقع');
            }
            
        } catch (error) {
            console.error('خطأ في حفظ البيانات:', error);
            alert('خطأ في حفظ البيانات: ' + error.message);
            return false;
        }
    }
    
    /**
     * ربط أحداث النموذج
     */
    bindFormEvents() {
        // ربط حدث الإرسال
        const form = document.getElementById('dynamic-service-form');
        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.saveData();
            });
        }
        
        // ربط أحداث التحقق من الصحة
        this.bindValidationEvents();
                
        // ربط أحداث الشرائح السعرية
        this.bindPriceTierEvents();
        
        // ربط أحداث تحديث اسم الخدمة للطباعة الديجيتال
        this.bindServiceNameEvents();
    }
    
    /**
     * ربط أحداث الشرائح السعرية
     */
    bindPriceTierEvents() {
        // ربط زر إضافة شريحة جديدة
        const addTierBtn = document.getElementById('add-tier-btn');
        if (addTierBtn) {
            addTierBtn.onclick = () => this.addNewTier();
        }
        
        // ربط أزرار حذف الشرائح الموجودة
        this.bindDeleteTierButtons();
    }
    
    /**
     * ربط أزرار حذف الشرائح
     */
    bindDeleteTierButtons() {
        const deleteButtons = document.querySelectorAll('.delete-tier-btn');
        deleteButtons.forEach(btn => {
            btn.onclick = (e) => {
                e.preventDefault();
                const tierRow = btn.closest('.tier-row');
                if (tierRow) {
                    this.deleteTier(tierRow);
                }
            };
        });
    }
    
    /**
     * ربط أحداث تحديث اسم الخدمة
     */
    bindServiceNameEvents() {
        if (this.serviceType === 'digital_printing') {
            const machineType = document.getElementById('machine-type');
            const paperSize = document.getElementById('paper-size');
            
            if (machineType) {
                machineType.addEventListener('change', () => this.updateServiceName());
            }
            if (paperSize) {
                paperSize.addEventListener('change', () => this.updateServiceName());
            }
        } else if (this.serviceType === 'paper') {
            const paperType = document.getElementById('paper-type');
            const gsm = document.getElementById('gsm');
            const sheetSize = document.getElementById('sheet-size');
            const country = document.getElementById('country');
            
            if (paperType) {
                paperType.addEventListener('change', () => this.updateServiceName());
            }
            if (gsm) {
                gsm.addEventListener('change', () => this.updateServiceName());
            }
            if (sheetSize) {
                sheetSize.addEventListener('change', () => this.updateServiceName());
            }
            if (country) {
                country.addEventListener('change', () => this.updateServiceName());
            }
        } else if (this.serviceType === 'plates') {
            const plateSize = document.getElementById('plate-size');
            
            if (plateSize) {
                plateSize.addEventListener('change', () => this.updateServiceName());
            }
        }
        
        // تحديث أولي
        this.updateServiceName();
    }
    
    /**
     * تحديث اسم الخدمة
     */
    updateServiceName() {
        if (this.serviceType === 'digital_printing') {
            this.updateDigitalServiceName();
        } else if (this.serviceType === 'paper') {
            this.updatePaperServiceName();
        } else if (this.serviceType === 'plates') {
            this.updatePlatesServiceName();
        } else {
        }
    }
    
    /**
     * تحديث اسم الخدمة للطباعة الديجيتال
     */
    updateDigitalServiceName() {
        
        const machineType = document.getElementById('machine-type');
        const paperSize = document.getElementById('paper-size');
        const serviceName = document.getElementById('service-name');
        
        if (!machineType || !paperSize || !serviceName) {
            console.error('عناصر مفقودة لتحديث اسم الخدمة الديجيتال');
            return;
        }
        
        if (machineType.value && paperSize.value) {
            let name = 'ماكينة ديجيتال ';
            
            const machineTypeText = machineType.options[machineType.selectedIndex].text;
            name += machineTypeText;
            
            const paperSizeText = paperSize.options[paperSize.selectedIndex].text;
            const sizeNameOnly = paperSizeText.split('(')[0].trim();
            name += ' - ' + sizeNameOnly;
            
            serviceName.value = name;
        } else {
            serviceName.value = '';
        }
    }
    
    /**
     * تحديث اسم الخدمة للورق
     */
    updatePaperServiceName() {
        
        const paperType = document.getElementById('paper-type');
        const gsm = document.getElementById('gsm');
        const sheetSize = document.getElementById('sheet-size');
        const country = document.getElementById('country');
        const serviceName = document.getElementById('service-name');
        
        
        if (!paperType || !gsm || !sheetSize || !serviceName) {
            console.error('عناصر مفقودة لتحديث اسم الخدمة للورق');
            return;
        }
        
        if (paperType.value && gsm.value && sheetSize.value) {
            let name = '';
            
            // نوع الورق
            const paperTypeText = paperType.options[paperType.selectedIndex].text;
            name += paperTypeText;
            
            // المنشأ (اختياري)
            if (country && country.value) {
                const countryText = country.options[country.selectedIndex].text;
                const countryName = countryText.split('(')[0].trim();
                name += ' ' + countryName;
            }
            
            // الوزن
            const gsmText = gsm.options[gsm.selectedIndex].text;
            const weightMatch = gsmText.match(/(\d+)\s*جم/);
            if (weightMatch) {
                name += ' - ' + weightMatch[1] + 'جم';
            }
            
            // المقاس - فقط اسم المقاس بدون الأبعاد
            const sheetSizeText = sheetSize.options[sheetSize.selectedIndex].text;
            const sizeNameOnly = sheetSizeText.split('(')[0].trim();
            name += ' - ' + sizeNameOnly;
            
            serviceName.value = name;
        } else {
            serviceName.value = '';
        }
    }
    
    /**
     * إضافة شريحة سعرية جديدة
     */
    addNewTier() {
        const container = document.getElementById('price-tiers-container');
        if (!container) return;
        
        const existingTiers = container.querySelectorAll('.tier-row');
        const tierNumber = existingTiers.length + 1;
        
        // حساب الحد الأدنى للشريحة الجديدة
        let minQuantity = 1;
        if (existingTiers.length > 0) {
            const lastTier = existingTiers[existingTiers.length - 1];
            const lastMaxInput = lastTier.querySelector('[name*="max_quantity"]');
            if (lastMaxInput && lastMaxInput.value) {
                minQuantity = parseInt(lastMaxInput.value) + 1;
            }
        }
        
        const tierHtml = `
            <div class="tier-row border rounded-3 p-3 mb-3 bg-light shadow-sm" data-tier="${tierNumber}">
                <div class="row g-3 align-items-end">
                    <div class="col-md-2">
                        <label class="form-label fw-bold text-muted small">من الكمية</label>
                        <input type="number" class="form-control text-center" name="tier_${tierNumber}_min_quantity" 
                               value="${minQuantity}" min="1" required>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label fw-bold text-muted small">إلى الكمية</label>
                        <input type="number" class="form-control text-center" name="tier_${tierNumber}_max_quantity" 
                               value="${minQuantity + 49}" min="1" required>
                    </div>
                    <div class="col-md-1"></div>
                    <div class="col-md-2">
                        <label class="form-label fw-bold text-muted small">السعر للقطعة (ج.م)</label>
                        <input type="number" class="form-control text-center" name="tier_${tierNumber}_price" 
                               min="0" placeholder="0.00" required>
                    </div>
                    <div class="col-md-2">
                        <label class="form-label fw-bold text-muted small">السعر للأرضيات (ج.م)</label>
                        <input type="number" class="form-control text-center" name="tier_${tierNumber}_floor_price" 
                               min="0" placeholder="0.00">
                    </div>
                    <div class="col"></div>
                    <div class="col-auto">
                        <label class="form-label fw-bold text-muted small">الإجراءات</label>
                        <div>
                            <button type="button" class="btn btn-outline-danger btn-sm delete-tier-btn">
                                <i class="fas fa-trash me-1"></i>حذف
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        container.insertAdjacentHTML('beforeend', tierHtml);
        
        // ربط زر الحذف للشريحة الجديدة
        this.bindDeleteTierButtons();
        
    }
    
    /**
     * حذف شريحة سعرية
     */
    deleteTier(tierRow) {
        const container = document.getElementById('price-tiers-container');
        const allTiers = container.querySelectorAll('.tier-row');
        
        // منع حذف الشريحة الوحيدة
        if (allTiers.length <= 1) {
            alert('لا يمكن حذف الشريحة الوحيدة');
            return;
        }
        
        // تأكيد الحذف
        if (confirm('هل أنت متأكد من حذف هذه الشريحة؟')) {
            tierRow.remove();
            
            // إعادة ترقيم الشرائح
            this.renumberTiers();
        }
    }
    
    /**
     * إعادة ترقيم الشرائح بعد الحذف
     */
    renumberTiers() {
        const container = document.getElementById('price-tiers-container');
        const tiers = container.querySelectorAll('.tier-row');
        
        tiers.forEach((tier, index) => {
            const tierNumber = index + 1;
            tier.setAttribute('data-tier', tierNumber);
            
            // تحديث أسماء الحقول
            const inputs = tier.querySelectorAll('input[name*="tier_"]');
            inputs.forEach(input => {
                const name = input.name;
                const fieldType = name.split('_').slice(2).join('_'); // min_quantity, max_quantity, etc.
                input.name = `tier_${tierNumber}_${fieldType}`;
            });
        });
        
    }
    
    /**
     * ربط أحداث التحقق من الصحة
     */
    bindValidationEvents() {
        if (!this.fieldMapping) return;
        
        for (const [fieldName, fieldConfig] of Object.entries(this.fieldMapping)) {
            const fieldElement = document.querySelector(`[data-field-id="${this.serviceType}:${fieldName}"]`);
            
            if (fieldElement && fieldConfig.required) {
                fieldElement.addEventListener('blur', () => {
                    this.validateField(fieldName, fieldElement);
                });
            }
        }
    }
    
    /**
     * التحقق من صحة حقل معين
     */
    validateField(fieldName, fieldElement) {
        const fieldConfig = this.fieldMapping[fieldName];
        const value = fieldElement.value;
        
        // التحقق من الحقول المطلوبة
        if (fieldConfig.required && !value) {
            this.showFieldError(fieldElement, 'هذا الحقل مطلوب');
            return false;
        }
        
        // التحقق من الأرقام الموجبة
        if (fieldConfig.validation === 'positive_number' && value) {
            const numValue = parseFloat(value);
            if (isNaN(numValue) || numValue < 0) {
                this.showFieldError(fieldElement, 'يجب أن تكون القيمة رقم موجب');
                return false;
            }
        }
        
        // إزالة رسالة الخطأ إذا كان الحقل صحيح
        this.clearFieldError(fieldElement);
        return true;
    }
    
    /**
     * عرض رسالة خطأ للحقل
     */
    showFieldError(fieldElement, message) {
        fieldElement.classList.add('is-invalid');
        
        // البحث عن عنصر الخطأ أو إنشاؤه
        let errorElement = fieldElement.parentNode.querySelector('.invalid-feedback');
        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.className = 'invalid-feedback';
            fieldElement.parentNode.appendChild(errorElement);
        }
        
        errorElement.textContent = message;
    }
    
    /**
     * إزالة رسالة خطأ الحقل
     */
    clearFieldError(fieldElement) {
        fieldElement.classList.remove('is-invalid');
        
        const errorElement = fieldElement.parentNode.querySelector('.invalid-feedback');
        if (errorElement) {
            errorElement.remove();
        }
    }
    
    /**
     * التحقق من صحة النموذج كاملاً
     */
    validateForm() {
        let isValid = true;
        
        if (this.fieldMapping) {
            for (const fieldName of Object.keys(this.fieldMapping)) {
                const fieldElement = document.querySelector(`[data-field-id="${this.serviceType}:${fieldName}"]`);
                if (fieldElement) {
                    if (!this.validateField(fieldName, fieldElement)) {
                        isValid = false;
                    }
                }
            }
        }
        
        return isValid;
    }
    
    /**
     * تحديث اسم خدمة الزنك
     */
    updatePlatesServiceName() {
        
        const plateSize = document.getElementById('plate-size');
        const serviceName = document.getElementById('service-name');
        
        if (plateSize && serviceName && plateSize.value) {
            const sizeText = plateSize.options[plateSize.selectedIndex].text;
            
            // إذا كان مقاس مخصوص، استخدم اسم مختلف
            if (plateSize.value === 'custom') {
                serviceName.value = 'زنك CTP - مقاس مخصوص';
            } else {
                // استخدم النص كما هو (ربع، نص، فرخ)
                serviceName.value = `زنك CTP - ${sizeText}`;
            }
            
        }
    }
}

// تصدير الكلاس للاستخدام العام
window.UniversalFormHandler = UniversalFormHandler;

// دوال عامة للتوافق مع النظام القديم
window.addNewTier = function() {
    // البحث عن instance النظام الموحد
    if (window.currentFormHandler && typeof window.currentFormHandler.addNewTier === 'function') {
        window.currentFormHandler.addNewTier();
    } else {
        console.error('النظام الموحد غير متاح');
    }
};

window.deleteTier = function(button) {
    // البحث عن instance النظام الموحد
    if (window.currentFormHandler && typeof window.currentFormHandler.deleteTier === 'function') {
        const tierRow = button.closest('.tier-row');
        if (tierRow) {
            window.currentFormHandler.deleteTier(tierRow);
        }
    } else {
        console.error('النظام الموحد غير متاح');
    }
};
