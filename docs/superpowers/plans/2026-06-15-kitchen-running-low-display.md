# Kitchen "Running Low" Wall Display — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revamp the Kitchen tab into a glanceable wall display whose primary content is a full-screen grid of **running-low** items — tap a tile to add it to the shopping list (tile flips to a persistent dimmed "✓ On list"), with a small "Got it" to mark it restocked — while demoting the existing product-browse catalog to a secondary overlay.

**Architecture:** Frontend-only changes in the single-file SPA `src/frontend/index.html` (the `#page-kitchen` markup + its JS) and `src/frontend/styles/page-shell/kitchen.css`. The running-low grid is driven by the EXISTING `GET /inventory?low_stock=true` endpoint (items already carry `product_id`, `product_name`, `latest_snapshot`, `quantity`, `threshold`, `manual_low`, `is_low`). Actions reuse existing endpoints: add → `quickAddToShoppingList` (POST `/shopping-list/items`); restock → `PUT /inventory/<id>/update {quantity}` + `setProductLowStatus(productId, false)` (PUT `/inventory/products/<id>/low-status`). The image fallback reuses the `shoppingItemEmoji(name, category)` helper. **No backend changes.**

**Tech Stack:** HTML + CSS + vanilla JS in `index.html` / `kitchen.css`. No JS test framework exists for the SPA (the repo's `tests/` are Python only). Verify each task with grep + `node --check` of the inline scripts + a manual browser pass. **Do not add a JS test framework.**

---

## Data contract — running-low item (from `GET /inventory?low_stock=true` → `.inventory[]`)
```js
{
  id: int,                 // inventory item id (used by /inventory/<id>/update & /consume)
  product_id: int,
  product_name: str,
  category: str | null,
  latest_snapshot: { image_url: str } | null,
  quantity: number,
  threshold: number | null,
  manual_low: bool,
  is_low: bool,            // true (the filter guarantees it)
}
```
On-list detection: build a Set of `product_id`s from the open shopping items (`loadKitchen` already fetches `/shopping-list` into `kitchenList`).

## How to run the app for verification
The backend serves the SPA. `docker compose up -d backend` → `http://localhost:8090` → log in → **Kitchen** tab. After each task hard-refresh (Cmd/Ctrl-Shift-R). Inline-JS syntax check used throughout:
```bash
python3 -c "import re;s=open('src/frontend/index.html').read();open('/tmp/c.js','w').write(chr(10).join(re.findall(r'<script(?![^>]*\\bsrc=)[^>]*>(.*?)</script>',s,re.S)))"; node --check /tmp/c.js
```

## File structure
- **Modify:** `src/frontend/index.html` — `#page-kitchen` markup (~3579–3645) + kitchen JS (`loadKitchen` ~28712, new render/action functions).
- **Modify:** `src/frontend/styles/page-shell/kitchen.css` — styles for the low grid, tiles, header.
No new files; no backend; no other tab touched.

---

### Task 1: CSS for the running-low header, grid, and tiles

**Files:**
- Modify: `src/frontend/styles/page-shell/kitchen.css` (append at end)

- [ ] **Step 1: Append the CSS**

```css
/* --- Kitchen revamp: Running Low wall display --- */
.kitchen-low-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin: 4px 0 14px;
}
.kitchen-low-header .title { font-size: 20px; font-weight: 700; color: var(--text, #e6edf3); }
.kitchen-low-header .title .count { color: var(--color-brand, #f0883e); }
.kitchen-low-header .meta { display: flex; gap: 10px; align-items: center; color: var(--muted, #8b949e); font-size: 14px; }
.kitchen-low-header .onlist-chip {
  border: 1px solid var(--border, #3a3a3c); border-radius: 14px;
  padding: 4px 12px; cursor: pointer; color: var(--text, #e6edf3); font-size: 14px;
}
.kitchen-low-grid {
  display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
}
.kitchen-low-tile {
  position: relative; background: var(--surface2, #161b22);
  border: 1px solid var(--border, #30363d); border-radius: 14px;
  padding: 10px; display: flex; flex-direction: column; gap: 6px;
  align-items: center; text-align: center; cursor: pointer;
  min-height: 150px; user-select: none;
}
.kitchen-low-tile:active { transform: scale(0.97); }
.kitchen-low-tile.urgent { border-color: var(--color-danger, #f85149); }
.kitchen-low-tile.on-list { opacity: 0.55; }
.kitchen-low-tile .thumb {
  width: 64px; height: 64px; border-radius: 10px; object-fit: cover;
  display: flex; align-items: center; justify-content: center; font-size: 34px;
  background: var(--surface3, #222831); border: 1px solid var(--border, #30363d);
}
.kitchen-low-tile .nm { font-size: 14px; font-weight: 600; color: var(--text, #e6edf3); line-height: 1.15; }
.kitchen-low-tile .lo { font-size: 12px; color: var(--color-brand, #f0883e); }
.kitchen-low-tile.urgent .lo { color: var(--color-danger, #f85149); }
.kitchen-low-tile .onlist-badge { font-size: 12px; color: var(--color-success, #3fb950); font-weight: 600; }
.kitchen-low-tile .gotit {
  position: absolute; top: 6px; right: 6px; font-size: 11px;
  border: 1px solid var(--border, #3a3a3c); border-radius: 10px;
  padding: 2px 8px; background: var(--surface, #0d1117); color: var(--muted, #8b949e);
}
.kitchen-low-empty { text-align: center; color: var(--muted, #8b949e); padding: 48px 12px; font-size: 18px; }
.kitchen-browse-bar { margin-top: 16px; }
```

- [ ] **Step 2: Verify it loads**

Hard-refresh `http://localhost:8090` → Kitchen tab. Expected: page renders unchanged (classes not yet used), no console errors.

- [ ] **Step 3: Commit**

```bash
git add src/frontend/styles/page-shell/kitchen.css
git commit -m "style(kitchen): CSS for Running Low wall display"
```

---

### Task 2: Markup — running-low header + grid; demote the catalog

**Files:**
- Modify: `src/frontend/index.html` — `#page-kitchen` (~3579–3645)

- [ ] **Step 1: Insert the new header + grid as the FIRST children of `#page-kitchen`**

Immediately after `<div class="page" id="page-kitchen">` and BEFORE the existing `<div class="kitchen-catalog" ...>`, insert:
```html
          <div class="kitchen-low-header">
            <div class="title">🍳 Running Low · <span class="count" id="kitchen-low-count">0</span></div>
            <div class="meta">
              <span id="kitchen-low-clock"></span>
              <span class="kitchen-weather" id="kitchen-weather" title="Local weather"></span>
              <span class="onlist-chip" id="kitchen-onlist-chip" onclick="showPage('shopping')">🛒 <span id="kitchen-onlist-count">0</span> on list</span>
            </div>
          </div>
          <div class="kitchen-low-grid" id="kitchen-low-grid"></div>
          <div class="kitchen-low-empty" id="kitchen-low-empty" style="display:none">All stocked ✅</div>
```
> NOTE: there is an existing `#kitchen-weather` element inside the old `.kitchen-list-header`. Move the weather into THIS new header by deleting the old `<div class="kitchen-weather" id="kitchen-weather" ...></div>` from `.kitchen-list-header` (so `#kitchen-weather` exists exactly once — the new one). Confirm with `grep -c 'id="kitchen-weather"'` → 1.

- [ ] **Step 2: Demote the browse catalog**

Wrap the existing `<div class="kitchen-catalog" id="kitchen-catalog">…</div>` in a collapsed-by-default container and give it a Browse toggle. Immediately before `#kitchen-catalog`, insert:
```html
          <div class="kitchen-browse-bar">
            <button type="button" class="btn btn-ghost btn-sm" onclick="toggleKitchenCatalog()">＋ Browse products</button>
          </div>
```
The catalog itself already supports collapse via `toggleKitchenCatalog()` / `applyKitchenCatalogCollapsed()` and the `kitchen_catalog_collapsed` localStorage flag — Task 4 makes it default-collapsed.

- [ ] **Step 3: Verify structure**

Hard-refresh. Expected: new "Running Low · 0" header + empty grid appear at top; the old catalog still below (Task 3 fills the grid). Run:
`grep -c 'id="kitchen-weather"' src/frontend/index.html` → expect `1`.
`grep -c 'id="kitchen-low-grid"' src/frontend/index.html` → expect `1`.
No console errors.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(kitchen): running-low header + grid markup; browse toggle"
```

---

### Task 3: Load + render the running-low grid

**Files:**
- Modify: `src/frontend/index.html` — `loadKitchen()` (~28712) + new functions; state var near `let kitchenList = [];` (~7858)

- [ ] **Step 1: Add state**

Find `let kitchenList = [];` and add after it:
```javascript
      let kitchenLowItems = [];
      let kitchenOnListIds = new Set();
```

- [ ] **Step 2: Fetch low inventory inside `loadKitchen`**

In `loadKitchen()`, change the `Promise.all` fetch list to add the low-inventory call, and capture it:
```javascript
          const [catRes, listRes, lowRes] = await Promise.all([
            api("/api/kitchen/catalog"),
            api("/shopping-list"),
            api("/inventory?low_stock=true"),
          ]);
          const cat = await catRes.json();
          const list = await listRes.json();
          const low = await lowRes.json();
          if (!catRes.ok) throw new Error(cat.error || "kitchen catalog failed");
          if (!listRes.ok) throw new Error(list.error || "shopping list failed");
          kitchenCatalog = cat;
          kitchenList = (list.items || []).filter(
            (i) => i.status === "open" || i.status === "skipped",
          );
          kitchenLowItems = (low && low.inventory) || [];
          kitchenOnListIds = new Set(
            (list.items || [])
              .filter((i) => i.status === "open" && i.product_id)
              .map((i) => Number(i.product_id)),
          );
```
Then, still inside `loadKitchen()` after `renderKitchenList();`, add a call:
```javascript
          renderKitchenLowGrid();
```

- [ ] **Step 3: Add the render function**

Add near `renderKitchenList` (search `function renderKitchenList`):
```javascript
      function renderKitchenLowGrid() {
        const grid = document.getElementById("kitchen-low-grid");
        const empty = document.getElementById("kitchen-low-empty");
        const countEl = document.getElementById("kitchen-low-count");
        const onListCountEl = document.getElementById("kitchen-onlist-count");
        if (!grid) return;
        if (onListCountEl) onListCountEl.textContent = kitchenOnListIds.size;

        const items = [...kitchenLowItems].sort((a, b) => {
          const ao = Number(a.quantity) <= 0 ? 0 : 1;
          const bo = Number(b.quantity) <= 0 ? 0 : 1;
          return ao - bo || Number(a.quantity || 0) - Number(b.quantity || 0);
        });
        if (countEl) countEl.textContent = items.length;
        if (!items.length) {
          grid.innerHTML = "";
          if (empty) empty.style.display = "block";
          return;
        }
        if (empty) empty.style.display = "none";

        grid.innerHTML = items
          .map((it) => {
            const onList = kitchenOnListIds.has(Number(it.product_id));
            const out = Number(it.quantity) <= 0;
            const url = it.latest_snapshot?.image_url;
            const thumb = url
              ? `<img class="thumb" src="${escAttr(url)}" alt="" loading="lazy" />`
              : `<div class="thumb">${shoppingItemEmoji(it.product_name, it.category)}</div>`;
            const lo = out ? "out" : (it.quantity != null ? `${it.quantity} left` : "low");
            const nameJs = `decodeURIComponent('${encodeURIComponent(it.product_name || "")}')`;
            const catJs = `decodeURIComponent('${encodeURIComponent(it.category || "other")}')`;
            return `
            <div class="kitchen-low-tile ${out ? "urgent" : ""} ${onList ? "on-list" : ""}"
                 data-pid="${it.product_id}"
                 onclick="kitchenAddLowToList(${it.product_id}, ${nameJs}, ${catJs}, this)">
              ${thumb}
              <div class="nm">${escHtml(it.product_name || "Item")}</div>
              ${onList
                ? `<div class="onlist-badge">✓ On list</div>`
                : `<div class="lo">${escHtml(lo)}</div>`}
              <button type="button" class="gotit"
                      onclick="event.stopPropagation(); kitchenMarkRestocked(${it.id}, ${it.product_id}, ${it.threshold ?? "null"}, ${it.manual_low ? "true" : "false"})">Got it</button>
            </div>`;
          })
          .join("");
      }
```

- [ ] **Step 4: Verify (after Tasks 4-5 add the action fns; for now just syntax)**

Run the inline-JS syntax check (top of plan). Expected: no syntax error. (Tile clicks will error until Task 4/5 define `kitchenAddLowToList`/`kitchenMarkRestocked` — those are next.)

- [ ] **Step 5: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(kitchen): load + render running-low grid from /inventory"
```

---

### Task 4: Tap-to-add action + default-collapse the catalog

**Files:**
- Modify: `src/frontend/index.html`

- [ ] **Step 1: Add `kitchenAddLowToList`**

Add near `renderKitchenLowGrid`:
```javascript
      async function kitchenAddLowToList(productId, name, category, tileEl) {
        if (tileEl && tileEl.classList.contains("on-list")) return; // already added
        // optimistic: flip the tile immediately
        if (tileEl) {
          tileEl.classList.add("on-list");
          const lo = tileEl.querySelector(".lo");
          if (lo) { lo.className = "onlist-badge"; lo.textContent = "✓ On list"; }
        }
        if (productId) kitchenOnListIds.add(Number(productId));
        const onListCountEl = document.getElementById("kitchen-onlist-count");
        if (onListCountEl) onListCountEl.textContent = kitchenOnListIds.size;
        await quickAddToShoppingList({
          product_id: productId,
          name: name,
          category: category,
          quantity: 1,
          source: "kitchen_low",
        });
      }
```
(`quickAddToShoppingList` already toasts and refreshes the shopping list; it does not re-render the kitchen, so the optimistic flip above provides instant feedback.)

- [ ] **Step 2: Default the browse catalog to collapsed on the kitchen tab**

The collapse state is `kitchenCatalogCollapsed` (line ~7866), keyed in localStorage as `kitchen-catalog-collapsed`, default OPEN. Change its initializer to default COLLAPSED (collapsed unless the user explicitly expanded it before, i.e. stored "0"):
```javascript
// BEFORE:
      let kitchenCatalogCollapsed = (typeof localStorage !== "undefined") &&
        localStorage.getItem("kitchen-catalog-collapsed") === "1";
// AFTER:
      let kitchenCatalogCollapsed = (typeof localStorage === "undefined") ||
        localStorage.getItem("kitchen-catalog-collapsed") !== "0";
```
(`toggleKitchenCatalog` already persists "1"/"0", and the search-focus branch at ~29031 still force-expands when the user types — both keep working.)

- [ ] **Step 3: Verify**

Syntax check passes. Hard-refresh Kitchen tab on a list that has low items: tiles render; tapping a tile flips it to "✓ On list", increments the on-list chip, and toasts "Added to shopping list ✅"; the browse catalog is collapsed behind "＋ Browse products". `grep -c "function kitchenAddLowToList"` → 1.

- [ ] **Step 4: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(kitchen): tap low tile to add to shopping list; collapse browse by default"
```

---

### Task 5: "Got it" — mark restocked

**Files:**
- Modify: `src/frontend/index.html`

- [ ] **Step 1: Add `kitchenMarkRestocked`**

```javascript
      async function kitchenMarkRestocked(inventoryId, productId, threshold, manualLow) {
        try {
          // 1) Clear a manual-low flag if set.
          if (manualLow && productId) {
            await api(`/inventory/products/${productId}/low-status`, {
              method: "PUT",
              body: JSON.stringify({ manual_low: false }),
            });
          }
          // 2) If low because quantity < threshold, lift quantity to the threshold.
          const t = Number(threshold);
          if (inventoryId && t > 0) {
            await api(`/inventory/${inventoryId}/update`, {
              method: "PUT",
              body: JSON.stringify({ quantity: t }),
            });
          }
          toast("Marked restocked ✅", "success");
        } catch (err) {
          toast("Could not mark restocked", "error");
        }
        await loadKitchen(); // refresh — the item should leave the low grid
      }
```

- [ ] **Step 2: Verify**

Syntax check passes. Hard-refresh: clicking "Got it" on a low tile removes it from the grid (count drops), toasts "Marked restocked ✅". `grep -c "function kitchenMarkRestocked"` → 1.
Confirm the endpoints exist: `grep -nE "low-status|/update" src/backend/manage_inventory.py | head` (the routes `/inventory/products/<id>/low-status` PUT and `/inventory/<id>/update` PUT must be present).

- [ ] **Step 3: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(kitchen): Got it button marks a low item restocked"
```

---

### Task 6: Live clock + weather placement

**Files:**
- Modify: `src/frontend/index.html`

- [ ] **Step 1: Add a clock updater**

Add near `loadKitchenWeather`:
```javascript
      let _kitchenClockTimer = null;
      function startKitchenClock() {
        const tick = () => {
          const el = document.getElementById("kitchen-low-clock");
          if (!el) return;
          const d = new Date();
          el.textContent = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
        };
        tick();
        if (_kitchenClockTimer) clearInterval(_kitchenClockTimer);
        _kitchenClockTimer = setInterval(tick, 30000);
      }
```

- [ ] **Step 2: Start it when the kitchen loads**

In `loadKitchen()` after `renderKitchenLowGrid();`, add:
```javascript
          startKitchenClock();
```

- [ ] **Step 3: Confirm weather renders into the new header**

`_kitchenRenderWeather` / `loadKitchenWeather` target `#kitchen-weather`, which now lives in the new header (moved in Task 2). No code change needed — just confirm the weather shows in the header after load. If `#kitchen-weather` is missing, Task 2's move wasn't applied; fix that.

- [ ] **Step 4: Verify + commit**

Syntax check passes; clock shows current time in the header and updates. 
```bash
git add src/frontend/index.html
git commit -m "feat(kitchen): live clock in the running-low header"
```

---

### Task 7: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Static checks**

```bash
grep -c 'id="kitchen-weather"' src/frontend/index.html        # 1
grep -c 'id="kitchen-low-grid"' src/frontend/index.html       # 1
grep -cE "function (renderKitchenLowGrid|kitchenAddLowToList|kitchenMarkRestocked|startKitchenClock)" src/frontend/index.html  # 4
python3 -c "import re;s=open('src/frontend/index.html').read();open('/tmp/c.js','w').write(chr(10).join(re.findall(r'<script(?![^>]*\\bsrc=)[^>]*>(.*?)</script>',s,re.S)))"; node --check /tmp/c.js  # no error
```

- [ ] **Step 2: Browser pass against spec success criteria**

With a logged-in account that has low-stock items:
1. Kitchen tab opens with "Running Low · N", weather + clock + "🛒 N on list" in the header, and the low tiles as the primary grid (out-of-stock first, urgent red).
2. Items already on the shopping list render as dimmed "✓ On list".
3. Tap a tile → toast "Added to shopping list ✅", tile flips to "✓ On list", on-list count +1, no double-add on a second tap.
4. "Got it" → toast "Marked restocked ✅", tile leaves the grid, count drops.
5. "＋ Browse products" expands the existing catalog (search/chips/tiles) to add non-low items.
6. With zero low items → "All stocked ✅" empty state.
7. Open other tabs once — no console errors, no layout breakage.

- [ ] **Step 3: Final commit**

```bash
git commit -m "test(kitchen): manual verification pass — running-low display complete" --allow-empty
```

---

## Notes for the implementer
- `shoppingItemEmoji(name, category)`, `quickAddToShoppingList(...)`, `escAttr`, `escHtml`, `toast`, `showPage`, `api(...)` already exist — reuse, don't redefine.
- The running-low data is `/inventory?low_stock=true` (NOT the kitchen catalog — catalog tiles have no low/qty info). The browse catalog stays for adding non-low products.
- Keep all existing catalog/sheet/list functions intact; this revamp adds a new primary view and demotes the catalog, it does not delete the catalog code.
- No backend changes. No JS test framework — verify via grep + `node --check` + the browser pass.
