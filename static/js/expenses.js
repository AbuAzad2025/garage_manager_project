document.addEventListener('DOMContentLoaded', function () {
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
        employeeSelect.setAttribute('disabled', 'disabled');
        if ('value' in employeeSelect) employeeSelect.value = '';
        const hidden = employeeField.querySelectorAll('input[type="hidden"]');
        hidden.forEach(h => { h.value = ''; });
      } else {
        employeeSelect.removeAttribute('disabled');
      }
    }
  }
  typeSel && typeSel.addEventListener('change', toggleEmployeeField);
  toggleEmployeeField();

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
        if (show) { inp.disabled = false; }
        else { if ('value' in inp) inp.value = ''; inp.disabled = true; }
      }
      if (show) any = true;
    });
    detailsWrap.style.display = any ? '' : 'none';
  }

  if (methodSel) {
    applyMethodDetails((methodSel.value || '').toLowerCase());
    methodSel.addEventListener('change', () => applyMethodDetails((methodSel.value || '').toLowerCase()));
  }

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
      if (lastCol !== null) baseOpts.columnDefs = [{ orderable: false, targets: [lastCol] }];
      if (hasButtons) { baseOpts.dom = "Bfrtip"; baseOpts.buttons = ["excelHtml5","print"]; }
      else { baseOpts.dom = "frtip"; }
      $(tableEl).DataTable(Object.assign({}, baseOpts, extraOpts || {}));
    }

    ['expenses-table','types-table','employees-table'].forEach(id => {
      const el = document.getElementById(id);
      if (el) initDT(el);
    });
  }
});
