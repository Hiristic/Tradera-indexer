"""Search the local Tradera index."""
from __future__ import annotations

from .config import Config
from .database import Database
from .models import AuctionType, Category, Item, SearchQuery, SearchResult, Sorting


class Searcher:
    """Query the local SQLite index for Tradera listings.

    Usage::

        config = Config.from_env()
        with Searcher(config) as searcher:
            result = searcher.search("cykel", limit=10)
            for item in result.items:
                print(item.title, item.price)
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._db: Database | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> Searcher:
        self._db = Database(self.config.db_path)
        self._db.connect()
        return self

    def __exit__(self, *_args: object) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    def _require_db(self) -> Database:
        if self._db is None:
            raise RuntimeError("Searcher is not started. Use as context manager.")
        return self._db

    # ------------------------------------------------------------------
    # Public search interface
    # ------------------------------------------------------------------

    def search(
        self,
        query: str = "",
        *,
        category: Category | None = None,
        price_min: int | None = None,
        price_max: int | None = None,
        auction_type: AuctionType = AuctionType.all,
        limit: int = 50,
        offset: int = 0,
    ) -> SearchResult:
        """Search the local index and return a :class:`SearchResult`.

        Args:
            query:        Free-text search term (uses FTS5 when provided).
            category:     Filter by :class:`Category`.
            price_min:    Minimum price in SEK (inclusive).
            price_max:    Maximum price in SEK (inclusive).
            auction_type: Filter by :class:`AuctionType`.
            limit:        Maximum number of items to return.
            offset:       Pagination offset (number of items to skip).
        """
        db = self._require_db()
        sq = SearchQuery(
            query=query,
            category=category,
            price_min=price_min,
            price_max=price_max,
            auction_type=auction_type,
            sorting=Sorting.best_hit,
        )
        items = db.search(sq, limit=limit, offset=offset)
        total = db.count()
        return SearchResult(
            items=items,
            total_count=total,
            page=(offset // limit) + 1 if limit > 0 else 1,
            has_more=(offset + len(items)) < total,
        )

    def get_item(self, item_id: str) -> Item | None:
        """Retrieve a single indexed item by its Tradera item ID."""
        return self._require_db().get_item(item_id)

    def stats(self) -> dict:
        """Return index statistics (item count, categories, last-indexed)."""
        return self._require_db().stats()
