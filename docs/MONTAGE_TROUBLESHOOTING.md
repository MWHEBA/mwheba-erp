# 🔧 دليل استكشاف أخطاء المونتاج وإصلاحها

## 🚨 المشكلة: `id_montage_info` لا يتأثر بتغيير مقاس الورق أو ماكينة الطباعة

### 🔍 الأسباب المحتملة:

#### **1. مشاكل في تحميل JavaScript:**
```javascript
// تحقق من تحميل الملفات في console المتصفح (F12)
- هل تم تحميل montage-calculator.js؟
- هل تم تحميل montage-handlers.js؟
- هل يوجد أخطاء JavaScript؟
```

#### **2. مشاكل في تسجيل معالجات الأحداث:**
```javascript
// تحقق من هذه الرسائل في console:
"تم تحميل النظام الاحترافي الجديد للمونتاج"
"تم إعداد معالجات المونتاج الشاملة بنجاح"
"إعداد معالجات الأحداث التقليدية..."
```

#### **3. عدم وجود الحقول المطلوبة:**
```html
<!-- تأكد من وجود هذه الحقول في HTML -->
<select id="id_paper_size">...</select>
<select id="id_press">...</select>
<input id="id_montage_info" />
<input id="id_custom_size_width" />
<input id="id_custom_size_height" />
```

#### **4. مشاكل في EventBus:**
```javascript
// إذا كان النظام يستخدم EventBus ولكنه غير متاح
if (PricingSystem.EventBus) {
    // سيستخدم EventBus
} else {
    // سيستخدم الطريقة التقليدية
}
```

### 🛠️ الحلول المطبقة:

#### **✅ إصلاح 1: تعريف المتغيرات المفقودة**
```javascript
// تم إصلاح هذا في setupTraditionalEventHandlers
const paperSizeSelect = document.getElementById('id_paper_size');
const customSizeWidthInput = document.getElementById('id_custom_size_width');
const customSizeHeightInput = document.getElementById('id_custom_size_height');
```

#### **✅ إصلاح 2: إضافة معالجات شاملة**
```javascript
// تم إضافة معالجات لجميع الحقول المؤثرة
paperSizeSelect.addEventListener('change', updateMontageOnChange);
pressSelect.addEventListener('change', updateMontageOnChange);
customSizeWidthInput.addEventListener('input', updateMontageOnChange);
designWidthInput.addEventListener('input', updateMontageOnChange);
```

#### **✅ إصلاح 3: إضافة تسجيل للتشخيص**
```javascript
// تم إضافة console.log لتتبع التنفيذ
console.log('تم تشغيل updateMontageOnChange');
console.log('تم استدعاء updateMontageInfo، isInternal:', isInternal);
```

### 🧪 خطوات التشخيص:

#### **الخطوة 1: فتح ملف الاختبار**
```
افتح: test_montage_debug.html في المتصفح
```

#### **الخطوة 2: فحص Console (F12)**
```javascript
// يجب أن ترى هذه الرسائل:
"بدء تشغيل النظام..."
"تم تحميل النظام الاحترافي الجديد للمونتاج"
"تم إعداد معالجات المونتاج الشاملة بنجاح"
"إعداد معالجات الأحداث التقليدية..."
```

#### **الخطوة 3: اختبار التفاعل**
```javascript
// عند تغيير مقاس الورق أو الماكينة يجب أن ترى:
"تم تشغيل updateMontageOnChange"
"تم استدعاء updateMontageInfo، isInternal: false"
```

#### **الخطوة 4: فحص الحقول**
```javascript
// تحقق من وجود الحقول
console.log(document.getElementById('id_paper_size')); // يجب ألا يكون null
console.log(document.getElementById('id_press')); // يجب ألا يكون null
console.log(document.getElementById('id_montage_info')); // يجب ألا يكون null
```

### 🔧 حلول إضافية:

#### **إذا لم تعمل الطريقة التقليدية:**
```javascript
// أضف هذا الكود في console المتصفح للاختبار اليدوي
if (PricingSystem && PricingSystem.Montage) {
    const montageField = document.getElementById('id_montage_info');
    if (montageField) {
        PricingSystem.Montage.updateMontageInfo(montageField);
    }
}
```

#### **إذا كان EventBus متاحاً ولكن لا يعمل:**
```javascript
// تحقق من تسجيل الأحداث
PricingSystem.EventBus.emit('field:id_paper_size:changed', {});
PricingSystem.EventBus.emit('field:id_press:changed', {});
```

#### **إذا كانت الحقول موجودة ولكن المعالجات لا تعمل:**
```javascript
// أضف معالجات يدوياً
document.getElementById('id_paper_size').addEventListener('change', function() {
    console.log('تغيير مقاس الورق');
    const montageField = document.getElementById('id_montage_info');
    if (montageField && PricingSystem.Montage) {
        PricingSystem.Montage.updateMontageInfo(montageField);
    }
});
```

### 📋 قائمة التحقق السريعة:

- [ ] **الملفات محملة**: montage-calculator.js و montage-handlers.js
- [ ] **لا توجد أخطاء JavaScript** في console
- [ ] **الحقول موجودة**: id_paper_size, id_press, id_montage_info
- [ ] **النظام مُهيأ**: رسالة "تم إعداد معالجات المونتاج الشاملة بنجاح"
- [ ] **المعالجات مسجلة**: رسالة "إعداد معالجات الأحداث التقليدية..."
- [ ] **التفاعل يعمل**: رسالة "تم تشغيل updateMontageOnChange" عند التغيير

### 🚀 الاختبار النهائي:

1. **افتح صفحة إنشاء طلب تسعير**
2. **افتح Console (F12)**
3. **غير مقاس الورق** - يجب أن ترى رسائل التشخيص
4. **غير ماكينة الطباعة** - يجب أن يتحدث حقل المونتاج
5. **أدخل مقاس مخصص** - يجب أن يتحدث المونتاج فوراً

### 📞 إذا استمرت المشكلة:

```javascript
// شغل هذا الكود في console للتشخيص المتقدم
console.log('=== تشخيص شامل ===');
console.log('PricingSystem:', typeof PricingSystem);
console.log('PricingSystem.Montage:', typeof PricingSystem?.Montage);
console.log('MontageCalculator:', typeof MontageCalculator);
console.log('id_paper_size:', document.getElementById('id_paper_size'));
console.log('id_press:', document.getElementById('id_press'));
console.log('id_montage_info:', document.getElementById('id_montage_info'));

// اختبار يدوي
if (PricingSystem?.Montage) {
    PricingSystem.Montage.setupMontageHandlers();
}
```
