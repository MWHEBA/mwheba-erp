# 🚀 تشغيل Bridge Agent v2.0 - دليل سريع

## ✨ الجديد في v2.0

- ✅ **إرسال السجلات الجديدة فقط** - توفير bandwidth
- ✅ **نظام Heartbeat** - البادج دائماً يعكس الحالة الصحيحة
- ✅ **حفظ آخر timestamp** في `last_sync.json`
- ✅ **تحديث تلقائي** لـ last_connection كل 5 دقائق

---

## 📋 خطوات التشغيل

### 1. تأكد من الإعدادات

**✓ ملف `.env` على السيرفر:**
```bash
BRIDGE_AGENTS=ZKTeco:zkteco-secret-key-2025
```

**✓ ملف `config.json` على الجهاز المحلي:**
```json
{
    "device_ip": "192.168.1.201",
    "device_port": 4370,
    "server_url": "http://127.0.0.1:8000",
    "agent_code": "ZKTeco",
    "agent_secret": "zkteco-secret-key-2025",
    "sync_interval": 5,
    "auto_discover_ip": true
}
```

**⚠️ مهم جداً:**
- `agent_code` في config.json = المفتاح في BRIDGE_AGENTS (ZKTeco)
- `agent_secret` في config.json = القيمة في BRIDGE_AGENTS (zkteco-secret-key-2025)
- يجب أن يتطابقا **تماماً** بدون مسافات زائدة

---

### 2. شغّل Django Server

```bash
# في مجلد المشروع
python manage.py runserver
```

يجب أن ترى:
```
Starting development server at http://127.0.0.1:8000/
```

---

### 3. شغّل Bridge Agent

```bash
# في مجلد bridge_agent
cd bridge_agent
python agent.py
```

---

## 📊 علامات النجاح

### يجب أن ترى في Bridge Agent:

#### لو فيه سجلات جديدة:
```
2025-11-05 01:26:00 - INFO - Bridge Agent initialized - Code: ZKTeco
2025-11-05 01:26:00 - INFO - Resuming from last sync: 2025-11-05 01:20:00
2025-11-05 01:26:00 - INFO - Starting sync cycle...
2025-11-05 01:26:01 - INFO - Fetched 3 records from device
2025-11-05 01:26:01 - INFO - Sending 3 records to server...
2025-11-05 01:26:02 - INFO - ✓ Server response: Processed 3 records
2025-11-05 01:26:02 - INFO -   Processed: 3
2025-11-05 01:26:02 - INFO -   Skipped: 0
2025-11-05 01:26:02 - INFO - ✓ Sync completed successfully
```

#### لو مافيش سجلات جديدة (Heartbeat):
```
2025-11-05 01:31:00 - INFO - Starting sync cycle...
2025-11-05 01:31:01 - INFO - Fetched 0 records from device
2025-11-05 01:31:01 - INFO - Sending 0 records to server...
2025-11-05 01:31:02 - INFO - ✓ Server response: Heartbeat received - No new records
2025-11-05 01:31:02 - INFO - ✓ Heartbeat sent - No new records
```

### في Django Console:

```
[05/Jan/2025 01:20:02] "POST /hr/api/biometric/bridge-sync/ HTTP/1.1" 200
```

### في Django Admin:

1. اذهب لـ: `http://127.0.0.1:8000/hr/biometric-devices/1/`
2. تحقق من:
   - **الحالة:** نشط (Active)
   - **آخر اتصال:** يجب أن يكون حديث (منذ ثوانٍ)
   - **إجمالي السجلات:** يجب أن يزيد

3. اذهب لـ: `http://127.0.0.1:8000/hr/biometric-logs/`
4. يجب أن ترى سجلات جديدة بـ timestamp حديث

---

## 🐛 استكشاف الأخطاء

### خطأ: "Invalid agent credentials"

**السبب:** عدم تطابق المفاتيح

**الحل:**
```bash
1. افتح .env وانسخ القيمة بعد ZKTeco:
2. افتح config.json والصق نفس القيمة في agent_secret
3. تأكد من عدم وجود مسافات زائدة
4. احفظ الملفات
5. أعد تشغيل Django و Bridge Agent
```

---

### خطأ: "404 Not Found"

**السبب:** URL خاطئ (تم إصلاحه!)

**التحقق:**
```python
# في agent.py - السطر 174
api_url = f"{self.server_url}/hr/api/biometric/bridge-sync/"
# يجب أن يحتوي على /hr/
```

---

### خطأ: "Connection refused to device"

**السبب:** IP الماكينة خاطئ أو الماكينة مغلقة

**الحل:**
```bash
1. تأكد أن الماكينة شغالة
2. جرب ping للماكينة:
   ping 192.168.1.201
3. إذا فشل، حدث device_ip في config.json
4. أو فعّل auto_discover_ip: true
```

---

### لا توجد أخطاء لكن لا توجد سجلات جديدة

**السبب:** لا توجد سجلات جديدة على الماكينة

**الحل:**
```bash
1. سجل بصمة تجريبية على الماكينة
2. انتظر 5 دقائق (وقت المزامنة)
3. راقب Bridge Agent log
```

---

## 🔧 إعدادات متقدمة

### تغيير وقت المزامنة:

```json
// في config.json
"sync_interval": 1  // كل دقيقة بدلاً من 5
```

### تشغيل في وضع Verbose:

```python
# في agent.py - السطر 20
logging.basicConfig(
    level=logging.DEBUG,  # غيّر من INFO إلى DEBUG
    ...
)
```

### للإنتاج (Production):

```json
// في config.json
{
    "server_url": "https://www.mwheba.co.uk",  // غيّر للدومين الفعلي
    ...
}
```

```bash
# في .env
ALLOWED_HOSTS=www.mwheba.co.uk,mwheba.co.uk
DEBUG=False
```

---

## 📞 الملفات المهمة

### على السيرفر:
- `.env` - إعدادات المصادقة
- `hr/views.py` - API endpoint (السطر 820-930)
- `hr/urls.py` - URL routing (السطر 78)
- `mwheba_erp/settings.py` - إعدادات BRIDGE_AGENTS

### على الجهاز المحلي:
- `config.json` - إعدادات Agent
- `agent.py` - الكود الرئيسي
- `bridge_agent.log` - سجل الأخطاء والأحداث

---

## ✨ نصائح

1. **راقب الـ logs باستمرار** أثناء التشغيل الأول
2. **سجل بصمة تجريبية** للتأكد من عمل النظام
3. **تحقق من Django Admin** بعد كل مزامنة
4. **احتفظ بنسخة احتياطية** من config.json و .env

---

**تاريخ التحديث:** 2025-01-05
**الحالة:** ✅ جاهز للتشغيل
**الإصلاحات:** تم تصحيح URL في agent.py
