/**
 * ملف JavaScript لنموذج التسعير
 */

document.addEventListener('DOMContentLoaded', function() {
    // تعريف المتغيرات العامة للغلاف
    const hasInternalContent = document.getElementById('id_has_internal_content');
    const internalFields = document.getElementById('internal-fields');
    const step3Element = document.getElementById('step-3');
    const section3Element = document.getElementById('section-3');
    const section2HeaderElement = document.querySelector('#section-2 .section-header h4');
    const step2Element = document.getElementById('step-2');
    
    // متغيرات الغلاف
    const printSidesSelect = document.getElementById('id_print_sides');
    const singleSideColors = document.getElementById('single-side-colors');
    const doubleSideColors = document.getElementById('double-side-colors');
    const montageInfoField = document.getElementById('id_montage_info');
    const orderTypeSelect = document.getElementById('id_order_type');
    const offsetFields = document.getElementById('offset-fields');
    
    // متغيرات المحتوى الداخلي
    const internalPrintSidesSelect = document.getElementById('id_internal_print_sides');
    const internalSingleSideColors = document.getElementById('internal-single-side-colors');
    const internalDoubleSideColors = document.getElementById('internal-double-side-colors');
    const internalMontageInfoField = document.getElementById('id_internal_montage_info');
    const internalOrderTypeSelect = document.getElementById('id_internal_order_type');
    const internalOffsetFields = document.getElementById('internal-offset-fields');
    
    // متغيرات المقاس المخصص
    const paperSizeSelect = document.getElementById('id_product_size');
    const customSizeFields = document.getElementById('custom-size-fields');
    
    // متغيرات المقاس المفتوح
    const useOpenSizeCheckbox = document.getElementById('use-open-size');
    const openSizeFields = document.getElementById('open-size-fields');
    
    // متغيرات الزنكات (CTP) للغلاف
    const ctpFields = document.getElementById('ctp-fields');
    const ctpPlateSizeSelect = document.getElementById('id_ctp_plate_size');
    const ctpCustomSizeFields = document.getElementById('ctp-custom-size-fields');
    const ctpPlatesCount = document.getElementById('id_ctp_plates_count');
    const ctpPlatePrice = document.getElementById('id_ctp_plate_price');
    const ctpTransportation = document.getElementById('id_ctp_transportation');
    const ctpTotalCost = document.getElementById('id_ctp_total_cost');
    
    // متغيرات الزنكات (CTP) للمحتوى الداخلي
    const internalCtpFields = document.getElementById('internal-ctp-fields');
    const internalCtpPlateSizeSelect = document.getElementById('id_internal_ctp_plate_size');
    const internalCtpCustomSizeFields = document.getElementById('internal-ctp-custom-size-fields');
    const internalCtpPlatesCount = document.getElementById('id_internal_ctp_plates_count');
    const internalCtpPlatePrice = document.getElementById('id_internal_ctp_plate_price');
    const internalCtpTransportation = document.getElementById('id_internal_ctp_transportation');
    const internalCtpTotalCost = document.getElementById('id_internal_ctp_total_cost');
    
    // التنقل بين الأقسام
    const sections = ['section-1', 'section-2', 'section-3', 'section-4', 'section-5'];
    const steps = ['step-1', 'step-2', 'step-3', 'step-4', 'step-5'];
    
    function showSection(sectionId) {
        // إخفاء جميع الأقسام
        sections.forEach(id => {
            document.getElementById(id).classList.add('section-hidden');
        });
        
        // إظهار القسم المحدد
        document.getElementById(sectionId).classList.remove('section-hidden');
        
        // تحديث مؤشر الخطوات
        const currentIndex = sections.indexOf(sectionId);
        steps.forEach((step, index) => {
            if (index < currentIndex) {
                document.getElementById(step).className = 'step completed clickable';
            } else if (index === currentIndex) {
                document.getElementById(step).className = 'step active clickable';
            } else {
                document.getElementById(step).className = 'step clickable';
            }
        });
    }
    
    // إضافة معالجة النقر على مؤشرات الخطوات
    steps.forEach(stepId => {
        const stepElement = document.getElementById(stepId);
        if (stepElement) {
            stepElement.addEventListener('click', function() {
                const targetSection = this.getAttribute('data-section');
                // تحقق مما إذا كان قسم المحتوى الداخلي غير ضروري
                if (targetSection === 'section-3' && (!hasInternalContent || !hasInternalContent.checked)) {
                    console.log('تخطي قسم المحتوى الداخلي لأنه غير مفعل');
                    showSection('section-4'); // انتقل إلى قسم التسعير مباشرة
                    return;
                }
                if (targetSection) {
                    showSection(targetSection);
                }
            });
        }
    });
    
    // تعريف أزرار التنقل
    const navigationButtons = {
        'to-section-1': 'section-1',
        'to-section-2': 'section-2',
        'to-section-3': 'section-3',
        'to-section-4': 'section-4',
        'to-section-5': 'section-5'
    };
    
    // إضافة معالجات الأحداث لجميع أزرار التنقل
    Object.keys(navigationButtons).forEach(buttonId => {
        const button = document.getElementById(buttonId);
        if (button) {
            button.addEventListener('click', function() {
                const targetSection = navigationButtons[buttonId];
                // تحقق مما إذا كان قسم المحتوى الداخلي غير ضروري
                if (targetSection === 'section-3' && (!hasInternalContent || !hasInternalContent.checked)) {
                    console.log('تخطي قسم المحتوى الداخلي لأنه غير مفعل');
                    showSection('section-4'); // انتقل إلى قسم التسعير مباشرة
                    return;
                }
                showSection(targetSection);
            });
        }
    });
    
    // إضافة معالجات الأحداث للأزرار المباشرة في النموذج
    document.querySelectorAll('.btn-prev-step, .btn-next-step').forEach(button => {
        if (button.id && navigationButtons[button.id]) {
            button.addEventListener('click', function() {
                showSection(navigationButtons[button.id]);
            });
        }
    });
    
    // إظهار/إخفاء حقول المقاس المخصص
    if (paperSizeSelect && customSizeFields) {
        paperSizeSelect.addEventListener('change', function() {
            // التحقق مما إذا كان المقاس المخصص هو المحدد
            // البحث عن "مقاس مخصص" بالضبط
            const isCustomSize = this.options[this.selectedIndex].text === 'مقاس مخصص';
            customSizeFields.style.display = isCustomSize ? 'flex' : 'none';
        });
        
        // التحقق عند تحميل الصفحة
        const isCustomSize = paperSizeSelect.options[paperSizeSelect.selectedIndex].text === 'مقاس مخصص';
        customSizeFields.style.display = isCustomSize ? 'flex' : 'none';
    }
    
    // إظهار/إخفاء حقول المقاس المفتوح
    if (useOpenSizeCheckbox && openSizeFields) {
        useOpenSizeCheckbox.addEventListener('change', function() {
            openSizeFields.style.display = this.checked ? 'flex' : 'none';
        });
    }
    
    // معالجة تغيير حالة "يحتوي على محتوى داخلي"
    if (hasInternalContent && internalFields && step3Element && section3Element && section2HeaderElement && step2Element) {
        console.log('تم العثور على جميع العناصر المطلوبة');
        
        // معالج حدث تغيير حالة "يحتوي على محتوى داخلي"
        hasInternalContent.addEventListener('change', function() {
            updateSectionsBasedOnInternalContent(this.checked);
        });
        
        // تحديث الواجهة عند التحميل
        updateSectionsBasedOnInternalContent(hasInternalContent.checked);
        
        // وظيفة تحديث الأقسام بناءً على حالة المحتوى الداخلي
        function updateSectionsBasedOnInternalContent(hasInternal) {
            console.log('تحديث الأقسام، الحالة:', hasInternal);
            
            // إظهار/إخفاء حقول المحتوى الداخلي في القسم الأول
            internalFields.style.display = hasInternal ? 'block' : 'none';
            
            // إظهار/إخفاء خطوة المحتوى الداخلي
            step3Element.style.display = hasInternal ? 'block' : 'none';
            section3Element.style.display = hasInternal ? 'block' : 'none';
            
            // تغيير عنوان القسم الثاني
            if (hasInternal) {
                // عند تفعيل المحتوى الداخلي
                section2HeaderElement.innerHTML = '🖨️ القسم الثاني: تفاصيل الغلاف';
                step2Element.textContent = 'تفاصيل الغلاف';
            } else {
                // عند إلغاء تفعيل المحتوى الداخلي
                section2HeaderElement.innerHTML = '🖨️ القسم الثاني: تفاصيل الطباعة';
                step2Element.textContent = 'تفاصيل الطباعة';
            }
        }
    } else {
        console.error('لم يتم العثور على بعض العناصر المطلوبة');
        console.log('hasInternalContent:', hasInternalContent);
        console.log('internalFields:', internalFields);
        console.log('step3Element:', step3Element);
        console.log('section3Element:', section3Element);
    }
    
    // إدارة حقول الغلاف
    if (printSidesSelect && singleSideColors && doubleSideColors) {
        // تحديث حقول الألوان عند تغيير عدد الأوجه
        printSidesSelect.addEventListener('change', function() {
            updateColorsFields(this.value, singleSideColors, doubleSideColors);
        });
        
        // تحديث حقول الألوان عند تحميل الصفحة
        updateColorsFields(printSidesSelect.value, singleSideColors, doubleSideColors);
        
        // تحديث معلومات المونتاج
        updateMontageInfo(montageInfoField);
        
        // تحديث معلومات المونتاج عند تغيير الكمية أو المقاس
        document.getElementById('id_quantity')?.addEventListener('change', function() {
            updateMontageInfo(montageInfoField);
        });
        document.getElementById('id_product_size')?.addEventListener('change', function() {
            updateMontageInfo(montageInfoField);
        });
    }
    
    // إدارة حقول المحتوى الداخلي
    if (internalPrintSidesSelect && internalSingleSideColors && internalDoubleSideColors) {
        // تحديث حقول الألوان عند تغيير عدد الأوجه
        internalPrintSidesSelect.addEventListener('change', function() {
            updateColorsFields(this.value, internalSingleSideColors, internalDoubleSideColors);
        });
        
        // تحديث حقول الألوان عند تحميل الصفحة
        updateColorsFields(internalPrintSidesSelect.value, internalSingleSideColors, internalDoubleSideColors);
        
        // تحديث معلومات المونتاج
        updateInternalMontageInfo(internalMontageInfoField);
        
        // تحديث معلومات المونتاج عند تغيير الكمية أو المقاس
        document.getElementById('id_quantity')?.addEventListener('change', function() {
            updateInternalMontageInfo(internalMontageInfoField);
        });
        document.getElementById('id_internal_page_count')?.addEventListener('change', function() {
            updateInternalMontageInfo(internalMontageInfoField);
        });
    }
    
    // إدارة حقول الأوفست للغلاف
    if (orderTypeSelect && offsetFields && ctpFields) {
        orderTypeSelect.addEventListener('change', function() {
            const isOffset = this.value === 'offset';
            offsetFields.style.display = isOffset ? 'block' : 'none';
            ctpFields.style.display = isOffset ? 'block' : 'none';
        });
        
        // تحديد نوع الطلب عند التحميل
        const isOffset = orderTypeSelect.value === 'offset';
        offsetFields.style.display = isOffset ? 'block' : 'none';
        ctpFields.style.display = isOffset ? 'block' : 'none';
    }
    
    // إدارة حقول الأوفست للمحتوى الداخلي
    if (internalOrderTypeSelect && internalOffsetFields && internalCtpFields) {
        internalOrderTypeSelect.addEventListener('change', function() {
            const isOffset = this.value === 'offset';
            internalOffsetFields.style.display = isOffset ? 'block' : 'none';
            internalCtpFields.style.display = isOffset ? 'block' : 'none';
        });
        
        // تحديد نوع الطلب عند التحميل
        const isOffset = internalOrderTypeSelect.value === 'offset';
        internalOffsetFields.style.display = isOffset ? 'block' : 'none';
        internalCtpFields.style.display = isOffset ? 'block' : 'none';
    }
    
    // إدارة حقول مقاس الزنك المخصص للغلاف
    if (ctpPlateSizeSelect && ctpCustomSizeFields) {
        ctpPlateSizeSelect.addEventListener('change', function() {
            ctpCustomSizeFields.style.display = this.value === 'custom' ? 'flex' : 'none';
        });
        
        // التحقق عند تحميل الصفحة
        ctpCustomSizeFields.style.display = ctpPlateSizeSelect.value === 'custom' ? 'flex' : 'none';
    }
    
    // إدارة حقول مقاس الزنك المخصص للمحتوى الداخلي
    if (internalCtpPlateSizeSelect && internalCtpCustomSizeFields) {
        internalCtpPlateSizeSelect.addEventListener('change', function() {
            internalCtpCustomSizeFields.style.display = this.value === 'custom' ? 'flex' : 'none';
        });
        
        // التحقق عند تحميل الصفحة
        internalCtpCustomSizeFields.style.display = internalCtpPlateSizeSelect.value === 'custom' ? 'flex' : 'none';
    }
    
    // جلب سعر الزنك تلقائيًا للغلاف
    function fetchPlatePrice(supplierId, plateSizeId, isInternal = false) {
        if (!supplierId || !plateSizeId) return;
        
        const url = `/pricing/get-plate-price/?supplier_id=${supplierId}&plate_size_id=${plateSizeId}`;
        
        fetch(url)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    if (isInternal) {
                        // تحديث حقول المحتوى الداخلي
                        document.getElementById('id_internal_ctp_plate_price').value = data.plate_price.toFixed(2);
                        document.getElementById('id_internal_ctp_transportation').value = data.transportation_cost.toFixed(2);
                        
                        // تحديث الحد الأدنى لعدد الزنكات
                        const platesCountField = document.getElementById('id_internal_ctp_plates_count');
                        if (platesCountField.value < data.min_plates_count) {
                            platesCountField.value = data.min_plates_count;
                        }
                        
                        // حساب التكلفة الإجمالية
                        calculateInternalCtpTotalCost();
                    } else {
                        // تحديث حقول الغلاف
                        document.getElementById('id_ctp_plate_price').value = data.plate_price.toFixed(2);
                        document.getElementById('id_ctp_transportation').value = data.transportation_cost.toFixed(2);
                        
                        // تحديث الحد الأدنى لعدد الزنكات
                        const platesCountField = document.getElementById('id_ctp_plates_count');
                        if (platesCountField.value < data.min_plates_count) {
                            platesCountField.value = data.min_plates_count;
                        }
                        
                        // حساب التكلفة الإجمالية
                        calculateCtpTotalCost();
                    }
                } else {
                    console.error('Error fetching plate price:', data.error);
                }
            })
            .catch(error => {
                console.error('Error:', error);
            });
    }
    
    // إضافة معالجات الأحداث لجلب سعر الزنك تلقائيًا للغلاف
    const ctpSupplierSelect = document.getElementById('id_ctp_supplier');
    if (ctpSupplierSelect && ctpPlateSizeSelect) {
        ctpSupplierSelect.addEventListener('change', function() {
            if (ctpPlateSizeSelect.value) {
                fetchPlatePrice(this.value, ctpPlateSizeSelect.value);
            }
        });
        
        ctpPlateSizeSelect.addEventListener('change', function() {
            if (ctpSupplierSelect.value) {
                fetchPlatePrice(ctpSupplierSelect.value, this.value);
            }
        });
    }
    
    // إضافة معالجات الأحداث لجلب سعر الزنك تلقائيًا للمحتوى الداخلي
    const internalCtpSupplierSelect = document.getElementById('id_internal_ctp_supplier');
    if (internalCtpSupplierSelect && internalCtpPlateSizeSelect) {
        internalCtpSupplierSelect.addEventListener('change', function() {
            if (internalCtpPlateSizeSelect.value) {
                fetchPlatePrice(this.value, internalCtpPlateSizeSelect.value, true);
            }
        });
        
        internalCtpPlateSizeSelect.addEventListener('change', function() {
            if (internalCtpSupplierSelect.value) {
                fetchPlatePrice(internalCtpSupplierSelect.value, this.value, true);
            }
        });
    }
    
    // حساب إجمالي تكلفة الزنكات للغلاف
    function calculateCtpTotalCost() {
        if (ctpPlatesCount && ctpPlatePrice && ctpTransportation && ctpTotalCost) {
            const platesCount = parseFloat(ctpPlatesCount.value) || 0;
            const platePrice = parseFloat(ctpPlatePrice.value) || 0;
            const transportation = parseFloat(ctpTransportation.value) || 0;
            
            const totalCost = (platesCount * platePrice) + transportation;
            ctpTotalCost.value = totalCost.toFixed(2);
        }
    }
    
    // حساب إجمالي تكلفة الزنكات للمحتوى الداخلي
    function calculateInternalCtpTotalCost() {
        if (internalCtpPlatesCount && internalCtpPlatePrice && internalCtpTransportation && internalCtpTotalCost) {
            const platesCount = parseFloat(internalCtpPlatesCount.value) || 0;
            const platePrice = parseFloat(internalCtpPlatePrice.value) || 0;
            const transportation = parseFloat(internalCtpTransportation.value) || 0;
            
            const totalCost = (platesCount * platePrice) + transportation;
            internalCtpTotalCost.value = totalCost.toFixed(2);
        }
    }
    
    // إضافة معالجات الأحداث لحساب تكلفة الزنكات للغلاف
    if (ctpPlatesCount && ctpPlatePrice && ctpTransportation) {
        ctpPlatesCount.addEventListener('input', calculateCtpTotalCost);
        ctpPlatePrice.addEventListener('input', calculateCtpTotalCost);
        ctpTransportation.addEventListener('input', calculateCtpTotalCost);
        
        // حساب التكلفة عند تحميل الصفحة
        calculateCtpTotalCost();
    }
    
    // إضافة معالجات الأحداث لحساب تكلفة الزنكات للمحتوى الداخلي
    if (internalCtpPlatesCount && internalCtpPlatePrice && internalCtpTransportation) {
        internalCtpPlatesCount.addEventListener('input', calculateInternalCtpTotalCost);
        internalCtpPlatePrice.addEventListener('input', calculateInternalCtpTotalCost);
        internalCtpTransportation.addEventListener('input', calculateInternalCtpTotalCost);
        
        // حساب التكلفة عند تحميل الصفحة
        calculateInternalCtpTotalCost();
    }
    
    // تحديث عدد الزنكات تلقائيًا بناءً على عدد الألوان
    function updateCtpPlatesCount() {
        if (ctpPlatesCount && singleSideColors && doubleSideColors) {
            let totalColors = 0;
            
            if (printSidesSelect.value === '1' || printSidesSelect.value === '3') {
                // وجه واحد أو طبع وقلب
                const colorsDesign = parseInt(document.getElementById('id_colors_design').value) || 0;
                totalColors = colorsDesign;
            } else if (printSidesSelect.value === '2') {
                // وجهين
                const colorsFront = parseInt(document.getElementById('id_colors_front').value) || 0;
                const colorsBack = parseInt(document.getElementById('id_colors_back').value) || 0;
                totalColors = colorsFront + colorsBack;
            }
            
            ctpPlatesCount.value = totalColors;
            calculateCtpTotalCost();
        }
    }
    
    // تحديث عدد زنكات المحتوى الداخلي تلقائيًا بناءً على عدد الألوان
    function updateInternalCtpPlatesCount() {
        if (internalCtpPlatesCount && internalSingleSideColors && internalDoubleSideColors) {
            let totalColors = 0;
            
            if (internalPrintSidesSelect.value === '1' || internalPrintSidesSelect.value === '3') {
                // وجه واحد أو طبع وقلب
                const colorsDesign = parseInt(document.getElementById('id_internal_colors_design').value) || 0;
                totalColors = colorsDesign;
            } else if (internalPrintSidesSelect.value === '2') {
                // وجهين
                const colorsFront = parseInt(document.getElementById('id_internal_colors_front').value) || 0;
                const colorsBack = parseInt(document.getElementById('id_internal_colors_back').value) || 0;
                totalColors = colorsFront + colorsBack;
            }
            
            internalCtpPlatesCount.value = totalColors;
            calculateInternalCtpTotalCost();
        }
    }
    
    // إضافة معالجات الأحداث لتحديث عدد الزنكات تلقائيًا
    document.getElementById('id_colors_design')?.addEventListener('input', updateCtpPlatesCount);
    document.getElementById('id_colors_front')?.addEventListener('input', updateCtpPlatesCount);
    document.getElementById('id_colors_back')?.addEventListener('input', updateCtpPlatesCount);
    
    document.getElementById('id_internal_colors_design')?.addEventListener('input', updateInternalCtpPlatesCount);
    document.getElementById('id_internal_colors_front')?.addEventListener('input', updateInternalCtpPlatesCount);
    document.getElementById('id_internal_colors_back')?.addEventListener('input', updateInternalCtpPlatesCount);
    
    // وظيفة تحديث حقول الألوان
    function updateColorsFields(sides, singleSideColors, doubleSideColors) {
        console.log('تحديث حقول الألوان، عدد الأوجه:', sides);
        if (sides === '1' || sides === '3') {
            // وجه واحد أو طبع وقلب: عرض حقل واحد للألوان
            singleSideColors.style.display = 'flex';
            doubleSideColors.style.display = 'none';
        } else if (sides === '2') {
            // وجهين: عرض حقلين للألوان (وجه وظهر)
            singleSideColors.style.display = 'none';
            doubleSideColors.style.display = 'flex';
        }
    }
    
    // وظيفة تحديث معلومات المونتاج للغلاف
    function updateMontageInfo(montageInfoField) {
        if (montageInfoField) {
            const quantity = document.getElementById('id_quantity')?.value || 0;
            const paperSize = document.getElementById('id_product_size');
            const paperSizeText = paperSize ? paperSize.options[paperSize.selectedIndex].text : '';
            
            montageInfoField.value = `${quantity} / ${paperSizeText}`;
        }
    }
    
    // وظيفة تحديث معلومات المونتاج للمحتوى الداخلي
    function updateInternalMontageInfo(montageInfoField) {
        if (montageInfoField) {
            const quantity = document.getElementById('id_quantity')?.value || 0;
            const pageCount = document.getElementById('id_internal_page_count')?.value || 0;
            
            montageInfoField.value = `${quantity} × ${pageCount} صفحة`;
        }
    }
    
    // حساب التكلفة والسعر
    const calculateCostBtn = document.getElementById('calculate-cost');
    if (calculateCostBtn) {
        calculateCostBtn.addEventListener('click', function() {
            // جمع البيانات من النموذج
            const materialCost = parseFloat(document.getElementById('id_material_cost').value) || 0;
            const printingCost = parseFloat(document.getElementById('id_printing_cost').value) || 0;
            const finishingCost = parseFloat(document.getElementById('id_finishing_cost').value) || 0;
            const extraCost = parseFloat(document.getElementById('id_extra_cost').value) || 0;
            const profitMargin = parseFloat(document.getElementById('id_profit_margin').value) || 0;
            const quantity = parseInt(document.getElementById('id_quantity').value) || 1;
            
            // حساب إجمالي التكلفة
            const totalCost = materialCost + printingCost + finishingCost + extraCost;
            
            // حساب سعر البيع
            const salePrice = totalCost * (1 + (profitMargin / 100));
            
            // حساب سعر الوحدة
            const unitPrice = salePrice / quantity;
            
            // حساب مبلغ الربح
            const profitAmount = salePrice - totalCost;
            
            // تحديث الحقول
            document.getElementById('total_cost').value = totalCost.toFixed(2);
            document.getElementById('id_sale_price').value = salePrice.toFixed(2);
            document.getElementById('unit_price').value = unitPrice.toFixed(2);
            document.getElementById('profit_amount').value = profitAmount.toFixed(2);
        });
        
        // استدعاء واجهة برمجة التطبيقات لحساب التكلفة
        function calculateCostAPI() {
            // البيانات التي سيتم إرسالها
            const formData = {
                order_type: document.getElementById('id_order_type').value,
                quantity: document.getElementById('id_quantity').value,
                paper_type: document.getElementById('id_paper_type').value,
                paper_size: document.getElementById('id_product_size').value,
                print_sides: document.getElementById('id_print_sides').value,
                colors_front: document.getElementById('id_colors_front').value,
                colors_back: document.getElementById('id_colors_back').value,
                coating_type: document.getElementById('id_coating_type').value,
                supplier: document.getElementById('id_supplier').value
            };
            
            // إرسال طلب Ajax
            fetch('/pricing/calculate_cost/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: JSON.stringify(formData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('id_material_cost').value = data.material_cost;
                    document.getElementById('id_printing_cost').value = data.printing_cost;
                    
                    // تشغيل حساب التكلفة والسعر تلقائيًا
                    calculateCostBtn.click();
                } else {
                    alert('حدث خطأ أثناء حساب التكلفة');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('حدث خطأ أثناء الاتصال بالخادم');
            });
        }
        
        // ربط وظيفة حساب التكلفة بالزر
        calculateCostBtn.addEventListener('click', calculateCostAPI);
    }
}); 