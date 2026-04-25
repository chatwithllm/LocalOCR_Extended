"""Unit tests for the chat-assistant temporal-intent extractor and
shopping-activity aggregator. In-memory SQLite, no Flask, no network.
"""
import os

# Configure env BEFORE importing the project — chat_assistant.py touches
# AIModelConfig at import time which expects FERNET_SECRET_KEY.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FERNET_SECRET_KEY", "test-fernet-key-for-unit-tests-only")
os.environ.setdefault("INITIAL_ADMIN_TOKEN", "test-admin-token")

import pytest

from src.backend.chat_assistant import _extract_temporal_intent


@pytest.mark.parametrize(
    "message",
    [
        "When did we shop lately?",
        "how often do we shop",
        "what's our consumption rate?",
        "show me recent shopping",
        "when was the last trip to the store",
        "we go pretty frequently right?",
        "how much are we consuming",
        "trend in our buying",
    ],
)
def test_temporal_intent_positive(message):
    assert _extract_temporal_intent(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "how much did we spend on milk last month",
        "where do property taxes belong",
        "list uncategorized receipts",
        "show me the top stores",
        "what's the grocery total",
        "",
    ],
)
def test_temporal_intent_negative(message):
    assert _extract_temporal_intent(message) is False
