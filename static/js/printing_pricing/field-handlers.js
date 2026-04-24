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
        requestTimeout: 10000, // 10 ثوانٍ
        // إعدادات التحقق
        validationDelay: 100,
        highlightDuration: 3000,
        // إعدادات الحفظ التلقائي
        autoSaveInterval: 30000, // 30 ثانية
        autoSaveFields: [
            'client', 'title', 'quantity', 'product_type', 'product_size', 'product_width', 'product_height',
            'order_type', 'has_internal_content', 'open_size_width', 'open_size_height',
            'internal_page_count', 'binding_side', 'print_sides', 'print_direction', 'colors_design',
            'colors_front', 'colors_back', 'design_price', 'supplier', 'press',
            'press_price_per_1000', 'press_runs', 'press_transportation', 'ctp_supplier', 'ctp_plate_size',
            'ctp_plates_count', 'ctp_transportation', 'internal_print_sides', 'internal_colors_design',
            'internal_colors_front', 'internal_colors_back', 'internal_design_price',
            'internal_ctp_supplier', 'internal_ctp_plate_size', 'internal_ctp_plates_count',
            'internal_ctp_transportation',
            // حقول الورق والمونتاج
            'piece_size', 'piece_width', 'piece_height', 'montage_count', 'montage_info',
            'paper_type', 'paper_supplier', 'paper_sheet_type', 'paper_weight', 'paper_origin',
            'paper_price', 'paper_sheets_count', 'paper_quantity', 'paper_total_cost'
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
        'product-sizes': { data: null, timestamp: 0 },
        'piece_size': { data: null, timestamp: 0 }
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
            this.cache[key] = { data: null, timestamp: 0 };
            return null;
        }
        
        return cached.data;
    },

    setCachedData: function(key, data) {
        this.cache[key] = {
            data: data,
            timestamp: Date.now()
        };
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
        
        this.initClientField();
        this.initProductTypeField();
        this.initProductSizeField();
        this.initPieceSizeField();
        this.initPrintDirectionField();
        this.initToggleFields();
        this.initPrintSidesField();
        this.initMontageInfoFields();
        this.initPressFields();
        this.initCTPFields();
        this.initPlatesCalculation();
        this.initPressRunsCalculation();
        this.initCTPCostCalculation();
        this.initPressCostCalculation();
        this.initPaperFields();
        this.initFinishingServices();
        this.initFormValidation();
        this.initAutoSave();
        this.setupGlobalSelect2Focus();
        
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
            this.onClientChange(selectedData);
            
            // تفعيل الحفظ التلقائي (بدون مؤشر فوري)
            if (this.autoSave) {
                this.autoSave.isDirty = true;
                // سيتم الحفظ في الدورة التالية للمؤقت
            }
        });

        clientField.on('select2:clear', () => {
            this.onClientClear();
            
            // تفعيل الحفظ التلقائي (بدون مؤشر فوري)
            if (this.autoSave) {
                this.autoSave.isDirty = true;
                // سيتم الحفظ في الدورة التالية للمؤقت
            }
        });

    },

    /**
     * تنسيق عرض خيار العميل في القائمة
     */
    formatClientOption: function(client) {
        if (client.loading) {
            return client.text;
        }

        // عرض النص كما هو من API (يحتوي على الكود + الاسم + الشركة)
        const $container = $(
            `<div class="select2-result-client">
                <div class="client-name">${client.text}</div>
            </div>`
        );

        return $container;
    },

    /**
     * تنسيق عرض العميل المختار (في الحقل بعد الاختيار)
     */
    formatClientSelection: function(client) {
        // عرض النص المركب من API فقط (لا تكرار)
        return client.text;
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
            this.onProductTypeChange(selectedData.id, selectedData.text);
            
            // تفعيل الحفظ التلقائي (بدون مؤشر فوري)
            if (this.autoSave) {
                this.autoSave.isDirty = true;
                // سيتم الحفظ في الدورة التالية للمؤقت
            }
        });

        productTypeField.on('select2:clear', () => {
            this.onProductTypeClear();
            
            // تفعيل الحفظ التلقائي (بدون مؤشر فوري)
            if (this.autoSave) {
                this.autoSave.isDirty = true;
                // سيتم الحفظ في الدورة التالية للمؤقت
            }
        });
    },

    /**
     * جلب أنواع المنتجات من API مع التخزين المؤقت
     */
    loadProductTypes: function() {
        // التحقق من وجود بيانات مخزنة مؤقتاً
        const cached = this.getCachedData('product-types');
        if (cached) {
            return Promise.resolve(cached);
        }

        const apiUrl = this.config.apiBaseUrl + 'get-product-types/';
        
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
                return;
            }
            
            const selectedOption = e.target.options[e.target.selectedIndex];
            
            // التحقق من وجود الخيار المحدد مع معالجة أفضل
            if (!selectedOption || selectedOption.selectedIndex === -1) {
                // محاولة العثور على الخيار بالقيمة
                const optionByValue = Array.from(e.target.options).find(opt => opt.value === selectedValue);
                if (optionByValue) {
                    this.handleProductSizeChange(selectedValue, optionByValue.text, {});
                }
                return;
            }
            
            const selectedText = selectedOption.text || selectedOption.textContent || 'غير محدد';
            
            // الحصول على البيانات الإضافية من data attributes (بشكل آمن)
            const width = selectedOption.dataset ? selectedOption.dataset.width : null;
            const height = selectedOption.dataset ? selectedOption.dataset.height : null;
            
            this.handleProductSizeChange(selectedValue, selectedText, { width, height });
        });

    },

    /**
     * تهيئة حقل مقاس القطع
     */
    initPieceSizeField: function() {
        console.log('🔧 تهيئة حقل مقاس القطع...');
        
        const pieceSizeField = $('#id_piece_size');
        
        if (!pieceSizeField.length) {
            console.warn('⚠️ حقل مقاس القطع غير موجود');
            return;
        }

        // تهيئة الحقل بحالة فارغة مع رسالة توضيحية
        pieceSizeField.find('option:not([value=""])').remove();
        pieceSizeField.find('option[value=""]').text('-- اختر مقاس الورق أولاً --');
        
        // تحميل أولي مع فلترة ذكية (سيتحقق من وجود مقاس الفرخ)
        this.updatePieceSizeOptions();

        // معالج تغيير مقاس القطع
        pieceSizeField.on('change', (e) => {
            const selectedValue = e.target.value;
            console.log('🔄 تم تغيير مقاس القطع:', selectedValue);
            
            if (!selectedValue) {
                console.log('⚠️ لم يتم اختيار مقاس قطع');
                return;
            }
            
            const selectedOption = e.target.options[e.target.selectedIndex];
            
            if (!selectedOption) {
                console.warn('⚠️ لا يمكن العثور على الخيار المحدد');
                return;
            }
            
            const selectedText = selectedOption.text || selectedOption.textContent || 'غير محدد';
            
            // الحصول على البيانات الإضافية من data attributes
            const width = selectedOption.dataset ? selectedOption.dataset.width : null;
            const height = selectedOption.dataset ? selectedOption.dataset.height : null;
            const paperType = selectedOption.dataset ? selectedOption.dataset.paperType : null;
            const name = selectedOption.dataset ? selectedOption.dataset.name : null;
            
            this.handlePieceSizeChange(selectedValue, selectedText, { width, height, paperType, name });
        });

        console.log('✅ تم تهيئة حقل مقاس القطع مع فلترة ذكية');
    },

    /**
     * تحديث خيارات مقاس القطع حسب الشروط المطلوبة
     */
    updatePieceSizeOptions: function() {
        console.log('🔄 تحديث خيارات مقاس القطع...');
        
        const pieceSizeField = $('#id_piece_size');
        const paperSheetTypeField = $('#id_paper_sheet_type');
        
        if (!pieceSizeField.length) {
            console.warn('⚠️ حقل مقاس القطع غير موجود');
            return;
        }

        // الحصول على القيم الحالية
        const paperSheetType = paperSheetTypeField.val();
        
        console.log('🔍 معايير الفلترة:', {
            paperSheetType: paperSheetType || 'غير محدد'
        });

        // التحقق من وجود مقاس الفرخ قبل تحميل البيانات
        if (!paperSheetType) {
            console.log('📋 اختر مقاس الورق أولاً لعرض مقاسات القطع المناسبة');
            // مسح الحقل وإضافة رسالة توضيحية
            pieceSizeField.find('option:not([value=""])').remove();
            pieceSizeField.find('option[value=""]').text('-- اختر مقاس الورق أولاً --');
            return;
        }

        // جلب مقاسات القطع مع الفلترة
        this.loadPieceSizes(paperSheetType)
            .then(data => {
                if (data.success) {
                    this.populatePieceSizeField(pieceSizeField, data.piece_sizes, data.status_message);
                    
                    // عرض رسالة توضيحية إذا لم توجد مقاسات
                    if (data.piece_sizes.length === 0) {
                        console.log('📋 لا توجد مقاسات قطع متاحة لمقاس الورق المحدد');
                    }
                }
            })
            .catch(error => {
                console.error('❌ خطأ في تحميل مقاسات القطع:', error);
                // إضافة خيار افتراضي في حالة الفشل
                pieceSizeField.find('option:not([value=""])').remove();
                pieceSizeField.find('option[value=""]').text('-- خطأ في التحميل --');
            });
    },

    /**
     * معالج تغيير مقاس القطع
     */
    handlePieceSizeChange: function(value, text, data) {
        console.log(`📏 تم اختيار مقاس القطع: ${text}`, data);
        
        // حفظ البيانات في التخزين المؤقت
        this.cache['piece_size'] = {
            value: value,
            text: text,
            data: data,
            timestamp: Date.now()
        };

        // إشعار النظام بتغيير مقاس القطع
        $(document).trigger('field:piece_size:changed', [value, text, data]);
        
        // تحديث معلومات المونتاج (سيحسب تلقائياً من الأبعاد)
        this.updateMontageInfo();
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
     * جلب مقاسات القطع من API مع فلترة حسب مقاس الورق فقط
     */
    loadPieceSizes: function(paperSheetType = null) {
        console.log('🔄 جلب مقاسات القطع من قاعدة البيانات...');
        
        // بناء URL مع معاملات الفلترة
        let apiUrl = this.config.apiBaseUrl + 'piece-sizes/';
        const params = new URLSearchParams();
        
        if (paperSheetType) {
            params.append('paper_sheet_type', paperSheetType);
            console.log('🔍 فلترة حسب مقاس الفرخ:', paperSheetType);
        }
        
        if (params.toString()) {
            apiUrl += '?' + params.toString();
        }
        
        return fetch(apiUrl, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                console.log(`✅ ${data.status_message}: ${data.total_count} مقاس`);
                return data;
            } else {
                throw new Error(data.error || 'فشل في جلب مقاسات القطع');
            }
        })
        .catch(error => {
            console.error('❌ خطأ في جلب مقاسات القطع:', error);
            throw error;
        });
    },

    /**
     * ملء حقل مقاس القطع بالبيانات مع رسائل توضيحية
     */
    populatePieceSizeField: function(field, pieceSizes, statusMessage = '') {
        // مسح الخيارات الموجودة (عدا الخيار الفارغ)
        field.find('option:not([value=""])').remove();
        
        // تحديث نص الخيار الفارغ حسب الحالة
        const emptyOption = field.find('option[value=""]');
        if (statusMessage.includes('اختر مقاس الورق أولاً')) {
            emptyOption.text('-- اختر مقاس الورق أولاً --');
        } else if (statusMessage.includes('اختر ماكينة الطباعة أولاً')) {
            emptyOption.text('-- اختر ماكينة الطباعة أولاً --');
        } else if (pieceSizes.length === 0) {
            emptyOption.text('-- لا توجد مقاسات متاحة --');
        } else {
            emptyOption.text('-- اختر مقاس القطع --');
        }
        
        // إضافة الخيارات الجديدة (بدون مقاس مخصص)
        pieceSizes.forEach(pieceSize => {
            const option = new Option(pieceSize.display_name, pieceSize.id, pieceSize.is_default, pieceSize.is_default);
            
            // إضافة بيانات إضافية كـ data attributes
            option.dataset.width = pieceSize.width;
            option.dataset.height = pieceSize.height;
            option.dataset.paperType = pieceSize.paper_type;
            option.dataset.paperTypeId = pieceSize.paper_type_id || '';
            option.dataset.name = pieceSize.name;
            option.dataset.piecesPerSheet = pieceSize.pieces_per_sheet || 1; // ✅ إضافة عدد القطع في الفرخ
            
            field.append(option);
        });

        // اختيار المقاس الافتراضي إذا وُجد
        const defaultPieceSize = pieceSizes.find(ps => ps.is_default);
        if (defaultPieceSize && pieceSizes.length > 0) {
            field.val(defaultPieceSize.id);
            console.log(`🔄 تم اختيار المقاس الافتراضي: ${defaultPieceSize.display_name}`);
        } else {
            field.val(''); // مسح الاختيار إذا لم توجد مقاسات
        }

        // تحديث العرض
        field.trigger('change');
        
        console.log(`✅ تم ملء حقل مقاسات القطع: ${pieceSizes.length} مقاس متاح`);
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
            
        } else if (value && dimensions.width && dimensions.height) {
            // مقاس عادي - ملء الحقول وجعلها readonly
            widthField.val(dimensions.width).prop('readonly', true);
            heightField.val(dimensions.height).prop('readonly', true);
            
        } else {
            // لا يوجد اختيار - تفريغ الحقول وجعلها readonly
            widthField.val('').prop('readonly', true);
            heightField.val('').prop('readonly', true);
            
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


        // معالج تغيير اتجاه الطباعة
        printDirectionField.on('change', (e) => {
            const selectedValue = e.target.value;
            const selectedText = e.target.options[e.target.selectedIndex].text;
            
            this.handlePrintDirectionChange(selectedValue, selectedText);
        });

        // الاستماع لتغييرات أبعاد المنتج
        $(document).on('product-size:changed', (e, data) => {
            this.handleDimensionsChange(data);
        });

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
                
            } else {
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
                
                // إطلاق حدث التغيير
                printDirectionField.trigger('change');
            }
        }
    },

    /**
     * تهيئة حقل عدد أوجه الطباعة وربطه بحقول الألوان
     */
    initPrintSidesField: function() {
        const printSidesSelect = document.getElementById('id_print_sides');
        const singleSideColors = document.getElementById('single-side-colors');
        const doubleSideColors = document.getElementById('double-side-colors');
        
        if (printSidesSelect && singleSideColors && doubleSideColors) {
            // تحديث حقول الألوان عند تحميل الصفحة
            this.updateColorsFields(printSidesSelect, singleSideColors, doubleSideColors);
            
            // إضافة معالج حدث لتغيير عدد الأوجه
            printSidesSelect.addEventListener('change', () => {
                this.updateColorsFields(printSidesSelect, singleSideColors, doubleSideColors);
            });
        }

        // تهيئة حقول المحتوى الداخلي
        const internalPrintSidesSelect = document.getElementById('id_internal_print_sides');
        const internalSingleSideColors = document.getElementById('internal-single-side-colors');
        const internalDoubleSideColors = document.getElementById('internal-double-side-colors');
        
        if (internalPrintSidesSelect && internalSingleSideColors && internalDoubleSideColors) {
            // تحديث حقول الألوان عند تحميل الصفحة
            this.updateColorsFields(internalPrintSidesSelect, internalSingleSideColors, internalDoubleSideColors);
            
            // إضافة معالج حدث لتغيير عدد الأوجه
            internalPrintSidesSelect.addEventListener('change', () => {
                this.updateColorsFields(internalPrintSidesSelect, internalSingleSideColors, internalDoubleSideColors);
            });
        }
    },

    /**
     * تحديث حقول الألوان حسب عدد أوجه الطباعة
     * @param {HTMLElement} printSidesSelect - قائمة عدد الأوجه
     * @param {HTMLElement} singleSideColors - حقل ألوان الوجه الواحد
     * @param {HTMLElement} doubleSideColors - حقل ألوان الوجهين
     */
    updateColorsFields: function(printSidesSelect, singleSideColors, doubleSideColors) {
        if (!printSidesSelect || !singleSideColors || !doubleSideColors) {
            return;
        }
        
        const selectedValue = printSidesSelect.value;
        
        // تحديث حقول الألوان حسب عدد الأوجه
        // القيم: 1 = وجه واحد، 2 = وجهين، 3 = طبع وقلب
        if (selectedValue === '1' || selectedValue === '3') {
            // وجه واحد أو طبع وقلب (تصميم واحد)
            singleSideColors.style.display = 'flex';
            doubleSideColors.style.display = 'none';
        } else if (selectedValue === '2') {
            // وجهين مختلفين
            singleSideColors.style.display = 'none';
            doubleSideColors.style.display = 'flex';
        } else {
            // القيمة الافتراضية - إظهار حقل الوجه الواحد
            singleSideColors.style.display = 'flex';
            doubleSideColors.style.display = 'none';
        }
    },

    /**
     * تهيئة حقول معلومات المونتاج
     */
    initMontageInfoFields: function() {
        console.log('🔧 تهيئة حقول معلومات المونتاج...');
        
        // تهيئة حقل المونتاج للغلاف
        const montageInfoField = $('#id_montage_info');
        if (montageInfoField.length) {
            // تحديث أولي
            this.updateMontageInfo();
            
            // ربط الأحداث مع الحقول المؤثرة (piece_size و product_size)
            $('#id_piece_size, #id_product_size').on('change', () => {
                this.updateMontageInfo();
            });
            
            // ربط حقول المقاسات المخصصة
            $('#id_piece_width, #id_piece_height, #id_product_width, #id_product_height').on('input change', () => {
                this.updateMontageInfo();
            });
            
            // ربط حقل الكمية لتحديث عدد الأفرخ
            $('#id_quantity').on('input change', () => {
                this.updatePaperSheetsCount();
            });
            
            // ربط حقل سعر الورق لتحديث التكلفة الإجمالية
            $('#id_paper_price').on('input change', () => {
                this.updatePaperTotalCost();
            });
            
            console.log('✅ تم تهيئة حقل معلومات المونتاج للغلاف');
        }
        
        // تهيئة حقل المونتاج للمحتوى الداخلي
        const internalMontageInfoField = $('#id_internal_montage_info');
        if (internalMontageInfoField.length) {
            // تحديث أولي
            this.updateInternalMontageInfo();
            
            // ربط الأحداث
            $('#id_quantity, #id_internal_page_count').on('change', () => {
                this.updateInternalMontageInfo();
            });
            
            console.log('✅ تم تهيئة حقل معلومات المونتاج للمحتوى الداخلي');
        }
    },

    /**
     * تحديث معلومات المونتاج للغلاف
     * يعرض: عدد القطع من المنتج / مقاس القطع
     * مثال: 2 / ربع فرخ (يعني قطعتين من المنتج في ربع الفرخ)
     */
    updateMontageInfo: function() {
        const montageInfoField = $('#id_montage_info');
        if (!montageInfoField.length) return;
        
        // الحصول على مقاس القطع
        const pieceSizeField = $('#id_piece_size');
        const pieceSizeValue = pieceSizeField.val();
        const pieceSizeText = pieceSizeField.length && pieceSizeValue 
            ? pieceSizeField.find('option:selected').text() 
            : '';
        
        // الحصول على مقاس المنتج
        const productSizeField = $('#id_product_size');
        const productSizeValue = productSizeField.val();
        
        // التحقق من وجود البيانات المطلوبة
        if (!pieceSizeValue || !productSizeValue) {
            montageInfoField.val('-- اختر مقاس القطع ومقاس المنتج --');
            montageInfoField.attr('placeholder', 'اختر مقاس القطع ومقاس المنتج أولاً');
            console.log('⚠️ مقاس القطع أو مقاس المنتج غير محدد');
            return;
        }
        
        // حساب المونتاج من أبعاد المقاسات
        const montageCount = this.calculateMontageCount();
        
        // الصيغة: عدد القطع / مقاس القطع
        const montageInfo = `${montageCount} / ${pieceSizeText}`;
        montageInfoField.val(montageInfo);
        montageInfoField.removeAttr('placeholder');
        
        // تحديث حقل montage_count المخفي
        $('#id_montage_count').val(montageCount);
        
        // حساب وتحديث عدد الأفرخ
        this.updatePaperSheetsCount();
        
        console.log(`📊 تحديث معلومات المونتاج: ${montageInfo} (${montageCount} قطعة من المنتج في ${pieceSizeText})`);
    },

    /**
     * حساب وتحديث عدد الأفرخ المطلوبة
     * الصيغة: عدد الأفرخ = ceil(عدد المنتج ÷ (المونتاج × عدد القطع في الفرخ))
     */
    updatePaperSheetsCount: function() {
        const paperSheetsField = $('#id_paper_sheets_count');
        if (!paperSheetsField.length) return;
        
        // الحصول على البيانات المطلوبة
        const quantity = parseInt($('#id_quantity').val()) || 0;
        const montageCount = parseInt($('#id_montage_count').val()) || 1;
        const pieceSizeField = $('#id_piece_size');
        
        if (!quantity || !pieceSizeField.val()) {
            paperSheetsField.val('');
            return;
        }
        
        // الحصول على عدد القطع في الفرخ
        const pieceSizeOption = pieceSizeField.find('option:selected');
        let piecesPerSheet = parseInt(pieceSizeOption.data('piecesPerSheet')) || 1;
        
        // إذا كان مقاس مخصص، نفترض 1 (فرخ كامل)
        if (pieceSizeField.val() === 'custom') {
            piecesPerSheet = 1;
            console.log('📐 مقاس مخصص: عدد القطع في الفرخ = 1 (فرخ كامل)');
        }
        
        // حساب عدد الأفرخ
        // عدد الأفرخ = ceil(عدد المنتج ÷ (المونتاج × عدد القطع في الفرخ))
        const totalPiecesPerSheet = montageCount * piecesPerSheet;
        const paperSheets = Math.ceil(quantity / totalPiecesPerSheet);
        
        console.log(`📄 حساب عدد الأفرخ:
        - عدد المنتج: ${quantity}
        - المونتاج: ${montageCount} قطعة/مقاس قطع
        - عدد القطع في الفرخ: ${piecesPerSheet}
        - إجمالي القطع في الفرخ: ${totalPiecesPerSheet} (${montageCount} × ${piecesPerSheet})
        - عدد الأفرخ المطلوبة: ${paperSheets} فرخ`);
        
        // تحديث الحقل
        paperSheetsField.val(paperSheets);
        
        // إطلاق حدث التغيير
        paperSheetsField.trigger('change');
        
        // حساب التكلفة الإجمالية للورق
        this.updatePaperTotalCost();
    },

    /**
     * حساب وتحديث التكلفة الإجمالية للورق
     * الصيغة: التكلفة الإجمالية = سعر الفرخ × عدد الأفرخ
     */
    updatePaperTotalCost: function() {
        const totalCostField = $('#id_paper_total_cost');
        if (!totalCostField.length) return;
        
        // الحصول على البيانات المطلوبة
        const paperPrice = parseFloat($('#id_paper_price').val()) || 0;
        const paperSheets = parseInt($('#id_paper_sheets_count').val()) || 0;
        
        if (!paperPrice || !paperSheets) {
            totalCostField.val('');
            return;
        }
        
        // حساب التكلفة الإجمالية
        const totalCost = paperPrice * paperSheets;
        
        console.log(`💰 حساب التكلفة الإجمالية للورق:
        - سعر الفرخ: ${paperPrice} جنيه
        - عدد الأفرخ: ${paperSheets} فرخ
        - التكلفة الإجمالية: ${totalCost.toFixed(2)} جنيه`);
        
        // تحديث الحقل
        totalCostField.val(totalCost.toFixed(2));
        
        // إطلاق حدث التغيير
        totalCostField.trigger('change');
    },

    /**
     * حساب عدد القطع من المنتج في مقاس القطع
     * بناءً على المساحات والأبعاد
     */
    calculateMontageCount: function() {
        const pieceSizeField = $('#id_piece_size');
        const productSizeField = $('#id_product_size');
        
        if (!pieceSizeField.val() || !productSizeField.val()) {
            return 1;
        }
        
        // الحصول على أبعاد مقاس القطع
        const pieceSizeOption = pieceSizeField.find('option:selected');
        let pieceWidth = parseFloat(pieceSizeOption.data('width')) || 0;
        let pieceHeight = parseFloat(pieceSizeOption.data('height')) || 0;
        
        // إذا كان مقاس القطع مخصص، نجيب الأبعاد من الحقول المخصصة
        if (pieceSizeField.val() === 'custom') {
            const customWidthField = $('#id_piece_width');
            const customHeightField = $('#id_piece_height');
            
            if (customWidthField.length && customHeightField.length) {
                pieceWidth = parseFloat(customWidthField.val()) || 0;
                pieceHeight = parseFloat(customHeightField.val()) || 0;
                console.log(`📐 مقاس قطع مخصص: ${pieceWidth}×${pieceHeight} سم`);
            }
        }
        
        // خصم السماحية من مقاس القطع (1 سم من العرض و 1 سم من الطول)
        const trimMargin = 1; // سم
        pieceWidth = Math.max(0, pieceWidth - trimMargin);
        pieceHeight = Math.max(0, pieceHeight - trimMargin);
        console.log(`✂️ مقاس القطع بعد خصم السماحية (${trimMargin} سم): ${pieceWidth}×${pieceHeight} سم`);
        
        // الحصول على أبعاد مقاس المنتج
        const productSizeOption = productSizeField.find('option:selected');
        let productWidth = parseFloat(productSizeOption.data('width')) || 0;
        let productHeight = parseFloat(productSizeOption.data('height')) || 0;
        
        // إذا كان مقاس المنتج مخصص، نجيب الأبعاد من الحقول المخصصة
        if (productSizeField.val() === 'custom') {
            const customWidthField = $('#id_product_width');
            const customHeightField = $('#id_product_height');
            
            if (customWidthField.length && customHeightField.length) {
                productWidth = parseFloat(customWidthField.val()) || 0;
                productHeight = parseFloat(customHeightField.val()) || 0;
                console.log(`📐 مقاس منتج مخصص: ${productWidth}×${productHeight} سم`);
            }
        }
        
        if (!pieceWidth || !pieceHeight || !productWidth || !productHeight) {
            console.warn('⚠️ لا يمكن الحصول على أبعاد المقاسات');
            return 1;
        }
        
        // حساب عدد القطع في كل اتجاه
        // نجرب الاتجاهين (عادي ومقلوب) ونختار الأفضل
        
        // الاتجاه العادي
        const countNormal = Math.floor(pieceWidth / productWidth) * Math.floor(pieceHeight / productHeight);
        
        // الاتجاه المقلوب
        const countRotated = Math.floor(pieceWidth / productHeight) * Math.floor(pieceHeight / productWidth);
        
        // اختيار الأفضل
        const montageCount = Math.max(countNormal, countRotated);
        
        console.log(`🧮 حساب المونتاج:
        - مقاس القطع: ${pieceWidth}×${pieceHeight} سم
        - مقاس المنتج: ${productWidth}×${productHeight} سم
        - الاتجاه العادي: ${countNormal} قطعة
        - الاتجاه المقلوب: ${countRotated} قطعة
        - النتيجة: ${montageCount} قطعة`);
        
        return montageCount || 1;
    },

    /**
     * تحديث معلومات المونتاج للمحتوى الداخلي
     * يعرض: الكمية × عدد الصفحات
     */
    updateInternalMontageInfo: function() {
        const internalMontageInfoField = $('#id_internal_montage_info');
        if (!internalMontageInfoField.length) return;
        
        const quantity = $('#id_quantity').val() || 0;
        const pageCount = $('#id_internal_page_count').val() || 0;
        
        const montageInfo = `${quantity} × ${pageCount} صفحة`;
        internalMontageInfoField.val(montageInfo);
        
        console.log(`📊 تحديث معلومات المونتاج الداخلي: ${montageInfo}`);
    },

    /**
     * تهيئة حقول المطبعة والماكينة
     */
    initPressFields: function() {
        // تهيئة حقول المطبعة والماكينة
        this.initSupplierPressFields();
    },

    /**
     * تهيئة حقول المطبعة والماكينة
     */
    initSupplierPressFields: function() {
        const supplierSelect = $('#id_supplier');
        const pressSelect = $('#id_press');
        
        if (!supplierSelect.length || !pressSelect.length) {
            return;
        }
        
        // تحويل المطبعة إلى Select2
        supplierSelect.select2({
            ...this.config.select2Config,
            placeholder: 'اختر المطبعة...',
            allowClear: true,
            minimumInputLength: 0
        });
        
        // الماكينة عادية بدون Select2 لتجنب التداخل
        // pressSelect سيبقى select عادي
        
        // تحميل قائمة المطابع
        this.loadSuppliers(supplierSelect);
        
        // إضافة معالج حدث لتغيير المطبعة - Select2 events
        supplierSelect.on('select2:select', (e) => {
            let selectedValue;
            
            // التحقق من مصدر الحدث (طبيعي أم مطلق)
            if (e.params && e.params.data && e.params.data.id) {
                selectedValue = e.params.data.id;
            } else {
                // في حالة الحدث المطلق، استخدم القيمة الحالية
                selectedValue = supplierSelect.val();
            }
            
            if (selectedValue) {
                this.handleSupplierChange(selectedValue, document.getElementById('id_press'));
            }
        });
        
        supplierSelect.on('select2:clear', () => {
            this.handleSupplierChange('', document.getElementById('id_press'));
        });
        
        // إضافة معالج حدث عادي أيضاً كـ backup
        supplierSelect.on('change', () => {
            const selectedValue = supplierSelect.val();
            
            if (selectedValue) {
                this.handleSupplierChange(selectedValue, document.getElementById('id_press'));
            } else {
                this.handleSupplierChange('', document.getElementById('id_press'));
            }
        });
        
        // إضافة معالج حدث لتغيير الماكينة
        pressSelect.on('change', () => {
            this.handlePressChange(pressSelect[0]);
        });
    },

    /**
     * تحميل قائمة المطابع
     */
    loadSuppliers: function(supplierSelect) {
        
        if (!supplierSelect || !supplierSelect.length) {
            return;
        }
        
        // بناء URL للـ API - جلب مطابع الأوفست فقط
        let apiUrl = '/printing-pricing/api/printing-suppliers/?order_type=offset';
        
        // تعطيل القائمة أثناء التحميل
        supplierSelect.prop('disabled', true);
        supplierSelect.empty();
        supplierSelect.append('<option value="">-- جاري التحميل... --</option>');
        
        // استدعاء API
        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                supplierSelect.prop('disabled', false);
                supplierSelect.empty();
                
                let html = '<option value="">-- اختر المطبعة --</option>';
                
                if (data.success && data.suppliers && data.suppliers.length > 0) {
                    data.suppliers.forEach(supplier => {
                        supplierSelect.append(`<option value="${supplier.id}">${supplier.name}</option>`);
                    });
                } else {
                    supplierSelect.append('<option value="">-- لا توجد مطابع متاحة --</option>');
                }
            })
            .catch(error => {
                console.error('❌ خطأ في تحميل المطابع:', error);
                supplierSelect.prop('disabled', false);
                supplierSelect.empty();
                supplierSelect.append('<option value="">-- خطأ في التحميل --</option>');
            });
    },

    /**
     * معالجة تغيير المطبعة
     */
    handleSupplierChange: function(supplierId, pressSelectElement) {
        if (!pressSelectElement) {
            console.error('❌ pressSelectElement is null or undefined');
            return;
        }
        
        const pressSelect = $(pressSelectElement);
        
        if (!supplierId || supplierId === '') {
            // مسح قائمة الماكينات
            let pressSelectElement;
            if (pressSelect && pressSelect.length) {
                pressSelectElement = pressSelect[0];
            } else if (pressSelect && pressSelect.nodeType) {
                pressSelectElement = pressSelect;
            } else {
                pressSelectElement = document.getElementById('id_press');
            }
            
            if (pressSelectElement) {
                pressSelectElement.innerHTML = '<option value="">اختر الماكينة</option>';
                $(pressSelectElement).trigger('change');
                this.clearPressPrice();
                this.lastLoadedPress = null; // مسح آخر ماكينة محملة
            }
            return;
        }
        
        // منع تكرار التحميل إذا كان قيد التنفيذ
        if (this.loadingPresses) {
            return;
        }
        
        this.loadPressesForSupplier(supplierId, pressSelect);
    },

    /**
     * تحميل ماكينات المطبعة
{{ ... }}
     */
    loadPressesForSupplier: function(supplierId, pressSelect) {
        // تعيين علامة التحميل
        this.loadingPresses = true;
        
        // التأكد من الحصول على العنصر الصحيح
        let pressSelectElement;
        if (pressSelect && pressSelect.length) {
            // jQuery object
            pressSelectElement = pressSelect[0];
        } else if (pressSelect && pressSelect.nodeType) {
            // DOM element
            pressSelectElement = pressSelect;
        } else {
            // البحث عن العنصر بالـ ID
            pressSelectElement = document.getElementById('id_press');
        }
        
        if (!pressSelectElement) {
            console.error('❌ لم يتم العثور على عنصر الماكينة');
            return;
        }
        
        
        // مسح الخيارات الحالية
        pressSelectElement.innerHTML = '<option value="">جاري التحميل...</option>';
        pressSelectElement.disabled = true;
        
        // بناء URL مع المعاملات - جلب ماكينات الأوفست فقط
        let apiUrl = `/printing-pricing/api/presses/?supplier_id=${supplierId}&order_type=offset`;
        
        
        // استدعاء API
        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                
                // إعادة تمكين القائمة - استخدام DOM عادي
                pressSelectElement.disabled = false;
                pressSelectElement.innerHTML = '<option value="">-- اختر ماكينة الطباعة --</option>';
                
                if (data && data.success && Array.isArray(data.presses) && data.presses.length > 0) {
                    // إضافة خيارات الماكينات
                    data.presses.forEach(press => {
                        if (press && typeof press === 'object' && press.id) {
                            const name = press.name || `ماكينة ${press.id}`;
                            let price = '';
                            
                            if (press.price_per_1000 !== undefined) {
                                price = press.price_per_1000;
                            } else if (press.unit_price !== undefined) {
                                price = press.unit_price;
                            }
                            
                            // إنشاء option جديد
                            const option = document.createElement('option');
                            option.value = press.id;
                            option.textContent = name;
                            option.setAttribute('data-price', price);
                            if (press.service_id) {
                                option.setAttribute('data-service-id', press.service_id);
                            }
                            pressSelectElement.appendChild(option);
                        }
                    });
                    
                    // اختيار الماكينة الأولى افتراضياً
                    if (data.presses.length > 0) {
                        const firstPress = data.presses[0];
                        pressSelectElement.value = firstPress.id;
                        
                        // إطلاق حدث change باستخدام jQuery للتوافق مع باقي النظام
                        $(pressSelectElement).trigger('change');
                    }
                    
                } else {
                    // إذا لم يتم العثور على ماكينات أو فشل API
                    if (data && data.success === false && data.error) {
                        // عرض رسالة الخطأ من API
                        console.error('❌ خطأ من API:', data.error);
                        pressSelectElement.innerHTML += `<option value="">-- ${data.error} --</option>`;
                    } else {
                        // حالة عدم وجود ماكينات
                        pressSelectElement.innerHTML += '<option value="">-- لا توجد ماكينات متاحة --</option>';
                    }
                }
                
                // إلغاء علامة التحميل
                this.loadingPresses = false;
            })
            .catch(error => {
                console.error('❌ خطأ في تحميل ماكينات الطباعة:', error);
                pressSelectElement.disabled = false;
                pressSelectElement.innerHTML = '<option value="">-- خطأ في تحميل الماكينات --</option>';
                
                // إلغاء علامة التحميل في حالة الخطأ
                this.loadingPresses = false;
            });
    },


    /**
     * معالجة تغيير الماكينة
     */
    handlePressChange: function(pressSelectElement) {
        const pressSelect = $(pressSelectElement);
        const selectedValue = pressSelect.val();
        
        if (!selectedValue) {
            this.clearPressPrice();
            return;
        }
        
        // منع تكرار تحميل نفس الماكينة
        if (this.lastLoadedPress === selectedValue) {
            return;
        }
        
        this.lastLoadedPress = selectedValue;
        
        // تحميل سعر الماكينة المختارة
        this.loadPressPrice(selectedValue);
    },

    /**
     * تحميل سعر الماكينة
     */
    loadPressPrice: function(pressId) {
        const priceField = $('#id_press_price_per_1000');
        const pressSelect = $('#id_press');
        
        if (!priceField.length || !pressId) {
            return;
        }
        
        // أولاً، محاولة الحصول على السعر من البيانات المخزنة في الخيار
        const pressSelectElement = document.getElementById('id_press');
        if (pressSelectElement) {
            const selectedOption = pressSelectElement.querySelector(`option[value="${pressId}"]`);
            if (selectedOption && selectedOption.getAttribute('data-price')) {
                const price = selectedOption.getAttribute('data-price');
                priceField.val(price);
                priceField.trigger('change');
                // حفظ service_id إذا متاح
                const serviceId = selectedOption.getAttribute('data-service-id');
                if (serviceId) {
                    $('#id_press').data('service-id', serviceId);
                    this._saveSupplierServiceSnapshot('printing', pressId, serviceId);
                }
                return;
            }
        }
        
        // إذا لم يتم العثور على السعر في البيانات المخزنة، استدعاء API
        fetch(`/printing-pricing/api/press-price/?press_id=${pressId}`)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                return response.json();
            })
            .then(data => {
                if (data && data.success) {
                    const price = data.price_per_1000 || data.price || data.unit_price || '0.00';
                    priceField.val(price);
                    priceField.trigger('change');
                    // حفظ service_id في data attribute
                    if (data.service_id) {
                        $('#id_press').data('service-id', data.service_id);
                        this._saveSupplierServiceSnapshot('printing', pressId, data.service_id);
                    }
                } else {
                    priceField.val('0.00');
                    priceField.trigger('change');
                }
            })
            .catch(error => {
                console.error('❌ خطأ في جلب سعر الماكينة:', error);
                priceField.val('0.00');
                priceField.trigger('change');
            });
    },

    /**
     * مسح سعر الماكينة
     */
    clearPressPrice: function() {
        const priceField = $('#id_press_price_per_1000');
        
        if (priceField.length) {
            priceField.val('');
            priceField.trigger('change');
        }
    },

    /**
     * تهيئة حقول الزنكات (CTP)
     */
    initCTPFields: function() {
        // تهيئة حقول الغلاف
        this.initCoverCTPFields();
        
        // تهيئة حقول المحتوى الداخلي
        this.initInternalCTPFields();
    },

    /**
     * تهيئة حقول الزنكات للغلاف
     */
    initCoverCTPFields: function() {
        const ctpSupplierSelect = $('#id_ctp_supplier');
        const ctpPlateSizeSelect = $('#id_ctp_plate_size');
        
        if (ctpSupplierSelect.length && ctpPlateSizeSelect.length) {
            // تحويل مورد الزنكات إلى Select2
            ctpSupplierSelect.select2({
                ...this.config.select2Config,
                placeholder: 'اختر مورد الزنكات...',
                allowClear: true,
                minimumInputLength: 0
            });
            
            // تحميل موردي الزنكات
            this.loadCTPSuppliers(ctpSupplierSelect);
            
            // إضافة معالج حدث لتغيير مورد الزنكات
            ctpSupplierSelect.on('select2:select', (e) => {
                let selectedValue;
                
                // التحقق من مصدر الحدث (طبيعي أم مطلق)
                if (e.params && e.params.data && e.params.data.id) {
                    selectedValue = e.params.data.id;
                } else {
                    // في حالة الحدث المطلق، استخدم القيمة الحالية
                    selectedValue = ctpSupplierSelect.val();
                }
                
                if (selectedValue) {
                    this.handleCTPSupplierChange(selectedValue, ctpPlateSizeSelect[0]);
                }
            });
            
            ctpSupplierSelect.on('select2:clear', () => {
                this.handleCTPSupplierChange('', ctpPlateSizeSelect[0]);
            });
            
            // إضافة معالج حدث لتغيير مقاس الزنك
            ctpPlateSizeSelect.on('change', () => {
                this.handleCTPPlateSizeChange(ctpPlateSizeSelect[0]);
            });
        }
    },

    /**
     * تهيئة حقول الزنكات للمحتوى الداخلي
     */
    initInternalCTPFields: function() {
        const internalCtpSupplierSelect = $('#id_internal_ctp_supplier');
        const internalCtpPlateSizeSelect = $('#id_internal_ctp_plate_size');
        
        if (internalCtpSupplierSelect.length && internalCtpPlateSizeSelect.length) {
            // تحويل مورد الزنكات إلى Select2
            internalCtpSupplierSelect.select2({
                ...this.config.select2Config,
                placeholder: 'اختر مورد الزنكات...',
                allowClear: true,
                minimumInputLength: 0
            });
            
            // تحميل موردي الزنكات
            this.loadCTPSuppliers(internalCtpSupplierSelect);
            
            // إضافة معالج حدث لتغيير مورد الزنكات
            internalCtpSupplierSelect.on('select2:select', (e) => {
                let selectedValue;
                
                // التحقق من مصدر الحدث (طبيعي أم مطلق)
                if (e.params && e.params.data && e.params.data.id) {
                    selectedValue = e.params.data.id;
                } else {
                    // في حالة الحدث المطلق، استخدم القيمة الحالية
                    selectedValue = internalCtpSupplierSelect.val();
                }
                
                if (selectedValue) {
                    this.handleCTPSupplierChange(selectedValue, internalCtpPlateSizeSelect[0]);
                }
            });
            
            internalCtpSupplierSelect.on('select2:clear', () => {
                this.handleCTPSupplierChange('', internalCtpPlateSizeSelect[0]);
            });
            
            // إضافة معالج حدث لتغيير مقاس الزنك
            internalCtpPlateSizeSelect.on('change', () => {
                this.handleCTPPlateSizeChange(internalCtpPlateSizeSelect[0]);
            });
        }
    },

    /**
     * تحميل موردي الزنكات
     */
    loadCTPSuppliers: function(supplierSelect) {
        if (!supplierSelect || !supplierSelect.length) return;
        
        // تعطيل القائمة أثناء التحميل
        supplierSelect.prop('disabled', true);
        
        // استدعاء API للحصول على موردي الزنكات - النظام الجديد
        fetch('/printing-pricing/api/ctp-suppliers/')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // إعادة تمكين القائمة
                supplierSelect.prop('disabled', false);
                
                if (data.success && data.suppliers && data.suppliers.length > 0) {
                    // مسح الخيارات الحالية
                    supplierSelect.empty();
                    supplierSelect.append('<option value="">-- اختر المورد --</option>');
                    
                    // إضافة الموردين إلى القائمة
                    data.suppliers.forEach(supplier => {
                        const option = new Option(supplier.name, supplier.id);
                        supplierSelect.append(option);
                    });
                    
                    // تحديث Select2
                    supplierSelect.trigger('change');
                } else {
                    console.warn('لا توجد موردين زنكات متاحين');
                }
            })
            .catch(error => {
                console.error('خطأ في تحميل موردي الزنكات:', error);
                supplierSelect.prop('disabled', false);
            });
    },

    /**
     * معالجة تغيير مورد الزنكات
     */
    handleCTPSupplierChange: function(supplierId, plateSizeSelect) {
        if (!plateSizeSelect) return;
        
        // إذا تم إعادة تعيين المورد (اختيار قيمة فارغة)
        if (!supplierId) {
            plateSizeSelect.innerHTML = '<option value="">-- اختر المقاس --</option>';
            plateSizeSelect.disabled = true;
            this.clearCTPPriceFields(plateSizeSelect);
            return;
        }
        
        // تحميل مقاسات الزنكات للمورد المختار
        this.loadPlateSizes(supplierId, plateSizeSelect);
    },

    /**
     * تحميل مقاسات الزنكات
     */
    loadPlateSizes: function(supplierId, plateSizeSelect) {
        if (!plateSizeSelect || !supplierId) return;
        
        // تعطيل القائمة أثناء التحميل
        plateSizeSelect.disabled = true;
        
        // مسح الخيارات الحالية
        plateSizeSelect.innerHTML = '<option value="">-- اختر المقاس --</option>';
        
        // استدعاء API للحصول على مقاسات الزنكات المتاحة - النظام الجديد
        fetch(`/printing-pricing/api/ctp-plates/?supplier_id=${supplierId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`فشل الطلب بكود الحالة: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // إعادة تمكين القائمة
                plateSizeSelect.disabled = false;
                
                if (data.success && data.plates && data.plates.length > 0) {
                    // إضافة مقاسات الزنكات إلى القائمة
                    data.plates.forEach(plate => {
                        const option = document.createElement('option');
                        option.value = plate.id;
                        option.text = plate.name;
                        option.dataset.price = plate.price_per_plate;
                        plateSizeSelect.appendChild(option);
                    });
                    
                    // اختيار أول خيار تلقائياً إذا كان هناك خيارات متاحة
                    if (plateSizeSelect.options.length > 1) {
                        plateSizeSelect.selectedIndex = 1; // اختيار أول خيار (تجاهل الخيار الفارغ)
                        
                        // تحديث سعر الزنك تلقائياً
                        this.handleCTPPlateSizeChange(plateSizeSelect);
                        
                        // إطلاق حدث change للتأكد من تحديث أي معالجات أخرى
                        const changeEvent = new Event('change', { bubbles: true });
                        plateSizeSelect.dispatchEvent(changeEvent);
                    }
                } else {
                    console.warn('لا توجد مقاسات زنكات متاحة للمورد المختار');
                }
            })
            .catch(error => {
                console.error('خطأ في تحميل مقاسات الزنكات:', error);
                plateSizeSelect.disabled = false;
            });
    },

    /**
     * معالجة تغيير مقاس الزنك
     */
    handleCTPPlateSizeChange: function(plateSizeSelect) {
        if (!plateSizeSelect) return;
        
        const selectedOption = plateSizeSelect.options[plateSizeSelect.selectedIndex];
        const price = selectedOption ? selectedOption.dataset.price : '';
        
        // تحديث سعر الزنك
        this.updateCTPPrice(plateSizeSelect, price);
    },

    /**
     * تحديث سعر الزنك
     */
    updateCTPPrice: function(plateSizeSelect, price) {
        // تحديد حقل السعر المناسب بناءً على نوع الحقل
        let priceFieldId;
        if (plateSizeSelect.id === 'id_ctp_plate_size') {
            priceFieldId = 'id_ctp_plate_price';
        } else if (plateSizeSelect.id === 'id_internal_ctp_plate_size') {
            priceFieldId = 'id_internal_ctp_plate_price';
        }
        
        const priceField = document.getElementById(priceFieldId);
        if (priceField) {
            priceField.value = price || '';
        }
    },

    /**
     * مسح حقول أسعار الزنكات
     */
    clearCTPPriceFields: function(plateSizeSelect) {
        // تحديد حقل السعر المناسب بناءً على نوع الحقل
        let priceFieldId;
        if (plateSizeSelect.id === 'id_ctp_plate_size') {
            priceFieldId = 'id_ctp_plate_price';
        } else if (plateSizeSelect.id === 'id_internal_ctp_plate_size') {
            priceFieldId = 'id_internal_ctp_plate_price';
        }
        
        const priceField = document.getElementById(priceFieldId);
        if (priceField) {
            priceField.value = '';
        }
    },

    /**
     * تهيئة حساب عدد الزنكات
     */
    initPlatesCalculation: function() {
        // تهيئة حساب الزنكات للغلاف
        this.initCoverPlatesCalculation();
        
        // تهيئة حساب الزنكات للمحتوى الداخلي
        this.initInternalPlatesCalculation();
    },

    /**
     * تهيئة حساب الزنكات للغلاف
     */
    initCoverPlatesCalculation: function() {
        const printSidesField = $('#id_print_sides');
        const colorsDesignField = $('#id_colors_design');
        const colorsFrontField = $('#id_colors_front');
        const colorsBackField = $('#id_colors_back');
        const platesCountField = $('#id_ctp_plates_count');
        
        if (printSidesField.length && platesCountField.length) {
            // إضافة معالجات الأحداث
            printSidesField.on('change', () => {
                this.calculatePlatesCount('cover');
            });
            
            colorsDesignField.on('input change', () => {
                this.calculatePlatesCount('cover');
            });
            
            colorsFrontField.on('input change', () => {
                this.calculatePlatesCount('cover');
            });
            
            colorsBackField.on('input change', () => {
                this.calculatePlatesCount('cover');
            });
        }
    },

    /**
     * تهيئة حساب الزنكات للمحتوى الداخلي
     */
    initInternalPlatesCalculation: function() {
        const internalPrintSidesField = $('#id_internal_print_sides');
        const internalColorsDesignField = $('#id_internal_colors_design');
        const internalColorsFrontField = $('#id_internal_colors_front');
        const internalColorsBackField = $('#id_internal_colors_back');
        const internalPlatesCountField = $('#id_internal_ctp_plates_count');
        
        if (internalPrintSidesField.length && internalPlatesCountField.length) {
            // إضافة معالجات الأحداث
            internalPrintSidesField.on('change', () => {
                this.calculatePlatesCount('internal');
            });
            
            internalColorsDesignField.on('input change', () => {
                this.calculatePlatesCount('internal');
            });
            
            internalColorsFrontField.on('input change', () => {
                this.calculatePlatesCount('internal');
            });
            
            internalColorsBackField.on('input change', () => {
                this.calculatePlatesCount('internal');
            });
        }
    },

    /**
     * حساب عدد الزنكات
     * @param {string} type - نوع الحساب ('cover' أو 'internal')
     */
    calculatePlatesCount: function(type) {
        let printSidesField, colorsDesignField, colorsFrontField, colorsBackField, platesCountField;
        
        if (type === 'cover') {
            printSidesField = $('#id_print_sides');
            colorsDesignField = $('#id_colors_design');
            colorsFrontField = $('#id_colors_front');
            colorsBackField = $('#id_colors_back');
            platesCountField = $('#id_ctp_plates_count');
        } else if (type === 'internal') {
            printSidesField = $('#id_internal_print_sides');
            colorsDesignField = $('#id_internal_colors_design');
            colorsFrontField = $('#id_internal_colors_front');
            colorsBackField = $('#id_internal_colors_back');
            platesCountField = $('#id_internal_ctp_plates_count');
        }
        
        if (!printSidesField.length || !platesCountField.length) {
            return;
        }
        
        const printSides = printSidesField.val();
        let totalColors = 0;
        let platesCount = 0;
        
        // حساب عدد الألوان حسب نوع الطباعة (نفس منطق حساب التراجات)
        if (printSides === '1') {
            // وجه واحد → عدد الزنكات = عدد ألوان التصميم
            platesCount = parseInt(colorsDesignField.val()) || 0;
        } else if (printSides === '2' || printSides === '3') {
            // وجهين أو طبع وقلب → عدد الزنكات = عدد ألوان الوجه الأمامي
            platesCount = parseInt(colorsFrontField.val()) || 0;
        }
        
        // تحديث حقل عدد الزنكات
        if (platesCount > 0) {
            platesCountField.val(platesCount);
        } else {
            platesCountField.val('');
        }
        
        // إطلاق حدث تغيير لتحديث التكاليف
        platesCountField.trigger('change');
    },

    /**
     * حساب عدد التراجات حسب القواعد الجديدة
     * يتم حساب التراجات بناءً على الكمية والمونتاج والألوان مع تطبيق قاعدة السماحية
     */
    calculatePressRuns: function() {
        console.log('🧮 بدء حساب عدد التراجات...');
        
        // الحصول على الحقول المطلوبة
        const quantityField = $('#id_quantity');
        const montageField = $('#id_montage_count');
        const printSidesField = $('#id_print_sides');
        const colorsDesignField = $('#id_colors_design');
        const colorsFrontField = $('#id_colors_front');
        const pressRunsField = $('#id_press_runs');
        const ctpPlatesField = $('#id_ctp_plates_count');
        
        // التحقق من وجود الحقول الأساسية المطلوبة
        if (!quantityField.length || !printSidesField.length || 
            !colorsDesignField.length || !colorsFrontField.length || !pressRunsField.length) {
            console.warn('⚠️ بعض الحقول الأساسية المطلوبة لحساب التراجات غير موجودة');
            return;
        }
        
        // الحصول على القيم مع قيم افتراضية آمنة
        const quantity = parseInt(quantityField.val()) || 0;
        const montageCount = montageField.length ? (parseInt(montageField.val()) || 1) : 1;
        const printSides = printSidesField.val();
        const colorsDesign = parseInt(colorsDesignField.val()) || 0;
        const colorsFront = parseInt(colorsFrontField.val()) || 0;
        
        console.log('📊 القيم المدخلة:', {
            quantity: quantity,
            montageCount: montageCount,
            printSides: printSides,
            colorsDesign: colorsDesign,
            colorsFront: colorsFront
        });
        
        // التحقق من وجود البيانات الأساسية
        if (quantity <= 0 || montageCount <= 0) {
            console.log('⚠️ الكمية أو المونتاج غير صحيح');
            pressRunsField.val('');
            return;
        }
        
        // 1. حساب عدد مقاس الطباعة الفعلي
        const printSheets = Math.ceil(quantity / montageCount);
        console.log(`📄 عدد مقاس الطباعة الفعلي: ${printSheets} = ceil(${quantity} / ${montageCount})`);
        
        // 2. تحديد عدد الألوان المستخدمة في الحساب
        let colorsTotal = 0;
        if (printSides === '1') {
            // وجه واحد → إجمالي الألوان = عدد ألوان التصميم
            colorsTotal = colorsDesign;
        } else if (printSides === '2' || printSides === '3') {
            // وجهين أو طبع وقلب → إجمالي الألوان = عدد ألوان الوجه الأمامي
            colorsTotal = colorsFront;
        }
        
        console.log(`🎨 إجمالي الألوان للحساب: ${colorsTotal} (نوع الطباعة: ${printSides})`);
        
        if (colorsTotal <= 0) {
            console.log('⚠️ عدد الألوان غير صحيح');
            pressRunsField.val('');
            return;
        }
        
        // 3. حساب عدد التراجات لكل لون مع تطبيق قاعدة السماحية
        let tarajPerColor = 0;
        
        if (printSheets <= 1000) {
            // إذا كان عدد الأوراق ≤ 1000 → تراج واحد لكل لون
            tarajPerColor = 1;
        } else {
            // إذا كان عدد الأوراق > 1000
            const R = printSheets - 1000;
            
            if (R <= 150) {
                // إذا كان الفرق ≤ 150 → تراج واحد لكل لون (سماحية)
                tarajPerColor = 1;
            } else {
                // إذا كان الفرق > 150 → حساب التراجات الإضافية
                tarajPerColor = 1 + Math.ceil((R - 150) / 1000);
            }
        }
        
        console.log(`📊 تفاصيل حساب التراجات لكل لون:
        - عدد الأوراق: ${printSheets}
        - التراجات لكل لون: ${tarajPerColor}`);
        
        // 4. حساب عدد التراجات الكلي
        const totalPressRuns = tarajPerColor * colorsTotal;
        
        console.log(`🏃 النتيجة النهائية: ${totalPressRuns} تراج = ${tarajPerColor} × ${colorsTotal}`);
        
        // تحديث حقل عدد التراجات
        pressRunsField.val(totalPressRuns);
        
        // 5. حساب عدد الزنكات (CTP) حسب نفس منطق الألوان
        let ctpPlatesCount = 0;
        if (printSides === '1') {
            // وجه واحد → عدد الزنكات = عدد ألوان التصميم
            ctpPlatesCount = colorsDesign;
        } else if (printSides === '2' || printSides === '3') {
            // وجهين أو طبع وقلب → عدد الزنكات = عدد ألوان الوجه الأمامي
            ctpPlatesCount = colorsFront;
        }
        
        if (ctpPlatesField.length && ctpPlatesCount > 0) {
            ctpPlatesField.val(ctpPlatesCount);
            console.log(`🖨️ عدد الزنكات: ${ctpPlatesCount}`);
        }
        
        // إطلاق أحداث التغيير لتحديث الحسابات الأخرى
        pressRunsField.trigger('change');
        if (ctpPlatesField.length) {
            ctpPlatesField.trigger('change');
        }
        
        console.log('✅ تم حساب عدد التراجات بنجاح');
    },

    /**
     * تهيئة حساب عدد التراجات التلقائي
     * ربط الحقول المؤثرة بدالة حساب التراجات
     */
    initPressRunsCalculation: function() {
        console.log('🔧 تهيئة حساب عدد التراجات التلقائي...');
        
        // الحقول المؤثرة على حساب التراجات
        const quantityField = $('#id_quantity');
        const montageField = $('#id_montage_count');
        const printSidesField = $('#id_print_sides');
        const colorsDesignField = $('#id_colors_design');
        const colorsFrontField = $('#id_colors_front');
        
        // ربط الأحداث بالحقول المؤثرة (فقط الحقول الموجودة)
        const fieldsToWatch = [quantityField, printSidesField, colorsDesignField, colorsFrontField];
        
        // إضافة حقل المونتاج إذا كان موجوداً
        if (montageField.length) {
            fieldsToWatch.push(montageField);
            console.log('✅ حقل المونتاج موجود وسيتم مراقبته');
        } else {
            console.log('⚠️ حقل المونتاج غير موجود، سيتم استخدام قيمة افتراضية (1)');
        }
        
        fieldsToWatch.forEach(field => {
            if (field.length) {
                // ربط أحداث التغيير
                field.on('input change keyup', () => {
                    // تأخير بسيط لتجنب الحسابات المتكررة
                    clearTimeout(this.pressRunsTimeout);
                    this.pressRunsTimeout = setTimeout(() => {
                        this.calculatePressRuns();
                    }, 300);
                });
                
                console.log(`✅ تم ربط حقل ${field.attr('id')} بحساب التراجات`);
            }
        });
        
        // حساب أولي عند التحميل
        setTimeout(() => {
            this.calculatePressRuns();
        }, 500);
        
        console.log('✅ تم تهيئة حساب عدد التراجات التلقائي');
    },

    /**
     * تهيئة حساب التكلفة الإجمالية للزنكات
     */
    initCTPCostCalculation: function() {
        // تهيئة حساب التكلفة للغلاف
        this.initCoverCTPCostCalculation();
        
        // تهيئة حساب التكلفة للمحتوى الداخلي
        this.initInternalCTPCostCalculation();
    },

    /**
     * تهيئة حساب التكلفة الإجمالية للزنكات للغلاف
     */
    initCoverCTPCostCalculation: function() {
        const platesCountField = $('#id_ctp_plates_count');
        const platePriceField = $('#id_ctp_plate_price');
        const transportationField = $('#id_ctp_transportation');
        const totalCostField = $('#id_ctp_total_cost');
        
        if (platesCountField.length && platePriceField.length && transportationField.length && totalCostField.length) {
            // إضافة معالجات الأحداث
            platesCountField.on('input change', () => {
                this.calculateCTPTotalCost('cover');
            });
            
            platePriceField.on('input change', () => {
                this.calculateCTPTotalCost('cover');
            });
            
            transportationField.on('input change', () => {
                this.calculateCTPTotalCost('cover');
            });
        }
    },

    /**
     * تهيئة حساب التكلفة الإجمالية للزنكات للمحتوى الداخلي
     */
    initInternalCTPCostCalculation: function() {
        const internalPlatesCountField = $('#id_internal_ctp_plates_count');
        const internalPlatePriceField = $('#id_internal_ctp_plate_price');
        const internalTransportationField = $('#id_internal_ctp_transportation');
        const internalTotalCostField = $('#id_internal_ctp_total_cost');
        
        if (internalPlatesCountField.length && internalPlatePriceField.length && internalTransportationField.length && internalTotalCostField.length) {
            // إضافة معالجات الأحداث
            internalPlatesCountField.on('input change', () => {
                this.calculateCTPTotalCost('internal');
            });
            
            internalPlatePriceField.on('input change', () => {
                this.calculateCTPTotalCost('internal');
            });
            
            internalTransportationField.on('input change', () => {
                this.calculateCTPTotalCost('internal');
            });
        }
    },

    /**
     * حساب التكلفة الإجمالية للزنكات
     * @param {string} type - نوع الحساب ('cover' أو 'internal')
     */
    calculateCTPTotalCost: function(type) {
        let platesCountField, platePriceField, transportationField, totalCostField;
        
        if (type === 'cover') {
            platesCountField = $('#id_ctp_plates_count');
            platePriceField = $('#id_ctp_plate_price');
            transportationField = $('#id_ctp_transportation');
            totalCostField = $('#id_ctp_total_cost');
        } else if (type === 'internal') {
            platesCountField = $('#id_internal_ctp_plates_count');
            platePriceField = $('#id_internal_ctp_plate_price');
            transportationField = $('#id_internal_ctp_transportation');
            totalCostField = $('#id_internal_ctp_total_cost');
        }
        
        if (!platesCountField.length || !platePriceField.length || !transportationField.length || !totalCostField.length) {
            return;
        }
        
        // الحصول على القيم
        const platesCount = parseFloat(platesCountField.val()) || 0;
        const platePrice = parseFloat(platePriceField.val()) || 0;
        const transportation = parseFloat(transportationField.val()) || 0;
        
        // حساب التكلفة الإجمالية
        // التكلفة الإجمالية = (عدد الزنكات × سعر الزنك) + تكلفة الانتقالات
        const totalCost = (platesCount * platePrice) + transportation;
        
        // تحديث حقل التكلفة الإجمالية
        if (totalCost > 0) {
            totalCostField.val(totalCost.toFixed(2));
        } else {
            totalCostField.val('');
        }
        
        // إطلاق حدث تغيير لتحديث التكاليف الأخرى
        totalCostField.trigger('change');
    },

    /**
     * تهيئة حساب التكلفة الإجمالية للمطبعة
     */
    initPressCostCalculation: function() {
        const priceField = $('#id_press_price_per_1000');
        const runsField = $('#id_press_runs');
        const transportationField = $('#id_press_transportation');
        const totalCostField = $('#id_press_total_cost');
        
        if (priceField.length && runsField.length && transportationField.length && totalCostField.length) {
            // إضافة معالجات الأحداث مع debounce
            const debouncedCalculate = debounce(() => {
                this.calculatePressTotalCost();
            }, 100);
            
            priceField.on('input change', debouncedCalculate);
            runsField.on('input change', debouncedCalculate);
            transportationField.on('input change', debouncedCalculate);
        }
    },

    /**
     * حساب التكلفة الإجمالية للمطبعة
     */
    calculatePressTotalCost: function() {
        // منع تكرار الحساب إذا كان قيد التنفيذ
        if (this.calculatingPressCost) {
            return;
        }
        
        // إضافة debounce داخلي إضافي
        if (this.pressCostTimeout) {
            clearTimeout(this.pressCostTimeout);
        }
        
        this.pressCostTimeout = setTimeout(() => {
            this.calculatingPressCost = true;
            this._doCalculatePressCost();
        }, 50);
    },
    
    _doCalculatePressCost: function() {
        
        const priceField = $('#id_press_price_per_1000');
        const runsField = $('#id_press_runs');
        const transportationField = $('#id_press_transportation');
        const totalCostField = $('#id_press_total_cost');
        
        if (!priceField.length || !runsField.length || !transportationField.length || !totalCostField.length) {
            this.calculatingPressCost = false;
            return;
        }
        
        // الحصول على القيم
        const pricePerRun = parseFloat(priceField.val()) || 0;
        const runs = parseFloat(runsField.val()) || 0;
        const transportation = parseFloat(transportationField.val()) || 0;
        
        // حساب التكلفة الإجمالية
        // التكلفة الإجمالية = (سعر التراج × عدد التراجات) + تكلفة الانتقالات
        const totalCost = (pricePerRun * runs) + transportation;
        
        // تحديث حقل التكلفة الإجمالية
        if (totalCost > 0) {
            totalCostField.val(totalCost.toFixed(2));
        } else {
            totalCostField.val('');
        }
        
        // إطلاق حدث تغيير لتحديث التكاليف الأخرى (بدون إطلاق حساب جديد)
        totalCostField.off('change.pressCost').trigger('change').on('change.pressCost', () => {
            // منع إعادة الحساب من هذا الحدث
        });
        
        // إلغاء علامة الحساب
        this.calculatingPressCost = false;
    },

    /**
     * تهيئة الحقول القابلة للإظهار/الإخفاء
     */
    initToggleFields: function() {
        
        // تهيئة checkbox المحتوى الداخلي
        this.initInternalContentToggle();
        
        // تهيئة checkbox المقاس المفتوح
        this.initOpenSizeToggle();
        
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
                this.updateSectionLabels(true);
            } else {
                targetSection.slideUp(300);
                this.updateSectionLabels(false);
            }
            
            // إطلاق حدث مخصص
            $(document).trigger('internal-content:toggled', { isVisible: isChecked });
        });

        // تطبيق الحالة الأولية إذا كان محدد مسبقاً
        if (checkbox.prop('checked')) {
            targetSection.show();
            this.updateSectionLabels(true);
        } else {
            this.updateSectionLabels(false);
        }
        
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
            
        } else {
            // إخفاء القسم الثالث
            step3.hide();
            section3Content.hide();
            
            // تحديث أرقام الخطوات: 1, 2, 3 (بدون القسم الثالث)
            $('.step[data-step="1"] .step-number').text('1');
            $('.step[data-step="2"] .step-number').text('2');
            $('.step[data-step="4"] .step-number').text('3'); // القسم الرابع يصبح الثالث
            
        }

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
            } else {
                targetFields.slideUp(300);
            }
            
            // إطلاق حدث مخصص
            $(document).trigger('open-size:toggled', { isVisible: isChecked });
        });

        // تطبيق الحالة الأولية إذا كان محدد مسبقاً
        if (checkbox.prop('checked')) {
            targetFields.show();
        }
        
    },

    /**
     * تهيئة حقول الورق
     */
    initPaperFields: function() {
        this.initPaperTypeField();
        this.initPaperSupplierField();
        this.initPaperSheetTypeField();
        this.initPaperWeightField();
        this.initPaperOriginField();
        this.initPaperPriceField();
    },

    /**
     * تهيئة حقل نوع الورق مع Select2
     */
    initPaperTypeField: function() {
        const paperTypeField = $('#id_paper_type');
        if (!paperTypeField.length) {
            return;
        }

        // تحويل الحقل إلى Select2
        paperTypeField.select2({
            ...this.config.select2Config,
            placeholder: 'اختر نوع الورق',
            allowClear: true
        });

        // جلب أنواع الورق من API
        this.loadPaperTypes();

        // معالج تغيير نوع الورق
        paperTypeField.on('select2:select', (e) => {
            const selectedPaperType = e.params.data.id;
            console.log('🔄 تم اختيار نوع الورق:', selectedPaperType);
            
            // تحديث قائمة الموردين حسب نوع الورق المختار
            this.loadPaperSuppliers(selectedPaperType);
            
            // تحديث باقي الحقول
            this.updatePaperWeightOptions();
            this.updatePaperOrigins();
        });

        paperTypeField.on('select2:clear', () => {
            console.log('🗑️ تم مسح نوع الورق');
            
            // إعادة تحميل جميع الموردين (بدون فلتر)
            this.loadPaperSuppliers();
            
            // مسح باقي الحقول
            this.clearPaperWeightOptions();
            this.clearPaperOrigins();
        });
    },

    /**
     * تهيئة حقل مورد الورق مع Select2
     */
    initPaperSupplierField: function() {
        const paperSupplierField = $('#id_paper_supplier');
        if (!paperSupplierField.length) {
            return;
        }

        // تحويل الحقل إلى Select2
        paperSupplierField.select2({
            ...this.config.select2Config,
            placeholder: 'اختر مورد الورق',
            allowClear: true
        });

        // جلب موردي الورق من API
        this.loadPaperSuppliers();

        // معالج تغيير مورد الورق
        paperSupplierField.on('select2:select', (e) => {
            this.updatePaperSheetTypes();
            this.updatePaperOrigins();
        });

        paperSupplierField.on('select2:clear', () => {
            this.clearPaperSheetTypes();
            this.clearPaperOrigins();
        });
    },

    /**
     * تهيئة حقل مقاس الفرخ
     */
    initPaperSheetTypeField: function() {
        const paperSheetTypeField = $('#id_paper_sheet_type');
        if (!paperSheetTypeField.length) {
            return;
        }

        // معالج تغيير مقاس الفرخ
        paperSheetTypeField.on('change', () => {
            this.updatePaperWeightOptions();
            this.updatePaperOrigins();
            this.updatePieceSizeOptions(); // تحديث مقاسات القطع عند تغيير مقاس الفرخ
        });
    },

    /**
     * تهيئة حقل وزن الورق
     */
    initPaperWeightField: function() {
        const paperWeightField = $('#id_paper_weight');
        if (!paperWeightField.length) {
            return;
        }

        // معالج تغيير وزن الورق
        paperWeightField.on('change', () => {
            this.updatePaperOrigins();
        });
    },

    /**
     * تهيئة حقل منشأ الورق
     */
    initPaperOriginField: function() {
        const paperOriginField = $('#id_paper_origin');
        if (!paperOriginField.length) {
            return;
        }

        // معالج تغيير منشأ الورق
        paperOriginField.on('change', () => {
            this.updatePaperPrice();
        });
    },

    /**
     * تهيئة حقل سعر الورق
     */
    initPaperPriceField: function() {
        const paperPriceField = $('#id_paper_price');
        if (!paperPriceField.length) {
            return;
        }

        // معالج تغيير سعر الورق
        paperPriceField.on('input change', () => {
            this.updateTotalPaperCost();
        });
    },

    /**
     * جلب أنواع الورق من API
     * ملاحظة: معطل حالياً - يحتاج إنشاء API حقيقي في النظام الجديد
     */
    loadPaperTypes: function() {
        const paperTypeField = $('#id_paper_type');
        if (!paperTypeField.length) {
            return;
        }

        // جلب أنواع الورق من API
        fetch('/printing-pricing/api/paper-types/')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.paper_types) {
                    // مسح الخيارات الحالية
                    paperTypeField.empty();
                    paperTypeField.append('<option value="">-- اختر نوع الورق --</option>');
                    
                    // إضافة أنواع الورق
                    data.paper_types.forEach(type => {
                        paperTypeField.append(`<option value="${type.id}">${type.name}</option>`);
                    });
                } else {
                    console.error('فشل في جلب أنواع الورق:', data.error || 'خطأ غير معروف');
                }
            })
            .catch(error => {
                console.error('خطأ في جلب أنواع الورق:', error);
            });
    },

    /**
     * جلب موردي الورق من API مع إمكانية الفلترة حسب نوع الورق
     * @param {string} paperTypeId - معرف نوع الورق للفلترة (اختياري)
     */
    loadPaperSuppliers: function(paperTypeId = null) {
        const paperSupplierField = $('#id_paper_supplier');
        if (!paperSupplierField.length) {
            return;
        }

        // بناء URL مع معامل نوع الورق إذا وُجد
        let apiUrl = '/printing-pricing/api/paper-suppliers/';
        if (paperTypeId) {
            apiUrl += `?paper_type_id=${paperTypeId}`;
            console.log('🔍 جلب موردي الورق لنوع الورق:', paperTypeId);
        } else {
            console.log('📋 جلب جميع موردي الورق');
        }

        // جلب موردي الورق من API
        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.suppliers) {
                    // مسح الخيارات الحالية
                    paperSupplierField.empty();
                    paperSupplierField.append('<option value="">-- اختر مورد الورق --</option>');
                    
                    // إضافة موردي الورق
                    data.suppliers.forEach(supplier => {
                        paperSupplierField.append(`<option value="${supplier.id}">${supplier.name}</option>`);
                    });
                    
                    // رسالة توضيحية
                    if (data.filtered_by_paper_type) {
                        console.log(`✅ تم جلب ${data.total_count} مورد لنوع الورق: ${data.filtered_by_paper_type.name}`);
                    } else {
                        console.log(`✅ تم جلب ${data.total_count} مورد ورق`);
                    }
                    
                    // تحديث Select2 لإظهار التغييرات أولاً
                    paperSupplierField.trigger('change');
                    
                    // اختيار أول مورد تلقائياً إذا وُجد (مع تأخير بسيط)
                    if (data.suppliers.length > 0) {
                        const self = this; // حفظ مرجع this
                        setTimeout(() => {
                            const firstSupplier = data.suppliers[0];
                            paperSupplierField.val(firstSupplier.id);
                            console.log(`🔄 تم اختيار أول مورد تلقائياً: ${firstSupplier.name}`);
                            
                            // تشغيل حدث التغيير لتحديث الحقول التابعة
                            paperSupplierField.trigger('change');
                            
                            // تحديث مقاسات الفرخ ومنشأ الورق يدوياً (لأن الاختيار التلقائي لا يشغل select2:select)
                            self.updatePaperSheetTypes();
                            self.updatePaperWeightOptions();
                            self.updatePaperOrigins();
                        }, 100);
                    }
                } else {
                    console.error('فشل في جلب موردي الورق:', data.error || 'خطأ غير معروف');
                }
            })
            .catch(error => {
                console.error('خطأ في جلب موردي الورق:', error);
            });
    },

    /**
     * تحديث خيارات وزن الورق حسب نوع الورق المختار
     */
    updatePaperWeightOptions: function() {
        const paperTypeField = $('#id_paper_type');
        const paperSupplierField = $('#id_paper_supplier');
        const paperSheetTypeField = $('#id_paper_sheet_type');
        const paperWeightField = $('#id_paper_weight');
        
        if (!paperTypeField.length || !paperWeightField.length) {
            return;
        }

        const selectedType = paperTypeField.val();
        if (!selectedType) {
            this.clearPaperWeightOptions();
            return;
        }

        // بناء URL مع جميع المعايير المتاحة
        let apiUrl = `/printing-pricing/api/paper-weights/?paper_type_id=${selectedType}`;
        
        const selectedSupplier = paperSupplierField.val();
        if (selectedSupplier) {
            apiUrl += `&supplier_id=${selectedSupplier}`;
        }
        
        const selectedSheetType = paperSheetTypeField.val();
        if (selectedSheetType) {
            apiUrl += `&sheet_type=${selectedSheetType}`;
        }

        console.log('🔍 جلب أوزان الورق للمعايير:', {
            paper_type: selectedType,
            supplier: selectedSupplier || 'غير محدد',
            sheet_type: selectedSheetType || 'غير محدد'
        });

        // جلب أوزان الورق من API
        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.weights) {
                    // مسح الخيارات الحالية
                    paperWeightField.empty();
                    paperWeightField.append('<option value="">-- اختر وزن الورق --</option>');
                    
                    // إضافة الأوزان الجديدة
                    data.weights.forEach(weight => {
                        paperWeightField.append(`<option value="${weight.value}">${weight.display_name}</option>`);
                    });
                    
                    // اختيار أول وزن تلقائياً إذا وُجد
                    if (data.weights.length > 0) {
                        const firstWeight = data.weights[0];
                        paperWeightField.val(firstWeight.value);
                        console.log(`🔄 تم اختيار أول وزن ورق تلقائياً: ${firstWeight.display_name}`);
                        paperWeightField.trigger('change');
                    }
                } else {
                    this.clearPaperWeightOptions();
                }
            })
            .catch(error => {
                console.error('خطأ في جلب أوزان الورق:', error);
                this.clearPaperWeightOptions();
            });
    },

    /**
     * تحديث مقاسات الفرخ حسب مورد الورق ونوع الورق
     */
    updatePaperSheetTypes: function() {
        const paperTypeField = $('#id_paper_type');
        const paperSupplierField = $('#id_paper_supplier');
        const paperSheetTypeField = $('#id_paper_sheet_type');
        
        if (!paperTypeField.length || !paperSupplierField.length || !paperSheetTypeField.length) {
            return;
        }

        const selectedType = paperTypeField.val();
        const selectedSupplier = paperSupplierField.val();
        
        if (!selectedType || !selectedSupplier) {
            this.clearPaperSheetTypes();
            return;
        }

        // جلب مقاسات الفرخ من API
        fetch(`/printing-pricing/api/paper-sheet-types/?supplier_id=${selectedSupplier}&paper_type_id=${selectedType}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.sheet_types) {
                    // مسح الخيارات الحالية
                    paperSheetTypeField.empty();
                    paperSheetTypeField.append('<option value="">-- اختر مقاس الفرخ --</option>');
                    
                    // إضافة المقاسات الجديدة
                    const uniqueSheetTypes = new Set();
                    data.sheet_types.forEach(item => {
                        if (item.sheet_type && !uniqueSheetTypes.has(item.sheet_type)) {
                            uniqueSheetTypes.add(item.sheet_type);
                            paperSheetTypeField.append(`<option value="${item.sheet_type}">${item.display_name || item.sheet_type}</option>`);
                        }
                    });
                    
                    // اختيار أول مقاس تلقائياً إذا وُجد
                    if (data.sheet_types.length > 0) {
                        const firstSheetType = data.sheet_types[0];
                        paperSheetTypeField.val(firstSheetType.sheet_type);
                        console.log(`🔄 تم اختيار أول مقاس فرخ تلقائياً: ${firstSheetType.display_name || firstSheetType.sheet_type}`);
                        paperSheetTypeField.trigger('change');
                    }
                } else {
                    this.clearPaperSheetTypes();
                }
            })
            .catch(error => {
                console.error('خطأ في جلب مقاسات الفرخ:', error);
                this.clearPaperSheetTypes();
            });
    },

    /**
     * تحديث منشأ الورق حسب المعايير المختارة
     */
    updatePaperOrigins: function() {
        const paperTypeField = $('#id_paper_type');
        const paperSupplierField = $('#id_paper_supplier');
        const paperSheetTypeField = $('#id_paper_sheet_type');
        const paperWeightField = $('#id_paper_weight');
        const paperOriginField = $('#id_paper_origin');
        
        if (!paperOriginField.length) {
            return;
        }

        const selectedType = paperTypeField.val();
        const selectedSupplier = paperSupplierField.val();
        const selectedSheetType = paperSheetTypeField.val();
        const selectedWeight = paperWeightField.val();
        
        if (!selectedType || !selectedSupplier) {
            this.clearPaperOrigins();
            return;
        }

        // بناء URL مع المعاملات
        let apiUrl = `/printing-pricing/api/paper-origins/?paper_type_id=${selectedType}&supplier_id=${selectedSupplier}`;
        if (selectedSheetType) apiUrl += `&sheet_type=${selectedSheetType}`;
        if (selectedWeight) apiUrl += `&weight=${selectedWeight}`;

        // جلب منشأ الورق من API
        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.origins) {
                    // مسح الخيارات الحالية
                    paperOriginField.empty();
                    paperOriginField.append('<option value="">-- اختر منشأ الورق --</option>');
                    
                    // إضافة المناشئ الجديدة
                    const uniqueOrigins = new Set();
                    data.origins.forEach(item => {
                        if (item.origin && !uniqueOrigins.has(item.origin)) {
                            uniqueOrigins.add(item.origin);
                            paperOriginField.append(`<option value="${item.origin}">${item.display_name || item.origin}</option>`);
                        }
                    });
                    
                    // اختيار أول منشأ تلقائياً إذا وُجد
                    if (data.origins.length > 0) {
                        const firstOrigin = data.origins[0];
                        paperOriginField.val(firstOrigin.origin);
                        console.log(`🔄 تم اختيار أول منشأ ورق تلقائياً: ${firstOrigin.display_name || firstOrigin.origin}`);
                        paperOriginField.trigger('change');
                    }
                } else {
                    this.clearPaperOrigins();
                }
            })
            .catch(error => {
                console.error('خطأ في جلب منشأ الورق:', error);
                this.clearPaperOrigins();
            });
    },

    /**
     * تحديث سعر الورق حسب المعايير المختارة
     */
    updatePaperPrice: function() {
        const paperTypeField = $('#id_paper_type');
        const paperSupplierField = $('#id_paper_supplier');
        const paperSheetTypeField = $('#id_paper_sheet_type');
        const paperWeightField = $('#id_paper_weight');
        const paperOriginField = $('#id_paper_origin');
        const paperPriceField = $('#id_paper_price');
        
        if (!paperPriceField.length) {
            return;
        }

        const selectedType = paperTypeField.val();
        const selectedSupplier = paperSupplierField.val();
        const selectedSheetType = paperSheetTypeField.val();
        const selectedWeight = paperWeightField.val();
        const selectedOrigin = paperOriginField.val();
        
        if (!selectedType || !selectedSupplier || !selectedSheetType || !selectedWeight || !selectedOrigin) {
            paperPriceField.val('');
            return;
        }

        // جلب سعر الورق من API
        const apiUrl = `/printing-pricing/api/paper-price/?paper_type_id=${selectedType}&supplier_id=${selectedSupplier}&sheet_type=${selectedSheetType}&weight=${selectedWeight}&origin=${selectedOrigin}`;
        
        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success && data.price !== undefined) {
                    paperPriceField.val(data.price);
                    this.updateTotalPaperCost();
                } else {
                    paperPriceField.val('');
                }
            })
            .catch(error => {
                console.error('خطأ في جلب سعر الورق:', error);
                paperPriceField.val('');
            });
    },

    /**
     * تحديث التكلفة الإجمالية للورق
     */
    updateTotalPaperCost: function() {
        const paperPriceField = $('#id_paper_price');
        const paperQuantityField = $('#id_paper_quantity');
        const totalPaperCostField = $('#id_total_paper_cost');
        
        if (!paperPriceField.length || !paperQuantityField.length || !totalPaperCostField.length) {
            return;
        }

        const price = parseFloat(paperPriceField.val()) || 0;
        const quantity = parseFloat(paperQuantityField.val()) || 0;
        const totalCost = price * quantity;
        
        totalPaperCostField.val(totalCost > 0 ? totalCost.toFixed(2) : '');
    },

    /**
     * مسح خيارات وزن الورق
     */
    clearPaperWeightOptions: function() {
        const paperWeightField = $('#id_paper_weight');
        if (paperWeightField.length) {
            paperWeightField.empty();
            paperWeightField.append('<option value="">-- اختر وزن الورق --</option>');
        }
    },

    /**
     * مسح خيارات مقاسات الفرخ
     */
    clearPaperSheetTypes: function() {
        const paperSheetTypeField = $('#id_paper_sheet_type');
        if (paperSheetTypeField.length) {
            paperSheetTypeField.empty();
            paperSheetTypeField.append('<option value="">-- اختر مقاس الفرخ --</option>');
        }
    },

    /**
     * مسح خيارات منشأ الورق
     */
    clearPaperOrigins: function() {
        const paperOriginField = $('#id_paper_origin');
        if (paperOriginField.length) {
            paperOriginField.empty();
            paperOriginField.append('<option value="">-- اختر منشأ الورق --</option>');
        }
    },

    /**
     * تهيئة خدمات ما بعد الطباعة (إخفاء/إظهار)
     */
    initFinishingServices: function() {
        // قائمة جميع الخدمات (checkbox → fields)
        const services = [
            // خدمات الغلاف
            { checkbox: '#enable_cover_coating', fields: '#cover-coating-fields' },
            { checkbox: '#enable_cover_folding', fields: '#cover-folding-fields' },
            { checkbox: '#enable_cover_die_cut', fields: '#cover-die-cut-fields' },
            { checkbox: '#enable_cover_packaging', fields: '#cover-packaging-fields' },
            
            // خدمات المحتوى الداخلي
            { checkbox: '#enable_internal_coating', fields: '#internal-coating-fields' },
            { checkbox: '#enable_internal_folding', fields: '#internal-folding-fields' },
            { checkbox: '#enable_internal_die_cut', fields: '#internal-die-cut-fields' },
            { checkbox: '#enable_internal_packaging', fields: '#internal-packaging-fields' }
        ];
        
        // تطبيق نفس المنطق على جميع الخدمات
        services.forEach(service => {
            const checkbox = $(service.checkbox);
            const fields = $(service.fields);
            
            if (checkbox.length && fields.length) {
                // إخفاء الحقول في البداية
                fields.hide();
                
                // معالج التغيير للـ checkbox
                checkbox.on('change', function() {
                    if ($(this).is(':checked')) {
                        fields.slideDown(300);
                    } else {
                        fields.slideUp(300);
                    }
                });
                
                // جعل الـ header كله قابل للنقر
                const header = checkbox.closest('.card-header');
                if (header.length) {
                    header.css('cursor', 'pointer');
                    header.on('click', function(e) {
                        // تجاهل النقر على الـ checkbox نفسه
                        if (e.target !== checkbox[0] && !$(e.target).is('label')) {
                            checkbox.prop('checked', !checkbox.prop('checked')).trigger('change');
                        }
                    });
                }
                
                // تحديث الحالة الأولية (للاستعادة من الحفظ)
                if (checkbox.is(':checked')) {
                    fields.show();
                }
            }
        });
        
        console.log('✅ تم تهيئة خدمات ما بعد الطباعة (8 خدمات)');
        
        // تحميل موردي الخدمات
        this.loadFinishingSuppliers();
        
        // تهيئة handlers للخدمات
        this.initFinishingServiceHandlers();
    },
    
    /**
     * تحميل موردي خدمات ما بعد الطباعة
     */
    loadFinishingSuppliers: function() {
        // تحميل موردي التغطية للغلاف
        this.loadCoatingSuppliers('#id_cover_coating_supplier');
        
        // تحميل موردي التغطية للمحتوى الداخلي
        this.loadCoatingSuppliers('#id_internal_coating_supplier');
    },
    
    /**
     * تحميل موردي التغطية
     */
    loadCoatingSuppliers: function(selectId) {
        const selectElement = $(selectId);
        if (!selectElement.length) return;
        
        $.ajax({
            url: '/supplier/api/suppliers/by-service-type/',
            method: 'GET',
            data: {
                service_type: 'coating'
            },
            success: (response) => {
                selectElement.empty();
                selectElement.append('<option value="">اختر المورد</option>');
                
                if (response.suppliers && response.suppliers.length > 0) {
                    response.suppliers.forEach(supplier => {
                        selectElement.append(
                            `<option value="${supplier.id}">${supplier.name}</option>`
                        );
                    });
                    console.log(`✅ تم تحميل ${response.suppliers.length} مورد تغطية`);
                } else {
                    selectElement.append('<option value="" disabled>لا يوجد موردين متاحين</option>');
                }
            },
            error: (xhr, status, error) => {
                console.error('❌ خطأ في تحميل موردي التغطية:', error);
                selectElement.append('<option value="" disabled>خطأ في التحميل</option>');
            }
        });
    },
    
    /**
     * تهيئة handlers لخدمات ما بعد الطباعة
     */
    initFinishingServiceHandlers: function() {
        // التغطية للغلاف
        this.initCoatingHandlers('#id_cover_coating_supplier', '#id_cover_coating_type', '#id_cover_coating_cost');
        
        // التغطية للمحتوى الداخلي
        this.initCoatingHandlers('#id_internal_coating_supplier', '#id_internal_coating_type', '#id_internal_coating_cost');
    },
    
    /**
     * تهيئة handlers للتغطية
     */
    initCoatingHandlers: function(supplierSelect, typeSelect, costInput) {
        const $supplier = $(supplierSelect);
        const $type = $(typeSelect);
        const $cost = $(costInput);
        
        if (!$supplier.length || !$type.length || !$cost.length) return;
        
        // عند تغيير المورد، تحميل خدماته
        $supplier.on('change', () => {
            const supplierId = $supplier.val();
            
            if (!supplierId) {
                $type.empty().append('<option value="">اختر النوع</option>');
                $cost.val('');
                return;
            }
            
            // تحميل خدمات التغطية للمورد
            $.ajax({
                url: '/supplier/api/supplier-coating-services/',
                method: 'GET',
                data: { supplier_id: supplierId },
                success: (response) => {
                    $type.empty().append('<option value="">اختر النوع</option>');
                    
                    if (response.services && response.services.length > 0) {
                        response.services.forEach(service => {
                            $type.append(
                                `<option value="${service.id}" data-price="${service.price}">${service.name}</option>`
                            );
                        });
                        console.log(`✅ تم تحميل ${response.services.length} خدمة تغطية`);
                        
                        // اختيار أول خدمة تلقائياً
                        $type.val(response.services[0].id).trigger('change');
                        console.log(`🔄 تم اختيار أول خدمة تلقائياً: ${response.services[0].name}`);
                    } else {
                        $type.append('<option value="" disabled>لا توجد خدمات متاحة</option>');
                    }
                },
                error: (xhr, status, error) => {
                    console.error('❌ خطأ في تحميل خدمات التغطية:', error);
                    $type.empty().append('<option value="" disabled>خطأ في التحميل</option>');
                }
            });
        });
        
        // عند تغيير نوع التغطية، تحديث السعر
        $type.on('change', () => {
            const selectedOption = $type.find('option:selected');
            const price = selectedOption.data('price');
            
            if (price) {
                $cost.val(price);
                console.log(`💰 تم تحديث سعر التغطية: ${price} ر.س`);
            } else {
                $cost.val('');
            }
        });
    },

    /**
     * تهيئة نظام التحقق من صحة النموذج
     */
    initFormValidation: function() {
        
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
            return false;
        }
        
        return true;
    },

    /**
     * التحقق من صحة قسم معين (بدون إشعارات)
     */
    validateSection: function(sectionNumber) {
        const missingFields = this.getMissingRequiredFieldsInSection(sectionNumber);
        return missingFields.length === 0;
    },

    /**
     * التحقق من صحة قسم معين مع إظهار الإشعارات
     */
    validateSectionWithNotification: function(sectionNumber) {
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
                    }
                });
                
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
                        } else {
                            // الحقول العادية الأخرى
                            const value = element.val();
                            if (value !== null && value !== undefined && value !== '') {
                                const fieldData = {
                                    value: value,
                                    isSelect2: false
                                };
                                
                                // معالجة خاصة للماكينة - حفظ الاسم أيضاً
                                if (fieldName === 'press' && value) {
                                    const selectedOption = element.find(`option[value="${value}"]`);
                                    if (selectedOption.length) {
                                        fieldData.text = selectedOption.text();
                                        fieldData.name = selectedOption.text(); // حفظ اسم الماكينة
                                    }
                                }
                                
                                formData[fieldName] = fieldData;
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
            
            
            // إظهار رسالة مفصلة عن ما تم حفظه
            const savedFields = Object.keys(formData);
            if (savedFields.length > 0) {
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
                    
                    // إعطاء أولوية لاستعادة الحقول التي لا تعتمد على APIs
                    const priorityFields = ['client', 'title', 'quantity', 'order_type', 'has_internal_content', 'open_size_width', 'open_size_height', 'internal_page_count', 'binding_side', 'print_sides', 'internal_print_sides'];
                    const colorFields = ['colors_design', 'colors_front', 'colors_back', 'design_price', 'internal_colors_design', 'internal_colors_front', 'internal_colors_back', 'internal_design_price']; // تحتاج print_sides أولاً
                    const apiDependentFields = ['product_type', 'product_size', 'paper_type', 'supplier', 'press', 'ctp_supplier', 'internal_ctp_supplier'];
                    const customSizeFields = ['product_width', 'product_height', 'piece_width', 'piece_height']; // تحتاج product_size و piece_size أولاً
                    const paperFields = ['paper_supplier', 'paper_sheet_type', 'paper_weight', 'paper_origin', 'paper_price', 'paper_quantity']; // تحتاج paper_type أولاً
                    const pieceSizeFields = ['piece_size']; // تحتاج paper_origin أولاً
                    const secondaryFields = ['press_price_per_1000', 'press_runs', 'press_transportation', 'ctp_plate_size', 'internal_ctp_plate_size', 'ctp_plates_count', 'internal_ctp_plates_count', 'montage_count', 'montage_info', 'paper_sheets_count', 'paper_total_cost']; // تحتاج تحميل المورد أولاً
                    const hiddenFields = ['use-open-size']; // الحقول المخفية داخل أقسام
                    
                    // استعادة الحقول ذات الأولوية أولاً
                    priorityFields.forEach(fieldName => {
                        if (draft.data[fieldName]) {
                            this.restoreField(fieldName, draft.data[fieldName]);
                        }
                    });
                    
                    // تأخير قصير لاستعادة حقول الألوان (بعد print_sides)
                    setTimeout(() => {
                        colorFields.forEach(fieldName => {
                            if (draft.data[fieldName]) {
                                this.restoreField(fieldName, draft.data[fieldName]);
                            }
                        });
                        
                        // إعادة حساب الزنكات بعد استعادة حقول الألوان
                        setTimeout(() => {
                            this.calculatePlatesCount('cover');
                            this.calculatePlatesCount('internal');
                        }, 100);
                    }, 500); // تأخير قصير لضمان تحديث عرض حقول الألوان
                    
                    // تأخير استعادة الحقول التي تعتمد على APIs
                    setTimeout(() => {
                        apiDependentFields.forEach(fieldName => {
                            if (draft.data[fieldName]) {
                                this.restoreField(fieldName, draft.data[fieldName]);
                            }
                        });
                    }, 1000);
                    
                    // استعادة حقول المقاسات المخصصة (بعد product_size و piece_size)
                    setTimeout(() => {
                        customSizeFields.forEach(fieldName => {
                            if (draft.data[fieldName]) {
                                this.restoreField(fieldName, draft.data[fieldName]);
                            }
                        });
                        
                        // استعادة print_direction بعد الأبعاد عشان ما يتغيرش تلقائياً
                        if (draft.data['print_direction']) {
                            setTimeout(() => {
                                this.restoreField('print_direction', draft.data['print_direction']);
                            }, 200); // تأخير صغير بعد الأبعاد
                        }
                    }, 1300); // تأخير قصير بعد المقاسات الأساسية
                    
                    // استعادة حقول الورق (بعد paper_type)
                    setTimeout(() => {
                        paperFields.forEach(fieldName => {
                            if (draft.data[fieldName]) {
                                this.restoreField(fieldName, draft.data[fieldName]);
                            }
                        });
                    }, 1500); // تأخير لضمان تحميل خيارات الورق
                    
                    // استعادة مقاس القطع - polling بسيط وفعال
                    if (draft.data['piece_size']) {
                        const pieceSizeValue = draft.data['piece_size'].value;
                        const pieceSizeElement = $('#id_piece_size');
                        let restored = false;
                        let attempts = 0;
                        const maxAttempts = 30; // 30 محاولة = 6 ثوانٍ
                        
                        const checkAndRestore = () => {
                            if (restored) return;
                            
                            attempts++;
                            const options = pieceSizeElement.find('option:not([value=""])');
                            
                            if (options.length > 0) {
                                // انتظار 800ms للسماح لجميع الـ handlers بالانتهاء
                                setTimeout(() => {
                                    // استعادة القيمة
                                    pieceSizeElement.val(pieceSizeValue);
                                    
                                    // التحقق من النجاح
                                    if (pieceSizeElement.val() === pieceSizeValue) {
                                        pieceSizeElement.trigger('change');
                                        restored = true;
                                        
                                        // التحقق بعد 500ms للتأكد من عدم المسح وإعادة الاستعادة إذا لزم الأمر
                                        setTimeout(() => {
                                            const currentValue = pieceSizeElement.val();
                                            if (currentValue !== pieceSizeValue) {
                                                pieceSizeElement.val(pieceSizeValue);
                                                pieceSizeElement.trigger('change');
                                            }
                                        }, 500);
                                    }
                                }, 800);
                            } else if (attempts < maxAttempts) {
                                // إعادة المحاولة بعد 200ms
                                setTimeout(checkAndRestore, 200);
                            }
                        };
                        
                        // بدء الفحص
                        checkAndRestore();
                    }
                    
                    // تأخير متوسط لاستعادة الحقول الثانوية (مقاسات الزنكات والمونتاج)
                    setTimeout(() => {
                        secondaryFields.forEach(fieldName => {
                            if (draft.data[fieldName]) {
                                this.restoreField(fieldName, draft.data[fieldName]);
                            }
                        });
                    }, 2000); // تأخير متوسط لضمان تحميل جميع البيانات
                    
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
                        }
                    }
                    
                    this.showRestoreNotification();
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
                
                // تحديث Select2 وإطلاق الأحداث المناسبة
                element.trigger('change');
                
                // معالجة خاصة لحقول CTP لتحميل المقاسات
                if (fieldName === 'ctp_supplier' || fieldName === 'internal_ctp_supplier') {
                    // تجاهل القيم الفارغة أو غير الصحيحة
                    if (!fieldData.value || fieldData.value === '' || fieldData.text === '-- اختر المورد --') {
                        return;
                    }
                    
                    
                    // إطلاق حدث select2:select لتحميل مقاسات الزنكات
                    element.trigger('select2:select');
                    
                }
                
                // معالجة خاصة لحقول المطبعة لتحميل الماكينات والأسعار
                if (fieldName === 'supplier' || fieldName === 'press') {
                    // تجاهل القيم الفارغة أو غير الصحيحة
                    if (!fieldData.value || fieldData.value === '' || fieldData.text === '-- اختر المطبعة --' || fieldData.text === '-- اختر الماكينة --') {
                        return;
                    }
                    
                    
                    // إطلاق حدث select2:select لتحميل البيانات التابعة
                    element.trigger('select2:select');
                    
                }
                
                // معالجة خاصة لحقول الورق (تسلسل متتابع)
                if (fieldName === 'paper_type') {
                    if (!fieldData.value || fieldData.value === '') return;
                    
                    const selectData = element.select2('data');
                    if (selectData && selectData.length > 0) {
                        element.trigger({
                            type: 'select2:select',
                            params: { data: selectData[0] }
                        });
                    }
                }
                
                if (fieldName === 'paper_supplier') {
                    if (!fieldData.value || fieldData.value === '') return;
                    
                    const selectData = element.select2('data');
                    if (selectData && selectData.length > 0) {
                        element.trigger({
                            type: 'select2:select',
                            params: { data: selectData[0] }
                        });
                    }
                }
                
                if (fieldName === 'piece_size') {
                    // تجاهل القيم الفارغة
                    if (!fieldData.value || fieldData.value === '') {
                        return;
                    }
                    
                    // الانتظار لحين تحميل الخيارات
                    let waitAttempts = 0;
                    const maxWaitAttempts = 20; // حد أقصى 4 ثوانٍ
                    
                    const waitForOptions = () => {
                        const options = element.find('option:not([value=""])');
                        
                        if (options.length === 0 && waitAttempts < maxWaitAttempts) {
                            waitAttempts++;
                            setTimeout(waitForOptions, 200);
                            return;
                        }
                        
                        if (options.length === 0) {
                            console.warn('⚠️ لم يتم تحميل خيارات مقاس القطع');
                            return;
                        }
                        
                        // محاولة استعادة القيمة
                        element.val(fieldData.value);
                        
                        if (element.val() === fieldData.value) {
                            // إطلاق حدث change لحساب المونتاج
                            element.trigger('change');
                            console.log(`✅ تم استعادة مقاس القطع: ${fieldData.value}`);
                        } else {
                            console.warn(`⚠️ فشل استعادة مقاس القطع: ${fieldData.value} (غير موجود في الخيارات)`);
                        }
                    };
                    
                    waitForOptions();
                    return; // الخروج لأننا بنعالج بشكل async
                }
                
                if (fieldName === 'product_size') {
                    if (!fieldData.value || fieldData.value === '') return;
                    element.trigger('change');
                }
            } else {
                // معالجة خاصة للـ checkboxes
                if (fieldData.isCheckbox) {
                    element.prop('checked', fieldData.value);
                } else {
                    // استعادة الحقول العادية
                    element.val(fieldData.value);
                    
                    // إطلاق حدث change للحقول المهمة
                    if (['print_direction', 'print_sides', 'order_type'].includes(fieldName)) {
                        element.trigger('change');
                    }
                    
                    // التحقق من نجاح الاستعادة
                    if (element.val() !== fieldData.value) {
                        
                        // للماكينات، حاول البحث بالاسم ثم اختيار أول خيار متاح
                        if (fieldName === 'press') {
                            // انتظار أطول للتأكد من تحميل الماكينات
                            let waitAttempts = 0;
                            const maxWaitAttempts = 15; // حد أقصى 3 ثوانٍ (15 × 200ms)
                            
                            const waitForMachines = () => {
                                // التحقق من وجود ماكينات محملة
                                const options = element.find('option:not([value=""])');
                                if (options.length === 0 && waitAttempts < maxWaitAttempts) {
                                    waitAttempts++;
                                    setTimeout(waitForMachines, 200); // إعادة المحاولة
                                    return;
                                } else if (options.length === 0) {
                                    console.warn('⚠️ انتهت محاولات انتظار تحميل الماكينات');
                                    return;
                                }
                                
                                let foundOption = null;
                                
                                // البحث بالاسم إذا كان متوفراً
                                if (fieldData.name || fieldData.text) {
                                    const searchName = fieldData.name || fieldData.text;
                                    element.find('option').each(function() {
                                        const optionText = $(this).text();
                                        if (optionText === searchName || optionText.includes(searchName.split(' - ')[0])) {
                                            foundOption = $(this);
                                            return false; // break
                                        }
                                    });
                                    
                                    if (foundOption && foundOption.val()) {
                                        element.val(foundOption.val());
                                        element.trigger('change');
                                        return;
                                    }
                                }
                                
                                // إذا لم يتم العثور بالاسم، اختر الأول المتاح
                                if (options.length > 0) {
                                    const firstOption = options.first();
                                    element.val(firstOption.val());
                                    element.trigger('change');
                                } else {
                                    console.warn(`⚠️ لا توجد ماكينات متاحة للاختيار`);
                                }
                            };
                            
                            // بدء عملية الانتظار والاستعادة
                            setTimeout(waitForMachines, 500);
                            return; // تخطي trigger الفوري
                        } else {
                            return; // تخطي trigger إذا فشلت الاستعادة
                        }
                    }
                }
                
                // تأخير trigger لضمان تحميل البيانات أولاً
                setTimeout(() => {
                    element.trigger('change');
                    
                    // معالجة خاصة لحقول عدد الأوجه لتحديث عرض حقول الألوان
                    if (fieldName === 'print_sides' || fieldName === 'internal_print_sides') {
                        
                        // تأخير إضافي لضمان وجود العناصر
                        setTimeout(() => {
                            // تحديث عرض حقول الألوان
                            if (fieldName === 'print_sides') {
                                const printSidesElement = document.getElementById('id_print_sides');
                                const singleSideColors = document.getElementById('single-side-colors');
                                const doubleSideColors = document.getElementById('double-side-colors');
                                
                                if (printSidesElement && singleSideColors && doubleSideColors) {
                                    this.updateColorsFields(printSidesElement, singleSideColors, doubleSideColors);
                                } else {
                                    console.warn(`⚠️ لم يتم العثور على عناصر حقول الألوان للغلاف`);
                                }
                            } else if (fieldName === 'internal_print_sides') {
                                const internalPrintSidesElement = document.getElementById('id_internal_print_sides');
                                const internalSingleSideColors = document.getElementById('internal-single-side-colors');
                                const internalDoubleSideColors = document.getElementById('internal-double-side-colors');
                                
                                if (internalPrintSidesElement && internalSingleSideColors && internalDoubleSideColors) {
                                    this.updateColorsFields(internalPrintSidesElement, internalSingleSideColors, internalDoubleSideColors);
                                } else {
                                    console.warn(`⚠️ لم يتم العثور على عناصر حقول الألوان للمحتوى الداخلي`);
                                }
                            }
                        }, 50); // تأخير قصير لضمان وجود العناصر
                    }
                    
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
        
    },

    /**
     * حفظ snapshot لخدمة المورد في OrderService (المرحلة الثالثة)
     * يُستدعى تلقائياً عند اختيار ماكينة أو زنكة أو ورق
     */
    _saveSupplierServiceSnapshot: function(category, itemId, serviceId) {
        if (!serviceId) return;

        // نحتاج order_id — نجلبه من الـ URL أو hidden field
        const orderIdField = document.getElementById('id_order_id') || document.querySelector('[name="order_id"]');
        const orderId = orderIdField ? orderIdField.value : null;
        if (!orderId) return; // لو مش في صفحة تعديل طلب موجود، نتجاهل

        const quantity = parseInt($('#id_quantity').val() || 1);
        const payload  = {
            order_id:            orderId,
            service_category:    category,
            service_name:        itemId,
            supplier_service_id: serviceId,
            quantity:            quantity,
        };

        fetch('/printing-pricing/api/save-order-service-supplier/', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': this.getCSRFToken() },
            body:    JSON.stringify(payload),
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                console.log(`✅ تم حفظ snapshot للخدمة ${serviceId} في الطلب ${orderId}`);
            }
        })
        .catch(err => console.warn('⚠️ فشل حفظ snapshot:', err));
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
});

// دالة debounce مساعدة
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
