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

  function showNotification(message, type) {
    type = type || 'info';
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
    el.setAttribute('role', 'alert');
    const isBS5 = !!(window.bootstrap && typeof bootstrap?.Modal === 'function');
    const closeBtn = isBS5
      ? '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>'
      : '<button type="button" class="close" data-dismiss="alert" aria-label="Close"><span aria-hidden="true">&times;</span></button>';
    el.innerHTML = message + closeBtn;
    c.appendChild(el);
    setTimeout(function () {
      if (!el.parentNode) return;
      el.classList.remove('show');
      setTimeout(function () { el.remove(); }, 300);
    }, 5000);
  }

  function markRequired(container) {
    (container || document).querySelectorAll('[required]').forEach(function (el) {
      el.setAttribute('aria-required', 'true');
      var id = el.id;
      var label = id ? (container || document).querySelector('label[for="' + id + '"]') : el.closest('.form-group')?.querySelector('label');
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

  async function ajaxFormSubmit(form, okMsg, reload, cb) {
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
        if (reload === true) setTimeout(function () { location.reload(); }, 900);
      } else {
        const err = data.error || data.message || JSON.stringify(data.errors || {});
        showNotification('خطأ: ' + err, 'danger');
      }
      return data;
    } catch (e) {
      showNotification('تعذر الاتصال بالخادم.', 'danger');
      return { success: false };
    } finally {
      if (submitBtn) submitBtn.disabled = prevDisabled || false;
    }
  }

  function selectSetValue(selectEl, id, text) {
    if (!selectEl) return;
    const val = String(id);
    let opt = Array.from(selectEl.options).find(function (o) { return o.value === val; });
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
          data: function (params) { return { q: params && params.term ? params.term : '', limit: 20 }; },
          processResults: function (data) {
            const arr = Array.isArray(data) ? data : (data.results || data.data || []);
            return { results: (arr || []).map(function (x) { return { id: x.id, text: x.text || x.name || String(x.id) }; }) };
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
      (data.shares || []).forEach(function (s) {
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

    document.querySelectorAll('form').forEach(function (f) {
      if (f.__validatedBound) return;
      f.__validatedBound = true;
      f.addEventListener('submit', function () { f.classList.add('was-validated'); }, { once: true });
    });

    document.querySelectorAll('form[data-ajax="1"]').forEach(function (f) {
      f.setAttribute('novalidate', 'novalidate');
      if (f.__ajaxBound) return;
      f.__ajaxBound = true;
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        ajaxFormSubmit(f, f.dataset.ok || 'تم الحفظ بنجاح.', f.dataset.reload === '1');
      });
    });

    document.querySelectorAll('.stock-level-form').forEach(function (f) {
      f.setAttribute('novalidate', 'novalidate');
      if (f.__ajaxBound) return;
      f.__ajaxBound = true;
      f.addEventListener('submit', function (e) {
        e.preventDefault();
        ajaxFormSubmit(f, 'تم تحديث المخزون بنجاح.');
      });
    });

    const transferForm = document.getElementById('transfer-form');
    if (transferForm && !transferForm.__ajaxBound) {
      transferForm.setAttribute('novalidate', 'novalidate');
      transferForm.__ajaxBound = true;
      transferForm.addEventListener('submit', function (e) {
        e.preventDefault();
        ajaxFormSubmit(transferForm, 'تم تسجيل التحويل.', true);
      });
    }

    const exchangeForm = document.getElementById('exchange-form');
    if (exchangeForm && !exchangeForm.__ajaxBound) {
      exchangeForm.setAttribute('novalidate', 'novalidate');
      exchangeForm.__ajaxBound = true;
      exchangeForm.addEventListener('submit', function (e) {
        e.preventDefault();
        ajaxFormSubmit(exchangeForm, 'تم تسجيل حركة التبادل.', true);
      });
    }

    const partnerSharesForm = document.getElementById('partner-shares-form');
    if (partnerSharesForm && !partnerSharesForm.__ajaxBound) {
      partnerSharesForm.setAttribute('novalidate', 'novalidate');
      partnerSharesForm.__ajaxBound = true;
      partnerSharesForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        const wid = partnerSharesForm.dataset.warehouseId;
        const rows = partnerSharesForm.querySelectorAll('.share-row');
        const shares = [];
        rows.forEach(function (r) {
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
      jQuery(document).on('select2:open select2:close', function () { markRequired(document); });
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
        }).on('error.dt', function () { showNotification('حدثت مشكلة أثناء تحميل الجدول.', 'danger'); });
      });
    }

    document.addEventListener('click', function (e) {
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
        }).then(function (r) { if (r.isConfirmed) form.submit(); });
      } else if (confirm('تأكيد الحذف؟')) form.submit();
    });

    (function () {
      const form = document.getElementById('add-product-form');
      if (!form) return;

      const wtype = (form.dataset.wtype || '').toUpperCase();
      const pSec = document.getElementById('partner-section');
      const eSec = document.getElementById('exchange-section');
      const isExchangeEl = document.getElementById('is_exchange_id');

      if (wtype === 'PARTNER' && pSec) pSec.classList.remove('d-none');

      const defaultExchange = (wtype === 'EXCHANGE');
      if (eSec) {
        if (isExchangeEl) {
          if (defaultExchange) isExchangeEl.checked = true;
          const sync = function () { eSec.classList.toggle('d-none', !isExchangeEl.checked && !defaultExchange); };
          sync();
          isExchangeEl.addEventListener('change', function () {
            eSec.classList.toggle('d-none', !isExchangeEl.checked);
          });
        } else {
          eSec.classList.toggle('d-none', !defaultExchange);
        }
      }

      const partnersWrap = document.getElementById('partners-container');
      const addPartnerBtn = document.getElementById('add-partner-btn');
      const partnerTpl = document.getElementById('partner-template')?.content;
      if (addPartnerBtn && partnersWrap && partnerTpl) {
        addPartnerBtn.addEventListener('click', function () {
          const node = document.importNode(partnerTpl, true);
          partnersWrap.appendChild(node);
          initSelect2In(partnersWrap);
          markRequired(partnersWrap);
        });
        partnersWrap.addEventListener('click', function (e) {
          if (e.target.closest('.remove-partner-btn')) e.target.closest('.partner-entry')?.remove();
        });
      }

      const vendorsWrap = document.getElementById('vendors-container');
      const addVendorBtn = document.getElementById('add-vendor-btn');
      const vendorTpl = document.getElementById('vendor-template')?.content;
      if (addVendorBtn && vendorsWrap && vendorTpl) {
        addVendorBtn.addEventListener('click', function () {
          const node = document.importNode(vendorTpl, true);
          vendorsWrap.appendChild(node);
          initSelect2In(vendorsWrap);
          markRequired(vendorsWrap);
        });
        vendorsWrap.addEventListener('click', function (e) {
          if (e.target.closest('.remove-vendor-btn')) e.target.closest('.vendor-entry')?.remove();
        });
      }

      // إجبار select2 على إرسال قيمة مفردة (لا تتحول لمصفوفة)
      form.addEventListener('submit', function () {
        if (window.jQuery) {
          var vCat = window.jQuery('#category_id').val();
          if (vCat != null) {
            var catEl = document.querySelector('select#category_id');
            if (catEl) catEl.value = Array.isArray(vCat) ? vCat[0] : vCat;
          }
          var vType = window.jQuery('#vehicle_type_id').val();
          if (vType != null) {
            var typeEl = document.querySelector('select#vehicle_type_id');
            if (typeEl) typeEl.value = Array.isArray(vType) ? vType[0] : vType;
          }
        }
      });
    })();

    // فحص الباركود (يقرأ الـ URL من data-barcode-url)
    (function(){
      const input = document.getElementById('barcode');
      const help  = document.getElementById('barcodeHelp');
      if (!input) return;
      const validateURL = input.getAttribute('data-barcode-url') || '';

      input.addEventListener('input', () => {
        let v = input.value.replace(/\D+/g,'');
        if (v.length > 13) v = v.slice(0,13);
        input.value = v;
        input.classList.remove('is-invalid','is-valid');
        if (v.length >= 12 && validateURL) check(v);
      });

      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const form = input.closest('form');
          const focusables = form.querySelectorAll('input,select,textarea,button');
          for (let i=0;i<focusables.length;i++){
            if (focusables[i] === input && focusables[i+1]) { focusables[i+1].focus(); break; }
          }
        }
      });

      async function check(code){
        try{
          const url = validateURL + (validateURL.includes('?') ? '&' : '?') + 'code=' + encodeURIComponent(code);
          const res = await fetch(url, { headers: {'X-Requested-With':'XMLHttpRequest'} });
          const r = await res.json();
          if (!r.valid) {
            input.classList.add('is-invalid');
            if (help) help.textContent = 'باركود غير صالح';
            return;
          }
          if (r.normalized && r.normalized !== input.value) {
            input.value = r.normalized;
          }
          if (r.exists) {
            input.classList.add('is-invalid');
            if (help) help.textContent = 'الباركود مستخدم بالفعل';
          } else {
            input.classList.add('is-valid');
            if (help) help.textContent = 'الباركود صالح';
          }
        } catch {
          if (help) help.textContent = 'تعذر التحقق الآن، سيتم الفحص عند الحفظ';
        }
      }
    })();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // متاح للاستخدام العام إن احتجت
  window.showNotification = showNotification;
})();
