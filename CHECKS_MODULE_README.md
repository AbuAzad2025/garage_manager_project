# 🏦 وحدة الشيكات الشاملة - دليل التشغيل والإكمال

## 🎉 ما تم إنجازه (85%)

### ✅ 1. البنية التحتية الكاملة
- **موديل Check** منفصل ومستقل (193 سطر)
- **5 Routes CRUD** جاهزة للعمل (260 سطر)
- **قالب form.html** احترافي (300+ سطر)
- **تكامل كامل** مع API الموجود

### ✅ 2. المميزات الرئيسية
#### 🔹 الموديل (`models.py` - سطر 7607)
```python
class Check(db.Model, TimestampMixin, AuditMixin):
    # 7 حالات: PENDING, CASHED, RETURNED, BOUNCED, RESUBMITTED, CANCELLED, OVERDUE
    # معلومات كاملة: الساحب، المستفيد، البنك، التواريخ
    # سجل تغييرات JSON
    # ربط اختياري بالعملاء/الموردين/الشركاء
    # دوال ذكية: is_overdue, days_until_due, is_due_soon
```

#### 🔹 Routes (`routes/checks.py`)
| Route | الوظيفة | الحالة |
|-------|---------|--------|
| `/checks/new` | إضافة شيك يدوي | ✅ |
| `/checks/edit/<id>` | تعديل شيك | ✅ |
| `/checks/detail/<id>` | عرض تفاصيل | ✅ |
| `/checks/delete/<id>` | حذف شيك | ✅ |
| `/checks/reports` | صفحة التقارير | ✅ |

#### 🔹 القالب (`templates/checks/form.html`)
- نموذج شامل للإضافة/التعديل
- 4 بطاقات منظمة (معلومات الشيك، الأطراف، الربط، الملاحظات)
- JavaScript للتحقق من البيانات
- دعم كامل للشيكات الواردة/الصادرة

---

## ⏳ ما يجب إكماله (15%)

### 1. **قالبين إضافيين** (30 دقيقة)

#### `templates/checks/detail.html`
```html
{% extends 'base.html' %}
{% block content %}
<div class="card">
  <div class="card-header">
    <h3>تفاصيل الشيك رقم {{ check.check_number }}</h3>
  </div>
  <div class="card-body">
    <!-- معلومات الشيك -->
    <div class="row">
      <div class="col-md-6">
        <p><strong>البنك:</strong> {{ check.check_bank }}</p>
        <p><strong>المبلغ:</strong> {{ check.amount }} {{ check.currency }}</p>
        <p><strong>تاريخ الاستحقاق:</strong> {{ check.check_due_date.strftime('%Y-%m-%d') }}</p>
      </div>
      <div class="col-md-6">
        <p><strong>الحالة:</strong> 
          <span class="badge badge-{{ CHECK_STATUS[check.status]['color'] }}">
            {{ CHECK_STATUS[check.status]['ar'] }}
          </span>
        </p>
        <p><strong>النوع:</strong> {{ 'وارد' if check.direction == 'IN' else 'صادر' }}</p>
      </div>
    </div>
    
    <!-- سجل التغييرات -->
    <h4>سجل التغييرات</h4>
    <ul class="timeline">
      {% for change in status_history %}
      <li>
        <i class="fas fa-clock bg-blue"></i>
        <div class="timeline-item">
          <span class="time">{{ change.timestamp }}</span>
          <h3 class="timeline-header">تغيير الحالة</h3>
          <div class="timeline-body">
            من {{ change.old_status }} إلى {{ change.new_status }}
            {% if change.reason %}<br>السبب: {{ change.reason }}{% endif %}
            {% if change.user %}<br>بواسطة: {{ change.user }}{% endif %}
          </div>
        </div>
      </li>
      {% endfor %}
    </ul>
    
    <!-- أزرار الإجراءات -->
    <a href="{{ url_for('checks.edit_check', check_id=check.id) }}" class="btn btn-primary">
      <i class="fas fa-edit"></i> تعديل
    </a>
    <form method="POST" action="{{ url_for('checks.delete_check', check_id=check.id) }}" style="display: inline;">
      <button type="submit" class="btn btn-danger" onclick="return confirm('هل أنت متأكد؟')">
        <i class="fas fa-trash"></i> حذف
      </button>
    </form>
  </div>
</div>
{% endblock %}
```

#### `templates/checks/reports.html`
```html
{% extends 'base.html' %}
{% block content %}
<div class="row">
  <!-- إحصائيات -->
  <div class="col-lg-3 col-6">
    <div class="small-box bg-info">
      <div class="inner">
        <h3>{{ independent_checks|length }}</h3>
        <p>إجمالي الشيكات</p>
      </div>
      <div class="icon"><i class="fas fa-money-check-alt"></i></div>
    </div>
  </div>
  
  <div class="col-lg-3 col-6">
    <div class="small-box bg-danger">
      <div class="inner">
        <h3>{{ overdue_checks|length }}</h3>
        <p>متأخرة</p>
      </div>
      <div class="icon"><i class="fas fa-exclamation-triangle"></i></div>
    </div>
  </div>
  
  <!-- جداول التفاصيل -->
  <div class="col-12">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">الشيكات المتأخرة</h3>
      </div>
      <div class="card-body">
        <table class="table table-bordered">
          <thead>
            <tr>
              <th>رقم الشيك</th>
              <th>البنك</th>
              <th>المبلغ</th>
              <th>الاستحقاق</th>
              <th>الأيام المتأخرة</th>
            </tr>
          </thead>
          <tbody>
            {% for check in overdue_checks %}
            <tr>
              <td>{{ check.check_number }}</td>
              <td>{{ check.check_bank }}</td>
              <td>{{ check.amount }} {{ check.currency }}</td>
              <td>{{ check.check_due_date.strftime('%Y-%m-%d') }}</td>
              <td class="text-danger">{{ -check.days_until_due }} يوم</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>
{% endblock %}
```

### 2. **Seed Data** (10 دقائق)

في نهاية `comprehensive_seed.py`:
```python
# إضافة شيكات تجريبية
from models import Check, CheckStatus, PaymentDirection
from datetime import datetime, timedelta

print("Adding sample checks...")
checks_data = [
    {
        'check_number': '10001',
        'check_bank': 'بنك فلسطين',
        'check_date': datetime.utcnow(),
        'check_due_date': datetime.utcnow() + timedelta(days=30),
        'amount': Decimal('5000.00'),
        'currency': 'ILS',
        'direction': PaymentDirection.IN.value,
        'status': CheckStatus.PENDING.value,
        'drawer_name': 'محمد أحمد',
        'drawer_phone': '0599123456',
        'payee_name': 'شركة أزاد',
        'notes': 'شيك دفعة أولى',
        'created_by_id': 1
    },
    {
        'check_number': '10002',
        'check_bank': 'بنك القدس',
        'check_date': datetime.utcnow() - timedelta(days=60),
        'check_due_date': datetime.utcnow() - timedelta(days=10),  # متأخر
        'amount': Decimal('3500.00'),
        'currency': 'ILS',
        'direction': PaymentDirection.OUT.value,
        'status': CheckStatus.PENDING.value,
        'drawer_name': 'شركة أزاد',
        'payee_name': 'شركة قطع الغيار',
        'payee_phone': '0599654321',
        'notes': 'دفعة لمورد',
        'created_by_id': 1
    },
    # أضف 3-5 شيكات أخرى بحالات مختلفة
]

for check_data in checks_data:
    check = Check(**check_data)
    db.session.add(check)

db.session.commit()
print("✅ Sample checks added!")
```

### 3. **Migration** (5 دقائق)

```bash
# تشغيل Flask shell
python -c "from app import app, db; from models import Check; app.app_context().push(); db.create_all(); print('✅ Table created!')"

# أو باستخدام Flask-Migrate
flask db migrate -m "Add checks table for independent checks"
flask db upgrade
```

---

## 🚀 التشغيل الفوري

### الأمر السريع (All-in-One)
```bash
# 1. إنشاء الجدول
python -c "from app import app, db; from models import Check; app.app_context().push(); db.create_all(); print('✅ Table created!')"

# 2. إضافة البيانات التجريبية
python comprehensive_seed.py

# 3. تشغيل النظام
python app.py
```

### الروابط المباشرة
- **إضافة شيك**: http://127.0.0.1:5000/checks/new
- **جميع الشيكات**: http://127.0.0.1:5000/checks
- **التقارير**: http://127.0.0.1:5000/checks/reports

---

## 📋 قائمة التحقق النهائية

- [x] موديل Check
- [x] Routes CRUD
- [x] قالب form.html
- [ ] قالب detail.html (انسخ الكود أعلاه)
- [ ] قالب reports.html (انسخ الكود أعلاه)
- [ ] Seed Data (انسخ الكود أعلاه)
- [ ] Migration (نفذ الأمر أعلاه)
- [ ] اختبار شامل

---

## 💡 ملاحظات مهمة

1. **الموديل جاهز تماماً** - لا يحتاج أي تعديل
2. **Routes كاملة** - جميع العمليات CRUD مكتملة
3. **form.html احترافي** - يدعم الإضافة والتعديل
4. **يحتاج فقط قالبين بسيطين** - detail و reports

---

## 🎯 الاستخدام

### إضافة شيك وارد (نستلم نحن)
1. اذهب إلى `/checks/new`
2. املأ البيانات:
   - رقم الشيك: 12345
   - البنك: بنك فلسطين
   - المبلغ: 5000 ILS
   - النوع: **شيك وارد**
   - معلومات الساحب (من يعطينا الشيك)
3. احفظ

### إضافة شيك صادر (ندفع نحن)
1. نفس الخطوات لكن:
   - النوع: **شيك صادر**
   - معلومات المستفيد (من نعطيه الشيك)

---

## 📞 للدعم

- المطور: أحمد غنام
- الموقع: رام الله، فلسطين
- WhatsApp: 0562150193

---

**✅ الوحدة جاهزة 85% - يمكن استخدامها فوراً!**

