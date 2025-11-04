# دليل إعداد ماكينات البصمة ZKTeco

## المشكلة: Dynamic IP في الشبكة المحلية

عندما يكون الراوتر لا يدعم Static IP، هناك عدة حلول:

---

## الحل 1: DHCP Reservation ⭐ (الأفضل)

### الخطوات:

1. **معرفة MAC Address الماكينة:**
   - ادخل على إعدادات الماكينة
   - اذهب لـ Communication → Network
   - اكتب MAC Address (مثال: `00:17:61:XX:XX:XX`)

2. **إعداد الراوتر:**
   ```
   - ادخل على الراوتر (192.168.1.1)
   - Username/Password (غالباً admin/admin)
   - اذهب لـ DHCP Settings أو LAN Settings
   - ابحث عن "DHCP Reservation" أو "Static DHCP"
   - أضف MAC Address الماكينة
   - احجز IP ثابت (مثلاً 192.168.1.100)
   - احفظ وأعد تشغيل الراوتر
   ```

3. **في النظام:**
   ```python
   # أضف الماكينة بالـ IP الثابت
   IP: 192.168.1.100
   Port: 4370
   ```

### المميزات:
- ✅ مجاني 100%
- ✅ لا يحتاج تعديل في الماكينة
- ✅ IP ثابت دائماً
- ✅ يعمل حتى مع restart

---

## الحل 2: Dynamic DNS + Port Forwarding

### للربط مع سيرفر cPanel:

#### 1. إنشاء Dynamic DNS:

**استخدم No-IP (مجاني):**
```
1. سجل في https://www.noip.com
2. أنشئ hostname: mycompany.ddns.net
3. حمل No-IP DUC على جهاز في الشبكة المحلية
4. سيحدث الـ IP تلقائياً
```

**أو استخدم DuckDNS:**
```
1. سجل في https://www.duckdns.org
2. أنشئ domain: mycompany.duckdns.org
3. ثبت script التحديث
```

#### 2. Port Forwarding في الراوتر:

```
- ادخل على الراوتر
- اذهب لـ Port Forwarding أو Virtual Server
- أضف قاعدة جديدة:
  External Port: 4370
  Internal IP: 192.168.1.100 (IP الماكينة)
  Internal Port: 4370
  Protocol: TCP
```

#### 3. في النظام:

```python
# استخدم الـ Domain بدلاً من IP
Domain: mycompany.ddns.net
Port: 4370
```

### المميزات:
- ✅ يعمل من أي مكان
- ✅ الوصول عبر الإنترنت
- ✅ مجاني (No-IP/DuckDNS)

### العيوب:
- ⚠️ يحتاج فتح Port في الراوتر
- ⚠️ مخاطر أمنية (استخدم VPN أفضل)

---

## الحل 3: Local Bridge Server ⭐⭐ (الأفضل للـ Production)

### المفهوم:
```
[ZKTeco Device] → [Local Bridge] → [cPanel Server]
   (192.168.x.x)    (جهاز محلي)      (عبر الإنترنت)
```

### الخطوات:

#### 1. إعداد Bridge Server محلي:

**على جهاز Windows في الشبكة المحلية:**

```python
# bridge_server.py
import schedule
import time
from zk import ZK
import requests

DEVICE_IP = "192.168.1.100"  # IP الماكينة (يمكن أن يكون dynamic)
DEVICE_PORT = 4370
REMOTE_API = "https://yoursite.com/api/biometric/sync/"
API_TOKEN = "your-secret-token"

def sync_attendance():
    """مزامنة كل 5 دقائق"""
    try:
        # الاتصال بالماكينة
        conn = ZK(DEVICE_IP, port=DEVICE_PORT, timeout=5)
        zk = conn.connect()
        
        # جلب السجلات
        attendances = zk.get_attendance()
        
        # تحويل للـ JSON
        records = []
        for att in attendances:
            records.append({
                'user_id': att.user_id,
                'timestamp': str(att.timestamp),
                'status': att.status
            })
        
        # إرسال للسيرفر
        response = requests.post(
            REMOTE_API,
            json={'records': records},
            headers={'Authorization': f'Token {API_TOKEN}'}
        )
        
        print(f"Synced {len(records)} records - Status: {response.status_code}")
        
        zk.disconnect()
        
    except Exception as e:
        print(f"Error: {e}")

# جدولة المزامنة كل 5 دقائق
schedule.every(5).minutes.do(sync_attendance)

print("Bridge Server Started...")
while True:
    schedule.run_pending()
    time.sleep(1)
```

#### 2. تشغيل كـ Windows Service:

```bash
# تثبيت المكتبات
pip install pyzk schedule requests pywin32

# تحويل لـ Service
python -m pip install pyinstaller
pyinstaller --onefile bridge_server.py

# أو استخدم NSSM لتشغيله كـ Service
nssm install BiometricBridge "C:\path\to\bridge_server.exe"
nssm start BiometricBridge
```

#### 3. API Endpoint على cPanel:

```python
# في views.py
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['POST'])
def biometric_sync_api(request):
    """استقبال البيانات من Bridge Server"""
    
    # التحقق من Token
    token = request.headers.get('Authorization')
    if token != f'Token {settings.BRIDGE_API_TOKEN}':
        return Response({'error': 'Unauthorized'}, status=401)
    
    records = request.data.get('records', [])
    
    # حفظ السجلات
    for record in records:
        BiometricLog.objects.create(
            device_id=1,  # أو حسب device_code
            user_id=record['user_id'],
            timestamp=record['timestamp'],
            is_processed=False
        )
    
    return Response({
        'success': True,
        'processed': len(records)
    })
```

### المميزات:
- ✅ لا يحتاج Port Forwarding
- ✅ آمن جداً
- ✅ يعمل مع Dynamic IP
- ✅ مزامنة تلقائية
- ✅ مناسب للـ Production

---

## الحل 4: VPN Tunnel

```
1. إنشاء VPN بين الشبكة المحلية والسيرفر
2. استخدام ZeroTier أو Tailscale (مجاني)
3. الماكينة تصبح في نفس الشبكة الافتراضية
```

---

## التوصية النهائية:

### للتطوير المحلي:
✅ **DHCP Reservation** (الحل 1)

### للـ Production على cPanel:
✅ **Local Bridge Server** (الحل 3)

---

## المكتبات المطلوبة:

```bash
# للاتصال بـ ZKTeco
pip install pyzk

# للـ Bridge Server
pip install schedule requests

# اختياري: للتشغيل كـ Service
pip install pywin32
```

---

## أمثلة الاستخدام:

### اختبار الاتصال:
```python
from zk import ZK

conn = ZK('192.168.1.100', port=4370, timeout=5)
zk = conn.connect()

print(f"Device Name: {zk.get_device_name()}")
print(f"Users: {len(zk.get_users())}")
print(f"Records: {len(zk.get_attendance())}")

zk.disconnect()
```

### جلب السجلات:
```python
attendances = zk.get_attendance()
for att in attendances:
    print(f"User: {att.user_id}, Time: {att.timestamp}")
```

---

## الأمان:

1. **لا تفتح Port 4370 للإنترنت مباشرة**
2. **استخدم VPN أو Bridge Server**
3. **غير الـ Password الافتراضي للماكينة**
4. **استخدم HTTPS للـ API**
5. **احفظ الـ API Token بشكل آمن**
