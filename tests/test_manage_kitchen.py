# tests/test_manage_kitchen.py
import pytest
from src.backend.manage_kitchen import category_for_product, DEFAULT_CATEGORIES, CATEGORY_EMOJI


class _StubProduct:
    def __init__(self, category):
        self.category = category


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Produce", "Produce"),
        ("produce", "Produce"),
        ("PRODUCE", "Produce"),
        ("Vegetables", "Produce"),
        ("Fruit", "Produce"),
        ("Fruits", "Produce"),
        ("Meat", "Meat"),
        ("Poultry", "Meat"),
        ("Seafood", "Meat"),
        ("Fish", "Meat"),
        ("Dairy", "Dairy"),
        ("Cheese", "Dairy"),
        ("Yogurt", "Dairy"),
        ("Bakery", "Bakery"),
        ("Bread", "Bakery"),
        ("Pantry", "Pantry"),
        ("Snacks", "Pantry"),
        ("Beverages", "Pantry"),
        ("Spices", "Pantry"),
        ("Condiments", "Pantry"),
        (None, "Other"),
        ("", "Other"),
        ("   ", "Other"),
        ("weird random thing", "Other"),
    ],
)
def test_category_for_product_truth_table(raw, expected):
    assert category_for_product(_StubProduct(raw)) == expected


def test_default_categories_are_in_emoji_map():
    for cat in DEFAULT_CATEGORIES:
        assert cat in CATEGORY_EMOJI


def test_default_categories_order():
    assert DEFAULT_CATEGORIES == [
        "Produce", "Meat", "Dairy", "Bakery", "Pantry", "Other",
    ]
