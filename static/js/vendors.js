(function () {
  "use strict";

  function fmt(n) {
    var x = Number(n || 0);
    if (!isFinite(x)) x = 0;
    return x.toFixed(2);
  }

  function directionBadge(dir) {
    if (dir === "IN") return '<span class="badge bg-success">وارد</span>';
    if (dir === "OUT") return '<span class="badge bg-danger">صادر</span>';
    return '<span class="badge bg-secondary">—</span>';
  }

  function openSettlementModal(payload) {
    var modalEl = document.getElementById("settlementModal");
    if (!modalEl) return;
    var bsModal = (window.bootstrap && window.bootstrap.Modal) ? new bootstrap.Modal(modalEl) : null;

    var dom = {
      name: document.getElementById("stlName"),
      balance: document.getElementById("stlBalance"),
      amount: document.getElementById("stlAmount"),
      currency: document.getElementById("stlCurrency"),
      method: document.getElementById("stlMethod"),
      direction: document.getElementById("stlDirectionBadge"),
      entityId: document.getElementById("stlEntityId"),
      entityType: document.getElementById("stlEntityType"),
      confirm: document.getElementById("stlConfirm"),
      print: document.getElementById("stlPrint")
    };

    var balance = Number(payload.balance || 0);
    if (!isFinite(balance)) balance = 0;
    var amount = Math.abs(balance);
    var dir = balance > 0 ? "OUT" : (balance < 0 ? "IN" : "OUT");

    dom.name.textContent = payload.name || "";
    dom.balance.innerHTML = fmt(balance) + " " + (payload.currency || "");
    dom.amount.value = fmt(amount);
    dom.currency.value = String(payload.currency || "ILS").toUpperCase();
    dom.entityId.value = payload.id || "";
    dom.entityType.value = String(payload.entityType || "").toUpperCase();
    dom.direction.innerHTML = directionBadge(dir);
    dom.confirm.disabled = (amount <= 0);

    dom.confirm.onclick = function () {
      var cfg = document.getElementById("vendors-config");
      var base = (cfg && cfg.dataset && cfg.dataset.payUrl) ? cfg.dataset.payUrl : "/payments/create";
      var amountVal = Math.max(0, Number(dom.amount.value || 0));
      if (!isFinite(amountVal) || amountVal <= 0) return;
      var et = dom.entityType.value;
      var referenceBase = (et === "SUPPLIER") ? "SupplierSettle" : (et === "PARTNER" ? "PartnerSettle" : "Settlement");
      var noteText = (et === "SUPPLIER") ? "تسوية رصيد مورد" : (et === "PARTNER" ? "تسوية رصيد شريك" : "تسوية رصيد");
      var params = new URLSearchParams({
        entity_type: et,
        entity_id: dom.entityId.value,
        direction: dir,
        total_amount: fmt(amountVal),
        currency: dom.currency.value,
        method: String(dom.method.value || "cash").toLowerCase(),
        reference: referenceBase,
        notes: noteText
      });
      window.location.href = base + "?" + params.toString();
    };

    dom.print.onclick = function () {
      var w = window.open("", "printWin");
      var now = new Date().toLocaleString();
      var methodText = dom.method.options[dom.method.selectedIndex].text;
      var dirText = dir === "IN" ? "وارد" : "صادر";
      var html =
        '<html dir="rtl"><head><meta charset="utf-8"><title>كشف تسوية</title>' +
        '<style>body{font-family:sans-serif;padding:20px} .row{margin:6px 0} .h{color:#666}</style>' +
        "</head><body>" +
        "<h3>كشف تسوية مختصر</h3>" +
        '<div class="row"><span class="h">الجهة:</span> ' + (payload.name || "") + "</div>" +
        '<div class="row"><span class="h">النوع:</span> ' + (dom.entityType.value === "PARTNER" ? "شريك" : "مورد") + "</div>" +
        '<div class="row"><span class="h">الرصيد الحالي:</span> ' + fmt(payload.balance) + " " + (payload.currency || "") + "</div>" +
        '<div class="row"><span class="h">المبلغ للتسوية:</span> ' + fmt(dom.amount.value) + " " + dom.currency.value + "</div>" +
        '<div class="row"><span class="h">الاتجاه:</span> ' + dirText + "</div>" +
        '<div class="row"><span class="h">الطريقة:</span> ' + methodText + "</div>" +
        "<hr><small>" + now + "</small>" +
        '<script>window.onload=function(){window.print();setTimeout(function(){window.close()},300)}</' + "script>" +
        "</body></html>";
      if (w && w.document) {
        w.document.write(html);
        w.document.close();
      }
    };

    if (bsModal) bsModal.show();
    else modalEl.style.display = "block";
  }

  function attachSettleButtons() {
    document.querySelectorAll(".btn-settle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openSettlementModal({
          entityType: btn.dataset.entityType,
          id: btn.dataset.id,
          name: btn.dataset.name,
          balance: Number(btn.dataset.balance || 0),
          currency: btn.dataset.currency || "ILS"
        });
      });
    });
  }

  function wireSimpleSearch(inputId, tableId, selectors) {
    var input = document.getElementById(inputId);
    var table = document.getElementById(tableId);
    if (!input || !table || !table.tBodies.length) return;
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      Array.from(table.tBodies[0].rows).forEach(function (row) {
        var haystack = selectors.map(function (sel) {
          var el = row.querySelector(sel);
          return (el && el.textContent || "").toLowerCase();
        }).join(" ");
        row.style.display = haystack.includes(q) ? "" : "none";
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireSimpleSearch("partnerSearch", "partnersTable", [".partner-name", ".partner-phone"]);
    wireSimpleSearch("supplierSearch", "suppliersTable", [".supplier-name", ".supplier-phone"]);
    attachSettleButtons();
    document.querySelectorAll("[data-bs-toggle=\"tooltip\"]").forEach(function (el) {
      if (window.bootstrap && bootstrap.Tooltip) new bootstrap.Tooltip(el);
    });
  });
})();
