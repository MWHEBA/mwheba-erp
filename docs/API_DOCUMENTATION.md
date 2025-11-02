# 📡 توثيق API - MWHEBA ERP

**الإصدار:** 1.0.0  
**تاريخ التحديث:** 2025-11-02  
**الحالة:** مكتمل ✅

---

## 📋 نظرة عامة

نظام API الخاص بـ MWHEBA ERP يوفر واجهة برمجية RESTful كاملة للتكامل مع الأنظمة الخارجية. يدعم API عمليات CRUD كاملة لجميع النماذج الرئيسية مع مصادقة آمنة وصلاحيات متقدمة.

### Base URL
```
http://your-domain.com/api/
```

### المصادقة
يدعم النظام نوعين من المصادقة:
1. **Token Authentication** - للتطبيقات البسيطة
2. **JWT Authentication** - للتطبيقات المتقدمة (موصى به)

---

## 🔐 المصادقة (Authentication)

### 1. الحصول على Token

#### Token Authentication
```http
POST /api/token/
Content-Type: application/json

{
  "username": "admin",
  "password": "password123"
}
```

**Response:**
```json
{
  "token": "9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b"
}
```

#### JWT Authentication
```http
POST /api/token/jwt/
Content-Type: application/json

{
  "username": "admin",
  "password": "password123"
}
```

**Response:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### 2. استخدام Token

#### Token Authentication
```http
GET /api/products/
Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b
```

#### JWT Authentication
```http
GET /api/products/
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

### 3. تحديث JWT Token
```http
POST /api/token/jwt/refresh/
Content-Type: application/json

{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

---

## 👥 Users API

### قائمة المستخدمين
```http
GET /api/users/
```

**Query Parameters:**
- `role` - تصفية حسب الدور
- `is_active` - تصفية حسب الحالة
- `search` - البحث في الاسم والبريد
- `ordering` - الترتيب (date_joined, username)

**Response:**
```json
{
  "count": 10,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "first_name": "محمد",
      "last_name": "أحمد",
      "phone": "01234567890",
      "role": "admin",
      "is_active": true,
      "is_staff": true,
      "date_joined": "2025-01-01T00:00:00Z"
    }
  ]
}
```

### تفاصيل مستخدم
```http
GET /api/users/{id}/
```

### إنشاء مستخدم
```http
POST /api/users/
Content-Type: application/json

{
  "username": "newuser",
  "email": "user@example.com",
  "password": "SecurePass123",
  "password_confirm": "SecurePass123",
  "first_name": "أحمد",
  "last_name": "محمد",
  "phone": "01234567890",
  "role": "accountant"
}
```

### المستخدم الحالي
```http
GET /api/users/me/
```

### إحصائيات المستخدمين
```http
GET /api/users/stats/
```

**Response:**
```json
{
  "total": 25,
  "active": 20,
  "staff": 5,
  "by_role": [
    {"role": "admin", "count": 2},
    {"role": "accountant", "count": 5},
    {"role": "sales", "count": 10}
  ]
}
```

---

## 📦 Products API

### قائمة المنتجات
```http
GET /api/products/
```

**Query Parameters:**
- `category` - تصفية حسب التصنيف
- `is_active` - تصفية حسب الحالة
- `search` - البحث في الاسم والكود
- `ordering` - الترتيب (name, unit_price, created_at)

**Response:**
```json
{
  "count": 100,
  "next": "http://api/products/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "منتج تجريبي",
      "sku": "PROD-001",
      "category": 1,
      "category_name": "إلكترونيات",
      "unit_price": "1500.00",
      "cost_price": "1000.00",
      "total_stock": 50,
      "is_active": true
    }
  ]
}
```

### تفاصيل منتج
```http
GET /api/products/{id}/
```

**Response:**
```json
{
  "id": 1,
  "name": "منتج تجريبي",
  "sku": "PROD-001",
  "barcode": "1234567890123",
  "category": 1,
  "category_name": "إلكترونيات",
  "description": "وصف المنتج",
  "unit_price": "1500.00",
  "cost_price": "1000.00",
  "min_stock_level": 10,
  "max_stock_level": 100,
  "reorder_point": 20,
  "unit_of_measure": "قطعة",
  "total_stock": 50,
  "stock_value": 50000.00,
  "is_active": true,
  "recent_movements": [...],
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-15T00:00:00Z"
}
```

### إنشاء منتج
```http
POST /api/products/
Content-Type: application/json

{
  "name": "منتج جديد",
  "sku": "PROD-002",
  "category": 1,
  "unit_price": "2000.00",
  "cost_price": "1500.00",
  "min_stock_level": 5,
  "reorder_point": 10,
  "unit_of_measure": "قطعة",
  "is_active": true
}
```

### تحديث منتج
```http
PUT /api/products/{id}/
PATCH /api/products/{id}/
```

### حذف منتج
```http
DELETE /api/products/{id}/
```

### المنتجات منخفضة المخزون
```http
GET /api/products/low_stock/
```

### إحصائيات المنتجات
```http
GET /api/products/stats/
```

**Response:**
```json
{
  "total": 150,
  "active": 140,
  "low_stock": 15,
  "total_value": 500000.00
}
```

### سجل حركات منتج
```http
GET /api/products/{id}/stock_history/
```

---

## 🏢 Suppliers API

### قائمة الموردين
```http
GET /api/suppliers/
```

**Query Parameters:**
- `type` - تصفية حسب النوع
- `is_active` - تصفية حسب الحالة
- `search` - البحث في الاسم والهاتف
- `ordering` - الترتيب (name, created_at)

### تفاصيل مورد
```http
GET /api/suppliers/{id}/
```

**Response:**
```json
{
  "id": 1,
  "name": "مورد تجريبي",
  "type": 1,
  "type_name": "مخزن ورق",
  "phone": "01234567890",
  "email": "supplier@example.com",
  "address": "العنوان",
  "city": "القاهرة",
  "country": "مصر",
  "tax_number": "123456789",
  "account": 10,
  "payment_terms": "30 يوم",
  "credit_limit": "100000.00",
  "notes": "ملاحظات",
  "total_purchases": 25,
  "total_amount": 250000.00,
  "account_balance": 50000.00,
  "is_active": true,
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-01-15T00:00:00Z"
}
```

### مشتريات مورد
```http
GET /api/suppliers/{id}/purchases/
```

### إحصائيات الموردين
```http
GET /api/suppliers/stats/
```

---

## 👤 Customers API

### قائمة العملاء
```http
GET /api/customers/
```

### تفاصيل عميل
```http
GET /api/customers/{id}/
```

### مبيعات عميل
```http
GET /api/customers/{id}/sales/
```

### إحصائيات العملاء
```http
GET /api/customers/stats/
```

---

## 💰 Sales API

### قائمة المبيعات
```http
GET /api/sales/
```

**Query Parameters:**
- `customer` - تصفية حسب العميل
- `status` - تصفية حسب الحالة
- `payment_method` - تصفية حسب طريقة الدفع
- `search` - البحث في رقم الفاتورة
- `ordering` - الترتيب (date, total_amount)

### تفاصيل فاتورة مبيعات
```http
GET /api/sales/{id}/
```

**Response:**
```json
{
  "id": 1,
  "invoice_number": "INV-2025-001",
  "customer": 1,
  "customer_name": "عميل تجريبي",
  "date": "2025-01-15",
  "due_date": "2025-02-15",
  "subtotal": "10000.00",
  "discount": "500.00",
  "tax": "1425.00",
  "total_amount": "10925.00",
  "paid_amount": "5000.00",
  "status": "partial",
  "payment_method": "cash",
  "notes": "ملاحظات",
  "items": [
    {
      "id": 1,
      "product": 1,
      "product_name": "منتج 1",
      "quantity": 5,
      "unit_price": "2000.00",
      "discount": "100.00",
      "tax_rate": "15.00",
      "total": "10925.00"
    }
  ],
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z"
}
```

### إنشاء فاتورة مبيعات
```http
POST /api/sales/
Content-Type: application/json

{
  "customer": 1,
  "date": "2025-01-15",
  "due_date": "2025-02-15",
  "payment_method": "cash",
  "notes": "ملاحظات",
  "items": [
    {
      "product": 1,
      "quantity": 5,
      "unit_price": "2000.00",
      "discount": "100.00",
      "tax_rate": "15.00"
    }
  ]
}
```

### إحصائيات المبيعات
```http
GET /api/sales/stats/
```

**Response:**
```json
{
  "total_count": 150,
  "total_amount": 500000.00,
  "paid_amount": 400000.00,
  "outstanding": 100000.00,
  "by_status": [
    {"status": "paid", "count": 100},
    {"status": "partial", "count": 30},
    {"status": "unpaid", "count": 20}
  ]
}
```

### آخر المبيعات
```http
GET /api/sales/recent/?limit=10
```

---

## 🛒 Purchases API

### قائمة المشتريات
```http
GET /api/purchases/
```

### تفاصيل فاتورة مشتريات
```http
GET /api/purchases/{id}/
```

### إحصائيات المشتريات
```http
GET /api/purchases/stats/
```

### آخر المشتريات
```http
GET /api/purchases/recent/?limit=10
```

---

## 📊 Financial API

### دليل الحسابات

#### قائمة الحسابات
```http
GET /api/accounts/
```

**Query Parameters:**
- `account_type` - تصفية حسب النوع
- `is_active` - تصفية حسب الحالة
- `search` - البحث في الكود والاسم
- `ordering` - الترتيب (code, name)

#### شجرة الحسابات
```http
GET /api/accounts/tree/
```

#### معاملات حساب
```http
GET /api/accounts/{id}/transactions/
```

**Response:**
```json
[
  {
    "date": "2025-01-15",
    "entry_number": "JE-2025-001",
    "description": "قيد افتتاحي",
    "debit": "10000.00",
    "credit": "0.00"
  }
]
```

### القيود المحاسبية

#### قائمة القيود
```http
GET /api/journal-entries/
```

#### تفاصيل قيد
```http
GET /api/journal-entries/{id}/
```

**Response:**
```json
{
  "id": 1,
  "entry_number": "JE-2025-001",
  "date": "2025-01-15",
  "description": "قيد افتتاحي",
  "reference_type": "opening",
  "reference_id": null,
  "total_debit": "10000.00",
  "total_credit": "10000.00",
  "status": "posted",
  "notes": "ملاحظات",
  "lines": [
    {
      "id": 1,
      "account": 1,
      "account_name": "الصندوق",
      "debit": "10000.00",
      "credit": "0.00",
      "description": "رصيد افتتاحي"
    }
  ],
  "created_by": 1,
  "created_by_name": "محمد أحمد",
  "created_at": "2025-01-15T10:00:00Z",
  "updated_at": "2025-01-15T10:00:00Z"
}
```

#### ترحيل قيد
```http
POST /api/journal-entries/{id}/post_entry/
```

#### إحصائيات القيود
```http
GET /api/journal-entries/stats/
```

---

## 📦 Stock & Warehouse API

### المخزون

#### قائمة المخزون
```http
GET /api/stocks/
```

#### المخزون حسب المخزن
```http
GET /api/stocks/by_warehouse/?warehouse_id=1
```

### حركات المخزون

#### قائمة الحركات
```http
GET /api/stock-movements/
```

**Query Parameters:**
- `product` - تصفية حسب المنتج
- `warehouse` - تصفية حسب المخزن
- `movement_type` - تصفية حسب النوع

### المخازن

#### قائمة المخازن
```http
GET /api/warehouses/
```

#### جرد مخزن
```http
GET /api/warehouses/{id}/inventory/
```

---

## 🔍 البحث والتصفية

### البحث
جميع endpoints تدعم البحث باستخدام `search` parameter:
```http
GET /api/products/?search=laptop
GET /api/customers/?search=أحمد
```

### التصفية
استخدم `filterset_fields` للتصفية:
```http
GET /api/products/?category=1&is_active=true
GET /api/sales/?status=paid&customer=5
```

### الترتيب
استخدم `ordering` parameter:
```http
GET /api/products/?ordering=name
GET /api/sales/?ordering=-date  # ترتيب عكسي
```

### Pagination
```http
GET /api/products/?page=2&page_size=50
```

---

## ⚠️ معالجة الأخطاء

### أكواد الحالة
- `200 OK` - نجاح العملية
- `201 Created` - تم الإنشاء بنجاح
- `204 No Content` - تم الحذف بنجاح
- `400 Bad Request` - خطأ في البيانات
- `401 Unauthorized` - غير مصرح
- `403 Forbidden` - ممنوع
- `404 Not Found` - غير موجود
- `500 Internal Server Error` - خطأ في الخادم

### أمثلة الأخطاء

#### خطأ في المصادقة
```json
{
  "detail": "Authentication credentials were not provided."
}
```

#### خطأ في التحقق
```json
{
  "name": ["هذا الحقل مطلوب"],
  "email": ["أدخل عنوان بريد إلكتروني صحيح"]
}
```

#### خطأ في الصلاحيات
```json
{
  "detail": "You do not have permission to perform this action."
}
```

---

## 🔒 الصلاحيات

### أنواع الصلاحيات
1. **IsAuthenticated** - مستخدم مسجل الدخول
2. **IsManagerOrReadOnly** - مدير للكتابة، الجميع للقراءة
3. **IsAdminOrReadOnly** - مدير نظام للكتابة، الجميع للقراءة
4. **IsOwnerOrReadOnly** - المالك للكتابة، الجميع للقراءة

### الصلاحيات حسب Endpoint
- **Users**: IsManagerOrReadOnly
- **Products**: IsManagerOrReadOnly
- **Suppliers**: IsManagerOrReadOnly
- **Customers**: IsManagerOrReadOnly
- **Sales**: IsManagerOrReadOnly
- **Purchases**: IsManagerOrReadOnly
- **Financial**: IsManagerOrReadOnly
- **Stock Movements**: IsAuthenticated (قراءة فقط)

---

## 💡 أمثلة الاستخدام

### Python (requests)
```python
import requests

# المصادقة
response = requests.post('http://api/token/jwt/', json={
    'username': 'admin',
    'password': 'password123'
})
token = response.json()['access']

# الحصول على المنتجات
headers = {'Authorization': f'Bearer {token}'}
response = requests.get('http://api/products/', headers=headers)
products = response.json()

# إنشاء منتج
data = {
    'name': 'منتج جديد',
    'sku': 'PROD-003',
    'category': 1,
    'unit_price': '1500.00',
    'cost_price': '1000.00'
}
response = requests.post('http://api/products/', json=data, headers=headers)
```

### JavaScript (fetch)
```javascript
// المصادقة
const response = await fetch('http://api/token/jwt/', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    username: 'admin',
    password: 'password123'
  })
});
const {access} = await response.json();

// الحصول على المنتجات
const products = await fetch('http://api/products/', {
  headers: {'Authorization': `Bearer ${access}`}
}).then(r => r.json());

// إنشاء منتج
const newProduct = await fetch('http://api/products/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'منتج جديد',
    sku: 'PROD-003',
    category: 1,
    unit_price: '1500.00',
    cost_price: '1000.00'
  })
}).then(r => r.json());
```

---

## 📝 ملاحظات مهمة

1. **جميع التواريخ** بصيغة ISO 8601: `2025-01-15T10:00:00Z`
2. **جميع الأسعار** بصيغة string مع خانتين عشريتين: `"1500.00"`
3. **Pagination** افتراضي: 100 عنصر لكل صفحة
4. **Rate Limiting**: سيتم إضافته في التحديثات القادمة
5. **Versioning**: الإصدار الحالي v1، سيتم إضافة versioning في المستقبل

---

## 🚀 التحديثات القادمة

- [ ] إضافة Swagger/OpenAPI documentation
- [ ] إضافة GraphQL support
- [ ] إضافة Webhooks
- [ ] إضافة Bulk operations
- [ ] إضافة Export/Import APIs
- [ ] إضافة Real-time notifications
- [ ] تحسين Performance مع caching
- [ ] إضافة Rate limiting

---

**آخر تحديث:** 2025-11-02  
**الإصدار:** 1.0.0  
**الحالة:** مكتمل ✅
