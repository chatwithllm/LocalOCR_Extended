import os
os.environ["DATABASE_URL"] = "sqlite://"
import time
import pytest

@pytest.fixture(scope="module")
def app():
    from src.backend.create_flask_application import create_app
    a = create_app(); a.config["TESTING"] = True
    yield a

def test_job_runs_and_completes(app, monkeypatch):
    import src.backend.manage_recommendations as mr
    monkeypatch.setattr(mr, "refresh_recommendation_cache", lambda: {"count": 2, "source": "ai"})
    job_id = mr.start_refresh_job()
    st = None
    for _ in range(60):
        st = mr.get_job_status(job_id)
        if st and st["status"] in {"done", "error"}:
            break
        time.sleep(0.05)
    assert st["status"] == "done", st
    assert st["summary"]["count"] == 2
