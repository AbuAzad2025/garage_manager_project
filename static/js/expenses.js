/* File: static/js/expenses.js */

document.addEventListener('DOMContentLoaded', function () {
  // ====== إظهار/إخفاء حقل الموظف في نموذج المصروف ======
  const typeSel = document.getElementById('type_id');
  const employeeField = document.getElementById('employee-field');
  const employeeSelect = employeeField ? employeeField.querySelector('select') : null;

  function toggleEmployeeField() {
    if (!typeSel || !employeeField || !employeeSelect) return;
    const txt = (typeSel.options[typeSel.selectedIndex] || {}).text || '';
    if (txt.trim() === 'راتب') {
      employeeField.style.display = '';
      employeeSelect.disabled = false;
    } else {
      employeeField.style.display = 'none';
      employeeSelect.disabled = true;
      try { employeeSelect.value = ''; } catch (e) {}
    }
  }
  typeSel && typeSel.addEventListener('change', toggleEmployeeField);
  toggleEmployeeField();

  // ====== DataTables موحّد لكل جداول وحدة المصاريف ======
  if (!(window.jQuery && $.fn && $.fn.DataTable)) return;

  const hasButtons = $.fn.dataTable && $.fn.dataTable.Buttons;
  const langUrl = "/static/datatables/Arabic.json"; // نفس مسار وحدة العملاء

  function initDT(tableEl, extraOpts) {
    const lastCol = tableEl.tHead ? tableEl.tHead.rows[0].cells.length - 1 : null;
    const baseOpts = {
      language: { url: langUrl },
      ordering: true,
      info: true,
      autoWidth: false
    };
    if (lastCol !== null) {
      baseOpts.columnDefs = [{ orderable: false, targets: [lastCol] }]; // عمود الإجراءات
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
});
