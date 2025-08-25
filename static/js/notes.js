// static/js/notes.js
(function () {
  const alertBox = document.getElementById('alertBox');
  const modal = document.getElementById('noteModal');
  const modalBody = document.getElementById('noteModalBody');
  const modalTitle = document.getElementById('noteModalTitle');
  const grid = document.getElementById('notesGrid');
  const btnOpenCreate = document.getElementById('btnOpenCreate');

  function showAlert(msg, type) {
    if (!alertBox) return;
    alertBox.textContent = msg;
    alertBox.className = 'alert alert-' + type;
    if (type === 'success') setTimeout(() => alertBox.className = 'alert d-none', 2000);
  }

  async function openCreateModal() {
    modalTitle.textContent = 'ملاحظة جديدة';
    const res = await fetch(NOTES_ENDPOINTS.createForm, { headers: { 'X-Requested-With': 'XMLHttpRequest' }});
    const html = await res.text();
    modalBody.innerHTML = html;
    $('#noteModal').modal('show');
    wireForm('#noteForm', 'create');
  }

  async function openEditModal(id) {
    modalTitle.textContent = 'تعديل الملاحظة';
    const res = await fetch(NOTES_ENDPOINTS.editForm(id), { headers: { 'X-Requested-With': 'XMLHttpRequest' }});
    const html = await res.text();
    modalBody.innerHTML = html;
    $('#noteModal').modal('show');
    wireForm('#noteForm', 'edit', id);
  }

  function cardHTML(n) {
    const badgeClass = n.priority === 'URGENT' ? 'badge-danger'
      : n.priority === 'HIGH' ? 'badge-warning'
      : n.priority === 'MEDIUM' ? 'badge-info' : 'badge-secondary';
    return `
      <div class="col-md-6 col-lg-4 mb-3" id="note-card-${n.id}">
        <div class="card note-card h-100 ${n.is_pinned ? 'border-warning' : ''}">
          <div class="card-header d-flex align-items-center justify-content-between">
            <div class="d-flex align-items-center">
              <i class="fas fa-user mr-2 text-muted"></i>
              <strong>${n.author || '-'}</strong>
            </div>
            ${n.priority ? `<span class="badge badge-pill ${badgeClass}">${n.priority}</span>` : ''}
          </div>
          <div class="card-body">
            ${n.is_pinned ? `<div class="mb-2"><i class="fas fa-thumbtack text-warning" title="مثبّت"></i></div>` : ''}
            <p class="mb-3 pre-wrap"></p>
            <div class="small text-muted d-flex flex-wrap gap-2">
              <span><i class="fas fa-clock"></i> ${n.created_at || '-'}</span>
              ${ (n.entity_type || n.entity_id) ? `<span class="ml-2"><i class="fas fa-link"></i> ${n.entity_type || ''} ${n.entity_id || ''}</span>` : '' }
            </div>
          </div>
          <div class="card-footer d-flex justify-content-between">
            <div class="btn-group">
              <button class="btn btn-sm btn-outline-primary btn-edit-note" data-id="${n.id}"><i class="fas fa-edit"></i></button>
              <button class="btn btn-sm btn-outline-danger btn-delete-note" data-id="${n.id}"><i class="fas fa-trash"></i></button>
              <button class="btn btn-sm btn-outline-warning btn-pin-note" data-id="${n.id}"><i class="fas fa-thumbtack"></i></button>
            </div>
            <a href="/notes/${n.id}" class="btn btn-sm btn-outline-secondary">تفاصيل</a>
          </div>
        </div>
      </div>`;
  }

  function wireCardActions(scope) {
    scope.querySelectorAll('.btn-edit-note').forEach(btn => {
      btn.addEventListener('click', () => openEditModal(btn.dataset.id));
    });
    scope.querySelectorAll('.btn-delete-note').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('تأكيد حذف الملاحظة؟')) return;
        const id = btn.dataset.id;
        const res = await fetch(NOTES_ENDPOINTS.delete(id), {
          method: 'POST',
          headers: {'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCSRF()}
        });
        const result = await res.json().catch(()=>({success:false}));
        if (result.success) {
          const card = document.getElementById('note-card-' + id);
          if (card) card.remove();
          showAlert('تم حذف الملاحظة.', 'success');
        } else {
          showAlert(result.error || 'فشل الحذف', 'danger');
        }
      });
    });
    scope.querySelectorAll('.btn-pin-note').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.id;
        const res = await fetch(NOTES_ENDPOINTS.togglePin(id), {
          method: 'POST',
          headers: {'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCSRF()}
        });
        const result = await res.json().catch(()=>({success:false}));
        if (result.success) {
          showAlert(result.is_pinned ? 'تم تثبيت الملاحظة.' : 'تم إلغاء التثبيت.', 'success');
          // اختيارياً: إعادة تحميل الصفحة لترتيب المثبتة أولاً
          location.reload();
        } else {
          showAlert(result.error || 'فشل العملية', 'danger');
        }
      });
    });
  }

  function getCSRF() {
    const el = document.querySelector('meta[name="csrf-token"]') ||
               document.querySelector('input[name="csrf_token"]');
    return el ? (el.content || el.value) : '';
  }

  function clearErrors(form) {
    form.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
    form.querySelectorAll('.invalid-feedback.dynamic').forEach(el => el.remove());
  }

  function addFieldError(form, fieldName, message) {
    const input = form.querySelector('[name="' + fieldName + '"]');
    if (!input) return;
    input.classList.add('is-invalid');
    const fb = document.createElement('div');
    fb.className = 'invalid-feedback dynamic';
    fb.textContent = message;
    if (input.parentElement) input.parentElement.appendChild(fb);
  }

  function wireForm(selector, mode, id) {
    const form = modalBody.querySelector(selector);
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearErrors(form);

      const action = form.getAttribute('action') || (mode === 'edit' ? NOTES_ENDPOINTS.update(id) : NOTES_ENDPOINTS.createForm);
      const res = await fetch(action, {
        method: 'POST',
        body: new FormData(form),
        headers: {'X-Requested-With': 'XMLHttpRequest'}
      });
      let result = {};
      try { result = await res.json(); } catch (_){}

      if (result && result.success) {
        $('#noteModal').modal('hide');
        showAlert(mode === 'edit' ? 'تم تحديث الملاحظة.' : 'تم إضافة الملاحظة.', 'success');

        // تحديث/إضافة الكارد
        const n = result.note;
        const exist = document.getElementById('note-card-' + n.id);
        if (exist) {
          exist.outerHTML = cardHTML(n);
          wireCardActions(document.getElementById('note-card-' + n.id));
          document.querySelector('#note-card-' + n.id + ' .pre-wrap').textContent = n.content || '';
        } else {
          grid.insertAdjacentHTML('afterbegin', cardHTML(n));
          const card = document.getElementById('note-card-' + n.id);
          card.querySelector('.pre-wrap').textContent = n.content || '';
          wireCardActions(card);
        }
      } else {
        if (result && result.errors) {
          Object.entries(result.errors).forEach(([k, v]) => addFieldError(form, k, Array.isArray(v) ? v[0] : v));
          showAlert('تحقق من الحقول.', 'danger');
        } else {
          showAlert((result && result.error) || 'حدث خطأ غير متوقع!', 'danger');
        }
      }
    });
  }

  if (btnOpenCreate && modal && modalBody) {
    btnOpenCreate.addEventListener('click', openCreateModal);
  }

  // ربط أزرار الكروت الحالية
  if (grid) wireCardActions(grid);
})();
