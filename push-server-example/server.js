'use strict';

/*
 * Minimal Web Push example server for LocalOCR.
 *
 * This is NOT part of the static site and is NOT required to serve it. A static
 * PWA cannot send push messages itself — that requires a server holding the
 * VAPID PRIVATE key. This example does the two things such a server must do:
 *
 *   POST /save-subscription   store a browser's PushSubscription
 *   POST /send                push a notification to every stored subscription
 *
 * SECURITY: the VAPID private key is read from an environment variable. It must
 * NEVER be hardcoded here, shipped to the browser, or committed to the repo.
 *
 * Subscriptions are kept in memory for the demo. Use a real database in
 * production.
 */

const express = require('express');
const webpush = require('web-push');

const PORT = process.env.PORT || 4000;
const VAPID_PUBLIC_KEY = process.env.VAPID_PUBLIC_KEY;
const VAPID_PRIVATE_KEY = process.env.VAPID_PRIVATE_KEY;          // secret — env only
const VAPID_SUBJECT = process.env.VAPID_SUBJECT || 'mailto:admin@example.com';
// Origin allowed to call this server (the site that serves the PWA).
const ALLOW_ORIGIN = process.env.ALLOW_ORIGIN || '*';

if (!VAPID_PUBLIC_KEY || !VAPID_PRIVATE_KEY) {
  console.error(
    'Missing VAPID keys. Generate a pair with:\n' +
    '  npx web-push generate-vapid-keys\n' +
    'then start the server with both set, e.g.:\n' +
    '  VAPID_PUBLIC_KEY=... VAPID_PRIVATE_KEY=... node server.js'
  );
  process.exit(1);
}

webpush.setVapidDetails(VAPID_SUBJECT, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY);

const app = express();
app.use(express.json());

// Minimal CORS so the browser on the site origin can POST here.
app.use((req, res, next) => {
  res.set('Access-Control-Allow-Origin', ALLOW_ORIGIN);
  res.set('Access-Control-Allow-Headers', 'Content-Type');
  res.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});

/** In-memory subscription store (swap for a DB in production). */
const subscriptions = new Map(); // endpoint -> subscription

app.post('/save-subscription', (req, res) => {
  const sub = req.body;
  if (!sub || !sub.endpoint) {
    return res.status(400).json({ error: 'Invalid subscription' });
  }
  subscriptions.set(sub.endpoint, sub);
  console.log(`Saved subscription (${subscriptions.size} total)`);
  res.status(201).json({ ok: true });
});

app.post('/send', async (req, res) => {
  const payload = JSON.stringify({
    title: (req.body && req.body.title) || 'LocalOCR',
    body: (req.body && req.body.body) || 'Hello from your own push server.',
    url: (req.body && req.body.url) || '/',
    icon: '/icon-192.png'
  });

  const results = await Promise.allSettled(
    [...subscriptions.values()].map((sub) => webpush.sendNotification(sub, payload))
  );

  // Drop subscriptions the push service reports as gone (404/410).
  results.forEach((result, i) => {
    if (result.status === 'rejected') {
      const code = result.reason && result.reason.statusCode;
      if (code === 404 || code === 410) {
        subscriptions.delete([...subscriptions.keys()][i]);
      }
    }
  });

  const sent = results.filter((r) => r.status === 'fulfilled').length;
  res.json({ sent, total: results.length });
});

app.get('/health', (_req, res) => res.json({ ok: true, subscriptions: subscriptions.size }));

app.listen(PORT, () => {
  console.log(`Push example server listening on http://localhost:${PORT}`);
});
