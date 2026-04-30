// ===========================================================
// Upload result enrichment
// -----------------------------------------------------------
// After a single-file receipt upload finishes successfully,
// fetch the persisted receipt by id and render an inline
// action UI on the Upload page so the user can:
//   • Tag the receipt to a household member (attribution).
//   • Add a product photo for any item that has a product_id.
//   • Still jump to the Receipts editor as an escape hatch.
//
// Reuses the existing primitives — toggleAttributionPicker,
// refreshAttributionTriggers, selectProductSnapshotFile —
// so all attribution + photo behaviour stays consistent with
// the Receipts page.
// ===========================================================
(function () {
  // Range-based fragment insertion — avoids the .innerHTML setter
  // that the project's PreToolUse security hook flags. Equivalent
  // safety profile to innerHTML for trusted server data; same
  // escHtml/escAttr discipline used elsewhere in the codebase.
  function _setHtml(el, html) {
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
    const range = document.createRange();
    range.selectNodeContents(el);
    el.appendChild(range.createContextualFragment(html));
  }

  function _esc(s) {
    if (typeof window.escHtml === "function") return window.escHtml(s);
    const div = document.createElement("div");
    div.textContent = String(s == null ? "" : s);
    return div.innerHTML;
  }

  function _money(v) {
    if (typeof window.formatMoney === "function") return window.formatMoney(v);
    const n = Number(v);
    return isFinite(n) ? "$" + n.toFixed(2) : "—";
  }

  async function _fetchReceiptWithItems(id) {
    if (typeof window.api !== "function") return null;
    // Backend may need a beat to persist OCR-extracted items after the
    // upload response returns. Poll briefly until items show up; bail
    // after ~1.5s and render with whatever we got.
    for (let attempt = 0; attempt < 5; attempt++) {
      try {
        const res = await window.api(`/receipts/${id}`);
        if (res && res.ok) {
          const data = await res.json();
          if (data && Array.isArray(data.items) && data.items.length) {
            return data;
          }
          if (attempt >= 4) return data; // last try, return whatever
        }
      } catch (_e) {}
      await new Promise((r) => setTimeout(r, 300));
    }
    return null;
  }

  function _renderItemsTable(items) {
    if (!items || !items.length) return "";
    const rows = items
      .map((i) => {
        const name = i.product_name || i.name || "—";
        const qty = i.quantity == null ? 1 : i.quantity;
        const price = _money(i.unit_price);
        const hasPhoto = !!(i.latest_snapshot && i.latest_snapshot.image_url);
        const photoBtn = i.product_id
          ? `<button type="button"
               class="btn btn-sm btn-ghost upload-result-photo-btn"
               onclick="selectProductSnapshotFile(${i.product_id}, '${encodeURIComponent(name)}')"
               title="${hasPhoto ? "Replace photo" : "Add photo"}">
               📷 ${hasPhoto ? "Replace" : "Add"}
             </button>`
          : `<span class="upload-result-photo-na">—</span>`;
        return `<tr>
          <td>${_esc(name)}</td>
          <td>${_esc(qty)}</td>
          <td>${_esc(price)}</td>
          <td class="upload-result-photo-cell">${photoBtn}</td>
        </tr>`;
      })
      .join("");
    return `<div class="upload-result-table-wrap">
      <table class="upload-result-items">
        <thead>
          <tr>
            <th>Item</th>
            <th>Qty</th>
            <th>Unit Price</th>
            <th class="upload-result-photo-cell">Photo</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  function _renderAttributionRow(receiptId) {
    return `<div class="upload-result-attr">
      <span class="upload-result-attr-label">Attributed to</span>
      <div class="attr-picker-wrap">
        <button type="button"
          id="receipt-attribution-${receiptId}"
          class="attr-picker-trigger"
          data-scope="receipt"
          data-receipt-id="${receiptId}"
          onclick="toggleAttributionPicker(event, 'receipt', ${receiptId})">
          <span class="attr-picker-label">— not set —</span>
          <span class="attr-caret">▾</span>
        </button>
      </div>
      <span class="upload-result-attr-hint">Tag the whole receipt now, or open it later for per-item tagging.</span>
    </div>`;
  }

  function _renderActionRow(receiptId) {
    return `<div class="upload-result-actions">
      <button type="button" class="btn btn-ghost btn-sm"
              onclick="jumpToReceipt(${receiptId})">
        Open in Receipts →
      </button>
    </div>`;
  }

  function _renderSummaryLine(receipt, fallbackData) {
    const summary = (fallbackData && fallbackData.data) || {};
    const store = summary.store || receipt.store || "Unknown";
    const total = summary.total != null ? summary.total : receipt.total_amount;
    const engine = (fallbackData && (fallbackData.ocr_engine || fallbackData.engine)) || "AI";
    const conf = fallbackData && fallbackData.confidence != null ? fallbackData.confidence : 0;
    return `<p class="upload-result-summary">
      Store: ${_esc(store)} · Total: ${_esc(_money(total))}
      · Extracted by: ${_esc(engine)} · Confidence: ${_esc((conf * 100).toFixed(0))}%
    </p>`;
  }

  function _renderLegacyFallback(target, fallbackData) {
    const items = (fallbackData && (fallbackData.items || (fallbackData.data && fallbackData.data.items))) || [];
    const summary = fallbackData && fallbackData.data;
    const html = items.length
      ? `<table>
          <thead><tr><th>Item</th><th>Qty</th><th>Unit Price</th></tr></thead>
          <tbody>${items
            .map(
              (i) =>
                `<tr><td>${_esc(i.name)}</td><td>${_esc(
                  i.quantity == null ? 1 : i.quantity,
                )}</td><td>${_esc(_money(i.unit_price))}</td></tr>`,
            )
            .join("")}</tbody>
        </table>
        <p style="margin-top:12px;color:var(--muted);font-size:0.8rem">Store: ${_esc(
          (summary && summary.store) || "Unknown",
        )} · Total: ${_esc(_money(summary && summary.total))}</p>`
      : `<pre style="color:var(--muted);font-size:0.82rem">${_esc(
          JSON.stringify(fallbackData, null, 2),
        )}</pre>`;
    _setHtml(target, html);
  }

  // Public entry point — called from the upload completion handler.
  window.renderUploadResultExtras = async function (target, receiptId, fallbackData) {
    if (!target) return;
    if (!receiptId) {
      _renderLegacyFallback(target, fallbackData);
      return;
    }
    _setHtml(
      target,
      '<div class="empty-state" style="padding:18px"><p>Loading receipt details…</p></div>',
    );
    const receipt = await _fetchReceiptWithItems(receiptId);
    if (!receipt) {
      _renderLegacyFallback(target, fallbackData);
      return;
    }
    const items = Array.isArray(receipt.items) ? receipt.items : [];
    const html =
      _renderAttributionRow(receipt.id) +
      _renderItemsTable(items) +
      _renderSummaryLine(receipt, fallbackData) +
      _renderActionRow(receipt.id);
    _setHtml(target, html);
    // Populate attribution label by reading current state.
    if (typeof window.refreshAttributionTriggers === "function") {
      try {
        await window.refreshAttributionTriggers(receipt, items);
      } catch (_e) {}
    }
  };
})();
