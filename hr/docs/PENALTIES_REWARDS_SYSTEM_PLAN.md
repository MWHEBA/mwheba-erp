# خطة تنفيذ نظام الجزاءات والمكافآت للموظفين
## Employee Penalties & Rewards System - Simplified Plan

---

## 📋 نظرة عامة

نظام بسيط لإدارة الجزاءات والمكافآت للموظفين:
- جزاء أو مكافأة فقط (بدون أنواع فرعية)
- 3 طرق حساب: قيمة ثابتة، بالأيام، بالساعات
- ربط تلقائي مع الرواتب
- اعتماد بسيط (4 حالات فقط)

---

## 🎯 المتطلبات الأساسية

### 1. النوعين الرئيسيين
- **جزاء (Penalty)**: خصم من الراتب
- **مكافأة (Reward)**: إضافة للراتب

### 2. طرق الحساب


#### أ. قيمة ثابتة (Fixed Amount)
```python
amount = fixed_value  # مثال: 500 جنيه
```

#### ب. بالأيام (By Days)
```python
# نفس حساب الأذونات - مع مراعاة الشيفت ورمضان
from hr.services.attendance_service import AttendanceService

daily_rate = AttendanceService.calculate_daily_rate(employee, date)
amount = days_count * daily_rate
```

#### ج. بالساعات (By Hours)
```python
# نفس حساب الأذونات - مع مراعاة الشيفت ورمضان
from hr.services.attendance_service import AttendanceService

hourly_rate = AttendanceService.calculate_hourly_rate(employee, date)
amount = hours_count * hourly_rate
```

---

## 🗂️ البنية التقنية

### 1. Model الوحيد

```python
class PenaltyReward(models.Model):
    """سجل الجزاءات والمكافآت - مبسط"""
    
    CATEGORY_CHOICES = [
        ('penalty', 'جزاء'),
        ('reward', 'مكافأة'),
    ]
    
    CALCULATION_METHOD_CHOICES = [
        ('fixed', 'قيمة ثابتة'),
        ('days', 'بالأيام'),
        ('hours', 'بالساعات'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'قيد الانتظار'),
        ('approved', 'معتمد'),
        ('rejected', 'مرفوض'),
        ('applied', 'مطبق'),
    ]
    
    # الأساسيات
    employee = ForeignKey('Employee', on_delete=CASCADE, related_name='penalties_rewards')
    category = CharField(max_length=20, choices=CATEGORY_CHOICES, verbose_name='النوع')
    
    # التاريخ
    date = DateField(verbose_name='التاريخ')
    month = DateField(verbose_name='الشهر', help_text='شهر التطبيق على الراتب')
    
    # الحساب
    calculation_method = CharField(max_length=20, choices=CALCULATION_METHOD_CHOICES)
    value = DecimalField(max_digits=10, decimal_places=2, verbose_name='القيمة/العدد')
    calculated_amount = DecimalField(max_digits=10, decimal_places=2, verbose_name='المبلغ المحسوب')
    
    # التفاصيل
    reason = TextField(verbose_name='السبب/التفاصيل')
    
    # الحالة
    status = CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # سير العمل
    created_by = ForeignKey(User, on_delete=PROTECT, related_name='created_penalties_rewards')
    created_at = DateTimeField(auto_now_add=True)
    
    approved_by = ForeignKey(User, on_delete=SET_NULL, null=True, blank=True, related_name='approved_penalties_rewards')
    approved_at = DateTimeField(null=True, blank=True)
    review_notes = TextField(blank=True)
    
    # الربط مع الراتب
    payroll = ForeignKey('Payroll', on_delete=SET_NULL, null=True, blank=True, related_name='penalties_rewards')
    applied_at = DateTimeField(null=True, blank=True)
    
    class Meta:
        verbose_name = 'جزاء/مكافأة'
        verbose_name_plural = 'الجزاءات والمكافآت'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['employee', 'status']),
            models.Index(fields=['month', 'status']),
        ]
    
    def calculate_amount(self):
        """حساب المبلغ - نفس منطق الأذونات"""
        from hr.services.attendance_service import AttendanceService
        
        if self.calculation_method == 'fixed':
            self.calculated_amount = self.value
        
        elif self.calculation_method == 'days':
            daily_rate = AttendanceService.calculate_daily_rate(self.employee, self.date)
            self.calculated_amount = self.value * daily_rate
        
        elif self.calculation_method == 'hours':
            hourly_rate = AttendanceService.calculate_hourly_rate(self.employee, self.date)
            self.calculated_amount = self.value * hourly_rate
        
        return self.calculated_amount
    
    def save(self, *args, **kwargs):
        """حساب المبلغ قبل الحفظ"""
        if not self.calculated_amount or self.calculated_amount == 0:
            self.calculate_amount()
        super().save(*args, **kwargs)
```

### 2. Service الوحيد

```python
class PenaltyRewardService:
    """خدمة إدارة الجزاءات والمكافآت"""
    
    @staticmethod
    @transaction.atomic
    def create_penalty_reward(employee, data, created_by):
        """إنشاء جزاء/مكافأة جديد"""
        
        pr = PenaltyReward.objects.create(
            employee=employee,
            category=data['category'],
            date=data['date'],
            month=data['month'],
            calculation_method=data['calculation_method'],
            value=data['value'],
            reason=data['reason'],
            created_by=created_by,
            status='pending'
        )
        
        # حساب المبلغ تلقائياً
        pr.calculate_amount()
        pr.save()
        
        return pr
    
    @staticmethod
    @transaction.atomic
    def approve(penalty_reward, approver, notes=''):
        """اعتماد الجزاء/المكافأة"""
        
        penalty_reward.status = 'approved'
        penalty_reward.approved_by = approver
        penalty_reward.approved_at = timezone.now()
        penalty_reward.review_notes = notes
        penalty_reward.save()
        
        return penalty_reward
    
    @staticmethod
    @transaction.atomic
    def reject(penalty_reward, approver, notes):
        """رفض الجزاء/المكافأة"""
        
        if not notes:
            raise ValueError('يجب إدخال سبب الرفض')
        
        penalty_reward.status = 'rejected'
        penalty_reward.approved_by = approver
        penalty_reward.approved_at = timezone.now()
        penalty_reward.review_notes = notes
        penalty_reward.save()
        
        return penalty_reward
    
    @staticmethod
    def apply_to_payroll(penalty_reward, payroll):
        """تطبيق على قسيمة الراتب"""
        from hr.models import PayrollLine
        
        # تحديد نوع البند
        component_type = 'deduction' if penalty_reward.category == 'penalty' else 'earning'
        
        # إنشاء بند في الراتب
        line = PayrollLine.objects.create(
            payroll=payroll,
            code=f"{penalty_reward.category.upper()}_{penalty_reward.id}",
            name_ar=f"{'جزاء' if penalty_reward.category == 'penalty' else 'مكافأة'} - {penalty_reward.reason[:50]}",
            name_en=f"{'Penalty' if penalty_reward.category == 'penalty' else 'Reward'}",
            component_type=component_type,
            amount=penalty_reward.calculated_amount,
            notes=f"{penalty_reward.reason} - {penalty_reward.date}"
        )
        
        # تحديث حالة الجزاء/المكافأة
        penalty_reward.payroll = payroll
        penalty_reward.status = 'applied'
        penalty_reward.applied_at = timezone.now()
        penalty_reward.save()
        
        # إعادة حساب الراتب
        payroll.calculate_totals_from_lines()
        payroll.save()
        
        return line
    
    @staticmethod
    def get_pending_for_month(employee, month):
        """الحصول على الجزاءات/المكافآت المعتمدة لشهر معين"""
        
        return PenaltyReward.objects.filter(
            employee=employee,
            month__year=month.year,
            month__month=month.month,
            status='approved'
        )
    
    @staticmethod
    def check_pending_before_payroll_approval(employee, month):
        """
        التحقق من عدم وجود جزاءات/مكافآت معلقة قبل اعتماد الراتب
        
        Returns:
            tuple: (can_approve, message)
        """
        pending = PenaltyReward.objects.filter(
            employee=employee,
            month__year=month.year,
            month__month=month.month,
            status='pending'
        ).count()
        
        if pending > 0:
            return False, f'يوجد {pending} جزاء/مكافأة معلقة لهذا الموظف في نفس الشهر'
        
        return True, ''
```

### 3. Form بسيط

```python
class PenaltyRewardForm(forms.ModelForm):
    """نموذج إضافة/تعديل"""
    
    class Meta:
        model = PenaltyReward
        fields = ['employee', 'category', 'date', 'month', 'calculation_method', 'value', 'reason']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'month': forms.DateInput(attrs={'type': 'month', 'class': 'form-control'}),
            'value': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
```

---

## 🎨 الواجهة

### 1. صفحة واحدة للقائمة

**المسار**: `/hr/penalties-rewards/`

**المكونات**:
- Header موحد مع زر واحد: "إضافة جديد"
- Breadcrumb: الرئيسية > الموارد البشرية > الجزاءات والمكافآت
- فلاتر: الموظف، النوع (جزاء/مكافأة)، الحالة، التاريخ من/إلى
- Badges ملونة للإحصائيات:
  - إجمالي الجزاءات (أحمر)
  - إجمالي المكافآت (أخضر)
  - معلق (أصفر)
  - معتمد (أزرق)
- جدول موحد (data_table.html):
  - الموظف
  - النوع (badge: أحمر للجزاء، أخضر للمكافأة)
  - التاريخ
  - المبلغ المحسوب
  - الحالة (badge ملون)
  - الإجراءات

### 2. مودال بسيط

```html
<div class="modal fade" id="penaltyRewardModal">
    <div class="modal-dialog">
        <div class="modal-content">
            <div class="modal-header">
                <h5>إضافة جزاء/مكافأة</h5>
            </div>
            <div class="modal-body">
                <form>
                    <!-- الموظف -->
                    <div class="mb-3">
                        <label>الموظف *</label>
                        <select name="employee" class="form-select" required></select>
                    </div>
                    
                    <!-- النوع -->
                    <div class="mb-3">
                        <label>النوع *</label>
                        <select name="category" class="form-select" required>
                            <option value="penalty">جزاء</option>
                            <option value="reward">مكافأة</option>
                        </select>
                    </div>
                    
                    <!-- التاريخ والشهر -->
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label>التاريخ *</label>
                            <input type="date" name="date" class="form-control" required>
                        </div>
                        <div class="col-md-6 mb-3">
                            <label>شهر التطبيق *</label>
                            <input type="month" name="month" class="form-control" required>
                        </div>
                    </div>
                    
                    <!-- طريقة الحساب -->
                    <div class="mb-3">
                        <label>طريقة الحساب *</label>
                        <select name="calculation_method" class="form-select" required onchange="updateLabel()">
                            <option value="fixed">قيمة ثابتة</option>
                            <option value="days">بالأيام</option>
                            <option value="hours">بالساعات</option>
                        </select>
                    </div>
                    
                    <!-- القيمة -->
                    <div class="mb-3">
                        <label id="valueLabel">القيمة *</label>
                        <input type="number" name="value" class="form-control" step="0.01" required onchange="calculateAmount()">
                        <small class="text-muted" id="calculatedAmount"></small>
                    </div>
                    
                    <!-- السبب -->
                    <div class="mb-3">
                        <label>السبب/التفاصيل *</label>
                        <textarea name="reason" class="form-control" rows="3" required></textarea>
                    </div>
                </form>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">إلغاء</button>
                <button type="submit" class="btn btn-primary">حفظ</button>
            </div>
        </div>
    </div>
</div>
```

### 3. صفحة التفاصيل

**المسار**: `/hr/penalties-rewards/<id>/`

**الأقسام**:
1. معلومات أساسية
2. التفاصيل المالية
3. السبب
4. سير العمل
5. أزرار الإجراءات (اعتماد/رفض)

---

## 🔄 سير العمل

```
[HR] → إضافة → ملء البيانات → حفظ (pending)
                                      ↓
                              [المدير] → اعتماد/رفض
                                      ↓
                                  (approved)
                                      ↓
                          [معالجة الرواتب] → تطبيق تلقائي
                                      ↓
                                  (applied)
```

---

## 🔗 التكامل مع الرواتب

### في integrated_payroll_service.py

```python
def process_monthly_payroll(employee, month):
    """معالجة راتب شهري"""
    
    # ... الكود الحالي ...
    
    # التحقق من عدم وجود جزاءات/مكافآت معلقة
    can_proceed, message = PenaltyRewardService.check_pending_before_payroll_approval(
        employee, month
    )
    
    if not can_proceed:
        raise ValidationError(message)
    
    # تطبيق الجزاءات/المكافآت المعتمدة
    penalties_rewards = PenaltyRewardService.get_pending_for_month(employee, month)
    
    for pr in penalties_rewards:
        PenaltyRewardService.apply_to_payroll(pr, payroll)
    
    # إعادة حساب الإجماليات
    payroll.calculate_totals_from_lines()
    payroll.save()
```

---

## 📁 هيكل الملفات

```
hr/
├── models/
│   └── penalty_reward.py
├── services/
│   └── penalty_reward_service.py
├── forms/
│   └── penalty_reward_forms.py
├── views/
│   └── penalty_reward_views.py
├── templates/hr/penalties_rewards/
│   ├── list.html
│   └── detail.html
└── fixtures/
    └── penalty_reward_sample.json
```

---

## 🎯 خطة التنفيذ

### يوم 1: Backend
- [ ] Model + Migration
- [ ] Service
- [ ] Form
- [ ] URLs

### يوم 2: Frontend
- [ ] صفحة القائمة
- [ ] مودال الإضافة
- [ ] صفحة التفاصيل
- [ ] JavaScript

### يوم 3: التكامل
- [ ] التكامل مع الرواتب
- [ ] التحقق من الجزاءات المعلقة
- [ ] إضافة في القائمة الجانبية
- [ ] الاختبار

---

**المدة المتوقعة**: 3 أيام عمل
**الحالة**: جاهز للتنفيذ
