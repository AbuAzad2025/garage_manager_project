// File: static/js/payment_form.js
document.addEventListener('DOMContentLoaded', function () {
  const MAX_SPLITS = 3;

  const METHOD_FIELDS = {
    cash:   [],
    online: [],
    cheque: ['check_number','check_bank','check_due_date'],
    bank:   ['bank_transfer_ref'],
    card:   ['card_number','card_holder','card_expiry','card_cvv'] // أُضيف CVV
  };

  const container  = document.getElementById('splitsContainer');
  const addBtn     = document.getElementById('addSplit');
  const form       = document.getElementById('paymentForm');
  const template   = container.querySelector('.split-form')?.cloneNode(true);
  const entityWrap = document.getElementById('entityFields');
  const totalInput = document.querySelector('[name="total_amount"]');
  const entityTypeSelect = document.querySelector('[name="entity_type"]');
  const topMethod  = document.querySelector('[name="method"]'); // مزامنة الطريقة العلوية

  function toggleAddBtn() {
    const count = container.querySelectorAll('.split-form').length;
    if (addBtn) addBtn.disabled = count >= MAX_SPLITS;
  }

  function applyDetailsForRow(row, method) {
    const details = row.querySelector('.split-details');
    if (!details) return;
    const want = new Set(METHOD_FIELDS[method] || []);
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

  function refreshSplits() {
    container.querySelectorAll('.split-form').forEach((el, i) => {
      el.dataset.index = i;
      const title = el.querySelector('h5');
      if (title) title.textContent = `الدفعة الجزئية #${i + 1}`;

      el.querySelectorAll('input,select,textarea').forEach(inp => {
        if (!inp.name) return;
        const field = inp.name.split('-').pop();
        inp.name = `splits-${i}-${field}`;
        inp.id   = `splits-${i}-${field}`;
      });

      const btn = el.querySelector('.remove-split');
      if (btn) btn.disabled = (i === 0);

      const sel = el.querySelector('select[name$="-method"]');
      const method = (sel?.value || '').toLowerCase();
      applyDetailsForRow(el, method);
    });
    toggleAddBtn();
    updateSplitSumHint();

    // مزامنة طريقة الدفع العلوية مع أول split
    if (topMethod) {
      const firstSel = container.querySelector('.split-form select[name$="-method"]');
      if (firstSel && firstSel.value) {
        topMethod.value = firstSel.value.toUpperCase();
      }
    }
  }

  function createSplitElement() {
    const idx   = container.querySelectorAll('.split-form').length;
    const clone = template.cloneNode(true);
    clone.dataset.index = idx;

    clone.querySelectorAll('input,select,textarea').forEach(el => {
      if (el.tagName === 'SELECT') el.selectedIndex = 0;
      else el.value = '';
      if (!el.name) return;
      const field = el.name.split('-').pop();
      el.name = `splits-${idx}-${field}`;
      el.id   = `splits-${idx}-${field}`;
      // افتراضياً عطّل كل التفاصيل
      if (el.closest('[data-field]')) {
        el.disabled = true;
      }
    });

    const details = clone.querySelector('.split-details');
    if (details) details.style.display = 'none';
    return clone;
  }

  function updateSplitSumHint() {
    if (!totalInput) return;
    const hint = document.getElementById('splitSum') || (() => {
      const small = document.createElement('div');
      small.className = 'form-text';
      small.id = 'splitSum';
      totalInput.parentElement.appendChild(small);
      return small;
    })();
    let sum = 0;
    container.querySelectorAll('.split-form').forEach(el => {
      const val = parseFloat((el.querySelector('[name$="-amount"]')?.value || '').replace(',', '.')) || 0;
      sum += val;
    });
    const total = parseFloat((totalInput.value || '').replace(',', '.')) || 0;
    hint.textContent = `مجموع الدفعات الجزئية: ${sum.toFixed(2)} — المبلغ الكلي: ${total.toFixed(2)}`;
    hint.style.color = Math.abs(sum - total) < 0.01 ? '' : '#b02a37';
  }

  if (addBtn) {
    addBtn.addEventListener('click', () => {
      const count = container.querySelectorAll('.split-form').length;
      if (count >= MAX_SPLITS) return;
      container.appendChild(createSplitElement());
      refreshSplits();
    });
  }

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
      const method = (e.target.value || '').toLowerCase();
      applyDetailsForRow(row, method);
      // لو أول صف، حدث الطريقة العلوية
      if (row && row.dataset.index === '0' && topMethod) {
        topMethod.value = (e.target.value || '').toUpperCase();
      }
    }
    if (e.target.matches('[name$="-amount"]')) updateSplitSumHint();
  });

  // لو المستخدم غيّر الطريقة العلوية، انعكس ذلك على أول split (إن وُجد)
  if (topMethod) {
    topMethod.addEventListener('change', () => {
      const firstSel = container.querySelector('.split-form select[name$="-method"]');
      if (firstSel) {
        firstSel.value = (topMethod.value || '').toUpperCase();
        const row = firstSel.closest('.split-form');
        applyDetailsForRow(row, (firstSel.value || '').toLowerCase());
      }
    });
  }

  if (totalInput) totalInput.addEventListener('input', updateSplitSumHint);

  function reloadEntityFields() {
    if (!entityTypeSelect || !entityWrap) return;
    const type = entityTypeSelect.value || '';
    const eidInput = document.getElementById('entity_id');
    const eid  = eidInput?.value || '';
    // امسح قيمة المرجع عند تغيير النوع لتفادي بقاء قيمة قديمة
    if (eidInput) eidInput.value = '';
    fetch(`/payments/entity-fields?type=${encodeURIComponent(type)}&entity_id=${encodeURIComponent(eid)}`)
      .then(r => r.text())
      .then(html => { entityWrap.innerHTML = html; })
      .catch(() => {});
  }

  if (entityTypeSelect) entityTypeSelect.addEventListener('change', reloadEntityFields);

  if (form) {
    form.addEventListener('submit', () => {
      // إزالة الصفوف الفارغة
      container.querySelectorAll('.split-form').forEach(el => {
        const m = (el.querySelector('[name$="-method"]')?.value || '').trim();
        const a = (el.querySelector('[name$="-amount"]')?.value || '').trim();
        if (!m && !a) el.remove();
      });
      // تأكد أن الحقول المعطلة فعلاً disabled (حتى لا تُرسل)
      container.querySelectorAll('.split-form').forEach(el => {
        const sel = el.querySelector('select[name$="-method"]');
        applyDetailsForRow(el, (sel?.value || '').toLowerCase());
      });
      refreshSplits();
    });
  }

  // تهيئة أولية
  container.querySelectorAll('.split-form select[name$="-method"]').forEach(sel => {
    applyDetailsForRow(sel.closest('.split-form'), (sel.value || '').toLowerCase());
  });
  reloadEntityFields();
  refreshSplits();
});
