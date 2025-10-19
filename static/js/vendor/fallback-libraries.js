/**
 * مكتبة بديلة للمكتبات المحجوبة
 * تقدم وظائف أساسية عند عدم توفر المكتبات الأصلية
 */

// إنشاء كائن XLSX بديل إذا لم يكن متوفراً
if (typeof XLSX === 'undefined') {
    window.XLSX = {
        utils: {
            table_to_book: function(table, options) {
                console.warn('XLSX غير متوفر - استخدام تصدير CSV بدلاً من ذلك');
                return null;
            },
            book_new: function() {
                console.warn('XLSX غير متوفر');
                return null;
            },
            aoa_to_sheet: function(data) {
                console.warn('XLSX غير متوفر');
                return null;
            },
            book_append_sheet: function(wb, ws, name) {
                console.warn('XLSX غير متوفر');
            }
        },
        writeFile: function(wb, filename) {
            console.warn('XLSX غير متوفر - لا يمكن تصدير Excel');
            alert('تصدير Excel غير متوفر حالياً. يرجى استخدام تصدير CSV.');
        }
    };
}

// إنشاء كائن pdfMake بديل إذا لم يكن متوفراً
if (typeof pdfMake === 'undefined') {
    window.pdfMake = {
        createPdf: function(docDefinition) {
            console.warn('pdfMake غير متوفر');
            alert('تصدير PDF غير متوفر حالياً.');
            return {
                download: function() {},
                open: function() {},
                print: function() {}
            };
        }
    };
}

// إنشاء كائن JSZip بديل إذا لم يكن متوفراً
if (typeof JSZip === 'undefined') {
    window.JSZip = function() {
        console.warn('JSZip غير متوفر');
        return {
            file: function() { return this; },
            generateAsync: function() {
                return Promise.reject('JSZip غير متوفر');
            }
        };
    };
}

