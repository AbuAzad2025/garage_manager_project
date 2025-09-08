(function () {
  if (window.__WAREHOUSES_INIT__) return;
  window.__WAREHOUSES_INIT__ = true;

  // ========= Helpers =========
  function getCSRFToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    var input = document.querySelector('input[name="csrf_token"]');
    if (input && input.value) return input.value;
    var m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : null;
  }

  function showNotification(message, type) {
    type = type || 'info';
    var c = document.getElementById('notification-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'notification-container';
      c.style.position = 'fixed';
      c.style.top = '20px';
      c.style.right = '20px';
      c.style.zIndex = '2000';
      document.body.appendChild(c);
    }
    var el = document.createElement('div');
    el.className = 'alert alert-' + type + ' alert-dismissible fade show shadow-sm mb-2';
    el.setAttribute('role', 'alert');
    var isBS5 = !!(window.bootstrap && window.bootstrap.Modal);
    var closeBtn = isBS5
      ? '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>'
      : '<button type="button" class="close" data-dismiss="alert" aria-label="Close"><span aria-hidden="true">&times;</span></button>';
    el.innerHTML = message + closeBtn;
    c.appendChild(el);
    setTimeout(function () {
      if (!el.parentNode) return;
      el.classList.remove('show');
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
    }, 5000);
  }

  function prefetchOnce($el, endpoint) {
    if (!$el || !endpoint) return;
    if ($el.data('prefetched')) return;
    $el.data('prefetched', true);
    fetch(endpoint + (endpoint.indexOf('?') >= 0 ? '&' : '?') + 'q=&limit=20', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin'
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var arr = Array.isArray(data) ? data : (data.results || data.data || []);
      (arr || []).forEach(function (x) {
        var id = x.id;
        var text = x.text || x.name || String(id);
        if (!id) return;
        if ($el.find('option[value="' + id + '"]').length === 0) {
          var opt = new Option(text, id, false, false);
          $el.append(opt);
        }
      });
      $el.trigger('change.select2');
    })
    .catch(function () { /* ignore */ });
  }

  function initSelect2(root) {
    if (!(window.jQuery && jQuery.fn.select2)) return;
    var $root = jQuery(root || document);
    $root.find('select.select2').each(function () {
      var $el = jQuery(this);
      if ($el.data('select2')) return;

      var endpoint = $el.data('url') || $el.data('endpoint');
      var placeholder = $el.attr('placeholder') || 'اختر...';

      var opts = {
        width: '100%',
        dir: 'rtl',
        theme: 'bootstrap4',
        allowClear: true,
        placeholder: placeholder,
        minimumInputLength: 0
      };

      if (endpoint) {
        opts.ajax = {
          delay: 250,
          cache: true,
          url: endpoint,
          dataType: 'json',
          data: function (params) {
            return { q: (params && params.term) ? params.term : '', limit: 20 };
          },
          processResults: function (data) {
            var arr = Array.isArray(data) ? data : (data.results || data.data || []);
            return {
              results: (arr || []).map(function (x) {
                return { id: x.id, text: x.text || x.name || String(x.id) };
              })
            };
          }
        };
      }

      $el.select2(opts);
      if (endpoint) prefetchOnce($el, endpoint);
    });
  }

  function postJSON(url, payload) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': getCSRFToken() || ''
      },
      credentials: 'same-origin',
      body: JSON.stringify(payload || {})
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var msg = (data && (data.error || data.message)) || ('HTTP ' + res.status);
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  function postForm(url, formElem) {
    var fd = new FormData(formElem);
    var csrf = getCSRFToken();
    if (csrf && !fd.get('csrf_token')) fd.append('csrf_token', csrf);
    return fetch(url, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
      body: fd
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok && !data.success) {
          var msg = (data && (data.error || data.message)) || ('HTTP ' + res.status);
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  function appendAndSelectOption(selectEl, id, text) {
    if (!selectEl || !id) return;
    var opt = new Option(text, id, true, true);
    selectEl.add(opt);
    if (window.jQuery) jQuery(selectEl).trigger('change');
  }

  function markRequired(container) {
    var root = container || document;
    var nodes = root.querySelectorAll('[required]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      el.setAttribute('aria-required', 'true');
      var id = el.id;
      var label = id ? root.querySelector('label[for="' + id + '"]') : null;
      if (!label) {
        var grp = el.closest('.form-group');
        if (grp) label = grp.querySelector('label');
      }
      if (label && !label.querySelector('.req')) {
        var s = document.createElement('span');
        s.className = 'req';
        s.textContent = '*';
        label.appendChild(s);
      }
      if (el.classList.contains('select2') || (el.tagName === 'SELECT' && el.classList.contains('select2'))) {
        var wrap = el.closest('.form-group') || el.parentElement || el;
        if (wrap) wrap.classList.add('is-required');
      }
    }
  }

  function toNumber(v) {
    if (v == null) return null;
    var s = String(v)
      .replace(/[^\d٠-٩.,-]/g, '')
      .replace(/[٠-٩]/g, function (d) { return '٠١٢٣٤٥٦٧٨٩'.indexOf(d); })
      .replace(/,/g, '.')
      .trim();
    if (s === '' || s === '-' || s === '.' || s === '-.') return null;
    var n = Number(s);
    return isFinite(n) ? n : null;
  }

  // ========= Validations =========
  function validatePartnerSection() {
    var ok = true;
    var container = document.getElementById('partners-container');
    if (!container) return true;

    var rows = Array.prototype.slice.call(container.querySelectorAll('.partner-entry'));
    var validRows = [];

    rows.forEach(function (row) {
      var pid  = row.querySelector('select[name="partner_id"]');
      var perc = row.querySelector('input[name="share_percentage"]');
      var amt  = row.querySelector('input[name="share_amount"]');

      var pidVal  = pid && pid.value ? String(pid.value).trim() : '';
      var percVal = toNumber(perc && perc.value);
      var amtVal  = toNumber(amt && amt.value);

      row.classList.remove('is-invalid');

      if (pidVal && ((percVal && percVal > 0) || (amtVal && amtVal > 0))) {
        validRows.push({ perc: percVal || 0, amt: amtVal || 0, row: row });
      }
    });

    if (!validRows.length) {
      ok = false;
      showNotification('أضف شريكًا واحدًا على الأقل مع نسبة أو قيمة مساهمة.', 'warning');
      var btn = document.getElementById('add-partner-btn');
      if (btn) btn.focus();
    } else {
      var allPercOnly = validRows.every(function (r) { return r.perc > 0 && (!r.amt || r.amt === 0); });
      if (allPercOnly) {
        var total = validRows.reduce(function (s, r) { return s + r.perc; }, 0);
        if (total > 100.0001) {
          ok = false;
          showNotification('مجموع نسب الشركاء يتجاوز 100٪.', 'danger');
          validRows.forEach(function (r) { r.row.classList.add('is-invalid'); });
        }
      }
    }
    return ok;
  }

  function validateExchangeSection() {
    var container = document.getElementById('vendors-container');
    if (!container) return true;
    var rows = Array.prototype.slice.call(container.querySelectorAll('.vendor-entry'));
    var hasSupplier = rows.some(function (row) {
      var sid = row.querySelector('select[name="supplier_id"]');
      return sid && sid.value && String(sid.value).trim() !== '';
    });
    if (!hasSupplier) {
      showNotification('أضف مورّدًا واحدًا على الأقل لمستودع التبادل.', 'warning');
      var btn = document.getElementById('add-vendor-btn');
      if (btn) btn.focus();
      return false;
    }
    return true;
  }

  function toggleSectionsByType(wtype) {
    var partnerSection = document.getElementById('partner-section');
    var exchangeSection = document.getElementById('exchange-section');
    if (partnerSection) partnerSection.classList.toggle('d-none', wtype !== 'PARTNER');
    if (exchangeSection) exchangeSection.classList.toggle('d-none', wtype !== 'EXCHANGE');
  }

  // ========= Init =========
  function initPage() {
    markRequired(document);
    initSelect2(document);

    var form = document.getElementById('add-product-form');
    var wtype = (form && form.dataset && form.dataset.wtype ? form.dataset.wtype : '').toUpperCase();
    var isExchangeEl = document.getElementById('is_exchange_id');

    toggleSectionsByType(wtype);

    if (isExchangeEl) {
      if (wtype === 'EXCHANGE') isExchangeEl.checked = true;
      var exchangeSection = document.getElementById('exchange-section');
      if (exchangeSection) {
        exchangeSection.classList.toggle('d-none', !(isExchangeEl.checked || wtype === 'EXCHANGE'));
        isExchangeEl.addEventListener('change', function () {
          exchangeSection.classList.toggle('d-none', !isExchangeEl.checked);
        });
      }
    }

    // Partners section (dynamic rows)
    var partnersContainer = document.getElementById('partners-container');
    var addPartnerBtn = document.getElementById('add-partner-btn');
    var partnerTpl = document.getElementById('partner-template');
    if (addPartnerBtn && partnersContainer && partnerTpl && partnerTpl.content) {
      addPartnerBtn.addEventListener('click', function () {
        var node = document.importNode(partnerTpl.content, true);
        partnersContainer.appendChild(node);
        initSelect2(partnersContainer);
        markRequired(partnersContainer);
      });
      partnersContainer.addEventListener('click', function (e) {
        var rm = e.target.closest('.remove-partner-btn');
        if (rm) { var row = e.target.closest('.partner-entry'); if (row) row.remove(); }
      });
    }

    // Vendors section (dynamic rows)
    var vendorsContainer = document.getElementById('vendors-container');
    var addVendorBtn = document.getElementById('add-vendor-btn');
    var vendorTpl = document.getElementById('vendor-template');
    if (addVendorBtn && vendorsContainer && vendorTpl && vendorTpl.content) {
      addVendorBtn.addEventListener('click', function () {
        var node = document.importNode(vendorTpl.content, true);
        vendorsContainer.appendChild(node);
        initSelect2(vendorsContainer);
        markRequired(vendorsContainer);
      });
      vendorsContainer.addEventListener('click', function (e) {
        var rm = e.target.closest('.remove-vendor-btn');
        if (rm) { var row = e.target.closest('.vendor-entry'); if (row) row.remove(); }
      });
    }

    // Remember last focused supplier select (for + modal)
    var lastSupplierSelect = null;
    document.addEventListener('focusin', function (e) {
      if (e.target && e.target.matches('#vendors-container select[name="supplier_id"]')) {
        lastSupplierSelect = e.target;
      }
    });
    window.lastSupplierSelect = lastSupplierSelect;

    // --- Category modal ---
    (function initCategoryModal() {
      var mform = document.getElementById('create-category-form');
      var select = document.getElementById('category_id');
      if (!mform || !select) return;
      mform.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = mform.querySelector('button[type="submit"]');
        if (btn) btn.disabled = true;
        var name = (mform.querySelector('input[name="name"]') || {}).value || '';
        name = name.trim();
        var notesEl = mform.querySelector('textarea[name="notes"]');
        var notes = notesEl ? (notesEl.value || '').trim() : '';
        if (!name) { showNotification('أدخل اسم الفئة', 'warning'); if (btn) btn.disabled = false; return; }
        var url = mform.getAttribute('data-url') || mform.action || window.location.href;
        postJSON(url, { name: name, notes: notes })
          .then(function (data) {
            var item = data.id ? { id: data.id, text: data.name || name }
                               : ((data.results && data.results[0]) ? data.results[0] : null);
            if (!item) throw new Error('استجابة غير متوقعة من الخادم');
            appendAndSelectOption(select, item.id, item.text || name);
            showNotification('تمت إضافة الفئة.', 'success');
            if (window.jQuery) jQuery(mform).closest('.modal').modal('hide');
            mform.reset();
          })
          .catch(function (err) {
            showNotification('تعذر إضافة الفئة: ' + (err && err.message ? err.message : 'خطأ غير معروف'), 'danger');
          })
          .finally(function () { if (btn) btn.disabled = false; });
      });
    })();

    // --- Equipment type modal ---
    (function initEquipmentTypeModal() {
      var mform = document.getElementById('equipmentTypeForm');
      var select = document.getElementById('vehicle_type_id');
      if (!mform || !select) return;
      mform.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = mform.querySelector('button[type="submit"]');
        if (btn) btn.disabled = true;
        var nameEl = mform.querySelector('input[name="name"]');
        var name = nameEl ? (nameEl.value || '').trim() : '';
        if (!name) { showNotification('أدخل اسم النوع', 'warning'); if (btn) btn.disabled = false; return; }
        var url = mform.getAttribute('data-url') || mform.action || window.location.href;
        postForm(url, mform)
          .then(function (data) {
            if (!data || !data.id) throw new Error(data && data.error ? data.error : 'استجابة غير متوقعة');
            appendAndSelectOption(select, data.id, data.name || name);
            showNotification('تمت إضافة النوع.', 'success');
            if (window.jQuery) jQuery(mform).closest('.modal').modal('hide');
            mform.reset();
          })
          .catch(function (err) {
            showNotification('تعذر إضافة النوع: ' + (err && err.message ? err.message : 'خطأ غير معروف'), 'danger');
          })
          .finally(function () { if (btn) btn.disabled = false; });
      });
    })();

    // --- Supplier modal ---
    (function initSupplierModal() {
      var mform = document.getElementById('create-supplier-form');
      if (!mform) return;
      mform.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = mform.querySelector('button[type="submit"]');
        if (btn) btn.disabled = true;
        var payload = {
          name: ((mform.querySelector('input[name="name"]') || {}).value || '').trim(),
          phone: ((mform.querySelector('input[name="phone"]') || {}).value || '').trim(),
          identity_number: ((mform.querySelector('input[name="identity_number"]') || {}).value || '').trim(),
          address: ((mform.querySelector('input[name="address"]') || {}).value || '').trim(),
          notes: ((mform.querySelector('textarea[name="notes"]') || {}).value || '').trim()
        };
        if (!payload.name) { showNotification('الاسم مطلوب', 'warning'); if (btn) btn.disabled = false; return; }
        var url = mform.getAttribute('data-url') || mform.action || window.location.href;
        postJSON(url, payload)
          .then(function (data) {
            if (!data || !data.id) throw new Error(data && data.error ? data.error : 'استجابة غير متوقعة');
            var fallback = document.querySelector('#vendors-container select[name="supplier_id"]');
            var select = window.lastSupplierSelect || fallback;
            if (select) appendAndSelectOption(select, data.id, data.name || payload.name);
            showNotification('تمت إضافة المورّد.', 'success');
            if (window.jQuery) jQuery(mform).closest('.modal').modal('hide');
            mform.reset();
          })
          .catch(function (err) {
            showNotification('تعذر إضافة المورّد: ' + (err && err.message ? err.message : 'خطأ غير معروف'), 'danger');
          })
          .finally(function () { if (btn) btn.disabled = false; });
      });
    })();

    // --- Form submit validations ---
    if (form) {
      form.addEventListener('submit', function (e) {
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

        if (wtype === 'PARTNER') {
          if (!validatePartnerSection()) {
            e.preventDefault();
            e.stopPropagation();
            return false;
          }
        }
        if (wtype === 'EXCHANGE') {
          if (!validateExchangeSection()) {
            e.preventDefault();
            e.stopPropagation();
            return false;
          }
        }
        return true;
      });
    }

    // --- Barcode live validation ---
    (function initBarcode() {
      var input = document.getElementById('barcode');
      var help  = document.getElementById('barcodeHelp');
      if (!input) return;
      var validateURL = input.getAttribute('data-barcode-url') || '';

      input.addEventListener('input', function () {
        var v = input.value.replace(/\D+/g, '');
        if (v.length > 13) v = v.slice(0, 13);
        input.value = v;
        input.classList.remove('is-invalid', 'is-valid');
        if (v.length >= 12 && validateURL) check(v);
      });

      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          var ff = input.closest('form');
          if (!ff) return;
          var focusables = ff.querySelectorAll('input,select,textarea,button');
          for (var i = 0; i < focusables.length; i++) {
            if (focusables[i] === input && focusables[i + 1]) {
              focusables[i + 1].focus(); break;
            }
          }
        }
      });

      function check(code) {
        if (!validateURL) return;
        fetch(validateURL + (validateURL.indexOf('?') >= 0 ? '&' : '?') + 'code=' + encodeURIComponent(code), {
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          credentials: 'same-origin'
        })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res.valid) {
            input.classList.add('is-invalid');
            if (help) help.textContent = 'باركود غير صالح';
            return;
          }
          if (res.normalized && res.normalized !== input.value) {
            input.value = res.normalized;
          }
          if (res.exists) {
            input.classList.add('is-invalid');
            if (help) help.textContent = 'الباركود مستخدم بالفعل';
          } else {
            input.classList.add('is-valid');
            if (help) help.textContent = 'الباركود صالح';
          }
        })
        .catch(function () {
          if (help) help.textContent = 'تعذر التحقق الآن، سيتم الفحص عند الحفظ';
        });
      }
    })();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPage);
  } else {
    initPage();
  }

  // expose
  window.showNotification = showNotification;
})();
