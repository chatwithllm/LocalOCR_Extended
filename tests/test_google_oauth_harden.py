"""Verification suite for the Google sign-in HARDENING work.

Context: "Sign in with Google" already shipped beside username/password login.
This suite does NOT rebuild it — it pins the two guarantees that mattered for
the hardening pass:

  1. The existing username/password login keeps working EXACTLY as before
     (regression — must never break).
  2. Google sign-in links to an existing account ONLY when the Google email is
     verified, matches unambiguously, and both methods resolve to ONE account;
     unverified / ambiguous matches are surfaced, never silently linked.

In-memory SQLite, identical to the rest of the suite. No real user store is
touched.
"""
from __future__ import annotations

import os

import pytest

# Force in-memory SQLite even if the shell exported DATABASE_URL — never let a
# test mutate a real store. (Same guard the other test modules use.)
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SESSION_SECRET", "test-secret-for-oauth-harden")


_SF = None  # shared in-memory session factory for the whole module


@pytest.fixture(scope="module")
def app():
    """A focused Flask app with ONLY the real auth blueprint wired to an
    in-memory DB — enough to exercise /auth/login and the OAuth resolver
    without importing the full app's heavy blueprint graph.
    """
    global _SF
    from flask import Flask, g
    from src.backend.initialize_database_schema import initialize_database
    from src.backend.manage_authentication import auth_bp

    _engine, _SF = initialize_database()  # DATABASE_URL=sqlite:// (in-memory)

    application = Flask(__name__)
    application.config["TESTING"] = True
    application.secret_key = os.environ["SESSION_SECRET"]
    application.register_blueprint(auth_bp)

    @application.before_request
    def _open():
        g.db_session = _SF()

    @application.teardown_request
    def _close(exc=None):
        s = g.pop("db_session", None)
        if s is not None:
            s.rollback() if exc else None
            s.close()

    yield application


@pytest.fixture()
def session(app):
    """A DB session on the same in-memory engine the requests use."""
    s = _SF()
    yield s
    s.rollback()
    s.close()


def _make_user(session, *, name, email, password=None, google_sub=None):
    from src.backend.initialize_database_schema import User
    from src.backend.manage_authentication import hash_password
    u = User(
        name=name,
        email=email,
        role="user",
        is_active=True,
        password_hash=hash_password(password) if password else None,
        google_sub=google_sub,
        session_version=0,
    )
    session.add(u)
    session.commit()
    return u


# ---------------------------------------------------------------------------
# (a) REGRESSION — password login is completely unchanged
# ---------------------------------------------------------------------------

def test_password_login_still_works(app, session):
    _make_user(session, name="Alice", email="alice@example.com", password="hunter2")
    client = app.test_client()
    resp = client.post("/auth/login", json={"email": "alice@example.com", "password": "hunter2"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["user"]["email"] == "alice@example.com"


def test_password_login_rejects_wrong_password(app, session):
    _make_user(session, name="Carol", email="carol@example.com", password="correct-horse")
    client = app.test_client()
    resp = client.post("/auth/login", json={"email": "carol@example.com", "password": "WRONG"})
    assert resp.status_code == 401


def test_password_login_case_insensitive_identifier(app, session):
    _make_user(session, name="Dave", email="dave@example.com", password="pw12345")
    client = app.test_client()
    resp = client.post("/auth/login", json={"email": "DAVE@EXAMPLE.COM", "password": "pw12345"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# (b/c) Google login for an existing VERIFIED email → links to same account;
#       both methods then resolve to ONE account.
# ---------------------------------------------------------------------------

def test_verified_google_links_to_existing_account(app, session):
    from src.backend.manage_authentication import _find_or_create_oauth_user
    user = _make_user(session, name="Eve", email="eve@example.com", password="pw-eve-001")
    assert user.google_sub is None

    resolved, reason = _find_or_create_oauth_user(
        session,
        {"sub": "google-sub-eve", "email": "Eve@Example.com", "email_verified": True, "name": "Eve"},
        invite_token=None,
    )
    session.commit()

    assert reason is None
    assert resolved is not None
    assert resolved.id == user.id           # SAME account, not a duplicate
    assert resolved.google_sub == "google-sub-eve"

    # Both methods now reach the one account.
    client = app.test_client()
    pw = client.post("/auth/login", json={"email": "eve@example.com", "password": "pw-eve-001"})
    assert pw.status_code == 200
    assert pw.get_json()["user"]["id"] == user.id

    again, reason2 = _find_or_create_oauth_user(
        session, {"sub": "google-sub-eve", "email": "eve@example.com", "email_verified": True}, None
    )
    assert reason2 is None and again.id == user.id   # Path A re-login


# ---------------------------------------------------------------------------
# THE SECURITY GUARANTEE — unverified email is NEVER silently linked
# ---------------------------------------------------------------------------

def test_unverified_google_email_is_NOT_linked(app, session):
    from src.backend.manage_authentication import _find_or_create_oauth_user
    user = _make_user(session, name="Frank", email="frank@example.com", password="pw-frank-1")

    resolved, reason = _find_or_create_oauth_user(
        session,
        {"sub": "attacker-sub", "email": "frank@example.com", "email_verified": False},
        invite_token=None,
    )
    session.commit()

    assert resolved is None
    assert reason == "email_unverified"

    session.refresh(user)
    assert user.google_sub is None          # account was NOT taken over
    # And password login still works afterwards.
    client = app.test_client()
    assert client.post(
        "/auth/login", json={"email": "frank@example.com", "password": "pw-frank-1"}
    ).status_code == 200


def test_missing_email_verified_field_fails_closed(app, session):
    from src.backend.manage_authentication import _find_or_create_oauth_user
    user = _make_user(session, name="Grace", email="grace@example.com", password="pw-grace-1")
    resolved, reason = _find_or_create_oauth_user(
        session,
        {"sub": "sub-grace", "email": "grace@example.com"},  # no email_verified key
        invite_token=None,
    )
    assert resolved is None and reason == "email_unverified"
    session.refresh(user)
    assert user.google_sub is None


# ---------------------------------------------------------------------------
# (d) Brand-new Google user via a valid invite (verified) → new account
# ---------------------------------------------------------------------------

def test_new_google_user_via_invite(app, session):
    # create_access_link / get_valid_access_link read g.db_session, so run
    # inside a request context bound to the same in-memory session.
    import json
    from flask import g
    from src.backend.manage_authentication import (
        _find_or_create_oauth_user, create_access_link,
    )
    from src.backend.initialize_database_schema import User

    with app.test_request_context():
        g.db_session = session
        token, _link = create_access_link(
            purpose="google_invite",
            created_by_id=None,
            expires_in_minutes=60,
            metadata_json=json.dumps({"email": "newbie@example.com", "name": "Newbie", "role": "user"}),
        )
        session.commit()

        assert session.query(User).filter_by(email="newbie@example.com").first() is None

        resolved, reason = _find_or_create_oauth_user(
            session,
            {"sub": "sub-newbie", "email": "newbie@example.com", "email_verified": True, "name": "Newbie"},
            invite_token=token,
        )
        session.commit()
        assert reason is None
        assert resolved is not None
        assert resolved.email == "newbie@example.com"
        assert resolved.google_sub == "sub-newbie"
        assert resolved.password_hash is None   # google-only account, no password


def test_invite_email_mismatch_is_rejected(app, session):
    import json
    from flask import g
    from src.backend.manage_authentication import (
        _find_or_create_oauth_user, create_access_link,
    )
    with app.test_request_context():
        g.db_session = session
        token, _link = create_access_link(
            purpose="google_invite",
            created_by_id=None,
            expires_in_minutes=60,
            metadata_json=json.dumps({"email": "invited@example.com", "name": "X", "role": "user"}),
        )
        session.commit()
        resolved, reason = _find_or_create_oauth_user(
            session,
            {"sub": "sub-other", "email": "someone-else@example.com", "email_verified": True},
            invite_token=token,
        )
        assert resolved is None and reason == "invite_email_mismatch"


def test_no_match_no_invite_is_rejected(app, session):
    from src.backend.manage_authentication import _find_or_create_oauth_user
    resolved, reason = _find_or_create_oauth_user(
        session,
        {"sub": "sub-stranger", "email": "stranger@example.com", "email_verified": True},
        invite_token=None,
    )
    assert resolved is None and reason == "no_match"
