#!/usr/bin/env python3
"""Holdout eval: measure hit-rate (did we recommend things actually rebought) and
junk-rate (recommended but not rebought), heuristic vs AI, over the current DB.
Run: PYTHONPATH=. DATABASE_URL=sqlite:///path/to/dev.db python3 scripts/eval_recommendations.py"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timezone

from flask import Flask, g
from src.backend.initialize_database_schema import create_db_engine, create_session_factory
from src.backend.recommendation_features import build_recommendation_candidates
from src.backend.recommend_via_llm import judge_candidates
from src.backend.generate_recommendations import generate_all_recommendations


def _ids_of(recs) -> set[int]:
    out: set[int] = set()
    for r in recs:
        if r.get("product_id"):
            out.add(int(r["product_id"]))
        for pid in (r.get("product_ids") or []):
            if pid:
                out.add(int(pid))
    return out


def main() -> int:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("set DATABASE_URL", file=sys.stderr)
        return 2
    Session = create_session_factory(create_db_engine(url))
    s = Session()
    app = Flask(__name__)
    try:
        with app.app_context():
            g.db_session = s
            now = datetime.now(timezone.utc)
            cands = build_recommendation_candidates(s, now=now, cap=50)
            # "truth" = items bought recently and recurring (what a good rec should surface)
            truth = {c["product_id"] for c in cands
                     if (c["days_since_last"] or 999) <= 30 and not c["one_off"]}

            def score(ids: set[int], label: str) -> None:
                hit = len(ids & truth) / len(truth) if truth else 0.0
                junk = len(ids - truth) / len(ids) if ids else 0.0
                print(f"{label:10} hit-rate={hit:.2f}  junk-rate={junk:.2f}  n={len(ids)}")

            heur = _ids_of(generate_all_recommendations())
            try:
                ai = _ids_of(judge_candidates(cands))
            except Exception as exc:  # noqa: BLE001
                print("AI judge failed (Ollama unreachable?):", exc)
                ai = set()

            print(f"truth set size: {len(truth)}")
            score(heur, "heuristic")
            score(ai, "ai")
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
