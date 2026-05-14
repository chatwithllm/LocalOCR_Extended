# Telegram Shopping Walk Implementation Plan — Part 2 (Tasks 11–20)

> Continues from [Part 1](./2026-05-14-telegram-shopping-walk.md). Tasks 1–10 deliver migration, model, env config, session helpers, recommendation fetch + bucketize, inserts, renderers, `start_walk`, `handle_category`.

---

## Task 11: `handle_add` (quick add, qty=1)

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_handle_add_inserts_qty_one_and_advances(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_add, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        TelegramShoppingSession, ShoppingListItem, Product,
    )
    # Seed products so insert can satisfy FK.
    p1 = Product(name="Olive oil", category="pantry"); session.add(p1); session.flush()
    p2 = Product(name="Pepper", category="pantry"); session.add(p2); session.flush()

    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p1.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock", "current_quantity": 1.0, "threshold": 5.0},
            {"product_id": p2.id, "product_name": "Pepper", "category": "pantry",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_add(session, "abc", message_id=100); session.commit()

    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["added"] == 1
    items = session.query(ShoppingListItem).all()
    assert len(items) == 1
    assert items[0].name == "Olive oil"
    assert items[0].quantity == 1
    assert items[0].preferred_store is None
    assert items[0].source == "telegram_shopping"
```

- [ ] **Step 2: Run test — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_add and not handle_add_detailed"`
Expected: FAIL — `handle_add` not defined.

- [ ] **Step 3: Implement `_advance_or_end_category` + `handle_add`**

Append to `src/backend/handle_shopping_walk.py`:

```python
def _advance_or_end_category(session, row, message_id: int | None) -> None:
    """After per-item action: cursor+1; render next item or transition to CATEGORY_END."""
    row.cursor += 1
    if row.cursor < len(row.item_queue):
        _render_current_item(row, message_id)
        return
    # End of items in this category — render CATEGORY_END.
    next_cat = row.category_queue[0] if row.category_queue else None
    text, kb = render_category_end(
        category=row.current_category or "other",
        next_category=next_cat,
        stats=row.stats or {},
    )
    row.pending_prompt = "category_end"
    _edit_telegram_message(row.chat_id, message_id, text, reply_markup=kb)


def handle_add(session, chat_id: str, message_id: int | None) -> None:
    """User tapped + Add (qty=1, no store). Insert + advance."""
    row = get_or_create_session(session, chat_id)
    if row.cursor >= len(row.item_queue):
        return
    item = row.item_queue[row.cursor]
    inserted = insert_recommendation(
        session,
        product_id=item.get("product_id"),
        name=item.get("name", "Item"),
        category=item.get("category"),
        quantity=1.0,
        preferred_store=None,
    )
    # Only bump stats if a NEW row was created (dedup might return existing).
    # We can't easily detect new-vs-existing without a flag — bump unconditionally;
    # one-walk-one-item-one-add invariant means double-bumping is structurally
    # impossible within a single walk for a given product_id.
    stats = dict(row.stats or {})
    stats["added"] = stats.get("added", 0) + 1
    row.stats = stats
    _advance_or_end_category(session, row, message_id)
```

- [ ] **Step 4: Run test**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_add and not handle_add_detailed"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): handle_add (quick add qty=1) + advance/end-category"
```

---

## Task 12: `handle_add_detailed` + `handle_qty`

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_handle_add_detailed_transitions_to_qty_prompt(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_add_detailed, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        TelegramShoppingSession, Product,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((c, m, t, reply_markup)),
    )
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_add_detailed(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "qty"
    assert row.pending_action == "add_detailed"
    assert "how many" in edits[-1][2].lower()


def test_handle_qty_transitions_to_store_prompt(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_qty, handle_add_detailed, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        TelegramShoppingSession, Product, Store, Purchase,
    )
    from datetime import datetime
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    s_store = Store(name="Costco"); session.add(s_store); session.flush()
    session.add(Purchase(store_id=s_store.id, total_amount=1.0,
                         date=datetime.utcnow(), transaction_type="purchase"))
    session.commit()

    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((c, m, t, reply_markup)),
    )
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()

    handle_qty(session, "abc", qty_arg="3", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "store"
    assert row.pending_qty == 3.0
    last = edits[-1][2]
    assert "× 3" in last or "x 3" in last.lower()
    callbacks = [b["callback_data"] for r in edits[-1][3]["inline_keyboard"] for b in r]
    assert "shop:store:costco" in callbacks


def test_handle_qty_custom_enters_typed_text_state(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_qty, handle_add_detailed, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        TelegramShoppingSession, Product,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()

    handle_qty(session, "abc", qty_arg="cu", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    # qty:cu prompts user to type a number — stays in qty state (typed-text branch)
    assert row.pending_prompt == "qty"
    assert row.pending_action == "add_detailed_qty_typed"
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_add_detailed or handle_qty"`
Expected: FAIL.

- [ ] **Step 3: Implement handlers**

Append to `src/backend/handle_shopping_walk.py`:

```python
def handle_add_detailed(session, chat_id: str, message_id: int | None) -> None:
    """User tapped + Add w/ qty+store. Render qty prompt, transition state."""
    row = get_or_create_session(session, chat_id)
    if row.cursor >= len(row.item_queue):
        return
    item = row.item_queue[row.cursor]
    text, kb = render_qty_prompt(item.get("name", "Item"))
    row.pending_prompt = "qty"
    row.pending_action = "add_detailed"
    row.last_item_id = item.get("product_id")
    _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)


def handle_qty(session, chat_id: str, qty_arg: str,
               message_id: int | None) -> None:
    """User tapped a qty button (1..5 or 'cu' for typed-text)."""
    row = get_or_create_session(session, chat_id)
    if qty_arg == "cu":
        # Switch to typed-text qty state. Next inbound message text is the qty.
        text = "Enter the quantity (number):"
        kb = {"inline_keyboard": [[{"text": "← Back", "callback_data": "shop:back"}]]}
        row.pending_action = (
            "custom_add_qty_typed"
            if row.pending_prompt == "custom_qty"
            else "add_detailed_qty_typed"
        )
        # pending_prompt stays "qty" or "custom_qty"
        _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)
        return

    try:
        qty = float(qty_arg)
    except ValueError:
        return  # malformed

    row.pending_qty = qty

    # Render store prompt — same for both recommendation and custom flows.
    if row.pending_action == "custom_add":
        # Custom: name lives in row.pending_name
        product_name = row.pending_name or "Item"
    else:
        # Existing recommendation: pull from item_queue[cursor]
        item = row.item_queue[row.cursor] if row.cursor < len(row.item_queue) else {}
        product_name = item.get("name", "Item")

    stores = top_stores(session, limit=3)
    text, kb = render_store_prompt(product_name=product_name, qty=qty, stores=stores)
    # Transition: custom_qty → custom_store, qty → store
    if row.pending_prompt == "custom_qty":
        row.pending_prompt = "custom_store"
    else:
        row.pending_prompt = "store"
    _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)


def consume_typed_qty(session, chat_id: str, text: str,
                      message_id: int | None) -> None:
    """Called from webhook when row.pending_action is *_qty_typed and user sent text."""
    row = get_or_create_session(session, chat_id)
    try:
        qty = float(text.strip())
        if qty <= 0:
            raise ValueError
    except (ValueError, TypeError):
        send_telegram_message(
            chat_id, "Couldn't parse that as a number. Try again:",
        )
        return
    # Replay through handle_qty with the parsed number.
    row.pending_action = "custom_add" if row.pending_prompt == "custom_qty" else "add_detailed"
    handle_qty(session, chat_id, qty_arg=str(qty), message_id=message_id)
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_add_detailed or handle_qty"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): handle_add_detailed + handle_qty + typed-qty consumer"
```

---

## Task 13: `handle_store` — finalize add with qty+store

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_handle_store_inserts_with_qty_and_store_then_advances(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_store, handle_qty, handle_add_detailed,
        handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, Store, Purchase, ShoppingListItem, TelegramShoppingSession,
    )
    from datetime import datetime
    p1 = Product(name="Olive oil", category="pantry"); session.add(p1); session.flush()
    p2 = Product(name="Pepper", category="pantry"); session.add(p2); session.flush()
    s = Store(name="Costco"); session.add(s); session.flush()
    session.add(Purchase(store_id=s.id, total_amount=1.0,
                         date=datetime.utcnow(), transaction_type="purchase"))
    session.commit()

    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p1.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
            {"product_id": p2.id, "product_name": "Pepper", "category": "pantry",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()
    handle_qty(session, "abc", qty_arg="3", message_id=100); session.commit()

    handle_store(session, "abc", store_arg="costco", message_id=100); session.commit()

    items = session.query(ShoppingListItem).all()
    assert len(items) == 1
    assert items[0].quantity == 3.0
    assert items[0].preferred_store == "Costco"
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["added"] == 1
    assert row.pending_prompt == "item"


def test_handle_store_skip_inserts_without_store(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_store, handle_qty, handle_add_detailed,
        handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, ShoppingListItem, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()
    handle_qty(session, "abc", qty_arg="2", message_id=100); session.commit()

    handle_store(session, "abc", store_arg="skip", message_id=100); session.commit()

    item = session.query(ShoppingListItem).one()
    assert item.preferred_store is None
    assert item.quantity == 2.0


def test_handle_store_other_enters_typed_text_state(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_store, handle_qty, handle_add_detailed,
        handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()
    handle_qty(session, "abc", qty_arg="1", message_id=100); session.commit()

    handle_store(session, "abc", store_arg="other", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "store"
    assert row.pending_action == "add_detailed_store_typed"
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_store"`
Expected: FAIL.

- [ ] **Step 3: Implement `handle_store` + typed-store consumer**

Append to `src/backend/handle_shopping_walk.py`:

```python
def _resolve_store_slug(session, slug: str) -> str | None:
    """Map slug back to a Store.name. Returns None if no match."""
    from src.backend.initialize_database_schema import Store
    rows = session.query(Store.name).all()
    for (name,) in rows:
        if _slug_store(name) == slug:
            return name
    return None


def handle_store(session, chat_id: str, store_arg: str,
                 message_id: int | None) -> None:
    """User picked store (slug, 'skip', or 'other')."""
    row = get_or_create_session(session, chat_id)
    is_custom = (row.pending_prompt == "custom_store" or
                 (row.pending_action or "").startswith("custom_add"))

    if store_arg == "other":
        # Switch to typed-text store state.
        text = "Type the store name:"
        kb = {"inline_keyboard": [[{"text": "← Back", "callback_data": "shop:back"}]]}
        row.pending_action = "custom_add_store_typed" if is_custom else "add_detailed_store_typed"
        _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)
        return

    store_name = None if store_arg == "skip" else _resolve_store_slug(session, store_arg)
    qty = row.pending_qty or 1.0

    if is_custom:
        # Custom-add path: insert with product_id=NULL
        name = row.pending_name or "Item"
        insert_custom_item(
            session,
            name=name,
            category=row.current_category,
            quantity=qty,
            preferred_store=store_name,
        )
        stats = dict(row.stats or {})
        stats["custom_added"] = stats.get("custom_added", 0) + 1
        row.stats = stats
        # Clear custom state, return to CATEGORY_END.
        row.pending_name = None
        row.pending_qty = None
        row.pending_action = None
        next_cat = row.category_queue[0] if row.category_queue else None
        text, kb = render_category_end(
            category=row.current_category or "other",
            next_category=next_cat,
            stats=row.stats or {},
        )
        row.pending_prompt = "category_end"
        _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)
        return

    # Existing-recommendation path.
    if row.cursor >= len(row.item_queue):
        return
    item = row.item_queue[row.cursor]
    insert_recommendation(
        session,
        product_id=item.get("product_id"),
        name=item.get("name", "Item"),
        category=item.get("category"),
        quantity=qty,
        preferred_store=store_name,
    )
    stats = dict(row.stats or {})
    stats["added"] = stats.get("added", 0) + 1
    row.stats = stats
    row.pending_qty = None
    row.pending_action = None
    _advance_or_end_category(session, row, message_id)


def consume_typed_store(session, chat_id: str, text: str,
                        message_id: int | None) -> None:
    """Called from webhook when row.pending_action is *_store_typed and user sent text."""
    row = get_or_create_session(session, chat_id)
    store_name = (text or "").strip()
    if not store_name:
        send_telegram_message(chat_id, "Store name can't be empty. Try again:")
        return

    qty = row.pending_qty or 1.0
    is_custom = (row.pending_prompt == "custom_store" or
                 (row.pending_action or "").startswith("custom_add"))

    if is_custom:
        insert_custom_item(
            session,
            name=row.pending_name or "Item",
            category=row.current_category,
            quantity=qty,
            preferred_store=store_name,
        )
        stats = dict(row.stats or {})
        stats["custom_added"] = stats.get("custom_added", 0) + 1
        row.stats = stats
        row.pending_name = None
        row.pending_qty = None
        row.pending_action = None
        next_cat = row.category_queue[0] if row.category_queue else None
        text_out, kb = render_category_end(
            category=row.current_category or "other",
            next_category=next_cat,
            stats=row.stats or {},
        )
        row.pending_prompt = "category_end"
        _edit_telegram_message(chat_id, message_id, text_out, reply_markup=kb)
        return

    if row.cursor >= len(row.item_queue):
        return
    item = row.item_queue[row.cursor]
    insert_recommendation(
        session,
        product_id=item.get("product_id"),
        name=item.get("name", "Item"),
        category=item.get("category"),
        quantity=qty,
        preferred_store=store_name,
    )
    stats = dict(row.stats or {})
    stats["added"] = stats.get("added", 0) + 1
    row.stats = stats
    row.pending_qty = None
    row.pending_action = None
    _advance_or_end_category(session, row, message_id)
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_store"`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): handle_store + typed-store consumer (skip/known/other)"
```

---

## Task 14: `handle_skip` / `handle_have` / `handle_done`

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_handle_skip_advances_no_write(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_skip, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, ShoppingListItem, TelegramShoppingSession,
    )
    p1 = Product(name="Olive oil", category="pantry"); session.add(p1); session.flush()
    p2 = Product(name="Pepper", category="pantry"); session.add(p2); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p1.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
            {"product_id": p2.id, "product_name": "Pepper", "category": "pantry",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_skip(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["skipped"] == 1
    assert session.query(ShoppingListItem).count() == 0


def test_handle_have_advances_no_write(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_have, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, ShoppingListItem, TelegramShoppingSession,
    )
    p1 = Product(name="Olive oil", category="pantry"); session.add(p1); session.flush()
    p2 = Product(name="Pepper", category="pantry"); session.add(p2); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p1.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
            {"product_id": p2.id, "product_name": "Pepper", "category": "pantry",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_have(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.cursor == 1
    assert row.stats["already_have"] == 1
    assert session.query(ShoppingListItem).count() == 0


def test_handle_done_ends_walk_with_summary(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_done, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    handle_done(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.status == "done"
    assert row.pending_prompt is None
    assert any("Shopping plan complete" in t for t in edits)
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_skip or handle_have or handle_done"`
Expected: FAIL.

- [ ] **Step 3: Implement handlers**

Append to `src/backend/handle_shopping_walk.py`:

```python
def handle_skip(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    stats = dict(row.stats or {})
    stats["skipped"] = stats.get("skipped", 0) + 1
    row.stats = stats
    _advance_or_end_category(session, row, message_id)


def handle_have(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    stats = dict(row.stats or {})
    stats["already_have"] = stats.get("already_have", 0) + 1
    row.stats = stats
    _advance_or_end_category(session, row, message_id)


def handle_done(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    _end_walk(row, message_id)


def _end_walk(row, message_id: int | None) -> None:
    text, kb = render_summary(row.stats or {})
    _edit_telegram_message(row.chat_id, message_id, text, reply_markup=kb)
    row.status = "done"
    row.pending_prompt = None
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_skip or handle_have or handle_done"`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): handle_skip/have/done"
```

---

## Task 15: `handle_cat_done` — next category or end walk

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_handle_cat_done_loads_next_category(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_cat_done, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    pa = Product(name="Olive oil", category="pantry"); session.add(pa); session.flush()
    pb = Product(name="Milk", category="fridge"); session.add(pb); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": pa.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
            {"product_id": pb.id, "product_name": "Milk", "category": "fridge",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    # Simulate having reached category_end (pantry done).
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()

    handle_cat_done(session, "abc", message_id=100); session.commit()

    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.current_category == "fridge"
    assert row.pending_prompt == "item"
    assert row.cursor == 0
    assert len(row.item_queue) == 1


def test_handle_cat_done_ends_walk_when_no_more_categories(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_cat_done, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()

    handle_cat_done(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.status == "done"
    assert any("Shopping plan complete" in t for t in edits)
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_cat_done"`
Expected: FAIL.

- [ ] **Step 3: Implement `handle_cat_done`**

Append to `src/backend/handle_shopping_walk.py`:

```python
def handle_cat_done(session, chat_id: str, message_id: int | None) -> None:
    """User tapped → Next category or → Finish at CATEGORY_END."""
    row = get_or_create_session(session, chat_id)
    if not row.category_queue:
        _end_walk(row, message_id)
        return

    next_cat = row.category_queue[0]
    # Re-bucketize current recommendations (handles cases where shopping list
    # may have grown via web between categories; engine's
    # _filter_confirmed_shopping_recommendations excludes already-added items).
    recs = fetch_recommendations(session)
    _, items_by = bucketize_by_category(recs)
    bucket = items_by.get(next_cat, [])

    row.current_category = next_cat
    row.item_queue = bucket
    row.cursor = 0
    row.category_queue = [c for c in row.category_queue if c != next_cat]

    if not bucket:
        # Skip empty bucket and recurse.
        handle_cat_done(session, chat_id, message_id)
        return

    _render_current_item(row, message_id)
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_cat_done"`
Expected: PASS — 2 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): handle_cat_done — next category or end walk"
```

---

## Task 16: Custom-add flow (`handle_custom` + typed-name consumer)

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_handle_custom_transitions_to_custom_name(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_custom, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()

    handle_custom(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "custom_name"
    assert row.pending_action == "custom_add"


def test_consume_typed_name_transitions_to_custom_qty(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        consume_typed_name, handle_custom,
        handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append((t, reply_markup)),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()
    handle_custom(session, "abc", message_id=100); session.commit()

    consume_typed_name(session, "abc", "Bay Leaves", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "custom_qty"
    assert row.pending_name == "Bay Leaves"
    assert "Bay Leaves" in edits[-1][0]


def test_consume_typed_name_rejects_empty(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        consume_typed_name, handle_custom, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(t),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()
    handle_custom(session, "abc", message_id=100); session.commit()

    consume_typed_name(session, "abc", "   ", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "custom_name"  # stays in name state
    assert any("can't be empty" in t for t in sent)
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_custom or consume_typed_name"`
Expected: FAIL.

- [ ] **Step 3: Implement `handle_custom` + `consume_typed_name`**

Append to `src/backend/handle_shopping_walk.py`:

```python
def handle_custom(session, chat_id: str, message_id: int | None) -> None:
    """User tapped + Add custom item. Transition to typed-name state."""
    row = get_or_create_session(session, chat_id)
    row.pending_prompt = "custom_name"
    row.pending_action = "custom_add"
    row.pending_name = None
    row.pending_qty = None
    text, kb = render_custom_name_prompt()
    _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)


def consume_typed_name(session, chat_id: str, text: str,
                       message_id: int | None) -> None:
    """Webhook calls this when row.pending_prompt == 'custom_name' and user sent text."""
    row = get_or_create_session(session, chat_id)
    name = (text or "").strip()
    if not name:
        send_telegram_message(chat_id, "Name can't be empty. Try again:")
        return
    row.pending_name = name
    row.pending_prompt = "custom_qty"
    text_out, kb = render_custom_qty_prompt(product_name=name)
    _edit_telegram_message(chat_id, message_id, text_out, reply_markup=kb)
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_custom or consume_typed_name"`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): custom-add — handle_custom + typed-name consumer"
```

---

## Task 17: `handle_back` / `handle_cancel` / `handle_resume` / `handle_restart`

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_handle_back_from_qty_returns_to_item(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        handle_back, handle_add_detailed, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    handle_add_detailed(session, "abc", message_id=100); session.commit()

    handle_back(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "item"
    assert row.pending_action is None


def test_handle_cancel_marks_abandoned(session, monkeypatch):
    from src.backend.handle_shopping_walk import handle_cancel, start_walk
    from src.backend.initialize_database_schema import TelegramShoppingSession
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [],
    )
    start_walk(session, "abc"); session.commit()

    handle_cancel(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.status == "abandoned"
    assert any("ancel" in t for t in edits)


def test_handle_restart_resets_state(session, monkeypatch):
    from src.backend.handle_shopping_walk import handle_restart
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    row = TelegramShoppingSession(
        chat_id="abc", status="active", current_category="pantry",
        item_queue=[{"product_id": 1, "name": "X", "category": "pantry",
                     "reason_label": "Low stock"}],
        cursor=1, pending_prompt="item",
    )
    session.add(row); session.commit()

    handle_restart(session, "abc", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.cursor == 0
    assert row.current_category is None
    assert row.pending_prompt == "category"
    assert any("Plan shopping" in t for t in edits)


def test_handle_resume_re_renders_current(session, monkeypatch):
    from src.backend.handle_shopping_walk import handle_resume
    from src.backend.initialize_database_schema import TelegramShoppingSession
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    row = TelegramShoppingSession(
        chat_id="abc", status="active", current_category="pantry",
        item_queue=[{"product_id": 1, "name": "Olive oil", "category": "pantry",
                     "reason_label": "Low stock"}],
        cursor=0, pending_prompt="resume",
    )
    session.add(row); session.commit()

    handle_resume(session, "abc", message_id=100); session.commit()
    assert any("Olive oil" in t for t in edits)
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_prompt == "item"
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_back or handle_cancel or handle_resume or handle_restart"`
Expected: FAIL.

- [ ] **Step 3: Implement handlers**

Append to `src/backend/handle_shopping_walk.py`:

```python
def handle_back(session, chat_id: str, message_id: int | None) -> None:
    """← Back from sub-prompt. Mapping by current pending_prompt:
    qty → item, store → qty, custom_name → category_end, custom_qty → custom_name,
    custom_store → custom_qty.
    """
    row = get_or_create_session(session, chat_id)
    p = row.pending_prompt
    if p == "qty":
        row.pending_action = None
        _render_current_item(row, message_id)
    elif p == "store":
        # Re-render qty prompt
        item = row.item_queue[row.cursor] if row.cursor < len(row.item_queue) else {}
        text, kb = render_qty_prompt(item.get("name", "Item"))
        row.pending_prompt = "qty"
        _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)
    elif p == "custom_name":
        # Back from name typing → return to CATEGORY_END
        next_cat = row.category_queue[0] if row.category_queue else None
        text, kb = render_category_end(
            category=row.current_category or "other",
            next_category=next_cat,
            stats=row.stats or {},
        )
        row.pending_prompt = "category_end"
        row.pending_action = None
        _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)
    elif p == "custom_qty":
        text, kb = render_custom_name_prompt()
        row.pending_prompt = "custom_name"
        _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)
    elif p == "custom_store":
        text, kb = render_custom_qty_prompt(product_name=row.pending_name or "Item")
        row.pending_prompt = "custom_qty"
        _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)


def handle_cancel(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    row.status = "abandoned"
    row.pending_prompt = None
    _edit_telegram_message(chat_id, message_id, "Cancelled.")


def handle_resume(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    if not row.item_queue or row.cursor >= len(row.item_queue):
        start_walk(session, chat_id)
        return
    _render_current_item(row, message_id)


def handle_restart(session, chat_id: str, message_id: int | None) -> None:
    row = get_or_create_session(session, chat_id)
    reset_for_start_over(row)
    recs = fetch_recommendations(session)
    if not recs:
        row.status = "done"
        row.pending_prompt = None
        _edit_telegram_message(
            chat_id, message_id,
            "🎉 Nothing to suggest right now — shopping list looks good.",
        )
        return
    cat_queue, items_by = bucketize_by_category(recs)
    row.category_queue = cat_queue
    counts = [(c, len(items_by[c])) for c in cat_queue]
    text, kb = render_category_screen(counts)
    _edit_telegram_message(chat_id, message_id, text, reply_markup=kb)
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "handle_back or handle_cancel or handle_resume or handle_restart"`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): handle_back/cancel/resume/restart"
```

---

## Task 18: Dispatcher + stale-verb guard + idle timeout + typed-text router

**Files:**
- Modify: `src/backend/handle_shopping_walk.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_dispatch_routes_valid_shop_skip(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        dispatch_shop_callback, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    p2 = Product(name="Pepper", category="pantry"); session.add(p2); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [
            {"product_id": p.id, "product_name": "Olive oil", "category": "pantry",
             "reason": "low_stock"},
            {"product_id": p2.id, "product_name": "Pepper", "category": "pantry",
             "reason": "manual_low"},
        ],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()

    dispatch_shop_callback(session, "abc", "shop:skip", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.stats["skipped"] == 1


def test_dispatch_rejects_stale_verb(session, monkeypatch):
    from src.backend.handle_shopping_walk import (
        dispatch_shop_callback, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import Product
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    sent = []
    edits = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk._edit_telegram_message",
        lambda c, m, t, reply_markup=None: edits.append(t),
    )
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(t),
    )
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    # pending_prompt == 'item'. Send a qty verb → mismatch.

    dispatch_shop_callback(session, "abc", "shop:qty:3", message_id=100); session.commit()
    combined = " ".join(edits + sent)
    assert "stale" in combined.lower()


def test_dispatch_idle_session_auto_abandons(session, monkeypatch):
    from src.backend.handle_shopping_walk import dispatch_shop_callback
    from src.backend.initialize_database_schema import TelegramShoppingSession
    row = TelegramShoppingSession(
        chat_id="abc", status="active",
        current_category="pantry",
        item_queue=[{"product_id": 1, "name": "X", "category": "pantry",
                     "reason_label": "Low stock"}],
        cursor=0, pending_prompt="item",
    )
    session.add(row); session.commit()
    row.last_action_at = datetime.utcnow() - timedelta(minutes=45)
    session.commit()
    sent = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(t),
    )
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)

    dispatch_shop_callback(session, "abc", "shop:skip", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.status == "abandoned"
    assert any("timed out" in t.lower() for t in sent)


def test_dispatch_nudge_callbacks(session, monkeypatch):
    from src.backend.handle_shopping_walk import dispatch_nudge_callback
    from src.backend.initialize_database_schema import TelegramShoppingSession
    session.add(TelegramShoppingSession(chat_id="abc", status="done")); session.commit()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)

    dispatch_nudge_callback(session, "abc", "nudge:shop:mute", message_id=100)
    session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.nudge_muted_until is not None
    now = datetime.utcnow()
    assert row.nudge_muted_until > now + timedelta(days=6)
    assert row.nudge_muted_until < now + timedelta(days=8)

    dispatch_nudge_callback(session, "abc", "nudge:shop:later", message_id=100)
    session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.nudge_muted_until < now + timedelta(days=4)


def test_consume_typed_text_routes_by_state(session, monkeypatch):
    """Webhook helper picks the right typed-text consumer based on pending_prompt."""
    from src.backend.handle_shopping_walk import (
        consume_typed_text, handle_custom, handle_category, start_walk,
    )
    from src.backend.initialize_database_schema import (
        Product, TelegramShoppingSession,
    )
    p = Product(name="Olive oil", category="pantry"); session.add(p); session.flush()
    monkeypatch.setattr("src.backend.handle_shopping_walk._edit_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr("src.backend.handle_shopping_walk.send_telegram_message",
                        lambda *a, **kw: None)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.fetch_recommendations",
        lambda _s: [{"product_id": p.id, "product_name": "Olive oil",
                     "category": "pantry", "reason": "low_stock"}],
    )
    start_walk(session, "abc"); session.commit()
    handle_category(session, "abc", "pantry", message_id=100); session.commit()
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    row.cursor = len(row.item_queue)
    row.pending_prompt = "category_end"
    session.commit()
    handle_custom(session, "abc", message_id=100); session.commit()
    # pending_prompt should now be 'custom_name'

    handled = consume_typed_text(session, "abc", "Bay Leaves", message_id=100)
    session.commit()
    assert handled is True
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.pending_name == "Bay Leaves"
    assert row.pending_prompt == "custom_qty"


def test_consume_typed_text_returns_false_when_not_in_typed_state(session, monkeypatch):
    from src.backend.handle_shopping_walk import consume_typed_text
    from src.backend.initialize_database_schema import TelegramShoppingSession
    row = TelegramShoppingSession(chat_id="abc", status="active",
                                  pending_prompt="item")
    session.add(row); session.commit()
    handled = consume_typed_text(session, "abc", "anything", message_id=100)
    assert handled is False
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "dispatch_routes or dispatch_rejects or dispatch_idle or dispatch_nudge or consume_typed_text"`
Expected: FAIL.

- [ ] **Step 3: Implement dispatcher + typed-text router + nudge dispatcher**

Append to `src/backend/handle_shopping_walk.py`:

```python
_VERB_TO_EXPECTED_PROMPT: dict[str, "str | set[str] | None"] = {
    "cat":      "category",
    "add":      "item",
    "add+":     "item",
    "skip":     "item",
    "have":     "item",
    "done":     {"item", "category_end"},
    "qty":      {"qty", "custom_qty"},
    "store":    {"store", "custom_store"},
    "custom":   "category_end",
    "cat_done": "category_end",
    "back":     {"qty", "store", "custom_name", "custom_qty", "custom_store"},
    "cancel":   "category",
    "resume":   "resume",
    "restart":  {"resume", None, "category"},
}


def _matches_expected(prompt, expected) -> bool:
    if isinstance(expected, set):
        return prompt in expected
    return prompt == expected


def _rerender_current_prompt(session, row, message_id: int | None) -> None:
    """Send a fresh prompt matching row.pending_prompt."""
    p = row.pending_prompt
    if p == "category":
        recs = fetch_recommendations(session)
        cat_queue, items_by = bucketize_by_category(recs)
        counts = [(c, len(items_by[c])) for c in cat_queue]
        text, kb = render_category_screen(counts) if counts else (
            "🎉 Nothing to suggest right now — shopping list looks good.", {})
        send_telegram_message(row.chat_id, text, reply_markup=kb or None)
    elif p == "item":
        _render_current_item(row, None)  # editMessage with no msg_id sends instead
    elif p == "qty":
        item = row.item_queue[row.cursor] if row.cursor < len(row.item_queue) else {}
        text, kb = render_qty_prompt(item.get("name", "Item"))
        send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif p == "store":
        item = row.item_queue[row.cursor] if row.cursor < len(row.item_queue) else {}
        stores = top_stores(session, limit=3)
        text, kb = render_store_prompt(
            product_name=item.get("name", "Item"),
            qty=row.pending_qty or 1.0, stores=stores,
        )
        send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif p == "category_end":
        next_cat = row.category_queue[0] if row.category_queue else None
        text, kb = render_category_end(
            category=row.current_category or "other",
            next_category=next_cat, stats=row.stats or {},
        )
        send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif p == "custom_name":
        text, kb = render_custom_name_prompt()
        send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif p == "custom_qty":
        text, kb = render_custom_qty_prompt(product_name=row.pending_name or "Item")
        send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif p == "custom_store":
        stores = top_stores(session, limit=3)
        text, kb = render_store_prompt(
            product_name=row.pending_name or "Item",
            qty=row.pending_qty or 1.0, stores=stores,
        )
        send_telegram_message(row.chat_id, text, reply_markup=kb)
    elif p == "resume":
        total = len(row.item_queue)
        text, kb = render_resume(row.current_category or "other", row.cursor, total)
        send_telegram_message(row.chat_id, text, reply_markup=kb)
    # None or unknown: do nothing.


def dispatch_shop_callback(session, chat_id: str, data: str,
                           message_id: int | None) -> None:
    """Route an `shop:*` callback."""
    row = get_or_create_session(session, chat_id)
    if abandon_if_idle(row):
        send_telegram_message(chat_id, "Session timed out. /shopping to restart.")
        return

    parts = data.split(":", 2)
    if len(parts) < 2 or parts[0] != "shop":
        return
    verb = parts[1]
    arg = parts[2] if len(parts) == 3 else ""

    expected = _VERB_TO_EXPECTED_PROMPT.get(verb)
    if expected is not None and not _matches_expected(row.pending_prompt, expected):
        _edit_telegram_message(chat_id, message_id, "That button is stale. Showing current step:")
        _rerender_current_prompt(session, row, None)
        return

    if verb == "cat":
        handle_category(session, chat_id, arg, message_id)
    elif verb == "add":
        handle_add(session, chat_id, message_id)
    elif verb == "add+":
        handle_add_detailed(session, chat_id, message_id)
    elif verb == "qty":
        handle_qty(session, chat_id, arg, message_id)
    elif verb == "store":
        handle_store(session, chat_id, arg, message_id)
    elif verb == "skip":
        handle_skip(session, chat_id, message_id)
    elif verb == "have":
        handle_have(session, chat_id, message_id)
    elif verb == "done":
        handle_done(session, chat_id, message_id)
    elif verb == "custom":
        handle_custom(session, chat_id, message_id)
    elif verb == "cat_done":
        handle_cat_done(session, chat_id, message_id)
    elif verb == "back":
        handle_back(session, chat_id, message_id)
    elif verb == "cancel":
        handle_cancel(session, chat_id, message_id)
    elif verb == "resume":
        handle_resume(session, chat_id, message_id)
    elif verb == "restart":
        handle_restart(session, chat_id, message_id)


def dispatch_nudge_callback(session, chat_id: str, data: str,
                            message_id: int | None) -> None:
    """Route nudge:shop:yes / :later / :mute."""
    row = get_or_create_session(session, chat_id)
    if data == "nudge:shop:yes":
        _edit_telegram_message(chat_id, message_id, "Starting walk…")
        start_walk(session, chat_id)
    elif data == "nudge:shop:later":
        row.nudge_muted_until = datetime.utcnow() + timedelta(days=3)
        _edit_telegram_message(chat_id, message_id, "OK, I'll ask again in a few days.")
    elif data == "nudge:shop:mute":
        row.nudge_muted_until = datetime.utcnow() + timedelta(days=7)
        _edit_telegram_message(chat_id, message_id, "Muted for a week.")


_TYPED_STATES = {"custom_name", "custom_qty", "custom_store", "qty", "store"}


def consume_typed_text(session, chat_id: str, text: str,
                       message_id: int | None) -> bool:
    """Webhook helper: if the row is in a typed-text state, consume the message.

    Returns True if handled (caller should NOT route to receipt-photo flow).
    Returns False if the row isn't in a typed-text state (caller continues).
    """
    row = get_or_create_session(session, chat_id)
    p = row.pending_prompt
    if p not in _TYPED_STATES:
        return False

    if p == "custom_name":
        consume_typed_name(session, chat_id, text, message_id)
        return True
    if p in ("qty", "custom_qty"):
        action = row.pending_action or ""
        if action.endswith("_qty_typed"):
            consume_typed_qty(session, chat_id, text, message_id)
            return True
        return False
    if p in ("store", "custom_store"):
        action = row.pending_action or ""
        if action.endswith("_store_typed"):
            consume_typed_store(session, chat_id, text, message_id)
            return True
        return False
    return False
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v`
Expected: ALL PASS (every test from prior tasks plus these 6).

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_shopping_walk.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): dispatcher + nudge callbacks + typed-text router"
```

---

## Task 19: Wire `/shopping` + callbacks into webhook

**Files:**
- Modify: `src/backend/handle_telegram_messages.py`
- Modify: `tests/test_telegram_shopping_walk.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_telegram_shopping_walk.py`:

```python
def test_webhook_shopping_command_starts_walk(session, monkeypatch):
    import flask
    from src.backend.handle_telegram_messages import _handle_command
    called = []
    monkeypatch.setenv("TELEGRAM_SHOPPING_WALK_ENABLED", "1")
    import importlib
    import src.backend.handle_shopping_walk as m
    importlib.reload(m)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.start_walk",
        lambda s, chat_id: called.append(chat_id),
    )
    app = flask.Flask("test")
    with app.app_context():
        flask.g.db_session = session
        out = _handle_command("/shopping", chat_id="abc")
    assert called == ["abc"]
    assert out == "" or "abc" in (out or "")


def test_webhook_routes_shop_callback(session, monkeypatch):
    import flask
    from src.backend.handle_telegram_messages import _handle_callback_query
    called = []
    monkeypatch.setenv("TELEGRAM_SHOPPING_WALK_ENABLED", "1")
    import importlib
    import src.backend.handle_shopping_walk as m
    importlib.reload(m)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.dispatch_shop_callback",
        lambda s, c, d, mid: called.append((c, d, mid)),
    )
    monkeypatch.setattr(
        "src.backend.handle_telegram_messages._answer_callback_query",
        lambda _: None,
    )
    cb = {
        "id": "cb1",
        "data": "shop:cat:pantry",
        "from": {"id": 42},
        "message": {"chat": {"id": "abc"}, "message_id": 100},
    }
    app = flask.Flask("test")
    with app.app_context():
        flask.g.db_session = session
        _handle_callback_query(cb)
    assert called == [("abc", "shop:cat:pantry", 100)]


def test_webhook_routes_nudge_shop_callback(session, monkeypatch):
    import flask
    from src.backend.handle_telegram_messages import _handle_callback_query
    called = []
    monkeypatch.setenv("TELEGRAM_SHOPPING_WALK_ENABLED", "1")
    import importlib
    import src.backend.handle_shopping_walk as m
    importlib.reload(m)
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.dispatch_nudge_callback",
        lambda s, c, d, mid: called.append((c, d, mid)),
    )
    monkeypatch.setattr(
        "src.backend.handle_telegram_messages._answer_callback_query",
        lambda _: None,
    )
    cb = {
        "id": "cb2",
        "data": "nudge:shop:mute",
        "from": {"id": 42},
        "message": {"chat": {"id": "abc"}, "message_id": 100},
    }
    app = flask.Flask("test")
    with app.app_context():
        flask.g.db_session = session
        _handle_callback_query(cb)
    assert called == [("abc", "nudge:shop:mute", 100)]


def test_webhook_typed_text_routes_to_consume_typed_text(session, monkeypatch):
    """Inbound text while pending_prompt is a typed-state must NOT hit receipt flow."""
    import flask
    from src.backend.handle_telegram_messages import telegram_webhook
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setenv("TELEGRAM_SHOPPING_WALK_ENABLED", "1")
    import importlib
    import src.backend.handle_shopping_walk as m
    importlib.reload(m)
    consumed = []
    monkeypatch.setattr(
        "src.backend.handle_shopping_walk.consume_typed_text",
        lambda s, c, t, mid: (consumed.append((c, t, mid)), True)[1],
    )

    row = TelegramShoppingSession(
        chat_id="42", status="active", current_category="pantry",
        pending_prompt="custom_name", pending_action="custom_add",
    )
    session.add(row); session.commit()

    app = flask.Flask("test")
    app.register_blueprint(__import__("src.backend.handle_telegram_messages",
                                      fromlist=["telegram_bp"]).telegram_bp)
    with app.test_client() as client:
        with app.app_context():
            flask.g.db_session = session
            r = client.post("/telegram/webhook", json={
                "update_id": 1,
                "message": {
                    "message_id": 9, "chat": {"id": 42}, "text": "Bay Leaves",
                },
            })
            assert r.status_code == 200
    assert consumed and consumed[0] == ("42", "Bay Leaves", 9)
```

- [ ] **Step 2: Run test — fail**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "webhook_shopping or webhook_routes_shop or webhook_routes_nudge_shop or webhook_typed_text"`
Expected: FAIL.

- [ ] **Step 3: Modify `handle_telegram_messages.py`**

Three changes:

**Change A — `/shopping` branch in `_handle_command`**

Locate the existing `_handle_command(command: str, chat_id: str = "") -> str:` (added in the inventory walk PR). Add a `/shopping` branch right after the `/inventory` branch:

```python
    if cmd == "/shopping":
        from src.backend.handle_shopping_walk import is_walk_enabled, start_walk
        if not is_walk_enabled(chat_id):
            return "Shopping walk is not enabled for this chat."
        start_walk(g.db_session, chat_id)
        return ""
```

Also update the `/help` text to mention `/shopping`:

```python
        "/help": (
            "📸 Send a receipt photo or PDF → I'll extract items and update your inventory.\n"
            "📦 /inventory → Walk through stale items and update what's left\n"
            "🛒 /shopping → Walk through recommended shopping items\n"
            "📊 /status → Check system status\n"
            "❓ /help → Show this message"
        ),
```

**Change B — `shop:*` + `nudge:shop:*` routing in `_handle_callback_query`**

Right after the existing `inv:*` branch and BEFORE the existing `nudge:` branch (or insert a `nudge:shop:` branch ahead of the inventory `nudge:` branch — they're distinguishable by prefix), add:

```python
    if data.startswith("shop:"):
        from src.backend.handle_shopping_walk import (
            is_walk_enabled, dispatch_shop_callback,
        )
        if is_walk_enabled(chat_id):
            dispatch_shop_callback(g.db_session, chat_id, data, callback_message_id)
            g.db_session.commit()
        return jsonify({"status": "ok"}), 200

    if data.startswith("nudge:shop:"):
        from src.backend.handle_shopping_walk import (
            is_walk_enabled, dispatch_nudge_callback,
        )
        if is_walk_enabled(chat_id):
            dispatch_nudge_callback(g.db_session, chat_id, data, callback_message_id)
            g.db_session.commit()
        return jsonify({"status": "ok"}), 200
```

**Change C — typed-text consumer hook in `telegram_webhook`**

In the message-handling branch of `telegram_webhook` (around the existing `text.startswith("/")` block), insert a typed-text-state check BEFORE the photo/document fallback. Replace the block:

```python
    text = message.get("text", "")
    if text.startswith("/"):
        response_text = _handle_command(text, chat_id=chat_id)
        if response_text:
            send_telegram_message(chat_id, response_text)
        return jsonify({"status": "ok"}), 200
```

with:

```python
    text = message.get("text", "")
    if text.startswith("/"):
        response_text = _handle_command(text, chat_id=chat_id)
        if response_text:
            send_telegram_message(chat_id, response_text)
        return jsonify({"status": "ok"}), 200

    if text:
        try:
            from src.backend.handle_shopping_walk import (
                consume_typed_text, is_walk_enabled,
            )
            if is_walk_enabled(chat_id):
                if consume_typed_text(g.db_session, chat_id, text,
                                      int(message.get("message_id") or 0) or None):
                    g.db_session.commit()
                    return jsonify({"status": "ok"}), 200
        except Exception as e:
            logger.warning(f"shopping walk typed-text consume failed: {e}")
```

This consumes typed text ONLY when the chat is in a `custom_name`, custom-qty-typed, or custom-store-typed state. Otherwise (`consume_typed_text` returns False), the code falls through to the existing photo/document handling.

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py -v -k "webhook_shopping or webhook_routes_shop or webhook_routes_nudge_shop or webhook_typed_text"`
Expected: PASS — 4 tests.

Then run the full walk file + inventory file as regression check:

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py tests/test_telegram_inventory_walk.py -v 2>&1 | tail -10`
Expected: ALL PASS, no inventory regressions.

- [ ] **Step 5: Commit**

```bash
git add src/backend/handle_telegram_messages.py tests/test_telegram_shopping_walk.py
git commit -m "feat(telegram): wire /shopping + shop:* + nudge:shop:* + typed-text routing"
```

---

## Task 20: Nudge job + APScheduler registration + E2E test

**Files:**
- Create: `src/backend/shopping_nudge_job.py`
- Modify: `src/backend/check_inventory_thresholds.py`
- Create: `tests/test_shopping_nudge_job.py`
- Create: `tests/test_telegram_shopping_e2e.py`

- [ ] **Step 1: Write the failing nudge-job tests**

Create `tests/test_shopping_nudge_job.py`:

```python
"""Tests for the daily shopping nudge job."""
import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")


@pytest.fixture
def session(tmp_path):
    from src.backend.initialize_database_schema import (
        Base, create_db_engine, create_session_factory,
    )
    db = tmp_path / "n.db"
    eng = create_db_engine(f"sqlite:///{db}")
    Base.metadata.create_all(eng)
    SessionFactory = create_session_factory(eng)
    s = SessionFactory()
    yield s
    s.close()


def _seed_chat_with_recs(session, chat_id, n_recs):
    from src.backend.initialize_database_schema import (
        Product, Inventory, TelegramReceipt,
    )
    session.add(TelegramReceipt(
        telegram_user_id=chat_id, message_id="m1", image_path="/tmp/x", status="processed",
    ))
    for i in range(n_recs):
        p = Product(name=f"Item-{chat_id}-{i}", category="pantry")
        session.add(p); session.flush()
        inv = Inventory(product_id=p.id, quantity=0.0, manual_low=True, is_active_window=True)
        session.add(inv)
    session.commit()


def test_eligibility_skips_under_threshold(session, monkeypatch):
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=5)
    assert "abc" not in m.eligible_chat_ids(session)


def test_eligibility_includes_chat_with_8plus_recs(session, monkeypatch):
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    assert "abc" in m.eligible_chat_ids(session)


def test_eligibility_skips_muted_chat(session, monkeypatch):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    session.add(TelegramShoppingSession(
        chat_id="abc", status="done",
        nudge_muted_until=datetime.utcnow() + timedelta(days=2),
    ))
    session.commit()
    assert "abc" not in m.eligible_chat_ids(session)


def test_eligibility_skips_recently_nudged(session, monkeypatch):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    monkeypatch.setenv("SHOPPING_NUDGE_GAP_DAYS", "3")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    session.add(TelegramShoppingSession(
        chat_id="abc", status="done",
        last_nudge_sent_at=datetime.utcnow() - timedelta(days=2),
    ))
    session.commit()
    assert "abc" not in m.eligible_chat_ids(session)


def test_eligibility_skips_chat_with_active_walk(session, monkeypatch):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    session.add(TelegramShoppingSession(
        chat_id="abc", status="active",
        category_queue=["pantry"], current_category="pantry",
        item_queue=[{"product_id": 1}], cursor=0, pending_prompt="item",
    ))
    session.commit()
    assert "abc" not in m.eligible_chat_ids(session)


def test_run_daily_shopping_nudge_sends_and_records(session, monkeypatch):
    from src.backend.initialize_database_schema import TelegramShoppingSession
    monkeypatch.setenv("SHOPPING_NUDGE_ENABLED", "1")
    monkeypatch.setenv("SHOPPING_NUDGE_MIN_RECS", "8")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    sent = []
    monkeypatch.setattr(
        "src.backend.shopping_nudge_job.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append((c, t)),
    )

    m.run_daily_shopping_nudge(session); session.commit()
    assert len(sent) == 1
    row = session.query(TelegramShoppingSession).filter_by(chat_id="abc").one()
    assert row.last_nudge_sent_at is not None


def test_run_daily_shopping_nudge_respects_disable_flag(session, monkeypatch):
    monkeypatch.setenv("SHOPPING_NUDGE_ENABLED", "0")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    _seed_chat_with_recs(session, "abc", n_recs=10)
    sent = []
    monkeypatch.setattr(
        "src.backend.shopping_nudge_job.send_telegram_message",
        lambda c, t, reply_markup=None: sent.append(c),
    )
    m.run_daily_shopping_nudge(session); session.commit()
    assert sent == []


def test_register_daily_shopping_nudge_job_when_enabled(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler
    monkeypatch.setenv("SHOPPING_NUDGE_ENABLED", "1")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    sched = BackgroundScheduler()
    m.register_daily_shopping_nudge_job(sched)
    jobs = sched.get_jobs()
    assert any(j.id == "shopping_daily_nudge" for j in jobs)


def test_register_skips_when_disabled(monkeypatch):
    from apscheduler.schedulers.background import BackgroundScheduler
    monkeypatch.setenv("SHOPPING_NUDGE_ENABLED", "0")
    import importlib
    import src.backend.shopping_nudge_job as m
    importlib.reload(m)
    sched = BackgroundScheduler()
    m.register_daily_shopping_nudge_job(sched)
    jobs = sched.get_jobs()
    assert not any(j.id == "shopping_daily_nudge" for j in jobs)
```

- [ ] **Step 2: Run tests — fail**

Run: `./venv/bin/python -m pytest tests/test_shopping_nudge_job.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `shopping_nudge_job.py`**

Create `src/backend/shopping_nudge_job.py`:

```python
"""Daily proactive shopping nudge.

See docs/superpowers/specs/2026-05-14-telegram-shopping-walk-design.md §8.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from src.backend.handle_shopping_walk import (
    _bool_env, _csv_env, _int_env,
    bucketize_by_category, fetch_recommendations,
    render_nudge, send_telegram_message,
)

logger = logging.getLogger(__name__)

NUDGE_MIN_RECS = _int_env("SHOPPING_NUDGE_MIN_RECS", 8)
NUDGE_GAP_DAYS = _int_env("SHOPPING_NUDGE_GAP_DAYS", 3)


def _allowlist() -> set[str] | None:
    cs = _csv_env("TELEGRAM_AUTHORIZED_CHAT_IDS")
    return cs or None


def _candidate_chat_ids(session) -> set[str]:
    from src.backend.initialize_database_schema import TelegramReceipt
    allow = _allowlist()
    if allow:
        return allow
    rows = session.query(TelegramReceipt.telegram_user_id).distinct().all()
    return {r[0] for r in rows if r[0]}


def eligible_chat_ids(session) -> list[str]:
    from src.backend.initialize_database_schema import TelegramShoppingSession
    now = datetime.utcnow()
    out: list[str] = []
    recs = fetch_recommendations(session)
    rec_count = len(recs)
    if rec_count < NUDGE_MIN_RECS:
        return out
    for chat_id in _candidate_chat_ids(session):
        sess_row = (
            session.query(TelegramShoppingSession)
            .filter_by(chat_id=chat_id)
            .one_or_none()
        )
        if sess_row and sess_row.status == "active" and sess_row.item_queue:
            continue
        if sess_row and sess_row.nudge_muted_until:
            mute_until = sess_row.nudge_muted_until
            if mute_until.tzinfo is not None:
                mute_until = mute_until.replace(tzinfo=None)
            if mute_until > now:
                continue
        if sess_row and sess_row.last_nudge_sent_at:
            last_sent = sess_row.last_nudge_sent_at
            if last_sent.tzinfo is not None:
                last_sent = last_sent.replace(tzinfo=None)
            if last_sent > now - timedelta(days=NUDGE_GAP_DAYS):
                continue
        out.append(chat_id)
    return out


def run_daily_shopping_nudge(session) -> None:
    if not _bool_env("SHOPPING_NUDGE_ENABLED", False):
        logger.info("shopping nudges disabled via env")
        return

    from src.backend.initialize_database_schema import TelegramShoppingSession

    recs = fetch_recommendations(session)
    if len(recs) < NUDGE_MIN_RECS:
        return
    cat_queue, _items_by = bucketize_by_category(recs)
    rec_count = len(recs)
    category_count = len(cat_queue)

    for chat_id in eligible_chat_ids(session):
        text, kb = render_nudge(rec_count=rec_count, category_count=category_count)
        try:
            send_telegram_message(chat_id, text, reply_markup=kb)
        except Exception as e:
            logger.warning("shopping nudge send failed for %s: %s", chat_id, e)
            continue
        row = (
            session.query(TelegramShoppingSession)
            .filter_by(chat_id=chat_id)
            .one_or_none()
        )
        if row is None:
            row = TelegramShoppingSession(chat_id=chat_id, status="done")
            session.add(row); session.flush()
        row.last_nudge_sent_at = datetime.utcnow()


def register_daily_shopping_nudge_job(scheduler) -> None:
    """Register daily 09:30 nudge job. No-op when SHOPPING_NUDGE_ENABLED is off."""
    if not _bool_env("SHOPPING_NUDGE_ENABLED", False):
        return
    from apscheduler.triggers.cron import CronTrigger

    def _job_wrapper():
        from src.backend.initialize_database_schema import (
            create_db_engine, create_session_factory,
        )
        engine = create_db_engine()
        Session = create_session_factory(engine)
        sess = Session()
        try:
            run_daily_shopping_nudge(sess)
            sess.commit()
        except Exception:
            sess.rollback()
            logger.exception("daily shopping nudge job failed")
        finally:
            sess.close()

    scheduler.add_job(
        _job_wrapper,
        trigger=CronTrigger(hour=9, minute=30),
        id="shopping_daily_nudge",
        name="Daily Shopping Nudge",
        replace_existing=True,
    )
```

Then modify `src/backend/check_inventory_thresholds.py` `start_threshold_checker()`. Right after the inventory nudge registration block (added by the previous PR), add:

```python
    try:
        from src.backend.shopping_nudge_job import register_daily_shopping_nudge_job
        register_daily_shopping_nudge_job(_scheduler)
    except Exception:
        logger.exception("failed to register shopping nudge job")
```

- [ ] **Step 4: Run tests**

Run: `./venv/bin/python -m pytest tests/test_shopping_nudge_job.py -v`
Expected: PASS — 9 tests.

- [ ] **Step 5: Write E2E test**

Create `tests/test_telegram_shopping_e2e.py`:

```python
"""End-to-end webhook flow tests for the Telegram shopping walk."""
import os
from datetime import timedelta
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ["TELEGRAM_SHOPPING_WALK_ENABLED"] = "1"
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "")


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "se2e.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    import importlib
    import src.backend.handle_shopping_walk as m
    importlib.reload(m)
    # Reset cached engine in create_flask_application before building app.
    import src.backend.create_flask_application as cfa
    if hasattr(cfa, "_engine"):
        cfa._engine = None
    if hasattr(cfa, "_SessionFactory"):
        cfa._SessionFactory = None
    flask_app = cfa.create_app()
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    with app.test_client() as c:
        with app.app_context():
            yield c


@pytest.fixture
def make_session(app):
    from src.backend.initialize_database_schema import (
        Base, create_db_engine, create_session_factory,
    )
    eng = create_db_engine()
    Base.metadata.create_all(eng)
    SessionFactory = create_session_factory(eng)
    def _make():
        return SessionFactory()
    return _make


def _post(client, payload):
    return client.post("/telegram/webhook", json=payload)


def _post_command(client, chat_id, text):
    return _post(client, {
        "update_id": 1,
        "message": {
            "message_id": 1, "chat": {"id": chat_id}, "text": text,
        },
    })


def _post_callback(client, chat_id, data, message_id=100, cb_id="cb1"):
    return _post(client, {
        "update_id": 2,
        "callback_query": {
            "id": cb_id, "data": data,
            "from": {"id": 42},
            "message": {"chat": {"id": chat_id}, "message_id": message_id},
        },
    })


def _post_text(client, chat_id, text, message_id=2):
    return _post(client, {
        "update_id": 3,
        "message": {
            "message_id": message_id, "chat": {"id": chat_id}, "text": text,
        },
    })


@patch("src.backend.handle_telegram_messages.http_requests")
def test_full_shopping_walk_with_custom(http_mock, client, make_session):
    """End-to-end: /shopping → cat → +Add → cat_done → +custom → name → qty → store → done."""
    http_mock.post = MagicMock(return_value=MagicMock(status_code=200))

    from src.backend.initialize_database_schema import (
        Product, Inventory, ShoppingListItem, TelegramShoppingSession,
    )

    db = make_session()
    p = Product(name="Olive oil", category="pantry"); db.add(p); db.flush()
    inv = Inventory(product_id=p.id, quantity=0.0, manual_low=True, is_active_window=True)
    db.add(inv); db.commit()
    db.close()

    chat = "12345"
    assert _post_command(client, chat, "/shopping").status_code == 200
    assert _post_callback(client, chat, "shop:cat:pantry").status_code == 200
    assert _post_callback(client, chat, "shop:add").status_code == 200
    # Now in CATEGORY_END
    assert _post_callback(client, chat, "shop:custom").status_code == 200
    assert _post_text(client, chat, "Bay Leaves").status_code == 200
    # Now in custom_qty
    assert _post_callback(client, chat, "shop:qty:1").status_code == 200
    # Now in custom_store
    assert _post_callback(client, chat, "shop:store:skip").status_code == 200
    # Back at CATEGORY_END
    assert _post_callback(client, chat, "shop:cat_done").status_code == 200
    # Walk should be done now (only one category, finished)

    db = make_session()
    items = db.query(ShoppingListItem).all()
    names = sorted(i.name for i in items)
    assert "Olive oil" in names
    assert "Bay Leaves" in names

    sess = db.query(TelegramShoppingSession).filter_by(chat_id=chat).one()
    assert sess.stats.get("added") == 1
    assert sess.stats.get("custom_added") == 1
    assert sess.status == "done"
    db.close()


@patch("src.backend.handle_telegram_messages.http_requests")
def test_two_chats_isolated(http_mock, client, make_session):
    http_mock.post = MagicMock(return_value=MagicMock(status_code=200))
    from src.backend.initialize_database_schema import (
        Product, Inventory, TelegramShoppingSession,
    )
    db = make_session()
    p1 = Product(name="Olive oil", category="pantry"); db.add(p1); db.flush()
    db.add(Inventory(product_id=p1.id, quantity=0.0, manual_low=True, is_active_window=True))
    p2 = Product(name="Milk", category="fridge"); db.add(p2); db.flush()
    db.add(Inventory(product_id=p2.id, quantity=0.0, manual_low=True, is_active_window=True))
    db.commit(); db.close()

    _post_command(client, "alpha", "/shopping")
    _post_callback(client, "alpha", "shop:cat:pantry", message_id=200)
    _post_command(client, "bravo", "/shopping")
    _post_callback(client, "bravo", "shop:cat:fridge", message_id=300)

    db = make_session()
    a = db.query(TelegramShoppingSession).filter_by(chat_id="alpha").one()
    b = db.query(TelegramShoppingSession).filter_by(chat_id="bravo").one()
    assert a.current_category == "pantry"
    assert b.current_category == "fridge"
    db.close()
```

- [ ] **Step 6: Run E2E test**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_e2e.py -v`
Expected: PASS — 2 tests. If `create_flask_application` engine-cache reset variables have different names, adapt to match `tests/test_telegram_inventory_e2e.py` from the prior PR.

- [ ] **Step 7: Run full suite + commit**

Run: `./venv/bin/python -m pytest tests/test_telegram_shopping_walk.py tests/test_shopping_nudge_job.py tests/test_telegram_shopping_e2e.py tests/test_migration_032.py tests/test_telegram_inventory_walk.py tests/test_inventory_nudge_job.py -v 2>&1 | tail -10`
Expected: ALL PASS. Shopping side count should be ~50; combined with inventory tests ~130+.

Then commit final pieces:

```bash
git add src/backend/shopping_nudge_job.py src/backend/check_inventory_thresholds.py tests/test_shopping_nudge_job.py tests/test_telegram_shopping_e2e.py
git commit -m "feat(telegram): shopping nudge job + APScheduler 09:30 + E2E"
```

---

## Smoke-test checklist (manual, post-merge on prod)

Per memory `feedback_smoke_tests`, run before announcing done:

- [ ] On prod with `TELEGRAM_SHOPPING_WALK_ENABLED=1` + your chat_id in `_PILOT_CHATS`, send `/shopping`. Category screen appears with stale counts.
- [ ] Tap a category → first recommended item shown with reason label + last-bought info.
- [ ] `[+ Add]` → confirm row appears in `/shopping/list` web page with `source=telegram_shopping`, `quantity=1`, no store.
- [ ] `[+ Add w/ qty+store]` → pick qty `3` → pick top store → confirm row has `quantity=3` + `preferred_store=<store>`.
- [ ] On CATEGORY_END, tap `+ Add custom item` → type `Bay Leaves` → pick qty `1` → tap `[Skip store]` → confirm row with `product_id=NULL`, `name=Bay Leaves`.
- [ ] Skip + Already have → no DB inserts, stats increment correctly.
- [ ] Mid-walk `[✓ Done for now]` → summary shows correct counts.
- [ ] Send `/shopping` again within 1h → Resume offer with current cursor.
- [ ] Set `SHOPPING_NUDGE_ENABLED=1` + recreate backend → trigger manually:
  ```bash
  docker compose exec backend python -c "
  from src.backend.initialize_database_schema import create_db_engine, create_session_factory
  from src.backend.shopping_nudge_job import run_daily_shopping_nudge
  s = create_session_factory(create_db_engine())()
  run_daily_shopping_nudge(s); s.commit()
  "
  ```
  Expect nudge arrives.
- [ ] Tap Mute 7d → next manual nudge run skips that chat.
- [ ] Backup → restore round-trip preserves `telegram_shopping_session` rows.

---

## Self-Review notes (Part 2)

**Spec coverage:**
- §6 verb table → Tasks 11–18 ✅
- §6 typed-text states → Tasks 12, 13, 16, 18 ✅
- §7 error copy → Tasks 12, 13, 16 (qty/name validation), 18 (stale + idle) ✅
- §8 nudge job + cron → Task 20 ✅
- §9 module layout → All ✅
- §11 testing strategy → All tasks include tests ✅
- E2E → Task 20 ✅

**Placeholder scan:** None — every step has executable code.

**Type consistency:**
- `pending_prompt`: category, item, qty, store, custom_name, custom_qty, custom_store, category_end, resume, None — used consistently.
- `pending_action`: add_detailed, add_detailed_qty_typed, add_detailed_store_typed, custom_add, custom_add_qty_typed, custom_add_store_typed — all introduced in their respective tasks and referenced consistently downstream.
- Stats keys: added, skipped, already_have, custom_added — consistent across all handlers.
- Slug convention: `_slug_store` defined in Task 8, used by `render_store_prompt` and `_resolve_store_slug` (Task 13).
- All handler names referenced by `dispatch_shop_callback` in Task 18 are defined in Tasks 10–17.
