(function () {
  if (window.__CUSTOMERS_INIT__) {return; }
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

  let customersSearchTimer = null;
  let customersRequestId = 0;

  qsa('input[name="phone"]').forEach((phone, i) => {
    const whatsapps = qsa('input[name="whatsapp"]');
    const whatsapp = whatsapps[i];
    if (!whatsapp) return;
    phone.addEventListener("blur", () => {
      if (!whatsapp.value && phone.value) whatsapp.value = phone.value.trim();
    });
  });

  // حذف العملاء يعمل من القوالب مباشرة (list.html & detail.html)
  const bindCustomerDeleteButtons = () => {
    if (!(window.jQuery && window.jQuery.fn)) return;
    window.jQuery(".delete-btn").off("click").on("click", function(e) {
      e.preventDefault();
      const customerId = window.jQuery(this).data("id");
      const url = "/customers/" + customerId + "/delete";
      if (confirm("هل أنت متأكد من حذف هذا العميل؟\n\nملاحظة: سيتم الحذف فقط إذا لم يكن له معاملات أو رصيد.")) {
        window.jQuery("#deleteForm").attr("action", url).submit();
      }
    });
  };

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
          if (isJson && data && data.errors) applyFieldErrors(form, data.errors);
          return;
        }
        const id = isJson && data ? data.id : null;
        const text = isJson && data ? (data.text || form.querySelector('[name="name"]')?.value || "عميل") : "عميل";
        form.dispatchEvent(new CustomEvent("customer:created", { detail: { id, text }, bubbles: true }));
        const m = form.closest(".modal");
        if (m) {
          if (window.jQuery && typeof window.jQuery(m).modal === "function") {
            window.jQuery(m).modal("hide");
          } else {
            m.classList.remove("show");
          }
        }
        const rt = form.querySelector('input[name="return_to"]')?.value || "";
        if (rt) window.location.href = rt;
      } catch (err) {
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

  const initCustomerTable = () => {
    bindCustomerDeleteButtons();
    if (typeof window !== "undefined" && typeof window.enableTableSorting === "function") {
      window.enableTableSorting("#customersTable");
    }
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCustomerTable);
  } else {
    initCustomerTable();
  }

  const customersTableWrapper = qs("#customers-table-wrapper");
  const paginationWrapper = qs("#customers-pagination-wrapper");
  const customersSearchInput = qs("#customers-search");
  const customersSearchSummary = qs("#customers-search-summary");

  const fetchCustomers = (targetUrl) => {
    if (!customersTableWrapper) return;
    const urlObj = new URL(targetUrl, window.location.origin);
    urlObj.searchParams.set("ajax", "1");
    const requestId = ++customersRequestId;
    const previousMarkup = customersTableWrapper.innerHTML;
    const tbody = customersTableWrapper.querySelector("tbody");
    if (tbody && typeof window.setLoading === "function") {
      window.setLoading(tbody, true);
    }
    return fetch(urlObj.toString(), {
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json"
      }
    }).then(res => {
      if (!res.ok) throw res;
      return res.json();
    }).then(data => {
      if (requestId !== customersRequestId) return;
      if (customersTableWrapper && typeof data.table_html === "string") {
        customersTableWrapper.innerHTML = data.table_html;
      }
      if (paginationWrapper) {
        paginationWrapper.innerHTML = data.pagination_html || "";
      }
      if (customersSearchSummary && typeof data.total_filtered === "number") {
        customersSearchSummary.textContent = `إجمالي النتائج: ${data.total_filtered}`;
      }
      initCustomerTable();
      urlObj.searchParams.delete("ajax");
      const qstr = urlObj.searchParams.toString();
      const nextUrl = qstr ? `${urlObj.pathname}?${qstr}` : urlObj.pathname;
      window.history.replaceState({}, "", nextUrl);
    }).catch(() => {
      if (requestId !== customersRequestId) return;
      if (customersTableWrapper) {
        customersTableWrapper.innerHTML = previousMarkup;
        initCustomerTable();
      }
      showToast("تعذر تحديث القائمة", "danger");
    });
  };

  if (paginationWrapper) {
    paginationWrapper.addEventListener("click", (event) => {
      const link = event.target.closest("a.page-link");
      if (!link) return;
      event.preventDefault();
      fetchCustomers(link.href);
    });
  }

  if (customersSearchInput) {
    const triggerSearch = () => {
      const currentUrl = new URL(window.location.href);
      const term = customersSearchInput.value.trim();
      if (term) {
        currentUrl.searchParams.set("q", term);
      } else {
        currentUrl.searchParams.delete("q");
      }
      currentUrl.searchParams.delete("page");
      currentUrl.searchParams.set("page", "1");
      fetchCustomers(currentUrl.toString());
    };
    customersSearchInput.addEventListener("input", () => {
      clearTimeout(customersSearchTimer);
      customersSearchTimer = setTimeout(triggerSearch, 350);
    });
  }

  const printBtn = qs("#btn-print");
  if (printBtn) printBtn.addEventListener("click", () => window.print());

  const printCustomersTrigger = qs("#open-print-modal");
  const printCustomersModal = qs("#printCustomersModal");
  if (printCustomersTrigger && printCustomersModal) {
    const canUseBootstrapModal = !!(window.jQuery && window.jQuery.fn && typeof window.jQuery.fn.modal === "function");
    printCustomersTrigger.addEventListener("click", () => {
      if (canUseBootstrapModal) {
        window.jQuery(printCustomersModal).modal("show");
      } else {
        printCustomersModal.classList.add("show");
        printCustomersModal.style.display = "block";
      }
    });
    if (!canUseBootstrapModal) {
      qsa('[data-dismiss="modal"]', printCustomersModal).forEach(el => {
        el.addEventListener("click", () => {
          printCustomersModal.classList.remove("show");
          printCustomersModal.style.display = "none";
        });
      });
    }
  }

  const printOptionsForm = qs("#print-options-form");
  if (printOptionsForm) {
    const scopeInputs = qsa('input[name="scope"]', printOptionsForm);
    const rangeInputs = qsa('#print-range-fields input', printOptionsForm);
    const pageInputs = qsa('#print-page-fields input', printOptionsForm);
    const toggleScopeFields = () => {
      const selected = printOptionsForm.querySelector('input[name="scope"]:checked');
      const scopeValue = selected ? selected.value : "all";
      const rangeEnabled = scopeValue === "range";
      const pageEnabled = scopeValue === "page";
      rangeInputs.forEach(input => {
        input.disabled = !rangeEnabled;
        if (rangeEnabled) {
          input.required = true;
        } else {
          input.required = false;
        }
      });
      pageInputs.forEach(input => {
        input.disabled = !pageEnabled;
        if (pageEnabled) {
          input.required = true;
        } else {
          input.required = false;
        }
      });
    };
    scopeInputs.forEach(input => input.addEventListener("change", toggleScopeFields));
    toggleScopeFields();
  }
})();
