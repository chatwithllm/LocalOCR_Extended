# LocalOCR — Push Server Example

A **minimal, optional** Web Push server. It is **not** part of the LocalOCR static
site and is **not** needed to install the PWA or use offline support. You only need
it to actually *send* push notifications, because a static site cannot push to
itself — that requires a server that holds the VAPID **private** key.

It exposes exactly two endpoints (plus a health check):

| Method | Path                  | Purpose                                            |
| ------ | --------------------- | -------------------------------------------------- |
| POST   | `/save-subscription`  | Store a browser's `PushSubscription` (sent by the site) |
| POST   | `/send`               | Push a notification to every stored subscription   |
| GET    | `/health`             | Liveness + current subscription count              |

Subscriptions are kept **in memory** for the demo. Use a real database in production.

---

## 1. Requirements

- **Node 18+** and npm.
- The site must be served over **HTTPS** (or `http://localhost` / `http://127.0.0.1`
  during development). Service workers and the Push API are disabled on insecure
  origins — this applies to the site, not this server.

## 2. Install

```bash
cd push-server-example
npm install        # pulls express + web-push (used ONLY by this example, not the site)
```

## 3. Generate VAPID keys

VAPID is a public/private key pair that identifies your push server.

```bash
npx web-push generate-vapid-keys
```

Output looks like:

```
Public Key:
BNc...long-base64url...
Private Key:
yZ...base64url...
```

- **Public key** → goes in the website config. Open
  `design/marketing/index.html`, find `window.PWA_PUSH_CONFIG`, and paste it as
  `vapidPublicKey`. The public key is safe to expose.
- **Private key** → **NEVER** put it in the website, in this repo, or in any
  client code. It lives **only** in this server's environment variable.

## 4. Run the server

Pass the keys as environment variables (never hardcode them):

```bash
VAPID_PUBLIC_KEY="paste-public-key" \
VAPID_PRIVATE_KEY="paste-private-key" \
VAPID_SUBJECT="mailto:you@example.com" \
ALLOW_ORIGIN="http://localhost:8090" \
node server.js
```

You should see:

```
Push example server listening on http://localhost:4000
```

`ALLOW_ORIGIN` should be the origin that serves the PWA (the LocalOCR site).
It defaults to `*` for convenience; tighten it in production.

> Tip: for local dev you can keep the keys in a `.env` file (already
> git-ignored) and load them with your preferred runner, e.g.
> `node --env-file=.env server.js` on Node 20+.

## 5. End-to-end test

1. Serve the LocalOCR site over `https://` or `http://localhost` and open it.
2. Click **Enable notifications** (bottom-left) and allow the permission prompt.
   The browser POSTs its subscription to `/save-subscription` on this server.
3. Trigger a push:

   ```bash
   curl -X POST http://localhost:4000/send \
     -H 'Content-Type: application/json' \
     -d '{"title":"LocalOCR","body":"Your receipt was filed.","url":"/"}'
   ```

4. A notification appears. Clicking it focuses an open tab or opens the site.

## Security checklist

- [ ] Private key is set via env var only — not in the repo, not in client code.
- [ ] `vapidPublicKey` in the site config is the **public** key.
- [ ] Site is served over HTTPS (or localhost during development).
- [ ] `ALLOW_ORIGIN` is restricted to your site's origin in production.
- [ ] Subscriptions are persisted to a real datastore before going live.
