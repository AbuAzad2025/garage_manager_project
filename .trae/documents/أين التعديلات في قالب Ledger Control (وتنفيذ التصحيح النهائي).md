## مواضع التعديلات في القالب

* التبويبات الرئيسية (BS4): `templates/security/ledger_control.html:12–43`

* تبويبات مركز التحكم الفرعية (BS4): `templates/security/ledger_control.html:119–140`

* زر الإغلاق للمودال إضافة (BS4): `templates/security/ledger_control.html:425–427`

* زر الإغلاق للمودال تعديل (BS4): `templates/security/ledger_control.html:472–474`

* دالة فحص الاستجابة JSON: `templates/security/ledger_control.html:541–547`

* دالة المودال المعتمدة على jQuery فقط: `templates/security/ledger_control.html:549–574`

* دالة تبويب عبر jQuery: `templates/security/ledger_control.html:576–588`

* تحميل الحسابات (spinner/JSON/errors): `templates/security/ledger_control.html:590–635`

* تعريف دوال الواجهة (فتح إضافة/عرض الشجرة): `templates/security/ledger_control.html:1510–1514`

* تفعيل التبويبات رئيسية وفرعية عبر jQuery + fallback: `templates/security/ledger_control.html:1519–1563` و`templates/security/ledger_control.html:1567–1599`

* كتلة `extra_js` بدون تحميل Bootstrap 5: `templates/security/ledger_control.html:1605–1608`

## تحقق وتشغيل

1. افتح `http://127.0.0.1:5000/security/ledger-control/?v=refresh` ثم حدّث بقوة (`Ctrl+Shift+R`).
2. جرّب التبويبات الرئيسية والفرعية؛ يجب أن تعمل فوراً عبر BS4.
3. افتح مودالات "إضافة/تعديل حساب"؛ يجب أن تعمل عبر jQuery بدون أخطاء.
4. لا يجب أن تظهر رسالة `bootstrap.Modal.getOrCreateInstance` في Console.

## تنفيذ التصحيح النهائي

* إذا وافقت، سأجري تحقق إضافي سريع وأعالج أي سطر متبقّي يسبب أخطاء مباشرة ضمن القالب.

