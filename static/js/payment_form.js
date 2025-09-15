// سكريبت نموذج سند الدفع:
// - إدارة الدفعات الجزئية (Splits) وإظهار/إخفاء حقول تفاصيل الطريقة حسب الاختيار
// - جمع مجموع مبالغ الـ Splits ومقارنته بالمبلغ الكلي
// - إعادة تحميل حقول الجهة المرتبطة حسب نوع الكيان
// - بحث تلقائي (أوتوكومبليت) للعملاء/الموردين/الشركاء باستخدام /payments/entity-search
// - حفظ نفس أسماء الحقول والأIDs كما في القالب لتجنب أي تعارض

document.addEventListener('DOMContentLoaded', function () {
  const container = document.getElementById('splitsContainer');
  const MAX_SPLITS = parseInt(container?.dataset.maxSplits || '3', 10);

  // خريطة الحقول المطلوبة لكل طريقة دفع
  const METHOD_FIELDS = {
    "": [],
    cash: [],
    online: [],
    mobile: [],
    cheque: ["check_number","check_bank","check_due_date"],
    check: ["check_number","check_bank","check_due_date"],
    bank: ["bank_transfer_ref"],
    transfer: ["bank_transfer_ref"],
    card: ["card_number","card_holder","card_expiry"],
    credit: ["card_number","card_holder","card_expiry"]
  };

  const addBtn = document.getElementById('addSplit');
  const form = document.getElementById('paymentForm');
  const template = container && container.querySelector('.split-form') ? container.querySelector('.split-form').cloneNode(true) : null;
  const entityWrap = document.getElementById('entityFields');
  const totalInput = document.querySelector('[name="total_amount"]');
  const entityTypeSelect = document.querySelector('[name="entity_type"]');

  // توحيد أسماء طرق الدفع للنمط المعتمد
  function normalizeMethod(val) {
    if (!val) return '';
    val = String(val).toLowerCase().trim();
    if (val.includes('cheq') || val === 'check' || val === 'cheque') return 'cheque';
    if (val.includes('bank') || val.includes('transfer')) return 'bank';
    if (val.includes('card') || val.includes('credit') || val.includes('visa') || val.includes('master')) return 'card';
    if (val.includes('cash')) return 'cash';
    if (val.includes('mobile')) return 'mobile';
    if (val.includes('online')) return 'online';
    return val;
  }

  // إضافة خيار Placeholder لأول عنصر في Select الطريقة
  function ensurePlaceholderOption(select) {
    if (!select) return;
    if (!select.options.length || select.options[0].value !== '') {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '— اختر الطريقة —';
      opt.disabled = true;
      opt.selected = !select.value;
      select.insertBefore(opt, select.firstChild);
    } else {
      select.options[0].disabled = true;
      if (!select.value) select.selectedIndex = 0;
    }
  }

  function toggleAddBtn() {
    if (!container || !addBtn) return;
    const count = container.querySelectorAll('.split-form').length;
    addBtn.disabled = count >= MAX_SPLITS;
  }

  // إظهار/إخفاء تفاصيل الطريقة داخل صف دفعة جزئية
  function applyDetailsForRow(row, method) {
    const details = row.querySelector('.split-details');
    if (!details) return;
    const key = normalizeMethod(method);
    const want = new Set(METHOD_FIELDS[key] || []);
    let anyShown = false;

    details.querySelectorAll('[data-field]').forEach(wrap => {
      const field = wrap.dataset.field;
      const show = want.has(field);
      const inp = wrap.querySelector('input,select,textarea');

      wrap.style.display = show ? '' : 'none';
      if (inp) {
        if (show) {
          inp.disabled = false;
        } else {
          inp.value = '';
          inp.disabled = true;
        }
      }
      if (show) anyShown = true;
    });

    details.style.display = anyShown ? 'block' : 'none';
  }

  // إعادة ترقيم حقول صف دفعة جزئية ليتوافق مع WTForms FieldList
  function renumberRowFields(row, i) {
    row.dataset.index = i;
    const title = row.querySelector('h5');
    if (title) title.textContent = `الدفعة الجزئية #${i + 1}`;

    row.querySelectorAll('input,select,textarea').forEach(inp => {
      if (!inp.name) return;
      const field = inp.name.split('-').pop();
      inp.name = `splits-${i}-${field}`;
      inp.id = `splits-${i}-${field}`;
    });

    const sel = row.querySelector('select[name$="-method"]');
    if (sel) {
      ensurePlaceholderOption(sel);
      if (!sel.value) sel.selectedIndex = 0;
    }

    const btn = row.querySelector('.remove-split');
    if (btn) btn.disabled = (i === 0);
  }

  // تحديث جميع الصفوف وإعادة تطبيق تفاصيل الطرق
  function refreshSplits() {
    if (!container) return;
    container.querySelectorAll('.split-form').forEach((el, i) => {
      renumberRowFields(el, i);
      const sel = el.querySelector('select[name$="-method"]');
      const method = (sel && sel.value ? sel.value : '');
      applyDetailsForRow(el, method);
    });
    toggleAddBtn();
    updateSplitSumHint();
  }

  // إنشاء صف دفعة جزئية جديد من القالب الأول
  function createSplitElement() {
    if (!container || !template) return null;
    const idx = container.querySelectorAll('.split-form').length;
    const clone = template.cloneNode(true);

    clone.querySelectorAll('input,select,textarea').forEach(el => {
      if (el.tagName === 'SELECT') el.selectedIndex = 0; else el.value = '';
      if (el.closest('[data-field]')) el.disabled = true;
    });

    const details = clone.querySelector('.split-details');
    if (details) details.style.display = 'none';

    renumberRowFields(clone, idx);
    return clone;
  }

  // إظهار تلميح مجموع مبالغ الـSplits مقابل المبلغ الكلي
  function updateSplitSumHint() {
    if (!container || !totalInput) return;

    const hint = document.getElementById('splitSum') || (() => {
      const small = document.createElement('div');
      small.className = 'form-text';
      small.id = 'splitSum';
      totalInput.parentElement.appendChild(small);
      return small;
    })();

    let sum = 0;
    container.querySelectorAll('.split-form').forEach(el => {
      const amountEl = el.querySelector('[name$="-amount"]');
      const val = parseFloat((amountEl ? amountEl.value : '').replace(',', '.')) || 0;
      sum += val;
    });

    const total = parseFloat((totalInput.value || '').replace(',', '.')) || 0;
    hint.textContent = `مجموع الدفعات الجزئية: ${sum.toFixed(2)} — المبلغ الكلي: ${total.toFixed(2)}`;
    hint.style.color = Math.abs(sum - total) < 0.01 ? '' : '#b02a37';
  }

  // زر إضافة دفعة جزئية
  if (addBtn && container) {
    addBtn.addEventListener('click', () => {
      const count = container.querySelectorAll('.split-form').length;
      if (count >= MAX_SPLITS) return;
      const el = createSplitElement();
      if (el) container.appendChild(el);
      refreshSplits();
    });
  }

  // أحداث على الحاوية: حذف صف/تغيير طريقة/قيمة
  if (container) {
    container.addEventListener('click', e => {
      if (e.target.matches('.remove-split')) {
        e.preventDefault();
        const row = e.target.closest('.split-form');
        if (!row) return;
        row.remove();
        refreshSplits();
      }
    });

    container.addEventListener('change', e => {
      if (e.target.matches('select[name$="-method"]')) {
        const row = e.target.closest('.split-form');
        const method = (e.target.value || '');
        applyDetailsForRow(row, method);
      }
      if (e.target.matches('[name$="-amount"]')) updateSplitSumHint();
    });

    container.addEventListener('input', e => {
      if (e.target.matches('[name$="-amount"]')) updateSplitSumHint();
    });

    // تجهيز الصفوف الحالية عند التحميل
    container.querySelectorAll('.split-form select[name$="-method"]').forEach(sel => {
      ensurePlaceholderOption(sel);
      applyDetailsForRow(sel.closest('.split-form'), (sel.value || ''));
    });
  }

  if (totalInput) totalInput.addEventListener('input', updateSplitSumHint);

  // إعادة تحميل حقول الجهة المرتبطة عند تغيير نوع الكيان
  function reloadEntityFields() {
    if (!entityTypeSelect || !entityWrap) return;
    const type = entityTypeSelect.value || '';
    const eidEl = document.getElementById('entity_id') || entityWrap.querySelector('input[name="entity_id"]');
    const eid = eidEl ? (eidEl.value || '') : '';
    if (!type) {
      entityWrap.innerHTML = '<div class="text-muted">اختر نوع الجهة أولاً.</div>';
      return;
    }
    fetch(`/payments/entity-fields?type=${encodeURIComponent(type)}&entity_id=${encodeURIComponent(eid)}`)
      .then(r => r.text())
      .then(html => {
        entityWrap.innerHTML = html;
        document.dispatchEvent(new Event('payments:entityFieldsReloaded'));
      })
      .catch(() => {});
  }

  if (entityTypeSelect) entityTypeSelect.addEventListener('change', reloadEntityFields);

  // محاولة اختيار عميل تلقائيًا قبل الإرسال إذا كُتب اسم ولم يُحدّد ID
  let autoSubmitting = false;

  if (form) {
    form.addEventListener('submit', async (e) => {
      const type = entityTypeSelect ? (entityTypeSelect.value || '').toUpperCase() : '';
      const root = document.getElementById('entityFields');
      const input = root ? root.querySelector(`input[name="${type.toLowerCase()}_search"]`) : null;
      const hidden = root ? root.querySelector(`input[name="${type.toLowerCase()}_id"]`) : null;
      const generic = root ? root.querySelector('input[name="entity_id"]') : null;

      // أوتوكومبليت سريع للعميل عند الإرسال
      if (!autoSubmitting && type === 'CUSTOMER' && input && hidden && !hidden.value && input.value.trim().length >= 2) {
        e.preventDefault();
        try {
          const q = input.value.trim();
          const r = await fetch(`/payments/entity-search?type=${encodeURIComponent(type)}&q=${encodeURIComponent(q)}`);
          const data = await r.json();
          const arr = Array.isArray(data) ? data : (Array.isArray(data?.results) ? data.results : []);
          const list = arr.map(x => ({
            id: x.id ?? x.value ?? x.pk ?? x.ID ?? '',
            label: x.label ?? x.text ?? x.name ?? x.title ?? '',
            extra: x.extra ?? x.subtitle ?? x.hint ?? ''
          })).filter(x => x.id && x.label);

          if (list.length > 0) {
            const best = list[0];
            input.value = best.label;
            hidden.value = String(best.id).replace(/[^\d]/g,'');
            if (generic) generic.value = hidden.value;
            autoSubmitting = true;
            if (typeof form.requestSubmit === 'function') form.requestSubmit(); else form.submit();
            return;
          }
        } catch (_) {}
      }

      // التحقق السريع: كل Split بمبلغ > 0 لازم يحدد طريقة
      if (!container) return;
      let invalidSplit = null;
      container.querySelectorAll('.split-form').forEach(el => {
        const amountEl = el.querySelector('[name$="-amount"]');
        const methodEl = el.querySelector('select[name$="-method"]');
        const amount = parseFloat((amountEl && amountEl.value ? amountEl.value : '').replace(',', '.')) || 0;
        const method = normalizeMethod(methodEl ? methodEl.value : '');
        if (!invalidSplit && amount > 0 && !method) invalidSplit = el;
      });
      if (invalidSplit) {
        e.preventDefault();
        const mSel = invalidSplit.querySelector('select[name$="-method"]');
        if (mSel) mSel.focus();
        return;
      }

      // تنظيف الصفوف الفارغة قبل الإرسال
      container.querySelectorAll('.split-form').forEach(el => {
        const amountEl = el.querySelector('[name$="-amount"]');
        const methodEl = el.querySelector('select[name$="-method"]');
        const amount = parseFloat((amountEl && amountEl.value ? amountEl.value : '').replace(',', '.')) || 0;
        if (amount <= 0) {
          if (methodEl) methodEl.value = '';
          el.querySelectorAll('[data-field] input,[data-field] select,[data-field] textarea').forEach(inp => {
            inp.value = '';
            inp.disabled = true;
          });
        }
      });

      // حذف الصفوف التي لا تحتوي لا مبلغ ولا طريقة
      container.querySelectorAll('.split-form').forEach(el => {
        const mEl = el.querySelector('[name$="-method"]');
        const aEl = el.querySelector('[name$="-amount"]');
        const m = mEl ? (mEl.value || '').trim() : '';
        const a = aEl ? (aEl.value || '').trim() : '';
        if (!m && !a) el.remove();
      });

      // تأكيد تفعيل/تعطيل الحقول التفصيلية حسب الاختيار النهائي
      container.querySelectorAll('.split-form').forEach(el => {
        const sel = el.querySelector('select[name$="-method"]');
        applyDetailsForRow(el, (sel && sel.value ? sel.value : ''));
      });

      refreshSplits();
    });
  }

  // قراءة باراميترات الاستعلام الأولى (entity_type & entity_id) وتطبيقها
  const qs = new URLSearchParams(location.search);
  const qsEntityType = (qs.get('entity_type') || '').toUpperCase();
  const qsEntityId = qs.get('entity_id') || '';
  const entityIdInput = document.getElementById('entity_id');
  if (entityTypeSelect && qsEntityType) entityTypeSelect.value = qsEntityType;
  if (entityIdInput && qsEntityId) entityIdInput.value = qsEntityId;

  // تحميل أولي
  reloadEntityFields();
  refreshSplits();

  // ربط أزرار "إضافة ..." الديناميكية داخل حقول الجهة (إن وُجدت)
  function wireAddButtons() {
    const root = document.getElementById('entityFields');
    if (!root) return;
    [
      { btn: '#addCustomerBtn', input: 'customer_search' },
      { btn: '#addSupplierBtn', input: 'supplier_search' },
      { btn: '#addPartnerBtn',  input: 'partner_search'  }
    ].forEach(map => {
      const btn = root.querySelector(map.btn);
      const input = root.querySelector(`input[name="${map.input}"]`);
      if (!btn || !input) return;
      const base = btn.getAttribute('data-base-href') || btn.getAttribute('href');
      const ret = encodeURIComponent(window.location.pathname + window.location.search);
      const update = () => {
        const name = encodeURIComponent((input.value || '').trim());
        btn.href = `${base}?name=${name}&return_to=${ret}`;
      };
      input.addEventListener('input', update);
      update();
    });
  }

  wireAddButtons();
  document.addEventListener('payments:entityFieldsReloaded', wireAddButtons);

  // أوتوكومبليت يدوي بسيط لحقول البحث عن الكيانات
  (function () {
    const root = document.getElementById('entityFields');
    let menu = null;
    let items = [];
    let activeIndex = -1;
    let currentType = null;

    function normalizeResults(data) {
      const arr = Array.isArray(data) ? data : (Array.isArray(data?.results) ? data.results : []);
      return arr.map(x => ({
        id: x.id ?? x.value ?? x.pk ?? x.ID ?? '',
        label: x.label ?? x.text ?? x.name ?? x.title ?? '',
        extra: x.extra ?? x.subtitle ?? x.hint ?? ''
      })).filter(x => x.id && (x.label || x.extra));
    }

    function buildMenu() {
      if (!menu) {
        menu = document.createElement('div');
        menu.className = 'dropdown-menu show';
        menu.style.position = 'absolute';
        menu.style.zIndex = '2000';
        document.body.appendChild(menu);
      }
    }

    function renderMenu(input, hidden) {
      if (!menu) return;
      menu.innerHTML = '';
      items.forEach((it, idx) => {
        const a = document.createElement('a');
        a.href = '#';
        a.className = 'dropdown-item' + (idx === activeIndex ? ' active' : '');
        a.textContent = it.label + (it.extra ? ' — ' + it.extra : '');
        a.addEventListener('click', e => { e.preventDefault(); pick(it, input, hidden); });
        menu.appendChild(a);
      });

      // خيار إضافة عميل سريعًا
      if (currentType === 'CUSTOMER') {
        const divider = document.createElement('div');
        divider.className = 'dropdown-divider';
        menu.appendChild(divider);
        const add = document.createElement('a');
        add.href = '#';
        add.className = 'dropdown-item';
        add.textContent = '➕ إضافة عميل جديد…';
        add.addEventListener('click', e => {
          e.preventDefault();
          const returnTo = location.pathname + location.search;
          const url = `/customers/create?name=${encodeURIComponent(input.value.trim())}&return_to=${encodeURIComponent(returnTo)}`;
          window.location.assign(url);
        });
        menu.appendChild(add);
      }

      const rect = input.getBoundingClientRect();
      menu.style.left = (window.scrollX + rect.left) + 'px';
      menu.style.top = (window.scrollY + rect.bottom) + 'px';
      menu.style.minWidth = rect.width + 'px';
    }

    function showMenu(list, input, hidden) {
      items = list || [];
      activeIndex = items.length ? 0 : -1;
      buildMenu();
      renderMenu(input, hidden);
    }

    function hideMenu() {
      if (menu) { menu.remove(); menu = null; }
      items = []; activeIndex = -1;
    }

    function pick(it, input, hidden) {
      const generic = document.querySelector('#entityFields input[name="entity_id"]');
      input.value = it.label || it.text || it.name || '';
      hidden.value = String(it.id).replace(/[^\d]/g,'');
      if (generic) generic.value = hidden.value;
      hideMenu();
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function mount(input, hidden, type) {
      if (!input || !hidden) return;
      currentType = type;
      if (!input.id) input.id = `${type.toLowerCase()}_search`;
      input.setAttribute('autocomplete', 'off');

      input.addEventListener('input', () => {
        hidden.value = '';
        const generic = document.querySelector('#entityFields input[name="entity_id"]');
        if (generic) generic.value = '';
        const q = input.value.trim();
        if (q.length < 2) { hideMenu(); return; }
        fetch(`/payments/entity-search?type=${encodeURIComponent(type)}&q=${encodeURIComponent(q)}`)
          .then(r => r.json())
          .then(data => showMenu(normalizeResults(data), input, hidden))
          .catch(hideMenu);
      });

      input.addEventListener('keydown', e => {
        if (!menu || !items.length) return;
        if (e.key === 'ArrowDown') { e.preventDefault(); activeIndex = (activeIndex + 1) % items.length; renderMenu(input, hidden); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); activeIndex = (activeIndex - 1 + items.length) % items.length; renderMenu(input, hidden); }
        else if (e.key === 'Enter') { e.preventDefault(); const target = items[Math.max(0, activeIndex)]; if (target) pick(target, input, hidden); }
        else if (e.key === 'Escape') { hideMenu(); }
      });

      input.addEventListener('blur', () => { setTimeout(hideMenu, 120); });
    }

    function wire() {
      if (!root) return;
      ['customer','supplier','partner'].forEach(t => {
        const input = root.querySelector(`input[name="${t}_search"]`);
        const hidden = root.querySelector(`input[name="${t}_id"]`);
        if (input && hidden) mount(input, hidden, t.toUpperCase());
      });
    }

    const root = document.getElementById('entityFields');
    wire();
    document.addEventListener('payments:entityFieldsReloaded', wire);
  })();
});
