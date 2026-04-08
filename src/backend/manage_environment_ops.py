import json
import os
import subprocess
import tarfile
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request, g, send_file

from src.backend.create_flask_application import require_auth
from src.backend.manage_authentication import is_admin

environment_ops_bp = Blueprint("environment_ops", __name__, url_prefix="/system")


def _admin_or_403():
    actor = getattr(g, "current_user", None)
    if not actor or not is_admin(actor):
        return None, (jsonify({"error": "Admin access required"}), 403)
    return actor, None


def _backups_dir() -> Path:
    return Path(os.getenv("BACKUP_DIR", "/data/backups"))


def _script_env() -> dict:
    env = os.environ.copy()
    env.setdefault("BACKUP_DIR", "/data/backups")
    env.setdefault("DB_PATH", "/data/db/localocr_extended.db")
    env.setdefault("RECEIPTS_DIR", "/data/receipts")
    env.setdefault("BACKUP_PREFIX", "localocr_extended")
    return env


def _run_script(script_name: str, *args: str, timeout: int = 600):
    script_path = Path("/app/scripts") / script_name
    cmd = ["bash", str(script_path), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_script_env(),
    )


def _list_backup_entries():
    backups_dir = _backups_dir()
    backups_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for archive in sorted(backups_dir.glob("*_backup_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True):
        manifest_data = _load_manifest_for_archive(archive)
        entries.append({
            "filename": archive.name,
            "size_bytes": archive.stat().st_size,
            "modified_at": archive.stat().st_mtime,
            "manifest": manifest_data,
        })
    return entries


def _manifest_sidecar_path(archive: Path) -> Path:
    return archive.with_suffix("").with_suffix(".manifest.json")


def _normalize_manifest(manifest_data: dict | None, archive: Path) -> dict | None:
    if not isinstance(manifest_data, dict):
        return None
    manifest = dict(manifest_data)
    manifest.setdefault("archive_name", archive.name)
    database = manifest.get("database")
    if isinstance(database, dict):
      # keep older manifests readable in the UI by adding explicit fields when missing
        if "trusted_device_rows" not in database and "trusted_devices" in database:
            database["trusted_device_rows"] = database.get("trusted_devices")
        if "active_trusted_devices" not in database and "trusted_devices" in database:
            database["active_trusted_devices"] = database.get("trusted_devices")
    return manifest


def _load_manifest_for_archive(archive: Path):
    manifest_path = _manifest_sidecar_path(archive)
    if manifest_path.exists():
        try:
            return _normalize_manifest(json.loads(manifest_path.read_text(encoding="utf-8")), archive)
        except Exception:
            pass
    try:
        with tarfile.open(archive, mode="r:gz") as tf:
            for candidate in ("meta/manifest.json", "./meta/manifest.json", "manifest.json", "./manifest.json"):
                try:
                    member = tf.getmember(candidate)
                except KeyError:
                    continue
                extracted = tf.extractfile(member)
                if not extracted:
                    continue
                manifest_data = json.loads(extracted.read().decode("utf-8"))
                normalized = _normalize_manifest(manifest_data, archive)
                if normalized:
                    try:
                        manifest_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                    return normalized
    except Exception:
        return None
    return None


def _validate_backup_filename(filename: str) -> str:
    cleaned = str(filename or "").strip()
    if not cleaned or "/" in cleaned or cleaned.startswith("."):
        raise ValueError("Backup filename is required")
    return cleaned


def _schedule_container_restart(delay_seconds: float = 1.0):
    def _shutdown():
        os._exit(0)
    timer = threading.Timer(delay_seconds, _shutdown)
    timer.daemon = True
    timer.start()


@environment_ops_bp.get("/backups")
@require_auth
def list_backups():
    _actor, error = _admin_or_403()
    if error:
        return error
    verify_report = None
    verify_path = _backups_dir() / "last_verify_report.json"
    if verify_path.exists():
        try:
            verify_report = json.loads(verify_path.read_text(encoding="utf-8"))
        except Exception:
            verify_report = None
    restore_report = None
    restore_path = _backups_dir() / "last_restore_report.json"
    if restore_path.exists():
        try:
            restore_report = json.loads(restore_path.read_text(encoding="utf-8"))
        except Exception:
            restore_report = None
    return jsonify({
        "backups": _list_backup_entries(),
        "last_verify_report": verify_report,
        "last_restore_report": restore_report,
    })


@environment_ops_bp.post("/backups/create")
@require_auth
def create_backup():
    _actor, error = _admin_or_403()
    if error:
        return error
    result = _run_script("backup_database_and_volumes.sh", timeout=900)
    if result.returncode != 0:
        return jsonify({
            "error": "Backup failed",
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }), 500
    backups = _list_backup_entries()
    return jsonify({
        "status": "created",
        "latest_backup": backups[0] if backups else None,
        "stdout": result.stdout[-4000:],
    })


@environment_ops_bp.post("/backups/upload")
@require_auth
def upload_backup():
    _actor, error = _admin_or_403()
    if error:
        return error

    uploaded = request.files.get("backup")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Backup file is required"}), 400

    filename = Path(uploaded.filename).name
    if not filename.endswith(".tar.gz"):
        return jsonify({"error": "Backup must be a .tar.gz archive"}), 400

    backup_path = _backups_dir() / filename
    uploaded.save(backup_path)
    manifest_data = _load_manifest_for_archive(backup_path)
    return jsonify({
        "status": "uploaded",
        "filename": filename,
        "size_bytes": backup_path.stat().st_size,
        "manifest": manifest_data,
    })


@environment_ops_bp.get("/backups/download/<path:filename>")
@require_auth
def download_backup(filename):
    _actor, error = _admin_or_403()
    if error:
        return error
    try:
        safe_name = _validate_backup_filename(filename)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    backup_path = _backups_dir() / safe_name
    if not backup_path.exists():
        return jsonify({"error": "Backup file not found"}), 404
    return send_file(backup_path, as_attachment=True, download_name=safe_name)


@environment_ops_bp.post("/backups/verify")
@require_auth
def verify_environment():
    _actor, error = _admin_or_403()
    if error:
        return error
    out_path = str(_backups_dir() / "last_verify_report.json")
    result = _run_script("verify_restored_environment.sh", out_path, timeout=180)
    if result.returncode != 0:
        return jsonify({
            "error": "Verification failed",
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }), 500
    report = None
    try:
        report = json.loads(result.stdout)
    except Exception:
        report = None
    return jsonify({
        "status": "verified",
        "report": report,
        "stdout": result.stdout[-4000:],
    })


@environment_ops_bp.post("/backups/restore")
@require_auth
def restore_backup():
    _actor, error = _admin_or_403()
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    try:
        filename = _validate_backup_filename(payload.get("filename") or "")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not filename:
        return jsonify({"error": "Backup filename is required"}), 400

    backup_path = _backups_dir() / filename
    if not backup_path.exists():
        return jsonify({"error": "Backup file not found"}), 404

    target_env = str(_backups_dir() / "restored_env.snapshot")
    result = _run_script(
        "restore_from_backup.sh",
        str(backup_path),
        "--yes",
        "--no-restart",
        "--target-env-file",
        target_env,
        timeout=900,
    )
    if result.returncode != 0:
        return jsonify({
            "error": "Restore failed",
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }), 500

    restore_report = None
    restore_path = _backups_dir() / "last_restore_report.json"
    if restore_path.exists():
        try:
            restore_report = json.loads(restore_path.read_text(encoding="utf-8"))
        except Exception:
            restore_report = None

    _schedule_container_restart(1.2)
    return jsonify({
        "status": "restored",
        "restart_scheduled": True,
        "message": "Restore applied. Backend restart scheduled.",
        "report": restore_report,
        "stdout": result.stdout[-4000:],
    })
