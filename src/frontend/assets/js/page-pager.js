// ===========================================================
// Page pager — bottom-of-page Prev / Next buttons
// -----------------------------------------------------------
// Replaces the auto-advance gesture with an explicit button at
// the end of every sidebar-listed page. Click routes through
// window.commitPageNav (overscroll-nav.js) which shares the
// iris-veil + per-page motif transition with the gesture and
// keyboard nav paths, so all three feel like one primitive.
//
// Order = sidebar visibility order (one source of truth).
// Edges (first/last) render the button disabled with a muted
// label rather than hidden so the layout stays symmetric.
// ===========================================================
(function () {
  const PAGER_CLASS = "page-pager";

  function getVisibleSidebarPages() {
    const items = document.querySelectorAll(
      '.sidebar .nav-item[onclick^="nav("]',
    );
    const out = [];
    items.forEach((el) => {
      if (el.offsetParent === null) return; // hidden by CSS / display:none
      const m = String(el.getAttribute("onclick") || "").match(
        /nav\(\s*['"]([^'"]+)['"]/,
      );
      if (m) out.push(m[1]);
    });
    return out;
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

  function getPageNavLabel(pageId) {
    const el = getNavItemEl(pageId);
    if (!el) return pageId;
    const clone = el.cloneNode(true);
    clone.querySelectorAll(".nav-icon").forEach((n) => n.remove());
    return clone.textContent.replace(/\s+/g, " ").trim();
  }

  function getNavIcon(pageId) {
    const el = getNavItemEl(pageId);
    if (!el) return "";
    const ic = el.querySelector(".nav-icon");
    return ic ? ic.textContent.trim() : "";
  }

  function buildButton(dir, targetPageId, label, icon, disabled) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "page-pager__btn " +
      (dir === -1 ? "page-pager__prev" : "page-pager__next");
    btn.dataset.dir = String(dir);
    btn.dataset.targetPage = targetPageId || "";
    btn.disabled = !!disabled;
    btn.setAttribute(
      "aria-label",
      (dir === -1 ? "Previous page" : "Next page") +
        (label ? ": " + label : ""),
    );

    const arrow = document.createElement("span");
    arrow.className =
      "page-pager__arrow" + (disabled ? " page-pager__arrow--mute" : "");
    arrow.textContent = dir === -1 ? "←" : "→";

    const stack = document.createElement("span");
    stack.className =
      "page-pager__stack" + (dir === 1 ? " page-pager__stack--right" : "");

    const hintEl = document.createElement("span");
    hintEl.className = "page-pager__hint";
    hintEl.textContent = disabled
      ? dir === -1
        ? "Start"
        : "End"
      : dir === -1
      ? "Previous"
      : "Next";

    const nameEl = document.createElement("span");
    nameEl.className =
      "page-pager__name" + (disabled ? " page-pager__name--mute" : "");
    if (disabled) {
      nameEl.textContent =
        dir === -1 ? "No earlier page" : "No further page";
    } else {
      // Icon leads on prev (←  📊 Dashboard); trails on next (Inventory 📦  →)
      nameEl.textContent =
        dir === -1
          ? (icon ? icon + " " : "") + label
          : label + (icon ? " " + icon : "");
    }

    stack.appendChild(hintEl);
    stack.appendChild(nameEl);

    if (dir === -1) {
      btn.appendChild(arrow);
      btn.appendChild(stack);
    } else {
      btn.appendChild(stack);
      btn.appendChild(arrow);
    }
    return btn;
  }

  function ensurePager(pageEl) {
    let pager = pageEl.querySelector(":scope > ." + PAGER_CLASS);
    if (pager) return pager;
    pager = document.createElement("nav");
    pager.className = PAGER_CLASS;
    pager.setAttribute("aria-label", "Page navigation");
    pageEl.appendChild(pager);
    pager.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-dir]");
      if (!btn || btn.disabled) return;
      const target = btn.dataset.targetPage;
      if (!target) return;
      if (typeof window.commitPageNav === "function") {
        window.commitPageNav(target);
      } else if (typeof window.nav === "function") {
        // Fallback if overscroll-nav.js failed to load.
        window.nav(target);
      }
    });
    return pager;
  }

  function renderPagerFor(pageEl, pageId, list) {
    const pager = ensurePager(pageEl);
    const idx = list.indexOf(pageId);
    if (idx < 0) {
      pager.style.display = "none";
      return;
    }
    pager.style.display = "";

    const prev = list[idx - 1] || null;
    const next = list[idx + 1] || null;

    // Rebuild buttons each render — labels can shift when sidebar
    // visibility changes (auth, role-gated nav items).
    while (pager.firstChild) pager.removeChild(pager.firstChild);

    pager.appendChild(
      buildButton(
        -1,
        prev,
        prev ? getPageNavLabel(prev) : "",
        prev ? getNavIcon(prev) : "",
        !prev,
      ),
    );

    const divider = document.createElement("div");
    divider.className = "page-pager__divider";
    divider.setAttribute("aria-hidden", "true");
    pager.appendChild(divider);

    pager.appendChild(
      buildButton(
        1,
        next,
        next ? getPageNavLabel(next) : "",
        next ? getNavIcon(next) : "",
        !next,
      ),
    );
  }

  function renderAll() {
    const list = getVisibleSidebarPages();
    document.querySelectorAll(".page").forEach((pageEl) => {
      const pageId = (pageEl.id || "").replace(/^page-/, "");
      if (!pageId) return;
      if (!list.includes(pageId)) {
        const pager = pageEl.querySelector(":scope > ." + PAGER_CLASS);
        if (pager) pager.remove();
        return;
      }
      renderPagerFor(pageEl, pageId, list);
    });
  }
  window.renderPagePagers = renderAll; // exposed for ad-hoc refreshes

  // Initial render once DOM is ready.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderAll);
  } else {
    renderAll();
  }

  // Sidebar visibility shifts on login / logout / role change.
  window.addEventListener("auth:user-changed", renderAll);

  // Re-render whenever a page activates — cheapest signal that
  // covers role-gated sidebar items mutating between renders.
  const obs = new MutationObserver((muts) => {
    for (const m of muts) {
      if (
        m.attributeName === "class" &&
        m.target.classList &&
        m.target.classList.contains("page")
      ) {
        renderAll();
        return;
      }
    }
  });
  function attachObservers() {
    document.querySelectorAll(".page").forEach((p) => {
      obs.observe(p, { attributes: true, attributeFilter: ["class"] });
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attachObservers);
  } else {
    attachObservers();
  }
})();
