# Sign in with Google — production credential wiring

**Status:** Design ready · Not yet implemented
**Branch:** `feat/google-signin`
**Date:** 2026-05-29
**Approach:** A (minimal config drop)

## TL;DR

The Google OAuth backend is already implemented in `src/backend/manage_authentication.py` (routes, user-model columns, state HMAC, three login paths). Production is missing only the GCP credentials. This change is configuration + documentation — **no code paths are touched.**

## Discovery — what already exists

| Component | Where | State |
|---|---|---|
| Backend routes (`/auth/oauth/google`, `/callback`, `/status`, `/link`, `/unlink`) | `src/backend/manage_authentication.py:2313-2487` | ✅ implemented |
| `_is_google_oauth_configured()` env-var gate | `manage_authentication.py:2022-2027` | ✅ implemented |
| `_get_oauth_redirect_uri()` callback builder | `manage_authentication.py:2030-2037` | ✅ implemented |
| HMAC state for CSRF (`_build_oauth_state` / `_verify_oauth_state`) | `manage_authentication.py:2040-2077` | ✅ implemented |
| `_fetch_google_user_info()` Google userinfo call | `manage_authentication.py:2080-2090` | ✅ implemented |
| `_find_or_create_oauth_user()` three-path logic | `manage_authentication.py:2092-2160` | ✅ implemented |
| `User.google_sub` + `User.google_email` columns | `src/backend/initialize_database_schema.py` | ✅ exists |
| `authlib>=1.3.0` dependency | `requirements.txt` | ✅ installed |
| SPA Sign-in-with-Google button (`#auth-google-btn`) | `src/frontend/index.html:1808` | ✅ exists, gated by `app-config.google_oauth_enabled` |

The three login paths in `_find_or_create_oauth_user()`:

- **A.** existing user with matching `google_sub` → log in directly
- **B.** existing user with matching email (case-insensitive) → link `google_sub`, log in
- **C.** invite-token present → create new user with `google_sub` + `google_email`

Path C is invite-gated. Self-registration without invite is **out of scope** for this branch.

## Goal

Production at `https://extended.npalakurla.com` can complete a full Google sign-in round trip:

1. Visitor clicks Sign-in-with-Google button in the SPA at `/app`.
2. Backend redirects to Google's consent screen.
3. User consents.
4. Google redirects back to `/auth/oauth/google/callback?code=…&state=…`.
5. Backend exchanges code for token, fetches userinfo, matches/creates user, sets Flask session.
6. User lands authenticated.

The current blocker is that `_is_google_oauth_configured()` returns `False` on prod because `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are not set. The SPA observes `app-config.google_oauth_enabled === false` and keeps the button hidden (`display: none`).

## Scope

### In scope

1. **`.env.example`** — append a documented `# ----- Google OAuth -----` section so future operators (and the prod box) know which variables exist and what they do.
2. **`docs/DEPLOYMENT_GUIDE.md`** — append an "Enabling Google Sign-In" section covering:
   - GCP-side: the exact redirect URI to register
   - Prod-side: how to safely edit `/opt/extended/LocalOCR_Extended/.env`
   - Restart: `docker compose restart backend`
   - Verification: HTTP `GET` to `/auth/oauth/google/status` and a manual browser round trip
3. **This design doc** — committed alongside, in `docs/superpowers/specs/`.

### Out of scope (deliberate, separate branches)

- Adding a Sign-in-with-Google CTA to the marketing landing at `/`. The SPA's existing button is sufficient for now; a landing CTA is a UX question, not an auth question.
- Self-registration policy change (Path C invite-gating stays).
- Migrating `GOOGLE_CLIENT_SECRET` from `.env` to Docker secrets / Vault / etc. The current `.env`-on-host pattern is acceptable for the self-hosted single-host deployment model.
- `_PLACEHOLDER_CONFIG_VALUES` extension to flag stub Google IDs. Useful but not required to ship.
- Startup log line confirming OAuth status. Useful but optional.

## Configuration contract

The backend reads these environment variables. Adding them to `.env` and restarting the backend container is sufficient to enable Google sign-in.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | yes | _(unset)_ | OAuth 2.0 Web Client ID from GCP Console |
| `GOOGLE_CLIENT_SECRET` | yes | _(unset)_ | OAuth 2.0 Web Client secret from GCP Console |
| `GOOGLE_OAUTH_ENABLED` | no | `true` | Set to `0`/`false`/`no` to disable even when creds present (kill-switch) |
| `PUBLIC_BASE_URL` | yes for prod | _(falls back to `request.host_url`)_ | Used to construct the redirect URI deterministically. Must match the GCP-registered URI exactly. |
| `OAUTH_REDIRECT_BASE_URL` | optional | falls back to `PUBLIC_BASE_URL` | Override when the public host and callback host differ (rare). |

**Redirect URI registered in GCP must be exactly:**

```
https://extended.npalakurla.com/auth/oauth/google/callback
```

— no trailing slash, scheme `https`, host without `www`.

## File changes

### 1. `.env.example` — appended section

```
# ----------------------------------------------------------------------
# Google OAuth — Sign in with Google
# ----------------------------------------------------------------------
# Create an OAuth 2.0 Web Client in Google Cloud Console:
#   APIs & Services → Credentials → Create Credentials → OAuth client ID
# Authorized redirect URI must exactly match:
#   <PUBLIC_BASE_URL>/auth/oauth/google/callback
# In production that is:
#   https://extended.npalakurla.com/auth/oauth/google/callback
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Kill-switch. Set to 0/false/no to disable Google sign-in even when
# CLIENT_ID and CLIENT_SECRET are present.
GOOGLE_OAUTH_ENABLED=true

# Public base URL the backend is served from. Required for OAuth so
# that the redirect URI is deterministic (not derived from request
# headers, which a reverse proxy can mangle).
PUBLIC_BASE_URL=https://extended.npalakurla.com
```

### 2. `docs/DEPLOYMENT_GUIDE.md` — appended section

A new top-level `## Enabling Google Sign-In` section after the existing deployment content, structured as:

- **Prerequisites**: a GCP project with the OAuth consent screen configured (External or Internal, doesn't matter), and the operator's email added as a test user if the consent screen is still in Testing mode.
- **GCP-side steps**: create OAuth 2.0 Client ID (Web application), register the exact redirect URI above, copy CLIENT_ID and CLIENT_SECRET.
- **Prod-side steps**:
  1. SSH to UDImmich
  2. `cd /opt/extended/LocalOCR_Extended`
  3. Edit `.env` (note that `.env` is gitignored — paste creds directly)
  4. `docker compose restart backend`
- **Verification**:
  - `curl -s https://extended.npalakurla.com/auth/oauth/google/status` → expect `{"enabled": true}`
  - Open `/app` in a browser, the Google sign-in button should be visible
  - Click button → Google consent → back to `/app` authenticated
- **Rollback**: comment out `GOOGLE_CLIENT_ID` in `.env`, restart backend. The SPA hides the button again, no schema or user-table changes need reverting.

### 3. No source-code changes

No `.py`, no `.html`, no `.js`, no migrations.

## Verification gates

Each gate must pass before the change is considered done.

1. **Static**
   - `git grep "GOOGLE_CLIENT_ID" .env.example` matches the new block.
   - `git grep "Enabling Google Sign-In" docs/DEPLOYMENT_GUIDE.md` matches the new section.

2. **Pre-deploy local**
   - Add the three variables to a local `.env` with test creds (or a GCP test client).
   - Restart local backend.
   - `curl -s http://localhost:8090/auth/oauth/google/status` → `{"enabled": true}`.

3. **Post-deploy prod**
   - `curl -s https://extended.npalakurla.com/auth/oauth/google/status` → `{"enabled": true}`.
   - Browser round trip: `/app` → click Google button → consent → back to `/app` with a session.
   - `docker compose logs backend --tail 200` shows no `GOOGLE_CLIENT_ID missing` warnings and shows the OAuth callback exchange succeeding.

## Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| GCP-registered redirect URI doesn't match `_get_oauth_redirect_uri()` output (trailing slash, http vs https, missing path) | High — easiest mistake | Hard-set `PUBLIC_BASE_URL=https://extended.npalakurla.com` (no trailing slash). Document the exact URI in `.env.example` and the deployment guide. |
| `.env` accidentally committed with secrets | Low | Already covered by `.gitignore` (`.env`, `.env.test`). Verified before this change. |
| Stale env after edit because operator runs `docker compose up -d` (no-op when image unchanged) instead of `restart` | Medium | Deployment guide explicitly says `restart`, not `up -d`. |
| `GOOGLE_OAUTH_ENABLED` left unset → defaults to `true` → button appears on prod before operator is ready | Low | `.env.example` shows the variable with explicit `true`, so operators consciously toggle it. |
| Path C invite-token flow lets unauthorized Google users register | None (already gated) | No change to path C; invite-only registration is preserved. |
| Test users on a Testing-mode consent screen hit `403: access_denied` | Medium during initial setup | Deployment guide notes the operator's email must be a registered test user, or the consent screen must be Published. |

## Rollback plan

Comment out `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `/opt/extended/LocalOCR_Extended/.env`, then `docker compose restart backend`. The `_is_google_oauth_configured()` gate flips to `False`, the SPA hides the button via `app-config`, and no other surface is affected. Existing users with linked `google_sub` retain their accounts; they fall back to password login.

## Follow-up branches (not this one)

- **`feat/landing-google-cta`** — add a Sign-in-with-Google CTA to the marketing landing at `/`.
- **`feat/google-self-register`** — allow Path C without an invite token, gated by an allowlist or domain restriction.
- **`feat/secret-hardening`** — extend `_PLACEHOLDER_CONFIG_VALUES`, add startup log, write `scripts/verify_oauth_config.sh`.
- **`feat/secrets-to-docker`** — move `GOOGLE_CLIENT_SECRET` (and other long-lived secrets) from `.env` to Docker secrets mounts.
