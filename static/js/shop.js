(function () {
  "use strict";

  // --- الترجمة متعددة اللغات ---
  const LANG = (document.documentElement.lang || "ar").toLowerCase();

  const T = {
    reset: {
      ar: "إعادة",
      en: "Reset",
      fr: "Réinitialiser"
    },
    maxExceeded: {
      ar: "تجاوزت الحد الأقصى المسموح.",
      en: "You exceeded the maximum allowed.",
      fr: "Vous avez dépassé le maximum autorisé."
    },
    noResults: {
      ar: "لا توجد منتجات مطابقة.",
      en: "No matching products found.",
      fr: "Aucun produit correspondant trouvé."
    }
  };

  const t = (key) => T[key]?.[LANG] || T[key]?.ar || key;

  // تضبط القيمة المدخلة حسب min/max
  function clampQuantity(input) {
    const val = Number(input.value || 0);
    const min = input.hasAttribute("min") ? Number(input.min) : 1;
    const max = input.dataset.max
      ? Number(input.dataset.max)
      : (input.hasAttribute("max") ? Number(input.max) : Infinity);

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

    scope.querySelectorAll(".btn-step").forEach(btn => {
      btn.addEventListener("click", () => {
        const dir = Number(btn.dataset.dir || 0);
        const input = btn.closest(".qty-control")?.querySelector(".qty-input");
        if (!input) return;
        const cur = clampQuantity(input);
        input.value = String(cur + dir);
        clampQuantity(input);
      });
    });

    scope.querySelectorAll(".qty-input").forEach(inp => {
      ["input", "change", "blur"].forEach(ev => {
        inp.addEventListener(ev, () => clampQuantity(inp));
      });

      // إنشاء زر إعادة إذا لم يكن موجود
      const wrapper = inp.closest(".qty-control");
      if (wrapper && !wrapper.querySelector(".btn-reset")) {
        const resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.className = "btn-reset btn btn-sm btn-outline-secondary ms-2";
        resetBtn.textContent = t("reset");

        resetBtn.addEventListener("click", () => {
          const min = inp.hasAttribute("min") ? Number(inp.min) : 1;
          inp.value = String(min);
          clampQuantity(inp);
        });

        wrapper.appendChild(resetBtn);
      }
    });
  }

  function debounce(fn, t = 200) {
    let id;
    return function (...args) {
      clearTimeout(id);
      id = setTimeout(() => fn.apply(this, args), t);
    };
  }

  function wireCatalogSearch() {
    const search = document.getElementById("search");
    const container = document.getElementById("products-container");
    const noResultsMsgId = "no-results-message";

    if (!search || !container) return;

    const cards = Array.from(container.querySelectorAll(".product-card"));

    // إنشاء عنصر رسالة عدم وجود نتائج
    let noResults = document.getElementById(noResultsMsgId);
    if (!noResults) {
      noResults = document.createElement("div");
      noResults.id = noResultsMsgId;
      noResults.textContent = t("noResults");
      noResults.className = "text-center text-muted my-3";
      noResults.style.display = "none";
      container.parentElement.appendChild(noResults);
    }

    const filter = () => {
      const q = (search.value || "").trim().toLowerCase();
      let visibleCount = 0;

      cards.forEach(card => {
        const name = card.getAttribute("data-name") || "";
        const desc = card.getAttribute("data-desc") || "";
        const match = name.toLowerCase().includes(q) || desc.toLowerCase().includes(q);
        card.style.display = match ? "" : "none";
        if (match) visibleCount++;
      });

      noResults.style.display = visibleCount === 0 ? "" : "none";
    };

    search.addEventListener("input", debounce(filter, 120));
  }

  function wireCheckoutForm() {
    const form = document.getElementById("payment-form");
    if (!form) return;

    const methodSel = document.getElementById("payment-method");
    const cardFields = document.getElementById("card-fields");
    const cardNumber = form.querySelector('input[name="card_number"]');
    const expiry = form.querySelector('input[name="expiry"]');

    function toggleCardFields() {
      const method = methodSel?.value || "card";
      if (cardFields) cardFields.style.display = method === "card" ? "" : "none";
    }

    if (methodSel) {
      methodSel.value = "card";
      Array.from(methodSel.options).forEach(opt => {
        opt.disabled = opt.value !== "card";
      });
      methodSel.addEventListener("change", toggleCardFields);
    }

    toggleCardFields();

    if (cardNumber) {
      cardNumber.addEventListener("input", () => {
        let val = (cardNumber.value || "").replace(/\D/g, "");
        val = val.replace(/(\d{4})(?=\d)/g, "$1 ");
        cardNumber.value = val.slice(0, 19);
      });
    }

    if (expiry) {
      expiry.addEventListener("input", () => {
        let val = (expiry.value || "").replace(/\D/g, "");
        if (val.length > 2) val = val.slice(0, 2) + "/" + val.slice(2);
        expiry.value = val.slice(0, 5);
      });
    }

    form.addEventListener("submit", () => {
      const btn = form.querySelector('button[type="submit"]');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري معالجة الدفع...';
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    wireQtyButtons();
    wireCatalogSearch();
    wireCheckoutForm();
  });

})();
