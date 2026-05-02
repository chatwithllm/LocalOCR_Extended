"""Regression guard: rebuild_active_inventory must not be a recurring job."""
import re

import src.backend.schedule_daily_recommendations as sched


def test_rebuild_active_inventory_is_not_scheduled():
    text = open(sched.__file__).read()
    matches = re.findall(r"add_job\(\s*rebuild_active_inventory", text)
    assert not matches, "rebuild_active_inventory must not be registered as a recurring job"
