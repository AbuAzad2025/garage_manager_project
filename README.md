# نظام إدارة الكراج (Garage Manager System)

نظام متكامل لإدارة ورش الصيانة والكراجات مع ميزات متقدمة لإدارة المخزون، المبيعات، الخدمات، والمحاسبة.

## 🚀 الميزات الرئيسية

### إدارة العملاء والخدمات
- ✅ نظام إدارة العملاء الشامل
- ✅ طلبات الخدمة مع تتبع الحالة
- ✅ إدارة قطع الغيار والمخزون
- ✅ نظام التسعير المرن

### المبيعات والمشتريات
- ✅ إدارة المبيعات والفواتير
- ✅ نظام الشحنات والموردين
- ✅ المستودعات المتعددة
- ✅ نظام النقل بين المستودعات

### المحاسبة والمدفوعات
- ✅ نظام الدفعات متعدد العملات
- ✅ تتبع الشيكات
- ✅ المحاسبة العامة (General Ledger)
- ✅ تسويات الموردين والشركاء

### الأنظمة المتقدمة
- ✅ نظام الصلاحيات والأدوار (RBAC)
- ✅ سجل المراجعة (Audit Log)
- ✅ نظام الإشعارات الفورية (Socket.IO)
- ✅ نظام النسخ الاحتياطي التلقائي
- ✅ نظام مراقبة الصحة (Health Check)
- ✅ دعم العملات المتعددة
- ✅ المساعد الذكي للمحاسبة (AI Assistant)

## 📋 متطلبات التشغيل

### الحد الأدنى
- Python 3.10 أو أحدث
- SQLite 3.35+ (مضمّن مع Python)

### للإنتاج (موصى به)
- Python 3.11+
- PostgreSQL 13+
- Redis 6+ (اختياري - للتخزين المؤقت)

## 🔧 التثبيت السريع

### 1. تحميل المشروع
```bash
git clone <repository-url>
cd garage_manager
```

### 2. إنشاء بيئة افتراضية
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. تثبيت المتطلبات
```bash
pip install -r requirements.txt
```

### 4. إعداد قاعدة البيانات
```bash
# إنشاء قاعدة البيانات
flask db upgrade

# إنشاء البيانات الأساسية
flask seed-roles
flask seed-all
```

### 5. إنشاء مستخدم مدير
```bash
flask create-superadmin
```

### 6. تشغيل التطبيق
```bash
# للتطوير
python app.py

# أو
flask run

# للإنتاج (استخدم gunicorn أو waitress)
waitress-serve --host=0.0.0.0 --port=5000 --call app:create_app
```

## ⚙️ الإعدادات

### ملف `.env`

انسخ ملف `.env.example` إلى `.env` وقم بتحديث القيم:

```bash
cp .env.example .env
```

**الإعدادات الأساسية:**
```env
APP_ENV=development
DEBUG=true
SECRET_KEY=your-secret-key-here

# قاعدة البيانات (اختياري - افتراضياً SQLite)
DATABASE_URL=postgresql://user:password@localhost/garage_db

# العملة الافتراضية
DEFAULT_CURRENCY=ILS
```

**للمساعد الذكي (اختياري):**
```env
OPENAI_API_KEY=sk-proj-your-key
# أو
ANTHROPIC_API_KEY=sk-ant-your-key
```

## 📊 لوحة التحكم

بعد تشغيل التطبيق، افتح المتصفح على:
```
http://localhost:5000
```

## 🔧 أوامر CLI المفيدة

### إدارة المستخدمين
```bash
# إنشاء مستخدم جديد
flask create-user --email admin@example.com --username admin

# إنشاء super admin
flask create-superadmin

# عرض المستخدمين
flask list-users
```

### إدارة قاعدة البيانات
```bash
# تحسين الأداء
flask optimize-db

# تشغيل الهجرات
flask db upgrade

# إنشاء نسخة احتياطية
flask backup-db
```

### البيانات الأولية
```bash
# إنشاء الأدوار والصلاحيات
flask seed-roles

# إنشاء جميع البيانات الأولية
flask seed-all
```

## 🏥 نقاط نهاية مراقبة الصحة

```bash
# فحص الصحة الشامل
curl http://localhost:5000/health

# فحص سريع (ping)
curl http://localhost:5000/health/ping

# فحص الجاهزية
curl http://localhost:5000/health/ready

# المقاييس
curl http://localhost:5000/health/metrics
```

## 📦 الهيكل التنظيمي

```
garage_manager/
├── app.py                 # التطبيق الرئيسي
├── config.py              # الإعدادات
├── models.py              # نماذج قاعدة البيانات
├── forms.py               # نماذج WTForms
├── cli.py                 # أوامر CLI
├── utils.py               # دوال مساعدة
├── extensions.py          # إعداد الإضافات
├── routes/                # مسارات التطبيق
│   ├── auth.py
│   ├── main.py
│   ├── customers.py
│   ├── service.py
│   ├── sales.py
│   ├── payments.py
│   ├── health.py         # مراقبة الصحة
│   └── ...
├── templates/             # قوالب HTML
├── static/                # الملفات الثابتة
├── migrations/            # هجرات قاعدة البيانات
└── instance/              # قاعدة البيانات والملفات المحلية
```

## 🔐 الأمان

### الصلاحيات الأساسية
- `manage_users` - إدارة المستخدمين
- `manage_customers` - إدارة العملاء
- `manage_service` - إدارة الخدمات
- `manage_sales` - إدارة المبيعات
- `manage_inventory` - إدارة المخزون
- `manage_payments` - إدارة المدفوعات
- `view_reports` - عرض التقارير

### الأدوار الافتراضية
- **Super Admin** - صلاحيات كاملة
- **Admin** - إدارة كاملة ماعدا الصلاحيات
- **Staff** - موظف (صلاحيات محدودة)
- **Mechanic** - ميكانيكي
- **Customer** - عميل (محدود)

## 🌍 دعم العملات

النظام يدعم العملات التالية:
- ILS (شيكل إسرائيلي) ₪
- USD (دولار أمريكي) $
- EUR (يورو) €
- JOD (دينار أردني)
- AED (درهم إماراتي)
- SAR (ريال سعودي)
- EGP (جنيه مصري)
- GBP (جنيه إسترليني)

## 🔄 النسخ الاحتياطي

النظام يقوم بالنسخ الاحتياطي التلقائي:
- **قاعدة البيانات**: كل ساعة
- **SQL Dump**: كل 24 ساعة
- **الموقع**: `instance/backups/`

لإنشاء نسخة احتياطية يدوية:
```bash
flask backup-db
```

## 📈 الأداء

### تحسين الأداء
```bash
# إنشاء الفهارس وتحليل قاعدة البيانات
flask optimize-db
```

### التخزين المؤقت
النظام يدعم:
- Simple (في الذاكرة)
- Redis (موصى به للإنتاج)
- Memcached

## 🐛 استكشاف الأخطاء

### المشاكل الشائعة

**1. خطأ في الاستيراد:**
```bash
# تأكد من تفعيل البيئة الافتراضية
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

**2. خطأ في قاعدة البيانات:**
```bash
# إعادة إنشاء قاعدة البيانات
flask db upgrade
flask seed-roles
```

**3. خطأ في الصلاحيات:**
```bash
# تحديث الصلاحيات
flask sync-permissions
```

## 📝 السجلات

السجلات تُحفظ في:
- `error.log` - أخطاء التطبيق
- `server_error.log` - أخطاء السيرفر

لعرض السجلات:
```bash
# Windows
type error.log

# Linux/Mac
tail -f error.log
```

## 🤝 المساهمة

نرحب بالمساهمات! الرجاء:
1. Fork المشروع
2. إنشاء branch جديد (`git checkout -b feature/amazing-feature`)
3. Commit التغييرات (`git commit -m 'Add amazing feature'`)
4. Push للـ branch (`git push origin feature/amazing-feature`)
5. فتح Pull Request

## 📄 الترخيص

هذا المشروع مرخص تحت **MIT License** - راجع ملف `LICENSE` للتفاصيل.

**حقوق النشر © 2024-2025 شركة أزاد للأنظمة الذكية**  
**Copyright © 2024-2025 Azad Smart Systems Company**

## 🏢 معلومات الشركة

**شركة أزاد للأنظمة الذكية** | **Azad Smart Systems**  
**المطور الرئيسي:** المهندس أحمد غنام | **Lead Developer:** Eng. Ahmed Ghannam  
**الموقع:** رام الله - فلسطين 🇵🇸 | **Location:** Ramallah, Palestine  
**الإصدار:** v4.0.0 Enterprise Edition  
**التخصص:** أنظمة إدارة الكراجات والمعدات الثقيلة

## 📞 الدعم

للدعم والاستفسارات:
- 📧 Email: ahmed@azad-systems.com
- 🌐 Website: https://azad-systems.com
- 📱 Phone: +970-XXX-XXXX (Palestine)
- 📍 Location: Ramallah, Palestine 🇵🇸

---

**Made with ❤️ in Palestine 🇵🇸 by Azad Smart Systems**  
**تم بناؤه بـ ❤️ في فلسطين من قبل شركة أزاد للأنظمة الذكية**

