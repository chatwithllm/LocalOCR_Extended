# Google Sign-In — Production Credential Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Google sign-in on `https://extended.npalakurla.com` by wiring already-implemented OAuth backend to GCP credentials via `.env` config + documentation.

**Architecture:** Approach A from the spec — no source-code changes. Two documentation files updated in-repo (`.env.example` + `docs/DEPLOYMENT_GUIDE.md`), then a manual `.env` edit on the prod host + container restart. The backend already implements every OAuth route and user-matching path; `_is_google_oauth_configured()` flips from `False` to `True` the moment `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are populated.

**Tech Stack:** Flask · `authlib>=1.3.0` (already installed) · Google OAuth 2.0 Web Client · Docker Compose · `.env` env-var loading via `python-dotenv`.

**Spec:** `docs/superpowers/specs/2026-05-29-google-signin-config-design.md`

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `.env.example` | append | Document the four Google OAuth env vars so operators know what `.env` needs |
| `docs/DEPLOYMENT_GUIDE.md` | append | "Enabling Google Sign-In" section: GCP-side + prod-side + verification + rollback steps |
| `/opt/extended/LocalOCR_Extended/.env` (prod, not in repo) | manual edit | Real credentials live here. `.env` is gitignored. |

No source code, no migrations, no tests.

---

## Task 1: Append Google OAuth section to `.env.example`

**Files:**
- Modify: `.env.example` (append to end of file)

- [ ] **Step 1: Open `.env.example` and confirm current end**

Run: `tail -5 .env.example`

Expected output (last 5 lines):
```
PLAID_CLIENT_ID=
PLAID_SECRET=
PLAID_ENV=sandbox
```

- [ ] **Step 2: Append Google OAuth section**

Append exactly this block to the end of `.env.example`:

```
# -----------------------------------------------------------------------------
# Optional: Google OAuth — Sign in with Google
# Create an OAuth 2.0 Web Client in Google Cloud Console:
#   APIs & Services → Credentials → Create Credentials → OAuth client ID
# Authorized redirect URI must exactly match:
#   <PUBLIC_BASE_URL>/auth/oauth/google/callback
# In production that is:
#   https://extended.npalakurla.com/auth/oauth/google/callback
# Leaving CLIENT_ID or CLIENT_SECRET blank disables Google sign-in.
# -----------------------------------------------------------------------------
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Kill-switch. Set to 0/false/no to disable Google sign-in even when
# CLIENT_ID and CLIENT_SECRET are present.
GOOGLE_OAUTH_ENABLED=true

# Public base URL the backend is served from. Required for OAuth so the
# redirect URI is deterministic (not derived from request headers, which
# a reverse proxy can mangle).
PUBLIC_BASE_URL=https://extended.npalakurla.com
```

- [ ] **Step 3: Verify the append landed**

Run: `grep -c "GOOGLE_CLIENT_ID" .env.example`
Expected: `1`

Run: `grep -c "PUBLIC_BASE_URL" .env.example`
Expected: `1`

Run: `tail -25 .env.example | head -5`
Expected: shows the new `Optional: Google OAuth` comment header.

- [ ] **Step 4: Confirm no syntax noise**

Run: `python3 -c "from dotenv import dotenv_values; v = dotenv_values('.env.example'); print(sorted(k for k in v if 'GOOGLE' in k or k == 'PUBLIC_BASE_URL'))"`

Expected:
```
['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_OAUTH_ENABLED', 'PUBLIC_BASE_URL']
```

(If `python-dotenv` not in the local venv: `pip install python-dotenv` first, or run inside the backend venv.)

- [ ] **Step 5: Commit**

```bash
git add .env.example
git commit -m "$(cat <<'EOF'
docs(env): document Google OAuth variables in .env.example

GOOGLE_CLIENT_ID + GOOGLE_CLIENT_SECRET are read by
_is_google_oauth_configured() in src/backend/manage_authentication.py
to gate the /auth/oauth/google/* routes. PUBLIC_BASE_URL is consumed
by _get_oauth_redirect_uri() to construct a deterministic redirect URI
that matches what's registered in the Google Cloud Console.

GOOGLE_OAUTH_ENABLED is a kill-switch so operators can disable the
button without removing the credentials.

No code change — backend already supports these variables.

Spec: docs/superpowers/specs/2026-05-29-google-signin-config-design.md
EOF
)"
```

---

## Task 2: Append "Enabling Google Sign-In" section to `docs/DEPLOYMENT_GUIDE.md`

**Files:**
- Modify: `docs/DEPLOYMENT_GUIDE.md` (append to end of file)

- [ ] **Step 1: Confirm current end of deployment guide**

Run: `tail -3 docs/DEPLOYMENT_GUIDE.md`

Expected last line:
```
- no rollback of grocery data or runtime is required
```

- [ ] **Step 2: Append new section**

Append exactly this block to the end of `docs/DEPLOYMENT_GUIDE.md`:

```markdown

## Enabling Google Sign-In

The backend already implements every Google OAuth route
(`/auth/oauth/google`, `/callback`, `/status`, `/link`, `/unlink`) in
`src/backend/manage_authentication.py`. It stays disabled until both
`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are present in the
environment. This section walks through enabling it on
`https://extended.npalakurla.com`.

### Prerequisites

- A Google Cloud project with the OAuth consent screen configured
  (External or Internal — both work).
- If the consent screen is in **Testing** mode, your sign-in email must
  be added as a test user, otherwise you will hit
  `Error 403: access_denied`.

### Step 1 — Create the OAuth 2.0 Web Client in GCP

1. Open Google Cloud Console → **APIs & Services** → **Credentials**.
2. Click **Create Credentials** → **OAuth client ID**.
3. Application type: **Web application**.
4. Authorized redirect URIs — add exactly:

   ```
   https://extended.npalakurla.com/auth/oauth/google/callback
   ```

   No trailing slash. Scheme must be `https`. Host without `www`.
5. Click **Create**. Copy the **Client ID** and **Client secret**.

### Step 2 — Edit prod `.env`

```bash
ssh UDImmich
cd /opt/extended/LocalOCR_Extended
cp .env .env.backup-$(date +%Y%m%d-%H%M%S)   # safety copy
nano .env
```

Add or update these four lines (paste the values from Step 1):

```
GOOGLE_CLIENT_ID=<paste from GCP>
GOOGLE_CLIENT_SECRET=<paste from GCP>
GOOGLE_OAUTH_ENABLED=true
PUBLIC_BASE_URL=https://extended.npalakurla.com
```

Save and exit. `.env` is gitignored, so the secrets stay on the host.

### Step 3 — Restart the backend

```bash
docker compose restart backend
```

> Use `restart`, **not** `up -d`. `up -d` is a no-op when the image is
> unchanged and will not pick up the new env vars.

### Step 4 — Verify

From any machine:

```bash
curl -s https://extended.npalakurla.com/auth/oauth/google/status
```

Expected:
```json
{"enabled": true}
```

If you see `{"enabled": false}`:
- check `docker compose exec backend env | grep GOOGLE`
- check `docker compose logs backend --tail 50` for missing-config warnings.

Then run the full browser round trip:

1. Open `https://extended.npalakurla.com/app` in a browser.
2. The Google sign-in button should be visible
   (`#auth-google-btn` un-hidden by the SPA reading `app-config`).
3. Click it → Google consent screen → consent → back to `/app`
   authenticated.
4. `docker compose logs backend --tail 100` shows the callback
   succeeding (no `redirect_uri_mismatch`, no `state` errors).

### Rollback

```bash
ssh UDImmich
cd /opt/extended/LocalOCR_Extended
# Comment out or blank the two credentials in .env:
sed -i 's/^GOOGLE_CLIENT_ID=.*/GOOGLE_CLIENT_ID=/' .env
sed -i 's/^GOOGLE_CLIENT_SECRET=.*/GOOGLE_CLIENT_SECRET=/' .env
docker compose restart backend
```

`_is_google_oauth_configured()` returns `False`, the SPA hides the
button, and existing users with linked `google_sub` fall back to
password login. No database changes need reverting.

### Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `Error 400: redirect_uri_mismatch` | URI in GCP doesn't match what backend sent | Compare GCP URI with `_get_oauth_redirect_uri()` output — usually a trailing slash or `http` vs `https`. |
| `Error 403: access_denied` | Consent screen in Testing mode, signing-in email not added as test user | Add the email under **OAuth consent screen → Test users**, or publish the consent screen. |
| `/auth/oauth/google/status` still `{"enabled": false}` after restart | Env not actually reloaded | `docker compose down && docker compose up -d backend` to force a recreate. |
| `Error: invalid_client` on callback | Wrong `GOOGLE_CLIENT_SECRET` | Re-copy the secret from GCP — they look similar but include subtle characters. |
```

- [ ] **Step 3: Verify the append landed**

Run: `grep -c "## Enabling Google Sign-In" docs/DEPLOYMENT_GUIDE.md`
Expected: `1`

Run: `grep -c "redirect_uri_mismatch" docs/DEPLOYMENT_GUIDE.md`
Expected: `1`

Run: `tail -3 docs/DEPLOYMENT_GUIDE.md`

Expected last line:
```
| `Error: invalid_client` on callback | Wrong `GOOGLE_CLIENT_SECRET` | Re-copy the secret from GCP — they look similar but include subtle characters. |
```

- [ ] **Step 4: Confirm markdown structure**

Run: `awk '/^## /{print NR": "$0}' docs/DEPLOYMENT_GUIDE.md | tail -3`

Expected: last `##` heading is `## Enabling Google Sign-In`.

- [ ] **Step 5: Commit**

```bash
git add docs/DEPLOYMENT_GUIDE.md
git commit -m "$(cat <<'EOF'
docs(deploy): add "Enabling Google Sign-In" section

Walks the operator through:
  1. Creating the OAuth 2.0 Web Client in GCP Console
  2. Editing /opt/extended/LocalOCR_Extended/.env on UDImmich
  3. docker compose restart backend (NOT up -d)
  4. Verifying via /auth/oauth/google/status + browser round trip
  5. Rolling back by blanking the credentials

Includes a troubleshooting table for the four most-common
misconfigurations: redirect_uri_mismatch, 403 access_denied,
stale env after restart, and invalid_client on callback.

Spec: docs/superpowers/specs/2026-05-29-google-signin-config-design.md
EOF
)"
```

---

## Task 3: Push branch and open PR

**Files:** none — git only.

- [ ] **Step 1: Confirm branch state**

Run: `git status --short`
Expected: empty output (working tree clean — Task 1 + Task 2 already committed).

Run: `git log --oneline -3`
Expected (top 3 commits, most-recent first):
```
<sha> docs(deploy): add "Enabling Google Sign-In" section
<sha> docs(env): document Google OAuth variables in .env.example
c8a0af5 docs(spec): design for wiring Google OAuth credentials on prod
```

- [ ] **Step 2: Push branch to origin**

```bash
git push -u origin feat/google-signin
```

Expected:
```
* [new branch]      feat/google-signin -> feat/google-signin
branch 'feat/google-signin' set up to track 'origin/feat/google-signin'.
```

- [ ] **Step 3: Open PR**

Either via `gh`:

```bash
gh pr create --base main --title "feat(auth): wire Google OAuth credentials on prod" --body "$(cat <<'EOF'
## Summary
- Add documented `GOOGLE_*` + `PUBLIC_BASE_URL` block to `.env.example`
- Add "Enabling Google Sign-In" walkthrough to `docs/DEPLOYMENT_GUIDE.md`
- Zero source-code changes — backend OAuth surface already implemented

## Why
`_is_google_oauth_configured()` currently returns `False` on prod
because `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are not set,
which leaves the SPA's existing Sign-in-with-Google button hidden.
This PR documents the config contract and the prod-side steps to
flip it on.

## Spec
`docs/superpowers/specs/2026-05-29-google-signin-config-design.md`

## Test plan
- [ ] Local: add test creds to `.env`, restart backend, hit
      `http://localhost:8090/auth/oauth/google/status` → `{"enabled": true}`
- [ ] Prod: follow `docs/DEPLOYMENT_GUIDE.md` § Enabling Google Sign-In
- [ ] Prod: `curl https://extended.npalakurla.com/auth/oauth/google/status`
      → `{"enabled": true}`
- [ ] Prod: browser round trip `/app` → Google consent → back authenticated
EOF
)"
```

Or via the URL printed by `git push` if `gh` is unavailable.

- [ ] **Step 4: Capture PR URL**

Print the PR URL so the operator can review:

```bash
gh pr view --json url -q .url
```

---

## Task 4 (manual, off-repo): GCP-side OAuth client setup

**Performed by operator in the Google Cloud Console — nothing to commit.**

- [ ] **Step 1: Open GCP Console → APIs & Services → Credentials**

URL: `https://console.cloud.google.com/apis/credentials`

Select the existing project the user identified during brainstorming.

- [ ] **Step 2: Create OAuth 2.0 Web Client**

Click **Create Credentials** → **OAuth client ID** → Application type **Web application**.

Set:
- Name: `LocalOCR Extended — prod`
- Authorized redirect URIs:

  ```
  https://extended.npalakurla.com/auth/oauth/google/callback
  ```

Click **Create**.

- [ ] **Step 3: Copy CLIENT_ID and CLIENT_SECRET**

Both values are shown once on the success modal. Copy them somewhere safe (password manager, not the terminal scrollback).

- [ ] **Step 4: (If consent screen in Testing mode) add test user**

GCP Console → **OAuth consent screen** → **Test users** → **Add users** → add the operator's email.

Skip this step if the consent screen is already **Published**.

---

## Task 5 (manual, on prod): edit `.env` and restart backend

**Performed via SSH to UDImmich after Task 3's PR is merged and Task 4's GCP setup is complete.**

- [ ] **Step 1: SSH and back up `.env`**

```bash
ssh UDImmich
cd /opt/extended/LocalOCR_Extended
cp .env .env.backup-$(date +%Y%m%d-%H%M%S)
ls -la .env.backup-*
```

Expected: the new backup file is listed.

- [ ] **Step 2: Pull the merged docs (so the operator can reread the section)**

```bash
git pull origin main
```

Expected: includes the two new commits (env + deploy guide).

- [ ] **Step 3: Edit `.env`**

```bash
nano .env
```

Add or update these four lines (paste real values from Task 4):

```
GOOGLE_CLIENT_ID=<paste from GCP>
GOOGLE_CLIENT_SECRET=<paste from GCP>
GOOGLE_OAUTH_ENABLED=true
PUBLIC_BASE_URL=https://extended.npalakurla.com
```

Save and exit.

- [ ] **Step 4: Confirm `.env` was updated (without echoing the secret)**

```bash
grep -E '^GOOGLE_CLIENT_ID=' .env | sed 's/=.*/=<set>/'
grep -E '^GOOGLE_CLIENT_SECRET=' .env | sed 's/=.*/=<set>/'
grep -E '^GOOGLE_OAUTH_ENABLED=' .env
grep -E '^PUBLIC_BASE_URL=' .env
```

Expected:
```
GOOGLE_CLIENT_ID=<set>
GOOGLE_CLIENT_SECRET=<set>
GOOGLE_OAUTH_ENABLED=true
PUBLIC_BASE_URL=https://extended.npalakurla.com
```

- [ ] **Step 5: Restart the backend container**

```bash
docker compose restart backend
```

Wait ~5 seconds for the container to come back.

- [ ] **Step 6: Confirm env vars are in the container**

```bash
docker compose exec backend env | grep -E '^(GOOGLE_CLIENT_ID|GOOGLE_OAUTH_ENABLED|PUBLIC_BASE_URL)=' | sed 's/=.*/=<set>/'
```

Expected:
```
GOOGLE_CLIENT_ID=<set>
GOOGLE_OAUTH_ENABLED=<set>
PUBLIC_BASE_URL=<set>
```

(Secret intentionally omitted from the grep.)

---

## Task 6: Post-deploy verification

**Performed from any machine after Task 5.**

- [ ] **Step 1: Status endpoint returns `enabled: true`**

```bash
curl -s https://extended.npalakurla.com/auth/oauth/google/status
```

Expected:
```json
{"enabled": true}
```

If `{"enabled": false}`: env vars didn't make it into the container — recheck Step 6 of Task 5.

- [ ] **Step 2: Browser round trip**

1. Open `https://extended.npalakurla.com/app` in a fresh private/incognito window.
2. Verify the Google sign-in button is visible.
3. Click it.
4. Complete the Google consent screen with the test user from Task 4 Step 4.
5. You should land back at `/app` authenticated.

- [ ] **Step 3: Tail logs to confirm the callback succeeded**

```bash
ssh UDImmich
cd /opt/extended/LocalOCR_Extended
docker compose logs backend --tail 200 | grep -iE '(oauth|google|redirect)'
```

Expected: a successful exchange log line — no `redirect_uri_mismatch`, no `invalid_state`, no `invalid_client`.

- [ ] **Step 4: Confirm a user row was matched or linked**

```bash
docker compose exec backend sqlite3 /data/db/localocr_extended.db \
  "SELECT id, email, google_email IS NOT NULL AS linked FROM users WHERE google_sub IS NOT NULL ORDER BY id DESC LIMIT 5;"
```

Expected: at least one row with `linked = 1` for the email you just signed in with.

---

## Task 7 (optional, post-merge): clean up the feature branch

- [ ] **Step 1: Delete the local branch**

```bash
cd ~/dev/active/LocalOCR_Extended
git checkout main
git pull origin main
git branch -d feat/google-signin
```

- [ ] **Step 2: Delete the remote branch**

```bash
git push origin --delete feat/google-signin
```

---

## Self-Review checklist (run by author before handoff)

- **Spec coverage:**
  - `.env.example` change → Task 1 ✓
  - `docs/DEPLOYMENT_GUIDE.md` change → Task 2 ✓
  - "No source-code changes" → confirmed: zero `.py`/`.html`/`.js` touched ✓
  - "Verification gates" from spec → Tasks 6.1 (status endpoint), 6.2 (browser round trip), 6.3 (logs) ✓
  - "Rollback plan" from spec → documented in DEPLOYMENT_GUIDE.md (Task 2) ✓
  - "Risks and mitigations" from spec → troubleshooting table in DEPLOYMENT_GUIDE.md (Task 2) ✓

- **Placeholder scan:** No "TBD", "TODO", "implement later", or vague "add appropriate handling" anywhere. ✓

- **Type / naming consistency:** Env var names (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_ENABLED`, `PUBLIC_BASE_URL`) and the redirect URI (`https://extended.npalakurla.com/auth/oauth/google/callback`) are identical across spec, `.env.example` block (Task 1), deployment guide (Task 2), and prod edit (Task 5). ✓
