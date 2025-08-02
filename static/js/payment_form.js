// File: static/js/payment_form.js
document.addEventListener('DOMContentLoaded', function() {
  // تحديث حقول الكيان ديناميكياً بناءً على النوع والقيمة الحالية
  const entityTypeSelect = document.querySelector('#entity_type');
  const entityIdHidden = document.querySelector('#current_entity_id');

  function updateEntityFields() {
    if (!entityTypeSelect) return;
    const type = entityTypeSelect.value;
    const id = entityIdHidden ? entityIdHidden.value : '';
    fetch(`/payments/entity-fields?type=${encodeURIComponent(type)}&entity_id=${encodeURIComponent(id)}`)
      .then(res => res.text())
      .then(html => {
        document.querySelector('#entityFields').innerHTML = html;
        initEntityFields();
      });
  }

  if (entityTypeSelect) {
    entityTypeSelect.addEventListener('change', updateEntityFields);
  }

  // إضافة دفعة جزئية جديدة عبر استنساخ النموذج الأخير
  const addSplitBtn = document.querySelector('#addSplit');
  if (addSplitBtn) {
    addSplitBtn.addEventListener('click', function() {
      const container = document.querySelector('#splitsContainer');
      const splitForms = container.querySelectorAll('.split-form');
      const lastForm = splitForms[splitForms.length - 1];
      const newForm = lastForm.cloneNode(true);
      const index = splitForms.length + 1;

      // تحديث العنوان والحقول
      newForm.querySelector('h5').textContent = `الدفعة الجزئية #${index}`;
      newForm.querySelectorAll('input, select, textarea').forEach(input => {
        if (input.type === 'checkbox') {
          input.checked = false;
        } else {
          input.value = '';
        }
        if (input.name) {
          input.name = input.name.replace(/splits-\d+-/, `splits-${index - 1}-`);
        }
        if (input.id) {
          input.id = input.id.replace(/splits-\d+-/, `splits-${index - 1}-`);
        }
      });

      attachSplitEvents(newForm);

      // تمكين زر الحذف للنموذج الجديد
      const removeBtn = newForm.querySelector('.remove-split');
      if (removeBtn) removeBtn.disabled = false;

      container.appendChild(newForm);
      reindexSplits();
    });
  }

  // إعادة ترقيم عناوين الدفعات الجزئية بعد حذف أو إضافة
  function reindexSplits() {
    document.querySelectorAll('.split-form').forEach((form, idx) => {
      form.querySelector('h5').textContent = `الدفعة الجزئية #${idx + 1}`;
    });
  }

  // ربط أحداث لكل نموذج دفعة جزئية (عرض التفاصيل أو حذف)
  function attachSplitEvents(splitForm) {
    const methodSelect = splitForm.querySelector('select[name$="method"]');
    const detailsDiv = splitForm.querySelector('.split-details');
    if (methodSelect && detailsDiv) {
      methodSelect.addEventListener('change', function() {
        detailsDiv.style.display = (this.value === 'check') ? 'block' : 'none';
      });
      detailsDiv.style.display = (methodSelect.value === 'check') ? 'block' : 'none';
    }
    const removeBtn = splitForm.querySelector('.remove-split');
    if (removeBtn) {
      removeBtn.addEventListener('click', function() {
        if (document.querySelectorAll('.split-form').length > 1) {
          splitForm.remove();
          reindexSplits();
        }
      });
    }
  }

  // تهيئة جميع نماذج السبلت الموجودة عند التحميل
  function initSplitForms() {
    document.querySelectorAll('.split-form').forEach(attachSplitEvents);
  }

  // ربط أحداث الحقول الديناميكية للكيان (customer، supplier، ...)
  function initEntityFields() {
    document.querySelectorAll('#entityFields select').forEach(select => {
      select.addEventListener('change', function() {
        const hidden = this.closest('.mb-3').querySelector('input[name="entity_id"]');
        if (hidden) hidden.value = this.value;
        if (entityIdHidden) entityIdHidden.value = this.value;
      });
    });
  }

  // التهيئة الأولية
  updateEntityFields();
  initSplitForms();
  initEntityFields();
});
