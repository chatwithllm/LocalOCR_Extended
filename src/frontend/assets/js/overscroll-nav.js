// ===========================================================
// Overscroll-to-navigate
// -----------------------------------------------------------
// Touch / wheel gesture: pull past the top of the document →
// previous sidebar page; pull past the bottom → next page.
// Visible affordance banner labels the target page; releasing
// past threshold commits via nav(). Yields to the Bills page
// PTR (which scopes scrolling to #bills-body) and to any
// inner scrollable container the gesture started in.
// ===========================================================
(function () {
  const TOUCH_THRESHOLD_BASE = 80;
  const WHEEL_THRESHOLD_TRACKPAD = 60;
  const WHEEL_THRESHOLD_MOUSE = 80;
  const WHEEL_RESET_MS = 250;
  const COMMIT_COOLDOWN_MS = 700;
  const DIRECTION_LOCK_MIN = 8;

  let banner = null;
  let bannerLabel = null;
  let bannerArrow = null;

  // Touch state
  let active = false;
  let startY = 0;
  let direction = 0; // -1 = pulling-down-at-top (prev); +1 = pulling-up-at-bottom (next)
  let armed = false;
  let targetPage = null;
  let targetLabel = "";

  // Wheel state
  let wheelAccum = 0;
  let wheelLastTs = 0;
  let cooldownUntil = 0;

  function ensureBanner() {
    if (banner) return banner;
    banner = document.createElement("div");
    banner.id = "overscroll-nav";
    banner.className = "osn";
    banner.setAttribute("aria-hidden", "true");
    banner.innerHTML =
      '<span class="osn__arrow" aria-hidden="true"></span>' +
      '<span class="osn__label"></span>';
    document.body.appendChild(banner);
    bannerLabel = banner.querySelector(".osn__label");
    bannerArrow = banner.querySelector(".osn__arrow");
    return banner;
  }

  function getVisibleSidebarPages() {
    const items = document.querySelectorAll(
      '.sidebar .nav-item[onclick^="nav("]',
    );
    const out = [];
    items.forEach((el) => {
      if (el.offsetParent === null) return; // hidden by CSS or display:none
      const m = String(el.getAttribute("onclick") || "").match(
        /nav\(\s*['"]([^'"]+)['"]/,
      );
      if (m) out.push(m[1]);
    });
    return out;
  }

  function getCurrentPageId() {
    const active = document.querySelector(".page.active");
    if (!active) return null;
    return (active.id || "").replace(/^page-/, "") || null;
  }

  function getAdjacentPage(dir) {
    const list = getVisibleSidebarPages();
    const cur = getCurrentPageId();
    const i = list.indexOf(cur);
    if (i < 0) return null;
    return list[i + dir] || null;
  }

  function getPageNavLabel(pageId) {
    const items = document.querySelectorAll(
      '.sidebar .nav-item[onclick^="nav("]',
    );
    for (const el of items) {
      const m = String(el.getAttribute("onclick") || "").match(
        /nav\(\s*['"]([^'"]+)['"]/,
      );
      if (m && m[1] === pageId) {
        const clone = el.cloneNode(true);
        clone
          .querySelectorAll(".nav-icon")
          .forEach((n) => n.remove());
        return clone.textContent.replace(/\s+/g, " ").trim();
      }
    }
    return pageId;
  }

  function getNavItemEl(pageId) {
    const items = document.querySelectorAll(
      '.sidebar .nav-item[onclick^="nav("]',
    );
    for (const el of items) {
      const m = String(el.getAttribute("onclick") || "").match(
        /nav\(\s*['"]([^'"]+)['"]/,
      );
      if (m && m[1] === pageId) return el;
    }
    return null;
  }

  function reducedMotion() {
    return (
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  // Edge-pull navigation is opt-in. Default off — readers were
  // hitting it accidentally on long pages and the recovery path
  // (open sidebar, click previous) felt punitive. Power users can
  // re-enable in Settings → Navigation.
  function overscrollNavEnabled() {
    try {
      return localStorage.getItem("overscroll_nav_enabled") === "1";
    } catch (_e) {
      return false;
    }
  }

  function shouldSuppressOverscroll(eventTarget) {
    // Long-press menu open
    if (document.querySelector(".inv-context-menu")) return true;
    // Focused text input
    const ae = document.activeElement;
    if (
      ae &&
      (ae.tagName === "INPUT" ||
        ae.tagName === "TEXTAREA" ||
        ae.tagName === "SELECT" ||
        ae.isContentEditable)
    )
      return true;
    // Modal/snapshot viewers open (best-effort match)
    if (
      document.querySelector(
        ".modal.active, .modal-overlay.active, .receipt-detail-overlay.active, .snapshot-overlay.active",
      )
    )
      return true;
    // Inside an inner scrollable container that isn't body/html
    if (eventTarget && eventTarget.nodeType === 1) {
      let node = eventTarget;
      while (node && node !== document.body && node !== document.documentElement) {
        if (node.scrollHeight - node.clientHeight > 1) {
          const cs = window.getComputedStyle(node);
          const oy = cs.overflowY;
          if (oy === "auto" || oy === "scroll") return true;
        }
        node = node.parentNode;
      }
    }
    return false;
  }

  function docScrollTop() {
    return (
      window.scrollY ||
      window.pageYOffset ||
      document.documentElement.scrollTop ||
      0
    );
  }

  function docAtTop() {
    return docScrollTop() <= 0;
  }

  function docAtBottom() {
    const st = docScrollTop();
    const ch = window.innerHeight;
    const sh = Math.max(
      document.documentElement.scrollHeight,
      document.body.scrollHeight,
    );
    return st + ch >= sh - 1;
  }

  function touchThreshold() {
    return Math.min(
      TOUCH_THRESHOLD_BASE,
      Math.max(40, Math.round(window.innerHeight * 0.12)),
    );
  }

  function rubberBand(distance) {
    const sign = Math.sign(distance);
    const abs = Math.abs(distance);
    const eased = Math.min(120, Math.pow(abs, 0.8) * 0.5);
    return sign * eased;
  }

  function setBannerForDirection(dir) {
    ensureBanner();
    const pageId = getAdjacentPage(dir);
    const isDisabled = !pageId;
    targetPage = pageId;
    targetLabel = pageId ? getPageNavLabel(pageId) : "";
    banner.classList.toggle("is-bottom", dir > 0);
    banner.classList.toggle("is-top", dir < 0);
    banner.classList.toggle("is-disabled", isDisabled);
    banner.classList.add("is-visible");
    banner.classList.remove("is-snapping");
    updateBannerLabel(false);
  }

  function updateBannerLabel(armedNow) {
    if (!banner) return;
    if (!targetPage) {
      bannerLabel.textContent = "End of navigation";
      bannerArrow.textContent = direction < 0 ? "↓" : "↑";
      return;
    }
    const arrow = direction > 0 ? "↑" : "↓";
    bannerArrow.textContent = arrow;
    bannerLabel.textContent =
      (armedNow ? "Release to go to " : "Pull to go to ") +
      targetLabel +
      " →";
  }

  function applyPullVisual(rawDy) {
    if (!banner) return;
    const dist = rubberBand(rawDy);
    if (reducedMotion()) {
      banner.style.transform = "";
    } else {
      banner.style.transform =
        "translateX(-50%) translateY(" + dist + "px)";
    }
    const wasArmed = armed;
    armed = Math.abs(rawDy) >= touchThreshold() && !!targetPage;
    if (armed !== wasArmed) {
      banner.classList.toggle("is-armed", armed);
      updateBannerLabel(armed);
    }
  }

  function snapBannerAway() {
    if (!banner) return;
    banner.classList.add("is-snapping");
    banner.classList.remove("is-visible", "is-armed");
    banner.style.transform = "";
    armed = false;
    targetPage = null;
  }

  function commitNavigation(pageId, opts) {
    const navEl = getNavItemEl(pageId);
    const dirAtCommit = direction; // captured before reset
    const label = getPageNavLabel(pageId);
    let icon = "";
    if (navEl) {
      const iconEl = navEl.querySelector(".nav-icon");
      if (iconEl) icon = iconEl.textContent.trim();
    }
    cooldownUntil = Date.now() + COMMIT_COOLDOWN_MS;
    // Iris transition: open the veil over the current page first,
    // swap pages while covered, then close the veil to reveal the
    // new page. Per-page motif paints inside the veil so the user
    // sees a hint of where they're going (boxes for inventory,
    // sparkline for dashboard, scan sweep for receipts).
    playIrisTransition(dirAtCommit, icon, label, pageId, opts || {}, () => {
      window.nav && window.nav(pageId, navEl);
    });
  }

  function playIrisTransition(dir, icon, label, targetPageId, opts, swapFn) {
    const x = "50%";
    const y = dir > 0 ? "100%" : dir < 0 ? "0%" : "50%";
    const clip0 = "circle(0% at " + x + " " + y + ")";
    const clipFull = "circle(160% at " + x + " " + y + ")";
    // Tempo: button-triggered nav uses "fast" so a click feels
    // closer to instant; gesture nav keeps the longer "default"
    // cinematic timing so the motif has room to read.
    const tempo = (opts && opts.tempo) || "default";
    const OPEN_MS = tempo === "fast" ? 240 : 320;
    const HOLD_MS = tempo === "fast" ? 350 : 650;
    const CLOSE_MS = tempo === "fast" ? 280 : 360;
    const reduced =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const veil = document.createElement("div");
    veil.className = "iris-veil";
    veil.style.zIndex = "100000";
    // Start invisible (empty circle).
    veil.style.clipPath = clip0;
    veil.style.webkitClipPath = clip0;

    // Per-page motif canvas behind the badge.
    const canvas = document.createElement("canvas");
    canvas.className = "iris-matrix-canvas";
    veil.appendChild(canvas);

    const badge = document.createElement("div");
    badge.className = "iris-veil__badge";
    badge.innerHTML =
      (icon ? '<span>' + icon + "</span>" : "") +
      "<span>" + (label || "").replace(/</g, "&lt;") + "</span>";
    veil.appendChild(badge);
    document.body.appendChild(veil);

    // Start the page-themed motif as soon as the veil mounts.
    const stopMatrix = startMotif(targetPageId, canvas);

    // Force layout so the first transition starts from clip0.
    void veil.offsetHeight;

    if (reduced) {
      // No motion — just cover, swap, uncover via opacity.
      veil.style.clipPath = "none";
      veil.style.webkitClipPath = "none";
      veil.style.opacity = "0.95";
      veil.style.transition = "opacity 180ms linear";
      setTimeout(() => {
        try { swapFn && swapFn(); } catch (e) { console.error(e); }
        setTimeout(() => {
          veil.style.opacity = "0";
          setTimeout(() => veil.remove(), 220);
        }, HOLD_MS);
      }, 180);
      return;
    }

    // Phase 1: open. CSS transition on clip-path — deterministic
    // and well-supported since values are fully-resolved strings.
    veil.style.transition =
      "clip-path " + OPEN_MS + "ms cubic-bezier(0.22, 1, 0.36, 1), " +
      "-webkit-clip-path " + OPEN_MS + "ms cubic-bezier(0.22, 1, 0.36, 1)";
    requestAnimationFrame(() => {
      veil.style.clipPath = clipFull;
      veil.style.webkitClipPath = clipFull;
    });

    // Phase 2: fully covered → swap pages + reveal the badge.
    setTimeout(() => {
      veil.classList.add("is-held");
      try { swapFn && swapFn(); } catch (e) { console.error(e); }
    }, OPEN_MS);

    // Phase 3: close — contract circle, revealing new page.
    setTimeout(() => {
      veil.classList.remove("is-held");
      veil.style.transition =
        "clip-path " + CLOSE_MS + "ms cubic-bezier(0.22, 1, 0.36, 1), " +
        "-webkit-clip-path " + CLOSE_MS + "ms cubic-bezier(0.22, 1, 0.36, 1)";
      veil.style.clipPath = clip0;
      veil.style.webkitClipPath = clip0;
    }, OPEN_MS + HOLD_MS);

    // Phase 4: cleanup.
    setTimeout(() => {
      stopMatrix && stopMatrix();
      veil.remove();
    }, OPEN_MS + HOLD_MS + CLOSE_MS + 50);
  }

  // ----- Motif dispatcher -----
  // Each motif paints a page-themed teaser inside the iris veil.
  // Signature: (canvas) -> stopFn. Stop is called on veil cleanup.
  // Unknown pageIds fall back to the matrix rain so unmotifed
  // pages still get a transition rather than a blank veil.
  function startMotif(pageId, canvas) {
    switch (pageId) {
      case "dashboard":     return motifDashboard(canvas);
      case "inventory":     return motifInventory(canvas);
      case "receipts":      return motifReceipts(canvas);
      case "shopping":      return motifShopping(canvas);
      case "expenses":      return motifExpenses(canvas);
      case "budget":        return motifBudget(canvas);
      case "bills":         return motifBills(canvas);
      case "accounts":      return motifAccounts(canvas);
      case "analytics":     return motifAnalytics(canvas);
      case "contributions": return motifContributions(canvas);
      case "settings":      return motifSettings(canvas);
      case "restaurant":    return motifRestaurant(canvas);
      case "upload":        return motifUpload(canvas);
      default:              return motifMatrix(canvas);
    }
  }

  function readThemeTokens() {
    const cs = getComputedStyle(document.documentElement);
    const get = (name, fallback) =>
      (cs.getPropertyValue(name).trim() || fallback);
    return {
      surface:   get("--color-surface", "#0a0a0a"),
      surface2:  get("--color-surface-2", "#1a1a1a"),
      text:      get("--color-text-primary", "#f5f5f7"),
      muted:     get("--color-text-muted", "#888"),
      brand:     get("--color-brand", "#0a84ff"),
      brandSoft: get("--color-brand-soft", "rgba(10,132,255,0.18)"),
      border:    get("--color-border", "#333"),
    };
  }

  function setupMotifCanvas(canvas) {
    const ctx = canvas.getContext("2d");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = window.innerWidth;
    const h = window.innerHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w, h };
  }

  function roundRectPath(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // ----- motifDashboard: animated KPI pills + sparkline -----
  function motifDashboard(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    const N = 60;
    const points = [];
    for (let i = 0; i < N; i++) {
      points.push(0.4 + 0.45 * Math.sin(i * 0.32) + (Math.random() - 0.5) * 0.12);
    }
    const targets = [4029, 138, 472];
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.fillRect(0, 0, w, h);
      // KPI pills
      const pillW = Math.min(220, w * 0.22);
      const pillH = 64;
      const gap = Math.min(40, w * 0.04);
      const totalW = pillW * 3 + gap * 2;
      const startX = (w - totalW) / 2;
      const baselineY = h * 0.62;
      const py = baselineY - h * 0.30;
      ctx.font = "600 28px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (let i = 0; i < 3; i++) {
        const px = startX + i * (pillW + gap);
        ctx.fillStyle = tk.surface2;
        roundRectPath(ctx, px, py, pillW, pillH, 14);
        ctx.fill();
        ctx.strokeStyle = tk.brandSoft;
        ctx.lineWidth = 1;
        roundRectPath(ctx, px, py, pillW, pillH, 14);
        ctx.stroke();
        const counter = Math.min(
          targets[i],
          Math.floor((Math.max(0, t - i * 0.12) * 1.6) * targets[i]),
        );
        ctx.fillStyle = tk.text;
        ctx.fillText(counter.toLocaleString(), px + pillW / 2, py + pillH / 2);
      }
      // Sparkline
      const progress = Math.min(1, t / 0.9);
      const visible = Math.floor(N * progress);
      const ampY = h * 0.16;
      ctx.strokeStyle = tk.brand;
      ctx.lineWidth = 3;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      for (let i = 0; i <= visible && i < N; i++) {
        const x = (i / (N - 1)) * w;
        const y = baselineY - points[i] * ampY;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      if (visible < N) {
        const x = (visible / (N - 1)) * w;
        const y = baselineY - points[visible] * ampY;
        ctx.fillStyle = tk.brand;
        ctx.beginPath();
        ctx.arc(x, y, 5 + 2 * Math.sin(t * 12), 0, Math.PI * 2);
        ctx.fill();
      }
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifInventory: stacking boxes -----
  function motifInventory(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    const COLS = Math.max(5, Math.min(10, Math.floor(w / 110)));
    const stacks = [];
    for (let i = 0; i < COLS; i++) {
      stacks.push({
        delay: Math.random() * 0.35,
        maxBoxes: 4 + Math.floor(Math.random() * 4),
        speed: 0.55 + Math.random() * 0.4,
      });
    }
    function drawBox(x, y, bw, bh) {
      ctx.fillStyle = tk.surface2;
      ctx.fillRect(x, y, bw, bh);
      ctx.strokeStyle = tk.brand;
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 1, y + 1, bw - 2, bh - 2);
      ctx.fillStyle = tk.brandSoft;
      ctx.fillRect(x + bw * 0.2, y - 3, bw * 0.6, 6);
      ctx.beginPath();
      ctx.moveTo(x, y + bh * 0.5);
      ctx.lineTo(x + bw, y + bh * 0.5);
      ctx.strokeStyle = tk.border;
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.16)";
      ctx.fillRect(0, 0, w, h);
      const colW = w / COLS;
      const boxW = colW * 0.74;
      const boxH = boxW * 0.62;
      const padX = (colW - boxW) / 2;
      const baselineY = h * 0.88;
      for (let c = 0; c < COLS; c++) {
        const s = stacks[c];
        const localT = Math.max(0, t - s.delay) * s.speed;
        const stacked = Math.min(s.maxBoxes, Math.floor(localT));
        const partial = Math.min(1, localT - stacked);
        for (let i = 0; i < stacked; i++) {
          drawBox(c * colW + padX, baselineY - (i + 1) * boxH, boxW, boxH);
        }
        if (stacked < s.maxBoxes) {
          const startY = -boxH;
          const targetY = baselineY - (stacked + 1) * boxH;
          const eased = 1 - Math.pow(1 - partial, 3);
          drawBox(c * colW + padX, startY + (targetY - startY) * eased, boxW, boxH);
        }
      }
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifReceipts: paper unroll + scan sweep -----
  function motifReceipts(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    const ROWS = 14;
    const rows = [];
    for (let i = 0; i < ROWS; i++) {
      rows.push({
        kind: i === 0 || (Math.random() < 0.22) ? "header" : "item",
        width: 0.55 + Math.random() * 0.35,
        delay: 0.05 + i * 0.06,
      });
    }
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.20)";
      ctx.fillRect(0, 0, w, h);
      const paperW = Math.min(440, w * 0.42);
      const paperX = (w - paperW) / 2;
      const paperHFinal = h * 0.86;
      const unrollT = Math.min(1, t / 0.55);
      const paperH = paperHFinal * unrollT;
      const paperY = h * 0.05;
      ctx.fillStyle = tk.surface2;
      ctx.fillRect(paperX, paperY, paperW, paperH);
      ctx.fillStyle = tk.brandSoft;
      ctx.fillRect(paperX, paperY, 4, paperH);
      const rowH = 18;
      for (let i = 0; i < ROWS; i++) {
        const r = rows[i];
        if (t < r.delay) continue;
        const rowY = paperY + 30 + i * (rowH + 6);
        if (rowY > paperY + paperH - 20) continue;
        const opacity = Math.min(1, (t - r.delay) * 4);
        ctx.globalAlpha = opacity;
        if (r.kind === "header") {
          ctx.fillStyle = tk.brand;
          ctx.fillRect(paperX + 16, rowY, paperW * r.width - 32, 4);
        } else {
          ctx.fillStyle = tk.text;
          ctx.fillRect(paperX + 16, rowY, paperW * r.width - 32, 3);
        }
        ctx.globalAlpha = 1;
      }
      if (unrollT >= 1) {
        const scanT = ((t - 0.55) % 0.9) / 0.9;
        const scanY = paperY + scanT * paperH;
        const grad = ctx.createLinearGradient(0, scanY - 14, 0, scanY + 14);
        grad.addColorStop(0, "rgba(0,0,0,0)");
        grad.addColorStop(0.5, tk.brand);
        grad.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = grad;
        ctx.fillRect(paperX, scanY - 14, paperW, 28);
      }
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifShopping: checklist items being checked off -----
  function motifShopping(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    const ROWS = 9;
    const items = [];
    for (let i = 0; i < ROWS; i++) {
      items.push({ delay: 0.08 + i * 0.12, width: 0.5 + Math.random() * 0.35 });
    }
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.fillRect(0, 0, w, h);
      const listW = Math.min(440, w * 0.42);
      const listX = (w - listW) / 2;
      const rowH = 38;
      const startY = h * 0.16;
      for (let i = 0; i < ROWS; i++) {
        const r = items[i];
        if (t < r.delay) continue;
        const rowY = startY + i * (rowH + 8);
        const checkProg = Math.min(1, (t - r.delay) * 4);
        const opacity = Math.min(1, (t - r.delay) * 5);
        ctx.globalAlpha = opacity;
        ctx.strokeStyle = tk.brand;
        ctx.lineWidth = 2;
        ctx.strokeRect(listX, rowY, 22, 22);
        if (checkProg > 0.5) {
          const ck = (checkProg - 0.5) * 2;
          ctx.fillStyle = tk.brand;
          ctx.fillRect(listX + 2, rowY + 2, 18, 18);
          ctx.strokeStyle = "#fff";
          ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.moveTo(listX + 5, rowY + 12);
          ctx.lineTo(listX + 9, rowY + 16);
          ctx.lineTo(listX + 9 + 8 * ck, rowY + 16 - 8 * ck);
          ctx.stroke();
        }
        ctx.fillStyle = checkProg > 0.5 ? tk.muted : tk.text;
        ctx.fillRect(listX + 32, rowY + 8, (listW - 32) * r.width, 4);
        ctx.fillRect(listX + 32, rowY + 16, (listW - 32) * r.width * 0.6, 3);
        ctx.globalAlpha = 1;
      }
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifExpenses: rising bar chart -----
  function motifExpenses(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    const N = 10;
    const targets = [];
    for (let i = 0; i < N; i++) targets.push(0.3 + Math.random() * 0.6);
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.16)";
      ctx.fillRect(0, 0, w, h);
      const chartW = Math.min(640, w * 0.7);
      const chartX = (w - chartW) / 2;
      const chartH = h * 0.55;
      const baselineY = h * 0.78;
      const barGap = chartW * 0.02;
      const barW = (chartW - barGap * (N - 1)) / N;
      ctx.strokeStyle = tk.border;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(chartX, baselineY);
      ctx.lineTo(chartX + chartW, baselineY);
      ctx.stroke();
      for (let i = 0; i < N; i++) {
        const localT = Math.max(0, t - i * 0.06) * 1.3;
        const eased = 1 - Math.pow(1 - Math.min(1, localT), 3);
        const bh = targets[i] * chartH * eased;
        const bx = chartX + i * (barW + barGap);
        const by = baselineY - bh;
        ctx.fillStyle = i % 3 === 0 ? tk.brand : tk.brandSoft;
        ctx.fillRect(bx, by, barW, bh);
        ctx.fillStyle = tk.brand;
        ctx.fillRect(bx, by, barW, 3);
      }
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifBudget: progress ring filling with % counter -----
  function motifBudget(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.fillRect(0, 0, w, h);
      const cx = w / 2, cy = h / 2;
      const radius = Math.min(w, h) * 0.20;
      const ringW = 18;
      ctx.strokeStyle = tk.surface2;
      ctx.lineWidth = ringW;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.stroke();
      const progress = Math.min(1, t / 1.1);
      ctx.strokeStyle = tk.brand;
      ctx.lineWidth = ringW;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.arc(cx, cy, radius, -Math.PI / 2, -Math.PI / 2 + progress * Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = tk.text;
      ctx.font = "700 56px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(Math.floor(progress * 100) + "%", cx, cy);
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifBills: calendar tiles flipping in -----
  function motifBills(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    const COLS = 7, ROWS = 5;
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.fillRect(0, 0, w, h);
      const gridW = Math.min(560, w * 0.5);
      const gridH = gridW * 0.7;
      const tileGap = 4;
      const tileW = (gridW - tileGap * (COLS - 1)) / COLS;
      const tileH = (gridH - tileGap * (ROWS - 1)) / ROWS;
      const startX = (w - gridW) / 2;
      const startY = (h - gridH) / 2;
      ctx.font = "600 16px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      let day = 1;
      for (let r = 0; r < ROWS; r++) {
        for (let c = 0; c < COLS; c++) {
          const idx = r * COLS + c;
          const delay = idx * 0.025;
          const localT = Math.max(0, t - delay) * 3;
          const sy = Math.max(0.05, Math.abs(Math.cos(Math.min(1, localT) * Math.PI)));
          const showFront = localT >= 0.5;
          const x = startX + c * (tileW + tileGap);
          const y = startY + r * (tileH + tileGap);
          const dh = tileH * sy;
          const dy = y + (tileH - dh) / 2;
          const isDue = day % 7 === 0;
          ctx.fillStyle = showFront && isDue ? tk.brand : tk.surface2;
          ctx.fillRect(x, dy, tileW, dh);
          ctx.strokeStyle = tk.border;
          ctx.lineWidth = 1;
          ctx.strokeRect(x + 0.5, dy + 0.5, tileW - 1, dh - 1);
          if (showFront && dh > tileH * 0.5) {
            ctx.fillStyle = isDue ? "#fff" : tk.text;
            ctx.fillText(String(day), x + tileW / 2, y + tileH / 2);
          }
          day++;
        }
      }
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifAccounts: bank cards fanning out -----
  function motifAccounts(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    const CARDS = 5;
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.fillRect(0, 0, w, h);
      const cardW = Math.min(240, w * 0.22);
      const cardH = cardW * 0.62;
      const cx = w / 2, cy = h * 0.55;
      for (let i = 0; i < CARDS; i++) {
        const delay = i * 0.08;
        const localT = Math.max(0, t - delay);
        const fanProg = 1 - Math.pow(1 - Math.min(1, localT * 1.6), 3);
        const angle = ((i - (CARDS - 1) / 2) * 0.18) * fanProg;
        const offsetY = (1 - fanProg) * 60;
        ctx.save();
        ctx.translate(cx, cy + offsetY);
        ctx.rotate(angle);
        ctx.fillStyle = "rgba(0,0,0,0.30)";
        ctx.fillRect(-cardW / 2 + 4, -cardH / 2 + 6, cardW, cardH);
        const grad = ctx.createLinearGradient(-cardW / 2, -cardH / 2, cardW / 2, cardH / 2);
        grad.addColorStop(0, tk.brand);
        grad.addColorStop(1, tk.brandSoft);
        ctx.fillStyle = grad;
        roundRectPath(ctx, -cardW / 2, -cardH / 2, cardW, cardH, 12);
        ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,0.55)";
        ctx.fillRect(-cardW / 2 + 16, -cardH / 2 + 16, 28, 22);
        ctx.fillStyle = "rgba(255,255,255,0.7)";
        for (let s = 0; s < 4; s++) {
          ctx.fillRect(-cardW / 2 + 16 + s * 38, cardH / 2 - 22, 28, 4);
        }
        ctx.restore();
      }
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifAnalytics: donut chart segments filling -----
  function motifAnalytics(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    const segments = [0.32, 0.24, 0.18, 0.14, 0.12];
    const colors = [tk.brand, tk.brandSoft, tk.muted, tk.border, tk.surface2];
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.fillRect(0, 0, w, h);
      const cx = w / 2, cy = h / 2;
      const rad = Math.min(w, h) * 0.24;
      const innerR = rad * 0.55;
      const totalProgress = Math.min(1, t / 1.1);
      let cumulative = 0;
      const startAngle = -Math.PI / 2;
      for (let i = 0; i < segments.length; i++) {
        const segStart = cumulative;
        const segEnd = cumulative + segments[i];
        const visEnd = Math.min(totalProgress, segEnd);
        const visSize = Math.max(0, visEnd - segStart);
        if (visSize > 0) {
          const a0 = startAngle + segStart * Math.PI * 2;
          const a1 = startAngle + (segStart + visSize) * Math.PI * 2;
          ctx.fillStyle = colors[i % colors.length] || tk.brand;
          ctx.beginPath();
          ctx.moveTo(cx, cy);
          ctx.arc(cx, cy, rad, a0, a1);
          ctx.closePath();
          ctx.fill();
        }
        cumulative = segEnd;
      }
      ctx.fillStyle = tk.surface;
      ctx.beginPath();
      ctx.arc(cx, cy, innerR, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = tk.text;
      ctx.font = "700 36px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(Math.floor(totalProgress * 100) + "%", cx, cy);
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifContributions: coins falling into a pot -----
  function motifContributions(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    const COINS = 14;
    const coins = [];
    for (let i = 0; i < COINS; i++) {
      coins.push({
        delay: Math.random() * 1.0,
        x: 0.32 + Math.random() * 0.36,
        finalY: 0.82 - i * 0.005,
        r: 12 + Math.random() * 6,
      });
    }
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.fillRect(0, 0, w, h);
      const potW = Math.min(300, w * 0.28);
      const potH = potW * 0.55;
      const potX = (w - potW) / 2;
      const potY = h * 0.78;
      ctx.fillStyle = tk.surface2;
      roundRectPath(ctx, potX, potY, potW, potH, 14);
      ctx.fill();
      ctx.strokeStyle = tk.brand;
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.fillStyle = tk.brandSoft;
      ctx.fillRect(potX + 6, potY + 6, potW - 12, 8);
      for (let i = 0; i < coins.length; i++) {
        const c = coins[i];
        if (t < c.delay) continue;
        const localT = Math.min(1, (t - c.delay) * 1.4);
        const eased = 1 - Math.pow(1 - localT, 2);
        const x = c.x * w;
        const y = (-0.05 + (c.finalY - -0.05) * eased) * h;
        ctx.fillStyle = tk.brand;
        ctx.beginPath();
        ctx.arc(x, y, c.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = tk.brandSoft;
        ctx.beginPath();
        ctx.arc(x - c.r * 0.25, y - c.r * 0.25, c.r * 0.45, 0, Math.PI * 2);
        ctx.fill();
      }
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifSettings: concentric gears rotating -----
  function motifSettings(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    function drawGear(cx, cy, r, teeth, thickness, rotation, color) {
      ctx.fillStyle = color;
      ctx.beginPath();
      for (let i = 0; i < teeth * 2; i++) {
        const angle = (i / (teeth * 2)) * Math.PI * 2 + rotation;
        const radius = i % 2 === 0 ? r : r - thickness;
        const x = cx + Math.cos(angle) * radius;
        const y = cy + Math.sin(angle) * radius;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = "rgba(0,0,0,0.4)";
      ctx.beginPath();
      ctx.arc(cx, cy, r * 0.32, 0, Math.PI * 2);
      ctx.fill();
    }
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.fillRect(0, 0, w, h);
      const cx = w / 2, cy = h / 2;
      const u = Math.min(w, h);
      drawGear(cx,           cy,            u * 0.22, 12,  18,  t * 0.8, tk.brand);
      drawGear(cx + u * 0.16, cy + u * 0.14, u * 0.13, 10,  12, -t * 1.3, tk.brandSoft);
      drawGear(cx - u * 0.18, cy - u * 0.10, u * 0.10,  8,  10,  t * 1.6, tk.muted);
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifRestaurant: plate, utensils, steam -----
  function motifRestaurant(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.fillRect(0, 0, w, h);
      const cx = w / 2, cy = h * 0.6;
      const plateR = Math.min(w, h) * 0.20;
      const plateProgress = Math.min(1, t / 0.45);
      ctx.strokeStyle = tk.text;
      ctx.lineWidth = 4;
      ctx.beginPath();
      ctx.arc(cx, cy, plateR, -Math.PI / 2, -Math.PI / 2 + plateProgress * Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = tk.surface2;
      ctx.beginPath();
      ctx.arc(cx, cy, plateR * 0.85, 0, Math.PI * 2);
      ctx.fill();
      // Steam
      for (let i = 0; i < 5; i++) {
        const phase = (t * 1.4 + i * 0.4) % 2;
        if (phase > 1.5) continue;
        const opacity = Math.max(0, 1 - phase);
        const offX = (i - 2) * 18 + Math.sin(phase * 4 + i) * 8;
        const sy = cy - plateR - phase * 80;
        ctx.fillStyle = tk.brandSoft;
        ctx.globalAlpha = opacity * 0.6;
        ctx.beginPath();
        ctx.arc(cx + offX, sy, 6 + phase * 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
      // Utensils slide in from sides
      const utenT = Math.min(1, Math.max(0, (t - 0.45)) / 0.45);
      const utenSlide = (1 - utenT) * 100;
      ctx.strokeStyle = tk.brand;
      ctx.lineWidth = 6;
      ctx.lineCap = "round";
      // Fork (left)
      const fx = cx - plateR * 1.6 - utenSlide;
      ctx.beginPath();
      ctx.moveTo(fx, cy - plateR);
      ctx.lineTo(fx, cy + plateR);
      ctx.stroke();
      ctx.lineWidth = 3;
      for (let i = -1; i <= 1; i++) {
        ctx.beginPath();
        ctx.moveTo(fx + i * 5, cy - plateR);
        ctx.lineTo(fx + i * 5, cy - plateR * 0.55);
        ctx.stroke();
      }
      // Knife (right)
      ctx.lineWidth = 6;
      const kx = cx + plateR * 1.6 + utenSlide;
      ctx.beginPath();
      ctx.moveTo(kx, cy - plateR);
      ctx.lineTo(kx, cy + plateR);
      ctx.stroke();
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifUpload: focus reticle + scan sweep -----
  function motifUpload(canvas) {
    const { ctx, w, h } = setupMotifCanvas(canvas);
    const tk = readThemeTokens();
    const t0 = performance.now();
    let rafId = null, stopped = false;
    function draw(now) {
      if (stopped) return;
      const t = (now - t0) / 1000;
      ctx.fillStyle = "rgba(0,0,0,0.20)";
      ctx.fillRect(0, 0, w, h);
      const cx = w / 2, cy = h / 2;
      const boxSize = Math.min(w, h) * 0.5;
      const x = cx - boxSize / 2;
      const y = cy - boxSize / 2;
      const cornerLen = 36;
      ctx.strokeStyle = tk.brand;
      ctx.lineWidth = 4;
      ctx.lineCap = "round";
      const reticleProg = Math.min(1, t / 0.4);
      const r = reticleProg * cornerLen;
      const corners = [
        [x, y, 1, 1],
        [x + boxSize, y, -1, 1],
        [x, y + boxSize, 1, -1],
        [x + boxSize, y + boxSize, -1, -1],
      ];
      for (const [px, py, dx, dy] of corners) {
        ctx.beginPath();
        ctx.moveTo(px, py + r * dy);
        ctx.lineTo(px, py);
        ctx.lineTo(px + r * dx, py);
        ctx.stroke();
      }
      if (reticleProg >= 1) {
        const scanT = ((t - 0.4) % 1.0) / 1.0;
        const scanY = y + scanT * boxSize;
        const grad = ctx.createLinearGradient(x, scanY - 16, x, scanY + 16);
        grad.addColorStop(0, "rgba(0,0,0,0)");
        grad.addColorStop(0.5, tk.brand);
        grad.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = grad;
        ctx.fillRect(x, scanY - 16, boxSize, 32);
        ctx.strokeStyle = tk.brand;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, scanY);
        ctx.lineTo(x + boxSize, scanY);
        ctx.stroke();
      }
      rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);
    return () => { stopped = true; if (rafId) cancelAnimationFrame(rafId); };
  }

  // ----- motifMatrix: default fallback (Katakana rain) -----
  function motifMatrix(canvas) {
    const ctx = canvas.getContext("2d");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let rafId = null;
    let stopped = false;
    const chars =
      "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ$%&@#";
    const fontSize = 16;
    let cols = 0;
    let drops = [];

    function resize() {
      const w = window.innerWidth;
      const h = window.innerHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = w + "px";
      canvas.style.height = h + "px";
      ctx.scale(dpr, dpr);
      cols = Math.max(1, Math.floor(w / fontSize));
      drops = new Array(cols)
        .fill(0)
        .map(() => Math.floor(Math.random() * (h / fontSize)));
    }
    resize();

    ctx.font = fontSize + "px 'Courier New', monospace";

    function draw() {
      if (stopped) return;
      const w = window.innerWidth;
      const h = window.innerHeight;
      ctx.fillStyle = "rgba(0, 0, 0, 0.08)";
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = "#0fdc6a";
      ctx.font = fontSize + "px 'Courier New', monospace";
      for (let i = 0; i < drops.length; i++) {
        const ch = chars.charAt(
          Math.floor(Math.random() * chars.length),
        );
        const yPos = drops[i] * fontSize;
        ctx.fillStyle = "#b6ffd0";
        ctx.fillText(ch, i * fontSize, yPos);
        ctx.fillStyle = "#0fdc6a";
        if (yPos > 0) {
          ctx.fillText(
            chars.charAt(Math.floor(Math.random() * chars.length)),
            i * fontSize,
            yPos - fontSize,
          );
        }
        if (yPos > h && Math.random() > 0.97) drops[i] = 0;
        drops[i]++;
      }
      rafId = requestAnimationFrame(draw);
    }
    draw();

    return () => {
      stopped = true;
      if (rafId) cancelAnimationFrame(rafId);
    };
  }

  function resetOverscrollNav() {
    active = false;
    armed = false;
    direction = 0;
    startY = 0;
    targetPage = null;
    wheelAccum = 0;
    if (banner) {
      banner.classList.remove("is-visible", "is-armed", "is-snapping");
      banner.style.transform = "";
    }
  }
  window.resetOverscrollNav = resetOverscrollNav;

  // Public entry point for button-triggered page navigation. The
  // bottom-of-page pager calls this; it shares the same iris +
  // motif transition as the gesture and keyboard paths so all
  // three feel like the same nav primitive.
  window.commitPageNav = function (pageId, opts) {
    if (!pageId) return;
    if (Date.now() < cooldownUntil) return;
    const list = getVisibleSidebarPages();
    const cur = getCurrentPageId();
    const i = list.indexOf(cur);
    const j = list.indexOf(pageId);
    if (j < 0) return; // page not in visible sidebar — refuse
    if (i >= 0) direction = j > i ? 1 : -1;
    commitNavigation(pageId, opts || { tempo: "fast" });
  };

  // ----- Touch -----
  document.addEventListener(
    "touchstart",
    (e) => {
      if (!overscrollNavEnabled()) return;
      if (Date.now() < cooldownUntil) return;
      if (shouldSuppressOverscroll(e.target)) return;
      if (e.touches.length !== 1) return;
      startY = e.touches[0].clientY;
      const top = docAtTop();
      const bottom = docAtBottom();
      if (!top && !bottom) {
        active = false;
        return;
      }
      active = true;
      direction = 0; // unlocked until first significant move
      armed = false;
    },
    { passive: true, capture: true },
  );

  document.addEventListener(
    "touchmove",
    (e) => {
      if (!active) return;
      const dy = e.touches[0].clientY - startY;
      if (direction === 0) {
        if (Math.abs(dy) < DIRECTION_LOCK_MIN) return;
        if (dy > 0 && docAtTop()) direction = -1;
        else if (dy < 0 && docAtBottom()) direction = 1;
        else {
          active = false;
          return;
        }
        setBannerForDirection(direction);
      }
      const matches =
        (direction === -1 && dy > 0) || (direction === 1 && dy < 0);
      if (!matches) {
        snapBannerAway();
        active = false;
        return;
      }
      const raw = direction === -1 ? dy : -dy;
      applyPullVisual(raw);
      if (e.cancelable) e.preventDefault();
    },
    { passive: false, capture: true },
  );

  function endTouch() {
    if (!active) return;
    active = false;
    if (armed && targetPage) {
      commitNavigation(targetPage);
    }
    snapBannerAway();
  }
  document.addEventListener("touchend", endTouch, { capture: true });
  document.addEventListener("touchcancel", endTouch, { capture: true });

  // ----- Keyboard: Alt+Left / Alt+Right -----
  // Always available regardless of overscrollNavEnabled — it is
  // the keyboard alternative to the gesture and the only sidebar
  // prev/next shortcut that is sequential rather than chord-based.
  // Existing global chord handler early-returns on altKey, so no
  // collision with `g d` / `g r` shortcuts.
  document.addEventListener("keydown", (e) => {
    if (!e.altKey) return;
    if (e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    if (Date.now() < cooldownUntil) return;
    if (shouldSuppressOverscroll(e.target)) return;
    const dir = e.key === "ArrowLeft" ? -1 : 1;
    const pageId = getAdjacentPage(dir);
    if (!pageId) return;
    e.preventDefault();
    direction = dir;
    commitNavigation(pageId);
  });

  // ----- Wheel / trackpad -----
  window.addEventListener(
    "wheel",
    (e) => {
      if (!overscrollNavEnabled()) return;
      if (Date.now() < cooldownUntil) return;
      if (shouldSuppressOverscroll(e.target)) return;
      const now = Date.now();
      if (now - wheelLastTs > WHEEL_RESET_MS) wheelAccum = 0;
      wheelLastTs = now;

      const dy = e.deltaY;
      if (Math.abs(dy) < 1) return;
      const top = docAtTop();
      const bottom = docAtBottom();
      // Only count overscroll past the matching edge.
      let dir = 0;
      if (dy > 0 && bottom) dir = 1;
      else if (dy < 0 && top) dir = -1;
      else {
        wheelAccum = 0;
        if (active) snapBannerAway();
        return;
      }
      // Reject huge per-event deltas (mouse wheel page-jumps are noisy).
      if (Math.abs(dy) > 200) {
        wheelAccum = 0;
        return;
      }
      // Lock direction for the gesture.
      if (direction !== dir) {
        direction = dir;
        setBannerForDirection(direction);
        wheelAccum = 0;
      }
      wheelAccum += Math.abs(dy);
      // Decide threshold by deltaMode (0 = pixels = trackpad/smooth)
      const threshold =
        e.deltaMode === 0 && Math.abs(dy) < 50
          ? WHEEL_THRESHOLD_TRACKPAD
          : WHEEL_THRESHOLD_MOUSE;
      applyPullVisual(direction === -1 ? wheelAccum : -wheelAccum);
      if (wheelAccum >= threshold && targetPage) {
        const target = targetPage;
        snapBannerAway();
        commitNavigation(target);
        wheelAccum = 0;
      }
      // Don't preventDefault on wheel — let other handlers see it.
    },
    { passive: true },
  );

  // Reset when the page changes (nav() hooks this too).
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) resetOverscrollNav();
  });

  // Make banner exists on init.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureBanner);
  } else {
    ensureBanner();
  }
})();

// ============================================================
// Settings — Navigation toggle (edge-pull on/off)
// ============================================================
function setOverscrollNavEnabled(enabled) {
  try {
    localStorage.setItem(
      "overscroll_nav_enabled",
      enabled ? "1" : "0",
    );
  } catch (_e) {}
}
function initOverscrollNavToggle() {
  const cb = document.getElementById("settings-overscroll-nav");
  if (!cb) return;
  let stored = "0";
  try {
    stored = localStorage.getItem("overscroll_nav_enabled") || "0";
  } catch (_e) {}
  cb.checked = stored === "1";
}
