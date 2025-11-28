## الهدف
إصلاح ملف القالب `templates/security/ledger_control.html` ليعمل بالكامل مع Bootstrap 4 (المحمّل عبر AdminLTE)، وإزالة أي تعارضات مع Bootstrap 5، وضمان أن التبويبات والمودالات تعمل بلا أخطاء.

## التعديلات المقترحة على الـ HTML
1. التبويبات الرئيسية (nav-pills):
- تحويل العناصر إلى روابط BS4: `<a class="nav-link" data-toggle="pill" href="#tab-..." role="tab" aria-controls="..." aria-selected="...">`.
- إزالة كل استعمال لـ `button` مع `data-bs-*`.

2. تبويبات مركز التحكم الفرعية (nav-tabs):
- استخدام روابط BS4: `<a class="nav-link" data-toggle="tab" href="#ops-..." role="tab">`.
- إزالة `data-bs-*` بالكامل.

3. المودالات:
- استخدام زر إغلاق BS4: `<button type="button" class="close" data-dismiss="modal" aria-label="Close"><span aria-hidden="true">&times;</span></button>`.
- التأكد من وجود هيكل BS4 القياسي: `.modal.fade > .modal-dialog > .modal-content`.

## التعديلات المقترحة على الـ JavaScript
1. تهيئة المودالات:
- إزالة أي استدعاء لـ `bootstrap.Modal.getOrCreateInstance`.
- تعريف دالة `getOrCreateModal(el)` تعتمد على jQuery فقط: `$('#id').modal('show'/'hide')`.

2. تفعيل التبويبات:
- ربط حدث `shown.bs.tab` عبر jQuery لبدء تحميل المحتوى.
- عند غياب jQuery، تفعيل يدوي: إزالة/إضافة `active` و`show` للروابط والبانلز.
- إزالة محددات/تعامل مع `data-bs-toggle` نهائياً.

3. الدوال العامة لمنع أخطاء undefined:
- تعريف `showAddAccountModal()`, `showEditAccountModal(...)`, `deleteAcc(id)`, `generateClosingEntries()`, `reverseBatch()` ضمن القالب.

## توافق عام مع المشروع
- عدم تضمين Bootstrap 5 في `extra_js` لهذه الصفحة.
- التحقق من منطق `smoothScroll` في `templates/base.html` ليظل يتجاهل روابط التبويب (موجود، سنبقيه).

## التحقق بعد التنفيذ
- التنقل بين التبويبات الرئيسية والفرعية يعمل فوراً.
- فتح/إغلاق مودالات "إضافة حساب" و"تعديل حساب" يعمل بلا أخطاء.
- لا تظهر رسالة `Uncaught TypeError: bootstrap.Modal.getOrCreateInstance is not a function` في الـ Console.
- الروابط المباشرة لـ `#tab-...` من `sitemap.html` تعمل.

## التسليم
- تحديث القالب فقط `security/ledger_control.html` وفق BS4 بالكامل، مع جافاسكربت متوافق وبدون أي تعليقات داخل الشيفرة.

هل تريد أن أبدأ بتنفيذ هذه التعديلات الآن؟