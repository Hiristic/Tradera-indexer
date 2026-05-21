"""Tests for tradera_indexer.indexer (Indexer)."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from tradera_indexer.indexer import Indexer
from tradera_indexer.models import (
    AuctionType,
    Category,
    Item,
    ItemStatus,
    SearchResult,
)


def _make_item(item_id: str, title: str = "Test item") -> Item:
    return Item(
        item_id=item_id,
        title=title,
        price=100.0,
        auction_type=AuctionType.auction,
        status=ItemStatus.unsold,
        indexed_at=datetime.now(tz=UTC),
    )


def _make_result(items, total=None, has_more=False) -> SearchResult:
    return SearchResult(
        items=items,
        total_count=total if total is not None else len(items),
        page=1,
        has_more=has_more,
    )


# ---------------------------------------------------------------------------
# index_query
# ---------------------------------------------------------------------------


def test_index_query_single_page(config, tmp_path):
    config.db_path = str(tmp_path / "test.db")

    mock_client = MagicMock()
    mock_client.search.return_value = _make_result(
        [_make_item("1"), _make_item("2")], total=2, has_more=False
    )

    indexer = Indexer(config)
    with patch("tradera_indexer.indexer.TraderaClient", return_value=mock_client):
        with patch.object(mock_client, "__enter__", return_value=mock_client):
            with patch.object(mock_client, "__exit__", return_value=None):
                with indexer:
                    count = indexer.index_query("cykel")

    assert count == 2


def test_index_query_multiple_pages(config, tmp_path):
    config.db_path = str(tmp_path / "test.db")
    config.request_delay = 0  # speed up tests

    page1_items = [_make_item(str(i)) for i in range(1, 4)]
    page2_items = [_make_item(str(i)) for i in range(4, 6)]

    def fake_search(query):
        if query.page == 1:
            return _make_result(page1_items, total=5, has_more=True)
        return _make_result(page2_items, total=5, has_more=False)

    mock_client = MagicMock()
    mock_client.search.side_effect = fake_search

    indexer = Indexer(config)
    with patch("tradera_indexer.indexer.TraderaClient", return_value=mock_client):
        with patch.object(mock_client, "__enter__", return_value=mock_client):
            with patch.object(mock_client, "__exit__", return_value=None):
                with indexer:
                    count = indexer.index_query("cykel", max_pages=5)

    assert count == 5


def test_index_query_stops_on_api_error(config, tmp_path):
    from tradera_indexer.client import TraderaAPIError

    config.db_path = str(tmp_path / "test.db")
    config.request_delay = 0

    mock_client = MagicMock()
    mock_client.search.side_effect = TraderaAPIError("server error")

    indexer = Indexer(config)
    with patch("tradera_indexer.indexer.TraderaClient", return_value=mock_client):
        with patch.object(mock_client, "__enter__", return_value=mock_client):
            with patch.object(mock_client, "__exit__", return_value=None):
                with indexer:
                    count = indexer.index_query("cykel")

    assert count == 0  # error → nothing indexed


def test_index_query_max_items_limit(config, tmp_path):
    config.db_path = str(tmp_path / "test.db")
    config.max_items_per_category = 2
    config.request_delay = 0
    config.items_per_page = 2

    # Page 1 returns 2 items and claims there are more
    items = [_make_item(str(i)) for i in range(2)]
    mock_client = MagicMock()
    mock_client.search.return_value = _make_result(items, total=100, has_more=True)

    indexer = Indexer(config)
    with patch("tradera_indexer.indexer.TraderaClient", return_value=mock_client):
        with patch.object(mock_client, "__enter__", return_value=mock_client):
            with patch.object(mock_client, "__exit__", return_value=None):
                with indexer:
                    count = indexer.index_query("cykel", max_pages=100)

    # Should stop after 2 items (= max_items_per_category)
    assert count == 2
    assert mock_client.search.call_count == 1


# ---------------------------------------------------------------------------
# index_category
# ---------------------------------------------------------------------------


def test_index_category_passes_category(config, tmp_path):
    config.db_path = str(tmp_path / "test.db")
    config.request_delay = 0

    mock_client = MagicMock()
    mock_client.search.return_value = _make_result([], total=0, has_more=False)

    indexer = Indexer(config)
    with patch("tradera_indexer.indexer.TraderaClient", return_value=mock_client):
        with patch.object(mock_client, "__enter__", return_value=mock_client):
            with patch.object(mock_client, "__exit__", return_value=None):
                with indexer:
                    indexer.index_category(Category.sport_fritid)

    called_query = mock_client.search.call_args[0][0]
    assert called_query.category == Category.sport_fritid


# ---------------------------------------------------------------------------
# Context manager guard
# ---------------------------------------------------------------------------


def test_indexer_not_started_raises(config):
    indexer = Indexer(config)
    with pytest.raises(RuntimeError, match="context manager"):
        indexer.index_query("test")
