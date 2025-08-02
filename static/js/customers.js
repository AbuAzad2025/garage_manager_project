// static/js/customers.js
document.addEventListener('DOMContentLoaded', function() {
  // 1. نسخ رقم الجوال إلى واتساب تلقائيًا في نماذج إنشاء وتعديل العميل
  const phoneInputs = document.querySelectorAll('input[name="phone"]');
  const whatsappInputs = document.querySelectorAll('input[name="whatsapp"]');
  
  phoneInputs.forEach((phoneInput, index) => {
    if (whatsappInputs[index]) {
      phoneInput.addEventListener('blur', function() {
        if (!whatsappInputs[index].value && phoneInput.value) {
          whatsappInputs[index].value = phoneInput.value;
        }
      });
    }
  });

  // 2. حذف العميل مع التأكيد عبر مودال
  const deleteButtons = document.querySelectorAll('.delete-btn');
  const deleteForm = document.getElementById('deleteForm');
  
  if (deleteButtons.length && deleteForm) {
    deleteButtons.forEach(button => {
      button.addEventListener('click', function() {
        const customerId = this.getAttribute('data-id');
        deleteForm.action = `/customers/${customerId}/delete`;
        const modal = new bootstrap.Modal(document.getElementById('deleteModal'));
        modal.show();
      });
    });
  }

  // 3. البحث المتقدم (إرسال النموذج)
  const advSearchForm = document.getElementById('customer-adv-search');
  if (advSearchForm) {
    advSearchForm.addEventListener('submit', function(e) {
      e.preventDefault();
      const formData = new FormData(this);
      const params = new URLSearchParams(formData).toString();
      window.location.href = `${window.location.pathname}?${params}`;
    });
  }

  // 4. تصدير نتائج البحث المتقدم إلى CSV
  const exportBtn = document.getElementById('export-results');
  if (exportBtn) {
    exportBtn.addEventListener('click', function() {
      const params = new URLSearchParams(window.location.search);
      params.set('format', 'csv');
      window.location.href = window.location.pathname + '?' + params.toString();
    });
  }

  // 5. إعادة تعيين نموذج البحث المتقدم
  const resetBtn = document.querySelector('button[type="reset"]');
  if (resetBtn) {
    resetBtn.addEventListener('click', function() {
      window.location.href = window.location.pathname;
    });
  }

  // 6. معاينة رسالة الواتساب الديناميكية
  const messageType = document.getElementById('message-type');
  if (messageType) {
    const customSection = document.getElementById('custom-message-section');
    const invoiceSection = document.getElementById('invoice-section');
    const paymentSection = document.getElementById('payment-section');
    const messagePreview = document.getElementById('message-preview');
    const customerName = document.querySelector('.card-header h3').textContent.replace('إرسال رسالة واتساب إلى', '').trim();
    
    function updateMessageSections() {
      const type = messageType.value;
      customSection.classList.add('d-none');
      invoiceSection.classList.add('d-none');
      paymentSection.classList.add('d-none');
      if (type === 'custom') {
        customSection.classList.remove('d-none');
      } else if (type === 'invoice') {
        invoiceSection.classList.remove('d-none');
      } else if (type === 'payment') {
        paymentSection.classList.remove('d-none');
      }
      updateMessagePreview();
    }
    
    function updateMessagePreview() {
      const type = messageType.value;
      let message = '';
      if (type === 'balance') {
        const balance = document.querySelector('.fw-bold.text-danger, .fw-bold.text-success')?.textContent || '0.00';
        message = `مرحباً ${customerName}،\n\nرصيد حسابك الحالي: ${balance}\n\nشكراً لتعاملك معنا.`;
      } else if (type === 'invoice') {
        const selectedInvoice = document.querySelector('select[name="invoice_id"] option:checked')?.textContent || 'فاتورة جديدة';
        message = `مرحباً ${customerName}،\n\nلديك فاتورة جديدة: ${selectedInvoice}\n\nيمكنك الاطلاع على التفاصيل من خلال لوحة التحكم.`;
      } else if (type === 'payment') {
        const selectedPayment = document.querySelector('select[name="payment_id"] option:checked')?.textContent || 'دفعة جديدة';
        message = `مرحباً ${customerName}،\n\nتم استلام دفعة: ${selectedPayment}\n\nشكراً لدفعك في الوقت المحدد.`;
      } else if (type === 'custom') {
        const customMessage = document.querySelector('textarea[name="custom_message"]').value || '[اكتب رسالتك هنا]';
        message = `مرحباً ${customerName},\n\n${customMessage}`;
      }
      messagePreview.textContent = message;
    }
    
    messageType.addEventListener('change', updateMessageSections);
    document.querySelector('textarea[name="custom_message"]')?.addEventListener('input', updateMessagePreview);
    document.querySelector('select[name="invoice_id"]')?.addEventListener('change', updateMessagePreview);
    document.querySelector('select[name="payment_id"]')?.addEventListener('change', updateMessagePreview);
    updateMessageSections();
  }

  // 7. تهيئة DataTable لقائمة العملاء
  const customersTable = document.getElementById('customersTable');
  if (customersTable) {
    $(customersTable).DataTable({
      language: {
        url: "/static/datatables/Arabic.json"
      },
      paging: false,
      searching: false,
      info: false,
      ordering: true,
      order: [[0, 'desc']],
      columnDefs: [
        { orderable: false, targets: [7] }
      ]
    });
  }

  // 8. التحقق من صحة البريد الإلكتروني عند الإرسال فقط
  const form = document.getElementById('customer-create-form');
  if (form) {
    form.addEventListener('submit', function(e) {
      const email = this.querySelector('input[name="email"]');
      if (email && email.value && !email.value.includes('@')) {
        e.preventDefault();
        // عرض رسالة خطأ تحت الحقل
        if (!email.classList.contains('is-invalid')) {
          email.classList.add('is-invalid');
          const feedback = document.createElement('div');
          feedback.className = 'invalid-feedback';
          feedback.textContent = 'يرجى إدخال بريد إلكتروني صالح';
          email.after(feedback);
        }
        email.focus();
        return;
      }
      // إضافة تحققات إضافية هنا إذا لزم
    });
  }

  // 9. التحقق من تطابق كلمة المرور عند الإرسال
  if (form) {
    const passwordInput = form.querySelector('input[name="password"]');
    const confirmInput = form.querySelector('input[name="confirm"]');
    if (passwordInput && confirmInput) {
      form.addEventListener('submit', function(e) {
        if (passwordInput.value !== confirmInput.value) {
          e.preventDefault();
          confirmInput.classList.add('is-invalid');
          if (!confirmInput.nextElementSibling?.classList.contains('invalid-feedback')) {
            const feedback = document.createElement('div');
            feedback.className = 'invalid-feedback';
            feedback.textContent = 'كلمة المرور غير متطابقة';
            confirmInput.after(feedback);
          }
          passwordInput.focus();
        }
      });
    }
  }

  // 10. تصدير جهات الاتصال بتنسيقات مختلفة
  const exportFormatSelect = document.querySelector('select[name="format"]');
  const exportSelectedBtn = document.querySelector('button[type="submit"]');
  if (exportFormatSelect && exportSelectedBtn) {
    exportSelectedBtn.addEventListener('click', function(e) {
      const format = exportFormatSelect.value;
      const selectedCustomers = Array.from(document.querySelectorAll('select[name="customer_ids"] option:checked'))
        .map(option => option.value);
      if (selectedCustomers.length === 0) {
        e.preventDefault();
        alert('يرجى اختيار عملاء على الأقل');
      } else {
        console.log(`Exporting ${selectedCustomers.length} customers in ${format} format`);
      }
    });
  }
});
