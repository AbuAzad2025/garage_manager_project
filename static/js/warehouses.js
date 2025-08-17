document.addEventListener('DOMContentLoaded', () => {
  function showNotification(message, type = 'info') {
    let container = document.getElementById('notification-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'notification-container';
      container.style.position = 'fixed';
      container.style.top = '20px';
      container.style.right = '20px';
      container.style.zIndex = '1050';
      document.body.appendChild(container);
    }
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.role = 'alert';
    alert.innerHTML = `
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    container.appendChild(alert);
    setTimeout(() => {
      alert.classList.remove('show');
      alert.classList.add('hide');
      setTimeout(() => alert.remove(), 500);
    }, 5000);
  }

  async function ajaxFormSubmit(form, successMessage, reload = false, callback = null) {
    try {
      const url = form.action;
      const method = form.method || 'POST';
      const formData = new FormData(form);
      const headers = { 'X-Requested-With': 'XMLHttpRequest' };
      const response = await fetch(url, { method, body: formData, headers });
      const data = await response.json();
      if (data.success) {
        showNotification(successMessage, 'success');
        if (reload) setTimeout(() => location.reload(), 1200);
        if (callback) callback(data);
      } else {
        showNotification(`خطأ: ${data.error || JSON.stringify(data.errors)}`, 'danger');
      }
    } catch (err) {
      showNotification('حدث خطأ في الاتصال بالخادم', 'danger');
    }
  }

  // ===== نماذج AJAX الموجودة عندك =====
  document.querySelectorAll('.stock-level-form').forEach(form => {
    form.addEventListener('submit', e => {
      e.preventDefault();
      ajaxFormSubmit(form, 'تم تحديث المخزون بنجاح.');
    });
  });

  const transferForm = document.getElementById('transfer-form');
  if (transferForm) {
    transferForm.addEventListener('submit', e => {
      e.preventDefault();
      ajaxFormSubmit(transferForm, 'تم تسجيل التحويل بنجاح.', true);
    });
  }

  const exchangeForm = document.getElementById('exchange-form');
  if (exchangeForm) {
    exchangeForm.addEventListener('submit', e => {
      e.preventDefault();
      ajaxFormSubmit(exchangeForm, 'تم تسجيل التبادل بنجاح.', true);
    });
  }

  // ===== تحميل/حفظ مشاركات الشركاء (كما هو عندك) =====
  async function loadPartnerShares(warehouseId) {
    try {
      const res = await fetch(`/warehouses/${warehouseId}/partner-shares`);
      const data = await res.json();
      if (!data.success) throw new Error('fail');
      const tbody = document.querySelector('#partner-shares-table tbody');
      if (!tbody) return;
      tbody.innerHTML = '';
      data.shares.forEach(s => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${s.product || ''}</td>
          <td>${s.partner || ''}</td>
          <td>${Number(s.share_percentage || 0).toFixed(2)}</td>
          <td>${Number(s.share_amount || 0).toFixed(2)}</td>
          <td>${s.notes || ''}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch {
      showNotification('فشل تحميل بيانات مشاركات الشركاء.', 'danger');
    }
  }

  const partnerSharesForm = document.getElementById('partner-shares-form');
  if (partnerSharesForm) {
    partnerSharesForm.addEventListener('submit', async e => {
      e.preventDefault();
      const warehouseId = partnerSharesForm.dataset.warehouseId;
      const shares = [];
      partnerSharesForm.querySelectorAll('.share-row').forEach(row => {
        shares.push({
          product_id: parseInt(row.querySelector('.product-id').value) || null,
          partner_id: parseInt(row.querySelector('.partner-id').value) || null,
          share_percentage: parseFloat(row.querySelector('.share-percentage').value) || 0,
          share_amount: parseFloat(row.querySelector('.share-amount').value) || 0,
          notes: row.querySelector('.notes').value || ''
        });
      });
      try {
        const res = await fetch(`/warehouses/${warehouseId}/partner-shares`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({ shares })
        });
        const data = await res.json();
        if (data.success) {
          showNotification('تم تحديث مشاركات الشركاء بنجاح.', 'success');
          loadPartnerShares(warehouseId);
        } else {
          showNotification(`خطأ في التحديث: ${data.error}`, 'danger');
        }
      } catch {
        showNotification('حدث خطأ في الاتصال.', 'danger');
      }
    });
    const table = document.getElementById('partner-shares-table');
    if (table) loadPartnerShares(partnerSharesForm.dataset.warehouseId);
  }

  // ===== إدارة ديناميكية لشركاء/تجّار (كما هو عندك) =====
  const partnersContainer = document.getElementById('partners-container');
  const addPartnerBtn = document.getElementById('add-partner-btn');
  const partnerTemplate = document.getElementById('partner-template')?.content;
  if (addPartnerBtn && partnersContainer && partnerTemplate) {
    addPartnerBtn.addEventListener('click', () => {
      const clone = document.importNode(partnerTemplate, true);
      partnersContainer.appendChild(clone);
    });
    partnersContainer.addEventListener('click', e => {
      if (e.target.classList.contains('remove-partner-btn')) {
        e.target.closest('.partner-entry').remove();
      }
    });
  }

  const vendorsContainer = document.getElementById('vendors-container');
  const addVendorBtn = document.getElementById('add-vendor-btn');
  const vendorTemplate = document.getElementById('vendor-template')?.content;
  if (addVendorBtn && vendorsContainer && vendorTemplate) {
    addVendorBtn.addEventListener('click', () => {
      const clone = document.importNode(vendorTemplate, true);
      vendorsContainer.appendChild(clone);
    });
    vendorsContainer.addEventListener('click', e => {
      if (e.target.classList.contains('remove-vendor-btn')) {
        e.target.closest('.vendor-entry').remove();
      }
    });
  }

  // ===== (جديد) تفعيل Select2 بالـ AJAX إذا متوفر =====
  if (window.jQuery && jQuery.fn.select2) {
    // العادي
    jQuery('.select2').each(function(){
      const $el = jQuery(this);
      const endpoint = $el.data('endpoint');
      if (endpoint) {
        $el.select2({
          width: '100%',
          allowClear: true,
          placeholder: 'اختر...',
          ajax: {
            delay: 250,
            url: endpoint,
            data: params => ({ q: params.term || '', limit: 20 }),
            processResults: (data) => {
              // يدعم {results:[{id,text}]} أو Array مباشرة أو {data:[...]}
              const arr = Array.isArray(data) ? data : (data.results || data.data || []);
              return { results: arr.map(x => ({ id: x.id, text: x.text || x.name || String(x.id) })) };
            }
          }
        });
      } else {
        $el.select2({ width: '100%' });
      }
    });
  }

  // ===== (جديد) تهيئة DataTables عامة اختيارية =====
  if (window.jQuery && jQuery.fn.DataTable) {
    jQuery('.datatable').each(function(){
      jQuery(this).DataTable({
        pageLength: 25,
        order: [],
        language: { url: '//cdn.datatables.net/plug-ins/1.13.6/i18n/ar.json' }
      });
    });
  }

  // ===== (جديد) تأكيد حذف عام للأزرار .btn-delete =====
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-delete');
    if (!btn) return;
    e.preventDefault();
    const form = btn.closest('form');
    if (!form) return;
    if (window.Swal) {
      Swal.fire({
        icon: 'warning',
        title: 'تأكيد الحذف',
        text: 'سيتم حذف السجل نهائيًا',
        showCancelButton: true,
        confirmButtonText: 'حذف'
      }).then(r => { if (r.isConfirmed) form.submit(); });
    } else {
      if (confirm('تأكيد الحذف؟')) form.submit();
    }
  });
});
