// static/js/warehouses.js
document.addEventListener('DOMContentLoaded', () => {
  // ========== إشعارات بسيطة ==========
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

  // ===== نماذج AJAX موجودة سابقاً =====
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

  // ===== تحميل/حفظ مشاركات الشركاء في صفحة المستودع =====
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

  // ===== إدارة ديناميكية (شركاء/تجّار) في صفحات أخرى =====
  const partnersContainerLegacy = document.getElementById('partners-container');
  const addPartnerBtnLegacy = document.getElementById('add-partner-btn');
  const partnerTemplateLegacy = document.getElementById('partner-template')?.content;
  if (addPartnerBtnLegacy && partnersContainerLegacy && partnerTemplateLegacy) {
    addPartnerBtnLegacy.addEventListener('click', () => {
      const clone = document.importNode(partnerTemplateLegacy, true);
      partnersContainerLegacy.appendChild(clone);
    });
    partnersContainerLegacy.addEventListener('click', e => {
      if (e.target.classList.contains('remove-partner-btn')) {
        e.target.closest('.partner-entry').remove();
      }
    });
  }

  const vendorsContainerLegacy = document.getElementById('vendors-container');
  const addVendorBtnLegacy = document.getElementById('add-vendor-btn');
  const vendorTemplateLegacy = document.getElementById('vendor-template')?.content;
  if (addVendorBtnLegacy && vendorsContainerLegacy && vendorTemplateLegacy) {
    addVendorBtnLegacy.addEventListener('click', () => {
      const clone = document.importNode(vendorTemplateLegacy, true);
      vendorsContainerLegacy.appendChild(clone);
    });
    vendorsContainerLegacy.addEventListener('click', e => {
      if (e.target.classList.contains('remove-vendor-btn')) {
        e.target.closest('.vendor-entry').remove();
      }
    });
  }

  // ===== Select2 AJAX إن توفر =====
  function initSelect2In(root=document) {
    if (window.jQuery && jQuery.fn.select2) {
      jQuery(root).find('.select2').each(function(){
        const $el = jQuery(this);
        const endpoint = $el.data('url') || $el.attr('data-url'); // AjaxSelectField يضيف data-url
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
                const arr = Array.isArray(data) ? data : (data.results || data.data || []);
                return { results: arr.map(x => ({ id: x.id, text: x.text || x.name || String(x.id) })) };
              }
            }
          });
        } else {
          $el.select2({ width: '100%', allowClear: true, placeholder: 'اختر...' });
        }
      });
    }
  }
  initSelect2In(document);

  // ===== DataTables (اختياري) =====
  if (window.jQuery && jQuery.fn.DataTable) {
    jQuery('.datatable').each(function(){
      jQuery(this).DataTable({
        pageLength: 25,
        order: [],
        language: { url: '//cdn.datatables.net/plug-ins/1.13.6/i18n/ar.json' }
      });
    });
  }

  // ===== تأكيد حذف عام =====
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

  // ====================== صفحة الشحنات ======================
  if (window.__SHIPMENT_PAGE__) {
    const itemsContainer = document.getElementById('items-container');
    const partnersContainer = document.getElementById('partners-container');
    const tplItem = document.getElementById('tpl-item');
    const tplPartner = document.getElementById('tpl-partner');
    const btnAddItem = document.getElementById('btn-add-item');
    const btnAddPartner = document.getElementById('btn-add-partner');
    const barcodeInput = document.getElementById('barcode-input');

    function addItemRow() {
      if (!itemsContainer || !tplItem) return;
      const idx = parseInt(itemsContainer.getAttribute('data-index') || '0', 10);
      let html = tplItem.innerHTML.replaceAll('__index__', idx);
      const wrapper = document.createElement('div');
      wrapper.innerHTML = html.trim();
      const row = wrapper.firstElementChild;
      itemsContainer.appendChild(row);
      itemsContainer.setAttribute('data-index', String(idx + 1));
      initSelect2In(row);
      recalcItemsSummary();
      return row;
    }

    function addPartnerRow() {
      if (!partnersContainer || !tplPartner) return;
      const idx = parseInt(partnersContainer.getAttribute('data-index') || '0', 10);
      let html = tplPartner.innerHTML.replaceAll('__index__', idx);
      const wrapper = document.createElement('div');
      wrapper.innerHTML = html.trim();
      const row = wrapper.firstElementChild;
      partnersContainer.appendChild(row);
      partnersContainer.setAttribute('data-index', String(idx + 1));
      initSelect2In(row);
      return row;
    }

    function recalcItemsSummary() {
      let count = 0, qtySum = 0, costSum = 0;
      itemsContainer?.querySelectorAll('.shipment-item').forEach(item => {
        count++;
        const qty = parseFloat(item.querySelector('.item-qty')?.value || '0') || 0;
        const cost = parseFloat(item.querySelector('.item-cost')?.value || '0') || 0;
        qtySum += qty;
        costSum += (qty * cost);
      });
      const n = (v) => Number(v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
      document.getElementById('items-count')?.innerText = String(count);
      document.getElementById('items-qty-sum')?.innerText = String(qtySum);
      document.getElementById('items-cost-sum')?.innerText = n(costSum);
    }

    // إضافة/حذف بنود
    btnAddItem?.addEventListener('click', () => addItemRow());
    itemsContainer?.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn-remove-item');
      if (!btn) return;
      btn.closest('.shipment-item')?.remove();
      recalcItemsSummary();
    });

    // حساب الإجماليات عند تغيير الكمية/التكلفة
    itemsContainer?.addEventListener('input', (e) => {
      if (e.target.matches('.item-qty') || e.target.matches('.item-cost')) recalcItemsSummary();
    });

    // إضافة/حذف شركاء
    btnAddPartner?.addEventListener('click', () => addPartnerRow());
    partnersContainer?.addEventListener('click', (e) => {
      const btn = e.target.closest('.btn-remove-partner');
      if (!btn) return;
      btn.closest('.shipment-partner')?.remove();
    });

    // سكان باركود/بحث سريع: حط القيمة في أول Select2 للمنتج بالصف الأخير
    barcodeInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        let row = itemsContainer?.querySelector('.shipment-item:last-of-type');
        if (!row) row = addItemRow();
        if (!row) return;
        const $sel = window.jQuery ? window.jQuery(row).find('select[data-url*="api.products"], select.select2') : null;
        if ($sel && $sel.length && $sel.select2) {
          $sel.select2('open');
          const searchInput = document.querySelector('.select2-container--open .select2-search__field');
          if (searchInput) {
            searchInput.value = (barcodeInput.value || '').trim();
            searchInput.dispatchEvent(new Event('input', { bubbles: true }));
          }
        }
        barcodeInput.value = '';
      }
    });

    // تهيئة أولية للإجماليات
    recalcItemsSummary();
  }
});
