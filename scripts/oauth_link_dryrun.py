#!/usr/bin/env python3
"""DRY RUN — Google sign-in account-linking preview. READ ONLY, ZERO WRITES.

Prints, for every existing user and a set of hypothetical incoming Google
logins, exactly what the linker WOULD do — before any linking write happens.
Classifies each as:

  MATCHED   verified Google email maps unambiguously to one existing account
            → would link (both methods then reach that one account)
  NO-MATCH  verified Google email matches no existing account
            → would require an invite (else rejected); never auto-creates
  CONFLICT  unverified email, OR an email that matches >1 active account
            → SURFACED, never silently linked (account-takeover guard)

Usage:
  DATABASE_URL=sqlite:///path/to/users.db \
      python3 scripts/oauth_link_dryrun.py [incoming_logins.json]

The optional JSON file is a list of {"sub","email","email_verified"} objects.
With no file, a built-in sample exercises every branch. The DB session is
opened read-only and rolled back — nothing is ever committed.
"""
from __future__ import annotations

import json
import os
import sys

from sqlalchemy import func

# Reuse the SAME verification rule the production resolver uses, so this preview
# can never drift from real behaviour.
from src.backend.manage_authentication import _google_email_is_verified
from src.backend.initialize_database_schema import (
    create_db_engine, create_session_factory, User,
)

SAMPLE = [
    {"sub": "g-1", "email": "MATCH@example.com", "email_verified": True},
    {"sub": "g-2", "email": "stranger@example.com", "email_verified": True},
    {"sub": "g-3", "email": "match@example.com", "email_verified": False},
    {"sub": "g-4", "email": "dupe@example.com", "email_verified": True},
]


def classify(session, g: dict) -> tuple[str, str]:
    email = str(g.get("email") or "").strip().lower()
    verified = _google_email_is_verified(g)
    if not email or not str(g.get("sub") or "").strip():
        return "CONFLICT", "missing sub/email in Google response"

    matches = (
        session.query(User)
        .filter(func.lower(User.email) == email, User.is_active.is_(True))
        .all()
    )
    if len(matches) > 1:
        return "CONFLICT", f"ambiguous — {len(matches)} active accounts share this email"
    if matches:
        u = matches[0]
        if u.google_sub and u.google_sub != g.get("sub"):
            return "CONFLICT", f"account #{u.id} already linked to a different Google sub"
        if not verified:
            return "CONFLICT", f"email matches account #{u.id} but Google email NOT verified"
        return "MATCHED", f"would link to existing account #{u.id} ({u.email})"
    # no existing account
    if not verified:
        return "CONFLICT", "no account + email unverified → rejected"
    return "NO-MATCH", "no existing account → requires an invite to create"


def main() -> int:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: set DATABASE_URL (read-only dry run).", file=sys.stderr)
        return 2

    incoming = SAMPLE
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as fh:
            incoming = json.load(fh)

    engine = create_db_engine(url)
    Session = create_session_factory(engine)
    session = Session()
    try:
        users = session.query(User).order_by(User.id.asc()).all()
        print("=" * 72)
        print(f"DRY RUN — Google account-linking preview  (DB: {url})")
        print("READ ONLY — no rows will be written.")
        print("=" * 72)

        print(f"\nExisting users: {len(users)}")
        for u in users:
            linked = f"google_sub={u.google_sub}" if u.google_sub else "no-google"
            haspw = "password" if u.password_hash else "no-password"
            print(f"  #{u.id:<3} {u.email or '(no email)':<28} "
                  f"[{'active' if u.is_active else 'inactive'}] {haspw} {linked}")

        print(f"\nIncoming Google logins to evaluate: {len(incoming)}")
        tally = {"MATCHED": 0, "NO-MATCH": 0, "CONFLICT": 0}
        for g in incoming:
            verdict, why = classify(session, g)
            tally[verdict] += 1
            vflag = "verified" if _google_email_is_verified(g) else "UNVERIFIED"
            print(f"  [{verdict:<8}] {str(g.get('email','')):<28} ({vflag:<10}) → {why}")

        print("\nSummary:", ", ".join(f"{k}={v}" for k, v in tally.items()))
        print("No linking writes performed (dry run).")
    finally:
        session.rollback()
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
