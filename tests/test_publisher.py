"""Tests for tradera_indexer.publisher (Publisher) and soap_client."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradera_indexer.models import NewListing
from tradera_indexer.publisher import Publisher, PublisherError
from tradera_indexer.soap_client import SOAPError, TraderaSOAPClient


def _valid_listing(**overrides) -> NewListing:
    defaults = dict(
        title="Retro cykel",
        description="Fint skick, minimal slitage.",
        category_id=25,
        start_price=200.0,
        buy_now_price=500.0,
        duration_days=7,
        item_condition="used",
    )
    defaults.update(overrides)
    return NewListing(**defaults)


# ---------------------------------------------------------------------------
# Publisher.publish
# ---------------------------------------------------------------------------


def test_publish_calls_soap_add_item(config):
    mock_soap = MagicMock(spec=TraderaSOAPClient)
    mock_soap.add_item.return_value = {"ItemId": 9876}

    with patch("tradera_indexer.publisher.TraderaSOAPClient", return_value=mock_soap):
        with patch.object(mock_soap, "connect", return_value=None):
            with patch.object(mock_soap, "close", return_value=None):
                with Publisher(config) as pub:
                    pub._soap = mock_soap
                    result = pub.publish(_valid_listing())

    assert result["ItemId"] == 9876
    mock_soap.add_item.assert_called_once()


def test_publish_raises_on_validation_error(config):
    mock_soap = MagicMock(spec=TraderaSOAPClient)

    with patch("tradera_indexer.publisher.TraderaSOAPClient", return_value=mock_soap):
        with patch.object(mock_soap, "connect"):
            with patch.object(mock_soap, "close"):
                with Publisher(config) as pub:
                    pub._soap = mock_soap
                    with pytest.raises(PublisherError, match="validation"):
                        # Title too short → validation error
                        pub.publish(_valid_listing(title="AB"))


def test_publish_raises_on_soap_error(config):
    mock_soap = MagicMock(spec=TraderaSOAPClient)
    mock_soap.add_item.side_effect = SOAPError("SOAP fault")

    with patch("tradera_indexer.publisher.TraderaSOAPClient", return_value=mock_soap):
        with patch.object(mock_soap, "connect"):
            with patch.object(mock_soap, "close"):
                with Publisher(config) as pub:
                    pub._soap = mock_soap
                    with pytest.raises(PublisherError, match="SOAP"):
                        pub.publish(_valid_listing())


# ---------------------------------------------------------------------------
# Publisher.update
# ---------------------------------------------------------------------------


def test_update_calls_soap_update_item(config):
    mock_soap = MagicMock(spec=TraderaSOAPClient)
    mock_soap.update_item.return_value = {"ItemId": 42}

    with patch("tradera_indexer.publisher.TraderaSOAPClient", return_value=mock_soap):
        with patch.object(mock_soap, "connect"):
            with patch.object(mock_soap, "close"):
                with Publisher(config) as pub:
                    pub._soap = mock_soap
                    result = pub.update(42, _valid_listing())

    assert result == {"ItemId": 42}
    mock_soap.update_item.assert_called_once()
    # Verify item_id was injected
    payload = mock_soap.update_item.call_args[0][0]
    assert payload["ItemId"] == 42


# ---------------------------------------------------------------------------
# Publisher.end
# ---------------------------------------------------------------------------


def test_end_calls_soap_end_item(config):
    mock_soap = MagicMock(spec=TraderaSOAPClient)
    mock_soap.end_item.return_value = {}

    with patch("tradera_indexer.publisher.TraderaSOAPClient", return_value=mock_soap):
        with patch.object(mock_soap, "connect"):
            with patch.object(mock_soap, "close"):
                with Publisher(config) as pub:
                    pub._soap = mock_soap
                    pub.end(99)

    mock_soap.end_item.assert_called_once_with(99, reason="NotSold")


# ---------------------------------------------------------------------------
# Publisher._build_soap_payload
# ---------------------------------------------------------------------------


def test_build_soap_payload_maps_correctly():
    listing = _valid_listing(
        title="  Cykel  ",
        description="  Fin  ",
        item_condition="new",
        buy_now_price=None,
        images=["https://img.example.com/photo.jpg"],
    )
    payload = Publisher._build_soap_payload(listing)
    assert payload["Title"] == "Cykel"
    assert payload["Description"] == "Fin"
    assert payload["ItemCondition"] == "New"
    assert payload["BuyNowPrice"] is None
    assert "photo.jpg" in payload["Images"]["ImageUrl"][0]


def test_build_soap_payload_uses_default_shipping():
    listing = _valid_listing(shipping_options=[])
    payload = Publisher._build_soap_payload(listing)
    assert payload["ShippingOptions"]["ShippingOption"]


# ---------------------------------------------------------------------------
# Publisher context manager guard
# ---------------------------------------------------------------------------


def test_publisher_not_started_raises(config):
    pub = Publisher(config)
    with pytest.raises(RuntimeError, match="context manager"):
        pub.publish(_valid_listing())


# ---------------------------------------------------------------------------
# SOAPError
# ---------------------------------------------------------------------------


def test_soap_error_is_exception():
    exc = SOAPError("something went wrong")
    assert str(exc) == "something went wrong"
    assert isinstance(exc, Exception)
