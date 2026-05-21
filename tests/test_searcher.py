"""Tests for tradera_indexer.searcher (Searcher)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tradera_indexer.models import AuctionType, Category, Item, ItemStatus
from tradera_indexer.searcher import Searcher


def _item(item_id: str, title: str, **kwargs) -> Item:
    defaults = dict(
        price=100.0,
        category_id=25,
        category_name="Sport",
        auction_type=AuctionType.auction,
        status=ItemStatus.unsold,
        indexed_at=datetime.now(tz=UTC),
    )
    defaults.update(kwargs)
    return Item(item_id=item_id, title=title, **defaults)


@pytest.fixture()
def searcher(config):
    with Searcher(config) as s:
        # Pre-populate the DB via the underlying Database instance.
        s._db.upsert_items([
            _item("1", "Blå cykel", category_id=25, category_name="Sport", price=300),
            _item("2", "Röd bil", category_id=10, category_name="Fordon", price=5000),
            _item(
                "3", "Gammal bok", category_id=11, category_name="Böcker",
                price=50, auction_type=AuctionType.buy_now,
            ),
        ])
        yield s


# ---------------------------------------------------------------------------
# Basic search
# ---------------------------------------------------------------------------


def test_search_returns_all_when_empty_query(searcher):
    result = searcher.search("")
    assert result.total_count == 3


def test_search_fts(searcher):
    result = searcher.search("cykel")
    assert len(result.items) == 1
    assert result.items[0].item_id == "1"


def test_search_category_filter(searcher):
    result = searcher.search("", category=Category.sport_fritid)
    assert len(result.items) == 1
    assert result.items[0].category_name == "Sport"


def test_search_price_range(searcher):
    result = searcher.search("", price_min=100, price_max=1000)
    ids = {i.item_id for i in result.items}
    assert "1" in ids          # 300 SEK – within range
    assert "2" not in ids      # 5000 SEK – too expensive
    assert "3" not in ids      # 50 SEK – too cheap


def test_search_auction_type(searcher):
    result = searcher.search("", auction_type=AuctionType.buy_now)
    assert all(i.auction_type == AuctionType.buy_now for i in result.items)


def test_search_pagination(searcher):
    page1 = searcher.search("", limit=2, offset=0)
    page2 = searcher.search("", limit=2, offset=2)
    assert len(page1.items) == 2
    assert len(page2.items) == 1
    ids_p1 = {i.item_id for i in page1.items}
    ids_p2 = {i.item_id for i in page2.items}
    assert not ids_p1 & ids_p2


# ---------------------------------------------------------------------------
# get_item
# ---------------------------------------------------------------------------


def test_get_item(searcher):
    item = searcher.get_item("1")
    assert item is not None
    assert item.title == "Blå cykel"


def test_get_item_not_found(searcher):
    assert searcher.get_item("nonexistent") is None


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def test_stats(searcher):
    s = searcher.stats()
    assert s["total_items"] == 3
    cat_names = {c["name"] for c in s["top_categories"]}
    assert "Sport" in cat_names


# ---------------------------------------------------------------------------
# Context manager guard
# ---------------------------------------------------------------------------


def test_searcher_requires_context_manager(config):
    searcher = Searcher(config)
    with pytest.raises(RuntimeError, match="context manager"):
        searcher.search("test")
