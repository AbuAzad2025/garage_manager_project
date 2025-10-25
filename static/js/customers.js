(function () {
  if (window.__CUSTOMERS_INIT__) { console.log("customers.js already loaded, skipping..."); return; }
  window.__CUSTOMERS_INIT__ = true;

  "use strict";

  const qs = (sel, root = document) => root.querySelector(sel);
  const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const isEmail = v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
  const getCsrf = (root = document) => {
    const meta = root.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const inp = root.querySelector('input[name="csrf_token"]');
    return inp && inp.value ? inp.value : null;
  };
  const showToast = (msg, level = "info") => {
    if (typeof window.showNotification === "function") return window.showNotification(msg, level);
    try { (level === "danger" ? console.error : console.log)(msg); } catch (_) {}
    if (!window.showNotification) alert(msg);
  };
  const clearFieldErrors = (form) => {
    form.querySelectorAll(".is-invalid").forEach(el => el.classList.remove("is-invalid"));
    form.querySelectorAll(".invalid-feedback").forEach(el => { if (el.classList.contains("d-block")) el.textContent = ""; else el.remove(); });
  };
  const applyFieldErrors = (form, errors) => {
    if (!errors) return;
    Object.entries(errors).forEach(([name, msgs]) => {
      const field = form.querySelector(`[name="${name}"]`);
      if (!field) return;
      field.classList.add("is-invalid");
      let fb = field.nextElementSibling;
      if (!fb || !fb.classList.contains("invalid-feedback")) {
        fb = document.createElement("div");
        fb.className = "invalid-feedback d-block";
        field.insertAdjacentElement("afterend", fb);
      }
      fb.textContent = Array.isArray(msgs) ? msgs.join("، ") : String(msgs || "");
    });
  };

  qsa('input[name="phone"]').forEach((phone, i) => {
    const whatsapps = qsa('input[name="whatsapp"]');
    const whatsapp = whatsapps[i];
    if (!whatsapp) return;
    phone.addEventListener("blur", () => {
      if (!whatsapp.value && phone.value) whatsapp.value = phone.value.trim();
    });
  });

  const deleteForm = qs("#deleteForm");
  const $ = window.jQuery;
  
  // ===== زر الحذف العادي =====
  qsa(".delete-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const url = btn.getAttribute("data-url") || `/customers/${btn.getAttribute("data-id")}/delete`;
      
      console.log('🗑️ حذف عادي - URL:', url);
      
      if (deleteForm && url) {
        deleteForm.setAttribute("action", url);
        
        // فتح Modal
        if ($) {
          $('#deleteModal').modal('show');
        } else {
          alert('jQuery not loaded');
        }
      }
    });
  });
  
  // تأكيد الحذف العادي
  const confirmDelete = qs("#confirmDelete");
  if (confirmDelete && deleteForm) {
    confirmDelete.addEventListener("click", () => {
      const action = deleteForm.getAttribute("action") || "";
      console.log('✅ تأكيد الحذف:', action);
      
      if (!action) {
        alert('خطأ: لا يوجد URL');
        return;
      }
      
      confirmDelete.disabled = true;
      confirmDelete.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> جاري الحذف...';
      
      deleteForm.submit();
    });
  }
  

  const advForm = qs("#customer-adv-search");
  if (advForm) {
    advForm.addEventListener("submit", e => {
      e.preventDefault();
      const params = new URLSearchParams(new FormData(advForm)).toString();
      const base = window.location.pathname;
      window.location.href = params ? `${base}?${params}` : base;
    });
  }

  const resetBtn = qs("#reset-adv-filter");
  if (resetBtn) resetBtn.addEventListener("click", () => { window.location.href = window.location.pathname; });

  const exportResultsBtn = qs("#export-results");
  if (exportResultsBtn) exportResultsBtn.addEventListener("click", () => {
    const params = new URLSearchParams(window.location.search);
    params.set("format", "csv");
    window.location.href = `${window.location.pathname}?${params}`;
  });

  const messageType = qs("#message-type");
  if (messageType) {
    const updateMessagePreview = () => {
      const type = messageType.value;
      const header = qs(".card-header h3");
      const customerName = header ? header.textContent.replace("إرسال رسالة واتساب إلى", "").trim() : "العميل";
      let msg = "";
      if (type === "balance") {
        const balanceEl = qs(".fw-bold.text-danger, .fw-bold.text-success");
        const balance = balanceEl ? balanceEl.textContent : "0.00";
        msg = `مرحباً ${customerName}،\n\nرصيد حسابك الحالي: ${balance}\n\nشكراً لتعاملك معنا.`;
      } else if (type === "invoice") {
        const opt = qs('select[name="invoice_id"] option:checked');
        const txt = opt ? opt.textContent : "فاتورة جديدة";
        msg = `مرحباً ${customerName}،\n\nلديك فاتورة جديدة: ${txt}\n\nيمكنك الاطلاع على التفاصيل من خلال لوحة التحكم.`;
      } else if (type === "payment") {
        const opt = qs('select[name="payment_id"] option:checked');
        const txt = opt ? opt.textContent : "دفعة جديدة";
        msg = `مرحباً ${customerName}،\n\nتم استلام دفعة: ${txt}\n\nشكراً لدفعك في الوقت المحدد.`;
      } else if (type === "custom") {
        const area = qs('textarea[name="custom_message"]');
        const custom = area && area.value ? area.value : "[اكتب رسالتك هنا]";
        msg = `مرحباً ${customerName},\n\n${custom}`;
      }
      const preview = qs("#message-preview");
      if (preview) preview.textContent = msg;
    };
    const toggleSections = () => {
      ["custom-message-section", "invoice-section", "payment-section"].forEach(id => {
        const el = qs(`#${id}`);
        if (el) el.classList.add("d-none");
      });
      const sectionMap = { custom: "custom-message-section", invoice: "invoice-section", payment: "payment-section" };
      const secId = sectionMap[messageType.value];
      const secEl = secId ? qs(`#${secId}`) : null;
      if (secEl) secEl.classList.remove("d-none");
      updateMessagePreview();
    };
    messageType.addEventListener("change", toggleSections);
    ["custom_message", "invoice_id", "payment_id"].forEach(name => {
      const field = qs(`[name="${name}"]`);
      if (!field) return;
      field.addEventListener("input", updateMessagePreview);
      field.addEventListener("change", updateMessagePreview);
    });
    toggleSections();
  }

  const customersTable = qs("#customersTable");
  if (customersTable && window.jQuery && window.jQuery.fn && window.jQuery.fn.DataTable) {
    const $tbl = window.jQuery(customersTable);
    
    // تحقق من البنية
    if (!$tbl.find('thead').length || !$tbl.find('tbody').length) {
      return;
    }
    
    // تحقق من وجود بيانات فعلية
    const dataRows = $tbl.find('tbody tr').not(':has(td[colspan])');
    if (dataRows.length === 0) {
      return; // لا نهيئ DataTables للجداول الفارغة
    }
    
    // تحقق من تطابق الأعمدة
    const headerCols = $tbl.find('thead tr:first th, thead tr:first td').length;
    const bodyCols = dataRows.first().find('td').length;
    
    if (headerCols !== bodyCols) {
      console.error('Customers table: column mismatch', {header: headerCols, body: bodyCols});
      return;
    }
    
    try {
        const lastCol = (customersTable.tHead && customersTable.tHead.rows[0]) ? customersTable.tHead.rows[0].cells.length - 1 : 8;
        $tbl.DataTable({
          language: { 
            url: "/static/datatables/Arabic.json",
            emptyTable: "لا توجد بيانات",
            paginate: { first: "الأول", last: "الأخير", next: "التالي", previous: "السابق" }
          },
          paging: false,
          searching: false,
          info: false,
          ordering: true,
          order: [[0, "desc"]],
          columnDefs: [{ orderable: false, targets: [lastCol] }]
        });
    } catch (e) {
      console.error('Customers DataTable initialization failed:', e);
    }
  }

  ["#customer-create-form", "#customer-edit-form"].forEach(sel => {
    const form = qs(sel);
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      const email = form.querySelector('input[name="email"]');
      const pw1 = form.querySelector('input[name="password"]');
      const pw2 = form.querySelector('input[name="confirm"]');
      if (email && email.value && !isEmail(email.value)) {
        e.preventDefault();
        email.classList.add("is-invalid");
        if (email.nextElementSibling) {
          if (!email.nextElementSibling.classList.contains("invalid-feedback")) {
            email.insertAdjacentHTML("afterend", `<div class="invalid-feedback">يرجى إدخال بريد إلكتروني صالح</div>`);
          }
        } else {
          email.insertAdjacentHTML("afterend", `<div class="invalid-feedback">يرجى إدخال بريد إلكتروني صالح</div>`);
        }
        email.focus();
        return;
      }
      if (pw1 && pw2 && pw1.value !== pw2.value) {
        e.preventDefault();
        pw2.classList.add("is-invalid");
        if (pw2.nextElementSibling) {
          if (!pw2.nextElementSibling.classList.contains("invalid-feedback")) {
            pw2.insertAdjacentHTML("afterend", `<div class="invalid-feedback">كلمة المرور غير متطابقة</div>`);
          }
        } else {
          pw2.insertAdjacentHTML("afterend", `<div class="invalid-feedback">كلمة المرور غير متطابقة</div>`);
        }
        pw2.focus();
        return;
      }
      if (sel !== "#customer-create-form") return;
      const inModal = !!form.closest(".modal");
      const ajaxEnabled = inModal || form.dataset.ajax === "1";
      if (!ajaxEnabled) return;
      e.preventDefault();
      clearFieldErrors(form);
      const csrf = getCsrf(form);
      try {
        const res = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: Object.assign(
            { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
            csrf ? { "X-CSRFToken": csrf } : {}
          )
        });
        const ct = res.headers.get("content-type") || "";
        const isJson = ct.includes("application/json");
        const data = isJson ? await res.json() : null;
        if (!res.ok || (isJson && data && data.ok === false)) {
          const message = (isJson && data && data.message) ? data.message : "فشل إنشاء العميل";
          showToast(message, "danger");
          if (isJson && data && data.errors) applyFieldErrors(form, data.errors);
          return;
        }
        const id = isJson && data ? data.id : null;
        const text = isJson && data ? (data.text || form.querySelector('[name="name"]')?.value || "عميل") : "عميل";
        showToast("تم إنشاء العميل بنجاح", "success");
        form.dispatchEvent(new CustomEvent("customer:created", { detail: { id, text }, bubbles: true }));
        const m = form.closest(".modal");
        if (m) {
          if (window.jQuery && typeof window.jQuery(m).modal === "function") window.jQuery(m).modal("hide");
          else if (window.bootstrap) (bootstrap.Modal.getInstance(m) || new bootstrap.Modal(m)).hide();
          else m.classList.remove("show");
        }
        const rt = form.querySelector('input[name="return_to"]')?.value || "";
        if (rt) window.location.href = rt;
      } catch (err) {
        console.error(err);
        showToast("خطأ بالشبكة أو السيرفر", "danger");
      }
    });
  });

  const exportForm = qs("#export-contacts-form") || qs('form[action*="/customers/export/contacts"]');
  if (exportForm) {
    exportForm.addEventListener("submit", e => {
      const sel = exportForm.querySelector('select[name="customer_ids"]');
      const options = sel ? Array.from(sel.options) : [];
      const selected = options.filter(o => o.selected);
      if (!selected.length) { e.preventDefault(); alert("يرجى اختيار عملاء على الأقل"); }
    });
  }

  document.addEventListener("customer:created", (ev) => {
    const payload = ev.detail || {};
    if (!payload?.id) return;
    const sel = document.getElementById("customer_id");
    if (!sel) return;
    const exists = Array.from(sel.options).some(o => String(o.value) === String(payload.id));
    if (!exists) {
      const opt = new Option(payload.text || "عميل", payload.id, true, true);
      sel.add(opt);
    } else {
      sel.value = String(payload.id);
    }
    if (window.jQuery) window.jQuery(sel).trigger("change");
  });

  if (window.jQuery && window.jQuery.fn && window.jQuery.fn.select2) {
    const $sel = window.jQuery("#customer_id");
    if ($sel.length) $sel.select2({ width: "100%", tags: false, createTag: () => null });
  }

  const printBtn = qs("#btn-print");
  if (printBtn) printBtn.addEventListener("click", () => window.print());
})();
