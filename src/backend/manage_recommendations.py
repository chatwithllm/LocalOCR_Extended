"""Async on-demand recommendation refresh. The LLM is slow on CPU, so the
endpoint spawns a thread and returns a job_id the UI polls."""
from __future__ import annotations
import logging
import threading
import uuid
from flask import Blueprint, Flask, g, jsonify

from src.backend.generate_recommendations import refresh_recommendation_cache
from src.backend.initialize_database_schema import create_db_engine, create_session_factory
from src.backend.manage_authentication import get_authenticated_user

logger = logging.getLogger(__name__)
recommendations_admin_bp = Blueprint("recommendations_admin", __name__, url_prefix="/recommendations")

_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _run(job_id: str) -> None:
    # Runs outside any request context — build a mock app context + g.db_session
    # exactly like the nightly job (push_daily_recommendations).
    engine = create_db_engine()
    Session = create_session_factory(engine)
    app = Flask(__name__)
    try:
        with app.app_context():
            g.db_session = Session()
            try:
                summary = refresh_recommendation_cache()
                g.db_session.commit()
                with _JOBS_LOCK:
                    _JOBS[job_id] = {"status": "done", "summary": summary}
            finally:
                g.db_session.close()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Recommendation refresh job failed")
        with _JOBS_LOCK:
            _JOBS[job_id] = {"status": "error", "error": str(exc)}


def start_refresh_job() -> str:
    job_id = uuid.uuid4().hex
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "running"}
    threading.Thread(target=_run, args=(job_id,), daemon=True).start()
    return job_id


def get_job_status(job_id: str) -> dict | None:
    with _JOBS_LOCK:
        return dict(_JOBS.get(job_id)) if job_id in _JOBS else None


@recommendations_admin_bp.route("/refresh", methods=["POST"])
def refresh_endpoint():
    if not get_authenticated_user():
        return jsonify({"error": "Authentication required"}), 401
    return jsonify({"job_id": start_refresh_job()}), 202


@recommendations_admin_bp.route("/refresh/<job_id>", methods=["GET"])
def refresh_status(job_id: str):
    if not get_authenticated_user():
        return jsonify({"error": "Authentication required"}), 401
    st = get_job_status(job_id)
    if not st:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify(st), 200
