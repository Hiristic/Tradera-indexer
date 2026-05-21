"""Tests for tradera_indexer.models."""
from __future__ import annotations

from datetime import UTC

import pytest

from tradera_indexer.models import (
    VALID_DURATIONS,
    AuctionType,
    Category,
    Item,
    NewListing,
    Sorting,
)

# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------


def test_item_to_dict_roundtrip():
    item = Item(item_id="123", title="Cykel", price=500.0, seller_alias="testare")
    d = item.to_dict()
    assert d["item_id"] == "123"
    assert d["title"] == "Cykel"
    assert d["price"] == 500.0
    assert d["seller_alias"] == "testare"
    assert d["end_time"] is None
    assert d["indexed_at"] is None


def test_item_to_dict_with_dates():
    from datetime import datetime

    dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
    item = Item(item_id="1", title="T", end_time=dt, indexed_at=dt)
    d = item.to_dict()
    assert "2024-06-15" in d["end_time"]
    assert "2024-06-15" in d["indexed_at"]


# ---------------------------------------------------------------------------
# NewListing.validate()
# ---------------------------------------------------------------------------


def _valid_listing(**kwargs) -> NewListing:
    defaults = dict(
        title="En fin cykel",
        description="Bra skick",
        category_id=25,
        start_price=100.0,
        duration_days=7,
        item_condition="used",
    )
    defaults.update(kwargs)
    return NewListing(**defaults)


def test_valid_listing_no_errors():
    assert _valid_listing().validate() == []


def test_title_too_short():
    errors = _valid_listing(title="AB").validate()
    assert any("3 characters" in e for e in errors)


def test_title_too_long():
    errors = _valid_listing(title="X" * 51).validate()
    assert any("50 characters" in e for e in errors)


def test_description_required():
    errors = _valid_listing(description="  ").validate()
    assert any("Description" in e for e in errors)


def test_category_required():
    errors = _valid_listing(category_id=0).validate()
    assert any("Category" in e for e in errors)


def test_start_price_must_be_positive():
    for bad_price in (0, -1, -100):
        errors = _valid_listing(start_price=bad_price).validate()
        assert any("positive" in e for e in errors), f"Expected error for price={bad_price}"


def test_buy_now_must_be_gte_start():
    errors = _valid_listing(start_price=200, buy_now_price=100).validate()
    assert any("Buy-now" in e for e in errors)


def test_buy_now_equal_start_is_valid():
    assert _valid_listing(start_price=100, buy_now_price=100).validate() == []


def test_invalid_duration():
    errors = _valid_listing(duration_days=99).validate()
    assert any("Duration" in e for e in errors)


@pytest.mark.parametrize("days", VALID_DURATIONS)
def test_valid_durations(days):
    assert _valid_listing(duration_days=days).validate() == []


def test_invalid_condition():
    errors = _valid_listing(item_condition="mint").validate()
    assert any("condition" in e for e in errors)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def test_category_enum_covers_expected_entries():
    names = {c.name for c in Category}
    for name in ("sport_fritid", "hemelektronik", "ovrigt", "bocker_tidningar"):
        assert name in names, f"Expected {name!r} in Category enum"


def test_sorting_enum():
    assert Sorting.best_hit == "Relevance"
    assert Sorting.time_left == "TimeLeft"


def test_auction_type_enum():
    assert AuctionType.all == "All"
    assert AuctionType.buy_now == "FixedPrice"
