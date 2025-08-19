/* File: static/js/expenses.js */
document.addEventListener('DOMContentLoaded', function () {
  // ====== إظهار/إخفاء حقل الموظف عندما النوع = "راتب" ======
  const typeSel = document.getElementById('type_id');
  const employeeField = document.getElementById('employee-field');
  const employeeSelect = employeeField ? employeeField.querySelector('select, input, .ajax-select') : null;

  function toggleEmployeeField() {
    if (!typeSel || !employeeField) return;
    const txt = (typeSel.options[typeSel.selectedIndex] || {}).text || '';
    const isSalary = txt.trim() === 'راتب';
    employeeField.style.display = isSalary ? '' : 'none';
    if (employeeSelect) {
      if (!isSalary) {
        // تعطيل وتصفير القيمة
        employeeSelect.setAttribute('disabled', 'disabled');
        if ('value' in employeeSelect) employeeSelect.value = '';
        // تصفير المخفيين إن وُجدوا
        const hidden = employeeField.querySelectorAll('input[type="hidden"]');
        hidden.forEach(h => { h.value = ''; });
      } else {
        employeeSelect.removeAttribute('disabled');
      }
    }
  }
  typeSel && typeSel.addEventListener('change', toggleEmployeeField);
  toggleEmployeeField();

  // ====== تفاصيل طريقة الدفع الديناميكية ======
  const METHOD_FIELDS = {
    cash:   [],
    cheque: ['check_number','check_bank','check_due_date'],
    bank:   ['bank_transfer_ref'],
    card:   ['card_number','card_holder','card_expiry'],
    online: ['online_gateway','online_ref'],
    other:  []
  };

  const methodSel   = document.getElementById('payment_method');
  const detailsWrap = document.getElementById('methodDetails');

  function applyMethodDetails(method) {
    if (!detailsWrap) return;
    const need = new Set(METHOD_FIELDS[method] || []);
    let any = false;
    detailsWrap.querySelectorAll('[data-field]').forEach(box => {
      const fname = box.dataset.field;
      const show = need.has(fname);
      const inp = box.querySelector('input,select,textarea');
      box.style.display = show ? '' : 'none';
      if (inp) {
        if (show) {
          inp.disabled = false;
          // ما بنعبّي أي قيمة تلقائياً
        } else {
          // تنظيف عند الإخفاء
          if ('value' in inp) inp.value = '';
          inp.disabled = true;
        }
      }
      if (show) any = true;
    });
    detailsWrap.style.display = any ? '' : 'none';
  }

  if (methodSel) {
    applyMethodDetails((methodSel.value || '').toLowerCase());
    methodSel.addEventListener('change', () => {
      applyMethodDetails((methodSel.value || '').toLowerCase());
    });
  }

  // ====== DataTables (لو متوفر) ======
  if (window.jQuery && $.fn && $.fn.DataTable) {
    const hasButtons = $.fn.dataTable && $.fn.dataTable.Buttons;
    const langUrl = "/static/datatables/Arabic.json";

    function initDT(tableEl, extraOpts) {
      const lastCol = tableEl.tHead ? tableEl.tHead.rows[0].cells.length - 1 : null;
      const baseOpts = {
        language: { url: langUrl },
        ordering: true,
        info: true,
        autoWidth: false
      };
      if (lastCol !== null) {
        baseOpts.columnDefs = [{ orderable: false, targets: [lastCol] }];
      }
      if (hasButtons) {
        baseOpts.dom = "Bfrtip";
        baseOpts.buttons = ["excelHtml5", "print"];
      } else {
        baseOpts.dom = "frtip";
      }
      $(tableEl).DataTable(Object.assign({}, baseOpts, extraOpts || {}));
    }

    const expensesTbl  = document.getElementById('expenses-table');
    const typesTbl     = document.getElementById('types-table');
    const employeesTbl = document.getElementById('employees-table');

    expensesTbl  && initDT(expensesTbl);
    typesTbl     && initDT(typesTbl);
    employeesTbl && initDT(employeesTbl);
  }
});
