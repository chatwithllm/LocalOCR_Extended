"""Admin-triggered image backfill: list candidates, pick provider, run jobs.

Async pattern: POST /run spawns a thread, returns job_id. UI polls
/jobs/<id> for live progress. Job state held in module-level dict —
cleared 1 hour after completion. Acceptable loss on container restart
because the cron job picks up where the admin run left off.

Endpoints (all require admin):
  GET  /api/admin/image-backfill/providers
  GET  /api/admin/image-backfill/candidates?limit=100
  POST /api/admin/image-backfill/run        body: {product_ids:[], provider:"auto|gemini|openai"}
  GET  /api/admin/image-backfill/jobs/<id>
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date as _date, datetime, timedelta, timezone
from uuid import uuid4

from flask import Blueprint, g, jsonify, request

from src.backend.backfill_product_images import (
    _PROVIDER_COST_USD, _is_meaningful_product, find_products_needing_images,
)
from src.backend.create_flask_application import require_auth
from src.backend.fetch_product_image import (
    DEFAULT_PROVIDER_CHAIN, available_providers, fetch_product_image,
    model_for_provider,
)
from src.backend.image_backfill_schedule import load_schedule, save_schedule
from src.backend.initialize_database_schema import (
    Product, ProductSnapshot, create_db_engine, create_session_factory,
)
from src.backend.manage_authentication import is_admin
from src.backend.manage_product_snapshots import get_snapshot_root


logger = logging.getLogger(__name__)

image_backfill_bp = Blueprint(
    "image_backfill", __name__, url_prefix="/api/admin/image-backfill",
)

# job_id -> {status, total, fetched, failed, items, providers_used, started_at, finished_at}
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 3600  # cleanup after 1h


def _admin_or_403():
    user = getattr(g, "current_user", None)
    if not user or not is_admin(user):
        return None, (jsonify({"error": "Admin access required"}), 403)
    return user, None


def _gc_jobs() -> None:
    """Drop finished jobs older than TTL. Called on every poll."""
    cutoff = time.time() - _JOB_TTL_SECONDS
    with _JOBS_LOCK:
        stale = [jid for jid, j in _JOBS.items()
                 if j.get("finished_at_ts") and j["finished_at_ts"] < cutoff]
        for jid in stale:
            _JOBS.pop(jid, None)


@image_backfill_bp.route("/providers", methods=["GET"])
@require_auth
def list_providers():
    _, error = _admin_or_403()
    if error:
        return error
    avail = available_providers()
    return jsonify({
        "providers": [
            {"id": p, "available": p in avail, "default_chain_position": i}
            for i, p in enumerate(DEFAULT_PROVIDER_CHAIN)
        ],
        "auto_chain": list(DEFAULT_PROVIDER_CHAIN),
    }), 200


@image_backfill_bp.route("/candidates", methods=["GET"])
@require_auth
def list_candidates():
    _, error = _admin_or_403()
    if error:
        return error
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 500))
    except (TypeError, ValueError):
        limit = 100
    products = find_products_needing_images(g.db_session, max_products=limit)
    return jsonify({
        "candidates": [
            {
                "id": p.id,
                "name": p.display_name or p.name,
                "category": p.category,
                "last_attempt_at": (p.last_image_fetch_attempt_at.isoformat()
                                    if p.last_image_fetch_attempt_at else None),
            }
            for p in products
        ],
        "count": len(products),
    }), 200


def _run_admin_job(job_id: str, product_ids: list[int], provider: str) -> None:
    """Background worker: opens its own DB session, fetches+persists each item."""
    engine = create_db_engine()
    SessionFactory = create_session_factory(engine)
    session = SessionFactory()
    try:
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "running"

        for pid in product_ids:
            product = session.query(Product).filter_by(id=pid).first()
            if not product:
                with _JOBS_LOCK:
                    _JOBS[job_id]["items"].append({
                        "id": pid, "name": None, "result": "not_found",
                        "provider_used": None,
                    })
                    _JOBS[job_id]["failed"] += 1
                continue

            name = (product.display_name or product.name or "").strip()
            if not _is_meaningful_product(product):
                with _JOBS_LOCK:
                    _JOBS[job_id]["items"].append({
                        "id": pid, "name": name, "result": "filtered_junk",
                        "provider_used": None,
                    })
                    _JOBS[job_id]["failed"] += 1
                product.last_image_fetch_attempt_at = datetime.now(timezone.utc)
                session.commit()
                continue

            try:
                data, prov_used = fetch_product_image(
                    name, product.category, provider=provider,
                )
            except Exception as exc:
                logger.exception("admin backfill fetch raised for %s", pid)
                data, prov_used = None, None

            now = datetime.now(timezone.utc)
            if data:
                year_month = now.strftime("%Y/%m")
                ts = now.strftime("%Y%m%d_%H%M%S")
                fname = f"{ts}_{uuid4().hex[:8]}.jpg"
                save_dir = get_snapshot_root() / year_month
                save_dir.mkdir(parents=True, exist_ok=True)
                save_path = save_dir / fname
                save_path.write_bytes(data)
                session.add(ProductSnapshot(
                    product_id=product.id,
                    source_context="auto_fetch",
                    status="auto",
                    image_path=str(save_path),
                    captured_at=now,
                    notes=json.dumps({
                        "provider": prov_used,
                        "model": model_for_provider(prov_used),
                        "cost_usd": _PROVIDER_COST_USD.get(prov_used, 0.0),
                    }),
                ))
                with _JOBS_LOCK:
                    _JOBS[job_id]["items"].append({
                        "id": pid, "name": name, "result": "fetched",
                        "provider_used": prov_used,
                    })
                    _JOBS[job_id]["fetched"] += 1
                    if prov_used:
                        pu = _JOBS[job_id]["providers_used"]
                        pu[prov_used] = pu.get(prov_used, 0) + 1
            else:
                with _JOBS_LOCK:
                    _JOBS[job_id]["items"].append({
                        "id": pid, "name": name, "result": "failed",
                        "provider_used": None,
                    })
                    _JOBS[job_id]["failed"] += 1

            product.last_image_fetch_attempt_at = now
            session.commit()
    except Exception as exc:
        logger.exception("admin backfill job %s crashed", job_id)
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "error"
            _JOBS[job_id]["error"] = str(exc)
    finally:
        session.close()
        with _JOBS_LOCK:
            if _JOBS[job_id]["status"] == "running":
                _JOBS[job_id]["status"] = "done"
            _JOBS[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
            _JOBS[job_id]["finished_at_ts"] = time.time()


@image_backfill_bp.route("/run", methods=["POST"])
@require_auth
def run_backfill():
    _, error = _admin_or_403()
    if error:
        return error
    body = request.get_json(silent=True) or {}
    raw_ids = body.get("product_ids") or []
    provider = (body.get("provider") or "auto").strip().lower()
    if provider not in ("auto", "gemini", "openai"):
        return jsonify({"error": f"invalid provider {provider!r}"}), 400
    try:
        product_ids = [int(x) for x in raw_ids]
    except (TypeError, ValueError):
        return jsonify({"error": "product_ids must be integers"}), 400
    if not product_ids:
        return jsonify({"error": "product_ids is required"}), 400
    if len(product_ids) > 200:
        return jsonify({"error": "max 200 product_ids per run"}), 400

    job_id = uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "id": job_id,
            "status": "queued",
            "provider": provider,
            "total": len(product_ids),
            "fetched": 0,
            "failed": 0,
            "providers_used": {},
            "items": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "finished_at_ts": None,
        }
    threading.Thread(
        target=_run_admin_job,
        args=(job_id, product_ids, provider),
        name=f"image-backfill-{job_id[:8]}",
        daemon=True,
    ).start()
    return jsonify({"job_id": job_id}), 202


@image_backfill_bp.route("/schedule", methods=["GET"])
@require_auth
def get_schedule():
    _, error = _admin_or_403()
    if error:
        return error
    cfg = load_schedule()
    next_run = None
    try:
        from src.backend.schedule_daily_recommendations import get_image_backfill_runtime
        rt = get_image_backfill_runtime() or {}
        next_run = rt.get("next_run_at")
    except Exception:
        pass
    return jsonify({**cfg, "next_run_at": next_run}), 200


@image_backfill_bp.route("/schedule", methods=["PUT"])
@require_auth
def update_schedule():
    _, error = _admin_or_403()
    if error:
        return error
    body = request.get_json(silent=True) or {}
    try:
        enabled = bool(body.get("enabled", True))
        hour = int(body.get("hour"))
        minute = int(body.get("minute"))
    except (TypeError, ValueError):
        return jsonify({"error": "enabled, hour, minute are required"}), 400
    try:
        cfg = save_schedule(enabled=enabled, hour=hour, minute=minute)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    next_run = None
    try:
        from src.backend.schedule_daily_recommendations import reschedule_image_backfill
        rt = reschedule_image_backfill(**cfg) or {}
        next_run = rt.get("next_run_at")
    except Exception as exc:
        logger.exception("Live reschedule failed: %s", exc)
        return jsonify({**cfg, "next_run_at": None,
                        "warning": f"saved but live reschedule failed: {exc}"}), 200
    return jsonify({**cfg, "next_run_at": next_run}), 200


@image_backfill_bp.route("/jobs/<job_id>", methods=["GET"])
@require_auth
def get_job(job_id):
    _, error = _admin_or_403()
    if error:
        return error
    _gc_jobs()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return jsonify({"error": "job not found"}), 404
        return jsonify(dict(job)), 200


@image_backfill_bp.route("/history", methods=["GET"])
@require_auth
def get_history():
    """Daily history of auto_fetch ProductSnapshots over the last N days
    so admins can see how many images were generated each night and what
    it cost. Provider + cost are read from the snapshot's notes field
    (stamped at write time); rows without notes count as unknown_provider
    and contribute 0 to the cost total.
    """
    _, error = _admin_or_403()
    if error:
        return error
    try:
        days = max(1, min(int(request.args.get("days", 30)), 365))
    except (TypeError, ValueError):
        days = 30
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        g.db_session.query(ProductSnapshot, Product)
        .join(Product, Product.id == ProductSnapshot.product_id)
        .filter(ProductSnapshot.source_context == "auto_fetch")
        .filter(ProductSnapshot.created_at >= cutoff)
        .order_by(ProductSnapshot.created_at.desc())
        .all()
    )
    by_day: dict[str, dict] = {}
    totals_by_provider: dict[str, int] = {}
    totals_by_model: dict[str, int] = {}
    total_fetched = 0
    total_cost = 0.0
    for r, prod in rows:
        day = (r.created_at or r.captured_at or datetime.now(timezone.utc)).date().isoformat()
        prov = "unknown"
        model = None
        cost = 0.0
        if r.notes:
            try:
                meta = json.loads(r.notes)
                prov = (meta.get("provider") or "unknown").lower()
                model = meta.get("model")
                cost = float(meta.get("cost_usd") or _PROVIDER_COST_USD.get(prov, 0.0))
            except (ValueError, TypeError):
                pass
        # Fall back to the provider→model map for older rows that have a
        # provider stamp but no explicit model field.
        if not model:
            model = model_for_provider(prov) or "unknown"
        bucket = by_day.setdefault(day, {
            "date": day, "fetched": 0, "cost_usd": 0.0,
            "by_provider": {}, "by_model": {}, "items": [],
        })
        bucket["fetched"] += 1
        bucket["cost_usd"] += cost
        bucket["by_provider"][prov] = bucket["by_provider"].get(prov, 0) + 1
        bucket["by_model"][model] = bucket["by_model"].get(model, 0) + 1
        bucket["items"].append({
            "snapshot_id": r.id,
            "product_id": prod.id,
            "product_name": (prod.display_name or prod.name) if prod else None,
            "category": prod.category if prod else None,
            "image_url": f"/product-snapshots/{r.id}/image",
            "provider": prov,
            "model": model,
            "cost_usd": cost,
            "captured_at": (r.captured_at or r.created_at).isoformat() if (r.captured_at or r.created_at) else None,
        })
        totals_by_provider[prov] = totals_by_provider.get(prov, 0) + 1
        totals_by_model[model] = totals_by_model.get(model, 0) + 1
        total_fetched += 1
        total_cost += cost
    days_sorted = sorted(by_day.values(), key=lambda d: d["date"], reverse=True)
    # Round each day's cost so floating-point cruft doesn't leak into UI.
    for d in days_sorted:
        d["cost_usd"] = round(d["cost_usd"], 4)
    return jsonify({
        "days": days_sorted,
        "totals": {
            "fetched": total_fetched,
            "cost_usd": round(total_cost, 4),
            "by_provider": totals_by_provider,
            "by_model": totals_by_model,
        },
        "window_days": days,
        "provider_pricing_usd": _PROVIDER_COST_USD,
    }), 200
