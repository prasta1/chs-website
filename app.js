/* Interactive bits of the CHS site. Each block no-ops on pages that lack its markup.
   Rows are already in the HTML — this only shows/hides them, so the archives are
   readable (and indexable) with JavaScript switched off. */

(function () {
  "use strict";

  // ---------------------------------------------------------------- records
  var recSearch = document.getElementById("rec-search");
  if (recSearch) {
    var recRows = [].slice.call(document.querySelectorAll("#rec-list .rec-row"));
    var recCount = document.getElementById("rec-count");
    var recChips = [].slice.call(document.querySelectorAll("#rec-chips .chip"));
    var recType = "All";

    function recFilter() {
      var q = recSearch.value.trim().toLowerCase();
      var shown = 0;
      recRows.forEach(function (row) {
        var typeOk = recType === "All" || row.dataset.type === recType;
        var qOk = !q || row.dataset.text.indexOf(q) !== -1;
        var ok = typeOk && qOk;
        row.hidden = !ok;
        if (ok) shown++;
      });
      recCount.textContent = shown === recRows.length
        ? recRows.length + " records"
        : shown + " of " + recRows.length + " records";
    }

    recSearch.addEventListener("input", recFilter);
    recChips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        recType = chip.dataset.type;
        recChips.forEach(function (c) {
          c.setAttribute("aria-pressed", String(c === chip));
        });
        recFilter();
      });
    });
  }

  // --------------------------------------------------------------- programs
  var evSearch = document.getElementById("ev-search");
  if (evSearch) {
    var evRows = [].slice.call(document.querySelectorAll("#ev-list .ev-row"));
    var evCount = document.getElementById("ev-count");
    var evVideo = document.getElementById("ev-video");
    var videoOnly = false;

    function evFilter() {
      var q = evSearch.value.trim().toLowerCase();
      var shown = 0;
      evRows.forEach(function (row) {
        var vidOk = !videoOnly || row.dataset.video === "1";
        var qOk = !q || row.dataset.text.indexOf(q) !== -1;
        var ok = vidOk && qOk;
        row.hidden = !ok;
        if (ok) shown++;
      });
      evCount.textContent = shown === evRows.length
        ? evRows.length + " programs, newest first"
        : shown + " of " + evRows.length + " programs";
    }

    evSearch.addEventListener("input", evFilter);
    evVideo.addEventListener("click", function () {
      videoOnly = !videoOnly;
      evVideo.setAttribute("aria-pressed", String(videoOnly));
      evVideo.textContent = "Video only: " + (videoOnly ? "on" : "off");
      evFilter();
    });
  }

  // ------------------------------------------------------------------ books
  var cartBox = document.getElementById("cart");
  if (cartBox) {
    var CATALOG = [
      { key: "postcards", title: "Cambridge, Vermont: From the Lens of a Camera... to a Postcard", price: 25 },
      { key: "tasteful", title: "Tasteful Traditions", price: 26.95 }
    ];
    var cart = { postcards: 0, tasteful: 0 };

    var empty = document.getElementById("cart-empty");
    var filled = document.getElementById("cart-filled");
    var lines = document.getElementById("cart-lines");
    var elSubtotal = document.getElementById("cart-subtotal");
    var elShipping = document.getElementById("cart-shipping");
    var elTotal = document.getElementById("cart-total");
    var elOrder = document.getElementById("cart-order");

    function money(n) { return "$" + n.toFixed(2); }

    function render() {
      var count = 0, subtotal = 0;
      lines.innerHTML = "";

      CATALOG.forEach(function (b) {
        var qty = cart[b.key];
        document.querySelector('[data-qty="' + b.key + '"]').textContent = qty;
        if (!qty) return;
        count += qty;
        subtotal += qty * b.price;

        var row = document.createElement("div");
        row.className = "cart-line";
        // textContent on each cell — book titles are data, never markup.
        var t = document.createElement("div"); t.className = "t"; t.textContent = b.title;
        var q = document.createElement("div"); q.className = "q"; q.textContent = qty + " ×";
        var a = document.createElement("div"); a.className = "a"; a.textContent = money(qty * b.price);
        row.appendChild(t); row.appendChild(q); row.appendChild(a);
        lines.appendChild(row);
      });

      // Design's rule: $5 for the first book, $2 for each additional, per order.
      var ship = count === 0 ? 0 : 5 + (count - 1) * 2;

      empty.hidden = count > 0;
      filled.hidden = count === 0;
      elSubtotal.textContent = money(subtotal);
      elShipping.textContent = money(ship);
      elTotal.textContent = money(subtotal + ship);

      var body = CATALOG.filter(function (b) { return cart[b.key] > 0; })
        .map(function (b) { return cart[b.key] + " x " + b.title + " — " + money(cart[b.key] * b.price); })
        .join("\n");
      elOrder.href = "mailto:info@cambridgehistoricalsociety.org"
        + "?subject=" + encodeURIComponent("Book order")
        + "&body=" + encodeURIComponent(
          body + "\n\nShipping: " + money(ship) + "\nTotal: " + money(subtotal + ship)
          + "\n\nName:\nShipping address:\nPhone:\nPreferred payment (mail / phone / in person):\n"
        );
    }

    cartBox.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-step]");
      if (!btn) return;
      var key = btn.dataset.step;
      var delta = Number(btn.dataset.delta);
      cart[key] = Math.max(0, Math.min(20, cart[key] + delta));
      render();
    });

    document.getElementById("cart-clear").addEventListener("click", function () {
      cart = { postcards: 0, tasteful: 0 };
      render();
    });

    render();
  }
})();
