"""FloorObligation model and CRUD API tests."""
from __future__ import annotations
import os
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("MQTT_BROKER", "localhost")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-tg-token")
os.environ.setdefault("SESSION_SECRET", "test-secret")


@pytest.fixture
def app(tmp_path):
    import src.backend.create_flask_application as cfa
    import src.backend.initialize_database_schema as schema_module
    from src.backend.create_flask_application import create_app

    db_url = f"sqlite:///{tmp_path / 'floor_test.db'}"
    os.environ["DATABASE_URL"] = db_url
    schema_module.DATABASE_URL = db_url
    cfa._engine = None
    cfa._SessionFactory = None

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _auth(client):
    return {"Authorization": "Bearer test-admin-token"}


def test_floor_obligation_table_exists(app):
    from src.backend.initialize_database_schema import FloorObligation
    from src.backend.create_flask_application import _engine
    from sqlalchemy import inspect
    insp = inspect(_engine)
    assert "floor_obligations" in insp.get_table_names()
