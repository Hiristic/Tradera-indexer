"""HTTP client that wraps Tradera's internal web search API."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from .config import Config
from .models import AuctionType, Item, ItemStatus, SearchQuery, SearchResult

logger = logging.getLogger(__name__)

_SEARCH_PATH = "/api/webapi/discover/web/independent-search"


class TraderaAPIError(Exception):
    """Raised when the Tradera API returns an unexpected response."""


class TraderaClient:
    """Thin wrapper around Tradera's public web search API.

    Usage::

        config = Config.from_env()
        with TraderaClient(config) as client:
            result = client.search(SearchQuery(query="cykel"))
            for item in result.items:
                print(item.title, item.price)
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._http: httpx.Client | None = None

    # ------------------------------------------------------------------
    # Context-manager interface
    # ------------------------------------------------------------------

    def __enter__(self) -> TraderaClient:
        self._http = httpx.Client(
            base_url=self.config.base_url,
            headers={
                "Accept": "application/json",
                "Accept-Language": "sv-SE,sv;q=0.9",
                "User-Agent": (
                    "Mozilla/5.0 (compatible; TraderaIndexer/1.0; "
                    "+https://github.com/Hiristic/Tradera-indexer)"
                ),
                **self.config.extra_headers,
            },
            timeout=30.0,
            follow_redirects=True,
        )
        # Establish a session / pick up cookies used by the search API.
        try:
            self._http.get("/")
        except httpx.HTTPError:
            pass  # Non-fatal; the search call may still succeed.
        return self

    def __exit__(self, *_args: object) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def _require_client(self) -> httpx.Client:
        if self._http is None:
            raise RuntimeError(
                "TraderaClient must be used as a context manager."
            )
        return self._http

    def search(self, query: SearchQuery) -> SearchResult:
        """Execute a search and return a :class:`SearchResult`."""
        client = self._require_client()
        params: dict = {
            "automaticTranslationPreferred": True,
            "forceKeywordSearch": False,
            "includeFilters": False,
            "languageCodeIso2": "sv",
            "searchTypeVariantHint": "enrichemptysearchresult",
            "shippingCountryCodeIso2": "SE",
            "itemStatus": "unsold",
            "query": query.query,
            "sortBy": str(query.sorting),
            "itemType": str(query.auction_type),
            "itemsPerPage": query.items_per_page,
            "pageNumber": query.page,
        }
        if query.category is not None:
            params["categoryId"] = int(query.category)
        if query.price_min is not None:
            params["fromPrice"] = query.price_min
        if query.price_max is not None:
            params["toPrice"] = query.price_max

        try:
            resp = client.post(_SEARCH_PATH, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            raise TraderaAPIError(
                f"Search request failed with HTTP {exc.response.status_code}: "
                f"{exc.response.text[:200]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise TraderaAPIError(f"Search request failed: {exc}") from exc

        return self._parse_search_result(data, query.page, query.items_per_page)

    def search_all_pages(self, query: SearchQuery, max_pages: int = 20) -> SearchResult:
        """Collect results across multiple pages, up to *max_pages*."""
        all_items: list[Item] = []
        total_count = 0

        for page_num in range(1, max_pages + 1):
            paged = SearchQuery(
                query=query.query,
                category=query.category,
                price_min=query.price_min,
                price_max=query.price_max,
                auction_type=query.auction_type,
                sorting=query.sorting,
                page=page_num,
                items_per_page=query.items_per_page,
            )
            result = self.search(paged)
            all_items.extend(result.items)
            total_count = result.total_count

            if not result.has_more or not result.items:
                break

        return SearchResult(
            items=all_items,
            total_count=total_count,
            page=1,
            has_more=False,
        )

    # ------------------------------------------------------------------
    # Internal parsers
    # ------------------------------------------------------------------

    def _parse_search_result(
        self, data: dict, page: int, items_per_page: int
    ) -> SearchResult:
        items_raw: list[dict] = data.get("items", []) or []
        total: int = int(data.get("totalCount", 0) or 0)

        items = [
            parsed
            for raw in items_raw
            if (parsed := self._parse_item(raw)) is not None
        ]

        fetched_so_far = (page - 1) * items_per_page + len(items)
        has_more = fetched_so_far < total and len(items) == items_per_page

        return SearchResult(
            items=items,
            total_count=total,
            page=page,
            has_more=has_more,
        )

    @staticmethod
    def _parse_item(raw: dict) -> Item | None:
        """Convert a raw API dict to an :class:`Item`, or *None* on failure."""
        try:
            item_id = str(raw.get("id") or raw.get("itemId") or "").strip()
            if not item_id:
                return None

            def _float(key: str) -> float | None:
                val = raw.get(key)
                return float(val) if val is not None else None

            def _seller_alias() -> str:
                alias = raw.get("sellerAlias")
                if alias:
                    return str(alias)
                seller = raw.get("seller")
                if isinstance(seller, dict):
                    return str(seller.get("alias", ""))
                return ""

            auction_type_raw = raw.get("itemType", "All")
            if auction_type_raw == "FixedPrice":
                auction_type = AuctionType.buy_now
            elif auction_type_raw == "Auction":
                auction_type = AuctionType.auction
            else:
                auction_type = AuctionType.all

            end_time: datetime | None = None
            end_time_raw: str | None = raw.get("endTime")
            if end_time_raw:
                try:
                    end_time = datetime.fromisoformat(
                        end_time_raw.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass

            return Item(
                item_id=item_id,
                title=str(
                    raw.get("shortDescription")
                    or raw.get("title")
                    or ""
                ).strip(),
                description=str(
                    raw.get("longDescription")
                    or raw.get("description")
                    or ""
                ).strip(),
                price=_float("price"),
                buy_now_price=_float("buyNowPrice"),
                shipping_cost=_float("shippingCost"),
                seller_alias=_seller_alias(),
                seller_id=raw.get("sellerId"),
                category_id=raw.get("categoryId"),
                category_name=str(raw.get("categoryName") or "").strip(),
                thumbnail_url=str(
                    raw.get("imageUrl") or raw.get("thumbnailUrl") or ""
                ).strip(),
                item_url=str(
                    raw.get("itemUrl") or f"/item/{item_id}"
                ).strip(),
                auction_type=auction_type,
                status=ItemStatus.unsold,
                end_time=end_time,
                bid_count=int(raw.get("numberOfBids") or 0),
                indexed_at=datetime.now(tz=UTC),
            )
        except Exception:
            logger.debug("Failed to parse item payload: %r", raw, exc_info=True)
            return None
