// ===========================================================
// Global keyboard shortcuts — chord nav (`g d`/`g r`/etc.)
// -----------------------------------------------------------
// Registers a single keydown listener that interprets the
// `g <letter>` chord pattern, the `?` cheat-sheet trigger,
// and Esc-to-close-cheatsheet. Suppresses while typing in
// any input/textarea/select/contenteditable, and short-
// circuits on metaKey/ctrlKey/altKey so it never fights
// browser shortcuts or the Alt+←/→ page-pager nav.
//
// Depends on globals defined elsewhere in the inline script
// (window.nav, openShortcutCheatsheet, closeShortcutCheatsheet,
// openAppleGallery). All four are top-level `function` decls,
// which attach to window automatically — safe to call from
// this deferred external script at gesture time.
// ===========================================================
const GLOBAL_NAV_SHORTCUTS = {
  d: "dashboard",
  r: "receipts",
  i: "inventory",
  u: "upload",
  p: "shopping",
  b: "bills",
  x: "expenses",
  a: "analytics",
  s: "settings",
};
(function initGlobalShortcuts() {
  if (window.__globalShortcutsInit) return;
  window.__globalShortcutsInit = true;
  let lastG = 0;
  document.addEventListener("keydown", (e) => {
    const t = e.target;
    const tag = (t && t.tagName) || "";
    if (
      tag === "INPUT" ||
      tag === "TEXTAREA" ||
      tag === "SELECT" ||
      (t && t.isContentEditable) ||
      e.metaKey ||
      e.ctrlKey ||
      e.altKey
    )
      return;
    if (e.key === "Escape") {
      const openSheet = document.getElementById(
        "shortcut-cheatsheet-overlay",
      );
      if (openSheet && openSheet.classList.contains("show")) {
        closeShortcutCheatsheet();
        e.preventDefault();
        return;
      }
    }
    if (e.key === "?" || (e.key === "/" && e.shiftKey)) {
      openShortcutCheatsheet();
      e.preventDefault();
      return;
    }
    if (e.key === "g") {
      lastG = Date.now();
      return;
    }
    if (Date.now() - lastG < 800) {
      lastG = 0;
      if (e.key === "g") {
        openAppleGallery();
        e.preventDefault();
        return;
      }
      const target = GLOBAL_NAV_SHORTCUTS[e.key];
      if (target && typeof nav === "function") {
        const navEl = document.getElementById("nav-" + target);
        nav(target, navEl);
        e.preventDefault();
      }
    }
  });
})();
