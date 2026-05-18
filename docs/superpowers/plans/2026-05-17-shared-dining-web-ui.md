# Shared Dining Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Balances page, Contacts page, inline Split Receipt panel, and shared-receipt badge to the web UI, wiring them to the existing `/shared-dining/*` REST API.

**Architecture:** Single-file SPA (`src/frontend/index.html`, 39 K lines). All pages are `<div class="page" id="page-xxx">` sections shown/hidden by `nav(pageName, el)`. JS is inline in a `<script>` block; CSS is in a `<style>` block. New code follows existing patterns: `api()` for authenticated fetch, `escHtml()` / `escAttr()` for XSS safety (all user content escaped before setting innerHTML — the codebase's established pattern), `toast(msg, type)` for feedback, `formatMoney()` for currency.

**Tech Stack:** Vanilla HTML/CSS/JS, no build step. Backend: Flask + SQLAlchemy (existing `/shared-dining/*` blueprint). Tests: pytest for backend changes, manual smoke-tests for frontend.

---

## File Structure

| File | Change |
|------|--------|
| `src/frontend/index.html` | Add CSS (before `</style>`), 2 nav items, 2 page sections, nav() hooks, split-panel button + container, all JS functions |
| `src/backend/handle_receipt_upload.py` | JOIN `SharedExpense` in `list_receipts` to include `my_amount` / `shared_expense_id` |
| `tests/test_shared_dining_receipt_badge.py` | Backend unit tests for the JOIN |

---

## Task 1: Balances Page

**Files:**
- Modify: `src/frontend/index.html` (CSS + nav item + page HTML + JS)

### Context
`GET /shared-dining/balances` returns:
```json
[{"contact_id": 1, "name": "John Smith", "net_amount": 92.55}]
```
Positive `net_amount` = they owe me. Negative = I owe them.

`POST /shared-dining/contacts/<id>/settle-all` → `{"settled": N}`.

### Steps

- [ ] **Step 1: Add CSS for balances page**

Locate the unique anchor near the end of the `<style>` block:
```
  .inv-tile-title-row .inv-drag-bubble { display: none; }
```
Insert the following CSS immediately before `    </style>`:

```css
/* Shared Dining: Balances */
.balances-table { width: 100%; border-collapse: collapse; }
.balances-table th,
.balances-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border, #333); font-size: 0.9rem; }
.balances-table th { font-weight: 600; color: var(--muted, #aaa); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
.balances-table td:last-child { text-align: right; }
.balances-amount--owe { color: var(--danger, #ff453a); font-weight: 600; }
.balances-amount--owed { color: var(--success, #32d74b); font-weight: 600; }
.balances-settle-btn { font-size: 0.78rem; padding: 3px 8px; }
```

- [ ] **Step 2: Add nav item for Balances**

Locate this exact 7-line HTML block (restaurant nav item):
```html
        <div
          class="nav-item"
          id="nav-restaurant"
          style="display: none"
          onclick="nav('restaurant', this)"
        >
          <span class="nav-icon">🍽️</span> Restaurant
        </div>
```

Insert immediately after the closing `</div>`:
```html
        <div class="nav-item" id="nav-balances" onclick="nav('balances', this)">
          <span class="nav-icon">💸</span> Balances
        </div>
```

- [ ] **Step 3: Add Balances page HTML**

Locate the exact text (the blank line between page-restaurant and page-expenses):
```
        <div class="page" id="page-expenses">
```

Insert immediately before it:
```html
        <div class="page" id="page-balances">
          <div class="page-header">
            <div>
              <h1>Balances</h1>
              <p>Outstanding debts across all shared receipts</p>
            </div>
            <button class="btn btn-ghost btn-sm" onclick="loadBalances()" aria-label="Refresh">🔄</button>
          </div>
          <div class="card">
            <div class="card-header">
              <span class="card-title">Who Owes What</span>
            </div>
            <div id="balances-body">
              <div class="empty-state"><p>Loading…</p></div>
            </div>
          </div>
        </div>

```

- [ ] **Step 4: Wire nav() to load balances**

Locate:
```javascript
        if (page === "restaurant") loadRestaurant();
```

Insert immediately after it:
```javascript
        if (page === "balances") loadBalances();
        if (page === "contacts") loadContacts();
```

- [ ] **Step 5: Add loadBalances() and settleAllWithContact() JS**

Locate `    </script>` (the large inline script's closing tag, ~line 39079). Insert before it:

```javascript
      // Shared Dining: Balances
      async function loadBalances() {
        const body = document.getElementById("balances-body");
        if (!body) return;
        body.innerHTML = '<div class="empty-state"><p>Loading…</p></div>';
        const res = await api("/shared-dining/balances");
        if (!res.ok) {
          body.innerHTML = '<div class="empty-state"><p>Could not load balances.</p></div>';
          return;
        }
        const rows = await res.json();
        if (!rows.length) {
          body.innerHTML = '<div class="empty-state"><p>No outstanding balances — all settled! 🎉</p></div>';
          return;
        }
        let html = '<table class="balances-table"><thead><tr><th>Contact</th><th>Direction</th><th style="text-align:right">Amount</th><th></th></tr></thead><tbody>';
        rows.forEach(function(r) {
          const owes = r.net_amount > 0;
          const amtClass = owes ? "balances-amount--owed" : "balances-amount--owe";
          const direction = owes ? "Owes you" : "You owe";
          const display = formatMoney(Math.abs(r.net_amount));
          html += '<tr><td>' + escHtml(r.name) + '</td><td>' + escHtml(direction) + '</td>';
          html += '<td class="' + amtClass + '">' + escHtml(display) + '</td>';
          html += '<td><button class="btn btn-ghost btn-sm balances-settle-btn" onclick="settleAllWithContact(' + r.contact_id + ', \'' + escAttr(r.name) + '\')">Settle all</button></td></tr>';
        });
        html += '</tbody></table>';
        body.innerHTML = html;
      }

      async function settleAllWithContact(contactId, name) {
        if (!confirm('Mark all debts with ' + name + ' as settled?')) return;
        const res = await api('/shared-dining/contacts/' + contactId + '/settle-all', { method: 'POST' });
        if (!res.ok) { toast('Could not settle debts', 'error'); return; }
        const data = await res.json();
        toast('Settled ' + data.settled + ' debt' + (data.settled === 1 ? '' : 's') + ' with ' + name, 'success');
        loadBalances();
      }
```

- [ ] **Step 6: Smoke test**

Start app → click "💸 Balances" in sidebar → page loads → empty state shows "No outstanding balances" when none exist. After splitting a receipt, Balances shows the contact row with amount and a "Settle all" button.

- [ ] **Step 7: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(web-ui): add Balances page for shared dining"
```

---

## Task 2: Contacts Page

**Files:**
- Modify: `src/frontend/index.html` (CSS + nav item + page HTML + JS)

### Context
`GET /shared-dining/contacts` → `[{"id": 1, "name": "John", "phone": "...", "email": "..."}]`

`POST /shared-dining/contacts` body: `{"name": "...", "phone": "...", "email": "..."}` → 201 `{"id": N, "name": "..."}`

No DELETE endpoint exists — page shows list + add form.

### Steps

- [ ] **Step 1: Add CSS for contacts page**

Insert before `    </style>` (after balances CSS from Task 1):

```css
/* Shared Dining: Contacts */
.contacts-list { display: grid; gap: 10px; }
.contacts-card { display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--surface2, #2c2c2e); border-radius: 10px; }
.contacts-card__avatar { width: 40px; height: 40px; border-radius: 50%; background: var(--accent, #0a84ff); display: flex; align-items: center; justify-content: center; font-size: 1.1rem; font-weight: 700; color: #fff; flex-shrink: 0; }
.contacts-card__info { flex: 1; min-width: 0; }
.contacts-card__name { font-weight: 600; font-size: 0.95rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.contacts-card__meta { font-size: 0.8rem; color: var(--muted, #aaa); margin-top: 2px; }
.contacts-add-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
@media (max-width: 640px) { .contacts-add-form { grid-template-columns: 1fr; } }
```

- [ ] **Step 2: Add nav item for Contacts**

Locate the balances nav item from Task 1:
```html
        <div class="nav-item" id="nav-balances" onclick="nav('balances', this)">
          <span class="nav-icon">💸</span> Balances
        </div>
```

Insert immediately after its `</div>`:
```html
        <div class="nav-item" id="nav-contacts" onclick="nav('contacts', this)">
          <span class="nav-icon">👥</span> Contacts
        </div>
```

- [ ] **Step 3: Add Contacts page HTML**

Locate the balances page HTML just added in Task 1, specifically its closing `</div>` followed by the blank line before `<div class="page" id="page-expenses">`. Insert the contacts page after the balances page:

```html
        <div class="page" id="page-contacts">
          <div class="page-header">
            <div>
              <h1>Dining Contacts</h1>
              <p>Saved contacts for splitting restaurant receipts</p>
            </div>
            <button class="btn btn-ghost btn-sm" onclick="loadContacts()" aria-label="Refresh">🔄</button>
          </div>
          <div class="card" style="margin-bottom:16px">
            <div class="card-header">
              <span class="card-title">Add Contact</span>
            </div>
            <div class="contacts-add-form">
              <div class="form-group" style="margin-bottom:0">
                <label for="contact-name-input">Name *</label>
                <input id="contact-name-input" type="text" placeholder="Full name" autocomplete="off" />
              </div>
              <div class="form-group" style="margin-bottom:0">
                <label for="contact-phone-input">Phone (optional)</label>
                <input id="contact-phone-input" type="tel" placeholder="+1 555 000 0000" />
              </div>
              <div class="form-group" style="margin-bottom:0">
                <label for="contact-email-input">Email (optional)</label>
                <input id="contact-email-input" type="email" placeholder="name@example.com" />
              </div>
              <div class="form-group" style="margin-bottom:0; display:flex; align-items:flex-end">
                <button class="btn btn-primary" style="width:100%" onclick="saveContact()">Add Contact</button>
              </div>
            </div>
          </div>
          <div class="card">
            <div class="card-header">
              <span class="card-title">Saved Contacts</span>
            </div>
            <div id="contacts-body">
              <div class="empty-state"><p>Loading…</p></div>
            </div>
          </div>
        </div>

```

- [ ] **Step 4: Add loadContacts() and saveContact() JS**

Insert before `    </script>` (after balances JS from Task 1):

```javascript
      // Shared Dining: Contacts
      var _diningContacts = [];

      async function loadContacts() {
        const body = document.getElementById('contacts-body');
        if (!body) return;
        body.innerHTML = '<div class="empty-state"><p>Loading…</p></div>';
        const res = await api('/shared-dining/contacts');
        if (!res.ok) {
          body.innerHTML = '<div class="empty-state"><p>Could not load contacts.</p></div>';
          return;
        }
        _diningContacts = await res.json();
        if (!_diningContacts.length) {
          body.innerHTML = '<div class="empty-state"><p>No saved contacts yet. Add one above.</p></div>';
          return;
        }
        let html = '<div class="contacts-list">';
        _diningContacts.forEach(function(c) {
          const initial = (c.name || '?').trim().charAt(0).toUpperCase();
          const meta = [c.phone, c.email].filter(Boolean).join(' · ');
          html += '<div class="contacts-card">';
          html += '<div class="contacts-card__avatar">' + escHtml(initial) + '</div>';
          html += '<div class="contacts-card__info">';
          html += '<div class="contacts-card__name">' + escHtml(c.name) + '</div>';
          if (meta) html += '<div class="contacts-card__meta">' + escHtml(meta) + '</div>';
          html += '</div></div>';
        });
        html += '</div>';
        body.innerHTML = html;
      }

      async function saveContact() {
        const name = (document.getElementById('contact-name-input')?.value || '').trim();
        if (!name) { toast('Name is required', 'error'); return; }
        const phone = (document.getElementById('contact-phone-input')?.value || '').trim() || null;
        const email = (document.getElementById('contact-email-input')?.value || '').trim() || null;
        const res = await api('/shared-dining/contacts', {
          method: 'POST',
          body: JSON.stringify({ name, phone, email }),
        });
        if (!res.ok) {
          const err = await res.json().catch(function() { return {}; });
          toast(err.error || 'Could not save contact', 'error');
          return;
        }
        toast(name + ' added', 'success');
        document.getElementById('contact-name-input').value = '';
        document.getElementById('contact-phone-input').value = '';
        document.getElementById('contact-email-input').value = '';
        loadContacts();
      }
```

- [ ] **Step 5: Smoke test**

Navigate to "👥 Contacts" → empty state. Fill in name "Test Person" → Add Contact → row appears with avatar initial → toast "Test Person added".

- [ ] **Step 6: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(web-ui): add Contacts page for dining contacts"
```

---

## Task 3: Split Receipt Inline Panel

**Files:**
- Modify: `src/frontend/index.html` (CSS + actionsHtml modification + splitPanelHtml + JS)

### Context

Receipt detail is rendered by `viewReceipt(id)`. The `actionsHtml` template literal (line ~32297) is assembled at line ~32566:

```javascript
return `<div class="receipt-detail-stack" style="display:grid;gap:16px">
    <div>${imageHtml}</div>
    ${statsHtml}
    ${billSummaryHtml}
    ${actionsHtml}
    ${extractedHtml}
```

`POST /shared-dining/purchases/<id>` body:
```json
{
  "payment_scenario": "PAID_ALL",
  "participants": [
    {"is_self": true, "share_amount": 92.55},
    {"contact_id": 1, "share_amount": 92.55},
    {"ad_hoc_name": "Ali family", "share_amount": 92.55}
  ]
}
```
For `OWED` scenario: one non-self participant also has `"payer": true`.
Returns 201 `{"id": N, "my_amount": 92.55}`.

### Steps

- [ ] **Step 1: Add CSS for split panel**

Insert before `    </style>` (after contacts CSS from Task 2):

```css
/* Shared Dining: Split Panel */
.split-panel { border: 1px solid var(--border, #333); border-radius: 12px; padding: 16px; background: var(--surface2, #2c2c2e); }
.split-panel__title { font-weight: 700; font-size: 1rem; margin-bottom: 14px; }
.split-scenario-row { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.split-scenario-btn { flex: 1; min-width: 90px; padding: 7px 10px; border-radius: 8px; border: 1px solid var(--border, #444); background: transparent; color: var(--text, #fff); cursor: pointer; font-size: 0.84rem; text-align: center; }
.split-scenario-btn.active { background: var(--accent, #0a84ff); border-color: var(--accent, #0a84ff); color: #fff; font-weight: 600; }
.split-participants { display: grid; gap: 8px; margin-bottom: 12px; }
.split-participant-row { display: grid; grid-template-columns: 1fr 90px auto; gap: 8px; align-items: center; }
.split-participant-row input[type="number"] { text-align: right; }
.split-total-check { font-size: 0.84rem; padding: 6px 0; }
.split-total-check.ok { color: var(--success, #32d74b); }
.split-total-check.bad { color: var(--danger, #ff453a); }
.split-panel-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
.split-contact-select { font-size: 0.84rem; padding: 5px 8px; border-radius: 6px; border: 1px solid var(--border, #444); background: var(--surface3, #3a3a3c); color: var(--text, #fff); width: 100%; }
```

- [ ] **Step 2: Add "Split Receipt" button to actionsHtml**

Locate this exact line inside the `actionsHtml` template literal:
```javascript
      <button type="button" class="btn btn-ghost btn-sm" onclick="markReceiptEditorAsRestaurant(${receipt.id})">🍽️ Mark as Restaurant</button>
```

Add immediately after it (inside the same template literal):
```javascript
      <button type="button" class="btn btn-ghost btn-sm" onclick="toggleSplitPanel(${receipt.id}, ${receipt.total || 0})">💸 Split Receipt</button>
```

- [ ] **Step 3: Inject split panel container into receipt detail return HTML**

Locate the exact return statement:
```javascript
        return `<div class="receipt-detail-stack" style="display:grid;gap:16px">
    <div>${imageHtml}</div>
    ${statsHtml}
    ${billSummaryHtml}
    ${actionsHtml}
    ${extractedHtml}
```

Change to (add `splitPanelHtml` variable and slot):
```javascript
        const splitPanelHtml = `<div id="split-panel-${receipt.id}" style="display:none"></div>`;
        return `<div class="receipt-detail-stack" style="display:grid;gap:16px">
    <div>${imageHtml}</div>
    ${statsHtml}
    ${billSummaryHtml}
    ${actionsHtml}
    ${splitPanelHtml}
    ${extractedHtml}
```

- [ ] **Step 4: Add all split panel JS**

Insert before `    </script>` (after contacts JS from Task 2):

```javascript
      // Shared Dining: Split Panel
      var _sp = null;

      function toggleSplitPanel(purchaseId, total) {
        const el = document.getElementById('split-panel-' + purchaseId);
        if (!el) return;
        if (el.style.display !== 'none') { el.style.display = 'none'; el.innerHTML = ''; _sp = null; return; }
        _sp = {
          purchaseId: purchaseId,
          total: Number(total) || 0,
          scenario: 'PAID_ALL',
          participants: [{ isSelf: true, name: 'You', contactId: null, shareAmount: Number(total) || 0, isPayer: false }],
        };
        _spRecalc();
        _spRender(el);
        el.style.display = '';
      }

      function _spRecalc() {
        if (!_sp) return;
        const n = _sp.participants.length;
        if (!n) return;
        const each = Math.floor((_sp.total / n) * 100) / 100;
        const rem = Math.round((_sp.total - each * n) * 100) / 100;
        _sp.participants.forEach(function(p, i) { p.shareAmount = i === 0 ? Math.round((each + rem) * 100) / 100 : each; });
      }

      function _spRender(el) {
        if (!_sp) return;
        const contactOpts = _diningContacts.map(function(c) {
          return '<option value="' + c.id + '">' + escHtml(c.name) + '</option>';
        }).join('');

        let pRows = '';
        _sp.participants.forEach(function(p, i) {
          if (p.isSelf) {
            pRows += '<div class="split-participant-row">';
            pRows += '<span style="font-size:0.88rem;font-weight:600">You</span>';
            pRows += '<input type="number" step="0.01" min="0" value="' + p.shareAmount.toFixed(2) + '" onchange="_spSetAmt(' + i + ',this.value)" />';
            pRows += '<span></span></div>';
          } else {
            const payerCtl = _sp.scenario === 'OWED'
              ? '<label style="font-size:0.78rem;white-space:nowrap"><input type="checkbox" ' + (p.isPayer ? 'checked' : '') + ' onchange="_spSetPayer(' + i + ',this.checked)" /> Payer</label>'
              : '<button type="button" class="btn btn-ghost btn-sm" style="padding:2px 6px" onclick="_spRemove(' + i + ')">×</button>';
            pRows += '<div class="split-participant-row">';
            pRows += '<select class="split-contact-select" onchange="_spSetContact(' + i + ',this.value)">';
            pRows += '<option value="">— Ad-hoc name —</option>' + contactOpts;
            pRows += '</select>';
            pRows += '<input type="number" step="0.01" min="0" value="' + p.shareAmount.toFixed(2) + '" onchange="_spSetAmt(' + i + ',this.value)" />';
            pRows += payerCtl + '</div>';
          }
        });

        const sum = _sp.participants.reduce(function(s, p) { return s + (p.shareAmount || 0); }, 0);
        const diff = Math.round((sum - _sp.total) * 100) / 100;
        const ok = Math.abs(diff) <= 0.01;
        const totalClass = ok ? 'ok' : 'bad';
        const totalMsg = ok
          ? '✓ ' + formatMoney(_sp.total)
          : formatMoney(sum) + ' (' + (diff > 0 ? '+' : '') + formatMoney(diff) + ' vs ' + formatMoney(_sp.total) + ')';

        const scenarios = [
          { key: 'PAID_ALL', label: 'I Paid All' },
          { key: 'PAID_OWN', label: 'Paid Own' },
          { key: 'OWED', label: 'I Owe' },
        ];
        let scenHtml = '';
        scenarios.forEach(function(s) {
          scenHtml += '<button type="button" class="split-scenario-btn' + (_sp.scenario === s.key ? ' active' : '') + '" onclick="_spSetScenario(\'' + s.key + '\')">' + s.label + '</button>';
        });

        let html = '<div class="split-panel">';
        html += '<div class="split-panel__title">💸 Split ' + formatMoney(_sp.total) + '</div>';
        html += '<div class="split-scenario-row">' + scenHtml + '</div>';
        html += '<div class="split-participants">' + pRows + '</div>';
        html += '<button type="button" class="btn btn-ghost btn-sm" style="width:100%;margin-bottom:8px" onclick="_spAdd()">+ Add person</button>';
        html += '<div class="split-total-check ' + totalClass + '">' + totalMsg + '</div>';
        html += '<div class="split-panel-actions">';
        html += '<button type="button" class="btn btn-ghost btn-sm" onclick="_spCancel()">Cancel</button>';
        html += '<button type="button" class="btn btn-primary btn-sm" onclick="_spSave()"' + (ok ? '' : ' disabled') + '>Save Split</button>';
        html += '</div></div>';
        el.innerHTML = html;
      }

      function _spSetScenario(s) {
        if (!_sp) return;
        _sp.scenario = s;
        if (s !== 'OWED') _sp.participants.forEach(function(p) { p.isPayer = false; });
        const el = document.getElementById('split-panel-' + _sp.purchaseId);
        if (el) _spRender(el);
      }

      function _spAdd() {
        if (!_sp) return;
        _sp.participants.push({ isSelf: false, name: '', contactId: null, shareAmount: 0, isPayer: false });
        _spRecalc();
        const el = document.getElementById('split-panel-' + _sp.purchaseId);
        if (el) _spRender(el);
      }

      function _spRemove(idx) {
        if (!_sp || idx === 0) return;
        _sp.participants.splice(idx, 1);
        _spRecalc();
        const el = document.getElementById('split-panel-' + _sp.purchaseId);
        if (el) _spRender(el);
      }

      function _spSetAmt(idx, val) {
        if (!_sp) return;
        _sp.participants[idx].shareAmount = Math.round(Number(val) * 100) / 100 || 0;
        const el = document.getElementById('split-panel-' + _sp.purchaseId);
        if (el) _spRender(el);
      }

      function _spSetContact(idx, val) {
        if (!_sp) return;
        const cid = Number(val) || null;
        _sp.participants[idx].contactId = cid;
        if (cid) {
          const c = _diningContacts.find(function(x) { return x.id === cid; });
          if (c) _sp.participants[idx].name = c.name;
        }
        const el = document.getElementById('split-panel-' + _sp.purchaseId);
        if (el) _spRender(el);
      }

      function _spSetPayer(idx, checked) {
        if (!_sp) return;
        _sp.participants.forEach(function(p, i) { p.isPayer = (i === idx && checked); });
        const el = document.getElementById('split-panel-' + _sp.purchaseId);
        if (el) _spRender(el);
      }

      function _spCancel() {
        if (!_sp) return;
        const el = document.getElementById('split-panel-' + _sp.purchaseId);
        if (el) { el.style.display = 'none'; el.innerHTML = ''; }
        _sp = null;
      }

      async function _spSave() {
        if (!_sp) return;
        const participants = _sp.participants.map(function(p) {
          const obj = { is_self: p.isSelf, share_amount: p.shareAmount };
          if (!p.isSelf) {
            if (p.contactId) { obj.contact_id = p.contactId; }
            else { obj.ad_hoc_name = p.name || 'Guest'; }
            if (_sp.scenario === 'OWED' && p.isPayer) obj.payer = true;
          }
          return obj;
        });
        const res = await api('/shared-dining/purchases/' + _sp.purchaseId, {
          method: 'POST',
          body: JSON.stringify({ payment_scenario: _sp.scenario, participants: participants }),
        });
        const data = await res.json().catch(function() { return {}; });
        if (!res.ok) { toast(data.error || 'Could not save split', 'error'); return; }
        toast('Split saved — your share: ' + formatMoney(data.my_amount), 'success');
        _spCancel();
      }
```

- [ ] **Step 5: Smoke test**

1. Receipts page → click a processed receipt → receipt detail panel shows.
2. Click "💸 Split Receipt" → panel expands showing "You $XX.XX".
3. "+ Add person" → second row, both amounts recalc equally.
4. Click "Save Split" → toast "Split saved — your share: $X.XX".
5. Click "💸 Split Receipt" again → panel collapses.
6. Try to split same receipt again → Save returns error toast "Purchase N already has a shared expense".

- [ ] **Step 6: Commit**

```bash
git add src/frontend/index.html
git commit -m "feat(web-ui): split receipt inline panel"
```

---

## Task 4: Receipt Shared Badge

**Files:**
- Modify: `src/backend/handle_receipt_upload.py` (JOIN SharedExpense in `list_receipts`)
- Create: `tests/test_shared_dining_receipt_badge.py`
- Modify: `src/frontend/index.html` (badge in receipt row + stat card in detail)

### Context

`list_receipts()` at line ~1092 queries `TelegramReceipt ⋈ Purchase ⋈ Store`. Add outer-join with `SharedExpense` to include `my_amount` when set. The result loop currently unpacks 3-tuples `(receipt, purchase, store)`.

Frontend: `renderCompactReceiptRows()` at line ~34278 renders each row's value as `formatMoney(receiptDisplayTotal(receipt))`. When `receipt.my_amount` is set, show `👥 $X.XX` instead.

### Steps

- [ ] **Step 1: Write failing test**

Create `tests/test_shared_dining_receipt_badge.py`:

```python
"""Receipts list endpoint includes my_amount when purchase is split."""
import pytest
from datetime import datetime, timezone

from src.backend.initialize_database_schema import (
    Base, Purchase, Store, TelegramReceipt, SharedExpense,
)


def _seed(session, total=100.0):
    store = Store(name="Test Dining", canonical_name="test dining")
    session.add(store)
    session.flush()
    purchase = Purchase(
        store_id=store.id, total_amount=total,
        date=datetime(2024, 6, 1, tzinfo=timezone.utc), domain="restaurant",
    )
    session.add(purchase)
    session.flush()
    tr = TelegramReceipt(
        telegram_user_id="tg_123", message_id="99",
        image_path="/tmp/badge_test.jpg", status="processed",
        purchase_id=purchase.id,
    )
    session.add(tr)
    session.flush()
    return tr, purchase


def test_receipt_without_split_has_no_my_amount(client):
    """Unsplit receipt: my_amount absent (None) in list response."""
    with client.application.app_context():
        from src.backend.create_flask_application import _get_db
        session = next(_get_db())
        _seed(session, total=120.0)
        session.commit()
    res = client.get("/receipts", headers={"Authorization": "Bearer test-token"})
    assert res.status_code == 200
    receipts = res.get_json().get("receipts", [])
    assert any(r.get("my_amount") is None for r in receipts)


def test_receipt_with_split_has_my_amount(client):
    """Split receipt: my_amount present and correct in list response."""
    with client.application.app_context():
        from src.backend.create_flask_application import _get_db
        session = next(_get_db())
        tr, purchase = _seed(session, total=200.0)
        expense = SharedExpense(
            purchase_id=purchase.id,
            total_amount=200.0,
            my_amount=100.0,
            payment_scenario="PAID_ALL",
        )
        session.add(expense)
        session.commit()
    res = client.get("/receipts", headers={"Authorization": "Bearer test-token"})
    assert res.status_code == 200
    receipts = res.get_json().get("receipts", [])
    split = next((r for r in receipts if r.get("my_amount") is not None), None)
    assert split is not None
    assert split["my_amount"] == pytest.approx(100.0)
    assert split["shared_expense_id"] is not None
```

Check whether `conftest.py` provides a `client` fixture — look in `tests/conftest.py`. If the fixture is named differently, adjust the parameter name to match.

- [ ] **Step 2: Run test — confirm it fails**

```bash
./venv/bin/pytest tests/test_shared_dining_receipt_badge.py -v
```
Expected: FAIL — `my_amount` key missing from receipt dicts.

- [ ] **Step 3: Join SharedExpense in list_receipts**

In `src/backend/handle_receipt_upload.py`, locate the query at line ~1119:

```python
    query = (
        session.query(TelegramReceipt, Purchase, Store)
        .outerjoin(Purchase, TelegramReceipt.purchase_id == Purchase.id)
        .outerjoin(Store, Purchase.store_id == Store.id)
    )
```

Change to:

```python
    from src.backend.initialize_database_schema import SharedExpense as _SE
    query = (
        session.query(TelegramReceipt, Purchase, Store, _SE)
        .outerjoin(Purchase, TelegramReceipt.purchase_id == Purchase.id)
        .outerjoin(Store, Purchase.store_id == Store.id)
        .outerjoin(_SE, _SE.purchase_id == Purchase.id)
    )
```

Then find the loop that unpacks query results (search for `for receipt, purchase, store in` in the same function). Change the unpacking:

```python
        for receipt, purchase, store, shared_exp in query:
```

In the dict built inside that loop, add two fields:

```python
            "my_amount": float(shared_exp.my_amount) if shared_exp and shared_exp.my_amount is not None else None,
            "shared_expense_id": shared_exp.id if shared_exp else None,
```

- [ ] **Step 4: Run test — confirm it passes**

```bash
./venv/bin/pytest tests/test_shared_dining_receipt_badge.py -v
```
Expected: PASS.

- [ ] **Step 5: Full test suite**

```bash
./venv/bin/pytest tests/ -q
```
Expected: all pass.

- [ ] **Step 6: Add shared badge to receipt row**

Locate in `renderCompactReceiptRows` (line ~34297):

```javascript
          <div class="summary-row__value">${formatMoney(receiptDisplayTotal(receipt))}</div>
```

Change to:

```javascript
          <div class="summary-row__value">${receipt.my_amount != null ? '<span title="Your share" style="font-size:0.82rem;color:var(--muted,#aaa)">👥 ' + formatMoney(receipt.my_amount) + '</span>' : formatMoney(receiptDisplayTotal(receipt))}</div>
```

- [ ] **Step 7: Add "Your Share" stat card in receipt detail**

Locate this exact long line in the receipt detail stats HTML (line ~32295):

```javascript
      <div class="stat-card ${normalizeReceiptTransactionType(receipt.transaction_type) === "refund" ? "warning" : "success"}"><div class="stat-label">Total</div><div class="stat-value" style="font-size:1.2rem">${formatMoney(receiptDisplayTotal(receipt))}</div><div class="stat-sub">${escHtml(formatLabel(receipt.receipt_type, "Unknown"))} · ${escHtml(formatReceiptTransactionLabel(receipt.transaction_type))}${refundMeta ? ` · ${escHtml(refundMeta)}` : ""}</div></div>
```

Add a new stat card immediately after it:

```javascript
      ${receipt.my_amount != null ? '<div class="stat-card"><div class="stat-label">Your Share</div><div class="stat-value" style="font-size:1.2rem">👥 ' + formatMoney(receipt.my_amount) + '</div><div class="stat-sub">of ' + formatMoney(receiptDisplayTotal(receipt)) + ' total</div></div>' : ''}
```

- [ ] **Step 8: Smoke test**

1. Split a receipt (via panel from Task 3 or via Telegram `/split`).
2. Receipts page: the split receipt row shows "👥 $X.XX" in muted text instead of full amount.
3. Click that receipt: detail shows "Your Share" stat card beside the "Total" card.
4. Unsplit receipts show full amount with no badge.

- [ ] **Step 9: Commit**

```bash
git add src/backend/handle_receipt_upload.py tests/test_shared_dining_receipt_badge.py src/frontend/index.html
git commit -m "feat(web-ui): show shared receipt badge and your-share stat card"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|----------------|------|
| "Split this receipt" button → inline panel | Task 3 |
| Payment scenario: Paid All / Paid Own / I Owe | Task 3 |
| Participant list with +Add, per-person amounts | Task 3 |
| Total must match receipt (hard block) | Task 3 (Save button disabled when mismatch) |
| Saved contacts + ad-hoc names | Task 3 (contact dropdown + ad_hoc_name fallback) |
| Balances page — net per contact | Task 1 |
| Settle all debts with contact | Task 1 |
| Receipt list badge: 👥 $X.XX | Task 4 |
| Contacts page CRUD | Task 2 (list + add; no DELETE endpoint exists yet) |

**Placeholder scan:** None.

**Type consistency:** `_sp.participants` items always have `{isSelf, name, contactId, shareAmount, isPayer}`. API payload maps these consistently in `_spSave()` → `{is_self, share_amount, contact_id, ad_hoc_name, payer}`.

**Known gap:** Contacts delete/edit omitted — no `DELETE /shared-dining/contacts/<id>` backend endpoint yet.
