/**
 * وظائف الأرشفة الموحدة
 * هذا الملف يحتوي على جميع وظائف الأرشفة المستخدمة في النظام
 */

// أرشفة العميل
function archiveCustomer(customerId) {
    console.log('🔍 [JS] بدء أرشفة العميل رقم:', customerId);
    console.log('🔍 [JS] نوع customerId:', typeof customerId);
    
    const reason = prompt('أدخل سبب أرشفة هذا العميل:');
    if (!reason) {
        console.log('❌ [JS] تم إلغاء الأرشفة - لا يوجد سبب');
        return;
    }
    
    console.log('✅ [JS] تم إدخال السبب:', reason);
    
    if (confirm('هل أنت متأكد من أرشفة هذا العميل؟')) {
        console.log('✅ [JS] تأكيد الأرشفة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/customers/archive/${customerId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        console.log('🔐 [JS] CSRF Token:', csrfToken.value ? 'موجود' : 'غير موجود');
        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);
        
        console.log('📋 [JS] محتويات النموذج:');
        console.log('  - Method:', form.method);
        console.log('  - Action:', form.action);
        console.log('  - CSRF Token:', csrfToken.value);
        console.log('  - Reason:', reasonInput.value);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {
            console.log('📡 [JS] تم إرسال النموذج بنجاح');
        });
        
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الأرشفة من قبل المستخدم');
    }
}

// أرشفة المبيعة
function archiveSale(saleId) {
    console.log('🔍 [JS] بدء أرشفة المبيعة رقم:', saleId);
    console.log('🔍 [JS] نوع saleId:', typeof saleId);
    
    const reason = prompt('أدخل سبب أرشفة هذه المبيعة:');
    if (!reason) {
        console.log('❌ [JS] تم إلغاء الأرشفة - لا يوجد سبب');
        return;
    }
    
    console.log('✅ [JS] تم إدخال السبب:', reason);
    
    if (confirm('هل أنت متأكد من أرشفة هذه المبيعة؟')) {
        console.log('✅ [JS] تأكيد الأرشفة - إنشاء النموذج');
        // إظهار رسالة تحميل
        const loadingMsg = document.createElement('div');
        loadingMsg.innerHTML = '<div class="alert alert-info">جاري أرشفة المبيعة...</div>';
        document.body.appendChild(loadingMsg);
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/sales/archive/${saleId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        console.log('🔐 [JS] CSRF Token:', csrfToken.value ? 'موجود' : 'غير موجود');
        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);
        
        console.log('📋 [JS] محتويات النموذج:');
        console.log('  - Method:', form.method);
        console.log('  - Action:', form.action);
        console.log('  - CSRF Token:', csrfToken.value);
        console.log('  - Reason:', reasonInput.value);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {
            console.log('📡 [JS] تم إرسال النموذج بنجاح');
        });
        
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الأرشفة من قبل المستخدم');
    }
}

// أرشفة النفقة
function archiveExpense(expenseId) {
    console.log('🔍 [JS] بدء أرشفة النفقة رقم:', expenseId);
    console.log('🔍 [JS] نوع expenseId:', typeof expenseId);
    
    const reason = prompt('أدخل سبب أرشفة هذه النفقة:');
    if (!reason) {
        console.log('❌ [JS] تم إلغاء الأرشفة - لا يوجد سبب');
        return;
    }
    
    console.log('✅ [JS] تم إدخال السبب:', reason);
    
    if (confirm('هل أنت متأكد من أرشفة هذه النفقة؟')) {
        console.log('✅ [JS] تأكيد الأرشفة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/expenses/archive/${expenseId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        console.log('🔐 [JS] CSRF Token:', csrfToken.value ? 'موجود' : 'غير موجود');
        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);
        
        console.log('📋 [JS] محتويات النموذج:');
        console.log('  - Method:', form.method);
        console.log('  - Action:', form.action);
        console.log('  - CSRF Token:', csrfToken.value);
        console.log('  - Reason:', reasonInput.value);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {
            console.log('📡 [JS] تم إرسال النموذج بنجاح');
        });
        
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الأرشفة من قبل المستخدم');
    }
}

// أرشفة طلب الصيانة
function archiveService(serviceId) {
    console.log('🔍 [JS] بدء أرشفة طلب الصيانة رقم:', serviceId);
    console.log('🔍 [JS] نوع serviceId:', typeof serviceId);
    
    const reason = prompt('أدخل سبب أرشفة هذا طلب الصيانة:');
    if (!reason) {
        console.log('❌ [JS] تم إلغاء الأرشفة - لا يوجد سبب');
        return;
    }
    
    console.log('✅ [JS] تم إدخال السبب:', reason);
    
    if (confirm('هل أنت متأكد من أرشفة هذا طلب الصيانة؟')) {
        console.log('✅ [JS] تأكيد الأرشفة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/service/archive/${serviceId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        console.log('🔐 [JS] CSRF Token:', csrfToken.value ? 'موجود' : 'غير موجود');
        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);
        
        console.log('📋 [JS] محتويات النموذج:');
        console.log('  - Method:', form.method);
        console.log('  - Action:', form.action);
        console.log('  - CSRF Token:', csrfToken.value);
        console.log('  - Reason:', reasonInput.value);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {
            console.log('📡 [JS] تم إرسال النموذج بنجاح');
        });
        
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الأرشفة من قبل المستخدم');
    }
}

// أرشفة المورد
function archiveSupplier(supplierId) {
    console.log('🔍 [JS] بدء أرشفة المورد رقم:', supplierId);
    console.log('🔍 [JS] نوع supplierId:', typeof supplierId);
    
    const reason = prompt('أدخل سبب أرشفة هذا المورد:');
    if (!reason) {
        console.log('❌ [JS] تم إلغاء الأرشفة - لا يوجد سبب');
        return;
    }
    
    console.log('✅ [JS] تم إدخال السبب:', reason);
    
    if (confirm('هل أنت متأكد من أرشفة هذا المورد؟')) {
        console.log('✅ [JS] تأكيد الأرشفة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/vendors/suppliers/archive/${supplierId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        console.log('🔐 [JS] CSRF Token:', csrfToken.value ? 'موجود' : 'غير موجود');
        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);
        
        console.log('📋 [JS] محتويات النموذج:');
        console.log('  - Method:', form.method);
        console.log('  - Action:', form.action);
        console.log('  - CSRF Token:', csrfToken.value);
        console.log('  - Reason:', reasonInput.value);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {
            console.log('📡 [JS] تم إرسال النموذج بنجاح');
        });
        
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الأرشفة من قبل المستخدم');
    }
}

// أرشفة الشريك
function archivePartner(partnerId) {
    console.log('🔍 [JS] بدء أرشفة الشريك رقم:', partnerId);
    console.log('🔍 [JS] نوع partnerId:', typeof partnerId);
    
    const reason = prompt('أدخل سبب أرشفة هذا الشريك:');
    if (!reason) {
        console.log('❌ [JS] تم إلغاء الأرشفة - لا يوجد سبب');
        return;
    }
    
    console.log('✅ [JS] تم إدخال السبب:', reason);
    
    if (confirm('هل أنت متأكد من أرشفة هذا الشريك؟')) {
        console.log('✅ [JS] تأكيد الأرشفة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/vendors/partners/archive/${partnerId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        console.log('🔐 [JS] CSRF Token:', csrfToken.value ? 'موجود' : 'غير موجود');
        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);
        
        console.log('📋 [JS] محتويات النموذج:');
        console.log('  - Method:', form.method);
        console.log('  - Action:', form.action);
        console.log('  - CSRF Token:', csrfToken.value);
        console.log('  - Reason:', reasonInput.value);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        
        // إضافة event listener لمراقبة إرسال النموذج
        form.addEventListener('submit', function(e) {
            console.log('📡 [JS] تم إرسال النموذج بنجاح');
        });
        
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الأرشفة من قبل المستخدم');
    }
}

// وظيفة مساعدة للحصول على CSRF token
function getCSRFToken() {
    console.log('🔐 [CSRF] البحث عن CSRF token...');
    
    // محاولة الحصول على الـ token من meta tag
    const metaToken = document.querySelector('meta[name="csrf-token"]')?.content;
    if (metaToken) {
        console.log('✅ [CSRF] تم العثور على token من meta tag:', metaToken.substring(0, 10) + '...');
        return metaToken;
    }
    
    // محاولة الحصول من hidden input في النموذج
    const hiddenInput = document.querySelector('input[name="csrf_token"]');
    if (hiddenInput) {
        console.log('✅ [CSRF] تم العثور على token من hidden input:', hiddenInput.value.substring(0, 10) + '...');
        return hiddenInput.value;
    }
    
    // إذا لم يتم العثور على token، إرجاع قيمة افتراضية
    console.warn('⚠️ [CSRF] لم يتم العثور على CSRF token');
    console.log('🔍 [CSRF] فحص meta tags:', document.querySelectorAll('meta[name="csrf-token"]'));
    console.log('🔍 [CSRF] فحص hidden inputs:', document.querySelectorAll('input[name="csrf_token"]'));
    return '';
}

// إضافة event listeners عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    console.log('📋 [DOM] تم تحميل وظائف الأرشفة بنجاح');
    
    // فحص CSRF token
    const csrfToken = getCSRFToken();
    console.log('🔐 [DOM] CSRF Token متاح:', csrfToken ? 'نعم' : 'لا');
    
    // إضافة console logs للأزرار
    const archiveButtons = document.querySelectorAll('button[onclick*="archive"]');
    console.log('🔘 [DOM] عدد أزرار الأرشفة الموجودة:', archiveButtons.length);
    archiveButtons.forEach((button, index) => {
        console.log(`🔘 [DOM] زر أرشفة ${index + 1}:`, button);
        console.log(`🔘 [DOM] onclick:`, button.getAttribute('onclick'));
    });
    
    // فحص أزرار أرشفة طلبات الصيانة تحديداً
    const serviceArchiveButtons = document.querySelectorAll('button[onclick*="archiveService"]');
    console.log('🔧 [DOM] عدد أزرار أرشفة طلبات الصيانة:', serviceArchiveButtons.length);
    serviceArchiveButtons.forEach((button, index) => {
        console.log(`🔧 [DOM] زر أرشفة صيانة ${index + 1}:`, button);
    });
    
    // فحص أزرار أرشفة العملاء
    const customerArchiveButtons = document.querySelectorAll('button[onclick*="archiveCustomer"]');
    console.log('👥 [DOM] عدد أزرار أرشفة العملاء:', customerArchiveButtons.length);
    customerArchiveButtons.forEach((button, index) => {
        console.log(`👥 [DOM] زر أرشفة عميل ${index + 1}:`, button);
    });
    
    // فحص أزرار أرشفة المبيعات
    const saleArchiveButtons = document.querySelectorAll('button[onclick*="archiveSale"]');
    console.log('💰 [DOM] عدد أزرار أرشفة المبيعات:', saleArchiveButtons.length);
    saleArchiveButtons.forEach((button, index) => {
        console.log(`💰 [DOM] زر أرشفة مبيعة ${index + 1}:`, button);
    });
    
    // فحص أزرار أرشفة النفقات
    const expenseArchiveButtons = document.querySelectorAll('button[onclick*="archiveExpense"]');
    console.log('💸 [DOM] عدد أزرار أرشفة النفقات:', expenseArchiveButtons.length);
    expenseArchiveButtons.forEach((button, index) => {
        console.log(`💸 [DOM] زر أرشفة نفقة ${index + 1}:`, button);
    });
    
    // فحص أزرار أرشفة الموردين
    const supplierArchiveButtons = document.querySelectorAll('button[onclick*="archiveSupplier"]');
    console.log('🏭 [DOM] عدد أزرار أرشفة الموردين:', supplierArchiveButtons.length);
    supplierArchiveButtons.forEach((button, index) => {
        console.log(`🏭 [DOM] زر أرشفة مورد ${index + 1}:`, button);
    });
    
    // فحص أزرار أرشفة الشركاء
    const partnerArchiveButtons = document.querySelectorAll('button[onclick*="archivePartner"]');
    console.log('🤝 [DOM] عدد أزرار أرشفة الشركاء:', partnerArchiveButtons.length);
    partnerArchiveButtons.forEach((button, index) => {
        console.log(`🤝 [DOM] زر أرشفة شريك ${index + 1}:`, button);
    });
});

// أرشفة الدفعة
function archivePayment(paymentId) {
    console.log('🔍 [JS] بدء أرشفة الدفعة رقم:', paymentId);
    console.log('🔍 [JS] نوع paymentId:', typeof paymentId);
    
    const reason = prompt('أدخل سبب أرشفة هذه الدفعة:');
    if (!reason) {
        console.log('❌ [JS] تم إلغاء الأرشفة - لا يوجد سبب');
        return;
    }
    
    console.log('✅ [JS] تم إدخال السبب:', reason);
    
    if (confirm('هل أنت متأكد من أرشفة هذه الدفعة؟')) {
        console.log('✅ [JS] تأكيد الأرشفة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/payments/archive/${paymentId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        console.log('🔐 [JS] CSRF Token:', csrfToken.value ? 'موجود' : 'غير موجود');
        form.appendChild(csrfToken);
        
        const reasonInput = document.createElement('input');
        reasonInput.type = 'hidden';
        reasonInput.name = 'reason';
        reasonInput.value = reason;
        form.appendChild(reasonInput);
        
        console.log('📋 [JS] محتويات النموذج:');
        console.log('  - Method:', form.method);
        console.log('  - Action:', form.action);
        console.log('  - CSRF Token:', csrfToken.value);
        console.log('  - Reason:', reasonInput.value);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        
        form.addEventListener('submit', function(e) {
            console.log('📡 [JS] تم إرسال النموذج بنجاح');
        });
        
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الأرشفة من قبل المستخدم');
    }
}

// ===== وظائف الاستعادة =====

// استعادة العميل
function restoreCustomer(customerId) {
    console.log('🔍 [JS] بدء استعادة العميل رقم:', customerId);
    
    if (confirm('هل أنت متأكد من استعادة هذا العميل؟')) {
        console.log('✅ [JS] تأكيد الاستعادة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/customers/restore/${customerId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الاستعادة من قبل المستخدم');
    }
}

// استعادة المبيعة
function restoreSale(saleId) {
    console.log('🔍 [JS] بدء استعادة المبيعة رقم:', saleId);
    
    if (confirm('هل أنت متأكد من استعادة هذه المبيعة؟')) {
        console.log('✅ [JS] تأكيد الاستعادة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/sales/restore/${saleId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الاستعادة من قبل المستخدم');
    }
}

// استعادة النفقة
function restoreExpense(expenseId) {
    console.log('🔍 [JS] بدء استعادة النفقة رقم:', expenseId);
    
    if (confirm('هل أنت متأكد من استعادة هذه النفقة؟')) {
        console.log('✅ [JS] تأكيد الاستعادة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/expenses/restore/${expenseId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الاستعادة من قبل المستخدم');
    }
}

// استعادة طلب الصيانة
function restoreService(serviceId) {
    console.log('🔍 [JS] بدء استعادة طلب الصيانة رقم:', serviceId);
    
    if (confirm('هل أنت متأكد من استعادة هذا طلب الصيانة؟')) {
        console.log('✅ [JS] تأكيد الاستعادة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/service/restore/${serviceId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الاستعادة من قبل المستخدم');
    }
}

// استعادة المورد
function restoreSupplier(supplierId) {
    console.log('🔍 [JS] بدء استعادة المورد رقم:', supplierId);
    
    if (confirm('هل أنت متأكد من استعادة هذا المورد؟')) {
        console.log('✅ [JS] تأكيد الاستعادة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/vendors/suppliers/restore/${supplierId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الاستعادة من قبل المستخدم');
    }
}

// استعادة الشريك
function restorePartner(partnerId) {
    console.log('🔍 [JS] بدء استعادة الشريك رقم:', partnerId);
    
    if (confirm('هل أنت متأكد من استعادة هذا الشريك؟')) {
        console.log('✅ [JS] تأكيد الاستعادة - إنشاء النموذج');
        
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = `/vendors/partners/restore/${partnerId}`;
        console.log('📤 [JS] إرسال الطلب إلى:', form.action);
        
        const csrfToken = document.createElement('input');
        csrfToken.type = 'hidden';
        csrfToken.name = 'csrf_token';
        csrfToken.value = getCSRFToken();
        form.appendChild(csrfToken);
        
        document.body.appendChild(form);
        console.log('🚀 [JS] إرسال النموذج...');
        form.submit();
    } else {
        console.log('❌ [JS] تم إلغاء الاستعادة من قبل المستخدم');
    }
}
