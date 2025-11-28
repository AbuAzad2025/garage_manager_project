## ما سنفعله الآن
1. استبدال شريط التبويبات الرئيسي إلى صيغة BS4 باستخدام روابط `<a data-toggle="pill" href="#...">`، مع تحديث الخصائص `role`/`aria-*`.
2. تحويل تبويبات مركز التحكم الفرعية إلى BS4 باستخدام روابط `<a data-toggle="tab" href="#ops-...">`.
3. تعديل المودالات إلى BS4: زر إغلاق `button.close` + `data-dismiss="modal"`، وإزالة أي استعمال لواجهات BS5.
4. تبسيط الجافاسكربت:
   - `getOrCreateModal(el)` تعتمد على jQuery فقط (`.modal('show'/'hide')`).
   - ربط `shown.bs.tab` عبر jQuery لتحميل المحتوى، مع تفعيل يدوي عند الحاجة.
   - تعريف دوال واجهة مطلوبة (`showAddAccountModal`, `showEditAccountModal`, `deleteAcc`, `generateClosingEntries`, `reverseBatch`).
5. إزالة أي تضمين أو استدعاء لـ Bootstrap 5 داخل القالب، والاعتماد على Bootstrap 4 الموجود في `base.html`.
6. التحقق بعد التنفيذ: تشغيل التبويبات والمودالات بدون أخطاء، واختفاء أي رسالة `getOrCreateInstance`.

## ملاحظات تنفيذ
- الملف المستهدف: `templates/security/ledger_control.html`.
- سنحافظ على بنية الكتل Jinja (`extends`, `block security_content`, `block extra_js`).
- لن نلمس بقية القوالب أو الاعتماديات خارج حدود هذا القالب.

## نتيجة متوقعة
- تنقل سلس بين التبويبات الرئيسية والفرعية.
- مودالات "إضافة/تعديل حساب" تعمل وتتوافق مع BS4.
- لا تظهر أخطاء BS5 في الـ Console.

سأبدأ بتنفيذ الخطوات الآن وتحديث القالب بالكامل وفق هذه الخطة.