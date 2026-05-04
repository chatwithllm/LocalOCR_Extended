"""
Medicine Cabinet — Medication CRUD API
=======================================

Blueprint: medications_bp  (url_prefix: /medications)

Endpoints:
  GET    /medications                  — list with optional filters
  POST   /medications/barcode-lookup   — pre-fill fields from barcode/name (no save)
  POST   /medications                  — create
  GET    /medications/<id>             — get single
  PUT    /medications/<id>             — update
  DELETE /medications/<id>             — delete
  POST   /medications/<id>/photo       — upload photo
"""

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, g, jsonify, request

from src.backend.create_flask_application import require_auth, require_write_access
from src.backend.initialize_database_schema import Medication

logger = logging.getLogger(__name__)

medications_bp = Blueprint("medications", __name__, url_prefix="/medications")

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_int(v):
    try:
        return int(v) if v not in (None, "", "null") else None
    except Exception:
        return None


def _is_expired(med: Medication) -> bool:
    if not med.expiry_date:
        return False
    return med.expiry_date < date.today()


def _is_low(med: Medication) -> bool:
    if med.low_threshold is None or med.quantity is None:
        return False
    return med.quantity <= med.low_threshold


def _serialize_medication(med: Medication) -> dict:
    return {
        "id": med.id,
        "name": med.name,
        "brand": med.brand,
        "strength": med.strength,
        "dosage_form": med.dosage_form,
        "active_ingredient": med.active_ingredient,
        "age_group": med.age_group or "both",
        "belongs_to": med.belongs_to or "household",
        "member_id": med.member_id,
        "barcode": med.barcode,
        "product_id": med.product_id,
        "manufacture_date": str(med.manufacture_date) if med.manufacture_date else None,
        "expiry_date": str(med.expiry_date) if med.expiry_date else None,
        "quantity": med.quantity,
        "unit": med.unit or "count",
        "low_threshold": med.low_threshold,
        "rx_number": med.rx_number,
        "prescribing_doctor": med.prescribing_doctor,
        "ai_warnings": json.loads(med.ai_warnings) if med.ai_warnings else [],
        "image_path": med.image_path,
        "status": med.status or "active",
        "notes": med.notes,
        "created_at": med.created_at.isoformat() if med.created_at else None,
        "updated_at": med.updated_at.isoformat() if med.updated_at else None,
        "is_expired": _is_expired(med),
        "is_low": _is_low(med),
    }


def _get_medication_photo_root() -> Path:
    """Return the base directory for medication photos, mirroring snapshot-root pattern."""
    configured = os.getenv("MEDICATION_PHOTOS_DIR")
    if configured:
        return Path(configured)

    container_path = Path("/data/medication_photos")
    if container_path.parent.exists():
        return container_path

    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "data" / "medication_photos"


def _parse_date(value: str):
    """Parse YYYY-MM-DD string → date, or raise ValueError."""
    return datetime.strptime(value, "%Y-%m-%d").date()


# Mutable fields accepted by POST (create) and PUT (update)
_MUTABLE_FIELDS = (
    "name", "brand", "strength", "dosage_form", "active_ingredient",
    "age_group", "belongs_to", "member_id", "barcode", "product_id",
    "quantity", "unit", "low_threshold", "rx_number", "prescribing_doctor",
    "notes", "status", "image_path",
)
_DATE_FIELDS = ("manufacture_date", "expiry_date")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@medications_bp.route("", methods=["GET"])
@require_auth
def list_medications():
    session = g.db_session
    query = session.query(Medication)

    status = request.args.get("status", "active")
    if status != "all":
        query = query.filter(Medication.status == status)

    member_id = _parse_int(request.args.get("member_id"))
    if member_id is not None:
        query = query.filter(Medication.member_id == member_id)

    age_group = request.args.get("age_group")
    if age_group:
        query = query.filter(Medication.age_group == age_group)

    meds = query.order_by(Medication.name).all()
    return jsonify({"medications": [_serialize_medication(m) for m in meds], "count": len(meds)}), 200


@medications_bp.route("/barcode-lookup", methods=["POST"])
@require_auth
def medication_barcode_lookup_endpoint():
    from src.backend.medication_barcode_lookup import lookup_by_barcode, lookup_by_name, ai_enrich_medication

    data = request.get_json(silent=True) or {}
    barcode = (data.get("barcode") or "").strip()
    name = (data.get("name") or "").strip()

    fields = {}
    if barcode:
        fields = lookup_by_barcode(barcode) or {}
    if not fields and name:
        fields = lookup_by_name(name) or {}

    # AI-enrich any gaps
    lookup_name = fields.get("name") or name
    if lookup_name:
        try:
            enriched = ai_enrich_medication(
                lookup_name, fields,
                session=g.db_session,
                user=getattr(g, "current_user", None),
            )
            for k, v in enriched.items():
                if k not in fields or not fields[k]:
                    fields[k] = v
        except Exception:
            logger.exception("AI enrich failed for barcode-lookup (non-fatal)")

    if barcode and "barcode" not in fields:
        fields["barcode"] = barcode

    return jsonify({"found": bool(fields), "fields": fields}), 200


@medications_bp.route("", methods=["POST"])
@require_auth
@require_write_access
def create_medication():
    session = g.db_session
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    med = Medication(name=name)

    for field in _MUTABLE_FIELDS:
        if field == "name":
            continue  # already set
        if field in data:
            setattr(med, field, data[field])

    for date_field in _DATE_FIELDS:
        if date_field in data and data[date_field]:
            try:
                setattr(med, date_field, _parse_date(data[date_field]))
            except ValueError:
                return jsonify({"error": f"Invalid date format for {date_field}; expected YYYY-MM-DD"}), 400

    med.created_by_id = g.current_user.id

    session.add(med)
    session.commit()
    session.refresh(med)

    return jsonify({"medication": _serialize_medication(med)}), 201


@medications_bp.route("/<int:med_id>", methods=["GET"])
@require_auth
def get_medication(med_id: int):
    session = g.db_session
    med = session.query(Medication).filter(Medication.id == med_id).first()
    if not med:
        return jsonify({"error": "Medication not found"}), 404
    return jsonify({"medication": _serialize_medication(med)}), 200


@medications_bp.route("/<int:med_id>", methods=["PUT"])
@require_auth
@require_write_access
def update_medication(med_id: int):
    session = g.db_session
    med = session.query(Medication).filter(Medication.id == med_id).first()
    if not med:
        return jsonify({"error": "Medication not found"}), 404

    data = request.get_json(silent=True) or {}

    for field in _MUTABLE_FIELDS:
        if field in data:
            setattr(med, field, data[field])

    for date_field in _DATE_FIELDS:
        if date_field in data:
            v = data[date_field]
            if v:
                try:
                    setattr(med, date_field, _parse_date(v))
                except ValueError:
                    return jsonify({"error": f"Invalid date format for {date_field}; expected YYYY-MM-DD"}), 400
            else:
                setattr(med, date_field, None)

    session.commit()
    session.refresh(med)
    return jsonify({"medication": _serialize_medication(med)}), 200


@medications_bp.route("/<int:med_id>", methods=["DELETE"])
@require_auth
@require_write_access
def delete_medication(med_id: int):
    session = g.db_session
    med = session.query(Medication).filter(Medication.id == med_id).first()
    if not med:
        return jsonify({"error": "Medication not found"}), 404
    session.delete(med)
    session.commit()
    return jsonify({"deleted": True, "id": med_id}), 200


@medications_bp.route("/<int:med_id>/photo", methods=["POST"])
@require_auth
@require_write_access
def upload_medication_photo(med_id: int):
    session = g.db_session
    med = session.query(Medication).filter(Medication.id == med_id).first()
    if not med:
        return jsonify({"error": "Medication not found"}), 404

    if "image" not in request.files:
        return jsonify({"error": "No image field in request"}), 400

    image_file = request.files["image"]
    if not image_file or not image_file.filename:
        return jsonify({"error": "Empty file upload"}), 400

    ext = Path(image_file.filename).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({"error": f"Unsupported image type: {ext}"}), 400

    now = datetime.utcnow()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    filename = f"{uuid4().hex}{ext}"

    photo_root = _get_medication_photo_root()
    save_dir = photo_root / year / month
    save_dir.mkdir(parents=True, exist_ok=True)

    save_path = save_dir / filename
    image_file.save(str(save_path))

    # Store a relative path so it remains portable across deployments
    med.image_path = str(Path(year) / month / filename)
    session.commit()
    session.refresh(med)

    return jsonify({"medication": _serialize_medication(med)}), 200
