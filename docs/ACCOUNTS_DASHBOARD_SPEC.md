# Accounts Dashboard — Design Specification

**Status:** Decisions revised after external review (2026-04-17) — ready for implementation
**Revision note:** Original locked decisions D1, D2, and D5 were unlocked in response to external reviewer feedback. See Section 10 for the final contract and Section 11 for the revision history.
**Owner:** Operator (single-household deployment)
**Scope:** Add a dedicated "Accounts" top-level page for Plaid-linked bank data, with explicit per-user visibility rules.

---

## 1. Goal (in one sentence)

Give each household member a clear view of *only their own* linked bank accounts and transactions, with a dedicated Accounts page that consolidates connection management, balances, transactions, and spending trends — without breaking Fernet-encrypted credentials, the existing backup/restore flow, or the current receipt/purchase pipeline.

---

## 2. Current State (as of 2026-04-17, measured from code)

### 2.1 Backend — data model

| Table | `user_id` FK | Encrypted columns | Notes |
|---|---|---|---|
| `plaid_items` | ✅ non-null, indexed | `access_token_encrypted` (Fernet) | One row per linked institution per user. Has `accounts_json` (Text, nullable) — JSON blob of last-known sub-account metadata (name, mask, type); will be superseded by new `plaid_accounts` table in migration 005. |
| `plaid_staged_transactions` | ✅ non-null, indexed | none | Holds in-flight transactions before Confirm |
| `purchases` | ✅ non-null, indexed | none | Target table after Confirm. Plaid-sourced rows are identified by `plaid_transaction_id IS NOT NULL` (unique-constrained). **There is no `source` column on `purchases`** — do not filter by `source='plaid'`. |
| `ai_model_configs` | varies | `api_key_encrypted` (Fernet) | **Shares the same FERNET_SECRET_KEY** |
| `users` | n/a | `password_hash`, `api_token_hash` (bcrypt-style, not Fernet) | Roles: `admin` \| `user` |

### 2.2 Backend — Plaid endpoints (all scoped by `user_id` today)

Every route below requires auth and filters by `g.current_user.id`. **No admin bypass exists currently.**

| Method | Path | Decorator | Scoping |
|---|---|---|---|
| GET | `/plaid/status` | `@require_auth` | n/a (global config) |
| POST | `/plaid/link-token` | `@require_write_access` | uses `current_user.id` |
| POST | `/plaid/exchange-public-token` | `@require_write_access` | inserts with `user_id=current_user.id` |
| GET | `/plaid/items` | `@require_auth` | `filter_by(user_id=...)` |
| POST | `/plaid/items/<id>/sync` | `@require_write_access` | `filter_by(id=id, user_id=...)` |
| GET | `/plaid/staged-transactions` | `@require_auth` | `filter_by(user_id=...)` |
| POST | `/plaid/staged-transactions/<id>/confirm` | `@require_write_access` | `filter_by(id=id, user_id=...)` |
| POST | `/plaid/staged-transactions/<id>/dismiss` | `@require_write_access` | same |
| POST | `/plaid/staged-transactions/<id>/flag-duplicate` | `@require_write_access` | same |
| DELETE | `/plaid/items/<id>` | `@require_write_access` | same |

### 2.3 Frontend — navigation

- 12 top-level nav items, DOM-visibility based (no hash routing): Dashboard, Inventory, Upload Receipt, Receipts, Shopping List, Restaurant (feature-flagged), Expenses, Budget, Bills, Analytics, Contribution, Settings.
- Plaid UI lives **inside the Settings page** as two stacked cards:
  - **"🏦 Bank Connections"** — list of linked items + Connect Bank button (`loadPlaidItems()`)
  - **"🧾 Review Imported Transactions"** — staged transactions queue with status filter + Confirm/Duplicate/Dismiss actions (`loadPlaidStagedTransactions()`)
- No per-account transaction history view, no balances view, no spending-trend view today.

### 2.4 Backup / restore

- `scripts/backup_database_and_volumes.sh` produces a `.tar.gz` containing:
  - `database.db` (full SQLite backup via `sqlite3.backup()`)
  - `receipts/` (full dir copy)
  - `product_snapshots/` (full dir copy)
  - `meta/env.snapshot` — **includes `FERNET_SECRET_KEY` and `SESSION_SECRET` in plaintext**
  - `meta/docker-compose.yml`
  - `meta/manifest.json` (counts + checksums)
- Admin-only endpoints in `manage_environment_ops.py`: `POST /system/backups/create`, `GET /system/backups`, `POST /system/backups/upload`.
- Restore is invoked via `scripts/restore_from_backup.sh` (shell, not HTTP).

### 2.5 Fernet contract

- `FERNET_SECRET_KEY` (44-char base64) is read once at first-encrypt/decrypt call (`route_ai_inference.py::_get_fernet`).
- Encrypts today: `plaid_items.access_token_encrypted`, `ai_model_configs.api_key_encrypted`.
- `decrypt_api_key()` raises `ValueError("Stored API key could not be decrypted")` on wrong key or tampered ciphertext.
- If key is missing at startup → no crash yet; first encrypt/decrypt raises → Plaid sync fails per-item (marks item `disconnected`, logs error).
- **Losing the key** (or mismatching key vs. backup) makes all encrypted columns unreadable. Per existing memory: DB + key must be backed up together.

---

## 3. What We're Planning

### 3.1 Access control policy — **DECIDED (revised): strict self-scope, no admin bypass**

| Option | Behavior | Decision |
|---|---|---|
| A. Self-scoped | Each user sees only their own items + txns | **✅ Final — the only mode** |
| ~~B. Admin read-all~~ | `?scope=all` query param gated by `is_admin()` | ❌ Dropped after external review (see Section 11) |
| ~~C. Shared-by-owner~~ | Rejected for v1 — complexity not justified for a household app | ❌ |
| ~~D. Household-global~~ | Rejected — regresses existing isolation | ❌ |

**Contract:**
- Every Plaid read and write endpoint filters by `user_id == current_user.id`. No query-param overrides, no role-based bypass.
- For the rare cross-user audit case, the operator connects directly to the container DB:
  ```
  docker exec localocr-extended-backend python3 -c \
    'import sqlite3; print(list(sqlite3.connect("/data/db/localocr_extended.db").execute("SELECT user_id, institution_name, last_sync_at FROM plaid_items")))'
  ```
  This is the right escape hatch for a 1–5 user household app — no additional code paths to get wrong.
- No `_scope_for_plaid_read()` helper is introduced. Every endpoint inlines `filter_by(user_id=current_user.id)` using the existing pattern from routes already in `plaid_integration.py`. With only 4–5 new read endpoints, inlining is more auditable than abstracting — a reviewer can confirm scoping by reading each route top-to-bottom.

### 3.2 New "Accounts" top-level page

New nav item **"🏦 Accounts"** inserted between Bills and Analytics. DOM id: `page-accounts`. Lazy-loaded on first nav like existing pages.

Three panels, stacked vertically (or tab-switched — pick during implementation):

**Panel 1 — Connected Accounts**
- Card per linked item: institution name, account sub-list (checking/savings/credit card), last-sync timestamp, status badge (active / login_required / disconnected), current balance per account (if Plaid balance is available — may require opt-in to Balance product).
- Per-item actions: **Sync Now**, **Disconnect**, **Rename** (custom nickname — new column `nickname` on `plaid_items`).
- Bottom: **+ Connect Bank** button (moves the existing button here from Settings).

**Panel 2 — Transactions**
- Filterable list of all posted transactions for the current user across all linked accounts.
- Filters: date range (last 30d / 90d / YTD / custom), account, Plaid category, merchant search.
- Columns: date, merchant, amount, account, category, source (receipt vs. Plaid), linked purchase.
- Two tabs within this panel:
  - **All spending** — default, hides `LOAN_PAYMENTS` and `TRANSFER_OUT`.
  - **Transfers & bills** — only `LOAN_PAYMENTS`, `TRANSFER_IN`, `TRANSFER_OUT`.

**Panel 3 — Spending trends**
- Monthly bar chart (last 12 months) of confirmed Plaid-sourced purchases + receipt-sourced purchases, stacked or grouped.
- Optional per-account line overlay.
- Category breakdown pie/donut for the current month.

### 3.3 Backend changes

**Schema (single migration `005_accounts_dashboard.py`, idempotent like `004`):**
- Add `nickname` nullable String(64) column to `plaid_items`.
- **New table `plaid_accounts`** — one row per Plaid sub-account (checking/savings/credit card) within a `plaid_item`:
  - `id` PK
  - `plaid_item_id` FK → `plaid_items.id` (non-null, indexed)
  - `user_id` FK → `users.id` (non-null, indexed) — denormalized for fast scoping
  - `plaid_account_id` String(64) unique-per-item (Plaid's account identifier)
  - `account_name` String, `account_mask` String(8), `account_type` String(32), `account_subtype` String(32)
  - `balance_cents` Integer nullable (current balance × 100)
  - `balance_iso_currency_code` String(3) default "USD"
  - `balance_updated_at` DateTime nullable
  - `created_at`, `updated_at`
- **New compound index on `purchases`:** `(user_id, date DESC, category)` — speeds up Panel 2's date/category filters and Panel 3's monthly aggregations. Verify index doesn't already exist before creating (idempotent).

**New routes (all scoped by `user_id == current_user.id`, no helper, inlined):**
- `GET /plaid/accounts` — joins `plaid_items` + `plaid_accounts` and returns the cached balances. Does **not** call Plaid.
- `POST /plaid/accounts/refresh-balances` — calls Plaid `/accounts/balance/get` per item the user owns, updates `plaid_accounts.balance_*` rows, returns the fresh data. Server-side throttle: rejects with 429 if any of the user's items had a balance refresh in the last 5 minutes. TTL check uses `max(plaid_accounts.balance_updated_at)` per item.
- `PATCH /plaid/items/<id>` — allows renaming (`nickname`) only.
- `GET /plaid/transactions?account_id=&start=&end=&category=&merchant=` — reads only from `purchases` (confirmed) where `plaid_transaction_id IS NOT NULL`. Returns a paginated list. `plaid_staged_transactions` is **not** read here (see Section 4.8). (There is no `source` column on `purchases` — origin is inferred from `plaid_transaction_id`.)
- `GET /plaid/spending-trends?months=12` — pre-aggregated monthly totals by category, sourced from `purchases`.

**No change** to existing sync / confirm / dismiss / delete / flag-duplicate endpoints. No change to the hourly scheduler. No new encrypted columns. No change to `encrypt_api_key` / `decrypt_api_key` signatures.

### 3.4 Frontend changes

- Add nav item + page div in `index.html`.
- Move Plaid connect / review cards out of Settings into the new page (keep status-only badge in Settings for convenience).
- New JS functions: `loadAccountsPage()`, `loadBalances()`, `loadTransactions(filters)`, `loadSpendingTrends()`.
- Chart library: reuse whatever Analytics page already uses — do not introduce a new dep.

---

## 4. Risk Register — what could break if not handled carefully

### 4.1 🔴 Fernet key contract — do not alter

**Risk:** Any change to `FERNET_SECRET_KEY` value, or to how `_get_fernet()` resolves it, silently breaks:
- All existing `plaid_items.access_token_encrypted` — users will see sync failures and items flipping to `disconnected`.
- All existing `ai_model_configs.api_key_encrypted` — stored AI provider keys become unreadable; users forced to re-enter.

**Guardrails:**
- Do NOT introduce a second encryption key.
- Do NOT rotate the key as part of this change.
- Do NOT add new encrypted columns that reuse `_get_fernet()` without testing decrypt-roundtrip against existing rows first.
- If renaming / refactoring `encrypt_api_key` / `decrypt_api_key`, keep the function signatures and behavior identical.

**Verification after deploy:**
- `POST /plaid/items/<id>/sync` on at least one existing item returns `last_sync_status=ok`.
- Loading the AI Models page in Settings still shows existing stored keys (decrypted).

### 4.2 🔴 Backup / restore compatibility

**Risk:** New schema (`plaid_items.nickname`) breaks restore from backups taken *before* the migration runs.

**Guardrails:**
- Alembic migration must be **additive and idempotent** (match the pattern of `004_add_plaid_tables.py` — check column existence before adding).
- Restore script already replays alembic `upgrade head` after copying `database.db`, so restoring a pre-migration backup onto a post-migration binary will auto-upgrade. Verify this still works.
- `env.snapshot` includes `FERNET_SECRET_KEY`; **the restore runbook already warns to keep backup + key together**. No change needed, but re-confirm in the runbook that the key in `env.snapshot` is the one that can decrypt the DB in the same archive.

**Verification:**
- Before merging: take a backup on current prod (pre-change), upgrade, restore that backup onto a clean docker-compose stack, confirm:
  - Alembic auto-upgrades to new head
  - All Plaid items still decrypt and sync
  - All AI model configs still decrypt

### 4.3 🟡 User-scope regression (downgraded after dropping admin bypass)

**Risk:** Any new endpoint that forgets `filter_by(user_id=current_user.id)` leaks another user's financial data.

**Guardrails:**
- No helper, no bypass — every read and write endpoint inlines `filter_by(user_id=current_user.id)` using the existing pattern from routes already in `plaid_integration.py`.
- Smoke tests in Section 7 verify isolation with a second user account; each new endpoint is exercised as User B and expected to return zero User A rows.
- Code review checklist: every new function in `plaid_integration.py` must contain `user_id=current_user.id` in its filter chain. Reject PRs that don't.

### 4.4 🟡 Plaid `/accounts/balance/get` cost + rate limits

**Risk:** Balance endpoint counts against paid API usage in Production (Transactions does not, for unlimited plans). Hitting it on every page load will rack up calls and can also be rate-limited per-item.

**Guardrails:**
- Balances persisted in new `plaid_accounts` table with `balance_updated_at` column (not in-memory — in-memory cache is fragile across container restarts).
- Page load reads cached balances from DB (no Plaid call).
- Refresh only happens when user clicks **🔄 Refresh balances** on the Accounts page.
- Server-side throttle: `POST /plaid/accounts/refresh-balances` returns 429 if `now() - max(plaid_accounts.balance_updated_at) < 5 minutes` for any of the requesting user's items.
- Hourly scheduler never calls `/accounts/balance/get`.

### 4.5 🔴 Frontend monolith regression (upgraded from 🟡)

**Risk:** `index.html` is one large vanilla-JS file with no build step, no module boundaries, and no test harness. Adding a 13th nav item, three collapsible panels, filter controls, sub-tabs, and chart rendering to that file is the single highest-probability source of bugs in this entire plan. A syntax error, a duplicate element ID, or a broken `onclick` handler can silently break routing or page rendering for all pages.

**Guardrails:**
- Insert new nav item using the **exact** `div class="nav-item" onclick="nav('page-accounts', this)"` pattern; do not invent new handler names.
- Insert new `<div id="page-accounts" class="page">…</div>` at the same nesting level as other `.page` divs.
- All new JS functions go in a dedicated section with a banner comment `// ==== Accounts page ====` to keep the diff reviewable.
- After each significant edit, run a quick manual smoke in the browser: every existing nav tab still loads, console shows no JS errors, no duplicate element IDs (checkable via `document.querySelectorAll('[id]')` dedupe).
- Keep panel-rendering functions small (target <80 LOC each). If any panel grows beyond that, refactor before merging.
- Delete the old Settings Plaid cards *in the same PR* as the new page goes in — two Plaid UIs in the same file doubles the surface area for bugs and creates ambiguous user flows.

### 4.6 🟢 Review queue → Accounts page migration

**Risk:** Users currently manage Plaid from Settings. Moving the cards could confuse mental models if two UIs exist in parallel.

**Guardrails:**
- Delete the old Settings cards in the **same PR** as the new Accounts page lands — no transition period. Household has 1–5 users; there is no "muscle memory" cohort to retrain. Leaving duplicate Plaid UI around invites real bugs (two Sync Now buttons, double-rendered staged counts, ambiguous user flows).
- Replace the Settings cards with a single line: "Banking moved to the Accounts tab" + a deep link — this reduces the attack surface and makes discovery obvious.

### 4.7 🟢 Scheduler interaction

**Risk:** The hourly Plaid sync scheduler is user-agnostic — it iterates all active items regardless of owner. If we add a new "disabled" state (e.g., user wants to pause sync), the scheduler needs to honor it.

**Guardrails:**
- Do NOT add a paused state in v1. Keep scheduler behavior unchanged.
- If users need pause later, add it as a follow-up with explicit scheduler-filter changes.

### 4.8 🟢 Purchase table double-writes

**Risk:** New transactions panel reading directly from `plaid_staged_transactions` (not `purchases`) could double-show transactions that have also been confirmed into `purchases`.

**Guardrails:**
- Panel 2 reads from `purchases` where `plaid_transaction_id IS NOT NULL` for confirmed history, and optionally from `plaid_staged_transactions` (status=`ready_to_import`) for a separate "pending review" badge — never the same row twice.
- Reuse existing dedup logic from `plaid_transaction_mapper.run_dedup_check` rather than reinventing.

### 4.9 🟢 Existing Dashboard Low Stock / Top Picks fix

**Risk:** Recent fix (`d8fe2d9`) excludes shopping-list items from Low Stock and Top Picks. If the new Accounts page introduces its own widgets on the main Dashboard, they must not regress this exclusion logic.

**Guardrails:**
- Do NOT add anything to `page-dashboard` in this change. Keep all new widgets on `page-accounts`.

### 4.10 🟡 Plaid vs. receipt-OCR category taxonomy mismatch

**Risk:** The spending-trends chart reads from `purchases`, which commingles Plaid-confirmed entries (Plaid's `personal_finance_category` taxonomy: `GENERAL_MERCHANDISE`, `LOAN_PAYMENTS`, etc.) with receipt-OCR entries (whatever the OCR pipeline emits — likely `grocery`, `dining`, `household`, free-text). A stacked bar chart or donut built naively will show misleading breakdowns because the same real-world concept is labeled two different ways.

**Guardrails:**
- Panel 3's category aggregation must include a source filter (Plaid only / receipt only / both) with a default to "both" but with category labels **normalized** through a lookup table in the backend response. Ship v1 with a minimal normalization map (Plaid's top ~10 categories → the app's existing category strings); expand over time.
- Alternatively (simpler v1): Panel 3 groups by *source* instead of by category — one bar per month split by "Plaid" vs. "Receipts" — and the category donut is shown only for the currently selected source.
- Pick one of the two approaches *before* implementing Panel 3. Document the decision inline.

### 4.11 🟡 Chart library capability not verified

**Risk:** Section 5 (constraints) forbids adding new frontend dependencies. Panel 3 wants stacked bar + line overlay + donut. If the existing charting approach in the Analytics page cannot do all three (e.g., if it's hand-rolled SVG only, or a minimal lib without stacked bar support), we either violate the no-new-deps rule or end up hand-rolling visualization code.

**Guardrails:**
- **Before any Panel 3 code is written:** open `index.html`, find the Analytics page's chart code, identify what library/approach is in use, and confirm it can produce: (a) stacked bar, (b) line overlay on bars, (c) donut.
- If it cannot: downgrade Panel 3 to what it can do (e.g., just a simple bar per month, no stacking; no overlay; a table instead of a donut). Do NOT add a new library.
- Document the finding in the PR description so the reviewer can confirm no new dep snuck in.

### 4.12 🟢 SQLite WAL + concurrent balance writes

**Risk:** If two users click "Refresh balances" simultaneously, the backend writes multiple `plaid_accounts.balance_*` rows concurrently. SQLite WAL handles concurrent reads well but concurrent writes can return `SQLITE_BUSY`. At 1–5 users with manual-only triggers this is very unlikely, but worth a note.

**Guardrails:**
- Use SQLAlchemy's default session-per-request pattern already in place.
- The 5-minute server-side throttle (Section 3.3) naturally prevents most concurrent writes.
- If `SQLITE_BUSY` ever surfaces in logs, add a small retry (3 attempts, 50ms backoff) in the refresh endpoint. Not needed pre-emptively.

---

## 5. Out of Scope (explicit — not in this change)

- Plaid webhook signature verification (separate security debt; see SECURITY TODO comment in `plaid_integration.py` near `/plaid/webhook`). Deferred until app is exposed on public HTTPS.
- Plaid Investments / Auth / Identity products. Current integration is Transactions + optional Balance only.
- Multi-currency (all amounts assumed USD).
- Bill auto-routing from `LOAN_PAYMENTS` into the Bills module (separate design).
- Mobile-specific layouts (inherit whatever responsiveness the existing pages have).
- Per-item sync pause / schedule customization.

---

## 6. Data Model Change (single migration)

```
alembic/versions/005_accounts_dashboard.py
  down_revision = "004_add_plaid_tables"
  upgrade():
    - if "nickname" not in plaid_items columns:
        op.add_column("plaid_items", sa.Column("nickname", sa.String(64), nullable=True))
    - if not _table_exists("plaid_accounts"):
        op.create_table("plaid_accounts",
          id PK, plaid_item_id FK (non-null, indexed),
          user_id FK (non-null, indexed),
          plaid_account_id String(64) (indexed), account_name, account_mask String(8),
          account_type String(32), account_subtype String(32),
          balance_cents Integer nullable, balance_iso_currency_code String(3) default "USD",
          balance_updated_at DateTime nullable,
          created_at, updated_at)
        op.create_unique_constraint("uq_plaid_accounts_item_account",
          "plaid_accounts", ["plaid_item_id", "plaid_account_id"])
    - if not _index_exists("ix_purchases_user_date_category"):
        op.create_index("ix_purchases_user_date_category", "purchases",
          ["user_id", "date", "category"])
  downgrade():
    - drop index, drop table (preserve nickname column — nullable, harmless)
```

Reuse the `_table_exists()` / `_index_exists()` / column-existence helpers from `004_add_plaid_tables.py`. No other schema changes.

---

## 7. Acceptance Smoke Tests

Run these post-deploy. All must pass before declaring the page shipped.

**Isolation (requires two user accounts — User A + User B; admin status irrelevant)**
- [ ] User A links Chase. User B logs in. User B sees zero Plaid items on Accounts page. `GET /plaid/items` returns `[]` for User B.
- [ ] User A confirms a Chase transaction. User B's Accounts → Transactions panel does not show it.
- [ ] Every new endpoint (`GET /plaid/accounts`, `GET /plaid/transactions`, `GET /plaid/spending-trends`, `POST /plaid/accounts/refresh-balances`, `PATCH /plaid/items/<id>`) returns zero User A data when called as User B.
- [ ] DB audit: `SELECT COUNT(DISTINCT user_id) FROM plaid_accounts` matches the count of users with linked items (no ownership drift from the sync pipeline).

**Fernet roundtrip**
- [ ] On a fresh container restart, existing pre-change Plaid items still sync successfully (`last_sync_status=ok`).
- [ ] Existing AI model configs in Settings still show decrypted keys.

**Backup / restore**
- [ ] Take a backup *before* applying the migration, then upgrade + migrate, then restore that pre-migration backup into a disposable compose stack. Confirm alembic auto-upgrades and all items remain decryptable.
- [ ] Take a backup *after* applying the migration; confirm manifest includes the new `nickname` column values (via restore into disposable stack).

**UI**
- [ ] New "Accounts" nav item appears between Bills and Analytics.
- [ ] Clicking other nav tabs (Dashboard, Inventory, Receipts, Budget, Bills, Analytics, Settings) still loads their pages without JS errors in console.
- [ ] Balances panel respects 5-minute cache (rapid page switches do not spam Plaid).
- [ ] "Transfers & bills" tab shows LOAN_PAYMENTS / TRANSFER_OUT and "All spending" excludes them.
- [ ] Monthly spending chart renders for at least one full month of data.

**Performance / cost**
- [ ] Plaid dashboard → Usage: balance calls per day stays low (expect < 10/day/user for casual use).
- [ ] Hourly scheduler still runs; its log line shows (0 new) on quiet hours, no balance calls.

**Throttle (stateful behavior on `POST /plaid/accounts/refresh-balances`)**
- [ ] Call `POST /plaid/accounts/refresh-balances` as User A — returns 200 with fresh balances; `plaid_accounts.balance_updated_at` is updated.
- [ ] Immediately call it again (within 5 minutes) — returns 429, response body identifies the TTL remaining, and `balance_updated_at` is **not** bumped.
- [ ] Wait past the 5-minute window (or manually `UPDATE plaid_accounts SET balance_updated_at = datetime('now', '-10 minutes')` in a test DB) — next call returns 200 again.
- [ ] User B's throttle state is independent of User A's: User B can refresh immediately regardless of User A's last call.

---

## 8. Rollback Plan

If any of the above fails in prod:

1. **App rollback:** `git revert <commit> && docker compose build backend && docker compose up -d backend`. Old version ignores the new `nickname` column, the new `plaid_accounts` table, and the new compound index on `purchases` — all three are additive and invisible to pre-migration code paths.
2. **Schema rollback:** Not needed. Leaving the new objects in place is safe:
   - `plaid_items.nickname` (nullable column) — not read by old code.
   - `plaid_accounts` table — orphaned but harmless; old code does not reference it. Rows can be kept for when you re-apply the feature, or cleared via `DELETE FROM plaid_accounts;` if a clean slate is preferred.
   - `ix_purchases_user_date_category` compound index — transparent to all code paths; only affects query planner, never data correctness.
   - No FK from `plaid_accounts` points outside `plaid_items`, so rolling back does not violate any constraint on existing tables.
3. **Restore last-known-good backup:** If the migration somehow corrupts the DB (should not happen with additive changes), `scripts/restore_from_backup.sh <pre-change-backup>.tar.gz`. This drops `plaid_accounts`, the index, and the `nickname` column along with everything else.
4. **Fernet recovery:** If and only if encrypted columns fail to decrypt after rollback, the `env.snapshot` inside the pre-change backup still has the original `FERNET_SECRET_KEY` — grep it out, restore into `.env`, restart.

---

## 9. Implementation Sequence (phased, 3 PRs)

Each phase is a self-contained PR that ships to prod and is smoke-tested before the next starts. This bounds blast radius and gives the operator reversible checkpoints.

### Phase 1 — Schema + read endpoints (PR 1)

- Alembic migration `005_accounts_dashboard` (nickname column, `plaid_accounts` table, compound index). Test locally: migrate up → down → up again with data.
- Backfill step inside the migration or a one-shot script: for each existing `plaid_items.accounts_json` blob, create matching `plaid_accounts` rows (no balances yet — `balance_updated_at = NULL`).
- New backend routes (no UI yet):
  - `PATCH /plaid/items/<id>` — rename
  - `GET /plaid/accounts`
  - `POST /plaid/accounts/refresh-balances` (with 5-min server-side throttle)
  - `GET /plaid/transactions`
  - `GET /plaid/spending-trends`
- **Acceptance for PR 1:** all smoke-test "Isolation" + "Backup/restore" + "Fernet" items in Section 7 pass. Run every new endpoint with curl as User A and User B.

### Phase 2 — Frontend Accounts page (PR 2)

- Before writing any code: **verify the chart library** (per risk 4.11). Document the finding.
- Nav item + `page-accounts` div scaffold.
- Panel 1 (Connected Accounts) with data + move Connect Bank button here.
- Panel 2 (Transactions) with filters + "All spending" / "Transfers & bills" tabs.
- Panel 3 (Spending trends) with the normalization/source-split decision resolved (per risk 4.10).
- Delete the existing Settings Plaid cards; replace with a single deep-link line.
- **Acceptance for PR 2:** all smoke-test "UI" + "Performance/cost" items pass. Confirm no duplicate element IDs in `index.html`. Every existing nav tab still loads.

### Phase 3 — Polish (PR 3, optional)

- Any findings from Phase 2 smoke tests (performance fixes, layout tweaks).
- Add Dependabot / pip-audit (if the user wants to upgrade the Plaid Q8 vuln-scan answer).
- Keep this PR small; if it starts to grow, split.

### Testing strategy (applies to all phases)

- **Automated:**
  - At minimum, one pytest per new backend route verifying (a) happy path returns data, (b) cross-user call returns empty. Add fixtures that create two users + one Plaid item each.
  - Alembic up/down/up roundtrip test using an ephemeral SQLite DB.
  - No frontend automated tests (no test harness exists; adding one is out of scope).
- **Manual:**
  - The entire Section 7 smoke-test matrix before each PR is merged to main.
  - Backup/restore dry run into a disposable Docker Compose stack after Phase 1's migration lands.
- **Rollback trigger:** if any 🔴 risk manifests in prod (Fernet decrypt failures, cross-user data leak, backup failing to restore), immediately `git revert <phase-commit>`, redeploy, and investigate before re-attempting.

### Deploy cadence

- Phase 1 PR → prod → bake for 24–48h → Phase 2 PR.
- Phase 2 PR → prod → bake for 48h → confirm stability → Phase 3 (if needed).
- No phases merged to main without full Section 7 matrix clean.

---

## 10. Decisions (revised 2026-04-17, post external review)

1. **Access model:** **Strict self-scope for all users.** No admin bypass, no query-param overrides. Operator uses direct DB query for rare cross-user audits. See Section 3.1 for the final contract.
2. **Balances feature:** Enabled via `/accounts/balance/get`, with **persistence in a new `plaid_accounts` table** (`balance_cents`, `balance_updated_at`). Manual refresh only via **🔄 Refresh balances** button; server-side 5-min throttle; no scheduler calls.
3. **Panels layout:** Three panels stacked vertically on the Accounts page (Connected Accounts → Transactions → Spending trends). Each panel is a collapsible card for narrower viewports.
4. **Nav position:** New "🏦 Accounts" item inserted between **Bills** and **Analytics** in the top-level nav.
5. **Settings cards fate:** **Deleted in the same PR** as the new Accounts page lands. Replaced with a single line + deep link to the Accounts tab. No transition period.

All decisions above are the operative design contract. Deviations require an explicit note in a follow-up PR.

---

## 11. Revision history

**2026-04-17 (initial)** — D1 (access model) chose A+B hybrid with admin read-all; D2 (balances) chose in-memory 5-min cache; D5 (Settings cards) chose one-release grace period with deep link.

**2026-04-17 (post external review)** — All three above revised based on strong, specific external reviewer pushback:

| # | Original | Revised | Reason |
|---|---|---|---|
| D1 | A + B hybrid | Strict A (self-scope only) | For 1–5 household users, admin bypass adds a standing risk of scope-leak bugs (every future endpoint must remember to funnel through the helper); direct DB query is simpler and more auditable for the rare audit case. Risk/reward is bad at household scale. |
| D2 | 5-min in-memory cache | DB-persisted with `balance_updated_at` | In-memory cache is wiped silently on container restart, OOM kill, or APScheduler restart. Timestamp-based DB cache is simpler, survives restarts, and makes the UI snappy after a reboot. |
| D5 | One-release grace period | Delete in same PR | No muscle-memory cohort at this scale. Duplicate UI creates real bug surface (double Sync Now buttons, double-rendered counts, ambiguous flows). Grace periods are SaaS patterns; don't apply to family-scale apps. |

Risk register additions in the same revision:
- New 🟡 risk 4.10 — Plaid vs. receipt-OCR category taxonomy mismatch in Panel 3.
- New 🟡 risk 4.11 — Chart library capability must be verified before writing Panel 3 (no-new-deps rule at stake).
- New 🟢 risk 4.12 — SQLite WAL concurrent write behavior (minor at current scale).
- Upgraded risk 4.5 (frontend monolith) from 🟡 to 🔴.
- Downgraded risk 4.3 (user-scope regression) from 🔴 to 🟡 now that admin bypass is gone.

Schema additions in the same revision:
- New `plaid_accounts` table for balance persistence.
- New compound index on `purchases (user_id, date, category)` for Panel 2 + Panel 3 performance.

Integration audits confirmed in the same revision:
- Telegram bot has no Plaid / transaction / balance handlers. Not a data vector.
- MQTT / HA discovery not touched.

**2026-04-17 (post Round 2 review)** — Reviewer accepted Round 1 revisions and flagged four pre-implementation clarifications. All addressed:

| # | Reviewer concern | Action |
|---|---|---|
| R2.1 | Rollback plan only mentioned `nickname`, not new `plaid_accounts` table or compound index | Section 8 rewritten to acknowledge all three additions; explicitly notes orphaned `plaid_accounts` rows after rollback are harmless (no FK to rest of schema). |
| R2.2 | `plaid_items.accounts_json` backfill source unclear — was the column real? | Verified: `accounts_json` Text column exists on `plaid_items` (line 705 of `initialize_database_schema.py`). Added to Section 2.1 data model with note that it will be superseded by `plaid_accounts`. |
| R2.3 | `purchases.source = 'plaid'` filter referenced but column unconfirmed | Verified: **there is no `source` column on `purchases`**. The column at line 466 of the schema file belongs to `ShoppingListItem`. All spec references updated to filter by `plaid_transaction_id IS NOT NULL` only (Sections 3.3, 5.2 Panel 2). Added explicit "no `source` column" note to Section 2.1. |
| R2.4 | Smoke test matrix missing 429 throttle check on `POST /plaid/accounts/refresh-balances` | Added new "Throttle" block to Section 7 with four checks: 200 → 429 within 5min → 200 after expiry → User B independent of User A. |

No changes to decisions, scope, phasing, or risk register. No new migration changes. Ready to implement Phase 1.
