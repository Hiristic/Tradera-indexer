"""Indexer: fetches listings from the Tradera API and stores them locally."""
from __future__ import annotations

import logging
import time

from .client import TraderaAPIError, TraderaClient
from .config import Config
from .database import Database
from .models import AuctionType, Category, SearchQuery, Sorting

logger = logging.getLogger(__name__)


class IndexerError(Exception):
    """Raised when the indexer encounters a non-recoverable error."""


class Indexer:
    """Fetches Tradera listings and persists them to the local database.

    Usage::

        config = Config.from_env()
        with Indexer(config) as indexer:
            count = indexer.index_query("cykel")
            count += indexer.index_category(Category.sport_fritid)
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._db: Database | None = None
        self._client: TraderaClient | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> Indexer:
        self._db = Database(self.config.db_path)
        self._db.connect()
        self._client = TraderaClient(self.config)
        self._client.__enter__()
        return self

    def __exit__(self, *_args: object) -> None:
        if self._client is not None:
            self._client.__exit__()
            self._client = None
        if self._db is not None:
            self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_db(self) -> Database:
        if self._db is None:
            raise RuntimeError("Indexer is not started. Use as context manager.")
        return self._db

    def _require_client(self) -> TraderaClient:
        if self._client is None:
            raise RuntimeError("Indexer is not started. Use as context manager.")
        return self._client

    # ------------------------------------------------------------------
    # Public indexing methods
    # ------------------------------------------------------------------

    def index_query(
        self,
        query: str,
        *,
        category: Category | None = None,
        auction_type: AuctionType = AuctionType.all,
        price_min: int | None = None,
        price_max: int | None = None,
        max_pages: int = 20,
    ) -> int:
        """Fetch all pages of *query* results and store them.

        Returns the number of items upserted into the database.
        """
        client = self._require_client()
        db = self._require_db()

        base_query = SearchQuery(
            query=query,
            category=category,
            auction_type=auction_type,
            price_min=price_min,
            price_max=price_max,
            sorting=Sorting.latest_added,
            items_per_page=self.config.items_per_page,
        )

        total_indexed = 0
        for page in range(1, max_pages + 1):
            paged = SearchQuery(
                query=base_query.query,
                category=base_query.category,
                auction_type=base_query.auction_type,
                price_min=base_query.price_min,
                price_max=base_query.price_max,
                sorting=base_query.sorting,
                page=page,
                items_per_page=base_query.items_per_page,
            )
            try:
                result = client.search(paged)
            except TraderaAPIError as exc:
                logger.warning("API error on page %d: %s", page, exc)
                break

            if not result.items:
                break

            count = db.upsert_items(result.items)
            total_indexed += count
            logger.info(
                "Page %d: indexed %d items (total so far: %d / %d)",
                page,
                count,
                total_indexed,
                result.total_count,
            )

            if not result.has_more:
                break
            if total_indexed >= self.config.max_items_per_category:
                logger.info(
                    "Reached max_items_per_category (%d), stopping.",
                    self.config.max_items_per_category,
                )
                break

            time.sleep(self.config.request_delay)

        return total_indexed

    def index_category(
        self,
        category: Category,
        *,
        auction_type: AuctionType = AuctionType.all,
        max_pages: int = 20,
    ) -> int:
        """Index all available listings in *category*.

        Returns the number of items upserted.
        """
        logger.info("Indexing category: %s (id=%d)", category.name, category.value)
        return self.index_query(
            query="",
            category=category,
            auction_type=auction_type,
            max_pages=max_pages,
        )

    def index_all_categories(
        self,
        *,
        auction_type: AuctionType = AuctionType.all,
        max_pages_per_category: int = 20,
    ) -> int:
        """Index every top-level Tradera category.

        Returns the total number of items upserted.
        """
        total = 0
        for category in Category:
            try:
                count = self.index_category(
                    category,
                    auction_type=auction_type,
                    max_pages=max_pages_per_category,
                )
                total += count
            except IndexerError as exc:
                logger.error(
                    "Failed to index category %s: %s", category.name, exc
                )
            time.sleep(self.config.request_delay)

        logger.info("Full index complete. Total items: %d", total)
        return total
