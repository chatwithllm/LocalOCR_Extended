# Design Review Prompt (Round 2) — Accounts Dashboard & Per-User Plaid Access Control

> **Instructions for the reviewer:** You are a senior full-stack engineer with experience in fintech integrations, small-team ops, and household-scale self-hosted apps. You are being asked to **stress-test this plan before implementation starts**. Push back hard on anything you find risky, over-engineered, under-specified, or misaligned with the deployment context. A reviewer who just says "looks good" has wasted our time — we want the things we're not seeing.
>
> **This is a revised plan.** An earlier external review (Round 1) already pushed back on three decisions and they were unlocked:
> - Admin "view all" bypass → **dropped** (strict self-scope only)
> - In-memory balance cache → **DB-persisted** instead
> - One-release migration for Settings cards → **deleted in same PR**
>
> If you disagree with *these revisions* (i.e., you think Round 1 pushed us the wrong way), say so explicitly. Otherwise, focus your attention on the remaining plan.
>
> **Structure your response as:**
> 1. **Biggest concerns** (top 3)
> 2. **Challenges to the locked decisions** (Section 4) — anything that should be re-opened?
> 3. **Round 1 revisions** — are any of them wrong in hindsight, or did we over-correct?
> 4. **Missing risks** — what's not in the risk register (Section 5)?
> 5. **Phasing concerns** (Section 6) — is the 3-PR breakdown right? Is anything in the wrong phase?
> 6. **Testing strategy** (Section 7) — is minimum pytest coverage actually sufficient?
> 7. **Over-engineering / under-specified** — what should be removed or clarified?
> 8. **Verdict** — green-light, revise-and-resubmit, or stop and re-think?

---

## 1. Context (1-minute read)

- **App:** self-hosted household finance app (Python/Flask/SQLite/vanilla-JS). 1–5 users. One Docker container on a home server.
- **Plaid:** went live in Production today. Transactions product only; hourly sync via APScheduler; no webhooks yet.
- **Encryption:** single Fernet key encrypts both `plaid_items.access_token_encrypted` and `ai_model_configs.api_key_encrypted`. No rotation. Backup includes the key in plaintext inside `meta/env.snapshot`.
- **Existing Plaid UI:** two cards nested inside the Settings page (Bank Connections list + Review Imported Transactions queue). No dedicated financial view.
- **All existing Plaid endpoints already filter by `user_id == current_user.id`.** No admin bypass exists today.

**Full code-audit details (routes, columns, integrations, backup script behavior):** See Appendix A at the bottom of this doc.

---

## 2. What we're building

A new top-level **"🏦 Accounts"** page (inserted between Bills and Analytics) with three stacked collapsible-card panels:

- **Panel 1 — Connected Accounts:** per-item card with institution, account sub-list (checking/savings/credit), last-sync, status, balances. Actions: Sync Now, Disconnect, Rename. "+ Connect Bank" button moves here from Settings.
- **Panel 2 — Transactions:** filterable list (date range, account, category, merchant). Two sub-tabs: "All spending" (excludes LOAN_PAYMENTS/TRANSFER_OUT) vs. "Transfers & bills" (only those).
- **Panel 3 — Spending trends:** monthly chart of last 12 months + current-month category breakdown.

**Backend delta (one migration + ~5 routes):**
- Migration `005_accounts_dashboard` — adds `nickname` column to `plaid_items`, new `plaid_accounts` table (stores balances with `balance_updated_at`), new compound index `(user_id, date, category)` on `purchases`. Additive, idempotent, reuses existing helpers from migration `004`.
- New routes: `PATCH /plaid/items/<id>`, `GET /plaid/accounts`, `POST /plaid/accounts/refresh-balances`, `GET /plaid/transactions`, `GET /plaid/spending-trends`. All inline `filter_by(user_id=current_user.id)`. No scope helper, no query-param overrides.

**Delete in the same PR:** the existing Plaid cards in Settings. Replace with a single deep-link line.

**Not touching:** Fernet key, encrypted column schemas, encrypt/decrypt helper signatures, hourly scheduler, backup/restore script, existing sync/confirm/dismiss/delete endpoints.

---

## 3. Non-negotiables (terse)

- [ ] No changes to `FERNET_SECRET_KEY`, no new encrypted columns, no encrypt/decrypt signature changes.
- [ ] No regression in per-user Plaid isolation.
- [ ] No breakage of restore from pre-change backup archives.
- [ ] No changes to the hourly sync scheduler.
- [ ] No new frontend or backend dependencies (use existing charting approach from Analytics page).
- [ ] No automated balance calls (manual only, server-side 5-min throttle).
- [ ] No second top-level page for financial data.

Any of these violated → block the PR.

---

## 4. Locked decisions (after Round 1 revisions)

### D1. Access control: **strict self-scope for all users**
- Every Plaid read + write endpoint inlines `filter_by(user_id=current_user.id)`. No helper function, no admin bypass, no query-param overrides.
- Rare cross-user audit case: operator runs a direct DB query via `docker exec ... python3 -c 'import sqlite3; ...'`.

**Push back if:** you think the lack of an admin audit view will bite in practice; you think the operator will end up hand-editing DB rows more than expected; you see an even simpler scoping approach.

### D2. Balances: **persisted in a new `plaid_accounts` table**
- Columns `balance_cents`, `balance_updated_at` on `plaid_accounts` (not on `plaid_items` — one row per sub-account).
- Manual refresh only via a button. Backend rejects refresh requests with 429 if `max(balance_updated_at)` for the user's items is less than 5 minutes old.
- Hourly scheduler never calls `/accounts/balance/get`.

**Push back if:** you see a way for concurrent writes to cause `SQLITE_BUSY` at household scale; you think the 5-min throttle window is wrong; you think the balance data should live on `plaid_items` instead (fewer rows, less JOIN); you see a way to pipeline this with the hourly sync cheaply.

### D3. Layout: three panels stacked vertically, each a collapsible card
- Not three sub-tabs. The review-heavy workflow (Panel 2) benefits from being visible alongside Panel 1.

**Push back if** you think density hurts on mobile or reduces comprehension.

### D4. Nav position: between Bills and Analytics
- Semantic grouping for financial data.

**Push back if** you see a better position.

### D5. Settings Plaid cards: **deleted in the same PR** as the Accounts page lands
- Replaced with a single "Banking moved to the Accounts tab" line + deep link.
- No transition period. Household has 1–5 users.

**Push back if** you think an atomic delete will actually break more than it fixes (e.g., if the operator hasn't seen the new page yet and relies on the old one mid-day).

---

## 5. Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| 🔴 | Fernet contract breakage (would take out Plaid tokens AND stored AI model keys) | No key changes, no new encrypted columns, no helper-signature changes; round-trip test after deploy |
| 🔴 | Backup/restore compat with new schema | Migration is additive + idempotent; restore script runs `alembic upgrade head`; verified by dry-run into disposable stack |
| 🔴 | Frontend monolith regression (single large `index.html`, no build step, no test harness) | Strict pattern adherence, dedupe check on element IDs, old Settings cards deleted in same PR to avoid duplicate UI |
| 🟡 | User-scope regression | No helper, every new endpoint inlines `filter_by(user_id=...)`; code review checklist; smoke tests with two users |
| 🟡 | Plaid `/accounts/balance/get` cost | DB-persisted; manual-only; server-side 5-min throttle |
| 🟡 | Plaid vs. receipt-OCR category taxonomy mismatch in Panel 3 | Source-split as v1 default; optional normalization map; decision documented inline before Panel 3 code is written |
| 🟡 | Chart library capability unverified | Inspect Analytics page's charting approach **before** writing Panel 3; downgrade Panel 3 to supported chart types rather than add a new dep |
| 🟢 | Review queue ambiguity (two Plaid UIs) | Eliminated by deleting Settings cards in same PR |
| 🟢 | Scheduler interaction (no new pause feature) | Out of scope; no behavioral change |
| 🟢 | Existing Dashboard widget fix (`d8fe2d9`) | Do not touch `page-dashboard` |
| 🟢 | SQLite WAL concurrent writes | Extremely unlikely at 1–5 users with manual-only triggers; add retry only if it ever surfaces |

---

## 6. Implementation phasing (3 PRs)

**Phase 1 — Schema + read endpoints (backend only, no UI):**
- Migration `005_accounts_dashboard` with `_table_exists()` / `_index_exists()` helpers.
- Backfill `plaid_accounts` from existing `plaid_items.accounts_json` blobs (no balances yet).
- All 5 new routes, inlined scoping.
- Acceptance: Section 7 tests for Isolation + Backup/Restore + Fernet all pass.

**Phase 2 — Frontend Accounts page:**
- Pre-step: verify chart library capabilities; document decision.
- Add nav item + `page-accounts` div.
- Build Panels 1 → 2 → 3.
- **Delete Settings Plaid cards in the same PR.** Replace with deep-link line.
- Acceptance: Section 7 UI + cost tests pass. No duplicate IDs in `index.html`. Every existing nav tab still loads.

**Phase 3 — Polish (optional):**
- Performance fixes, layout tweaks from Phase 2 feedback.
- Keep small or split.

**Deploy cadence:** Phase 1 → prod → bake 24–48h → Phase 2 → bake 48h → Phase 3.

**Rollback trigger:** any 🔴 risk manifesting in prod → `git revert`, redeploy, investigate.

---

## 7. Testing strategy

**Automated:**
- **pytest per new backend route:** one happy-path test + one cross-user-isolation test (User B calling User A's endpoint/resource returns empty or 404). Fixtures create two users each with one mock Plaid item.
- **Alembic migration roundtrip:** up → down → up on an ephemeral SQLite DB, seeded with representative data.
- **No new frontend test harness:** the repo has none today. Adding one is explicitly out of scope. Frontend verification is manual.

**Manual (both phases):**
- Full Section 8 smoke-test matrix before merging each PR.
- Phase 1 backup/restore dry run: take backup pre-change, apply migration, restore into disposable Docker Compose stack, verify all encrypted columns decrypt and alembic auto-upgrades cleanly.

**What is deliberately not tested:**
- Concurrent balance writes (unlikely at scale).
- Chart rendering pixel-accuracy (manual eyeball).
- Multi-browser / mobile layouts (inherit whatever the existing pages do).

---

## 8. Smoke-test matrix (must pass before merge)

**Isolation (requires two user accounts, User A and User B):**
- Non-admin User A links Chase → User B sees zero Plaid items.
- User A confirms a Chase txn → User B's Transactions panel doesn't show it.
- Every new endpoint returns zero User A data when called as User B.
- DB audit: `SELECT COUNT(DISTINCT user_id) FROM plaid_accounts` matches user count with linked items.

**Fernet:**
- On container restart, existing Plaid items still sync (`last_sync_status=ok`).
- Existing AI model configs in Settings still show decrypted stored keys.

**Backup/restore:**
- Pre-migration backup → apply migration → restore that backup into disposable compose stack → alembic auto-upgrades → all encrypted columns still decrypt.

**UI:**
- New "Accounts" nav appears; every other existing nav tab still works.
- No duplicate element IDs in `index.html`.
- Balance refresh: rapid clicks within 5 min trigger only one Plaid call (server-side throttle).
- "Transfers & bills" tab correctly splits from "All spending".
- Settings Plaid cards are gone (no duplicate Sync/Connect buttons anywhere).

**Cost:**
- Plaid dashboard usage < 10 balance calls/day/user under casual use.

---

## 9. Explicit invitation to challenge

Top of mind — specifically wanting pushback on:

1. **Round 1 revisions right?** Did the external reviewer correctly push us on D1/D2/D5, or did we over-correct in any direction?
2. **Phasing:** Should migration + endpoints be two separate PRs instead of one Phase 1? Is there a reason Phase 2 shouldn't ship the Settings-card deletion with the new page (e.g., if deployment issues could leave the app with neither UI)?
3. **Testing depth:** Is "one happy + one isolation test per endpoint" actually enough? Is the lack of frontend automated tests a problem in practice?
4. **Migration risk at prod:** The migration adds a table, a column, an index. Can any of those operations lock the DB long enough to be user-visible on a healthy SQLite with ~1k rows? (Should be sub-second but worth a sanity check.)
5. **Chart library:** What should the fallback *actually* be if the existing Analytics charting approach can't do stacked bars / overlays / donuts? Is "ship with plain bars + a table" an acceptable v1 UX, or does Panel 3 need to be deferred to Phase 3?
6. **Category taxonomy:** Would you ship Panel 3 with source-split (Plaid vs. Receipts as separate stack segments) as v1, or would you ship a minimal normalization map now and skip the source-split? Which gives the user more value at this stage?
7. **Anything in the non-negotiables (Section 3) that's actually negotiable** and you think we're being too rigid about?
8. **Anything in the risk register** that should be upgraded / downgraded / combined / split?

---

## 10. What we'll do with your feedback

Bring it back to the implementing engineer. Any locked decision can still be un-locked. We'd rather revise before coding than ship something we regret.

Be direct. Be specific. Name line numbers, file paths, or concrete alternatives where you can.

---

---

## Appendix A — Ground-truth code audit

*(Collapsed here so the review above stays focused. Read this if you need to verify any claim above.)*

**Plaid data model:**
- `plaid_items` — one row per linked institution per user. Columns: `user_id` (FK non-null, indexed), `plaid_item_id` unique, `institution_id/name`, `access_token_encrypted` (Fernet), `accounts_json`, `products`, `transaction_cursor`, `last_sync_at`, `last_sync_status`, `last_sync_error`, `status`, `created_at`, `updated_at`.
- `plaid_staged_transactions` — in-flight transactions before Confirm. Columns include `user_id` (non-null, indexed), `plaid_item_id`, `plaid_transaction_id` unique, `amount`, `transaction_date`, `name`, `merchant_name`, `plaid_category_primary/detailed`, `pending`, `status` (ready_to_import / duplicate_flagged / skipped_pending / confirmed / dismissed), `duplicate_purchase_id`, `confirmed_purchase_id`, `raw_json`.
- `purchases` — target table after Confirm. Carries `user_id`, `plaid_transaction_id`, `category`, `source`, `date`, `amount`.

**Plaid routes (every one filters by `user_id = current_user.id` today):**
- `GET /plaid/status` `@require_auth`
- `POST /plaid/link-token` `@require_write_access`
- `POST /plaid/exchange-public-token` `@require_write_access`
- `GET /plaid/items` `@require_auth`
- `POST /plaid/items/<id>/sync` `@require_write_access`
- `GET /plaid/staged-transactions` `@require_auth`
- `POST /plaid/staged-transactions/<id>/confirm | /dismiss | /flag-duplicate` `@require_write_access`
- `DELETE /plaid/items/<id>` `@require_write_access`

**User/role model:**
- `users.role` String(20), values `"admin"` or `"user"`. Helper: `is_admin(user)`.
- Per-user scoping is the repo-wide pattern (not household-global). Receipts and inventory blueprints also scope by `g.current_user.id`.

**Backup script (`scripts/backup_database_and_volumes.sh`):** produces `.tar.gz` containing `database.db` (SQLite `backup()`), `receipts/`, `product_snapshots/`, `meta/env.snapshot` (**includes `FERNET_SECRET_KEY` in plaintext**), `meta/docker-compose.yml`, `meta/manifest.json`. Admin-only endpoints in `manage_environment_ops.py`. Restore is a shell script (no HTTP endpoint).

**Fernet usage:** single `FERNET_SECRET_KEY` encrypts `plaid_items.access_token_encrypted` + `ai_model_configs.api_key_encrypted`. `_get_fernet()` reads env; `decrypt_api_key` raises `ValueError` on invalid token. No rotation mechanism.

**Frontend:** `src/frontend/index.html` is one file. 12 top-level nav items (Dashboard / Inventory / Upload / Receipts / Shopping / Restaurant / Expenses / Budget / Bills / Analytics / Contribution / Settings). DOM-visibility routing via `nav(page, this)`. Plaid UI today is nested inside Settings as two cards.

**Integrations checked for Plaid exposure:**
- Telegram bot (`handle_telegram_messages.py`) — 11 handlers, none touch Plaid/transactions/balance. Receipt-only vector. Not a risk.
- MQTT / HA discovery — not reviewed in depth; unlikely to surface financial data but worth confirming once before shipping.
