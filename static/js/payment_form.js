document.addEventListener('DOMContentLoaded', function () {
  const MAX_SPLITS = 3;

  const METHOD_FIELDS = {
    "":      [],
    cash:    [],
    online:  [],
    cheque:  ['check_number','check_bank','check_due_date'],
    bank:    ['bank_transfer_ref'],
    card:    ['card_number','card_holder','card_expiry']
  };

  const container  = document.getElementById('splitsContainer');
  const addBtn     = document.getElementById('addSplit');
  const form       = document.getElementById('paymentForm');
  const template   = container.querySelector('.split-form')?.cloneNode(true);
  const entityWrap = document.getElementById('entityFields');
  const totalInput = document.querySelector('[name="total_amount"]');
  const entityTypeSelect = document.querySelector('[name="entity_type"]');

  function ensurePlaceholderOption(select) {
    if (!select) return;
    if (!select.options.length || select.options[0].value !== '') {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '— اختر الطريقة —';
      select.insertBefore(opt, select.firstChild);
    }
  }

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

  function renumberRowFields(row, i) {
    row.dataset.index = i;
    const title = row.querySelector('h5');
    if (title) title.textContent = `الدفعة الجزئية #${i + 1}`;
    row.querySelectorAll('input,select,textarea').forEach(inp => {
      if (!inp.name) return;
      const field = inp.name.split('-').pop();
      inp.name = `splits-${i}-${field}`;
      inp.id   = `splits-${i}-${field}`;
    });
    const sel = row.querySelector('select[name$="-method"]');
    if (sel) {
      ensurePlaceholderOption(sel);
      // في حال كان الصف جديدًا ولم يحدد المستخدم الطريقة
      if (!sel.value) sel.selectedIndex = 0;
    }
    const btn = row.querySelector('.remove-split');
    if (btn) btn.disabled = (i === 0);
  }

  function refreshSplits() {
    container.querySelectorAll('.split-form').forEach((el, i) => {
      renumberRowFields(el, i);
      const sel = el.querySelector('select[name$="-method"]');
      const method = (sel?.value || '').toLowerCase();
      applyDetailsForRow(el, method);
    });
    toggleAddBtn();
    updateSplitSumHint();
  }

  function createSplitElement() {
    const idx   = container.querySelectorAll('.split-form').length;
    const clone = template.cloneNode(true);

    // صِفْر قيم الحقول
    clone.querySelectorAll('input,select,textarea').forEach(el => {
      if (el.tagName === 'SELECT') {
        el.selectedIndex = 0;
      } else {
        el.value = '';
      }
      if (el.closest('[data-field]')) el.disabled = true;
    });

    const details = clone.querySelector('.split-details');
    if (details) details.style.display = 'none';

    renumberRowFields(clone, idx);
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
    }
    if (e.target.matches('[name$="-amount"]')) updateSplitSumHint();
  });

  if (totalInput) totalInput.addEventListener('input', updateSplitSumHint);

  function reloadEntityFields() {
    if (!entityTypeSelect || !entityWrap) return;
    const type = entityTypeSelect.value || '';
    const eid  = document.getElementById('entity_id')?.value || '';
    fetch(`/payments/entity-fields?type=${encodeURIComponent(type)}&entity_id=${encodeURIComponent(eid)}`)
      .then(r => r.text())
      .then(html => { entityWrap.innerHTML = html; })
      .catch(() => {});
  }

  if (entityTypeSelect) entityTypeSelect.addEventListener('change', reloadEntityFields);

  if (form) {
    form.addEventListener('submit', () => {
      // أي صف مبلغُه غير مُدخل أو <= 0: نُفرّغ طريقته ونُعطّل التفاصيل
      container.querySelectorAll('.split-form').forEach(el => {
        const amountEl = el.querySelector('[name$="-amount"]');
        const methodEl = el.querySelector('select[name$="-method"]');
        const amount = parseFloat((amountEl?.value || '').replace(',', '.')) || 0;

        if (amount <= 0) {
          if (methodEl) methodEl.value = ''; // يضمن عدم تفعيل فالديشن تفاصيل الطريقة
          el.querySelectorAll('[data-field] input,[data-field] select,[data-field] textarea').forEach(inp => {
            inp.value = '';
            inp.disabled = true;
          });
        }
      });

      // إزالة الصفوف الفارغة بالكامل (لا طريقة ولا مبلغ)
      container.querySelectorAll('.split-form').forEach(el => {
        const m = (el.querySelector('[name$="-method"]')?.value || '').trim();
        const a = (el.querySelector('[name$="-amount"]')?.value || '').trim();
        if (!m && !a) el.remove();
      });

      // تأكيد تعطيل التفاصيل للطرق غير المختارة أو غير المطلوبة
      container.querySelectorAll('.split-form').forEach(el => {
        const sel = el.querySelector('select[name$="-method"]');
        applyDetailsForRow(el, (sel?.value || '').toLowerCase());
      });

      refreshSplits();
    });
  }

  // تهيئة: تأكد من وجود placeholder في كل قوائم الطريقة
  container.querySelectorAll('.split-form select[name$="-method"]').forEach(sel => {
    ensurePlaceholderOption(sel);
    applyDetailsForRow(sel.closest('.split-form'), (sel.value || '').toLowerCase());
  });
  reloadEntityFields();
  refreshSplits();
});
