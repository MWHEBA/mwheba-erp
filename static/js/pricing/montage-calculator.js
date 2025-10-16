/**
 * نظام حساب المونتاج الاحترافي
 * يحسب عدد التصاميم التي يمكن طباعتها على ورقة واحدة
 */

class MontageCalculator {
    constructor() {
        // مقاسات الورق المعيارية (بالسنتيمتر)
        this.paperSizes = {
            'full_70x100': { width: 70, height: 100, name: 'فرخ كامل', quarter: { width: 35, height: 50 } },
            'jayer_66x88': { width: 66, height: 88, name: 'فرخ جاير', quarter: { width: 33, height: 44 } },
            'half_50x70': { width: 50, height: 70, name: 'نصف فرخ' },
            'quarter_35x50': { width: 35, height: 50, name: 'ربع فرخ' },
            'quarter_jayer_33x44': { width: 33, height: 44, name: 'ربع جاير' }
        };

        // مقاسات المكائن المدعومة
        this.pressSizes = {
            'quarter': { width: 35, height: 50, name: 'ربع فرخ', maxWidth: 35, maxHeight: 50 },
            'half': { width: 50, height: 70, name: 'نصف فرخ', maxWidth: 50, maxHeight: 70 },
            'full': { width: 70, height: 100, name: 'فرخ كامل', maxWidth: 70, maxHeight: 100 }
        };
    }

    /**
     * حساب المونتاج الرئيسي
     * @param {Object} designSize - مقاس التصميم {width, height}
     * @param {string} paperType - نوع الورق
     * @param {string} pressType - نوع الماكينة
     * @returns {Object} نتيجة المونتاج
     */
    calculateMontage(designSize, paperType, pressType) {
        try {
            // التحقق من صحة المدخلات
            const validation = this.validateInputs(designSize, paperType, pressType);
            if (!validation.valid) {
                return {
                    success: false,
                    error: validation.error,
                    count: 0,
                    description: 'خطأ في المدخلات'
                };
            }

            // تحديد مقاس الطباعة الفعلي
            const effectivePrintSize = this.getEffectivePrintSize(paperType, pressType);
            
            // حساب عدد التصاميم
            const designCount = this.calculateDesignCount(designSize, effectivePrintSize);
            
            // تحديد وصف المونتاج
            const description = this.getMontageDescription(designCount, effectivePrintSize, paperType);

            return {
                success: true,
                count: designCount.count,
                description: description,
                details: {
                    paperSize: this.paperSizes[paperType],
                    pressSize: this.pressSizes[pressType],
                    effectivePrintSize: effectivePrintSize,
                    calculation: designCount,
                    isRotated: designCount.isRotated
                }
            };

        } catch (error) {
            console.error('خطأ في حساب المونتاج:', error);
            return {
                success: false,
                error: 'خطأ غير متوقع في الحساب',
                count: 0,
                description: 'خطأ في النظام'
            };
        }
    }
    /**
     * تحديد مقاس الطباعة الفعلي بناءً على الورق والماكينة
     */
    async getEffectivePrintSize(paperType, pressId) {
        const paper = this.paperSizes[paperType];
        const press = await fetch(`/pricing/api/press-size/?press_id=${pressId}`)
            .then(response => response.json());

        // إذا كان الورق يناسب الماكينة مباشرة
        if (paper.width <= press.maxWidth && paper.height <= press.maxHeight) {
            return {
                width: paper.width,
                height: paper.height,
                name: paper.name,
                type: 'direct'
            };
        }

        // إذا كان الورق أكبر من الماكينة، نحتاج لقطعه
        return this.calculateCutSize(paper, press, paperType);
    }

    /**
     * حساب مقاس القطع المناسب
     */
    calculateCutSize(paper, press, paperType) {
        // للفرخ الكامل مع ماكينة ربع
        if (paperType === 'full_70x100' && press.maxWidth === 35) {
            return {
                width: 35,
                height: 50,
                name: 'الربع',
                type: 'quarter_cut'
            };
        }

        // للفرخ الجاير مع ماكينة ربع
        if (paperType === 'jayer_66x88' && press.maxWidth === 35) {
            return {
                width: 33,
                height: 44,
                name: 'ربع الجاير',
                type: 'quarter_jayer_cut'
            };
        }

        // للفرخ الكامل مع ماكينة نصف
        if (paperType === 'full_70x100' && press.maxWidth === 50) {
            return {
                width: 50,
                height: 70,
                name: 'النصف',
                type: 'half_cut'
            };
        }

        // للفرخ الجاير مع ماكينة نصف
        if (paperType === 'jayer_66x88' && press.maxWidth === 50) {
            return {
                width: 44,
                height: 66,
                name: 'نصف الجاير',
                type: 'half_jayer_cut'
            };
        }

        // إذا لم نجد قطع مناسب، نستخدم أقصى مقاس للماكينة
        return {
            width: Math.min(paper.width, press.maxWidth),
            height: Math.min(paper.height, press.maxHeight),
            name: 'المقاس',
            type: 'custom_cut'
        };
    }

    /**
     * حساب عدد التصاميم على مقاس الطباعة
     */
    calculateDesignCount(designSize, printSize) {
        // حساب العدد بالوضع العادي
        const normalWidthCount = Math.floor(printSize.width / designSize.width);
        const normalHeightCount = Math.floor(printSize.height / designSize.height);
        const normalCount = normalWidthCount * normalHeightCount;

        // حساب العدد بعد تدوير التصميم
        const rotatedWidthCount = Math.floor(printSize.width / designSize.height);
        const rotatedHeightCount = Math.floor(printSize.height / designSize.width);
        const rotatedCount = rotatedWidthCount * rotatedHeightCount;

        // اختيار الأفضل
        if (rotatedCount > normalCount) {
            return {
                count: rotatedCount,
                isRotated: true,
                widthCount: rotatedWidthCount,
                heightCount: rotatedHeightCount,
                calculation: `${rotatedWidthCount} × ${rotatedHeightCount} = ${rotatedCount} (مع تدوير التصميم)`
            };
        } else {
            return {
                count: normalCount,
                isRotated: false,
                widthCount: normalWidthCount,
                heightCount: normalHeightCount,
                calculation: `${normalWidthCount} × ${normalHeightCount} = ${normalCount}`
            };
        }
    }

    /**
     * تحديد وصف المونتاج النهائي
     */
    getMontageDescription(designCount, printSize, paperType) {
        const count = designCount.count;
        
        // إذا كان العدد صفر
        if (count === 0) {
            return 'التصميم كبير جداً - غير قابل للطباعة';
        }

        // تحديد الوصف بناءً على نوع القطع
        let sizeDescription;
        switch (printSize.type) {
            case 'quarter_cut':
                sizeDescription = 'الربع';
                break;
            case 'quarter_jayer_cut':
                sizeDescription = 'ربع الجاير';
                break;
            case 'half_cut':
                sizeDescription = 'النصف';
                break;
            case 'half_jayer_cut':
                sizeDescription = 'نصف الجاير';
                break;
            case 'direct':
                if (printSize.width === 70 && printSize.height === 100) {
                    sizeDescription = 'الفرخ';
                } else if (printSize.width === 50 && printSize.height === 70) {
                    sizeDescription = 'النصف';
                } else if (printSize.width === 35 && printSize.height === 50) {
                    sizeDescription = 'الربع';
                } else if (printSize.width === 33 && printSize.height === 44) {
                    sizeDescription = 'ربع الجاير';
                } else {
                    sizeDescription = 'المقاس';
                }
                break;
            default:
                sizeDescription = 'المقاس';
        }

        return `${count} / ${sizeDescription}`;
    }

    /**
     * التحقق من صحة المدخلات
     */
    validateInputs(designSize, paperType, pressType) {
        // التحقق من مقاس التصميم
        if (!designSize || !designSize.width || !designSize.height) {
            return { valid: false, error: 'مقاس التصميم مطلوب' };
        }

        if (designSize.width <= 0 || designSize.height <= 0) {
            return { valid: false, error: 'مقاس التصميم يجب أن يكون أكبر من صفر' };
        }

        // التحقق من نوع الورق
        if (!paperType || !this.paperSizes[paperType]) {
            return { valid: false, error: 'نوع الورق غير صحيح' };
        }

        // التحقق من نوع الماكينة
        if (!pressType || !this.pressSizes[pressType]) {
            return { valid: false, error: 'نوع الماكينة غير صحيح' };
        }

        return { valid: true };
    }

    /**
     * إضافة مقاس ورق مخصص
     */
    addCustomPaperSize(key, width, height, name) {
        this.paperSizes[key] = {
            width: width,
            height: height,
            name: name,
            type: 'custom'
        };
    }

    /**
     * الحصول على قائمة مقاسات الورق المتاحة
     */
    getAvailablePaperSizes() {
        return Object.keys(this.paperSizes).map(key => ({
            key: key,
            name: this.paperSizes[key].name,
            width: this.paperSizes[key].width,
            height: this.paperSizes[key].height
        }));
    }

    /**
     * الحصول على قائمة مقاسات المكائن المتاحة
     */
    getAvailablePressSizes() {
        return Object.keys(this.pressSizes).map(key => ({
            key: key,
            name: this.pressSizes[key].name,
            maxWidth: this.pressSizes[key].maxWidth,
            maxHeight: this.pressSizes[key].maxHeight
        }));
    }
}

// أمثلة للاختبار
function testMontageCalculator() {
    const calculator = new MontageCalculator();
    
    console.log('=== اختبار حساب المونتاج ===\n');
    
    // مثال 1: A4 على فرخ كامل بماكينة ربع
    const test1 = calculator.calculateMontage(
        { width: 21, height: 29.7 },  // A4
        'full_70x100',                // فرخ كامل
        'quarter'                     // ماكينة ربع
    );
    console.log('مثال 1 - A4 على فرخ كامل بماكينة ربع:');
    console.log(`النتيجة: ${test1.description}`);
    console.log(`التفاصيل: ${test1.details?.calculation}\n`);
    
    // مثال 2: A4 على فرخ جاير بماكينة ربع
    const test2 = calculator.calculateMontage(
        { width: 21, height: 29.7 },  // A4
        'jayer_66x88',                // فرخ جاير
        'quarter'                     // ماكينة ربع
    );
    console.log('مثال 2 - A4 على فرخ جاير بماكينة ربع:');
    console.log(`النتيجة: ${test2.description}`);
    console.log(`التفاصيل: ${test2.details?.calculation}\n`);
    
    // مثال 3: A4 على مقاس 30×40 بماكينة ربع
    calculator.addCustomPaperSize('custom_30x40', 30, 40, 'مقاس 30×40');
    const test3 = calculator.calculateMontage(
        { width: 21, height: 29.7 },  // A4
        'custom_30x40',               // مقاس مخصص
        'quarter'                     // ماكينة ربع
    );
    console.log('مثال 3 - A4 على مقاس 30×40 بماكينة ربع:');
    console.log(`النتيجة: ${test3.description}`);
    console.log(`التفاصيل: ${test3.details?.calculation}\n`);
    
    // مثال 4: بطاقة أعمال على فرخ كامل بماكينة ربع
    const test4 = calculator.calculateMontage(
        { width: 9, height: 5 },      // بطاقة أعمال
        'full_70x100',                // فرخ كامل
        'quarter'                     // ماكينة ربع
    );
    console.log('مثال 4 - بطاقة أعمال على فرخ كامل بماكينة ربع:');
    console.log(`النتيجة: ${test4.description}`);
    console.log(`التفاصيل: ${test4.details?.calculation}\n`);
}

// تشغيل الاختبارات
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MontageCalculator;
} else {
    // للاختبار في المتصفح
    window.MontageCalculator = MontageCalculator;
    window.testMontageCalculator = testMontageCalculator;
}
