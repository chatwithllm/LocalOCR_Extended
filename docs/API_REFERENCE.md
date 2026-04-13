# API Reference

## Authentication

Browser users can authenticate with a local session cookie:

- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /auth/bootstrap-info`

App endpoints also accept a Bearer token for integrations and direct API access:

```
Authorization: Bearer <your-api-token>
```

Bootstrap browser login uses:

- email: `INITIAL_ADMIN_EMAIL` (defaults to `admin@localhost`)
- password: `INITIAL_ADMIN_PASSWORD`

If `INITIAL_ADMIN_PASSWORD` is blank, the first browser login falls back to `INITIAL_ADMIN_TOKEN`.

Unauthorized requests receive `401 Unauthorized`.

---

## Endpoints

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/auth/bootstrap-info` | None | Return safe bootstrap login hints for the first local admin login |
| POST | `/auth/login` | None | Create a browser session cookie |
| POST | `/auth/forgot-password` | None | Record a password reset request for an existing local account |
| POST | `/auth/logout` | Session or Bearer token | End the browser session |
| GET | `/auth/me` | Session or Bearer token | Return the current authenticated user |
| GET | `/auth/users` | Admin session or Bearer token | List household users |
| POST | `/auth/users` | Admin session or Bearer token | Create a household user |
| PUT | `/auth/users/{id}` | Admin session or Bearer token | Edit a user, reset password, or activate/deactivate the account |

### Health Check

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | None | Service health status |

**Response:**
```json
{"status": "healthy", "service": "localocr-extended-backend"}
```

---

### Receipt Management

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/telegram/webhook` | Telegram signature | Receive Telegram bot updates |
| POST | `/receipts/upload` | Session or Bearer token | Upload receipt image or PDF for OCR |
| GET | `/receipts/{id}` | Session or Bearer token | Retrieve receipt details |
| POST | `/receipts/{id}/reprocess` | Session or Bearer token | Re-run OCR for a stored receipt and refresh review data |
| POST | `/receipts/{id}/approve` | Session or Bearer token | Approve a review receipt and save it as a purchase |

#### POST `/receipts/upload`

Upload a receipt image or PDF for OCR processing.

**Request:** `multipart/form-data`
```bash
curl -X POST http://localhost:8080/receipts/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "image=@receipt.jpg"
```

The multipart field name remains `image` for both images and PDFs:

```bash
curl -X POST http://localhost:8080/receipts/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "image=@receipt.pdf"
```

**Response (200):**
```json
{
  "status": "processed",
  "source": "upload",
  "confidence": 0.92,
  "ocr_engine": "gemini",
  "purchase_id": 10,
  "data": {
    "store": "Whole Foods",
    "date": "2026-04-01",
    "items": [
      {"name": "Organic Milk", "quantity": 1, "unit_price": 3.20, "category": "dairy"}
    ],
    "total": 45.67
  }
}
```

#### POST `/receipts/{id}/reprocess`

Re-runs OCR for an existing stored receipt. Useful for older review receipts that do not yet have stored raw OCR JSON.

#### POST `/receipts/{id}/approve`

Approves a review receipt using either the stored OCR payload or an edited payload you submit.

```json
{
  "data": {
    "store": "Costco Wholesale",
    "date": "2026-04-01",
    "total": 361.02,
    "items": [
      {"name": "Spring Roll", "quantity": 1, "unit_price": 9.99, "category": "snacks"}
    ]
  }
}
```

---

### Product Snapshots

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/product-snapshots/upload` | Session or Bearer token | Upload a supporting product/item photo from shopping or receipt review |
| GET | `/product-snapshots` | Session or Bearer token | List product snapshots |
| GET | `/product-snapshots/{id}` | Session or Bearer token | Retrieve one snapshot record |
| GET | `/product-snapshots/{id}/image` | Session or Bearer token | Stream the stored snapshot image |
| GET | `/product-snapshots/review-queue` | Admin session or Bearer token | List pending/admin-review snapshots |
| PUT | `/product-snapshots/{id}/review` | Admin session or Bearer token | Review, archive, or link a snapshot to product context |

#### POST `/product-snapshots/upload`

Upload a supporting image for either a shopping-list item or a receipt item.

**Request:** `multipart/form-data`

Example shopping-item upload:

```bash
curl -X POST http://localhost:8090/product-snapshots/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "image=@item-photo.jpg" \
  -F "shopping_list_item_id=42" \
  -F "source_context=shopping"
```

Example receipt-item upload:

```bash
curl -X POST http://localhost:8090/product-snapshots/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "image=@receipt-item-photo.jpg" \
  -F "receipt_item_id=315" \
  -F "source_context=receipt_review"
```

**Response (201):**

```json
{
  "snapshot": {
    "id": 7,
    "status": "pending",
    "source_context": "shopping",
    "shopping_list_item_id": 42,
    "image_url": "/product-snapshots/7/image",
    "captured_at": "2026-04-11T17:30:57Z"
  }
}
```

#### PUT `/product-snapshots/{id}/review`

Admin review can archive a snapshot or attach it to an existing/new product workflow.

```json
{
  "status": "reviewed",
  "resolved_name": "Avocado Oil",
  "resolved_category": "condiments",
  "product_id": 18
}
```

---

### Product Catalog

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/products` | Session or Bearer token | List all products (paginated) |
| GET | `/products/search?q=milk` | Session or Bearer token | Search products |
| POST | `/products/create` | Session or Bearer token | Add new product |
| PUT | `/products/{id}/update` | Session or Bearer token | Update product |
| DELETE | `/products/{id}` | Session or Bearer token | Remove product |

---

### Inventory

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/inventory` | Session or Bearer token | List current inventory |
| POST | `/inventory/add-item` | Session or Bearer token | Add item with quantity |
| PUT | `/inventory/{id}/consume` | Session or Bearer token | Decrease quantity by 1 |
| PUT | `/inventory/{id}/update` | Session or Bearer token | Set quantity directly |
| DELETE | `/inventory/{id}` | Session or Bearer token | Remove from inventory |

#### GET `/inventory`

**Response:**
```json
{
  "count": 2,
  "inventory": [
    {
      "id": 1,
      "product_id": 1,
      "product_name": "Milk",
      "category": "dairy",
      "quantity": 2.0,
      "location": "Fridge",
      "threshold": 1.0,
      "is_low": false
    }
  ]
}
```

#### POST `/inventory/add-item`

```json
{
  "product_id": 1,
  "quantity": 2.0,
  "location": "Fridge"
}
```

---

### Analytics

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/analytics/spending?period=monthly` | Session or Bearer token | Spending by period |
| GET | `/analytics/spending?category=dairy` | Session or Bearer token | Spending by category |
| GET | `/analytics/price-history?product_id=1` | Session or Bearer token | Price trends |
| GET | `/analytics/deals-captured?months=1` | Session or Bearer token | Savings from deals |
| GET | `/analytics/store-comparison` | Session or Bearer token | Cross-store price comparison |

#### GET `/analytics/spending?period=monthly`

**Response:**
```json
{
  "period": "monthly",
  "months_back": 6,
  "grand_total": 83.48,
  "spending_by_period": {
    "2025-11": {
      "total": 83.48,
      "count": 1
    }
  },
  "category_breakdown": {
    "snacks": {
      "total": 7.44,
      "count": 2
    }
  }
}
```

---

### Budget

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/budget/set-monthly` | Session or Bearer token | Set monthly budget |
| GET | `/budget/status` | Session or Bearer token | Budget vs actual spending |

#### POST `/budget/set-monthly`

```json
{
  "month": "2026-04",
  "budget_amount": 600.00
}
```

---

### Recommendations

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/recommendations` | Session or Bearer token | Get current recommendations |

---

### Shopping List

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/shopping-list?status=open` | Session or Bearer token | List shopping list items |
| POST | `/shopping-list/items` | Session or Bearer token | Add a shopping list item |
| PUT | `/shopping-list/items/{id}` | Session or Bearer token | Update shopping list item details or status |
| DELETE | `/shopping-list/items/{id}` | Session or Bearer token | Delete a shopping list item |

---

## MQTT Topics

| Topic | Direction | Payload |
|-------|-----------|---------|
| `home/grocery/inventory/{product_id}` | Backend → HA | `{product_id, name, quantity, location, updated_by, timestamp}` |
| `home/grocery/alerts/low_stock` | Backend → HA | `{product_id, name, current, threshold, alert_type}` |
| `home/grocery/alerts/budget` | Backend → HA | `{budget_amount, spent, percentage, alert_type}` |
| `home/grocery/recommendations/daily` | Backend → HA | `{recommendations: [...], count, timestamp}` |

### Home Assistant Discovery Topics

The app also publishes MQTT discovery config payloads for Home Assistant auto-discovery.

| Topic | Purpose |
|-------|---------|
| `homeassistant/sensor/grocery_inventory_{product_id}/config` | Per-product inventory quantity sensor |
| `homeassistant/sensor/grocery_recommendations_count/config` | Recommendations count sensor |
| `homeassistant/sensor/grocery_budget_alert/config` | Budget alert sensor |
| `homeassistant/sensor/grocery_low_stock_alert/config` | Low-stock alert sensor |

Related env vars:

- `MQTT_DISCOVERY_ENABLED`
- `HOME_ASSISTANT_DISCOVERY_PREFIX`

---

## Error Responses

| Code | Meaning |
|------|---------|
| 400 | Bad request — missing or invalid parameters |
| 401 | Unauthorized — missing or invalid session/token |
| 403 | Forbidden — insufficient permissions |
| 404 | Not found — resource doesn't exist |
| 500 | Internal server error |
| 501 | Not implemented — endpoint stub not yet built |
