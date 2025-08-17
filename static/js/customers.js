document.addEventListener('DOMContentLoaded', function () {
  // ---------- أدوات مساعدة ----------
  const qs  = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const isEmail = v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);

  // ---------- 0) مزامنة الهاتف مع الواتساب ----------
  qsa('input[name="phone"]').forEach((phone, i) => {
    const whatsapps = qsa('input[name="whatsapp"]');
    const whatsapp = whatsapps[i];
    if (whatsapp) {
      phone.addEventListener('blur', () => {
        if (!whatsapp.value && phone.value) {
          whatsapp.value = phone.value.trim();
        }
      });
    }
  });

  // ---------- 1) حذف عميل عبر نموذج + مودال ----------
  const deleteForm = qs('#deleteForm');
  const modalEl = qs('#deleteModal');
  const modal = (window.bootstrap && modalEl) ? new bootstrap.Modal(modalEl) : null;
  const confirmBtn = qs('#confirmDelete');

  qsa('.delete-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const urlAttr = btn.getAttribute('data-delete-url');
      const idAttr  = btn.getAttribute('data-id');
      const url = urlAttr || (idAttr ? `/customers/${idAttr}/delete` : '');

      if (deleteForm && url) {
        deleteForm.setAttribute('action', url);
        if (modal) modal.show();
      }
    });
  });

  confirmBtn && confirmBtn.addEventListener('click', () => {
    if (!deleteForm) return;
    const action = deleteForm.getAttribute('action') || '';
    if (!action) return;
    confirmBtn.disabled = true;
    try {
      deleteForm.submit();
    } finally {
      setTimeout(() => { confirmBtn.disabled = false; }, 2000);
    }
  });

  // ---------- 2) البحث المتقدم ----------
  const advForm = qs('#customer-adv-search');
  advForm && advForm.addEventListener('submit', e => {
    e.preventDefault();
    const params = new URLSearchParams(new FormData(advForm)).toString();
    const base = window.location.pathname;
    window.location.href = params ? `${base}?${params}` : base;
  });

  // ---------- 3) إعادة تعيين البحث ----------
  const resetBtn = qs('#reset-adv-filter');
  resetBtn && resetBtn.addEventListener('click', () => {
    window.location.href = window.location.pathname;
  });

  // ---------- 4) تصدير نتائج البحث كـ CSV (إن وُجد زر) ----------
  const exportResultsBtn = qs('#export-results');
  exportResultsBtn && exportResultsBtn.addEventListener('click', () => {
    const params = new URLSearchParams(window.location.search);
    params.set('format', 'csv');
    window.location.href = `${window.location.pathname}?${params}`;
  });

  // ---------- 5) معاينة رسائل واتساب ----------
  const messageType = qs('#message-type');
  if (messageType) {
    const updateMessagePreview = () => {
      const type = messageType.value;
      const header = qs('.card-header h3');
      const customerName = header ? header.textContent.replace('إرسال رسالة واتساب إلى', '').trim() : 'العميل';
      let msg = '';

      if (type === 'balance') {
        const balanceEl = qs('.fw-bold.text-danger, .fw-bold.text-success');
        const balance = balanceEl ? balanceEl.textContent : '0.00';
        msg = `مرحباً ${customerName}،\n\nرصيد حسابك الحالي: ${balance}\n\nشكراً لتعاملك معنا.`;
      } else if (type === 'invoice') {
        const opt = qs('select[name="invoice_id"] option:checked');
        const txt = opt ? opt.textContent : 'فاتورة جديدة';
        msg = `مرحباً ${customerName}،\n\nلديك فاتورة جديدة: ${txt}\n\nيمكنك الاطلاع على التفاصيل من خلال لوحة التحكم.`;
      } else if (type === 'payment') {
        const opt = qs('select[name="payment_id"] option:checked');
        const txt = opt ? opt.textContent : 'دفعة جديدة';
        msg = `مرحباً ${customerName}،\n\nتم استلام دفعة: ${txt}\n\nشكراً لدفعك في الوقت المحدد.`;
      } else if (type === 'custom') {
        const area = qs('textarea[name="custom_message"]');
        const custom = area && area.value ? area.value : '[اكتب رسالتك هنا]';
        msg = `مرحباً ${customerName},\n\n${custom}`;
      }

      const preview = qs('#message-preview');
      if (preview) preview.textContent = msg;
    };

    const toggleSections = () => {
      ['custom-message-section', 'invoice-section', 'payment-section'].forEach(id => {
        const el = qs(`#${id}`);
        if (el) el.classList.add('d-none');
      });
      const sectionMap = { custom: 'custom-message-section', invoice: 'invoice-section', payment: 'payment-section' };
      const secId = sectionMap[messageType.value];
      const secEl = secId ? qs(`#${secId}`) : null;
      if (secEl) secEl.classList.remove('d-none');
      updateMessagePreview();
    };

    messageType.addEventListener('change', toggleSections);
    ['custom_message', 'invoice_id', 'payment_id'].forEach(name => {
      const field = qs(`[name="${name}"]`);
      field && field.addEventListener('input', updateMessagePreview);
      field && field.addEventListener('change', updateMessagePreview);
    });
    toggleSections();
  }

  // ---------- 6) تهيئة جدول العملاء (DataTables) إن وُجدت المكتبة ----------
  const customersTable = qs('#customersTable');
  if (customersTable && window.jQuery && $.fn && $.fn.DataTable) {
    const lastCol = (customersTable.tHead && customersTable.tHead.rows[0])
      ? customersTable.tHead.rows[0].cells.length - 1
      : 8;
    $(customersTable).DataTable({
      language: { url: "/static/datatables/Arabic.json" },
      paging: false,
      searching: false,
      info: false,
      ordering: true,
      order: [[0, 'desc']],
      columnDefs: [{ orderable: false, targets: [lastCol] }]
    });
  }

  // ---------- 7) التحقق من صحة البريد وكلمات المرور في النماذج ----------
  ['#customer-create-form', '#customer-edit-form'].forEach(sel => {
    const form = qs(sel);
    form && form.addEventListener('submit', e => {
      const email = form.querySelector('input[name="email"]');
      const pw1 = form.querySelector('input[name="password"]');
      const pw2 = form.querySelector('input[name="confirm"]');

      if (email && email.value && !isEmail(email.value)) {
        e.preventDefault();
        email.classList.add('is-invalid');
        if (email.nextElementSibling) {
          if (!email.nextElementSibling.classList.contains('invalid-feedback')) {
            email.insertAdjacentHTML('afterend', `<div class="invalid-feedback">يرجى إدخال بريد إلكتروني صالح</div>`);
          }
        } else {
          email.insertAdjacentHTML('afterend', `<div class="invalid-feedback">يرجى إدخال بريد إلكتروني صالح</div>`);
        }
        email.focus();
        return;
      }

      if (pw1 && pw2 && pw1.value !== pw2.value) {
        e.preventDefault();
        pw2.classList.add('is-invalid');
        if (pw2.nextElementSibling) {
          if (!pw2.nextElementSibling.classList.contains('invalid-feedback')) {
            pw2.insertAdjacentHTML('afterend', `<div class="invalid-feedback">كلمة المرور غير متطابقة</div>`);
          }
        } else {
          pw2.insertAdjacentHTML('afterend', `<div class="invalid-feedback">كلمة المرور غير متطابقة</div>`);
        }
        pw2.focus();
      }
    });
  });

  // ---------- 8) التحقق من اختيار عملاء عند تصدير جهات الاتصال ----------
  const exportForm = qs('#export-contacts-form') || qs('form[action*="/customers/export/contacts"]');
  if (exportForm) {
    exportForm.addEventListener('submit', e => {
      const sel = exportForm.querySelector('select[name="customer_ids"]');
      const options = sel ? Array.from(sel.options) : [];
      const selected = options.filter(o => o.selected);
      if (!selected.length) {
        e.preventDefault();
        alert('يرجى اختيار عملاء على الأقل');
      }
    });
  }
});
