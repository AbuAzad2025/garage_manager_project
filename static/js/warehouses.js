<script>
(function () {
  if (window.__WAREHOUSES_INIT__) return;
  window.__WAREHOUSES_INIT__ = true;

  function getCSRFToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const input = document.querySelector('input[name="csrf_token"]');
    if (input && input.value) return input.value;
    const m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : null;
  }

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
    el.className = 'alert alert-' + type + ' alert-dismissible fade show shadow-sm mb-2';
    el.role = 'alert';
    el.innerHTML = message + '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>';
    c.appendChild(el);
    setTimeout(function(){ if (!el.parentNode) return; el.classList.remove('show'); setTimeout(function(){ el.remove(); }, 300); }, 5000);
  }

  function markRequired(container) {
    (container || document).querySelectorAll('[required]').forEach(function(el){
      el.setAttribute('aria-required','true');
      var id = el.id;
      var label = id ? (container || document).querySelector('label[for="'+id+'"]') : el.closest('.form-group')?.querySelector('label');
      if (label && !label.querySelector('.req')) {
        var s = document.createElement('span');
        s.className = 'req';
        s.textContent = '*';
        label.appendChild(s);
      }
      if (el.classList.contains('select2') || el.matches('select.select2')) {
        var wrap = el.closest('.form-group') || el.parentElement || el;
        wrap.classList.add('is-required');
      }
    });
  }

  async function ajaxFormSubmit(form, okMsg, reload = false, cb = null) {
    const submitBtn = form.querySelector('[type="submit"]');
    const prevDisabled = submitBtn && submitBtn.disabled;
    if (submitBtn) submitBtn.disabled = true;
    try {
      const url = form.dataset.url || form.getAttribute('action') || form.action || window.location.href;
      const method = (form.getAttribute('method') || 'POST').toUpperCase();
      const fd = new FormData(form);
      const headers = { 'X-Requested-With': 'XMLHttpRequest' };
      const csrf = getCSRFToken();
      if (csrf) headers['X-CSRFToken'] = csrf;
      const res = await fetch(url, { method, body: fd, headers, credentials: 'same-origin' });
      const ct = res.headers.get('content-type') || '';
      const data = ct.includes('application/json') ? await res.json() : { success: res.ok };
      if (data.success || res.ok) {
        showNotification(okMsg || 'تم التنفيذ بنجاح.', 'success');
        if (cb) cb(data);
        if (reload) setTimeout(function(){ location.reload(); }, 900);
      } else {
        const err = data.error || data.message || JSON.stringify(data.errors || {});
        showNotification('خطأ: ' + err, 'danger');
      }
      return data;
    } catch {
      showNotification('تعذر الاتصال بالخادم.', 'danger');
      return { success: false };
    } finally {
      if (submitBtn) submitBtn.disabled = prevDisabled || false;
    }
  }

  function selectSetValue(selectEl, id, text) {
    if (!selectEl) return;
    const val = String(id);
    let opt = Array.from(selectEl.options).find(function(o){ return o.value === val; });
    if (!opt) {
      opt = document.createElement('option');
      opt.value = val;
      opt.textContent = text || val;
      selectEl.appendChild(opt);
    } else if (text && !opt.textContent) {
      opt.textContent = text;
    }
    selectEl.value = val;
    if (window.jQuery) {
      const $sel = window.jQuery(selectEl);
      $sel.val(val).trigger('change');
    } else {
      const evt = new Event('change', { bubbles: true });
      selectEl.dispatchEvent(evt);
    }
  }

  function initSelect2In(root) {
    if (!(window.jQuery && jQuery.fn.select2)) return;
    jQuery(root || document).find('.select2').each(function () {
      const $el = jQuery(this);
      if ($el.data('select2')) return;
      const endpoint = $el.data('url') || $el.attr('data-url') || $el.data('endpoint');
      const opts = { width: '100%', dir: 'rtl', theme: 'bootstrap4', allowClear: true, placeholder: $el.attr('placeholder') || $el.data('placeholder') || 'اختر...' };
      if (endpoint) {
        opts.ajax = {
          delay: 250,
          url: endpoint,
          data: function(params){ return { q: params.term || '', limit: 20 }; },
          processResults: function(data) {
            const arr = Array.isArray(data) ? data : (data.results || data.data || []);
            return { results: arr.map(function(x){ return { id: x.id, text: x.text || x.name || String(x.id) }; }) };
          }
        };
      }
      $el.select2(opts);
    });
  }

  async function loadPartnerShares(warehouseId) {
    try {
      const headers = { 'X-Requested-With': 'XMLHttpRequest' };
      const csrf = getCSRFToken();
      if (csrf) headers['X-CSRFToken'] = csrf;
      const res = await fetch('/warehouses/' + warehouseId + '/partner-shares', { headers, credentials: 'same-origin' });
      const data = await res.json();
      if (!data.success) throw 0;
      const tbody = document.querySelector('#partner-shares-table tbody');
      if (!tbody) return;
      tbody.innerHTML = '';
      (data.shares || []).forEach(function(s){
        const tr = document.createElement('tr');
        tr.innerHTML =
          '<td>' + (s.product || '') + '</td>' +
          '<td>' + (s.partner || '') + '</td>' +
          '<td class="text-center">' + Number(s.share_percentage || 0).toFixed(2) + '</td>' +
          '<td class="text-end">' + Number(s.share_amount || 0).toFixed(2) + '</td>' +
          '<td>' + (s.notes || '') + '</td>';
        tbody.appendChild(tr);
      });
    } catch {
      showNotification('فشل تحميل بيانات حصص الشركاء.', 'danger');
    }
  }

  function init() {
    markRequired(document);

    document.querySelectorAll('form').forEach(function(f){
      if (f.__validatedBound) return;
      f.__validatedBound = true;
      f.addEventListener('submit', function(){ f.classList.add('was-validated'); }, { once: true });
    });

    document.querySelectorAll('form[data-ajax="1"]').forEach(function(f){
      f.setAttribute('novalidate', 'novalidate');
      if (f.__ajaxBound) return;
      f.__ajaxBound = true;
      f.addEventListener('submit', function(e){
        e.preventDefault();
        ajaxFormSubmit(f, f.dataset.ok || 'تم الحفظ بنجاح.', f.dataset.reload === '1');
      });
    });

    document.querySelectorAll('.stock-level-form').forEach(function(f){
      f.setAttribute('novalidate', 'novalidate');
      if (f.__ajaxBound) return;
      f.__ajaxBound = true;
      f.addEventListener('submit', function(e){
        e.preventDefault();
        ajaxFormSubmit(f, 'تم تحديث المخزون بنجاح.');
      });
    });

    const transferForm = document.getElementById('transfer-form');
    if (transferForm && !transferForm.__ajaxBound) {
      transferForm.setAttribute('novalidate', 'novalidate');
      transferForm.__ajaxBound = true;
      transferForm.addEventListener('submit', function(e){
        e.preventDefault();
        ajaxFormSubmit(transferForm, 'تم تسجيل التحويل.', true);
      });
    }

    const exchangeForm = document.getElementById('exchange-form');
    if (exchangeForm && !exchangeForm.__ajaxBound) {
      exchangeForm.setAttribute('novalidate', 'novalidate');
      exchangeForm.__ajaxBound = true;
      exchangeForm.addEventListener('submit', function(e){
        e.preventDefault();
        ajaxFormSubmit(exchangeForm, 'تم تسجيل حركة التبادل.', true);
      });
    }

    const partnerSharesForm = document.getElementById('partner-shares-form');
    if (partnerSharesForm && !partnerSharesForm.__ajaxBound) {
      partnerSharesForm.setAttribute('novalidate', 'novalidate');
      partnerSharesForm.__ajaxBound = true;
      partnerSharesForm.addEventListener('submit', async function(e){
        e.preventDefault();
        const wid = partnerSharesForm.dataset.warehouseId;
        const rows = partnerSharesForm.querySelectorAll('.share-row');
        const shares = [];
        rows.forEach(function(r){
          shares.push({
            product_id: parseInt(r.querySelector('.product-id')?.value || '0', 10) || null,
            partner_id: parseInt(r.querySelector('.partner-id')?.value || '0', 10) || null,
            share_percentage: parseFloat(r.querySelector('.share-percentage')?.value || '0') || 0,
            share_amount: parseFloat(r.querySelector('.share-amount')?.value || '0') || 0,
            notes: r.querySelector('.notes')?.value || ''
          });
        });
        try {
          const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' };
          const csrf = getCSRFToken();
          if (csrf) headers['X-CSRFToken'] = csrf;
          const res = await fetch('/warehouses/' + wid + '/partner-shares', { method: 'POST', headers, body: JSON.stringify({ shares }), credentials: 'same-origin' });
          const data = await res.json();
          if (data.success) {
            showNotification('تم تحديث الحصص.', 'success');
            loadPartnerShares(wid);
          } else {
            showNotification('خطأ: ' + (data.error || 'تعذر التحديث'), 'danger');
          }
        } catch {
          showNotification('تعذر الاتصال أثناء تحديث الحصص.', 'danger');
        }
      });
      const tbl = document.getElementById('partner-shares-table');
      if (tbl) loadPartnerShares(partnerSharesForm.dataset.warehouseId);
    }

    initSelect2In(document);

    if (window.jQuery && jQuery.fn.select2) {
      jQuery(document).on('select2:open select2:close', function(){ markRequired(document); });
    }

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
          language: { url: 'https://cdn.datatables.net/plug-ins/1.13.6/i18n/ar.json' }
        }).on('error.dt', function(){ showNotification('حدثت مشكلة أثناء تحميل الجدول.', 'danger'); });
      });
    }

    document.addEventListener('click', function(e){
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
        }).then(function(r){ if (r.isConfirmed) form.submit(); });
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
    addPartnerBtn.addEventListener('click', function(){
      const node = document.importNode(partnerTpl, true);
      partnersWrap.appendChild(node);
      initSelect2In(partnersWrap);
      markRequired(partnersWrap);
    });
    partnersWrap.addEventListener('click', function(e){
      if (e.target.closest('.remove-partner-btn')) e.target.closest('.partner-entry')?.remove();
    });
  }

  const vendorsWrap = document.getElementById('vendors-container');
  const addVendorBtn = document.getElementById('add-vendor-btn');
  const vendorTpl = document.getElementById('vendor-template')?.content;
  if (addVendorBtn && vendorsWrap && vendorTpl) {
    addVendorBtn.addEventListener('click', function(){
      const node = document.importNode(vendorTpl, true);
      vendorsWrap.appendChild(node);
      initSelect2In(vendorsWrap);
      markRequired(vendorsWrap);
    });
    vendorsWrap.addEventListener('click', function(e){
      if (e.target.closest('.remove-vendor-btn')) e.target.closest('.vendor-entry')?.remove();
    });
  }

  form.addEventListener('submit', function () {
    if (window.jQuery) {
      var vCat = jQuery('#category_id').val();
      if (vCat != null) {
        document.getElementById('category_id').value = Array.isArray(vCat) ? vCat[0] : vCat;
      }
      var vType = jQuery('#vehicle_type_id').val();
      if (vType != null) {
        document.getElementById('vehicle_type_id').value = Array.isArray(vType) ? vType[0] : vType;
      }
    }
  });
})();

    const categoryForm = document.getElementById('create-category-form');
    if (categoryForm && !categoryForm.__ajaxBound) {
      categoryForm.setAttribute('novalidate', 'novalidate');
      categoryForm.__ajaxBound = true;
      categoryForm.addEventListener('submit', async function(e){
        e.preventDefault();
        const data = await ajaxFormSubmit(categoryForm, 'تمت إضافة الفئة.');
        try {
          let id = data && data.id, text = data && (data.text || data.name);
          if (!id) {
            const name = categoryForm.querySelector('input[name="name"]')?.value || '';
            const catSearchURL = categoryForm.dataset.searchUrl || '/api/search_categories';
            const headers = { 'X-Requested-With': 'XMLHttpRequest' };
            const csrf = getCSRFToken();
            if (csrf) headers['X-CSRFToken'] = csrf;
            const res = await fetch(catSearchURL + '?q=' + encodeURIComponent(name) + '&limit=1', { headers, credentials: 'same-origin' });
            const jd = await res.json();
            const arr = Array.isArray(jd) ? jd : (jd.results || jd.data || []);
            const top = arr && arr[0];
            if (top) { id = top.id; text = top.text || top.name || name; }
          }
          if (id) {
            const catSel = document.getElementById('category_id');
            selectSetValue(catSel, id, text);
          }
        } catch {}
        const modalEl = document.getElementById('categoryModal');
        if (modalEl && window.bootstrap && bootstrap.Modal.getInstance(modalEl)) bootstrap.Modal.getInstance(modalEl).hide();
        if (window.jQuery) jQuery('#categoryModal').modal?.('hide');
        categoryForm.reset();
      });
    }

    const equipmentTypeForm = document.getElementById('equipmentTypeForm');
    if (equipmentTypeForm && !equipmentTypeForm.__ajaxBound) {
      equipmentTypeForm.setAttribute('novalidate', 'novalidate');
      equipmentTypeForm.__ajaxBound = true;
      equipmentTypeForm.addEventListener('submit', async function(e){
        e.preventDefault();
        const data = await ajaxFormSubmit(equipmentTypeForm, 'تمت إضافة نوع المركبة.');
        try {
          let id = data && data.id, text = data && (data.text || data.name);
          if (!id) {
            const name = equipmentTypeForm.querySelector('input[name="name"]')?.value || '';
            const eqTypesSearchURL = equipmentTypeForm.dataset.searchUrl || window.API_SEARCH_EQUIPMENT_TYPES || '/api/search_equipment_types';
            const headers = { 'X-Requested-With': 'XMLHttpRequest' };
            const csrf = getCSRFToken();
            if (csrf) headers['X-CSRFToken'] = csrf;
            const res = await fetch(eqTypesSearchURL + '?q=' + encodeURIComponent(name) + '&limit=1', { headers, credentials: 'same-origin' });
            const jd = await res.json();
            const arr = Array.isArray(jd) ? jd : (jd.results || jd.data || []);
            const top = arr && arr[0];
            if (top) { id = top.id; text = top.text || top.name || name; }
          }
          const sel = document.getElementById('vehicle_type_id');
          if (id && sel) selectSetValue(sel, id, text);
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
    document.addEventListener('click', function(e){
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
    if (supplierForm && !supplierForm.__ajaxBound) {
      supplierForm.setAttribute('novalidate', 'novalidate');
      supplierForm.__ajaxBound = true;
      supplierForm.addEventListener('submit', async function(e){
        e.preventDefault();
        const data = await ajaxFormSubmit(supplierForm, 'تمت إضافة المورّد.');
        try {
          let id = data && data.id, text = data && (data.text || data.name);
          if (!id) {
            const name = supplierForm.querySelector('input[name="name"]')?.value || '';
            const suppliersSearchURL = supplierForm.dataset.searchUrl || window.API_SEARCH_SUPPLIERS || '/api/search_suppliers';
            const headers = { 'X-Requested-With': 'XMLHttpRequest' };
            const csrf = getCSRFToken();
            if (csrf) headers['X-CSRFToken'] = csrf;
            const res = await fetch(suppliersSearchURL + '?q=' + encodeURIComponent(name) + '&limit=1', { headers, credentials: 'same-origin' });
            const jd = await res.json();
            const arr = Array.isArray(jd) ? jd : (jd.results || jd.data || []);
            const top = arr && arr[0];
            if (top) { id = top.id; text = top.text || top.name || name; }
          }
          if (currentSupplierSelect && id) selectSetValue(currentSupplierSelect, id, text);
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
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.showNotification = showNotification;
})();
</script>
