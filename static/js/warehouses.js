if (window.__WAREHOUSES_INIT__) {
  console.log("warehouses.js already loaded, skipping...");
} 
window.__WAREHOUSES_INIT__ = true;
document.addEventListener('DOMContentLoaded', () => {
  function showNotification(message, type = 'info') {
    let c = document.getElementById('notification-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'notification-container';
      c.style.position = 'fixed';
      c.style.top = '20px';
      c.style.right = '20px';
      c.style.zIndex = '2000';
      document.body.appendChild(c);
    }
    const el = document.createElement('div');
    el.className = `alert alert-${type} alert-dismissible fade show shadow-sm mb-2`;
    el.role = 'alert';
    el.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
    c.appendChild(el);
    setTimeout(() => {
      if (!el.parentNode) return;
      el.classList.remove('show');
      setTimeout(() => el.remove(), 300);
    }, 5000);
  }

  async function ajaxFormSubmit(form, okMsg, reload = false, cb = null) {
    const submitBtn = form.querySelector('[type="submit"]');
    const prevDisabled = submitBtn?.disabled;
    if (submitBtn) submitBtn.disabled = true;
    try {
      const url = form.dataset.url || form.getAttribute('action') || form.action || window.location.href;
      const method = (form.getAttribute('method') || 'POST').toUpperCase();
      const fd = new FormData(form);
      const res = await fetch(url, { method, body: fd, headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      const ct = res.headers.get('content-type') || '';
      const data = ct.includes('application/json') ? await res.json() : { success: res.ok };
      if (data.success || res.ok) {
        showNotification(okMsg || 'تم التنفيذ بنجاح.', 'success');
        if (cb) cb(data);
        if (reload) setTimeout(() => location.reload(), 900);
      } else {
        const err = data.error || data.message || JSON.stringify(data.errors || {});
        showNotification(`خطأ: ${err}`, 'danger');
      }
      return data;
    } catch {
      showNotification('تعذر الاتصال بالخادم.', 'danger');
      return { success: false };
    } finally {
      if (submitBtn) submitBtn.disabled = prevDisabled ?? false;
    }
  }

  document.querySelectorAll('form[data-ajax="1"]').forEach(f => {
    f.addEventListener('submit', e => {
      e.preventDefault();
      ajaxFormSubmit(f, f.dataset.ok || 'تم الحفظ بنجاح.', f.dataset.reload === '1');
    });
  });

  document.querySelectorAll('.stock-level-form').forEach(f => {
    f.addEventListener('submit', e => {
      e.preventDefault();
      ajaxFormSubmit(f, 'تم تحديث المخزون بنجاح.');
    });
  });

  const transferForm = document.getElementById('transfer-form');
  if (transferForm) {
    transferForm.addEventListener('submit', e => {
      e.preventDefault();
      ajaxFormSubmit(transferForm, 'تم تسجيل التحويل.', true);
    });
  }

  const exchangeForm = document.getElementById('exchange-form');
  if (exchangeForm) {
    exchangeForm.addEventListener('submit', e => {
      e.preventDefault();
      ajaxFormSubmit(exchangeForm, 'تم تسجيل حركة التبادل.', true);
    });
  }

  async function loadPartnerShares(warehouseId) {
    try {
      const res = await fetch(`/warehouses/${warehouseId}/partner-shares`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      const data = await res.json();
      if (!data.success) throw 0;
      const tbody = document.querySelector('#partner-shares-table tbody');
      if (!tbody) return;
      tbody.innerHTML = '';
      (data.shares || []).forEach(s => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${s.product || ''}</td>
          <td>${s.partner || ''}</td>
          <td class="text-center">${Number(s.share_percentage || 0).toFixed(2)}</td>
          <td class="text-end">${Number(s.share_amount || 0).toFixed(2)}</td>
          <td>${s.notes || ''}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch {
      showNotification('فشل تحميل بيانات حصص الشركاء.', 'danger');
    }
  }

  const partnerSharesForm = document.getElementById('partner-shares-form');
  if (partnerSharesForm) {
    partnerSharesForm.addEventListener('submit', async e => {
      e.preventDefault();
      const wid = partnerSharesForm.dataset.warehouseId;
      const rows = partnerSharesForm.querySelectorAll('.share-row');
      const shares = [];
      rows.forEach(r => {
        shares.push({
          product_id: parseInt(r.querySelector('.product-id')?.value || '0', 10) || null,
          partner_id: parseInt(r.querySelector('.partner-id')?.value || '0', 10) || null,
          share_percentage: parseFloat(r.querySelector('.share-percentage')?.value || '0') || 0,
          share_amount: parseFloat(r.querySelector('.share-amount')?.value || '0') || 0,
          notes: r.querySelector('.notes')?.value || ''
        });
      });
      try {
        const res = await fetch(`/warehouses/${wid}/partner-shares`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({ shares })
        });
        const data = await res.json();
        if (data.success) {
          showNotification('تم تحديث الحصص.', 'success');
          loadPartnerShares(wid);
        } else {
          showNotification(`خطأ: ${data.error || 'تعذر التحديث'}`, 'danger');
        }
      } catch {
        showNotification('تعذر الاتصال أثناء تحديث الحصص.', 'danger');
      }
    });
    const tbl = document.getElementById('partner-shares-table');
    if (tbl) loadPartnerShares(partnerSharesForm.dataset.warehouseId);
  }

  function initSelect2In(root = document) {
    if (!(window.jQuery && jQuery.fn.select2)) return;
    jQuery(root).find('.select2').each(function () {
      const $el = jQuery(this);
      if ($el.data('select2')) return;
      const endpoint = $el.data('url') || $el.attr('data-url') || $el.data('endpoint');
      const opts = {
        width: '100%',
        dir: 'rtl',
        theme: 'bootstrap4',
        allowClear: true,
        placeholder: $el.attr('placeholder') || $el.data('placeholder') || 'اختر...'
      };
      if (endpoint) {
        opts.ajax = {
          delay: 250,
          url: endpoint,
          data: params => ({ q: params.term || '', limit: 20 }),
          processResults: (data) => {
            const arr = Array.isArray(data) ? data : (data.results || data.data || []);
            return { results: arr.map(x => ({ id: x.id, text: x.text || x.name || String(x.id) })) };
          }
        };
      }
      $el.select2(opts);
    });
  }
  initSelect2In(document);

  if (window.jQuery && jQuery.fn.DataTable) {
    jQuery.fn.dataTable.ext.errMode = 'none';
    jQuery('.datatable').each(function () {
      const $t = jQuery(this);
      if ($t.hasClass('dt-initialized')) return;
      $t.addClass('dt-initialized').DataTable({
        pageLength: 25,
        order: [],
        responsive: true,
        autoWidth: false,
        language: { url: '//cdn.datatables.net/plug-ins/1.13.6/i18n/ar.json' }
      }).on('error.dt', () => showNotification('حدثت مشكلة أثناء تحميل الجدول.', 'danger'));
    });
  }

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-delete');
    if (!btn) return;
    e.preventDefault();
    const form = btn.closest('form');
    if (!form) return;
    if (window.Swal && Swal.fire) {
      Swal.fire({
        icon: 'warning',
        title: 'تأكيد الحذف',
        html: 'سيتم حذف السجل نهائيًا',
        showCancelButton: true,
        confirmButtonText: 'حذف',
        cancelButtonText: 'إلغاء',
        reverseButtons: true
      }).then(r => { if (r.isConfirmed) form.submit(); });
    } else if (confirm('تأكيد الحذف؟')) form.submit();
  });

  (function () {
    const form = document.getElementById('add-product-form');
    if (!form) return;
    const wtype = (form.dataset.wtype || '').toUpperCase();
    const pSec = document.getElementById('partner-section');
    const eSec = document.getElementById('exchange-section');
    if (wtype === 'PARTNER' && pSec) pSec.classList.remove('d-none');
    if (wtype === 'EXCHANGE' && eSec) eSec.classList.remove('d-none');

    const partnersWrap = document.getElementById('partners-container');
    const addPartnerBtn = document.getElementById('add-partner-btn');
    const partnerTpl = document.getElementById('partner-template')?.content;
    if (addPartnerBtn && partnersWrap && partnerTpl) {
      addPartnerBtn.addEventListener('click', () => {
        const node = document.importNode(partnerTpl, true);
        partnersWrap.appendChild(node);
        initSelect2In(partnersWrap);
      });
      partnersWrap.addEventListener('click', (e) => {
        if (e.target.closest('.remove-partner-btn')) e.target.closest('.partner-entry')?.remove();
      });
    }

    const vendorsWrap = document.getElementById('vendors-container');
    const addVendorBtn = document.getElementById('add-vendor-btn');
    const vendorTpl = document.getElementById('vendor-template')?.content;
    if (addVendorBtn && vendorsWrap && vendorTpl) {
      addVendorBtn.addEventListener('click', () => {
        const node = document.importNode(vendorTpl, true);
        vendorsWrap.appendChild(node);
        initSelect2In(vendorsWrap);
      });
      vendorsWrap.addEventListener('click', (e) => {
        if (e.target.closest('.remove-vendor-btn')) e.target.closest('.vendor-entry')?.remove();
      });
    }
  })();

  const categoryForm = document.getElementById('create-category-form');
  if (categoryForm) {
    categoryForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const data = await ajaxFormSubmit(categoryForm, 'تمت إضافة الفئة.');
      try {
        let id = data && data.id, text = data && (data.text || data.name);
        if (!id) {
          const name = categoryForm.querySelector('input[name="name"]')?.value || '';
          const catSearchURL = categoryForm.dataset.searchUrl || '/api/categories' || '/api/search_categories';
          const res = await fetch(`${catSearchURL}?q=${encodeURIComponent(name)}&limit=1`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
          const jd = await res.json();
          const arr = Array.isArray(jd) ? jd : (jd.results || jd.data || []);
          const top = arr && arr[0];
          if (top) { id = top.id; text = top.text || top.name || name; }
        }
        if (id) {
          const $cat = window.jQuery && jQuery('#category_id');
          if ($cat && $cat.length) {
            const option = new Option(text || id, id, true, true);
            $cat.append(option).trigger('change');
          } else {
            const sel = document.getElementById('category_id');
            if (sel) {
              const opt = document.createElement('option');
              opt.value = id;
              opt.textContent = text || id;
              opt.selected = true;
              sel.appendChild(opt);
            }
          }
        }
      } catch {}
      const modalEl = document.getElementById('categoryModal');
      if (modalEl && window.bootstrap && bootstrap.Modal.getInstance(modalEl)) bootstrap.Modal.getInstance(modalEl).hide();
      if (window.jQuery) jQuery('#categoryModal').modal?.('hide');
      categoryForm.reset();
    });
  }

  const equipmentTypeForm = document.getElementById('equipmentTypeForm');
  if (equipmentTypeForm) {
    equipmentTypeForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const data = await ajaxFormSubmit(equipmentTypeForm, 'تمت إضافة نوع المركبة.');
      try {
        let id = data && data.id, text = data && (data.text || data.name);
        if (!id) {
          const name = equipmentTypeForm.querySelector('input[name="name"]')?.value || '';
          const eqTypesSearchURL = equipmentTypeForm.dataset.searchUrl || window.API_SEARCH_EQUIPMENT_TYPES || '/api/search_equipment_types';
          const res = await fetch(`${eqTypesSearchURL}?q=${encodeURIComponent(name)}&limit=1`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
          const jd = await res.json();
          const arr = Array.isArray(jd) ? jd : (jd.results || jd.data || []);
          const top = arr && arr[0];
          if (top) { id = top.id; text = top.text || top.name || name; }
        }
        const sel = document.getElementById('vehicle_type_id');
        if (id && sel) {
          if (window.jQuery) {
            const $sel = jQuery(sel);
            const opt = new Option(text || id, id, true, true);
            $sel.append(opt).trigger('change');
          } else {
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = text || id;
            opt.selected = true;
            sel.appendChild(opt);
          }
        }
      } catch {}
      const modalEl = document.getElementById('equipmentTypeModal');
      if (modalEl) {
        if (window.bootstrap && bootstrap.Modal.getInstance(modalEl)) bootstrap.Modal.getInstance(modalEl).hide();
        else if (window.jQuery) jQuery(modalEl).modal('hide');
      }
      equipmentTypeForm.reset();
    });
  }

  let currentSupplierSelect = null;
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.add-supplier-btn');
    if (!btn) return;
    const group = btn.closest('.input-group');
    currentSupplierSelect = group?.querySelector('select') || btn.closest('.vendor-entry')?.querySelector('select') || null;
    const modal = document.getElementById('supplierModal');
    if (modal) {
      if (window.jQuery) jQuery(modal).modal('show');
      else if (window.bootstrap) new bootstrap.Modal(modal).show();
    }
  });

  const supplierForm = document.getElementById('create-supplier-form');
  if (supplierForm) {
    supplierForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const data = await ajaxFormSubmit(supplierForm, 'تمت إضافة المورّد.');
      try {
        let id = data && data.id, text = data && (data.text || data.name);
        if (!id) {
          const name = supplierForm.querySelector('input[name="name"]')?.value || '';
          const suppliersSearchURL = supplierForm.dataset.searchUrl || window.API_SEARCH_SUPPLIERS || '/api/search_suppliers';
          const res = await fetch(`${suppliersSearchURL}?q=${encodeURIComponent(name)}&limit=1`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
          const jd = await res.json();
          const arr = Array.isArray(jd) ? jd : (jd.results || jd.data || []);
          const top = arr && arr[0];
          if (top) { id = top.id; text = top.text || top.name || name; }
        }
        if (currentSupplierSelect && id) {
          if (window.jQuery) {
            const $sel = jQuery(currentSupplierSelect);
            const opt = new Option(text || id, id, true, true);
            $sel.append(opt).trigger('change');
          } else {
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = text || id;
            opt.selected = true;
            currentSupplierSelect.appendChild(opt);
          }
        }
      } catch {}
      const modalEl = document.getElementById('supplierModal');
      if (modalEl) {
        if (window.bootstrap && bootstrap.Modal.getInstance(modalEl)) bootstrap.Modal.getInstance(modalEl).hide();
        else if (window.jQuery) jQuery(modalEl).modal('hide');
      }
      supplierForm.reset();
      currentSupplierSelect = null;
    });
  }
});
