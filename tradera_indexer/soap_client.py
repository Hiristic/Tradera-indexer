"""Tradera SOAP API client (ListingService) used for publishing listings."""
from __future__ import annotations

import logging
from typing import Any

from .config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import of zeep so that the rest of the package works without it.
# ---------------------------------------------------------------------------

try:
    import zeep as _zeep  # noqa: F401

    _ZEEP_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ZEEP_AVAILABLE = False


class SOAPError(Exception):
    """Raised when the Tradera SOAP API reports an error."""


class TraderaSOAPClient:
    """Low-level wrapper around the Tradera SOAP ListingService.

    The ``zeep`` library is required for this client.  Install it with::

        pip install zeep

    Credentials are read from the :class:`~tradera_indexer.config.Config`
    object.  *app_id* and *app_key* are always required; *user_id* and
    *user_token* are needed for seller operations (e.g. ``AddItem``).
    """

    def __init__(self, config: Config) -> None:
        if not _ZEEP_AVAILABLE:
            raise ImportError(
                "The 'zeep' package is required for SOAP publishing. "
                "Install it with:  pip install zeep"
            )
        self.config = config
        self._listing_client: Any | None = None

    # ------------------------------------------------------------------
    # Initialisation / teardown
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Initialise the zeep SOAP client (fetches the WSDL)."""
        from zeep import Client  # type: ignore[import]

        self._listing_client = Client(self.config.listing_service_wsdl)
        logger.debug("SOAP listing client initialised (%s)", self.config.listing_service_wsdl)

    def close(self) -> None:
        self._listing_client = None

    def __enter__(self) -> TraderaSOAPClient:
        self.connect()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_client(self) -> Any:
        if self._listing_client is None:
            raise RuntimeError(
                "SOAPClient not connected. Use as context manager or call connect()."
            )
        return self._listing_client

    def _make_request_header(self, *, authenticated: bool = True) -> dict:
        """Build the SOAP RequestHeader dict expected by the Tradera API."""
        header: dict[str, Any] = {
            "AppId": self.config.app_id,
            "AppKey": self.config.app_key,
        }
        if authenticated:
            if not self.config.user_token or not self.config.user_id:
                raise SOAPError(
                    "user_token and user_id are required for authenticated SOAP calls. "
                    "Set TRADERA_USER_TOKEN and TRADERA_USER_ID in your environment."
                )
            header["Token"] = self.config.user_token
            header["UserId"] = self.config.user_id
        return header

    def _call(self, method: str, *, authenticated: bool = True, **kwargs: Any) -> Any:
        """Call a SOAP method, wrapping zeep Fault in :class:`SOAPError`."""
        from zeep.exceptions import Fault  # type: ignore[import]

        client = self._require_client()
        header = self._make_request_header(authenticated=authenticated)
        try:
            service_method = getattr(client.service, method)
            result = service_method(_soapheaders=header, **kwargs)
            logger.debug("SOAP %s → %r", method, result)
            return result
        except Fault as exc:
            raise SOAPError(f"SOAP fault calling {method}: {exc}") from exc
        except Exception as exc:
            raise SOAPError(f"Unexpected error calling {method}: {exc}") from exc

    # ------------------------------------------------------------------
    # Public ListingService methods
    # ------------------------------------------------------------------

    def add_item(self, item_data: dict) -> dict:
        """Create a new listing on Tradera.

        *item_data* should match the ``AddItem`` SOAP request body.  Use
        :class:`~tradera_indexer.publisher.Publisher` for a higher-level
        interface that handles validation and mapping.

        Returns the SOAP response as a dict.
        """
        result = self._call("AddItem", authenticated=True, **item_data)
        return self._to_dict(result)

    def update_item(self, item_data: dict) -> dict:
        """Update an existing listing.

        *item_data* must include ``ItemId``.
        Returns the SOAP response as a dict.
        """
        result = self._call("UpdateItem", authenticated=True, **item_data)
        return self._to_dict(result)

    def end_item(self, item_id: int, reason: str = "NotSold") -> dict:
        """End an active listing early.

        Args:
            item_id: The Tradera item ID.
            reason:  One of ``"NotSold"`` or ``"Sold"``.
        Returns the SOAP response as a dict.
        """
        result = self._call(
            "EndItem",
            authenticated=True,
            ItemId=item_id,
            Reason=reason,
        )
        return self._to_dict(result)

    def get_seller_items(self) -> list[dict]:
        """Return all current listings for the authenticated seller."""
        result = self._call("GetSellerItems", authenticated=True)
        items = result if isinstance(result, list) else getattr(result, "Items", []) or []
        return [self._to_dict(i) for i in items]

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(obj: Any) -> dict:
        """Convert a zeep object or dict to a plain dict."""
        if obj is None:
            return {}
        if isinstance(obj, dict):
            return obj
        # zeep objects have a __values__ attribute
        if hasattr(obj, "__values__"):
            return dict(obj.__values__)
        # Fallback: convert via zeep helpers if available
        try:
            from zeep.helpers import serialize_object  # type: ignore[import]

            return serialize_object(obj) or {}
        except Exception:
            return {}
