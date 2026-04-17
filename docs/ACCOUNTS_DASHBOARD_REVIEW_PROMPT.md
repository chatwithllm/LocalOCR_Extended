# Design Review Prompt — Accounts Dashboard & Per-User Plaid Access Control

> **Instructions for the reviewer:** You are a senior full-stack engineer with experience in fintech integrations, small-team ops, and household-scale self-hosted apps. You are being asked to **stress-test this plan before implementation starts**. Push back hard on anything you find risky, over-engineered, under-specified, or misaligned with the deployment context. Point out missing edge cases, safer alternatives, and implicit assumptions that aren't justified. A reviewer who just says "looks good" has wasted our time — we want the things we're not seeing.
>
> Please structure your response as:
> 1. **Biggest concerns** (top 3) — what's most likely to cause pain?
> 2. **Challenges to each locked decision** (Section 4 below) — is each decision actually the right call?
> 3. **Missing risks** — what's not in the risk register that should be?
> 4. **Over-engineering** — what should be removed or simplified?
> 5. **Under-specified** — what needs more detail before coding starts?
> 6. **Verdict** — green-light, revise-and-resubmit, or stop and re-think?

---

## 1. Context

**App:** "LocalOCR Extended" — a self-hosted household finance / grocery-inventory / receipt-OCR app. Single Docker Compose stack on a home server (UDImmich, an Unraid-like box). Python 3.11 + Flask + SQLAlchemy + SQLite (WAL mode) + APScheduler + a single large vanilla-JS `index.html` frontend. No React, no build step.

**Scale:**
- 1–5 household users total (small family app, not SaaS)
- SQLite DB under 10 MB today
- Hosted behind an HTTPS reverse proxy on the home LAN / Tailscale

**Current integrations:**
- **Gemini / OpenAI / OpenRouter / Ollama** — receipt OCR (fallback chain)
- **Plaid** — just went live in Production today: Transactions product, `/transactions/sync` on an hourly APScheduler job, no webhooks yet (signature verification deferred)
- **MQTT / Home Assistant discovery** — optional, disabled on this host
- **Telegram bot** — optional receipt upload channel, disabled on this host
- **Backup/restore** — shell-scripted `.tar.gz` of SQLite DB + receipts + an `env.snapshot` containing `FERNET_SECRET_KEY` (yes, plaintext inside the archive — the backup assumes the operator owns both halves)

**Encryption:**
- `FERNET_SECRET_KEY` (single symmetric key) encrypts:
  - `plaid_items.access_token_encrypted`
  - `ai_model_configs.api_key_encrypted`
- No key rotation mechanism. Losing the key = losing access to encrypted columns.
- The backup archive includes the current key in `meta/env.snapshot`.

---

## 2. What exists today (ground truth from code audit)

**Plaid data model**
- `plaid_items` — one row per linked institution per user. Has `user_id` (non-null FK), encrypted access token, institution metadata, `transaction_cursor`, `last_sync_at`, `status`, etc.
- `plaid_staged_transactions` — in-flight transactions before the user Confirms them. Has `user_id`, `plaid_item_id`, amount, merchant, category, `status` (ready_to_import / duplicate_flagged / skipped_pending / confirmed / dismissed).
- `purchases` — target table after Confirm. Has `user_id`, `plaid_transaction_id`, category, etc.

**Backend routes (every one already filters by `user_id = current_user.id`):**
- `GET /plaid/status`, `POST /plaid/link-token`, `POST /plaid/exchange-public-token`
- `GET /plaid/items`, `POST /plaid/items/<id>/sync`, `DELETE /plaid/items/<id>`
- `GET /plaid/staged-transactions`, `POST /plaid/staged-transactions/<id>/confirm`, `/dismiss`, `/flag-duplicate`
- No admin bypass currently exists for any route.

**User/role model**
- `users.role` is a simple `String(20)` — only two values used: `"admin"` or `"user"`.
- `is_admin(user)` helper returns `bool(user and user.role == "admin")`.
- Admin-only endpoints today: backup/restore, user creation, device pairing.

**Frontend**
- Single-page app driven by DOM visibility: 12 top-level nav items, no hash routing.
- Plaid UI today is **nested inside the Settings page** as two cards: "🏦 Bank Connections" and "🧾 Review Imported Transactions".
- No balances view, no per-account transaction history view, no spending trends view for Plaid data.

**Sync scheduler**
- APScheduler hourly job iterates all active `plaid_items`, calls `/transactions/sync`, upserts into `plaid_staged_transactions`.
- Runs as a background job in the Flask process. Not user-aware.

---

## 3. What we're planning to build

**A new top-level "🏦 Accounts" page** (inserted between Bills and Analytics) with three stacked collapsible-card panels:

**Panel 1 — Connected Accounts**
- Per-item card: institution, account sub-list, last-sync, status, balances.
- Actions: Sync Now, Disconnect, Rename (new `nickname` column on `plaid_items`).
- "+ Connect Bank" button relocated here.

**Panel 2 — Transactions**
- Filterable list across all the user's linked accounts: date range, account, category, merchant search.
- Two sub-tabs: "All spending" (excludes `LOAN_PAYMENTS` / `TRANSFER_OUT`) vs. "Transfers & bills" (only those).

**Panel 3 — Spending trends**
- Monthly bar chart (last 12 months, stacked by source: Plaid vs. receipt).
- Optional per-account line overlay.
- Category breakdown donut for current month.

**Backend delta:**
- New Alembic migration `005_add_plaid_item_nickname.py` — single nullable String(64) column. Idempotent.
- New routes: `GET /plaid/accounts`, `PATCH /plaid/items/<id>` (rename-only), `GET /plaid/transactions` (filtered), `GET /plaid/spending-trends`.
- A single helper `_scope_for_plaid_read(query, model, current_user)` applied on every read endpoint that wants to honor admin-bypass.

**Scope not touched:**
- Fernet contract (no key changes, no new encrypted columns, no rotation).
- Existing sync / confirm / dismiss / delete endpoints.
- Scheduler behavior.
- Backup/restore script — new column is additive and nullable, Alembic auto-upgrade on restore handles it.
- Webhook signature verification — still deferred.

---

## 4. Decisions locked — challenge each one

### D1. Access control model: **Self-scoped default + admin read-all toggle**

- Every non-admin user sees only their own Plaid data. No UI override, no opt-in to see others.
- Admin users see self-scoped by default and can flip a front-end toggle **"👁 View all (admin)"** that passes `?scope=all` on GET endpoints.
- The backend honors `?scope=all` **only** when `is_admin(current_user)` is true; non-admins passing the flag get self-scoped rows silently.
- **Writes are never bypassed** — confirm / dismiss / sync / rename / delete continue to require `user_id == current_user.id` even for admins. An admin cannot confirm a transaction on behalf of another user (would corrupt purchase attribution).
- Every admin `scope=all` request logs at INFO level for audit.
- Admin's "View all" toggle does **not** persist across sessions — defaults off on each login to prevent accidentally continued broad access.
- Rejected alternatives: C (per-item explicit sharing, too complex for 5 users), D (household-global, regresses existing isolation).

**Reviewer — push back if:**
- You think the admin bypass invites more risk than value for a 1–5 user household app
- You think C (explicit share-per-item) is actually the right call for a multi-user household
- You see a path for a non-admin to gain `scope=all` that we've missed
- You think the "no persistence across sessions" is security theater vs. a real mitigation

### D2. Plaid `/accounts/balance/get` enabled with 5-min in-memory cache + manual refresh

- Balance pulls are paid/rate-limited per item on Plaid Production. Hourly scheduler does **not** call balance. User must click a "🔄 Refresh balances" button on the Accounts page.
- In-memory dict cache keyed by `plaid_item_id`, TTL 5 minutes, cleared on container restart.
- Accepted the cost tradeoff.

**Reviewer — push back if:**
- You think an in-memory cache is wrong vs. persisting balances in the DB (survives restart, trickier invalidation)
- You see a way users could inadvertently spam balance calls (e.g., rapid clicks, multiple tabs) that the 5-min cache wouldn't cover
- You think the balance feature should be gated behind an opt-in env var

### D3. Three panels stacked vertically, each a collapsible card

- Single-page Accounts view: Connected Accounts → Transactions → Spending trends.
- Collapsible so narrow viewports stay usable.
- Rejected alternative: three sub-tabs inside the page. Rejected because sub-tabs hide content and this is a review-heavy workflow.

**Reviewer — push back if:**
- You think information density hurts on mobile / reduces comprehension
- You think the Transactions panel with filters belongs on its own dedicated page

### D4. Nav position: between Bills and Analytics

- Semantic grouping: financial data clusters together.

**Reviewer — push back if you see a better position.**

### D5. Settings Plaid cards stay for one release with "View on Accounts page →" link, then deleted

- Soft migration to avoid retraining muscle memory overnight.
- Follow-up PR deletes them.

**Reviewer — push back if:**
- You think leaving duplicate UI around invites bugs (sync happening on both pages, user confusion)
- You think the migration should be atomic (delete Settings cards in the same PR)

---

## 5. Risk register (what we're watching)

| Severity | Risk | Mitigation |
|---|---|---|
| 🔴 | **Fernet contract breakage** — any change silently breaks existing Plaid tokens *and* existing AI model keys (they share the same key). | No key changes, no new encrypted columns, no rotation. Round-trip test after deploy: existing Plaid sync still works, AI models page still shows stored keys. |
| 🔴 | **Backup/restore compat** — new schema must not break restore from pre-change backups. | Alembic migration is additive (nullable column) and idempotent. Restore script already runs `alembic upgrade head`. Test: pre-change backup restored into disposable stack, confirm all encrypted columns still decrypt. |
| 🔴 | **User-scope regression (bumped up due to admin bypass)** — a misapplied `?scope=all` leaks household-wide financial data. | Single `_scope_for_plaid_read()` helper; writes never use it; explicit `is_admin()` check inside helper; INFO-log every bypass use; smoke tests cover both positive (admin sees all) and negative (non-admin `scope=all` is silently ignored) paths. |
| 🟡 | Plaid `/accounts/balance` rate-limits / cost. | 5-min cache + manual-only, never scheduled. |
| 🟡 | Frontend nav regression (one big index.html). | Exact copy of existing `nav()` pattern; smoke test every existing tab after deploy. |
| 🟡 | Review queue double-counting if Panel 2 reads from both `plaid_staged_transactions` and `purchases`. | Panel 2 reads *only* `purchases` for confirmed history; `plaid_staged_transactions` surfaces as a separate "N pending review" badge. |
| 🟢 | Scheduler still runs as-is; no pause-per-item feature in v1. | Explicit out-of-scope. |
| 🟢 | Existing Dashboard Low Stock / Top Picks fix (commit `d8fe2d9`). | No touches to `page-dashboard` in this change. |

---

## 6. Smoke-test matrix we will run before declaring done

**Isolation (requires two user accounts, one admin one non-admin)**
- Non-admin User A links Chase → Non-admin User B sees nothing.
- Admin flips "View all" → sees both users' items; log line emitted.
- Non-admin passes `?scope=all` via DevTools → still gets only their own rows.
- Admin in "View all" tries to Confirm User A's staged txn → rejected (writes don't honor bypass).
- Admin's "View all" preference does NOT persist across logout/login.

**Fernet**
- On container restart, existing Plaid items still sync (`last_sync_status=ok`).
- Existing AI model configs in Settings still show decrypted stored keys.

**Backup/restore**
- Take backup *before* migration runs, apply migration, restore that backup into disposable compose stack. Alembic auto-upgrades. All encrypted columns still decrypt.

**UI**
- New "Accounts" nav appears. Every existing nav tab still works.
- Balance cache: rapid Refresh clicks within 5 min → only one `/accounts/balance/get` call to Plaid.
- "Transfers & bills" sub-tab correctly splits from "All spending".

**Cost**
- Plaid dashboard usage < 10 balance calls/day/user under casual use.

---

## 7. Constraints and non-negotiables

- **Must not** change the Fernet encryption key, encrypt/decrypt helper semantics, or existing encrypted column schemas.
- **Must not** regress the current per-user isolation of Plaid endpoints.
- **Must not** break restore from existing (pre-change) backup archives.
- **Must not** touch the existing hourly sync scheduler or its behavior.
- **Must not** add a new dependency to either backend or frontend for this feature. Use existing chart library from Analytics page, existing stdlib + SQLAlchemy, existing vanilla JS.
- **Must not** call Plaid `/accounts/balance/get` from any automated job (only on explicit user action).
- **Must not** create a second top-level page for financial data — keep it all under "🏦 Accounts".

---

## 8. Explicit invitation to challenge

Specifically, we want opinions on:

1. **Is the admin bypass actually worth the complexity?** For 1–5 household users, would it be simpler / safer to drop D1's admin toggle entirely and require the admin to use a per-user impersonation flow (or direct DB query) for the rare audit case?
2. **Should balances be persisted in the DB** (with a `last_fetched_at` column) rather than held in in-memory cache? Persistence survives restart and makes the UI feel faster after a reboot, at the cost of one more column and cache invalidation logic.
3. **Is the "one release" migration period for the Settings cards the right call**, or does it invite bugs (user confusion over which Plaid UI is canonical, double sync buttons, etc.)?
4. **Are there integrations we've forgotten?** The app has Home Assistant MQTT discovery and a Telegram bot in its module list — could any of them reach into Plaid data in ways this plan hasn't accounted for?
5. **Is the single-user-scope helper (`_scope_for_plaid_read`) the right abstraction**, or is there a cleaner pattern (e.g., a SQLAlchemy event hook, a custom Query subclass, or just inlining the check per-endpoint)?
6. **What's the right thing to do with `LOAN_PAYMENTS` / `TRANSFER_OUT` transactions long-term?** This plan puts them in a separate tab but doesn't route them into the Bills module. Is that the right half-measure, or should we design the bill-routing now?
7. **Anything in the Risk Register that should be upgraded in severity**, or any risks we've missed entirely?

---

## 9. What we'll do with your feedback

Bring it back to the implementing engineer. Locked decisions can still be un-locked if the challenge is strong enough. We'd rather revise before coding than ship something we regret.

Be direct. Be specific. Name line numbers, file paths, or concrete alternatives where you can.
