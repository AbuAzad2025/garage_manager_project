## الهدف
إعادة بناء قالب Ledger Control من الصفر بصيغة نظيفة ومتوافقة بالكامل مع Bootstrap 4، مع تبويبات ومودالات تعمل بشكل موثوق، وإزالة أي منطق قديم أو متعارض.

## النطاق
- ملف واحد فقط: `templates/security/ledger_control.html`.
- الحفاظ على هيكل الكتل Jinja (`extends` + `block security_content` + `block extra_js`).
- عدم تعديل بقية الصفحات أو الاعتماديات خارج ما يلزم للتوافق.

## اختيار Bootstrap
- استخدام Bootstrap 4 فقط (متوافق مع AdminLTE المحمّل في `base.html`).
- عدم استخدام `data-bs-*` ولا واجهات `window.bootstrap` الخاصة بـ BS5.

## هيكل الواجهة (Markup)
1. شريط تبويبات رئيسي (nav-pills):
   - عناصر `<a class="nav-link" data-toggle="pill" href="#tab-accounts">`، وTabs: accounts, entries, batches, operations, editor, tools.
   - خصائص إمكانية الوصول: `role="tab"`, `aria-controls`, `aria-selected`.
2. محتوى التبويبات (tab-content):
   - أقسام بسيطة لكل تبويب مع عناصر أساسية (جداول أو placeholders)، بدون منطق متقدم في البداية.
3. تبويبات فرعية داخل "مركز التحكم" (nav-tabs):
   - عناصر `<a class="nav-link" data-toggle="tab" href="#ops-periods">` وغيرها.
4. مودالات BS4:
   - `div.modal.fade` + `data-dismiss="modal"` مع زر إغلاق `button.close`، ومودالين: إضافة حساب، تعديل حساب.

## منطق الجافاسكربت (BS4 فقط)
1. تفعيل التبويبات:
   - ربط `shown.bs.tab` عبر jQuery لبدء التحميل عند الانتقال.
   - دعم fallback يدوي إذا غاب jQuery (إضافة/إزالة `active`/`show`).
2. تحميل البيانات (أساسيات):
   - دوال: `loadAccounts`, `loadEntries`, `loadBatches`, وداخل العمليات `loadPendingBatches` إن لزم.
   - دالة مساعدة `ensureJson(response)` للتحقق من `content-type` و`status` مع عرض spinner.
3. المودالات:
   - فتح عبر `$('#addAccountModal').modal('show')` و`$('#editAccountModal').modal('show')`.
   - حفظ/تحديث عبر `fetch` (POST) ثم إعادة التحميل وإغلاق المودال.
4. إزالة أي استدعاءات لـ BS5:
   - عدم استخدام `bootstrap.Modal.getOrCreateInstance` أو `new bootstrap.Modal`.
   - عدم استخدام محددات `button[data-bs-toggle]`.

## توافق عام
- التأكد أن منطق التمرير السلس لا يعترض روابط التبويبات (موجود في `base.html` بالفعل؛ سنضمن أن الروابط تستخدم `data-toggle` و`role="tab"`).
- عدم إضافة أي تضمين لملفات BS5 في `extra_js`.

## التحقق
- النقر بين التبويبات الرئيسية والفرعية يفعّل المحتوى الصحيح.
- فتح/إغلاق المودالات يعمل دون أخطاء.
- لا توجد رسائل خطأ حول `bootstrap.Modal.getOrCreateInstance`.

## التسليم
- ملف `ledger_control.html` مُعاد بناؤه بالكامل بصيغة BS4، نظيف، ومبسّط، مع JS متوافق.
- تعليقات صفر داخل الشيفرة (اتباع سياسة المستودع).