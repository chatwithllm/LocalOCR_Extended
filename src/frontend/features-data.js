window.FEATURES_DATA = [
  // ── Receipts ──────────────────────────────────────────────────────────────
  {
    id: "ocr-upload",
    group: "Receipts",
    icon: "📸",
    title: "OCR Upload",
    tagline: "Upload a receipt photo — AI extracts items and saves them to inventory.",
    platforms: ["Web", "Mobile"],
    where: "Nav -> Upload (camera icon)",
    flow: [
      { icon: "📷", label: "Upload Photo", sub: "JPEG, PNG, HEIC, PDF" },
      { icon: "🤖", label: "AI OCR", sub: "Extract items & totals" },
      { icon: "✏️", label: "Review", sub: "Edit any field" },
      { icon: "✅", label: "Confirm", sub: "Saved to inventory" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<div style="color:#aaa;margin-bottom:6px;font-size:0.72rem">📄 Whole Foods Market</div>'
      + '<div style="font-size:1rem;font-weight:600;margin-bottom:10px">$47.23 · May 17 2026</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;margin-bottom:6px">'
      + '<div style="display:flex;justify-content:space-between"><span>Organic Milk</span><span style="color:#4ade80">$5.49</span></div>'
      + '</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;margin-bottom:6px">'
      + '<div style="display:flex;justify-content:space-between"><span>Sourdough Bread</span><span style="color:#4ade80">$4.99</span></div>'
      + '</div>'
      + '<div style="color:#555;font-size:0.72rem;margin-bottom:10px">+ 8 more items</div>'
      + '<div style="display:flex;gap:6px">'
      + '<button style="background:#3b82f6;color:#fff;border:none;border-radius:5px;padding:5px 10px;font-size:0.72rem;cursor:pointer">Confirm</button>'
      + '<button style="background:#333;color:#aaa;border:none;border-radius:5px;padding:5px 10px;font-size:0.72rem;cursor:pointer">Edit</button>'
      + '<button style="background:#333;color:#aaa;border:none;border-radius:5px;padding:5px 10px;font-size:0.72rem;cursor:pointer">Re-run OCR</button>'
      + '</div>'
      + '</div>',
    interactions: [
      "🔖 Choose type: auto / grocery / restaurant / expense",
      "🤖 Switch AI model before or after OCR",
      "✏️ Edit any extracted field inline",
      "🔄 Re-run OCR anytime with a different model",
    ],
    tip: "Landscape photos are auto-rotated. If items are missing, try Re-run OCR with a different model.",
  },

  {
    id: "review-edit",
    group: "Receipts",
    icon: "✏️",
    title: "Review and Edit",
    tagline: "Edit any extracted field before confirming — fix store name, date, totals, or line items.",
    platforms: ["Web", "Mobile"],
    where: "Nav -> Upload -> after OCR completes",
    flow: [
      { icon: "🤖", label: "OCR Result", sub: "Draft fields ready" },
      { icon: "✏️", label: "Edit Fields", sub: "Tap any value to change" },
      { icon: "✅", label: "Confirm", sub: "Saved to inventory" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<div style="color:#aaa;margin-bottom:8px;font-size:0.72rem;text-transform:uppercase;letter-spacing:0.04em">Edit Receipt</div>'
      + '<div style="margin-bottom:7px">'
      + '<div style="color:#888;font-size:0.7rem;margin-bottom:2px">Store</div>'
      + '<input style="background:#222;border:1px solid #444;border-radius:5px;padding:5px 8px;color:#fff;font-size:0.75rem;width:100%;box-sizing:border-box" value="Whole Foods Market" readonly />'
      + '</div>'
      + '<div style="margin-bottom:7px">'
      + '<div style="color:#888;font-size:0.7rem;margin-bottom:2px">Date</div>'
      + '<input style="background:#222;border:1px solid #444;border-radius:5px;padding:5px 8px;color:#fff;font-size:0.75rem;width:100%;box-sizing:border-box" value="2026-05-17" readonly />'
      + '</div>'
      + '<div style="margin-bottom:10px">'
      + '<div style="color:#888;font-size:0.7rem;margin-bottom:2px">Total</div>'
      + '<input style="background:#222;border:1px solid #444;border-radius:5px;padding:5px 8px;color:#fff;font-size:0.75rem;width:100%;box-sizing:border-box" value="$47.23" readonly />'
      + '</div>'
      + '<div style="display:flex;gap:6px">'
      + '<button style="background:#3b82f6;color:#fff;border:none;border-radius:5px;padding:5px 10px;font-size:0.72rem;cursor:pointer">Save</button>'
      + '<button style="background:#333;color:#aaa;border:none;border-radius:5px;padding:5px 10px;font-size:0.72rem;cursor:pointer">Cancel</button>'
      + '</div>'
      + '</div>',
    interactions: [
      "✏️ Tap any field to edit store, date, or total",
      "🔄 Rotate photo if OCR read sideways text",
      "➕ Add missing items manually",
      "🗑️ Delete incorrect line items",
    ],
    tip: "Items flagged yellow have low OCR confidence — check them first before confirming.",
  },

  {
    id: "rerun-ocr",
    group: "Receipts",
    icon: "🔄",
    title: "Re-run OCR",
    tagline: "Re-process a saved receipt with a different AI model to catch missed items.",
    platforms: ["Web"],
    where: "Nav -> Receipts -> tap receipt -> Re-run OCR button",
    flow: [
      { icon: "🧾", label: "Saved Receipt", sub: "Open any past receipt" },
      { icon: "🤖", label: "Pick Model", sub: "GPT-4o, Gemini, etc." },
      { icon: "⚡", label: "Re-extract", sub: "AI re-reads the image" },
      { icon: "🔀", label: "Merge Result", sub: "Diff view: accept or discard" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<div style="font-weight:600;margin-bottom:6px">Whole Foods Market · $47.23</div>'
      + '<div style="background:#e0a13420;border:1px solid #e0a13440;border-radius:5px;padding:8px;margin-bottom:10px;color:#e0a134;font-size:0.72rem">'
      + '⚠️ 3 items may have been missed in original scan'
      + '</div>'
      + '<div style="color:#888;font-size:0.7rem;margin-bottom:4px">AI Model</div>'
      + '<select style="background:#222;border:1px solid #444;border-radius:5px;padding:5px 8px;color:#fff;font-size:0.75rem;width:100%;margin-bottom:10px">'
      + '<option>GPT-4o (best for dense text)</option>'
      + '<option>Gemini 1.5 Pro</option>'
      + '<option>Claude Sonnet</option>'
      + '</select>'
      + '<button style="background:#3b82f6;color:#fff;border:none;border-radius:5px;padding:6px 14px;font-size:0.72rem;cursor:pointer;width:100%">🔄 Re-run OCR</button>'
      + '</div>',
    interactions: [
      "🤖 Select a different AI model from dropdown",
      "🔀 Diff view shows new vs existing items",
      "✅ Accept new items individually or all at once",
      "🗑️ Discard re-run if result is worse",
    ],
    tip: "Re-run shows a diff — existing items are never deleted automatically. GPT-4o for dense text, Gemini for blurry or rotated receipts.",
  },

  {
    id: "receipt-types",
    group: "Receipts",
    icon: "🏷️",
    title: "Receipt Types",
    tagline: "Auto-detect grocery / restaurant / expense, or pick manually — routes to the right workspace.",
    platforms: ["Web", "Mobile"],
    where: "Nav -> Upload -> Type selector at top",
    flow: [
      { icon: "📷", label: "Upload", sub: "Photo or PDF" },
      { icon: "🔍", label: "Auto-detect", sub: "AI reads layout" },
      { icon: "🤖", label: "Type-aware OCR", sub: "Optimized extraction" },
      { icon: "📂", label: "Saved", sub: "Goes to right bucket" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<div style="color:#aaa;font-size:0.7rem;margin-bottom:8px">Receipt Type</div>'
      + '<div style="display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap">'
      + '<button style="background:#3b82f6;color:#fff;border:none;border-radius:5px;padding:5px 10px;font-size:0.72rem">Auto</button>'
      + '<button style="background:#333;color:#aaa;border:none;border-radius:5px;padding:5px 10px;font-size:0.72rem">Grocery</button>'
      + '<button style="background:#333;color:#aaa;border:none;border-radius:5px;padding:5px 10px;font-size:0.72rem">Restaurant</button>'
      + '<button style="background:#333;color:#aaa;border:none;border-radius:5px;padding:5px 10px;font-size:0.72rem">Expense</button>'
      + '</div>'
      + '<div style="background:#4ade8015;border:1px solid #4ade8030;border-radius:5px;padding:8px;color:#4ade80;font-size:0.72rem">'
      + '✓ Auto-detected: Grocery (94% confidence)'
      + '</div>'
      + '</div>',
    interactions: [
      "🔍 Auto-detect from receipt layout and merchant name",
      "🛒 Grocery adds line items to inventory",
      "🍽️ Restaurant routes to dining workspace",
      "💳 Expense feeds spend tracking",
    ],
    tip: "Pharmacy receipts sometimes mis-detect as grocery. Switch manually using the type buttons if needed.",
  },

  // ── Grocery ───────────────────────────────────────────────────────────────
  {
    id: "inventory",
    group: "Grocery",
    icon: "📦",
    title: "Inventory",
    tagline: "Product catalog with stock levels, categories, and price history — auto-updated from receipts.",
    platforms: ["Web", "Mobile"],
    where: "Nav -> Inventory",
    flow: [
      { icon: "🧾", label: "Receipt OCR", sub: "Items auto-added" },
      { icon: "📦", label: "Inventory", sub: "Current stock levels" },
      { icon: "✏️", label: "Edit Stock", sub: "Manual adjustments" },
      { icon: "📈", label: "History", sub: "Price trends over time" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<input style="background:#222;border:1px solid #444;border-radius:5px;padding:5px 8px;color:#aaa;font-size:0.75rem;width:100%;box-sizing:border-box;margin-bottom:10px" placeholder="🔍 Search inventory..." readonly />'
      + '<div style="background:#222;border-radius:5px;padding:8px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">'
      + '<div><div>Organic Milk</div><div style="color:#888;font-size:0.7rem">Dairy · $5.49 avg</div></div>'
      + '<span style="background:#4ade8020;color:#4ade80;border-radius:4px;padding:2px 8px;font-size:0.7rem">2 in stock</span>'
      + '</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;display:flex;justify-content:space-between;align-items:center">'
      + '<div><div>Sourdough Bread</div><div style="color:#888;font-size:0.7rem">Bakery · $4.99 avg</div></div>'
      + '<span style="background:#e0a13420;color:#e0a134;border-radius:4px;padding:2px 8px;font-size:0.7rem">1 low</span>'
      + '</div>'
      + '</div>',
    interactions: [
      "🔍 Search and filter by category or product name",
      "✏️ Edit quantity manually (logged in history)",
      "📈 View price history and trend chart",
      "🗑️ Remove products no longer bought",
    ],
    tip: "Stock auto-decrements during a Shopping Walk. Manual adjustments are logged so price history stays accurate.",
  },

  {
    id: "shopping-list",
    group: "Grocery",
    icon: "🛒",
    title: "Shopping List",
    tagline: "Smart list: add manually, auto-populate from low stock, share via QR, or start a Telegram Walk.",
    platforms: ["Web", "Mobile", "Telegram"],
    where: "Nav -> Shopping",
    flow: [
      { icon: "⚠️", label: "Low-stock alert", sub: "Auto-suggested items" },
      { icon: "📋", label: "Build List", sub: "Add / remove items" },
      { icon: "📱", label: "Share QR", sub: "Helper opens on any device" },
      { icon: "✅", label: "Walk Done", sub: "Stock updated" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'
      + '<span style="font-weight:600">Shopping List</span>'
      + '<button style="background:#3b82f6;color:#fff;border:none;border-radius:5px;padding:4px 10px;font-size:0.72rem;cursor:pointer">+ Add</button>'
      + '</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;margin-bottom:6px;display:flex;align-items:center;gap:8px">'
      + '<span style="color:#4ade80">✓</span>'
      + '<span style="text-decoration:line-through;color:#555">Organic Milk</span>'
      + '</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;margin-bottom:6px;display:flex;align-items:center;gap:8px">'
      + '<span style="color:#666">○</span>'
      + '<span>Sourdough Bread</span>'
      + '</div>'
      + '<div style="background:#222;border:1px solid #4ade8040;border-radius:5px;padding:8px;display:flex;justify-content:space-between;align-items:center">'
      + '<span>Greek Yogurt</span>'
      + '<span style="background:#4ade8020;color:#4ade80;border-radius:4px;padding:2px 6px;font-size:0.7rem">💡 Low stock</span>'
      + '</div>'
      + '</div>',
    interactions: [
      "➕ Add items manually or from inventory search",
      "💡 Auto-populate from low-stock items with one tap",
      "📱 Share QR — opens list read-only on any device",
      "🤖 Start Telegram Shopping Walk from list",
    ],
    tip: "QR share opens the list read-only on any device — great for a family member without the app.",
  },

  {
    id: "recommendations",
    group: "Grocery",
    icon: "💡",
    title: "Recommendations",
    tagline: "Low-stock alerts and buy-again suggestions ranked by AI confidence score.",
    platforms: ["Web"],
    where: "Nav -> Shopping -> Recommendations tab",
    flow: [
      { icon: "📦", label: "Inventory", sub: "Current stock levels" },
      { icon: "🤖", label: "AI Scoring", sub: "Frequency + recency" },
      { icon: "💡", label: "Suggestions", sub: "Ranked by confidence" },
      { icon: "➕", label: "Add to List", sub: "One tap" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<div style="color:#aaa;font-size:0.7rem;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.04em">Recommendations</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">'
      + '<div>'
      + '<div style="font-weight:500">Greek Yogurt</div>'
      + '<div style="color:#e0a134;font-size:0.7rem">⚠️ Stock: 0 · avg every 10 days</div>'
      + '</div>'
      + '<button style="background:#3b82f6;color:#fff;border:none;border-radius:5px;padding:4px 8px;font-size:0.7rem;cursor:pointer">+ Add</button>'
      + '</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;display:flex;justify-content:space-between;align-items:center">'
      + '<div>'
      + '<div style="font-weight:500">Eggs</div>'
      + '<div style="color:#888;font-size:0.7rem">Stock: 6 · confidence 72%</div>'
      + '</div>'
      + '<button style="background:#333;color:#aaa;border:none;border-radius:5px;padding:4px 8px;font-size:0.7rem;cursor:pointer">+ Add</button>'
      + '</div>'
      + '</div>',
    interactions: [
      "⚠️ AI-ranked list sorted by urgency and confidence",
      "📊 Confidence score shown per recommendation",
      "➕ Add directly to shopping list with one tap",
      "🚫 Dismiss items you don't want suggested again",
    ],
    tip: "Items marked ⚠️ are genuinely out of stock. Higher confidence means bought recently and frequently.",
  },

  {
    id: "kitchen-view",
    group: "Grocery",
    icon: "🍳",
    title: "Kitchen View",
    tagline: "Ingredient-level compact view of what's in stock, grouped by type — perfect for meal planning.",
    platforms: ["Web"],
    where: "Nav -> Shopping -> Kitchen tab",
    flow: [
      { icon: "📦", label: "Inventory", sub: "All products" },
      { icon: "🍳", label: "Kitchen View", sub: "Ingredient-first layout" },
      { icon: "📂", label: "Browse by Type", sub: "Dairy, Produce, Bakery…" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<div style="color:#aaa;font-size:0.7rem;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.04em">Kitchen</div>'
      + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">'
      + '<div style="background:#222;border-radius:6px;padding:8px">'
      + '<div style="color:#60a5fa;font-size:0.7rem;margin-bottom:4px;font-weight:600">Dairy</div>'
      + '<div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>Milk</span><span style="color:#4ade80">✓ 2</span></div>'
      + '<div style="display:flex;justify-content:space-between"><span>Yogurt</span><span style="color:#e0a134">⚠ 0</span></div>'
      + '</div>'
      + '<div style="background:#222;border-radius:6px;padding:8px">'
      + '<div style="color:#60a5fa;font-size:0.7rem;margin-bottom:4px;font-weight:600">Bakery</div>'
      + '<div style="display:flex;justify-content:space-between;margin-bottom:3px"><span>Bread</span><span style="color:#e0a134">⚠ 1</span></div>'
      + '<div style="display:flex;justify-content:space-between"><span>Bagels</span><span style="color:#4ade80">✓ 6</span></div>'
      + '</div>'
      + '</div>'
      + '</div>',
    interactions: [
      "🗂️ Browse by ingredient category (Dairy, Produce, Bakery…)",
      "⚠️ Spot low-stock or out-of-stock at a glance",
      "➕ Tap any ingredient to add to shopping list",
    ],
    tip: "Groups by ingredient type, not brand — useful for meal planning when you care about 'milk' not 'Organic Valley'.",
  },

  // ── Restaurant ────────────────────────────────────────────────────────────
  {
    id: "restaurant-workspace",
    group: "Restaurant",
    icon: "🍽️",
    title: "Restaurant Workspace",
    tagline: "Dedicated workspace for restaurant receipts with dining spend analytics and budget tracking.",
    platforms: ["Web"],
    where: "Nav -> Dining",
    flow: [
      { icon: "📷", label: "Upload Receipt", sub: "Restaurant type" },
      { icon: "🍽️", label: "Workspace", sub: "Visit line items" },
      { icon: "📊", label: "Analytics", sub: "Dining spend summary" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">'
      + '<span style="font-weight:600">Dining</span>'
      + '<span style="color:#e0a134;font-size:0.72rem">$340 / $500 budget</span>'
      + '</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center">'
      + '<div>'
      + '<div style="font-weight:500">Nobu</div>'
      + '<div style="color:#888;font-size:0.7rem">May 17 · 4 people</div>'
      + '</div>'
      + '<span style="color:#fff;font-weight:600">$120.00</span>'
      + '</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;display:flex;justify-content:space-between;align-items:center">'
      + '<div>'
      + '<div style="font-weight:500">Chipotle</div>'
      + '<div style="color:#888;font-size:0.7rem">May 15 · 2 people</div>'
      + '</div>'
      + '<span style="color:#fff;font-weight:600">$38.50</span>'
      + '</div>'
      + '</div>',
    interactions: [
      "📷 Upload restaurant receipts (auto-routed from type selector)",
      "🧾 View line items for each dining visit",
      "📊 See dining spend vs budget for the month",
      "👥 See party size and who you dined with",
    ],
    tip: "Restaurant receipts don't add to grocery inventory — they feed dining analytics and the budget card only.",
  },

  {
    id: "repeat-orders",
    group: "Restaurant",
    icon: "🔁",
    title: "Repeat Orders",
    tagline: "Most-ordered dishes ranked by frequency, with average price and last-ordered date.",
    platforms: ["Web"],
    where: "Nav -> Dining -> Repeat Orders tab",
    flow: [
      { icon: "🧾", label: "Past Receipts", sub: "Full dining history" },
      { icon: "🔀", label: "Group by Name", sub: "Fuzzy item matching" },
      { icon: "🏆", label: "Rank", sub: "By order frequency" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<div style="color:#aaa;font-size:0.7rem;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.04em">Repeat Orders</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;margin-bottom:6px;display:flex;align-items:center;gap:8px">'
      + '<span style="background:#4ade8020;color:#4ade80;border-radius:4px;padding:2px 6px;font-size:0.7rem;min-width:20px;text-align:center">#1</span>'
      + '<div style="flex:1">'
      + '<div style="font-weight:500">Pad Thai</div>'
      + '<div style="color:#888;font-size:0.7rem">Ordered 8x · avg $14.50</div>'
      + '</div>'
      + '</div>'
      + '<div style="background:#222;border-radius:5px;padding:8px;display:flex;align-items:center;gap:8px">'
      + '<span style="background:#3b82f620;color:#60a5fa;border-radius:4px;padding:2px 6px;font-size:0.7rem;min-width:20px;text-align:center">#2</span>'
      + '<div style="flex:1">'
      + '<div style="font-weight:500">Margherita Pizza</div>'
      + '<div style="color:#888;font-size:0.7rem">Ordered 5x · avg $18.00</div>'
      + '</div>'
      + '</div>'
      + '</div>',
    interactions: [
      "🏆 View top dishes ranked by how often you order them",
      "💰 See average price per dish across all visits",
      "📅 See the last date you ordered each dish",
    ],
    tip: "Item matching is fuzzy — 'Pad Thai' and 'Pad thai noodles' are counted together automatically.",
  },

  {
    id: "dining-budget",
    group: "Restaurant",
    icon: "💰",
    title: "Dining Budget",
    tagline: "Monthly dining budget card showing actual spend vs budget with a live progress bar.",
    platforms: ["Web"],
    where: "Nav -> Dining -> Budget card at top",
    flow: [
      { icon: "⚙️", label: "Set Budget", sub: "Monthly $ in Settings" },
      { icon: "🍽️", label: "Dining Spend", sub: "Auto-tracked from receipts" },
      { icon: "📊", label: "Budget Bar", sub: "Actual vs budget" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:8px;padding:14px;font-size:0.75rem;color:#fff;min-width:220px">'
      + '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
      + '<span style="font-weight:600">Dining Budget — May</span>'
      + '</div>'
      + '<div style="font-size:1.1rem;font-weight:700;margin-bottom:8px">$340 <span style="color:#888;font-size:0.8rem;font-weight:400">/ $500</span></div>'
      + '<div style="background:#333;border-radius:4px;height:8px;margin-bottom:6px;overflow:hidden">'
      + '<div style="background:#4ade80;width:68%;height:100%;border-radius:4px"></div>'
      + '</div>'
      + '<div style="color:#888;font-size:0.7rem">68% used · $160 remaining</div>'
      + '</div>',
    interactions: [
      "⚙️ Set monthly budget amount in Settings",
      "🟢 Bar turns amber at 80%, red at 95% of budget",
      "🔄 Budget resets automatically on the 1st of each month",
    ],
    tip: "Only Restaurant-type receipts count toward the dining budget. Expense receipts (coffee, snacks) are excluded.",
  },

  // ── Expenses ──────────────────────────────────────────────────────────────
  {
    id: "expense-tracking",
    group: "Expenses",
    icon: "💸",
    title: "Expense Tracking",
    tagline: "Log general expense receipts — merchants, amounts, categories",
    platforms: ["Web"],
    where: "Nav -> Upload -> pick Expense type",
    flow: [
      { icon: "📷", label: "Upload",     sub: "expense receipt" },
      { icon: "💸", label: "Categorize", sub: "auto or manual" },
      { icon: "📊", label: "Analytics",  sub: "spend trends" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:6px;padding:6px 10px;font-size:0.75rem">'
      + '<div style="color:#aaa;margin-bottom:4px">Recent Expenses</div>'
      + '<div style="display:flex;justify-content:space-between;color:#fff;padding:3px 0">Amazon<span style="color:#4ade80">$89.99</span></div>'
      + '<div style="display:flex;justify-content:space-between;color:#fff;padding:3px 0">Starbucks<span style="color:#4ade80">$6.75</span></div>'
      + '<div style="display:flex;justify-content:space-between;color:#fff;padding:3px 0">CVS Pharmacy<span style="color:#4ade80">$23.40</span></div>'
      + '</div>',
    interactions: [
      "Upload any non-grocery non-restaurant receipt",
      "Tag by category (Shopping/Health/Transport)",
      "See merchant frequency in analytics",
      "Log cash expenses manually",
    ],
    tip: "Expense receipts feed analytics but don't affect grocery inventory.",
  },

  {
    id: "category-tagging",
    group: "Expenses",
    icon: "🏷",
    title: "Category Tagging",
    tagline: "Tag expenses by category — view breakdown, drill into any category",
    platforms: ["Web"],
    where: "Nav -> Analytics -> Spending by Category",
    flow: [
      { icon: "💸", label: "Expense recorded", sub: "receipt or cash" },
      { icon: "🏷",  label: "Tag category",    sub: "auto or manual" },
      { icon: "📊", label: "Breakdown",        sub: "pie by category" },
      { icon: "🔍", label: "Drill",            sub: "see receipts" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:6px;padding:6px 10px;font-size:0.75rem">'
      + '<div style="color:#aaa;margin-bottom:4px">Category Breakdown</div>'
      + '<div style="display:flex;align-items:center;gap:6px;padding:3px 0">'
      + '<span style="width:8px;height:8px;border-radius:50%;background:#3b82f6;display:inline-block"></span>'
      + '<span style="color:#fff;flex:1">Grocery</span><span style="color:#fff">$342</span>'
      + '<span style="background:#3b82f6;color:#fff;border-radius:4px;padding:0 4px;font-size:0.65rem">41%</span></div>'
      + '<div style="display:flex;align-items:center;gap:6px;padding:3px 0">'
      + '<span style="width:8px;height:8px;border-radius:50%;background:#e0a134;display:inline-block"></span>'
      + '<span style="color:#fff;flex:1">Dining</span><span style="color:#fff">$210</span>'
      + '<span style="background:#e0a134;color:#fff;border-radius:4px;padding:0 4px;font-size:0.65rem">25%</span></div>'
      + '<div style="display:flex;align-items:center;gap:6px;padding:3px 0">'
      + '<span style="width:8px;height:8px;border-radius:50%;background:#a855f7;display:inline-block"></span>'
      + '<span style="color:#fff;flex:1">Health</span><span style="color:#fff">$89</span>'
      + '<span style="background:#a855f7;color:#fff;border-radius:4px;padding:0 4px;font-size:0.65rem">11%</span></div>'
      + '</div>',
    interactions: [
      "Auto-tag from merchant name (editable)",
      "Category breakdown with % of total",
      "Tap category to drill into receipts",
      "Filter by month",
    ],
    tip: "You can retag any receipt from its detail page. Categories are inferred from merchant names initially.",
  },

  {
    id: "expense-analytics",
    group: "Expenses",
    icon: "📉",
    title: "Expense Analytics",
    tagline: "Spend trends by week/month, merchant frequency chart, category breakdown",
    platforms: ["Web"],
    where: "Nav -> Analytics",
    flow: [
      { icon: "📊", label: "All spend",  sub: "receipts + cash" },
      { icon: "📈", label: "Trends",     sub: "week / month" },
      { icon: "🏪", label: "Merchants",  sub: "frequency chart" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:6px;padding:6px 10px;font-size:0.75rem">'
      + '<div style="color:#aaa;margin-bottom:6px">Monthly Spend</div>'
      + '<div style="display:flex;align-items:flex-end;gap:6px;height:50px">'
      + '<div style="display:flex;flex-direction:column;align-items:center;flex:1">'
      + '<div style="background:#3b82f6;width:100%;height:60%;border-radius:2px 2px 0 0"></div>'
      + '<span style="color:#888;font-size:0.65rem;margin-top:2px">Jan</span></div>'
      + '<div style="display:flex;flex-direction:column;align-items:center;flex:1">'
      + '<div style="background:#3b82f6;width:100%;height:80%;border-radius:2px 2px 0 0"></div>'
      + '<span style="color:#888;font-size:0.65rem;margin-top:2px">Feb</span></div>'
      + '<div style="display:flex;flex-direction:column;align-items:center;flex:1">'
      + '<div style="background:#3b82f6;width:100%;height:45%;border-radius:2px 2px 0 0"></div>'
      + '<span style="color:#888;font-size:0.65rem;margin-top:2px">Mar</span></div>'
      + '<div style="display:flex;flex-direction:column;align-items:center;flex:1">'
      + '<div style="background:#3b82f6;width:100%;height:90%;border-radius:2px 2px 0 0"></div>'
      + '<span style="color:#888;font-size:0.65rem;margin-top:2px">Apr</span></div>'
      + '<div style="display:flex;flex-direction:column;align-items:center;flex:1">'
      + '<div style="background:#3b82f6;width:100%;height:55%;border-radius:2px 2px 0 0"></div>'
      + '<span style="color:#888;font-size:0.65rem;margin-top:2px">May</span></div>'
      + '</div></div>',
    interactions: [
      "Switch between weekly and monthly view",
      "Bar chart for spend over time",
      "Merchant frequency — who you spend most at",
      "Category pie for current month",
    ],
    tip: "Analytics excludes fixed bill payments (floor obligations) to avoid double-counting.",
  },

  // ── Finance ───────────────────────────────────────────────────────────────
  {
    id: "spending-by-category",
    group: "Finance",
    icon: "📊",
    title: "Spending by Category",
    tagline: "Dashboard tile — every spend category in one place, expandable drill panel",
    platforms: ["Web"],
    where: "Nav -> Dashboard -> Spending tile",
    flow: [
      { icon: "📊", label: "Dashboard tile", sub: "all categories" },
      { icon: "🔍", label: "Expand",         sub: "tap category" },
      { icon: "📋", label: "Drill receipts", sub: "see line items" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:6px;padding:6px 10px;font-size:0.75rem">'
      + '<div style="color:#aaa;margin-bottom:4px">Spending</div>'
      + '<div style="padding:3px 0">'
      + '<div style="display:flex;justify-content:space-between;color:#fff;margin-bottom:2px">'
      + '<span>Grocery</span><span>$342</span></div>'
      + '<div style="background:#333;border-radius:4px;height:6px">'
      + '<div style="background:#3b82f6;width:68%;height:6px;border-radius:4px"></div></div></div>'
      + '<div style="padding:3px 0;margin-top:4px">'
      + '<div style="display:flex;justify-content:space-between;color:#fff;margin-bottom:2px">'
      + '<span>Fixed</span><span>$850</span></div>'
      + '<div style="background:#333;border-radius:4px;height:6px">'
      + '<div style="background:#a855f7;width:85%;height:6px;border-radius:4px"></div></div></div>'
      + '</div>',
    interactions: [
      "All categories ranked by spend",
      "Fixed row shows total paid vs expected obligations",
      "Tap any row to drill into receipts",
      "Filter by month",
    ],
    tip: "Fixed obligations appear as a separate 'Fixed' row and are excluded from other categories to prevent double-counting.",
  },

  {
    id: "fixed-bills",
    group: "Finance",
    icon: "📌",
    title: "Fixed Bills",
    tagline: "Track floor obligations (rent, subscriptions) — paid vs expected, inline rename",
    platforms: ["Web"],
    where: "Nav -> Bills",
    flow: [
      { icon: "➕", label: "Add bill",   sub: "provider + amount" },
      { icon: "🏦", label: "Plaid match", sub: "auto-link transaction" },
      { icon: "📌", label: "Track",       sub: "paid vs expected" },
      { icon: "📊", label: "Dashboard",   sub: "Fixed row" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:6px;padding:6px 10px;font-size:0.75rem">'
      + '<div style="display:flex;gap:6px;margin-bottom:6px">'
      + '<span style="background:#3b82f6;color:#fff;border-radius:4px;padding:1px 8px;font-size:0.7rem">Selected</span>'
      + '<span style="color:#888;border-radius:4px;padding:1px 8px;font-size:0.7rem">Available</span>'
      + '</div>'
      + '<div style="display:grid;grid-template-columns:1fr auto auto;gap:4px;align-items:center;color:#fff">'
      + '<input style="background:#2a2a2e;border:none;border-radius:3px;color:#fff;padding:2px 4px;font-size:0.7rem" value="Rent" />'
      + '<span style="color:#4ade80">$1200 ✓</span><span style="color:#888">/ $1200</span>'
      + '<input style="background:#2a2a2e;border:none;border-radius:3px;color:#fff;padding:2px 4px;font-size:0.7rem" value="Netflix" />'
      + '<span style="color:#e0a134">$0</span><span style="color:#888">/ $18</span>'
      + '</div></div>',
    interactions: [
      "Add floor obligation (name + expected amount)",
      "Click Name column to rename inline (saves on blur/Enter)",
      "Link to Plaid transaction for auto-matching",
      "Appears as Fixed row in Spending dashboard",
    ],
    tip: "Name column is an editable text input — click it and type a friendlier label (e.g. 'Streaming' instead of the merchant code).",
  },

  {
    id: "plaid-integration",
    group: "Finance",
    icon: "🏦",
    title: "Plaid Integration",
    tagline: "Sync bank transactions and auto-match to receipts you've already scanned",
    platforms: ["Web"],
    where: "Nav -> Accounts",
    flow: [
      { icon: "🏦", label: "Link bank",    sub: "via Plaid OAuth" },
      { icon: "🔄", label: "Sync txns",    sub: "daily automatic" },
      { icon: "🔍", label: "Auto-match",   sub: "amount + date" },
      { icon: "✅", label: "Reconciled",   sub: "matched to receipt" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:6px;padding:6px 10px;font-size:0.75rem">'
      + '<div style="color:#aaa;margin-bottom:4px">Bank Transactions</div>'
      + '<div style="padding:3px 0;border-bottom:1px solid #2a2a2e">'
      + '<div style="display:flex;justify-content:space-between;color:#fff">'
      + '<span>Whole Foods</span><span>-$47.23</span></div>'
      + '<div style="color:#4ade80;font-size:0.7rem">✓ Matched to receipt May 18</div></div>'
      + '<div style="padding:3px 0">'
      + '<div style="display:flex;justify-content:space-between;color:#fff">'
      + '<span>Netflix</span><span>-$18.00</span></div>'
      + '<div style="color:#888;font-size:0.7rem">Unmatched</div></div>'
      + '</div>',
    interactions: [
      "Link bank account via Plaid OAuth",
      "Transactions sync daily automatically",
      "Auto-match to scanned receipts by amount+date",
      "Link unmatched transactions to floor obligations",
    ],
    tip: "Plaid matching uses amount + date ±3 days. If a receipt total was edited, it may not auto-match — link manually.",
  },

  {
    id: "cash-transactions",
    group: "Finance",
    icon: "💵",
    title: "Cash Transactions",
    tagline: "Manually log cash spend with no receipt — feeds into spending analytics",
    platforms: ["Web"],
    where: "Nav -> Analytics -> Cash tab",
    flow: [
      { icon: "💵", label: "Log cash",   sub: "amount + note" },
      { icon: "🏷",  label: "Category",  sub: "tag it" },
      { icon: "📊", label: "Analytics",  sub: "included in spend" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:6px;padding:6px 10px;font-size:0.75rem">'
      + '<div style="color:#aaa;margin-bottom:4px">Log Cash Spend</div>'
      + '<input style="background:#2a2a2e;border:none;border-radius:3px;color:#fff;padding:3px 6px;font-size:0.72rem;width:100%;margin-bottom:4px;box-sizing:border-box" placeholder="Farmer\'s market" />'
      + '<div style="display:flex;gap:4px;margin-bottom:4px">'
      + '<input style="background:#2a2a2e;border:none;border-radius:3px;color:#fff;padding:3px 6px;font-size:0.72rem;flex:1" placeholder="$0.00" />'
      + '<select style="background:#2a2a2e;border:none;border-radius:3px;color:#fff;padding:3px 6px;font-size:0.72rem;flex:1">'
      + '<option>Grocery</option><option>Dining</option></select></div>'
      + '<button style="background:#3b82f6;color:#fff;border:none;border-radius:4px;padding:4px 10px;font-size:0.72rem;width:100%">Log Cash Spend</button>'
      + '</div>',
    interactions: [
      "Enter amount and description",
      "Assign to a spending category",
      "Back-date if you forgot same day",
      "Appears in analytics alongside receipt spend",
    ],
    tip: "Cash transactions don't affect inventory — analytics only.",
  },

  // ── Shared Dining ─────────────────────────────────────────────────────────
  {
    id: "split-bills",
    group: "Shared Dining",
    icon: "➗",
    title: "Split Bills",
    tagline: "Split restaurant receipts by person — tracks who owes what",
    platforms: ["Web", "Telegram"],
    where: "Nav -> Dining -> Split tab",
    flow: [
      { icon: "🍽",  label: "Restaurant receipt", sub: "scan or upload" },
      { icon: "👥", label: "Add diners",          sub: "pick contacts" },
      { icon: "➗", label: "Split",               sub: "even or custom" },
      { icon: "⚖️", label: "Debts",               sub: "who owes who" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:6px;padding:6px 10px;font-size:0.75rem">'
      + '<div style="color:#fff;font-weight:bold;margin-bottom:4px">Nobu &middot; $120.00 &middot; 4 people</div>'
      + '<div style="display:flex;justify-content:space-between;padding:3px 0">'
      + '<span style="color:#fff">You</span>'
      + '<span style="color:#4ade80">$30.00 paid</span></div>'
      + '<div style="display:flex;justify-content:space-between;padding:3px 0">'
      + '<span style="color:#fff">Alex</span>'
      + '<span style="color:#e0a134">$30.00 owes you</span></div>'
      + '<div style="display:flex;justify-content:space-between;padding:3px 0">'
      + '<span style="color:#fff">Sam</span>'
      + '<span style="color:#e0a134">$30.00 owes you</span></div>'
      + '</div>',
    interactions: [
      "Select contacts who joined the meal",
      "Even split or custom amounts per person",
      "Split via Telegram Dining Walk bot",
      "Debts tracked in Balances view",
    ],
    tip: "You can split via Telegram too — use the Dining Walk bot to photograph the bill and assign items per person in chat.",
  },

  {
    id: "contacts",
    group: "Shared Dining",
    icon: "👥",
    title: "Contacts",
    tagline: "Dining contacts list — per-contact balance and meal history",
    platforms: ["Web"],
    where: "Nav -> Dining -> Contacts tab",
    flow: [
      { icon: "➕", label: "Add contact",  sub: "by name" },
      { icon: "🍽",  label: "Share meals", sub: "split bills together" },
      { icon: "⚖️", label: "Balance",      sub: "running total" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:6px;padding:6px 10px;font-size:0.75rem">'
      + '<div style="color:#aaa;margin-bottom:4px">Dining Contacts</div>'
      + '<div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid #2a2a2e">'
      + '<div><div style="color:#fff">Alex</div>'
      + '<div style="color:#888;font-size:0.7rem">12 shared meals</div></div>'
      + '<span style="color:#e0a134">owes you $45</span></div>'
      + '<div style="display:flex;justify-content:space-between;align-items:center;padding:3px 0">'
      + '<div><div style="color:#fff">Sam</div>'
      + '<div style="color:#888;font-size:0.7rem">5 shared meals</div></div>'
      + '<span style="color:#4ade80">you owe $12</span></div>'
      + '</div>',
    interactions: [
      "Add dining contacts by name",
      "View meal history per contact",
      "See running balance",
      "Mark settled from Balances view",
    ],
    tip: "Contacts are separate from household members — they're external friends you split bills with.",
  },

  {
    id: "balances-settle",
    group: "Shared Dining",
    icon: "⚖️",
    title: "Balances and Settle",
    tagline: "Outstanding debt view across all contacts — settle-all with one tap",
    platforms: ["Web"],
    where: "Nav -> Dining -> Balances tab",
    flow: [
      { icon: "⚖️", label: "View debts", sub: "all contacts" },
      { icon: "💸", label: "Settle",     sub: "mark paid" },
      { icon: "✅", label: "Cleared",    sub: "balance reset" },
    ],
    mockup: '<div style="background:#1a1a1e;border-radius:6px;padding:6px 10px;font-size:0.75rem">'
      + '<div style="color:#aaa;margin-bottom:4px">Balances</div>'
      + '<div style="text-align:center;padding:4px 0">'
      + '<div style="color:#4ade80;font-weight:bold;font-size:0.8rem">Total owed to you $75</div>'
      + '<div style="color:#e0a134;font-weight:bold;font-size:0.8rem;margin-top:2px">You owe $12</div></div>'
      + '<button style="background:#4ade80;color:#000;border:none;border-radius:4px;padding:4px 10px;font-size:0.72rem;width:100%;margin-top:6px;font-weight:bold">Settle All</button>'
      + '</div>',
    interactions: [
      "See net position across all contacts",
      "Settle individual or settle-all",
      "Debt history per contact",
    ],
    tip: "Settle-all marks all outstanding debts as paid — it doesn't send notifications. Tell people externally.",
  },

  // ── Telegram Bot ──────────────────────────────────────────────────────────
  {
    id: "shopping-walk",
    group: "Telegram Bot",
    icon: "🛍",
    title: "Shopping Walk",
    tagline: "Guided Telegram session — item-by-item confirmation while you're at the store",
    platforms: ["Telegram"],
    where: "Telegram -> /shopping or nudge tap",
    flow: [
      { icon: "📱", label: "Start walk", sub: "/shopping" },
      { icon: "🛍", label: "Item-by-item", sub: "bot guides you" },
      { icon: "✅", label: "Confirm", sub: "got it or skip" },
      { icon: "📦", label: "Stock updated", sub: "auto" },
    ],
    mockup: '<div style="max-width:260px;background:#1a1a1e;border-radius:10px;padding:10px;font-size:0.75rem;color:#fff">'
      + '<div style="font-size:0.65rem;color:#aaa;margin-bottom:4px">ShopBot</div>'
      + '<div style="background:#2a2a2e;border-radius:8px;padding:8px;margin-bottom:8px">'
      + '<div style="font-weight:bold;margin-bottom:4px">🛒 Shopping Walk</div>'
      + '<div style="color:#fff;margin-bottom:2px">Next: Organic Milk 1gal</div>'
      + '<div style="color:#aaa;font-size:0.7rem">Last price: $5.49 · Low stock ⚠️</div>'
      + '</div>'
      + '<div style="display:flex;gap:6px">'
      + '<div style="background:#16a34a;color:#fff;border-radius:6px;padding:4px 10px;font-size:0.72rem;text-align:center;flex:1">✅ Got it</div>'
      + '<div style="background:#3a1a1a;color:#f87171;border-radius:6px;padding:4px 10px;font-size:0.72rem;text-align:center;flex:1">❌ Skip</div>'
      + '</div>'
      + '</div>',
    interactions: [
      "Start with /shopping in Telegram",
      "Got it to add to cart / Skip to pass",
      "Resume a paused walk with /resume",
      "Stock levels update after each confirmation",
    ],
    tip: "If you close Telegram mid-walk, send /resume to pick up where you left off.",
  },
  {
    id: "inventory-walk",
    group: "Telegram Bot",
    icon: "📦",
    title: "Inventory Walk",
    tagline: "Update inventory quantities via Telegram — bot asks, you reply with count",
    platforms: ["Telegram"],
    where: "Telegram -> /inventory",
    flow: [
      { icon: "📱", label: "Start", sub: "/inventory" },
      { icon: "📦", label: "Item prompt", sub: "bot asks qty" },
      { icon: "🔢", label: "Reply qty", sub: "type number" },
      { icon: "✅", label: "Saved", sub: "inventory updated" },
    ],
    mockup: '<div style="max-width:260px;background:#1a1a1e;border-radius:10px;padding:10px;font-size:0.75rem;color:#fff">'
      + '<div style="font-size:0.65rem;color:#aaa;margin-bottom:4px">ShopBot</div>'
      + '<div style="background:#2a2a2e;border-radius:8px;padding:8px;margin-bottom:6px">'
      + '<div style="color:#fff">How many Organic Milk 1gal do you have?</div>'
      + '<div style="color:#aaa;font-size:0.7rem;margin-top:2px">Current: 2 · Reply with new count</div>'
      + '</div>'
      + '<div style="display:flex;justify-content:flex-end;margin-bottom:6px">'
      + '<div style="background:#1e3a5f;color:#fff;border-radius:8px;padding:5px 10px;font-size:0.75rem">3</div>'
      + '</div>'
      + '<div style="background:#2a2a2e;border-radius:8px;padding:8px">'
      + '<div style="color:#4ade80">✅ Updated to 3. Next: Sourdough Bread...</div>'
      + '</div>'
      + '</div>',
    interactions: [
      "Start with /inventory in Telegram",
      "Reply with current quantity for each item",
      "Type 'skip' to leave an item unchanged",
      "Walk ends when all items counted",
    ],
    tip: "Use Inventory Walk after a big restock. Faster than editing counts one-by-one in the web UI.",
  },
  {
    id: "dining-walk",
    group: "Telegram Bot",
    icon: "🍽",
    title: "Dining Walk",
    tagline: "Split a restaurant bill via Telegram — photo the bill, assign items per person",
    platforms: ["Telegram"],
    where: "Telegram -> /dining",
    flow: [
      { icon: "📷", label: "Photo bill", sub: "send to bot" },
      { icon: "🤖", label: "OCR", sub: "extracts items" },
      { icon: "👥", label: "Assign", sub: "who had what" },
      { icon: "⚖️", label: "Splits", sub: "calculated" },
    ],
    mockup: '<div style="max-width:260px;background:#1a1a1e;border-radius:10px;padding:10px;font-size:0.75rem;color:#fff">'
      + '<div style="font-size:0.65rem;color:#aaa;margin-bottom:4px">ShopBot</div>'
      + '<div style="background:#2a2a2e;border-radius:8px;padding:8px;margin-bottom:6px">'
      + '<div style="color:#fff;margin-bottom:2px">Who had Pad Thai $14.50?</div>'
      + '<div style="color:#aaa;font-size:0.7rem">Reply: me / alex / sam / all</div>'
      + '</div>'
      + '<div style="display:flex;justify-content:flex-end">'
      + '<div style="background:#1e3a5f;color:#fff;border-radius:8px;padding:5px 10px;font-size:0.75rem">me and alex</div>'
      + '</div>'
      + '</div>',
    interactions: [
      "Send receipt photo to bot in Telegram",
      "Bot extracts line items via OCR",
      "Assign each item to person(s)",
      "Bot calculates final split per person",
    ],
    tip: "Assign an item to multiple people — the bot splits that item's cost evenly among them.",
  },
  {
    id: "nudges",
    group: "Telegram Bot",
    icon: "🔔",
    title: "Nudges",
    tagline: "Scheduled Telegram reminders — shopping nudge at 09:30 when low-stock items exist",
    platforms: ["Telegram"],
    where: "Telegram -> auto-sent at scheduled time",
    flow: [
      { icon: "⚙️", label: "Configure", sub: "time + type" },
      { icon: "🔔", label: "Nudge sent", sub: "at schedule" },
      { icon: "📱", label: "Tap CTA", sub: "start walk" },
    ],
    mockup: '<div style="max-width:260px;background:#1a1a1e;border-radius:10px;padding:10px;font-size:0.75rem;color:#fff">'
      + '<div style="font-size:0.65rem;color:#aaa;margin-bottom:4px">ShopBot · 9:30 AM</div>'
      + '<div style="background:#2a2a2e;border-radius:8px;padding:8px;margin-bottom:8px">'
      + '<div style="font-weight:bold;margin-bottom:4px">🛒 Shopping reminder</div>'
      + '<div style="color:#fff;margin-bottom:2px">You have 5 low-stock items.</div>'
      + '<div style="color:#aaa;font-size:0.7rem">Ready to walk the store?</div>'
      + '</div>'
      + '<div style="display:flex;gap:6px">'
      + '<div style="background:#3b82f6;color:#fff;border-radius:6px;padding:4px 10px;font-size:0.72rem;text-align:center;flex:1">Start walk</div>'
      + '<div style="background:#333;color:#aaa;border-radius:6px;padding:4px 10px;font-size:0.72rem;text-align:center;flex:1">Later</div>'
      + '</div>'
      + '</div>',
    interactions: [
      "Fires daily at 09:30 if low-stock items exist",
      "Tap 'Start walk' to begin Shopping Walk inline",
      "Tap 'Later' to dismiss for today",
    ],
    tip: "Nudge only fires when there are actual low-stock items — you won't get reminders on a fully-stocked week.",
  },

  // ── Household ─────────────────────────────────────────────────────────────
  {
    id: "auth-members",
    group: "Household",
    icon: "🔑",
    title: "Auth and Members",
    tagline: "Login, household roles (admin/member), invite flow for new members",
    platforms: ["Web", "Mobile"],
    where: "/ (login page) · Nav -> Settings -> Members",
    flow: [
      { icon: "🔑", label: "Login", sub: "email + pass" },
      { icon: "🏠", label: "Household", sub: "join or create" },
      { icon: "👥", label: "Invite", sub: "share code" },
      { icon: "✅", label: "Member", sub: "full access" },
    ],
    mockup: '<div style="max-width:260px;background:#1a1a1e;border-radius:10px;padding:10px;font-size:0.75rem;color:#fff">'
      + '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2a2a2e">'
      + '<div><div style="font-weight:bold">You (admin)</div><div style="color:#888;font-size:0.7rem">chatwithllm@gmail.com</div></div>'
      + '<div style="background:#1e3a5f;color:#60a5fa;border-radius:4px;padding:2px 8px;font-size:0.65rem;font-weight:bold">admin</div>'
      + '</div>'
      + '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2a2a2e">'
      + '<div><div style="font-weight:bold">Alex</div><div style="color:#888;font-size:0.7rem">alex@example.com</div></div>'
      + '<div style="background:#2a2a2e;color:#aaa;border-radius:4px;padding:2px 8px;font-size:0.65rem">member</div>'
      + '</div>'
      + '<div style="background:#3b82f6;color:#fff;border-radius:6px;padding:5px 10px;font-size:0.72rem;text-align:center;margin-top:8px">+ Invite member</div>'
      + '</div>',
    interactions: [
      "Email + password login",
      "Create new household or join with invite code",
      "Admin can invite and remove members",
      "All members share the same data",
    ],
    tip: "All household members share inventory, receipts, and analytics. Contributions track who scanned what.",
  },
  {
    id: "contributions",
    group: "Household",
    icon: "🏅",
    title: "Contributions",
    tagline: "Who scanned what — per-member contribution ledger and monthly leaderboard",
    platforms: ["Web"],
    where: "Nav -> Contribution",
    flow: [
      { icon: "📸", label: "Member scans", sub: "receipt" },
      { icon: "🏅", label: "Credit", sub: "auto-recorded" },
      { icon: "📊", label: "Leaderboard", sub: "monthly" },
    ],
    mockup: '<div style="max-width:260px;background:#1a1a1e;border-radius:10px;padding:10px;font-size:0.75rem;color:#fff">'
      + '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2a2a2e">'
      + '<div style="display:flex;align-items:center;gap:6px"><span>🥇</span><div><div style="font-weight:bold;color:#4ade80">You</div><div style="color:#888;font-size:0.7rem">42 receipts this month</div></div></div>'
      + '<div style="color:#4ade80;font-weight:bold">1,240 pts</div>'
      + '</div>'
      + '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0">'
      + '<div style="display:flex;align-items:center;gap:6px"><span>🥈</span><div><div style="color:#aaa">Alex</div><div style="color:#888;font-size:0.7rem">18 receipts</div></div></div>'
      + '<div style="color:#aaa">540 pts</div>'
      + '</div>'
      + '</div>',
    interactions: [
      "Monthly leaderboard by receipts scanned",
      "Drill into any member's contribution list",
      "Points reset each month",
    ],
    tip: "Points are just for fun — no app behavior changes based on rank.",
  },
  {
    id: "demo-mode",
    group: "Household",
    icon: "👁",
    title: "Demo Mode",
    tagline: "Read-only guest mode with seeded sample data — safe to show anyone",
    platforms: ["Web"],
    where: "/ (login page) -> Try Demo",
    flow: [
      { icon: "👁", label: "Open demo", sub: "no login" },
      { icon: "🔒", label: "Read-only", sub: "no mutations" },
      { icon: "📊", label: "Full UI", sub: "seeded data" },
    ],
    mockup: '<div style="max-width:260px;background:#1a1a1e;border-radius:10px;padding:10px;font-size:0.75rem;color:#fff">'
      + '<div style="background:#e0a134;color:#000;border-radius:6px;padding:5px 8px;font-size:0.72rem;margin-bottom:8px;font-weight:bold">'
      + '👁 Demo Mode — read-only. Data is sample data only.'
      + '</div>'
      + '<div style="color:#aaa;font-size:0.7rem;margin-bottom:6px">All features visible. Write actions show:</div>'
      + '<div style="color:#e0a134;font-size:0.72rem">Demo mode — sign in to save</div>'
      + '</div>',
    interactions: [
      "Click 'Try Demo' on the login page",
      "Browse full UI with realistic sample data",
      "Write actions prompt you to sign in",
      "Exit demo by clicking Sign In",
    ],
    tip: "Demo mode is perfect for showing the app to a potential new household member before they create an account.",
  },
  {
    id: "ai-chat",
    group: "Household",
    icon: "🤖",
    title: "AI Chat",
    tagline: "Natural language questions about your spending and inventory",
    platforms: ["Web"],
    where: "Nav -> Chat",
    flow: [
      { icon: "💬", label: "Ask question", sub: "plain English" },
      { icon: "🤖", label: "AI queries", sub: "your data" },
      { icon: "📊", label: "Answer", sub: "with context" },
    ],
    mockup: '<div style="max-width:260px;background:#1a1a1e;border-radius:10px;padding:10px;font-size:0.75rem;color:#fff">'
      + '<div style="display:flex;justify-content:flex-end;margin-bottom:6px">'
      + '<div style="background:#1e3a5f;color:#fff;border-radius:8px;padding:5px 10px;font-size:0.72rem;max-width:80%">How much did I spend on groceries last month?</div>'
      + '</div>'
      + '<div style="background:#2a2a2e;border-radius:8px;padding:8px;font-size:0.72rem">'
      + '<div style="color:#60a5fa;font-size:0.65rem;margin-bottom:4px">AI</div>'
      + '<div style="color:#fff">In April you spent <span style="color:#4ade80;font-weight:bold">$342</span> on groceries across 8 receipts.</div>'
      + '<div style="color:#aaa;margin-top:4px">Whole Foods was your most visited ($210).</div>'
      + '</div>'
      + '</div>',
    interactions: [
      "Ask anything about your spending history",
      "Ask about inventory ('do I have eggs?')",
      "Get summaries ('biggest expense category?')",
      "Switch AI model in Settings",
    ],
    tip: "Chat has access to receipts, inventory, and analytics — not bank transaction details.",
  },
  {
    id: "medications",
    group: "Household",
    icon: "💊",
    title: "Medications",
    tagline: "Medication tracking workspace — log medications, track stock, set refill alerts",
    platforms: ["Web"],
    where: "Nav -> Medications",
    flow: [
      { icon: "➕", label: "Add med", sub: "name + dose" },
      { icon: "💊", label: "Track", sub: "stock count" },
      { icon: "🔔", label: "Remind", sub: "refill alert" },
    ],
    mockup: '<div style="max-width:260px;background:#1a1a1e;border-radius:10px;padding:10px;font-size:0.75rem;color:#fff">'
      + '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid #2a2a2e">'
      + '<div><div style="font-weight:bold">Vitamin D 2000IU</div><div style="color:#888;font-size:0.7rem">Daily · 45 remaining</div></div>'
      + '<div style="color:#4ade80;font-size:0.8rem">✓</div>'
      + '</div>'
      + '<div style="display:flex;align-items:center;justify-content:space-between;padding:6px 0">'
      + '<div><div style="font-weight:bold">Magnesium</div><div style="color:#e0a134;font-size:0.7rem">⚠️ 5 remaining — refill soon</div></div>'
      + '<div style="color:#e0a134;font-size:0.8rem">⚠️</div>'
      + '</div>'
      + '</div>',
    interactions: [
      "Add medications with name, dose, frequency",
      "Track remaining pill count",
      "Get refill alerts when stock is low",
      "View medication history",
    ],
    tip: "Medication stock doesn't auto-decrement — update count manually when you open a new bottle.",
  },
];
