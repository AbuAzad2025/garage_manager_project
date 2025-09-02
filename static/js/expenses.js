document.addEventListener('DOMContentLoaded', function () {
  const typeSel = document.getElementById('type_id');
  const employeeField = document.getElementById('employee-field');
  const employeeSelect = employeeField ? employeeField.querySelector('select, input, .ajax-select') : null;

  function isSalarySelected() {
    if (!typeSel) return false;
    const opt = typeSel.options[typeSel.selectedIndex] || {};
    const val = (typeSel.value || '').toLowerCase();
    const txt = (opt.text || '').trim();
    const dataFlag = opt.getAttribute('data-salary') || opt.dataset.salary;
    return dataFlag === '1' || val === 'salary' || txt === 'راتب';
  }

  function setDisabled(el, disabled) {
    if (!el) return;
    const isSelect2 = el.classList && el.classList.contains('select2-hidden-accessible');
    if (isSelect2) {
      el.disabled = !!disabled;
      if (window.jQuery) jQuery(el).trigger('change.select2');
      return;
    }
    if (disabled) el.setAttribute('disabled', 'disabled'); else el.removeAttribute('disabled');
  }

  function clearFieldValues(container) {
    if (!container) return;
    container.querySelectorAll('input, select, textarea').forEach(function (inp) {
      if (inp.type === 'hidden') { inp.value = ''; return; }
      if (inp.tagName === 'SELECT') { inp.selectedIndex = -1; }
      else if ('value' in inp) { inp.value = ''; }
    });
  }

  function toggleEmployeeField() {
    if (!typeSel || !employeeField) return;
    const show = isSalarySelected();
    employeeField.style.display = show ? '' : 'none';
    if (employeeSelect) {
      setDisabled(employeeSelect, !show);
      if (!show) clearFieldValues(employeeField);
    }
  }

  if (typeSel) {
    typeSel.addEventListener('change', toggleEmployeeField);
    toggleEmployeeField();
  }

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
    detailsWrap.querySelectorAll('[data-field]').forEach(function (box) {
      const fname = box.getAttribute('data-field');
      const show = need.has(fname);
      const inp = box.querySelector('input,select,textarea');
      box.style.display = show ? '' : 'none';
      if (inp) {
        setDisabled(inp, !show);
        if (!show && 'value' in inp) inp.value = '';
      }
      if (show) any = true;
    });
    detailsWrap.style.display = any ? '' : 'none';
  }

  if (methodSel) {
    applyMethodDetails((methodSel.value || '').toLowerCase());
    methodSel.addEventListener('change', function () {
      applyMethodDetails((methodSel.value || '').toLowerCase());
    });
  }

  if (window.jQuery && $.fn && $.fn.DataTable) {
    const hasButtons = $.fn.dataTable && $.fn.dataTable.Buttons;
    const langUrl = "/static/datatables/Arabic.json";

    function initDT(tableEl, extraOpts) {
      if (!tableEl) return;
      if ($.fn.DataTable.isDataTable(tableEl)) return;
      const cols = tableEl.tHead ? tableEl.tHead.rows[0].cells.length : 0;
      const lastCol = cols ? cols - 1 : null;
      const baseOpts = {
        language: { url: langUrl },
        ordering: true,
        info: true,
        autoWidth: false,
        responsive: true,
        stateSave: true,
        pageLength: 25
      };
      if (lastCol !== null) baseOpts.columnDefs = [{ orderable: false, targets: [lastCol] }];
      if (hasButtons) { baseOpts.dom = "Bfrtip"; baseOpts.buttons = ["excelHtml5","print"]; }
      else { baseOpts.dom = "frtip"; }
      $(tableEl).DataTable(Object.assign({}, baseOpts, extraOpts || {}));
    }

    ['expenses-table','types-table','employees-table'].forEach(function(id){
      initDT(document.getElementById(id));
    });
  }
});
