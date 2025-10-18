/**
 * field-handlers.js - معالجات الحقول الديناميكية للنظام الجديد - المحسن
 * 
 * هذا الملف يحتوي على معالجات احترافية للحقول مع تحسينات المرحلة الأولى:
 * - id_client (Select2 مع البحث)
 * - id_product_type (Select مع البيانات من API)
 * - id_product_size (Select مع البيانات من API)
 * 
 * تحسينات المرحلة الأولى:
 * - نظام التخزين المؤقت الذكي
 * - معالجة الأخطاء المحسنة
 * - الحفظ التلقائي
 * - تحسين أداء API
 */
// تعريف كائن عام للنظام الجديد
window.PrintingPricingSystem = window.PrintingPricingSystem || {};

// وحدة معالجة الحقول
PrintingPricingSystem.FieldHandlers = {
    /**
     * إعدادات النظام الأساسية
     */
    config: {
        apiBaseUrl: '/printing-pricing/api/',
        debounceDelay: 300,
        animationDuration: 300,
        // إعدادات الأداء
        cacheTimeout: 300000, // 5 دقائق
        maxRetries: 3,
        requestTimeout: 10000, // 10 ثوانٍ
        // إعدادات التحقق
        validationDelay: 100,
        highlightDuration: 3000,
        // إعدادات الحفظ التلقائي
        autoSaveInterval: 30000, // 30 ثانية
        autoSaveFields: [
            'client', 'title', 'quantity', 'product_type', 'product_size',
            'has_internal_content', 'open_size_width', 'open_size_height',
            'internal_page_count', 'binding_side'
        ],
        // حقول خاصة بمعرفات مخصصة (ليس id_*)
        specialFields: ['use-open-size'],
        // إعدادات Select2
        select2Config: {
            theme: 'bootstrap-5',
            dir: 'rtl',
            language: 'ar',
            width: '100%'
        }
    },

    /**
     * ذاكرة التخزين المؤقت للبيانات
     */
    cache: {
        'clients': { data: null, timestamp: 0 },
        'product-types': { data: null, timestamp: 0 },
        'product-sizes': { data: null, timestamp: 0 }
    },

    /**
     * إدارة التخزين المؤقت
     */
    getCachedData: function(key) {
        const cached = this.cache[key];
        if (!cached || !cached.data) return null;
        
        const now = Date.now();
        const isExpired = (now - cached.timestamp) > this.config.cacheTimeout;
        
        if (isExpired) {
            console.log(`⏰ انتهت صلاحية البيانات المخزنة: ${key}`);
            this.cache[key] = { data: null, timestamp: 0 };
            return null;
        }
        
        console.log(`📦 استخدام البيانات المخزنة: ${key}`);
        return cached.data;
    },

    setCachedData: function(key, data) {
        this.cache[key] = {
            data: data,
            timestamp: Date.now()
        };
        console.log(`💾 تم تخزين البيانات: ${key}`);
    },

    clearCache: function(key) {
        if (key) {
            this.cache[key] = { data: null, timestamp: 0 };
        } else {
            // مسح جميع البيانات المخزنة
            Object.keys(this.cache).forEach(k => {
                this.cache[k] = { data: null, timestamp: 0 };
            });
        }
    },


    /**
     * تهيئة جميع معالجات الحقول
     */
    init: function() {
        console.log('🚀 تهيئة معالجات الحقول...');
        
        this.initClientField();
        this.initProductTypeField();
        this.initProductSizeField();
        this.initPrintDirectionField();
        this.initToggleFields();
        this.initFormValidation();
        this.initAutoSave();
        this.setupGlobalSelect2Focus();
        
        console.log('✅ تم تهيئة معالجات الحقول بنجاح');
    },

    /**
     * إعداد Focus تلقائي لجميع Select2 في الصفحة
     */
    setupGlobalSelect2Focus: function() {
        // تطبيق Focus على جميع Select2 الموجودة
        $('select.select2-hidden-accessible').each(function() {
            const $select = $(this);
            
            // إضافة معالج Focus لكل Select2
            $select.on('select2:open', function() {
                setTimeout(() => {
                    const searchField = document.querySelector('.select2-search__field');
                    if (searchField) {
                        searchField.focus();
                    }
                }, 100);
            });
        });

        // مراقبة Select2 الجديدة التي قد تُضاف لاحقاً
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === 1) { // Element node
                        // البحث عن Select2 جديدة في العقدة المضافة
                        const newSelect2 = $(node).find('select.select2-hidden-accessible');
                        newSelect2.each(function() {
                            const $select = $(this);
                            
                            // التأكد من عدم إضافة المعالج مسبقاً
                            if (!$select.data('focus-handler-added')) {
                                $select.on('select2:open', function() {
                                    setTimeout(() => {
                                        const searchField = document.querySelector('.select2-search__field');
                                        if (searchField) {
                                            searchField.focus();
                                        }
                                    }, 100);
                                });
                                
                                $select.data('focus-handler-added', true);
                            }
                        });
                    }
                });
            });
        });

        // بدء مراقبة التغييرات في DOM
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        console.log('✅ تم إعداد Focus تلقائي لجميع Select2');
    },

    /**
     * تهيئة حقل العميل مع Select2
     */
    initClientField: function() {
        const clientField = $('#id_client');
        if (!clientField.length) {
            console.warn('⚠️ حقل العميل غير موجود');
            return;
        }

        console.log('🔧 تهيئة حقل العميل...');

        // تحويل الحقل إلى Select2 مع البحث الديناميكي
        clientField.select2({
            ...this.config.select2Config,
            placeholder: 'اختر العميل...',
            allowClear: true,
            minimumInputLength: 0,
            ajax: {
                url: this.config.apiBaseUrl + 'get-clients/',
                dataType: 'json',
                delay: 300,
                data: function(params) {
                    return {
                        search: params.term || '',
                        page: params.page || 1
                    };
                },
                processResults: function(data, params) {
                    params.page = params.page || 1;
                    
                    if (data.success) {
                        return {
                            results: data.results,
                            pagination: {
                                more: data.pagination.more
                            }
                        };
                    } else {
                        console.error('خطأ في جلب العملاء:', data.error);
                        return { results: [] };
                    }
                },
                cache: true
            },
            templateResult: this.formatClientOption,
            templateSelection: this.formatClientSelection
        });

        // معالج تغيير العميل
        clientField.on('select2:select', (e) => {
            const selectedData = e.params.data;
            console.log('👤 تم اختيار العميل:', selectedData.text);
            this.onClientChange(selectedData);
            
            // تفعيل الحفظ التلقائي (بدون مؤشر فوري)
            if (this.autoSave) {
                this.autoSave.isDirty = true;
                // سيتم الحفظ في الدورة التالية للمؤقت
            }
        });

        clientField.on('select2:clear', () => {
            console.log('🗑️ تم مسح اختيار العميل');
            this.onClientClear();
            
            // تفعيل الحفظ التلقائي (بدون مؤشر فوري)
            if (this.autoSave) {
                this.autoSave.isDirty = true;
                // سيتم الحفظ في الدورة التالية للمؤقت
            }
        });

        console.log('✅ تم تهيئة حقل العميل بنجاح');
    },

    /**
     * تنسيق عرض خيار العميل في القائمة
     */
    formatClientOption: function(client) {
        if (client.loading) {
            return client.text;
        }

        const $container = $(
            `<div class="select2-result-client">
                <div class="client-name">${client.text}</div>
            </div>`
        );

        return $container;
    },

    /**
     * تنسيق عرض العميل المختار
     */
    formatClientSelection: function(client) {
        return client.text || client.name;
    },

    /**
     * معالج تغيير العميل
     */
    onClientChange: function(clientData) {
        // يمكن إضافة منطق إضافي هنا
        // مثل تحديث معلومات العميل أو الأسعار الخاصة
        
        // إطلاق حدث مخصص
        $(document).trigger('client:changed', clientData);
    },

    /**
     * معالج مسح العميل
     */
    onClientClear: function() {
        // إطلاق حدث مخصص
        $(document).trigger('client:cleared');
    },

    /**
     * تهيئة حقل نوع المنتج مع Select2
     */
    initProductTypeField: function() {
        const productTypeField = $('#id_product_type');
        if (!productTypeField.length) {
            console.warn('⚠️ حقل نوع المنتج غير موجود');
            return;
        }

        console.log('🔧 تهيئة حقل نوع المنتج مع Select2...');

        // تحويل الحقل إلى Select2
        productTypeField.select2({
            ...this.config.select2Config,
            placeholder: 'اختر نوع المنتج...',
            allowClear: true,
            minimumInputLength: 0
        });

        // جلب أنواع المنتجات من API
        this.loadProductTypes()
            .then(productTypes => {
                // loadProductTypes ترجع مصفوفة مباشرة
                if (productTypes && Array.isArray(productTypes) && productTypes.length > 0) {
                    this.populateProductTypeField(productTypeField, productTypes);
                } else {
                    console.warn('⚠️ لم يتم العثور على أنواع منتجات');
                    // استخدام بيانات افتراضية
                    const defaultTypes = [
                        { id: '1', text: 'كتاب', is_default: false },
                        { id: '2', text: 'مجلة', is_default: false },
                        { id: '3', text: 'بروشور', is_default: true }
                    ];
                    this.populateProductTypeField(productTypeField, defaultTypes);
                }
            })
            .catch(error => {
                console.error('خطأ في API أنواع المنتجات:', error);
                // استخدام بيانات افتراضية في حالة الخطأ
                const fallbackTypes = [
                    { id: '1', text: 'كتاب', is_default: false },
                    { id: '2', text: 'مجلة', is_default: false },
                    { id: '3', text: 'بروشور', is_default: true }
                ];
                this.populateProductTypeField(productTypeField, fallbackTypes);
                if (typeof showPricingNotification !== 'undefined') {
                    showPricingNotification('تم استخدام أنواع منتجات افتراضية', 'info');
                }
            });

        // معالج تغيير نوع المنتج
        productTypeField.on('select2:select', (e) => {
            const selectedData = e.params.data;
            console.log('📦 تم اختيار نوع المنتج:', selectedData.text);
            this.onProductTypeChange(selectedData.id, selectedData.text);
            
            // تفعيل الحفظ التلقائي (بدون مؤشر فوري)
            if (this.autoSave) {
                this.autoSave.isDirty = true;
                // سيتم الحفظ في الدورة التالية للمؤقت
            }
        });

        productTypeField.on('select2:clear', () => {
            console.log('🗑️ تم مسح اختيار نوع المنتج');
            this.onProductTypeClear();
            
            // تفعيل الحفظ التلقائي (بدون مؤشر فوري)
            if (this.autoSave) {
                this.autoSave.isDirty = true;
                // سيتم الحفظ في الدورة التالية للمؤقت
            }
        });
        console.log('✅ تم تهيئة حقل نوع المنتج مع Select2 بنجاح');
    },

    /**
     * جلب أنواع المنتجات من API مع التخزين المؤقت
     */
    loadProductTypes: function() {
        // التحقق من وجود بيانات مخزنة مؤقتاً
        const cached = this.getCachedData('product-types');
        if (cached) {
            console.log('📦 استخدام بيانات أنواع المنتجات المخزنة مؤقتاً');
            return Promise.resolve(cached);
        }

        const apiUrl = this.config.apiBaseUrl + 'get-product-types/';
        console.log('🌐 جلب أنواع المنتجات من الخادم...', apiUrl);
        
        return fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                // التحقق من وجود البيانات
                if (data && data.success && data.results) {
                    console.log(`🎯 تم جلب ${data.results.length} نوع منتج من API`);
                    // حفظ البيانات في التخزين المؤقت
                    this.setCachedData('product-types', data.results);
                    return data.results;
                } else if (data && data.error) {
                    throw new Error(data.error);
                } else {
                    // في حالة عدم وجود بيانات، إنشاء أنواع منتجات افتراضية
                    console.warn('⚠️ لا توجد أنواع منتجات في قاعدة البيانات، سيتم إنشاء بيانات افتراضية');
                    
                    // محاولة إنشاء أنواع منتجات في قاعدة البيانات
                    this.createDefaultProductTypes();
                    
                    const defaultTypes = [
                        { id: '1', text: 'كتاب', is_default: false },
                        { id: '2', text: 'مجلة', is_default: false },
                        { id: '3', text: 'بروشور', is_default: true },
                        { id: '4', text: 'كتالوج', is_default: false },
                        { id: '5', text: 'فلاير', is_default: false },
                        { id: '6', text: 'بوستر', is_default: false }
                    ];
                    this.setCachedData('product-types', defaultTypes);
                    return defaultTypes;
                }
            })
            .catch(error => {
                console.error('❌ خطأ في جلب أنواع المنتجات:', error);
                console.error('تفاصيل الخطأ:', error.message);
                
                // استخدام بيانات افتراضية في حالة الخطأ
                const fallbackTypes = [
                    { id: '1', text: 'كتاب', is_default: false },
                    { id: '2', text: 'مجلة', is_default: false },
                    { id: '3', text: 'بروشور', is_default: true }
                ];
                this.setCachedData('product-types', fallbackTypes);
                
                // إشعار مفصل للمستخدم
                if (typeof showPricingNotification !== 'undefined') {
                    showPricingNotification(`فشل في جلب أنواع المنتجات من الخادم: ${error.message}. تم استخدام بيانات افتراضية.`, 'error');
                }
                return fallbackTypes;
            });
    },

    /**
     * إنشاء أنواع منتجات افتراضية في قاعدة البيانات
     */
    createDefaultProductTypes: function() {
        const defaultTypes = [
            { name: 'كتاب', description: 'كتب ومطبوعات', is_default: false },
            { name: 'مجلة', description: 'مجلات ودوريات', is_default: false },
            { name: 'بروشور', description: 'بروشورات إعلانية', is_default: true },
            { name: 'كتالوج', description: 'كتالوجات منتجات', is_default: false },
            { name: 'فلاير', description: 'فلايرات إعلانية', is_default: false },
            { name: 'بوستر', description: 'بوسترات وملصقات', is_default: false }
        ];

        // إرسال طلب لإنشاء أنواع المنتجات
        fetch(this.config.apiBaseUrl + 'create-default-product-types/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify({ product_types: defaultTypes })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log('✅ تم إنشاء أنواع المنتجات الافتراضية بنجاح');
                // مسح التخزين المؤقت لإعادة تحميل البيانات الجديدة
                this.clearCache('product-types');
            } else {
                console.warn('⚠️ فشل في إنشاء أنواع المنتجات الافتراضية:', data.error);
            }
        })
        .catch(error => {
            console.warn('⚠️ خطأ في إنشاء أنواع المنتجات الافتراضية:', error);
        });
    },

    /**
     * الحصول على CSRF Token
     */
    getCSRFToken: function() {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
        return csrfToken ? csrfToken.value : '';
    },

    /**
     * ملء حقل نوع المنتج بالبيانات
     */
    populateProductTypeField: function(field, productTypes) {
        // مسح الخيارات الموجودة
        field.empty();
        
        // إضافة خيار فارغ
        field.append(new Option('-- اختر نوع المنتج --', '', false, false));
        
        // إضافة أنواع المنتجات
        productTypes.forEach(productType => {
            const option = new Option(
                productType.text || productType.name, 
                productType.id, 
                productType.is_default || false, 
                productType.is_default || false
            );
            field.append(option);
        });

        // تحديث Select2
        field.trigger('change');
        
        console.log(`✅ تم تحميل ${productTypes.length} نوع منتج`);
    },

    /**
     * معالج تغيير نوع المنتج
     */
    onProductTypeChange: function(value, text) {
        // إطلاق حدث مخصص
        $(document).trigger('product-type:changed', { value, text });
    },

    /**
     * معالج مسح نوع المنتج
     */
    onProductTypeClear: function() {
        // إطلاق حدث مخصص
        $(document).trigger('product-type:cleared');
    },

    /**
     * تهيئة حقل مقاس المنتج
     */
    initProductSizeField: function() {
        const productSizeField = $('#id_product_size');
        if (!productSizeField.length) {
            console.warn('⚠️ حقل مقاس المنتج غير موجود');
            return;
        }

        console.log('🔧 تهيئة حقل مقاس المنتج...');

        // جلب مقاسات المنتجات من API
        this.loadProductSizes()
            .then(data => {
                if (data.success) {
                    this.populateProductSizeField(productSizeField, data.results);
                } else {
                    console.error('خطأ في جلب مقاسات المنتجات:', data.error);
                    if (typeof showPricingNotification !== 'undefined') {
                        showPricingNotification('فشل في تحميل مقاسات المنتجات', 'error');
                    }
                }
            })
            .catch(error => {
                console.error('خطأ في API مقاسات المنتجات:', error);
                if (typeof showPricingNotification !== 'undefined') {
                    showPricingNotification('خطأ في الاتصال بالخادم', 'error');
                }
            });

        // معالج تغيير مقاس المنتج
        productSizeField.on('change', (e) => {
            const selectedValue = e.target.value;
            
            // التحقق من وجود قيمة أولاً
            if (!selectedValue) {
                console.log('📏 تم مسح اختيار مقاس المنتج');
                return;
            }
            
            const selectedOption = e.target.options[e.target.selectedIndex];
            
            // التحقق من وجود الخيار المحدد مع معالجة أفضل
            if (!selectedOption || selectedOption.selectedIndex === -1) {
                console.log('📏 مقاس المنتج محدد لكن الخيار غير متاح حالياً:', selectedValue);
                // محاولة العثور على الخيار بالقيمة
                const optionByValue = Array.from(e.target.options).find(opt => opt.value === selectedValue);
                if (optionByValue) {
                    console.log('📏 تم العثور على الخيار بالقيمة:', optionByValue.text);
                    this.handleProductSizeChange(selectedValue, optionByValue.text, {});
                }
                return;
            }
            
            const selectedText = selectedOption.text || selectedOption.textContent || 'غير محدد';
            
            // الحصول على البيانات الإضافية من data attributes (بشكل آمن)
            const width = selectedOption.dataset ? selectedOption.dataset.width : null;
            const height = selectedOption.dataset ? selectedOption.dataset.height : null;
            
            console.log('📏 تم تغيير مقاس المنتج:', selectedText);
            this.handleProductSizeChange(selectedValue, selectedText, { width, height });
        });

        console.log('✅ تم تهيئة حقل مقاس المنتج بنجاح');
    },

    /**
     * جلب مقاسات المنتجات من API
     */
    loadProductSizes: function() {
        return fetch(this.config.apiBaseUrl + 'get-product-sizes/', {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin'
        })
        .then(response => response.json());
    },

    /**
     * ملء حقل مقاس المنتج بالبيانات
     */
    populateProductSizeField: function(field, productSizes) {
        // مسح الخيارات الموجودة (عدا الخيار الفارغ)
        field.find('option:not([value=""])').remove();
        
        // إضافة الخيارات الجديدة
        productSizes.forEach(productSize => {
            const option = new Option(productSize.text, productSize.id, productSize.is_default, productSize.is_default);
            
            // إضافة بيانات إضافية كـ data attributes
            option.dataset.width = productSize.width;
            option.dataset.height = productSize.height;
            option.dataset.dimensions = productSize.dimensions;
            
            field.append(option);
        });

        // إضافة خيار "مقاس مخصص" في النهاية
        const customOption = new Option('مقاس مخصص', 'custom', false, false);
        customOption.dataset.width = '';
        customOption.dataset.height = '';
        customOption.dataset.dimensions = '';
        field.append(customOption);

        // تحديث العرض
        field.trigger('change');
        
        console.log(`✅ تم تحميل ${productSizes.length} مقاس منتج + خيار مخصص`);
    },

    /**
     * معالجة تغيير مقاس المنتج
     */
    handleProductSizeChange: function(value, text, dimensions) {
        const widthField = $('#id_product_width');
        const heightField = $('#id_product_height');
        
        if (!widthField.length || !heightField.length) {
            console.warn('⚠️ حقول الأبعاد غير موجودة');
            return;
        }

        if (value === 'custom') {
            // مقاس مخصص - تفريغ الحقول وإزالة readonly
            widthField.val('').prop('readonly', false);
            heightField.val('').prop('readonly', false);
            
            console.log('📝 تم تفعيل وضع المقاس المخصص');
        } else if (value && dimensions.width && dimensions.height) {
            // مقاس عادي - ملء الحقول وجعلها readonly
            widthField.val(dimensions.width).prop('readonly', true);
            heightField.val(dimensions.height).prop('readonly', true);
            
            console.log(`📏 تم تحديد المقاس: ${dimensions.width} × ${dimensions.height} سم`);
        } else {
            // لا يوجد اختيار - تفريغ الحقول وجعلها readonly
            widthField.val('').prop('readonly', true);
            heightField.val('').prop('readonly', true);
            
            console.log('🔄 تم مسح أبعاد المقاس');
        }

        // إطلاق حدث مخصص
        this.onProductSizeChange(value, text, dimensions);
    },

    /**
     * معالج تغيير مقاس المنتج (حدث مخصص)
     */
    onProductSizeChange: function(value, text, dimensions) {
        // إطلاق حدث مخصص
        $(document).trigger('product-size:changed', { value, text, dimensions });
    },

    /**
     * تهيئة حقل اتجاه الطباعة
     */
    initPrintDirectionField: function() {
        const printDirectionField = $('#id_print_direction');
        if (!printDirectionField.length) {
            console.warn('⚠️ حقل اتجاه الطباعة غير موجود');
            return;
        }

        console.log('🔧 تهيئة حقل اتجاه الطباعة...');

        // معالج تغيير اتجاه الطباعة
        printDirectionField.on('change', (e) => {
            const selectedValue = e.target.value;
            const selectedText = e.target.options[e.target.selectedIndex].text;
            
            console.log('🔄 تم تغيير اتجاه الطباعة:', selectedText);
            this.handlePrintDirectionChange(selectedValue, selectedText);
        });

        // الاستماع لتغييرات أبعاد المنتج
        $(document).on('product-size:changed', (e, data) => {
            this.handleDimensionsChange(data);
        });

        console.log('✅ تم تهيئة حقل اتجاه الطباعة بنجاح');
    },

    /**
     * معالجة تغيير اتجاه الطباعة
     */
    handlePrintDirectionChange: function(direction, directionText) {
        const widthField = $('#id_product_width');
        const heightField = $('#id_product_height');
        
        if (!widthField.length || !heightField.length) {
            console.warn('⚠️ حقول الأبعاد غير موجودة');
            return;
        }

        // الحصول على القيم الحالية
        const currentWidth = parseFloat(widthField.val()) || 0;
        const currentHeight = parseFloat(heightField.val()) || 0;

        // التحقق من وجود قيم
        if (currentWidth > 0 && currentHeight > 0) {
            // حفظ حالة readonly الأصلية
            const wasWidthReadonly = widthField.prop('readonly');
            const wasHeightReadonly = heightField.prop('readonly');
            
            // عكس الأبعاد حسب الاتجاه المطلوب
            if (direction === 'landscape' && currentWidth < currentHeight) {
                // إزالة readonly مؤقتاً للتعديل
                widthField.prop('readonly', false);
                heightField.prop('readonly', false);
                
                // مثال: كان 21×30 (عمودي) → يصبح 30×21 (أفقي)
                widthField.val(currentHeight);
                heightField.val(currentWidth);
                
                // إعادة readonly للحالة الأصلية
                widthField.prop('readonly', wasWidthReadonly);
                heightField.prop('readonly', wasHeightReadonly);
                
                console.log(`🔄 عكس للأفقي: ${currentWidth}×${currentHeight} → ${currentHeight}×${currentWidth}`);
            } else if (direction === 'portrait' && currentWidth > currentHeight) {
                // إزالة readonly مؤقتاً للتعديل
                widthField.prop('readonly', false);
                heightField.prop('readonly', false);
                
                // مثال: كان 30×21 (أفقي) → يصبح 21×30 (عمودي)
                widthField.val(currentHeight);
                heightField.val(currentWidth);
                
                // إعادة readonly للحالة الأصلية
                widthField.prop('readonly', wasWidthReadonly);
                heightField.prop('readonly', wasHeightReadonly);
                
                console.log(`🔄 عكس للعمودي: ${currentWidth}×${currentHeight} → ${currentHeight}×${currentWidth}`);
            } else {
                console.log(`✅ الاتجاه متطابق مع الأبعاد الحالية: ${currentWidth}×${currentHeight}`);
            }
        }

        // إطلاق حدث مخصص
        $(document).trigger('print-direction:changed', { direction, directionText });
    },

    /**
     * معالجة تغيير أبعاد المنتج (للتحقق من الاتجاه)
     */
    handleDimensionsChange: function(data) {
        const printDirectionField = $('#id_print_direction');
        
        if (!printDirectionField.length || !data.dimensions) {
            return;
        }

        const width = parseFloat(data.dimensions.width) || 0;
        const height = parseFloat(data.dimensions.height) || 0;

        if (width > 0 && height > 0) {
            // تحديد الاتجاه المناسب تلقائياً
            const suggestedDirection = width > height ? 'landscape' : 'portrait';
            const currentDirection = printDirectionField.val();

            // اقتراح تغيير الاتجاه إذا كان مختلفاً
            if (currentDirection !== suggestedDirection) {
                printDirectionField.val(suggestedDirection);
                
                const directionText = suggestedDirection === 'landscape' ? 'أفقي' : 'عمودي';
                console.log(`💡 تم اقتراح الاتجاه: ${directionText} (${width} × ${height})`);
                
                // إطلاق حدث التغيير
                printDirectionField.trigger('change');
            }
        }
    },

    /**
     * تهيئة الحقول القابلة للإظهار/الإخفاء
     */
    initToggleFields: function() {
        console.log('🔧 تهيئة الحقول القابلة للإظهار/الإخفاء...');
        
        // تهيئة checkbox المحتوى الداخلي
        this.initInternalContentToggle();
        
        // تهيئة checkbox المقاس المفتوح
        this.initOpenSizeToggle();
        
        console.log('✅ تم تهيئة الحقول القابلة للإظهار/الإخفاء بنجاح');
    },

    /**
     * تهيئة معالج المحتوى الداخلي
     */
    initInternalContentToggle: function() {
        const checkbox = $('#id_has_internal_content');
        const targetSection = $('#internal-content-section');
        
        if (!checkbox.length) {
            console.warn('⚠️ checkbox المحتوى الداخلي غير موجود');
            return;
        }
        
        if (!targetSection.length) {
            console.warn('⚠️ قسم المحتوى الداخلي غير موجود');
            return;
        }

        // إخفاء القسم والخطوة افتراضياً
        targetSection.hide();
        $('.step[data-step="3"]').hide();
        
        // معالج تغيير الحالة
        checkbox.on('change', (e) => {
            const isChecked = e.target.checked;
            
            if (isChecked) {
                targetSection.slideDown(300);
                console.log('📖 تم إظهار قسم المحتوى الداخلي');
                this.updateSectionLabels(true);
            } else {
                targetSection.slideUp(300);
                console.log('📖 تم إخفاء قسم المحتوى الداخلي');
                this.updateSectionLabels(false);
            }
            
            // إطلاق حدث مخصص
            $(document).trigger('internal-content:toggled', { isVisible: isChecked });
        });

        // تطبيق الحالة الأولية إذا كان محدد مسبقاً
        if (checkbox.prop('checked')) {
            targetSection.show();
            this.updateSectionLabels(true);
            console.log('📖 قسم المحتوى الداخلي مفعل مسبقاً');
        } else {
            this.updateSectionLabels(false);
        }
        
        console.log('✅ تم تهيئة معالج المحتوى الداخلي');
    },

    /**
     * تحديث تسميات وأرقام الأقسام حسب حالة المحتوى الداخلي
     */
    updateSectionLabels: function(hasInternalContent) {
        // تحديث تسمية القسم الثاني (data-step="2")
        const section2Title = $('.step[data-step="2"] .step-title');
        if (section2Title.length) {
            if (hasInternalContent) {
                section2Title.text('تفاصيل الغلاف');
            } else {
                section2Title.text('تفاصيل الطباعة');
            }
        }

        // إظهار/إخفاء القسم الثالث وتحديث أرقام الخطوات
        const step3 = $('.step[data-step="3"]');
        const step4 = $('.step[data-step="4"]');
        const section3Content = $('#internal-content-section');
        
        if (hasInternalContent) {
            // إظهار القسم الثالث
            step3.show();
            section3Content.show();
            
            // تحديث أرقام الخطوات: 1, 2, 3, 4
            $('.step[data-step="1"] .step-number').text('1');
            $('.step[data-step="2"] .step-number').text('2');
            $('.step[data-step="3"] .step-number').text('3');
            $('.step[data-step="4"] .step-number').text('4');
            
            console.log('🏷️ تم تفعيل المحتوى الداخلي - 4 خطوات');
        } else {
            // إخفاء القسم الثالث
            step3.hide();
            section3Content.hide();
            
            // تحديث أرقام الخطوات: 1, 2, 3 (بدون القسم الثالث)
            $('.step[data-step="1"] .step-number').text('1');
            $('.step[data-step="2"] .step-number').text('2');
            $('.step[data-step="4"] .step-number').text('3'); // القسم الرابع يصبح الثالث
            
            console.log('🏷️ تم تعطيل المحتوى الداخلي - 3 خطوات');
        }

        console.log(`🏷️ تم تحديث تسميات الأقسام - المحتوى الداخلي: ${hasInternalContent ? 'مفعل' : 'معطل'}`);
    },

    /**
     * تهيئة معالج المقاس المفتوح
     */
    initOpenSizeToggle: function() {
        const checkbox = $('#use-open-size');
        const targetFields = $('#open-size-fields');
        
        if (!checkbox.length) {
            console.warn('⚠️ checkbox المقاس المفتوح غير موجود');
            return;
        }
        
        if (!targetFields.length) {
            console.warn('⚠️ حقول المقاس المفتوح غير موجودة');
            return;
        }

        // إخفاء الحقول افتراضياً
        targetFields.hide();
        
        // معالج تغيير الحالة
        checkbox.on('change', (e) => {
            const isChecked = e.target.checked;
            
            if (isChecked) {
                targetFields.slideDown(300);
                console.log('📐 تم إظهار حقول المقاس المفتوح');
            } else {
                targetFields.slideUp(300);
                console.log('📐 تم إخفاء حقول المقاس المفتوح');
            }
            
            // إطلاق حدث مخصص
            $(document).trigger('open-size:toggled', { isVisible: isChecked });
        });

        // تطبيق الحالة الأولية إذا كان محدد مسبقاً
        if (checkbox.prop('checked')) {
            targetFields.show();
            console.log('📐 حقول المقاس المفتوح مفعلة مسبقاً');
        }
        
        console.log('✅ تم تهيئة معالج المقاس المفتوح');
    },

    /**
     * تهيئة نظام التحقق من صحة النموذج
     */
    initFormValidation: function() {
        console.log('🔧 تهيئة نظام التحقق من صحة النموذج...');
        
        // إضافة معالج للنموذج عند الإرسال
        const form = $('form');
        if (form.length) {
            form.on('submit', (e) => {
                if (!this.validateForm()) {
                    e.preventDefault();
                    return false;
                }
            });
        }

        // إضافة معالج لأزرار الانتقال بين الأقسام
        $('.btn-next').on('click', (e) => {
            const currentSection = $('.form-section.active').data('section');
            if (!this.validateSection(currentSection)) {
                e.preventDefault();
                return false;
            }
        });

        // إضافة زر للتحقق السريع من البيانات
        this.addQuickValidationButton();

        console.log('✅ تم تهيئة نظام التحقق من صحة النموذج');
    },

    /**
     * إضافة زر للتحقق السريع من البيانات
     */
    addQuickValidationButton: function() {
        // البحث عن مكان مناسب لإضافة الزر
        const formActions = $('.form-actions, .card-footer, .btn-group').first();
        
        if (formActions.length) {
            const validateBtn = $(`
                <button type="button" class="btn btn-outline-warning btn-sm me-2" id="quick-validate-btn">
                    <i class="fas fa-check-circle"></i> التحقق من البيانات
                </button>
            `);
            
            formActions.prepend(validateBtn);
            
            // إضافة معالج للزر
            validateBtn.on('click', () => {
                this.performQuickValidation();
            });
        }
    },

    /**
     * تنفيذ التحقق السريع
     */
    performQuickValidation: function() {
        const missingFields = this.getMissingRequiredFields();
        
        if (missingFields.length === 0) {
            // جميع الحقول مكتملة
            if (typeof showPricingNotification !== 'undefined') {
                showPricingNotification('جميع البيانات المطلوبة مكتملة!', 'success', 'تحقق ناجح');
            }
            
            console.log('✅ جميع البيانات المطلوبة مكتملة');
        } else {
            // هناك حقول مفقودة
            this.showMissingFieldsNotification(missingFields);
            this.focusOnFirstMissingField(missingFields[0]);
        }
    },

    /**
     * التحقق من صحة النموذج كاملاً
     */
    validateForm: function() {
        const missingFields = this.getMissingRequiredFields();
        
        if (missingFields.length > 0) {
            this.showMissingFieldsNotification(missingFields);
            this.focusOnFirstMissingField(missingFields[0]);
            return false;
        }
        
        return true;
    },

    /**
     * التحقق من صحة قسم معين
     */
    validateSection: function(sectionNumber) {
        const missingFields = this.getMissingRequiredFieldsInSection(sectionNumber);
        
        if (missingFields.length > 0) {
            this.showMissingFieldsNotification(missingFields);
            this.focusOnFirstMissingField(missingFields[0]);
            return false;
        }
        
        return true;
    },

    /**
     * الحصول على قائمة الحقول المطلوبة المفقودة
     */
    getMissingRequiredFields: function() {
        const requiredFields = [
            { id: 'id_client', name: 'العميل', section: 1 },
            { id: 'id_title', name: 'عنوان الطلب', section: 1 },
            { id: 'id_product_type', name: 'نوع المنتج', section: 1 },
            { id: 'id_quantity', name: 'الكمية', section: 1 },
            { id: 'id_product_size', name: 'مقاس المنتج', section: 1 },
            { id: 'id_order_type', name: 'نوع الطباعة', section: 2 },
            { id: 'id_sides', name: 'عدد الأوجه', section: 2 }
        ];

        const missingFields = [];

        requiredFields.forEach(field => {
            const element = $(`#${field.id}`);
            if (element.length) {
                const value = element.val();
                const isEmpty = !value || value.trim() === '' || value === 'null' || value === 'undefined';
                
                if (isEmpty) {
                    missingFields.push(field);
                }
            }
        });

        return missingFields;
    },

    /**
     * الحصول على قائمة الحقول المطلوبة المفقودة في قسم معين
     */
    getMissingRequiredFieldsInSection: function(sectionNumber) {
        const allMissingFields = this.getMissingRequiredFields();
        return allMissingFields.filter(field => field.section === parseInt(sectionNumber));
    },

    /**
     * عرض إشعار بالحقول المفقودة
     */
    showMissingFieldsNotification: function(missingFields) {
        // إنشاء قائمة بأسماء الحقول المفقودة
        const fieldNames = missingFields.map(field => field.name).join('، ');
        
        // إنشاء رسالة الإشعار
        const message = `يرجى إكمال الحقول التالية: ${fieldNames}`;
        
        // عرض الإشعار باستخدام النظام الموحد
        if (typeof showPricingNotification !== 'undefined') {
            showPricingNotification(message, 'warning', 'بيانات مطلوبة مفقودة');
        }

        console.warn('⚠️ حقول مطلوبة مفقودة:', missingFields.map(f => f.name));
    },

    /**
     * التركيز على أول حقل مفقود
     */
    focusOnFirstMissingField: function(field) {
        const element = $(`#${field.id}`);
        
        if (element.length) {
            // الانتقال إلى القسم المناسب إذا لم يكن مرئياً
            this.navigateToSection(field.section);
            
            // انتظار قصير للسماح بالانتقال
            setTimeout(() => {
                // التمرير إلى الحقل
                element[0].scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'center' 
                });
                
                // التركيز على الحقل
                if (element.hasClass('select2-hidden-accessible')) {
                    // إذا كان Select2، افتح القائمة
                    element.select2('open');
                } else {
                    // حقل عادي
                    element.focus();
                }
                
                // إضافة تأثير بصري للحقل
                this.highlightField(element);
                
                console.log(`🎯 تم التركيز على الحقل: ${field.name}`);
            }, 300);
        }
    },

    /**
     * الانتقال إلى قسم معين
     */
    navigateToSection: function(sectionNumber) {
        // إخفاء جميع الأقسام
        $('.form-section').removeClass('active').hide();
        
        // إظهار القسم المطلوب
        $(`.form-section[data-section="${sectionNumber}"]`).addClass('active').show();
        
        // تحديث مؤشر الخطوات
        $('.step').removeClass('active');
        $(`.step[data-step="${sectionNumber}"]`).addClass('active');
        
        console.log(`📍 تم الانتقال إلى القسم ${sectionNumber}`);
    },

    /**
     * إضافة تأثير بصري للحقل
     */
    highlightField: function(element) {
        // إضافة class للتأثير البصري
        element.addClass('field-highlight');
        
        // إزالة التأثير بعد 3 ثوانٍ
        setTimeout(() => {
            element.removeClass('field-highlight');
        }, 3000);
    },


    /**
     * نظام الحفظ التلقائي
     */
    initAutoSave: function() {
        console.log('💾 تهيئة نظام الحفظ التلقائي...');
        
        const self = this;
        this.autoSave = {
            enabled: true,
            timer: null,
            isDirty: false,
            
            start: function() {
                if (!self.autoSave.enabled) return;
                
                // بدء مؤقت الحفظ التلقائي
                self.autoSave.timer = setInterval(function() {
                    if (self.autoSave.isDirty) {
                        self.saveFormState();
                    }
                }, self.config.autoSaveInterval);
                
                // إعداد معالجات التغيير مع debounce
                self.config.autoSaveFields.forEach(function(fieldName) {
                    const element = $(`#id_${fieldName}`);
                    if (element.length) {
                        // استخدام debounce لتقليل عدد مرات الحفظ
                        let saveTimeout;
                        element.on('change input', function() {
                            self.autoSave.isDirty = true;
                            
                            // إلغاء المؤقت السابق
                            clearTimeout(saveTimeout);
                            
                            // تأخير إظهار المؤشر لتجنب الإزعاج
                            saveTimeout = setTimeout(() => {
                                if (self.autoSave.isDirty) {
                                    self.showSaveIndicator();
                                }
                            }, 500); // تأخير نصف ثانية
                        });
                    }
                });
                
                // معالجة خاصة لحقل الوصف (له ID ديناميكي)
                const descriptionField = $('textarea[name="description"]');
                if (descriptionField.length) {
                    let saveTimeout;
                    descriptionField.on('change input', function() {
                        self.autoSave.isDirty = true;
                        
                        // إلغاء المؤقت السابق
                        clearTimeout(saveTimeout);
                        
                        // تأخير إظهار المؤشر لتجنب الإزعاج
                        saveTimeout = setTimeout(() => {
                            if (self.autoSave.isDirty) {
                                self.showSaveIndicator();
                            }
                        }, 500);
                    });
                }
                
                // معالجة الحقول الخاصة (بمعرفات مخصصة)
                self.config.specialFields.forEach(function(fieldName) {
                    const element = $(`#${fieldName}`);
                    if (element.length) {
                        let saveTimeout;
                        element.on('change input', function() {
                            self.autoSave.isDirty = true;
                            
                            // إلغاء المؤقت السابق
                            clearTimeout(saveTimeout);
                            
                            // تأخير إظهار المؤشر لتجنب الإزعاج
                            saveTimeout = setTimeout(() => {
                                if (self.autoSave.isDirty) {
                                    self.showSaveIndicator();
                                }
                            }, 500);
                        });
                        console.log(`✅ تم تفعيل الحفظ التلقائي للحقل الخاص: ${fieldName}`);
                    }
                });
                
                console.log('✅ تم تفعيل الحفظ التلقائي');
            }
        };
        
        // استعادة البيانات المحفوظة (بتأخير أكبر لضمان تحميل جميع الخيارات)
        setTimeout(() => {
            this.restoreFormState();
        }, 2500); // تأخير أكبر لضمان تحميل خيارات مقاس المنتج
        
        // بدء النظام
        this.autoSave.start();
    },

    /**
     * حفظ حالة النموذج
     */
    saveFormState: function() {
        try {
            const formData = {};
            this.config.autoSaveFields.forEach(fieldName => {
                const element = $(`#id_${fieldName}`);
                if (element.length) {
                    // معالجة خاصة لحقول Select2
                    if (element.hasClass('select2-hidden-accessible')) {
                        const selectedData = element.select2('data');
                        if (selectedData && selectedData.length > 0) {
                            formData[fieldName] = {
                                value: selectedData[0].id,
                                text: selectedData[0].text,
                                isSelect2: true
                            };
                        }
                    } else {
                        // معالجة خاصة للـ checkboxes
                        if (element.is(':checkbox')) {
                            const isChecked = element.prop('checked');
                            formData[fieldName] = {
                                value: isChecked,
                                isSelect2: false,
                                isCheckbox: true
                            };
                            console.log(`💾 حفظ checkbox ${fieldName}:`, isChecked);
                        } else {
                            // الحقول العادية الأخرى
                            const value = element.val();
                            if (value !== null && value !== undefined && value !== '') {
                                formData[fieldName] = {
                                    value: value,
                                    isSelect2: false
                                };
                            }
                        }
                    }
                }
            });
            
            // معالجة الحقول الخاصة (بمعرفات مخصصة)
            this.config.specialFields.forEach(fieldName => {
                const element = $(`#${fieldName}`);
                if (element.length) {
                    if (element.is(':checkbox')) {
                        const isChecked = element.prop('checked');
                        formData[fieldName] = {
                            value: isChecked,
                            isSelect2: false,
                            isCheckbox: true,
                            isSpecial: true
                        };
                        console.log(`💾 حفظ special checkbox ${fieldName}:`, isChecked);
                    } else {
                        const value = element.val();
                        if (value !== null && value !== undefined && value !== '') {
                            formData[fieldName] = {
                                value: value,
                                isSelect2: false,
                                isSpecial: true
                            };
                        }
                    }
                }
            });
            
            // معالجة خاصة لحقل الوصف
            const descriptionField = $('textarea[name="description"]');
            if (descriptionField.length && descriptionField.val()) {
                formData['description'] = {
                    value: descriptionField.val(),
                    isSelect2: false
                };
            }
            
            localStorage.setItem('printing_form_draft', JSON.stringify({
                data: formData,
                timestamp: Date.now(),
                url: window.location.href
            }));
            
            this.autoSave.isDirty = false;
            this.showSaveSuccess();
            
            console.log('💾 تم حفظ حالة النموذج:', formData);
            
            // إظهار رسالة مفصلة عن ما تم حفظه
            const savedFields = Object.keys(formData);
            if (savedFields.length > 0) {
                console.log(`📝 تم حفظ ${savedFields.length} حقل: ${savedFields.join(', ')}`);
            }
        } catch (error) {
            console.error('❌ خطأ في الحفظ التلقائي:', error);
        }
    },

    /**
     * استعادة حالة النموذج
     */
    restoreFormState: function() {
        try {
            const saved = localStorage.getItem('printing_form_draft');
            if (saved) {
                const draft = JSON.parse(saved);
                const age = Date.now() - draft.timestamp;
                
                // استعادة البيانات إذا كانت أحدث من ساعة واحدة
                if (age < 3600000 && draft.url === window.location.href) {
                    console.log('🔄 بدء استعادة البيانات المحفوظة...');
                    
                    // إعطاء أولوية لاستعادة الحقول التي لا تعتمد على APIs
                    const priorityFields = ['title', 'quantity', 'has_internal_content', 'open_size_width', 'open_size_height', 'internal_page_count', 'binding_side'];
                    const apiDependentFields = ['client', 'product_type', 'product_size'];
                    const hiddenFields = ['use-open-size']; // الحقول المخفية داخل أقسام
                    
                    // استعادة الحقول ذات الأولوية أولاً
                    priorityFields.forEach(fieldName => {
                        if (draft.data[fieldName]) {
                            this.restoreField(fieldName, draft.data[fieldName]);
                        }
                    });
                    
                    // تأخير استعادة الحقول التي تعتمد على APIs
                    setTimeout(() => {
                        apiDependentFields.forEach(fieldName => {
                            if (draft.data[fieldName]) {
                                this.restoreField(fieldName, draft.data[fieldName]);
                            }
                        });
                    }, 1000);
                    
                    // تأخير أكبر لاستعادة الحقول المخفية داخل الأقسام
                    setTimeout(() => {
                        hiddenFields.forEach(fieldName => {
                            if (draft.data[fieldName]) {
                                this.restoreSpecialField(fieldName, draft.data[fieldName]);
                            }
                        });
                    }, 2000); // تأخير أكبر لضمان ظهور الأقسام
                    
                    // استعادة حقل الوصف (معالجة خاصة)
                    if (draft.data['description']) {
                        const descriptionField = $('textarea[name="description"]');
                        if (descriptionField.length) {
                            descriptionField.val(draft.data['description'].value);
                            console.log('🔄 تم استعادة حقل الوصف');
                        }
                    }
                    
                    this.showRestoreNotification();
                    console.log('📋 تم استعادة البيانات المحفوظة');
                }
            }
        } catch (error) {
            console.error('❌ خطأ في استعادة البيانات:', error);
        }
    },

    /**
     * استعادة حقل واحد
     */
    restoreField: function(fieldName, fieldData) {
        const element = $(`#id_${fieldName}`);
        
        if (!element.length || !fieldData) {
            return;
        }
        
        try {
            if (fieldData.isSelect2) {
                // استعادة حقول Select2
                console.log(`🔄 استعادة Select2 ${fieldName}:`, fieldData);
                
                // التحقق من وجود الخيار أولاً
                const existingOption = element.find(`option[value="${fieldData.value}"]`);
                if (existingOption.length === 0) {
                    // إنشاء خيار جديد وإضافته
                    const option = new Option(fieldData.text, fieldData.value, true, true);
                    element.append(option);
                } else {
                    // استخدام الخيار الموجود
                    element.val(fieldData.value);
                }
                
                // تحديث Select2
                element.trigger('change');
            } else {
                // معالجة خاصة للـ checkboxes
                if (fieldData.isCheckbox) {
                    element.prop('checked', fieldData.value);
                    console.log(`🔄 استعادة checkbox ${fieldName}:`, fieldData.value);
                } else {
                    // استعادة الحقول العادية
                    element.val(fieldData.value);
                    
                    // التحقق من نجاح الاستعادة
                    if (element.val() !== fieldData.value) {
                        console.warn(`⚠️ فشل في استعادة ${fieldName}، الخيار غير متاح:`, fieldData.value);
                        return; // تخطي trigger إذا فشلت الاستعادة
                    }
                }
                
                // تأخير trigger لضمان تحميل البيانات أولاً
                setTimeout(() => {
                    element.trigger('change');
                    
                    // معالجة خاصة لحقل المحتوى الداخلي
                    if (fieldName === 'has_internal_content') {
                        const isChecked = element.prop('checked');
                        this.updateSectionLabels(isChecked);
                        
                        // إظهار/إخفاء القسم مع الرسوم المتحركة
                        const targetSection = $('#internal-content-section');
                        if (isChecked) {
                            targetSection.slideDown(300);
                        } else {
                            targetSection.slideUp(300);
                        }
                    }
                }, 300);
            }
        } catch (error) {
            console.warn(`⚠️ تعذر استعادة حقل ${fieldName}:`, error);
        }
    },

    /**
     * استعادة حقل خاص (بمعرف مخصص)
     */
    restoreSpecialField: function(fieldName, fieldData) {
        const element = $(`#${fieldName}`);
        
        if (!element.length || !fieldData) {
            console.warn(`⚠️ لم يتم العثور على الحقل الخاص: ${fieldName}`);
            return;
        }
        
        try {
            if (fieldData.isCheckbox) {
                element.prop('checked', fieldData.value);
                console.log(`🔄 استعادة special checkbox ${fieldName}:`, fieldData.value);
                
                // تأخير trigger لضمان تحميل البيانات أولاً
                setTimeout(() => {
                    element.trigger('change');
                    
                    // معالجة خاصة لـ use-open-size
                    if (fieldName === 'use-open-size') {
                        const isChecked = element.prop('checked');
                        const targetFields = $('#open-size-fields');
                        if (isChecked) {
                            targetFields.slideDown(300);
                        } else {
                            targetFields.slideUp(300);
                        }
                        console.log(`🔄 تم تطبيق حالة المقاس المفتوح: ${isChecked}`);
                    }
                }, 300);
            } else {
                element.val(fieldData.value);
                setTimeout(() => {
                    element.trigger('change');
                }, 300);
            }
        } catch (error) {
            console.warn(`⚠️ تعذر استعادة الحقل الخاص ${fieldName}:`, error);
        }
    },

    /**
     * إظهار مؤشر الحفظ
     */
    showSaveIndicator: function() {
        // إزالة أي مؤشر سابق
        $('#auto-save-indicator').remove();
        
        // إنشاء مؤشر جديد بتصميم أقل إزعاجاً
        const indicator = $(`
            <div id="auto-save-indicator" class="position-fixed" style="bottom: 20px; left: 20px; z-index: 1050;">
                <div class="badge bg-secondary bg-opacity-75 text-white" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">
                    <i class="fas fa-save me-1"></i>حفظ تلقائي...
                </div>
            </div>
        `);
        
        $('body').append(indicator);
        
        // إخفاء المؤشر تلقائياً بعد ثانية واحدة
        setTimeout(() => {
            indicator.fadeOut(300);
        }, 1000);
    },

    /**
     * إظهار نجاح الحفظ
     */
    showSaveSuccess: function() {
        // إزالة أي مؤشر سابق
        $('#auto-save-indicator').remove();
        
        // إنشاء مؤشر نجاح بسيط
        const successIndicator = $(`
            <div id="auto-save-indicator" class="position-fixed" style="bottom: 20px; left: 20px; z-index: 1050;">
                <div class="badge bg-success bg-opacity-90 text-white" style="font-size: 0.75rem; padding: 0.25rem 0.5rem;">
                    <i class="fas fa-check me-1"></i>محفوظ
                </div>
            </div>
        `);
        
        $('body').append(successIndicator);
        
        // إخفاء المؤشر بعد ثانيتين
        setTimeout(() => {
            successIndicator.fadeOut(300, function() {
                $(this).remove();
            });
        }, 1500);
    },

    /**
     * إظهار إشعار الاستعادة
     */
    showRestoreNotification: function() {
        if (typeof showPricingNotification !== 'undefined') {
            showPricingNotification('تم استعادة البيانات المحفوظة مسبقاً', 'info', 'استعادة البيانات');
        }
    },

    /**
     * تنظيف الموارد
     */
    destroy: function() {
        // تنظيف Select2 للعميل
        const clientField = $('#id_client');
        if (clientField.hasClass('select2-hidden-accessible')) {
            clientField.select2('destroy');
        }
        // تنظيف Select2 لنوع المنتج
        const productTypeField = $('#id_product_type');
        if (productTypeField.hasClass('select2-hidden-accessible')) {
            productTypeField.select2('destroy');
        }

        // إزالة معالجات الأحداث
        $('#id_product_size').off('change');
        
        // تنظيف الحفظ التلقائي
        if (this.autoSave && this.autoSave.timer) {
            clearInterval(this.autoSave.timer);
        }
        
        console.log('🧹 تم تنظيف معالجات الحقول');
    }
};

// تهيئة تلقائية عند تحميل الصفحة
$(document).ready(function() {
    PrintingPricingSystem.FieldHandlers.init();
});

// تنظيف عند مغادرة الصفحة
window.addEventListener('beforeunload', function(e) {
    // حفظ البيانات قبل المغادرة
    if (PrintingPricingSystem.FieldHandlers.autoSave && PrintingPricingSystem.FieldHandlers.autoSave.isDirty) {
        PrintingPricingSystem.FieldHandlers.saveFormState();
    }
    
    // تنظيف الموارد
    PrintingPricingSystem.FieldHandlers.destroy();
});

// حفظ البيانات عند إرسال النموذج
$('form').on('submit', function() {
    // مسح المسودة عند الإرسال الناجح
    localStorage.removeItem('printing_form_draft');
    console.log('🗑️ تم مسح المسودة المحفوظة');
});
