# تحليل المشاكل الشامل - MWHEBA ERP
**التاريخ:** 2026-04-21  
**البيئة:** Production

---

## المشكلة الأولى: `api/notifications/count/` → 500 Error (متكررة)

### السبب الجذري
الـ view `get_notifications_count` في `core/api.py` **مش عنده `@login_required`**.  
لما الـ session تنتهي (المستخدم سيب الموقع مفتوح)، الـ polling بيستمر كل دقيقتين، والـ Django بيحاول يعمل query بـ `request.user` اللي بقى anonymous — بيرجع 500 بدل 200.

### الكود الحالي (خطأ)
```python
@require_http_methods(["GET"])
def get_notifications_count(request):
    if not request.user.is_authenticated:
        return JsonResponse({"success": True, "count": 0})
    ...
```
المشكلة: الـ check بيحصل داخل الـ view، لكن لو في middleware بيعمل حاجة قبل كده (زي session validation) بيرمي 500 قبل ما الـ view يتنفذ.

### الحل
إضافة `@login_required` مع redirect مناسب + معالجة الـ 401 في الـ JS.

---

## المشكلة الثانية: CSP Violation لـ Cloudflare Beacon

### السبب الجذري
في `core/csp_config_advanced.py`، الـ production `SCRIPT_SRC` بيحتوي على:
```python
"https://static.cloudflareinsights.com",  # Cloudflare Analytics
```
لكن الـ error بيقول إن الـ script من:
```
https://static.cloudflareinsights.com/beacon.min.js/v8c78df7c7c0f484497ecbca7046644da1771523124516
```
**المشكلة:** الـ CSP policy المبنية بتستخدم `build_csp_policy_advanced()` اللي بتكاش الـ policy في أول request. لو الـ cache اتبنى قبل ما الـ production config يتحمل صح، أو لو في override في settings.py بيكتب على الـ SCRIPT_SRC، الـ Cloudflare domain مش بيتضاف.

**الدليل:** في `settings.py` في السطر 1283:
```python
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "'unsafe-eval'")  # بيكتب على الـ config!
```
ده بيكتب على الـ `csp_config_advanced.py` ويشيل Cloudflare من الـ list.

---

## المشكلة الثالثة: `Unchecked runtime.lastError: Could not establish connection`

### السبب الجذري
ده مش error في الكود — ده browser extension (غالباً ad blocker أو security extension) بيحاول يتواصل مع background script مش موجود. **مش محتاج تصليح في الكود.**

---

## الحلول المطلوبة

### 1. تصليح `api/notifications/count/` → 500

**الملف:** `core/api.py`

```python
# قبل
@require_http_methods(["GET"])
def get_notifications_count(request):
    if not request.user.is_authenticated:
        return JsonResponse({"success": True, "count": 0})

# بعد
@require_http_methods(["GET"])
def get_notifications_count(request):
    if not request.user.is_authenticated:
        return JsonResponse({"success": True, "count": 0}, status=200)
    # + إضافة try/except شامل حول كل الـ middleware exceptions
```

**الملف:** `static/js/notifications.js`  
إضافة exponential backoff لما يحصل 500 متكرر.

### 2. تصليح CSP

**الملف:** `corporate_erp/settings.py`  
حذف أو تعديل السطر 1283 اللي بيكتب على الـ CSP config.

### 3. إضافة Cloudflare لـ CSP بشكل صحيح

**الملف:** `core/csp_config_advanced.py`  
التأكد من إن `https://static.cloudflareinsights.com` موجود في production SCRIPT_SRC.
