(function () {
  "use strict";

  const LANG = (document.documentElement.lang || "ar").toLowerCase();
  const T = {
    reset: { ar: "إعادة", en: "Reset", fr: "Réinitialiser" },
    maxExceeded: {
      ar: "تجاوزت الحد الأقصى المسموح.",
      en: "You exceeded the maximum allowed.",
      fr: "Vous avez dépassé le maximum autorisé."
    },
    noResults: {
      ar: "لا توجد منتجات مطابقة.",
      en: "No matching products found.",
      fr: "Aucun produit correspondant trouvé."
    },
    processing: {
      ar: "جاري معالجة الدفع...",
      en: "Processing payment...",
      fr: "Traitement du paiement..."
    }
  };
  const DIGITS_AR = "٠١٢٣٤٥٦٧٨٩";
  const DIGITS_FA = "۰۱۲۳۴۵۶۷۸۹";

  function t(k) {
    return T[k]?.[LANG] || T[k]?.ar || k;
  }

  function normalizeDigits(str) {
    if (!str) return "";
    return String(str).replace(/[0-9\u0660-\u0669\u06F0-\u06F9]/g, (ch) => {
      const c = ch.charCodeAt(0);
      if (c >= 48 && c <= 57) return ch;
      const i1 = DIGITS_AR.indexOf(ch);
      if (i1 >= 0) return String(i1);
      const i2 = DIGITS_FA.indexOf(ch);
      if (i2 >= 0) return String(i2);
      return ch;
    });
  }

  function normalizeDecimal(s) {
    if (s == null) return "";
    return String(s).replace(/[٬،]/g, ",").replace(/[٫]/g, ".").replace(",", ".").trim();
  }

  function debounce(fn, tmo = 200) {
    let id;
    return function () {
      clearTimeout(id);
      const a = arguments;
      const th = this;
      id = setTimeout(function () {
        fn.apply(th, a);
      }, tmo);
    };
  }

  function csrf() {
    const m = document.querySelector('meta[name="csrf-token"]');
    if (m && m.content) return m.content;
    const i = document.querySelector('input[name="csrf_token"]');
    if (i && i.value) return i.value;
    const c = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return c ? decodeURIComponent(c[1]) : "";
  }

  function num(text) {
    const s = normalizeDecimal(normalizeDigits(String(text || ""))).replace(/[^\d.]/g, "");
    const n = parseFloat(s);
    return Number.isFinite(n) ? n : 0;
  }

  function money(n) {
    return (Number(n) || 0).toFixed(2) + " شيكل";
  }

  function prepaidRate() {
    const m = document.querySelector('meta[name="prepaid-rate"]');
    const r = m ? Number(m.content) : NaN;
    return Number.isFinite(r) ? r : 0.2;
  }

  function clampQuantity(input) {
    const raw = normalizeDigits(input.value || "");
    const val = Number(raw || 0);
    const min = input.hasAttribute("min") ? Number(input.min) : 1;
    const max = input.dataset.max
      ? Number(input.dataset.max)
      : input.hasAttribute("max")
      ? Number(input.max)
      : Infinity;
    let v = !Number.isFinite(val) || val < min ? min : val;
    if (Number.isFinite(max) && v > max) {
      alert(t("maxExceeded"));
      v = max;
    }
    input.value = String(v);
    return v;
  }

  function wireQtyButtons(root) {
    const scope = root || document;
    scope.querySelectorAll(".btn-step").forEach((btn) => {
      btn.addEventListener("click", () => {
        const dir = Number(btn.dataset.dir || 0);
        const input = btn.closest(".qty-control")?.querySelector(".qty-input");
        if (!input) return;
        const cur = clampQuantity(input);
        input.value = String(cur + dir);
        clampQuantity(input);
      });
    });
    scope.querySelectorAll(".qty-input").forEach((inp) => {
      ["input", "change", "blur"].forEach((ev) => inp.addEventListener(ev, () => clampQuantity(inp)));
      const w = inp.closest(".qty-control");
      if (w && !w.querySelector(".btn-reset")) {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "btn-reset btn btn-sm btn-outline-secondary ms-2";
        b.textContent = t("reset");
        b.addEventListener("click", () => {
          const min = inp.hasAttribute("min") ? Number(inp.min) : 1;
          inp.value = String(min);
          clampQuantity(inp);
        });
        w.appendChild(b);
      }
    });
  }

  function wireCatalogSearch() {
    const s = document.getElementById("search");
    const c = document.getElementById("products-container");
    if (!s || !c) return;
    const items = Array.from(c.querySelectorAll(".product-card, .product-row"));
    let no = document.getElementById("no-results-message");
    if (!no) {
      no = document.createElement("div");
      no.id = "no-results-message";
      no.textContent = t("noResults");
      no.className = "text-center text-muted my-3";
      no.style.display = "none";
      (c.parentElement || c).appendChild(no);
    }
    const ga = (el, n) => el.getAttribute(n) || el.querySelector(`[${n}]`)?.getAttribute(n) || "";
    const name = (el) =>
      ga(el, "data-name") ||
      el.querySelector(".card-title")?.textContent ||
      el.querySelector("td .fw-semibold, td div:first-child")?.textContent ||
      el.textContent ||
      "";
    const desc = (el) => ga(el, "data-desc") || el.querySelector(".card-text, .text-muted")?.textContent || "";
    const extra = (el) => [ga(el, "data-sku"), ga(el, "data-part"), ga(el, "data-alt")].filter(Boolean).join(" ");
    const filter = () => {
      const q = normalizeDigits((s.value || "").trim().toLowerCase());
      let v = 0;
      items.forEach((el) => {
        const hay = [name(el), desc(el), extra(el)].join(" ").toLowerCase();
        const m = !q || hay.includes(q);
        el.style.display = m ? "" : "none";
        if (m) v++;
      });
      no.style.display = v === 0 ? "" : "none";
    };
    s.addEventListener("input", debounce(filter, 120));
  }

  function detectBrand(d) {
    if (/^4\d{12,18}$/.test(d)) return "VISA";
    if (/^(5[1-5]\d{14}|2(2[2-9]\d{12}|[3-6]\d{13}|7[01]\d{12}|720\d{12}))$/.test(d)) return "MASTERCARD";
    if (/^3[47]\d{13}$/.test(d)) return "AMEX";
    if (/^6(?:011|5\d{2})\d{12}$/.test(d)) return "DISCOVER";
    return "CARD";
  }

  function wireCheckoutForm() {
    const f = document.getElementById("payment-form");
    if (!f) return;
    const methodSel = document.getElementById("payment-method");
    const cardFields = document.getElementById("card-fields");
    const holder = f.querySelector('input[name="cardholder_name"]');
    const number = f.querySelector('input[name="card_number"]');
    const expiry = f.querySelector('input[name="card_expiry"]');
    const tx = f.querySelector("#transaction_data");
    const last4 = f.querySelector("#card_last4");
    const brand = f.querySelector("#card_brand");

    function toggle() {
      const m = methodSel?.value || "card";
      if (cardFields) cardFields.style.display = m === "card" ? "" : "none";
    }

    if (methodSel) {
      methodSel.value = "card";
      Array.from(methodSel.options).forEach((o) => {
        o.disabled = o.value !== "card";
      });
      methodSel.addEventListener("change", toggle);
      toggle();
    }

    if (number) {
      number.addEventListener("input", () => {
        let v = normalizeDigits(number.value || "").replace(/\D/g, "");
        v = v.replace(/(\d{4})(?=\d)/g, "$1 ");
        number.value = v.slice(0, 19);
      });
    }

    if (expiry) {
      expiry.addEventListener("input", () => {
        let v = normalizeDigits(expiry.value || "").replace(/\D/g, "");
        if (v.length > 2) v = v.slice(0, 2) + "/" + v.slice(2);
        expiry.value = v.slice(0, 5);
      });
    }

    f.addEventListener("submit", () => {
      const btn = f.querySelector('button[type="submit"]');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> ' + t("processing");
      }
      const digits = normalizeDigits((number?.value || "").replace(/\D/g, ""));
      const br = detectBrand(digits);
      const l4 = digits.slice(-4);
      if (last4) last4.value = l4 || "";
      if (brand) brand.value = br || "CARD";
      if (tx) {
        const payload = {
          transaction_id: "TXN-" + Math.random().toString(16).slice(2, 10).toUpperCase(),
          card: {
            holder: (holder?.value || "").trim() || null,
            last4: l4 || null,
            expiry: (expiry?.value || "").trim() || null,
            brand: br || null
          },
          meta: { ua: navigator.userAgent, t: Date.now() }
        };
        try {
          const ex = (tx.value || "").trim();
          if (ex) {
            const p = JSON.parse(ex);
            Object.assign(p, payload);
            tx.value = JSON.stringify(p);
          } else {
            tx.value = JSON.stringify(payload);
          }
        } catch {
          tx.value = JSON.stringify(payload);
        }
      }
    });
  }

  async function postJSON(url, payload) {
    const r = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf(),
        "X-CSRF-Token": csrf()
      },
      body: JSON.stringify(payload || {})
    });
    let data;
    try {
      data = await r.json();
    } catch {
      data = { message: r.ok ? "ok" : "error" };
    }
    return { ok: r.ok, data };
  }

  function hideBsModal(id) {
    const el = document.getElementById(id);
    if (!el) return;
    try {
      if (window.bootstrap && bootstrap.Modal) {
        let m = bootstrap.Modal.getInstance(el);
        if (!m) m = bootstrap.Modal.getOrCreateInstance(el);
        m.hide();
        setTimeout(() => {
          m.dispose && m.dispose();
          document.querySelectorAll(".modal-backdrop").forEach((b) => b.remove());
          document.body.classList.remove("modal-open");
          document.body.style.removeProperty("padding-right");
          document.body.style.removeProperty("overflow");
        }, 200);
      } else if (window.jQuery && window.jQuery.fn.modal) {
        window.jQuery(el).modal("hide");
        setTimeout(() => {
          document.querySelectorAll(".modal-backdrop").forEach((b) => b.remove());
          document.body.classList.remove("modal-open");
          document.body.style.removeProperty("padding-right");
          document.body.style.removeProperty("overflow");
        }, 200);
      } else {
        el.classList.remove("show");
        el.style.display = "none";
        el.setAttribute("aria-hidden", "true");
        document.querySelectorAll(".modal-backdrop").forEach((b) => b.remove());
        document.body.classList.remove("modal-open");
        document.body.style.removeProperty("padding-right");
        document.body.style.removeProperty("overflow");
      }
    } catch {
      document.querySelectorAll(".modal-backdrop").forEach((b) => b.remove());
      document.body.classList.remove("modal-open");
      document.body.style.removeProperty("padding-right");
      document.body.style.removeProperty("overflow");
    }
  }

  function wireAdminProductForm() {
    const form = document.getElementById("product-form");
    const priceInput = form ? form.querySelector('input[name="price"], #price') : document.getElementById("price");

    if (priceInput) {
      priceInput.addEventListener("input", function () {
        this.value = this.value.replace(/[^\d.,٫]/g, "");
      });
      if (form) {
        form.addEventListener("submit", function () {
          priceInput.value = normalizeDecimal(priceInput.value);
        });
      }
    }

    const quickBtn = document.getElementById("quick-update-btn");
    const quickName = document.getElementById("quick-name");
    const quickPrice = document.getElementById("quick-price");
    const badge = document.getElementById("prod-status-badge");
    const toggleBtn = document.getElementById("toggle-active-btn");

    if (quickBtn && quickName && quickPrice) {
      quickBtn.addEventListener("click", async function () {
        const nameVal = (quickName.value || "").trim();
        const priceVal = normalizeDecimal(quickPrice.value);
        const payload = {};
        if (nameVal) payload.name = nameVal;
        if (priceVal !== "") payload.price = priceVal;
        const url = this.dataset.updateUrl || this.getAttribute("data-update-url") || "";
        if (!url) return;
        const { ok, data } = await postJSON(url, payload);
        if (ok) {
          const nm = form ? form.querySelector('input[name="name"], #name') : document.getElementById("name");
          if (nm && payload.name) nm.value = payload.name;
          if (priceInput && payload.price) priceInput.value = Number(payload.price).toFixed(2);
          alert(data.message || "تم التحديث");
        } else {
          alert(data.message || "تعذر التحديث");
        }
      });
    }

    if (toggleBtn) {
      toggleBtn.addEventListener("click", async function () {
        const url = this.dataset.toggleUrl || this.getAttribute("data-toggle-url") || "";
        if (!url) return;
        const { ok, data } = await postJSON(url, {});
        if (ok) {
          if (badge) {
            const off = badge.classList.contains("badge-inactive");
            if (off) {
              badge.classList.remove("badge-inactive");
              badge.classList.add("badge-active");
              badge.textContent = "مفعل";
              toggleBtn.innerHTML = '<i class="fas fa-pause me-1"></i> تعطيل';
            } else {
              badge.classList.remove("badge-active");
              badge.classList.add("badge-inactive");
              badge.textContent = "غير مفعل";
              toggleBtn.innerHTML = '<i class="fas fa-play me-1"></i> تفعيل';
            }
          }
          alert(data.message || "تم التحديث");
        } else {
          alert(data.message || "تعذر التحديث");
        }
      });
    }

    const catForm = document.getElementById("quick-category-form");
    const catSelect = document.querySelector('[name="category_id"], #category_id');

    if (catForm && catSelect) {
      catForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        const url = catForm.getAttribute("data-url") || catForm.getAttribute("action");
        const nameEl = catForm.querySelector("#qc-name");
        const nm = (nameEl?.value || "").trim();
        if (!nm) {
          alert("الاسم مطلوب");
          nameEl && nameEl.focus();
          return;
        }
        const fd = new FormData(catForm);
        fd.set("name", nm);
        const r = await fetch(url, { method: "POST", headers: { "X-CSRFToken": csrf() }, body: fd });
        let js = {};
        try {
          js = await r.json();
        } catch {
          js = {};
        }
        if (!r.ok || !js.ok) {
          alert(js.error || "تعذر إنشاء الفئة");
          return;
        }
        const opt = document.createElement("option");
        opt.value = js.id;
        opt.textContent = js.name || nm;
        opt.selected = true;
        catSelect.appendChild(opt);
        hideBsModal("quickCategoryModal");
      });
    }

    const onlinePanel = document.getElementById("online-panel");
    if (onlinePanel) {
      const pid = Number(onlinePanel.dataset.pid || "0");
      const badgeEl = document.getElementById("online-warehouse-badge");
      const alertNoOnline = document.getElementById("online-alert");
      const onlineForm = document.getElementById("online-form");
      const statusEl = document.getElementById("online-status");
      const priceEl = document.getElementById("online-price");
      const qtyEl = document.getElementById("online-qty");
      const fileEl = document.getElementById("online-file");
      const thumbEl = document.getElementById("online-thumb");
      const imgUrlEl = document.getElementById("online-image-url");
      const btnUpload = document.getElementById("btn-upload-online");
      const btnSave = document.getElementById("btn-save-online");
      const listUrl = onlinePanel.dataset.listUrl;
      const prodTpl = onlinePanel.dataset.productsUrlTemplate;
      const uploadUrl = onlinePanel.dataset.uploadUrl;
      const updTpl = onlinePanel.dataset.updateInlineUrlTemplate;
      let onlineWid = null;

      function setStatus(msg, spin) {
        statusEl.innerHTML = spin ? '<span class="inline-spinner"><i class="fas fa-spinner"></i> ' + msg + "</span>" : msg;
      }

      async function findOnlineWarehouse() {
        try {
          const res = await fetch(listUrl, { headers: { "X-CSRFToken": csrf() } });
          const js = await res.json();
          const rows = js?.data || [];
          if (!rows.length) {
            badgeEl.textContent = "لا يوجد أونلاين";
            alertNoOnline.classList.remove("d-none");
            onlineForm.classList.add("d-none");
            return null;
          }
          const def = rows.find((w) => w.online_is_default) || rows[0];
          onlineWid = def.id;
          badgeEl.classList.remove("bg-secondary");
          badgeEl.classList.add("bg-info");
          badgeEl.textContent = `Online #${def.id} - ${def.name}`;
          return onlineWid;
        } catch {
          badgeEl.textContent = "فشل الجلب";
          return null;
        }
      }

      async function loadOnlineData() {
        if (!onlineWid) return;
        setStatus("جاري تحميل بيانات الأونلاين...", true);
        try {
          const url = prodTpl.replace(/0$/, String(onlineWid));
          const res = await fetch(url, { headers: { "X-CSRFToken": csrf() } });
          const js = await res.json();
          const data = (js?.data || []).find((p) => Number(p.id) === pid);
          if (data) {
            if (priceEl) priceEl.value = data.online_price != null ? Number(data.online_price).toFixed(2) : "";
            if (qtyEl) qtyEl.value = data.quantity ?? 0;
            if (imgUrlEl && (data.online_image || "")) imgUrlEl.textContent = data.online_image || "";
          }
          setStatus("تم التحميل.");
        } catch {
          setStatus("تعذر تحميل البيانات.");
        }
      }

      async function uploadOnlineImage() {
        if (!fileEl?.files?.length) {
          alert("اختر صورة أولاً");
          return;
        }
        const fd = new FormData();
        fd.append("file", fileEl.files[0]);
        fd.append("subdir", "products");
        fd.append("max_side", "1200");
        fd.append("quality", "82");
        setStatus("جاري رفع الصورة...", true);
        try {
          const r = await fetch(uploadUrl, { method: "POST", headers: { "X-CSRFToken": csrf() }, body: fd });
          const js = await r.json();
          if (!r.ok || !js.ok) {
            alert(js.error || "فشل الرفع");
            setStatus("فشل الرفع");
            return;
          }
          const url = js.url || js.thumb_url;
          if (thumbEl && url) thumbEl.src = js.thumb_url || url;
          if (imgUrlEl) imgUrlEl.textContent = url;
          setStatus("تم رفع الصورة.");
        } catch {
          setStatus("تعذر رفع الصورة");
        }
      }

      async function saveOnline() {
        if (!onlineWid) {
          alert("لا يوجد مستودع أونلاين");
          return;
        }
        const payload = {};
        const p = (priceEl?.value || "").trim();
        if (p !== "") {
          const s = p.replace(/[٬،]/g, ",").replace(/[٫]/g, ".").replace(",", ".").replace(/[^0-9.]/g, "");
          const n = Number(s);
          if (Number.isFinite(n)) payload.online_price = n;
        }
        const q = (qtyEl?.value ?? "").toString().trim();
        if (q !== "") {
          const n = Number(q);
          if (Number.isFinite(n) && n >= 0) payload.quantity = n;
        }
        const u = (imgUrlEl?.textContent || "").trim();
        if (u) payload.online_image = u;
        if (!Object.keys(payload).length) {
          alert("لا يوجد أي تغيير للحفظ");
          return;
        }
        setStatus("جارٍ الحفظ...", true);
        try {
          const url = updTpl.replace("/0/", `/${onlineWid}/`).replace(/0$/, String(pid));
          const res = await fetch(url, {
            method: "PATCH",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
            body: JSON.stringify(payload)
          });
          const js = await res.json();
          if (!res.ok || !js.ok) {
            alert(js.error || js.message || "تعذر الحفظ");
            setStatus("تعذر الحفظ");
            return;
          }
          if (js.product && priceEl && js.product.online_price != null) {
            priceEl.value = Number(js.product.online_price).toFixed(2);
          }
          if ("quantity" in js && qtyEl) {
            qtyEl.value = js.quantity ?? qtyEl.value;
          }
          setStatus("تم الحفظ بنجاح.");
          alert("تم حفظ إعدادات الأونلاين");
        } catch {
          setStatus("تعذر الحفظ");
        }
      }

      btnUpload && btnUpload.addEventListener("click", uploadOnlineImage);
      btnSave && btnSave.addEventListener("click", saveOnline);
      (async function () {
        const ok = await findOnlineWarehouse();
        if (ok) await loadOnlineData();
      })();
    }
  }

  function updateCartCounter(val) {
    const el = document.getElementById("cart-counter");
    if (el && typeof val !== "undefined" && val !== null) el.textContent = String(val);
  }

  function recalcRowTotal(tr) {
    const qty = num(tr.querySelector('input[name="quantity"]')?.value || "1");
    const unit =
      num(tr.querySelector(".price-unit")?.getAttribute("data-unit") || tr.querySelector(".price-unit")?.textContent || "0");
    const total = qty * unit;
    const cell = tr.querySelector(".row-total");
    if (cell) cell.textContent = money(total);
    return total;
  }

  function recalcSummary() {
    const rows = [...document.querySelectorAll(".cart-row")];
    let subtotal = 0;
    rows.forEach((tr) => {
      subtotal += num(tr.querySelector(".row-total")?.textContent || "0");
    });
    const subtotalEl = document.getElementById("cart-subtotal");
    const totalEl = document.getElementById("cart-total");
    const prepaidEl = document.getElementById("cart-prepaid");
    if (subtotalEl) subtotalEl.textContent = money(subtotal);
    if (totalEl) totalEl.textContent = money(subtotal);
    if (prepaidEl) prepaidEl.textContent = money(subtotal * prepaidRate());
  }

  function applyCartJSON(tr, js) {
    if (js?.cart_count != null) updateCartCounter(js.cart_count);

    if (js?.item && tr) {
      if (js.item.quantity != null) {
        const q = tr.querySelector('input[name="quantity"]');
        if (q) q.value = js.item.quantity;
      }
      if (js.item.price != null) {
        const p = tr.querySelector(".price-unit");
        if (p) {
          p.setAttribute("data-unit", Number(js.item.price).toFixed(2));
          p.textContent = money(js.item.price);
        }
      }
      if (js.item.total != null) {
        const rt = tr.querySelector(".row-total");
        if (rt) rt.textContent = money(js.item.total);
      }
    }

    if (js?.subtotal != null || js?.total != null || js?.prepaid_amount != null) {
      const subtotalEl = document.getElementById("cart-subtotal");
      const totalEl = document.getElementById("cart-total");
      const prepaidEl = document.getElementById("cart-prepaid");
      if (js.subtotal != null && subtotalEl) subtotalEl.textContent = money(js.subtotal);
      if (js.total != null && totalEl) totalEl.textContent = money(js.total);
      if (js.prepaid_amount != null && prepaidEl) prepaidEl.textContent = money(js.prepaid_amount);
    }
  }

  function wireCartInteractions() {
    async function handleSubmit(form, tr) {
      const fd = new FormData(form);
      try {
        const r = await fetch(form.action, {
          method: "POST",
          headers: { "X-CSRFToken": csrf(), Accept: "application/json" },
          body: fd
        });
        const ct = (r.headers.get("content-type") || "").toLowerCase();
        if (!r.ok) {
          alert("فشل العملية");
          return;
        }
        if (ct.includes("application/json")) {
          const js = await r.json();
          applyCartJSON(tr, js);
        } else {
          const html = await r.text();
          const temp = document.createElement("div");
          temp.innerHTML = html;
          const newCounter = temp.querySelector("#cart-counter");
          if (newCounter) updateCartCounter(num(newCounter.textContent));
        }
        if (tr && form.matches(".cart-update-form")) recalcRowTotal(tr);
        if (tr && form.matches(".cart-remove-form")) tr.remove();
        const rows = document.querySelectorAll(".cart-row");
        if (rows.length) recalcSummary();
        else location.reload();
      } catch {
        alert("خطأ في الاتصال");
      }
    }

    document.body.addEventListener("submit", function (e) {
      const form = e.target;
      if (
        form.matches(
          '.cart-update-form, form[action*="/cart/update/"], .cart-remove-form, form[action*="/cart/remove/"]'
        )
      ) {
        e.preventDefault();
        const tr = form.closest("tr");
        handleSubmit(form, tr);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireQtyButtons();
    wireCatalogSearch();
    wireCheckoutForm();
    wireAdminProductForm();
    wireCartInteractions();
    document.querySelectorAll(".alert").forEach((el) => {
      setTimeout(() => {
        try {
          new bootstrap.Alert(el).close();
        } catch {}
      }, 5000);
    });
  });
})();
