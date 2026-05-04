"""Medication lookup via OpenFDA and optional AI enrichment.

Two public entry points:

  lookup_by_barcode(barcode)  -- query OpenFDA NDC endpoint by UPC/NDC
  lookup_by_name(name)        -- query OpenFDA by brand/generic name
  ai_enrich_medication(...)   -- fill gaps with an AI call

All functions return a dict compatible with the MedicineCabinetItem
schema, or None / {} on failure.  They never raise -- all errors are
logged at WARNING level and swallowed so callers can degrade gracefully.
"""
from __future__ import annotations

import json
import logging
import re

import requests

logger = logging.getLogger(__name__)

OPENFDA_TIMEOUT = 6  # seconds

DOSAGE_FORM_MAP: dict[str, str] = {
    "tablet": "tablet",
    "tablets": "tablet",
    "capsule": "capsule",
    "capsules": "capsule",
    "solution": "liquid",
    "suspension": "liquid",
    "syrup": "liquid",
    "liquid": "liquid",
    "cream": "cream",
    "gel": "cream",
    "ointment": "cream",
    "spray": "spray",
    "patch": "patch",
    "film": "patch",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_openfda_result(hit: dict) -> dict:
    """Extract fields from an OpenFDA drug/ndc or drug/label result.

    The NDC endpoint returns flat ``results[0]`` objects; the label
    endpoint nests most identifiers under an ``openfda`` sub-dict.
    Both layouts are handled here.
    """
    openfda = hit.get("openfda") or {}

    def first(value):
        """Return the first element of a list, or the value itself."""
        if isinstance(value, list):
            return value[0] if value else None
        return value or None

    # Dosage form
    raw_form: str = first(hit.get("dosage_form") or openfda.get("dosage_form")) or ""
    key = raw_form.lower().split()[0] if raw_form.strip() else ""
    normalized_form = DOSAGE_FORM_MAP.get(key, "other")

    # Strength from active_ingredients list
    ais = hit.get("active_ingredients") or []
    strength = ais[0].get("strength") if ais and isinstance(ais[0], dict) else None

    # Warnings — label endpoint has full-text arrays
    warn_text: str = (
        first(hit.get("warnings") or hit.get("warnings_and_cautions")) or ""
    )
    warnings = [warn_text[:500]] if warn_text else []

    # Age-group hint from pediatric_use / indications_and_usage
    pediatric = first(hit.get("pediatric_use") or [])
    indications: str = first(hit.get("indications_and_usage") or []) or ""
    age_group = "both"
    if pediatric:
        age_group = "child" if "adult" not in str(pediatric).lower() else "both"
    elif "adult" in indications.lower() and "child" not in indications.lower():
        age_group = "adult"

    generic = first(hit.get("generic_name") or openfda.get("generic_name"))
    brand = first(hit.get("brand_name") or openfda.get("brand_name"))
    manufacturer = first(
        hit.get("manufacturer_name") or openfda.get("manufacturer_name")
    )

    return {
        k: v
        for k, v in {
            "name": brand or generic,
            "brand": manufacturer,
            "active_ingredient": generic,
            "dosage_form": normalized_form,
            "strength": strength,
            "age_group": age_group,
            "ai_warnings": json.dumps(warnings) if warnings else None,
        }.items()
        if v is not None
    }


# ---------------------------------------------------------------------------
# Public lookup functions
# ---------------------------------------------------------------------------

def lookup_by_barcode(barcode: str) -> dict | None:
    """Query OpenFDA by UPC/NDC barcode.

    Tries ``package_ndc`` first, then ``product_ndc``.
    Returns a normalized dict or None if nothing is found.
    """
    clean = re.sub(r"[^0-9]", "", barcode or "")
    if not clean:
        return None

    urls = [
        f"https://api.fda.gov/drug/ndc.json?search=package_ndc:{clean}&limit=1",
        f"https://api.fda.gov/drug/ndc.json?search=product_ndc:{clean}&limit=1",
    ]
    for url in urls:
        try:
            resp = requests.get(url, timeout=OPENFDA_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results") or []
                if results:
                    return _normalize_openfda_result(results[0])
        except Exception as exc:
            logger.warning("OpenFDA barcode lookup failed: %s", exc)
    return None


def lookup_by_name(name: str) -> dict | None:
    """Query OpenFDA by brand or generic name.

    Tries the label endpoint first (richer field set), then NDC by
    brand_name, then NDC by generic_name.
    Returns a normalized dict or None if nothing is found.
    """
    if not (name or "").strip():
        return None

    safe = requests.utils.quote(name.strip())
    urls = [
        f"https://api.fda.gov/drug/label.json?search=openfda.brand_name:{safe}&limit=1",
        f"https://api.fda.gov/drug/ndc.json?search=brand_name:{safe}&limit=1",
        f"https://api.fda.gov/drug/ndc.json?search=generic_name:{safe}&limit=1",
    ]
    for url in urls:
        try:
            resp = requests.get(url, timeout=OPENFDA_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results") or []
                if results:
                    return _normalize_openfda_result(results[0])
        except Exception as exc:
            logger.warning("OpenFDA name lookup failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# AI enrichment
# ---------------------------------------------------------------------------

def ai_enrich_medication(
    name: str,
    existing_fields: dict,
    session=None,
    user=None,
) -> dict:
    """Call the app's AI layer to fill gaps and add warnings.

    Uses ``_build_provider_chain`` from ``chat_assistant`` so it
    honours whatever AI key/model the operator has configured.
    Returns a dict with any subset of:
        {age_group, ai_warnings, dosage_form, active_ingredient, strength}
    Falls back to ``{}`` if no AI is configured or the call fails.
    """
    try:
        from src.backend.chat_assistant import _build_provider_chain  # noqa: PLC0415

        chain = _build_provider_chain(session, user) if session else []
        if not chain:
            return {}

        # Each entry is a dict: {provider, label, model_string, call}
        caller = chain[0]["call"]

        known = {k: v for k, v in existing_fields.items() if v}
        system_prompt = (
            "You are a pharmaceutical data assistant. "
            "Return ONLY a JSON object with these fields (omit any you are uncertain about): "
            "age_group (adult|child|both), "
            "dosage_form (tablet|capsule|liquid|cream|spray|patch|other), "
            "active_ingredient, strength, "
            "ai_warnings (array of short warning strings, max 3). "
            "No explanation, no markdown, just the JSON object."
        )
        user_message = f"Medication: {name}. Known: {json.dumps(known)}"

        raw: str = caller(
            system_prompt=system_prompt,
            history=[],
            user_message=user_message,
        )

        # Strip markdown code fences if the model wrapped its output
        raw = re.sub(
            r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE
        ).strip()
        result = json.loads(raw)

        out: dict = {}
        if "age_group" in result and result["age_group"] in ("adult", "child", "both"):
            out["age_group"] = result["age_group"]
        if "dosage_form" in result:
            out["dosage_form"] = str(result["dosage_form"])[:50]
        if "active_ingredient" in result:
            out["active_ingredient"] = str(result["active_ingredient"])[:200]
        if "strength" in result:
            out["strength"] = str(result["strength"])[:100]
        if "ai_warnings" in result and isinstance(result["ai_warnings"], list):
            out["ai_warnings"] = json.dumps(
                [str(w)[:200] for w in result["ai_warnings"][:3]]
            )
        return out

    except Exception as exc:
        logger.warning("AI medication enrichment failed: %s", exc)
        return {}
