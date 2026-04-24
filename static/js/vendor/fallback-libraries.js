/**
 * مكتبة بديلة للمكتبات المحجوبة
 * تقدم وظائف أساسية عند عدم توفر المكتبات الأصلية
 */

// إنشاء كائن QRCode بديل إذا لم يكن متوفراً
if (typeof QRCode === 'undefined') {
    window.QRCode = {
        toCanvas: function(canvas, text, options, callback) {
            console.warn('QRCode CDN غير متوفر - استخدام Backend API بدلاً من ذلك');
            
            // استخراج token من النص
            const urlParts = text.split('/');
            const token = urlParts[urlParts.length - 2]; // قبل الآخير
            
            if (window.QRGenerator && token) {
                // استخدام QRGenerator المحلي
                window.QRGenerator.generateQR(token, canvas, {
                    size: options?.width || 200,
                    downloadButtons: false
                }).then(success => {
                    if (callback) callback(success ? null : new Error('فشل في إنشاء QR Code'));
                });
            } else {
                // عرض رسالة خطأ
                if (canvas) {
                    canvas.innerHTML = '<div class="alert alert-warning">QR Code غير متوفر حالياً</div>';
                }
                if (callback) callback(new Error('QRCode library not available'));
            }
        },
        
        toDataURL: function(text, options, callback) {
            console.warn('QRCode CDN غير متوفر - استخدام Backend API بدلاً من ذلك');
            
            const urlParts = text.split('/');
            const token = urlParts[urlParts.length - 2];
            
            if (window.QRGenerator && token) {
                window.QRGenerator.fetchQRData(token, { size: options?.width || 200 })
                    .then(data => {
                        if (callback) callback(null, data.data_url);
                    })
                    .catch(error => {
                        if (callback) callback(error);
                    });
            } else {
                if (callback) callback(new Error('QRCode library not available'));
            }
        }
    };
}

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

