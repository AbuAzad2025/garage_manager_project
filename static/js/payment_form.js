// File: static/js/payment_form.js
document.addEventListener('DOMContentLoaded', function () {
  const MAX_SPLITS = 3;

  const container  = document.getElementById('splitsContainer');
  const addBtn     = document.getElementById('addSplit');
  const form       = document.getElementById('paymentForm');
  const template   = container.querySelector('.split-form')?.cloneNode(true);
  const entityWrap = document.getElementById('entityFields');
  const totalInput = document.querySelector('[name="total_amount"]');

  function toggleAddBtn() {
    const count = container.querySelectorAll('.split-form').length;
    if (addBtn) addBtn.disabled = count >= MAX_SPLITS;
  }

  function refreshSplits() {
    container.querySelectorAll('.split-form').forEach((el, i) => {
      el.dataset.index = i;
      const title = el.querySelector('h5');
      if (title) title.textContent = `الدفعة الجزئية #${i + 1}`;
      el.querySelectorAll('input,select,textarea').forEach(inp => {
        if (!inp.name) return;
        const parts = inp.name.split('-');
        const field = parts.pop();
        inp.name = `splits-${i}-${field}`;
        inp.id   = `splits-${i}-${field}`;
      });
      const btn = el.querySelector('.remove-split');
      if (btn) btn.disabled = (i === 0);
    });
    toggleAddBtn();
    updateSplitSumHint();
  }

  function createSplitElement() {
    const idx   = container.querySelectorAll('.split-form').length;
    const clone = template.cloneNode(true);
    clone.dataset.index = idx;
    clone.querySelectorAll('input,select,textarea').forEach(el => {
      if (el.tagName === 'SELECT') el.selectedIndex = 0;
      else el.value = '';
      if (!el.name) return;
      const parts = el.name.split('-');
      const field = parts.pop();
      el.name = `splits-${idx}-${field}`;
      el.id   = `splits-${idx}-${field}`;
    });
    const details = clone.querySelector('.split-details');
    if (details) details.style.display = 'none';
    return clone;
  }

  function showHideDetails(selectEl) {
    const wrapper = selectEl.closest('.split-form');
    const details = wrapper?.querySelector('.split-details');
    if (!details) return;
    const v = (selectEl.value || '').toLowerCase();
    details.style.display = ['cheque', 'bank', 'card'].includes(v) ? 'block' : 'none';
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
    if (e.target.matches('select')) showHideDetails(e.target);
    if (e.target.matches('[name$="-amount"]')) updateSplitSumHint();
    if (e.target.matches('[name$="-method"]')) updateSplitSumHint();
  });

  if (totalInput) totalInput.addEventListener('input', updateSplitSumHint);

  const entityTypeSelect = document.querySelector('[name="entity_type"]');
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
      container.querySelectorAll('.split-form').forEach(el => {
        const m = (el.querySelector('[name$="-method"]')?.value || '').trim();
        const a = (el.querySelector('[name$="-amount"]')?.value || '').trim();
        if (!m && !a) el.remove();
      });
      refreshSplits();
    });
  }

  container.querySelectorAll('.split-form select').forEach(sel => showHideDetails(sel));
  refreshSplits();
});
