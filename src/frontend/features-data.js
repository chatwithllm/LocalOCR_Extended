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
];
