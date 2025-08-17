// File: static/js/warehouse.js

document.addEventListener('DOMContentLoaded', () => {

  // ---- تنبيهات داخلية (تعديل حسب قوالبك) ----
  function showNotification(message, type = 'info') {
    // type: 'success', 'danger', 'warning', 'info'
    // أنشئ عنصر رسالة أو استعمل عنصر موجود مسبقاً في القالب (يفضل استبداله بمكتبة مثل toastr)
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

  // ---- دالة إرسال نموذج عبر AJAX مع دعم فورم داتا ----
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
        if (reload) {
          setTimeout(() => location.reload(), 1200);
        }
        if (callback) callback(data);
      } else {
        showNotification(`خطأ: ${data.error || JSON.stringify(data.errors)}`, 'danger');
      }
    } catch (err) {
      showNotification('حدث خطأ في الاتصال بالخادم', 'danger');
    }
  }

  // ---- تحديث المخزون (stock-level-form) ----
  document.querySelectorAll('.stock-level-form').forEach(form => {
    form.addEventListener('submit', e => {
      e.preventDefault();
      ajaxFormSubmit(form, 'تم تحديث المخزون بنجاح.');
    });
  });

  // ---- تحويل المنتجات (transfer-form) ----
  const transferForm = document.getElementById('transfer-form');
  if (transferForm) {
    transferForm.addEventListener('submit', e => {
      e.preventDefault();
      ajaxFormSubmit(transferForm, 'تم تسجيل التحويل بنجاح.', true);
    });
  }

  // ---- تبادل المنتجات (exchange-form) ----
  const exchangeForm = document.getElementById('exchange-form');
  if (exchangeForm) {
    exchangeForm.addEventListener('submit', e => {
      e.preventDefault();
      ajaxFormSubmit(exchangeForm, 'تم تسجيل التبادل بنجاح.', true);
    });
  }

  // ---- تحميل مشاركات الشركاء (partner-shares) ----
  async function loadPartnerShares(warehouseId) {
    try {
      const res = await fetch(`/warehouses/${warehouseId}/partner-shares`);
      const data = await res.json();
      if (!data.success) throw new Error('فشل تحميل البيانات');
      const tbody = document.querySelector('#partner-shares-table tbody');
      if (!tbody) return;
      tbody.innerHTML = '';
      data.shares.forEach(s => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${s.product}</td>
          <td>${s.partner}</td>
          <td>${s.share_percentage.toFixed(2)}</td>
          <td>${s.share_amount.toFixed(2)}</td>
          <td>${s.notes || ''}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch {
      showNotification('فشل تحميل بيانات مشاركات الشركاء.', 'danger');
    }
  }

  // ---- تحديث مشاركات الشركاء (partner-shares-form) ----
  const partnerSharesForm = document.getElementById('partner-shares-form');
  if (partnerSharesForm) {
    partnerSharesForm.addEventListener('submit', async e => {
      e.preventDefault();
      const warehouseId = partnerSharesForm.dataset.warehouseId;
      const shares = [];
      partnerSharesForm.querySelectorAll('.share-row').forEach(row => {
        shares.push({
          product_id: row.querySelector('.product-id').value,
          partner_id: row.querySelector('.partner-id').value,
          share_percentage: parseFloat(row.querySelector('.share-percentage').value) || 0,
          share_amount: parseFloat(row.querySelector('.share-amount').value) || 0,
          notes: row.querySelector('.notes').value || ''
        });
      });
      try {
        const res = await fetch(`/warehouses/${warehouseId}/partner-shares`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
          },
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
  }

  // ---- إدارة إضافة/حذف شركاء في نموذج إضافة منتج ----
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

  // ---- إدارة إضافة/حذف تجار التبادل في نموذج إضافة منتج ----
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

  // ---- إضافة أي تفاعلات إضافية حسب الحاجة هنا ----

});
