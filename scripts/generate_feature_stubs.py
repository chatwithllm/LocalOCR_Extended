#!/usr/bin/env python3
"""
generate_feature_stubs.py — One-time utility to generate features.html data stubs.

Reads spec files from docs/superpowers/specs/ and outputs window.FEATURES_DATA
as a flat array with group field on each feature.

Usage:
    python scripts/generate_feature_stubs.py > src/frontend/features-data.js
    python scripts/generate_feature_stubs.py 2>/dev/null | head -10
"""

import os
import sys
import re
from pathlib import Path

GROUPS = [
    {"label": "Receipts",      "icon": "📸",  "features": ["ocr-upload", "review-edit", "rerun-ocr", "receipt-types"]},
    {"label": "Grocery",       "icon": "🛒",  "features": ["inventory", "shopping-list", "recommendations", "kitchen-view"]},
    {"label": "Restaurant",    "icon": "🍽",  "features": ["restaurant-workspace", "repeat-orders", "dining-budget"]},
    {"label": "Expenses",      "icon": "💸",  "features": ["expense-tracking", "category-tagging", "expense-analytics"]},
    {"label": "Finance",       "icon": "📊",  "features": ["spending-by-category", "fixed-bills", "plaid-integration", "cash-transactions"]},
    {"label": "Shared Dining", "icon": "🤝",  "features": ["split-bills", "contacts", "balances-settle"]},
    {"label": "Telegram Bot",  "icon": "🤖",  "features": ["shopping-walk", "inventory-walk", "dining-walk", "nudges"]},
    {"label": "Household",     "icon": "🏠",  "features": ["auth-members", "contributions", "demo-mode", "ai-chat", "medications"]},
]

FEATURE_META = {
    "ocr-upload":           {"icon": "📸", "title": "OCR Upload"},
    "review-edit":          {"icon": "✏️", "title": "Review and Edit"},
    "rerun-ocr":            {"icon": "🔄", "title": "Re-run OCR"},
    "receipt-types":        {"icon": "🏷", "title": "Receipt Types"},
    "inventory":            {"icon": "📦", "title": "Inventory"},
    "shopping-list":        {"icon": "🛒", "title": "Shopping List"},
    "recommendations":      {"icon": "💡", "title": "Recommendations"},
    "kitchen-view":         {"icon": "🍳", "title": "Kitchen View"},
    "restaurant-workspace": {"icon": "🍽", "title": "Restaurant Workspace"},
    "repeat-orders":        {"icon": "🔁", "title": "Repeat Orders"},
    "dining-budget":        {"icon": "💳", "title": "Dining Budget"},
    "expense-tracking":     {"icon": "💸", "title": "Expense Tracking"},
    "category-tagging":     {"icon": "🏷", "title": "Category Tagging"},
    "expense-analytics":    {"icon": "📉", "title": "Expense Analytics"},
    "spending-by-category": {"icon": "📊", "title": "Spending by Category"},
    "fixed-bills":          {"icon": "📌", "title": "Fixed Bills"},
    "plaid-integration":    {"icon": "🏦", "title": "Plaid Integration"},
    "cash-transactions":    {"icon": "💵", "title": "Cash Transactions"},
    "split-bills":          {"icon": "➗", "title": "Split Bills"},
    "contacts":             {"icon": "👥", "title": "Contacts"},
    "balances-settle":      {"icon": "⚖️", "title": "Balances and Settle"},
    "shopping-walk":        {"icon": "🛍", "title": "Shopping Walk"},
    "inventory-walk":       {"icon": "📦", "title": "Inventory Walk"},
    "dining-walk":          {"icon": "🍽", "title": "Dining Walk"},
    "nudges":               {"icon": "🔔", "title": "Nudges"},
    "auth-members":         {"icon": "🔑", "title": "Auth and Members"},
    "contributions":        {"icon": "🏅", "title": "Contributions"},
    "demo-mode":            {"icon": "👁", "title": "Demo Mode"},
    "ai-chat":              {"icon": "🤖", "title": "AI Chat"},
    "medications":          {"icon": "💊", "title": "Medications"},
}


def read_specs_dir(spec_dir):
    """Read all .md files from spec directory and extract Goal paragraphs."""
    taglines = {}

    if not os.path.isdir(spec_dir):
        return taglines

    spec_files = sorted([f for f in os.listdir(spec_dir) if f.endswith('.md')])

    for filename in spec_files:
        filepath = os.path.join(spec_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Find "## Goal" section and extract first paragraph
            goal_match = re.search(r'##\s+[0-9]+\.\s+Goal\n\n(.+?)(?:\n\n##|\Z)', content, re.DOTALL)
            if goal_match:
                goal_text = goal_match.group(1).strip()
                # Take first line (or first sentence)
                first_line = goal_text.split('\n')[0].strip()
                if first_line:
                    # Try to match this goal to a feature by keyword
                    matched_feature = keyword_match_feature(first_line)
                    if matched_feature:
                        taglines[matched_feature] = first_line
        except Exception as e:
            print(f"Warning: Could not read {filename}: {e}", file=sys.stderr)

    return taglines


def keyword_match_feature(text):
    """
    Attempt to match a goal/tagline text to a feature ID by keyword.
    Returns feature_id or None.
    """
    text_lower = text.lower()

    # Build keyword map: feature_id -> keywords
    keywords_map = {
        "shopping-walk":      ["shopping", "walk", "telegram", "shop"],
        "inventory-walk":     ["inventory", "walk", "telegram"],
        "dining-walk":        ["dining", "walk", "telegram"],
        "nudges":             ["nudge", "telegram"],
        "kitchen-view":       ["kitchen", "view"],
        "inventory":          ["inventory"],
        "shopping-list":      ["shopping list", "shopping"],
        "recommendations":    ["recommend"],
        "restaurant-workspace": ["restaurant", "workspace"],
        "repeat-orders":      ["repeat", "order"],
        "dining-budget":      ["dining", "budget"],
        "expense-tracking":   ["expense", "tracking"],
        "category-tagging":   ["category", "tag"],
        "expense-analytics":  ["expense", "analytics"],
        "spending-by-category": ["spending", "category"],
        "fixed-bills":        ["fixed", "bills", "obligation"],
        "plaid-integration":  ["plaid"],
        "cash-transactions":  ["cash"],
        "split-bills":        ["split", "bill"],
        "balances-settle":    ["balance", "settle"],
        "auth-members":       ["auth", "member"],
        "contributions":      ["contribution"],
        "demo-mode":          ["demo", "mode"],
        "ai-chat":            ["ai", "chat"],
        "medications":        ["medication"],
        "ocr-upload":         ["ocr", "upload"],
        "review-edit":        ["review", "edit"],
        "rerun-ocr":          ["rerun", "ocr"],
        "receipt-types":      ["receipt", "type"],
        "contacts":           ["contact"],
    }

    # Return the first feature whose keyword list has any match (insertion order)
    for feature_id, keywords in keywords_map.items():
        for keyword in keywords:
            if keyword in text_lower:
                return feature_id

    return None


def generate_feature_stubs():
    """Generate the feature stubs array and return as JS string."""
    # Determine spec directory relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    spec_dir = os.path.join(project_root, 'docs', 'superpowers', 'specs')

    # Read taglines from spec files
    taglines = read_specs_dir(spec_dir)

    # Track which features have taglines
    features_with_taglines = set(taglines.keys())
    all_features = set()

    # Build flat array
    features_array = []

    for group in GROUPS:
        group_label = group["label"]
        for feature_id in group["features"]:
            all_features.add(feature_id)

            if feature_id not in FEATURE_META:
                print(f"Warning: Feature {feature_id} not in FEATURE_META", file=sys.stderr)
                continue

            meta = FEATURE_META[feature_id]
            tagline = taglines.get(feature_id, f"TODO: one-line description")

            feature_obj = {
                "id": feature_id,
                "group": group_label,
                "icon": meta["icon"],
                "title": meta["title"],
                "tagline": tagline,
                "platforms": ["Web"],
                "where": "TODO: nav path",
                "flow": [
                    {"icon": "▶️", "label": "Start", "sub": ""},
                    {"icon": "✅", "label": "Done", "sub": ""},
                ],
                "mockup": "",
                "interactions": ["TODO"],
                "tip": "",
            }
            features_array.append(feature_obj)

    # Generate JavaScript output
    js_lines = [
        "// Auto-generated stub data for features.html",
        "// Generated by scripts/generate_feature_stubs.py",
        "",
        "window.FEATURES_DATA = [",
    ]

    for i, feature in enumerate(features_array):
        js_lines.append("  {")
        js_lines.append(f'    id: "{feature["id"]}", ')
        js_lines.append(f'    group: "{feature["group"]}", ')
        def esc(s):
            return s.replace('\\', '\\\\').replace('"', '\\"')

        js_lines.append(f'    icon: "{esc(feature["icon"])}", ')
        js_lines.append(f'    title: "{esc(feature["title"])}", ')
        js_lines.append(f'    tagline: "{esc(feature["tagline"])}", ')
        js_lines.append(f'    platforms: {repr(feature["platforms"]).replace("'", '"')}, ')
        js_lines.append(f'    where: "{esc(feature["where"])}", ')

        # Flow array
        js_lines.append("    flow: [")
        for flow_item in feature["flow"]:
            js_lines.append(f'      {{ icon: "{esc(flow_item["icon"])}", label: "{esc(flow_item["label"])}", sub: "{esc(flow_item["sub"])}" }},')
        js_lines.append("    ],")

        js_lines.append(f'    mockup: "{feature["mockup"]}", ')
        js_lines.append(f'    interactions: {repr(feature["interactions"]).replace("'", '"')}, ')
        js_lines.append(f'    tip: "{esc(feature["tip"])}", ')

        if i < len(features_array) - 1:
            js_lines.append("  },")
        else:
            js_lines.append("  },")

    js_lines.append("];")
    js_lines.append("")

    # Print to stdout
    print('\n'.join(js_lines))

    # Print checklist to stderr
    print("", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print("FEATURES TAGLINE CHECKLIST", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"Total features: {len(all_features)}", file=sys.stderr)
    print(f"Features with taglines from specs: {len(features_with_taglines)}", file=sys.stderr)
    print(f"Features needing manual taglines: {len(all_features) - len(features_with_taglines)}", file=sys.stderr)
    print("", file=sys.stderr)

    if features_with_taglines:
        print("✓ Got taglines for:", file=sys.stderr)
        for fid in sorted(features_with_taglines):
            print(f"  - {fid}: {taglines[fid][:60]}...", file=sys.stderr)
        print("", file=sys.stderr)

    needs_taglines = sorted(all_features - features_with_taglines)
    if needs_taglines:
        print("TODO: Add manual taglines for:", file=sys.stderr)
        for fid in needs_taglines:
            print(f"  - {fid}", file=sys.stderr)
        print("", file=sys.stderr)

    print("Output: stdout is valid JavaScript (window.FEATURES_DATA)", file=sys.stderr)
    print("=" * 70, file=sys.stderr)


if __name__ == "__main__":
    generate_feature_stubs()
