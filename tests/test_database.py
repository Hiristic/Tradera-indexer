"""Tests for tradera_indexer.database (Database + FTS5)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tradera_indexer.database import Database
from tradera_indexer.models import AuctionType, Category, Item, ItemStatus, SearchQuery


def _item(item_id: str, title: str, **kwargs) -> Item:
    defaults = dict(
        description="",
        price=100.0,
        seller_alias="seller",
        category_id=25,
        category_name="Sport",
        auction_type=AuctionType.auction,
        status=ItemStatus.unsold,
        indexed_at=datetime.now(tz=UTC),
    )
    defaults.update(kwargs)
    return Item(item_id=item_id, title=title, **defaults)


# ---------------------------------------------------------------------------
# Basic CRUD
# ---------------------------------------------------------------------------


def test_upsert_and_retrieve(db):
    item = _item("1", "Röd cykel")
    db.upsert_item(item)
    fetched = db.get_item("1")
    assert fetched is not None
    assert fetched.title == "Röd cykel"
    assert fetched.price == 100.0


def test_upsert_updates_existing(db):
    item = _item("42", "Gammal titel")
    db.upsert_item(item)
    updated = _item("42", "Ny titel", price=200.0)
    db.upsert_item(updated)
    fetched = db.get_item("42")
    assert fetched.title == "Ny titel"
    assert fetched.price == 200.0


def test_get_item_nonexistent_returns_none(db):
    assert db.get_item("does-not-exist") is None


def test_delete_item(db):
    db.upsert_item(_item("del", "ToDelete"))
    db.delete_item("del")
    assert db.get_item("del") is None


def test_count(db):
    assert db.count() == 0
    db.upsert_items([_item(str(i), f"Item {i}") for i in range(5)])
    assert db.count() == 5


def test_clear(db):
    db.upsert_items([_item(str(i), f"Item {i}") for i in range(3)])
    db.clear()
    assert db.count() == 0


# ---------------------------------------------------------------------------
# FTS5 search
# ---------------------------------------------------------------------------


def test_fts_search_by_title(db):
    db.upsert_item(_item("1", "Blå cykel till salu"))
    db.upsert_item(_item("2", "Röd bil till salu"))
    results = db.search(SearchQuery(query="cykel"))
    ids = {r.item_id for r in results}
    assert "1" in ids
    assert "2" not in ids


def test_fts_search_by_description(db):
    db.upsert_item(_item("1", "Artikel", description="sällsynt samlarobjekt"))
    db.upsert_item(_item("2", "Annan artikel", description="vanlig pryl"))
    results = db.search(SearchQuery(query="samlarobjekt"))
    assert any(r.item_id == "1" for r in results)


def test_fts_empty_query_returns_all(db):
    db.upsert_items([_item(str(i), f"Item {i}") for i in range(4)])
    results = db.search(SearchQuery(query=""))
    assert len(results) == 4


def test_search_category_filter(db):
    db.upsert_item(_item("1", "Sport item", category_id=25))
    db.upsert_item(_item("2", "Book item", category_id=11))
    results = db.search(SearchQuery(query="", category=Category.sport_fritid))
    assert all(r.category_id == 25 for r in results)
    assert len(results) == 1


def test_search_price_filter(db):
    db.upsert_item(_item("cheap", "Billig sak", price=50.0))
    db.upsert_item(_item("expensive", "Dyr sak", price=5000.0))
    results = db.search(SearchQuery(query="", price_max=200))
    ids = {r.item_id for r in results}
    assert "cheap" in ids
    assert "expensive" not in ids


def test_search_auction_type_filter(db):
    db.upsert_item(_item("auction_item", "Auktion", auction_type=AuctionType.auction))
    db.upsert_item(
        _item("buynow_item", "Köp nu", auction_type=AuctionType.buy_now)
    )
    results = db.search(SearchQuery(query="", auction_type=AuctionType.buy_now))
    ids = {r.item_id for r in results}
    assert "buynow_item" in ids
    assert "auction_item" not in ids


def test_search_pagination(db):
    db.upsert_items([_item(str(i), f"Item {i}") for i in range(10)])
    first = db.search(SearchQuery(query=""), limit=5, offset=0)
    second = db.search(SearchQuery(query=""), limit=5, offset=5)
    assert len(first) == 5
    assert len(second) == 5
    # No overlap
    first_ids = {r.item_id for r in first}
    second_ids = {r.item_id for r in second}
    assert not first_ids & second_ids


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def test_stats(db):
    db.upsert_items([
        _item("1", "A", category_name="Sport"),
        _item("2", "B", category_name="Sport"),
        _item("3", "C", category_name="Böcker"),
    ])
    s = db.stats()
    assert s["total_items"] == 3
    assert s["last_indexed"] is not None
    cat_names = {c["name"] for c in s["top_categories"]}
    assert "Sport" in cat_names


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


def test_context_manager(tmp_path):
    db_path = str(tmp_path / "cm_test.db")
    with Database(db_path) as db:
        db.upsert_item(_item("x", "Test"))
        assert db.count() == 1


def test_requires_connection(tmp_path):
    db = Database(str(tmp_path / "nc.db"))
    with pytest.raises(RuntimeError, match="not connected"):
        db.count()
