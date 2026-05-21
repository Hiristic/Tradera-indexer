"""Tests for tradera_indexer.client (TraderaClient)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradera_indexer.client import TraderaAPIError, TraderaClient
from tradera_indexer.models import AuctionType, SearchQuery


@pytest.fixture()
def client(config) -> TraderaClient:
    return TraderaClient(config)


# ---------------------------------------------------------------------------
# _parse_item
# ---------------------------------------------------------------------------


def test_parse_item_full():
    raw = {
        "id": "12345",
        "shortDescription": "Retro cykel",
        "longDescription": "Bra skick.",
        "price": 450,
        "buyNowPrice": 900,
        "shippingCost": 79,
        "sellerAlias": "cyklare99",
        "sellerId": 5555,
        "categoryId": 25,
        "categoryName": "Sport & Fritid",
        "imageUrl": "https://img.tradera.net/image.jpg",
        "itemUrl": "/item/12345",
        "itemType": "Auction",
        "endTime": "2024-12-31T23:59:59Z",
        "numberOfBids": 3,
    }
    item = TraderaClient._parse_item(raw)
    assert item is not None
    assert item.item_id == "12345"
    assert item.title == "Retro cykel"
    assert item.description == "Bra skick."
    assert item.price == 450.0
    assert item.buy_now_price == 900.0
    assert item.shipping_cost == 79.0
    assert item.seller_alias == "cyklare99"
    assert item.seller_id == 5555
    assert item.category_id == 25
    assert item.category_name == "Sport & Fritid"
    assert item.auction_type == AuctionType.auction
    assert item.bid_count == 3
    assert item.end_time is not None
    assert item.end_time.year == 2024


def test_parse_item_buy_now():
    raw = {"id": "99", "itemType": "FixedPrice", "price": 199, "shortDescription": "Bok"}
    item = TraderaClient._parse_item(raw)
    assert item is not None
    assert item.auction_type == AuctionType.buy_now


def test_parse_item_seller_as_dict():
    raw = {
        "id": "7",
        "shortDescription": "Lampa",
        "seller": {"alias": "lamp_store"},
    }
    item = TraderaClient._parse_item(raw)
    assert item is not None
    assert item.seller_alias == "lamp_store"


def test_parse_item_missing_id_returns_none():
    assert TraderaClient._parse_item({}) is None
    assert TraderaClient._parse_item({"id": ""}) is None


def test_parse_item_bad_end_time():
    raw = {"id": "1", "shortDescription": "X", "endTime": "not-a-date"}
    item = TraderaClient._parse_item(raw)
    assert item is not None
    assert item.end_time is None


# ---------------------------------------------------------------------------
# search() – with mocked HTTP
# ---------------------------------------------------------------------------


def _make_api_response(n_items: int = 2, total: int = 5) -> dict:
    items = [
        {
            "id": str(i),
            "shortDescription": f"Item {i}",
            "price": float(i * 100),
            "itemType": "Auction",
        }
        for i in range(1, n_items + 1)
    ]
    return {"items": items, "totalCount": total}


def test_search_calls_correct_endpoint(config):
    mock_response = MagicMock()
    mock_response.json.return_value = _make_api_response(2, 2)
    mock_response.raise_for_status = MagicMock()

    mock_http = MagicMock()
    mock_http.get = MagicMock(return_value=MagicMock(status_code=200))
    mock_http.post.return_value = mock_response

    client = TraderaClient(config)
    client._http = mock_http

    result = client.search(SearchQuery(query="cykel"))
    assert len(result.items) == 2
    assert result.total_count == 2
    mock_http.post.assert_called_once()
    call_args = mock_http.post.call_args
    assert "/independent-search" in call_args[0][0]


def test_search_raises_on_http_error(config):
    import httpx

    mock_http = MagicMock()
    mock_http.get = MagicMock(return_value=MagicMock(status_code=200))
    mock_http.post.side_effect = httpx.HTTPError("connection error")

    client = TraderaClient(config)
    client._http = mock_http

    with pytest.raises(TraderaAPIError, match="connection error"):
        client.search(SearchQuery(query="test"))


def test_search_all_pages_stops_when_no_more(config):
    """search_all_pages should stop after the first page if has_more is False."""
    mock_response = MagicMock()
    mock_response.json.return_value = _make_api_response(2, 2)  # total==len → no more
    mock_response.raise_for_status = MagicMock()

    mock_http = MagicMock()
    mock_http.get = MagicMock()
    mock_http.post.return_value = mock_response

    client = TraderaClient(config)
    client._http = mock_http

    result = client.search_all_pages(SearchQuery(query="cykel"), max_pages=5)
    assert mock_http.post.call_count == 1  # only one page needed
    assert len(result.items) == 2


def test_client_context_manager_requires_enter(config):
    client = TraderaClient(config)
    with pytest.raises(RuntimeError, match="context manager"):
        client.search(SearchQuery(query="test"))
