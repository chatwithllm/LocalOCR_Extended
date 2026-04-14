# Multi-Model Selection Architecture

A repo-aware design guide for adding per-user AI model selection to `LocalOCR Extended`.

This version is intentionally written against the current codebase, not a generic Flask starter. It assumes:

- Flask blueprints registered from [src/backend/create_flask_application.py](/Users/assistant/.gemini/antigravity/LocalOCR_Extended/src/backend/create_flask_application.py)
- SQLAlchemy models initialized in [src/backend/initialize_database_schema.py](/Users/assistant/.gemini/antigravity/LocalOCR_Extended/src/backend/initialize_database_schema.py)
- auth via `require_auth` and `require_write_access`
- existing OCR entry points in:
  - [src/backend/handle_receipt_upload.py](/Users/assistant/.gemini/antigravity/LocalOCR_Extended/src/backend/handle_receipt_upload.py)
  - [src/backend/extract_receipt_data.py](/Users/assistant/.gemini/antigravity/LocalOCR_Extended/src/backend/extract_receipt_data.py)
- current provider integrations already present for Gemini, OpenAI, and Ollama
- the browser UI living directly in [src/frontend/index.html](/Users/assistant/.gemini/antigravity/LocalOCR_Extended/src/frontend/index.html)

---

## Decision Summary

The original multi-model idea is solid, but the implementation should follow a few repo-specific rules:

- keep the current receipt upload and reprocess flow intact
- add a model registry instead of hardcoding provider selection in environment variables
- store active model selection per user
- route inference through one normalized provider dispatcher
- support OpenRouter as a first-class provider alongside Gemini, OpenAI, Ollama, and Anthropic
- keep environment-based fallback behavior so the app still works when no user model is selected
- separate model catalog metadata from credential handling
- build this in phases so the app gains value early without requiring the full purchase/admin stack on day one

Bottom line: this feature should extend the current OCR architecture, not replace it.

---

## 1. Product Goal

Allow each authenticated user to choose which AI model processes their receipts and OCR jobs.

Target providers:

- OpenAI
- Anthropic
- Google Gemini
- Ollama
- OpenRouter

Core requirements:

- admin-managed model registry
- optional per-user unlock/purchase support
- one active model per user
- one unified inference router
- compatibility with images and PDFs
- backend-enforced access and availability checks

---

## 2. Repo-Specific Constraints

This app already has a strong structure. The safest implementation is the one that fits what is already here.

### Backend constraints

- request auth is enforced with `require_auth` and `require_write_access`, not `login_required`
- backend modules are organized by responsibility and exposed as blueprints
- schema changes belong in `initialize_database_schema.py` plus the repo’s migration/bootstrap path

### OCR constraints

The OCR pipeline already supports:

- direct upload processing
- receipt reprocessing
- image files
- PDF files
- provider-specific extraction modules

That means the model router cannot assume the input is always raw image bytes.

### Frontend constraints

- the current UI is not a separate React app
- new model-selection UI should be integrated into `index.html` and current JS helpers
- visual treatment should match the app’s current dark interface

### Design implication

Do not build this as a parallel mini-framework.

Implement it as a repo-native extension that threads model selection through the existing upload and reprocess workflow.

---

## 3. Recommended Schema

The original draft used very generic table names like `models` and `user_models`.

For this repo, I recommend more explicit names:

- `ai_model_configs`
- `user_ai_model_access`

And one new nullable field on `users`:

- `active_ai_model_config_id`

### Why these names

`models` is too generic in a codebase that already has many domain models and ORM classes. Explicit names reduce confusion during future maintenance and migrations.

### Recommended `ai_model_configs` shape

```python
class AIModelConfig(Base):
    __tablename__ = "ai_model_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)                # "GPT-4o", "Gemini Flash", "Claude Sonnet"
    provider = Column(String(40), nullable=False)             # openai, anthropic, gemini, ollama, openrouter
    model_string = Column(String(200), nullable=False)        # provider-native model id
    description = Column(Text, nullable=True)
    price_tier = Column(String(20), nullable=False, default="free")
    is_enabled = Column(Boolean, nullable=False, default=True)
    is_visible = Column(Boolean, nullable=False, default=True)
    credential_mode = Column(String(20), nullable=False, default="env")
    api_key_encrypted = Column(Text, nullable=True)
    base_url = Column(String(255), nullable=True)
    supports_vision = Column(Boolean, nullable=False, default=True)
    supports_pdf = Column(Boolean, nullable=False, default=False)
    supports_json_mode = Column(Boolean, nullable=False, default=False)
    supports_image_input = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=100)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### Recommended `credential_mode` values

- `env`
  Use environment-backed credentials already configured for the deployment.
- `stored_key`
  Use an encrypted key stored on the model row.
- `no_key_required`
  For local or unauthenticated runtimes such as some Ollama deployments.

This is more flexible than assuming every model row always owns a raw API key.

### Recommended `user_ai_model_access` shape

```python
class UserAIModelAccess(Base):
    __tablename__ = "user_ai_model_access"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    model_config_id = Column(Integer, ForeignKey("ai_model_configs.id"), nullable=False)
    unlocked_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

Add a uniqueness constraint on:

- `user_id`
- `model_config_id`

### Recommended addition to `User`

```python
active_ai_model_config_id = Column(
    Integer,
    ForeignKey("ai_model_configs.id"),
    nullable=True,
)
```

### Free model rule

Do not create unlock rows for every free model.

Instead:

- treat `price_tier == "free"` as implicitly unlocked
- only store access rows for paid, granted, or expiring model access

---

## 4. Provider Capability Metadata

This is the most important addition I would strongly recommend.

Do not assume every model can do the same work.

Across OpenAI, Anthropic, Gemini, Ollama, and OpenRouter, models vary in support for:

- image understanding
- PDF handling
- structured JSON output
- token limits
- latency and cost

That is why capability flags belong on `ai_model_configs`.

At minimum, store:

- `supports_vision`
- `supports_pdf`
- `supports_json_mode`
- `supports_image_input`

Without these flags, users will be able to select models that look available in the UI but cannot process the file type the app is about to send.

---

## 5. Credentials And Security

### Strong recommendation

Do not make per-row stored API keys the only credential mechanism.

Use a layered strategy:

- environment-backed credentials for normal deployments
- optional encrypted stored keys for admin-managed advanced setups
- no-key mode for local runtimes such as Ollama

### API key handling

If `credential_mode = stored_key`:

- store encrypted ciphertext, not plaintext
- use an app-level encryption secret from environment configuration
- decrypt only immediately before dispatch
- never return decrypted keys in admin responses

### Access control

All access decisions must be enforced server-side.

Do not trust:

- localStorage state
- frontend `unlocked` flags
- client-submitted `model_id` values without validation

### Model availability checks

Before a model can be selected or used, the backend should verify:

- the model exists
- `is_enabled` is true
- the model is visible or otherwise accessible
- the user has access if the tier is not free
- required credentials are available
- the model supports the file type being processed

---

## 6. Recommended Routes

Keep the original spirit of the API, but implement it using this repo’s existing blueprint and auth style.

### User-facing routes

- `GET /api/models`
- `POST /api/models/select`
- optional later: `POST /api/models/unlock`

### `GET /api/models`

This route should return visible models together with user-specific state.

Suggested response shape:

```json
{
  "models": [
    {
      "id": 1,
      "name": "Gemini Flash",
      "provider": "gemini",
      "description": "Fast OCR processing",
      "price_tier": "free",
      "is_enabled": true,
      "unlocked": true,
      "active": true,
      "supports_vision": true,
      "supports_pdf": true
    }
  ]
}
```

### `POST /api/models/select`

This route should:

- validate the chosen model
- verify user access
- verify credentials/capability availability
- persist selection to `current_user.active_ai_model_config_id`
- return the saved selection

### Recommended admin routes

- `GET /api/admin/models`
- `POST /api/admin/models`
- `PATCH /api/admin/models/<id>`
- optional later: credential rotation or disable endpoints

These routes should use the repo’s current auth/admin patterns instead of introducing a generic `@admin_required` abstraction from another stack.

---

## 7. Unified Provider Router

The original routing idea is correct, but the function contract should be richer.

### Do not use this as the long-term contract

```python
route_inference(prompt, image_bytes, user_selected_model_id) -> str
```

That is too narrow for this app because the app already handles:

- PDFs
- receipt reprocessing from stored assets
- provider-specific fallbacks
- extraction metadata that is useful for debugging and usage tracking

### Recommended router contract

```python
def route_inference(
    *,
    prompt: str,
    file_bytes: bytes,
    mime_type: str,
    model_config_id: int | None = None,
    options: dict | None = None,
) -> dict:
    """
    Returns a normalized provider result object.
    """
```

### Recommended normalized result shape

```python
{
    "provider": "openrouter",
    "model_string": "google/gemini-2.0-flash",
    "raw_text": "...",
    "usage": {...},            # when provider returns it
    "finish_reason": "...",    # when available
    "latency_ms": 812,
    "response_meta": {...},    # provider-specific debug details
}
```

This gives the app better observability and leaves room for future usage tracking or billing analysis.

### Resolution order

Recommended model resolution priority:

1. explicit `model_config_id` from the request
2. `current_user.active_ai_model_config_id`
3. existing environment/provider fallback behavior

That keeps the new system additive and backwards-compatible.

---

## 8. Provider-Specific Notes

### OpenAI

- reuse the current OpenAI integration patterns already present in the repo
- keep transport behavior aligned with the existing receipt extraction layer

### Anthropic

- add support explicitly rather than assuming OpenAI-compatible transport
- verify exact vision-capable model names before enabling them in the registry

### Gemini

- align credential lookup with the current app’s Gemini environment conventions
- avoid introducing a second conflicting key convention unless the app is intentionally standardized later

### Ollama

- treat many Ollama model rows as `credential_mode = no_key_required`
- allow `base_url` override per row so different deployments can be targeted cleanly

### OpenRouter

This should be supported as a first-class provider, not hidden inside OpenAI.

Recommended behavior:

- `provider = "openrouter"`
- default `base_url = "https://openrouter.ai/api/v1"`
- use OpenAI-compatible transport where appropriate
- support optional request headers such as:
  - `HTTP-Referer`
  - `X-Title`

Important note:

- OpenRouter exposes many upstream models with different capabilities, so capability flags on `ai_model_configs` matter even more here

---

## 9. Receipt Flow Integration

This is where the generic version needed the most adjustment.

### Do not replace the current receipt flow

Instead:

- thread `model_config_id` through `POST /receipts/upload`
- thread `model_config_id` through `POST /receipts/<id>/reprocess`
- resolve the active model early in the request
- pass provider/model metadata into the extraction layer

### Recommended extraction integration

The extraction layer should receive:

- selected model config
- provider name
- model string
- file mime type

Then dispatch through the unified router.

### Recommended persistence for audit/debug

Where practical, store on the receipt or processing metadata:

- provider used
- model string used
- model config id used

This will make:

- troubleshooting
- reprocessing
- usage analysis
- support debugging

much easier later.

### Important compatibility rule

If no user model is selected, the app should continue to work exactly as it does today by using existing provider/environment defaults.

---

## 10. Frontend Recommendations

The frontend should feel native to this app rather than imported from a different stack.

### Recommended UX

Phase 1:

- a compact selector near the receipt upload and processing controls
- a visible active-model label
- a model picker modal or dropdown

Phase 2:

- richer cards or dropdown entries with:
  - provider badge
  - price tier
  - locked/unlocked state
  - capability tags such as `Vision`, `PDF`, `Local`, or `Premium`

### What the selector should show

- name
- provider
- short description
- price tier
- locked/unlocked state
- active state

### Persistence behavior

Keep both:

- backend active-model persistence
- localStorage cache for fast startup and UI continuity

But the backend remains the source of truth.

### Important repo-specific note

Do not assume a standalone React component system.

This work should integrate into the current `index.html` structure and existing fetch/UI helpers.

---

## 11. Phased Rollout Recommendation

I do not recommend implementing every piece in one pass.

### Phase 1: internal registry and selection

Implement:

- `ai_model_configs`
- `users.active_ai_model_config_id`
- `GET /api/models`
- `POST /api/models/select`
- unified provider router
- upload/reprocess wiring

Keep access simple:

- enabled models only
- free models only
- no purchase flow yet

### Phase 2: user entitlements and unlocks

Implement:

- `user_ai_model_access`
- locked-model handling
- upgrade/unlock CTA in UI

### Phase 3: admin management

Implement:

- admin CRUD for model configs
- enable/disable toggles
- visibility controls
- credential mode controls
- optional encrypted stored-key management

### Phase 4: capability, usage, and cost tracking

Implement:

- capability-driven UI filtering
- usage capture from provider responses
- optional per-request cost estimates
- optional quotas or spend tracking

This phased approach gives the app useful model selection early while keeping risk controlled.

---

## 12. Recommended First Implementation Scope

If we want the safest and highest-value first version, I recommend building this exact subset first:

- add `ai_model_configs`
- add `active_ai_model_config_id` to `users`
- expose `GET /api/models`
- expose `POST /api/models/select`
- implement unified provider routing for:
  - Gemini
  - OpenAI
  - Ollama
  - OpenRouter
- leave Anthropic scaffolded but optional if time is tight
- thread model selection through:
  - `/receipts/upload`
  - `/receipts/<id>/reprocess`
- keep environment fallback behavior

That scope is small enough to implement safely and large enough to prove the architecture.

---

## 13. Bottom-Line Recommendation

This architecture direction is good, but it should be grounded in how `LocalOCR Extended` already works.

My recommended implementation choices are:

- use repo-native SQLAlchemy models in `initialize_database_schema.py`
- use repo-native auth patterns from `create_flask_application.py`
- avoid generic table names like `models`
- separate model catalog metadata from credential strategy
- design the inference router for both images and PDFs
- treat OpenRouter as a first-class provider with OpenAI-compatible transport
- preserve current environment fallback behavior
- phase the rollout instead of coupling selection, purchases, admin UI, and accounting into one release

If implemented this way, multi-model support will fit the current app cleanly, remain backward-compatible, and be flexible enough for future pricing, provider expansion, and user-level entitlements.
