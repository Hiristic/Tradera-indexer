"""Publisher: validates and publishes new Tradera listings via the SOAP API."""
from __future__ import annotations

import logging

from .config import Config
from .models import NewListing
from .soap_client import SOAPError, TraderaSOAPClient

logger = logging.getLogger(__name__)

# Default shipping option used when the caller provides none.
_DEFAULT_SHIPPING = [
    {
        "Type": "Standard",
        "Cost": 0,
        "IsTracked": False,
    }
]

# Default payment options accepted by Tradera.
_DEFAULT_PAYMENT = ["Swish", "BankTransfer"]


class PublisherError(Exception):
    """Raised when publishing fails due to validation or API errors."""


class Publisher:
    """High-level interface for creating Tradera listings.

    Usage::

        config = Config.from_env()
        with Publisher(config) as pub:
            listing = NewListing(
                title="Retro cykel",
                description="Fint skick, inga repor.",
                category_id=25,  # sport_fritid
                start_price=200,
                buy_now_price=500,
                duration_days=7,
            )
            result = pub.publish(listing)
            print("Published item ID:", result["ItemId"])
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._soap: TraderaSOAPClient | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> Publisher:
        self._soap = TraderaSOAPClient(self.config)
        self._soap.connect()
        return self

    def __exit__(self, *_args: object) -> None:
        if self._soap is not None:
            self._soap.close()
            self._soap = None

    def _require_soap(self) -> TraderaSOAPClient:
        if self._soap is None:
            raise RuntimeError("Publisher not started. Use as context manager.")
        return self._soap

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish(self, listing: NewListing) -> dict:
        """Validate *listing* and create it on Tradera.

        Returns the SOAP response dict on success (contains ``ItemId``).
        Raises :class:`PublisherError` on validation failure or API error.
        """
        errors = listing.validate()
        if errors:
            raise PublisherError(
                "Listing validation failed:\n" + "\n".join(f"  • {e}" for e in errors)
            )

        soap = self._require_soap()
        item_data = self._build_soap_payload(listing)

        try:
            result = soap.add_item(item_data)
        except SOAPError as exc:
            raise PublisherError(f"SOAP API error while publishing: {exc}") from exc

        item_id = result.get("ItemId") or result.get("itemId")
        logger.info("Successfully published listing '%s' (ItemId=%s)", listing.title, item_id)
        return result

    def update(self, item_id: int, listing: NewListing) -> dict:
        """Update an existing Tradera listing.

        Args:
            item_id: The Tradera item ID to update.
            listing: New data for the listing (fully replaces existing fields).
        Returns the SOAP response dict.
        """
        errors = listing.validate()
        if errors:
            raise PublisherError(
                "Listing validation failed:\n" + "\n".join(f"  • {e}" for e in errors)
            )

        soap = self._require_soap()
        item_data = self._build_soap_payload(listing)
        item_data["ItemId"] = item_id

        try:
            result = soap.update_item(item_data)
        except SOAPError as exc:
            raise PublisherError(f"SOAP API error while updating: {exc}") from exc

        logger.info("Successfully updated listing (ItemId=%d)", item_id)
        return result

    def end(self, item_id: int, reason: str = "NotSold") -> dict:
        """End an active listing early.

        Args:
            item_id: The Tradera item ID.
            reason:  ``"NotSold"`` (default) or ``"Sold"``.
        """
        soap = self._require_soap()
        try:
            result = soap.end_item(item_id, reason=reason)
        except SOAPError as exc:
            raise PublisherError(f"SOAP API error while ending item: {exc}") from exc

        logger.info("Ended listing (ItemId=%d, reason=%s)", item_id, reason)
        return result

    def get_my_listings(self) -> list[dict]:
        """Return all current listings for the authenticated seller."""
        soap = self._require_soap()
        try:
            return soap.get_seller_items()
        except SOAPError as exc:
            raise PublisherError(f"SOAP API error while fetching listings: {exc}") from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_soap_payload(listing: NewListing) -> dict:
        """Map a :class:`NewListing` to the dict expected by AddItem/UpdateItem."""
        shipping = listing.shipping_options if listing.shipping_options else _DEFAULT_SHIPPING
        return {
            "Title": listing.title.strip(),
            "Description": listing.description.strip(),
            "CategoryId": listing.category_id,
            "StartingBid": listing.start_price,
            "BuyNowPrice": listing.buy_now_price,
            "Duration": listing.duration_days,
            "ShippingOptions": {"ShippingOption": shipping},
            "PaymentOptions": {"PaymentOption": _DEFAULT_PAYMENT},
            "ItemCondition": "New" if listing.item_condition == "new" else "Used",
            "AcceptBidding": listing.accept_bidding,
            "Images": (
                {"ImageUrl": listing.images} if listing.images else None
            ),
        }
