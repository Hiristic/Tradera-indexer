"""SQLite database layer with FTS5 full-text search for the Tradera index."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .models import AuctionType, Item, ItemStatus, SearchQuery

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_CREATE_ITEMS = """
CREATE TABLE IF NOT EXISTS items (
    item_id          TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    description      TEXT NOT NULL DEFAULT '',
    price            REAL,
    buy_now_price    REAL,
    shipping_cost    REAL,
    seller_alias     TEXT NOT NULL DEFAULT '',
    seller_id        INTEGER,
    category_id      INTEGER,
    category_name    TEXT NOT NULL DEFAULT '',
    thumbnail_url    TEXT NOT NULL DEFAULT '',
    item_url         TEXT NOT NULL DEFAULT '',
    auction_type     TEXT NOT NULL DEFAULT 'All',
    status           TEXT NOT NULL DEFAULT 'unsold',
    end_time         TEXT,
    bid_count        INTEGER NOT NULL DEFAULT 0,
    indexed_at       TEXT NOT NULL
)
"""

_CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    item_id    UNINDEXED,
    title,
    description,
    category_name,
    seller_alias,
    content    = 'items',
    content_rowid = 'rowid'
)
"""

_CREATE_TRIGGER_AI = """
CREATE TRIGGER IF NOT EXISTS items_ai
AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, item_id, title, description, category_name, seller_alias)
    VALUES (new.rowid, new.item_id, new.title, new.description,
            new.category_name, new.seller_alias);
END
"""

_CREATE_TRIGGER_AD = """
CREATE TRIGGER IF NOT EXISTS items_ad
AFTER DELETE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, item_id, title, description,
                          category_name, seller_alias)
    VALUES ('delete', old.rowid, old.item_id, old.title, old.description,
            old.category_name, old.seller_alias);
END
"""

_CREATE_TRIGGER_AU = """
CREATE TRIGGER IF NOT EXISTS items_au
AFTER UPDATE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, item_id, title, description,
                          category_name, seller_alias)
    VALUES ('delete', old.rowid, old.item_id, old.title, old.description,
            old.category_name, old.seller_alias);
    INSERT INTO items_fts(rowid, item_id, title, description,
                          category_name, seller_alias)
    VALUES (new.rowid, new.item_id, new.title, new.description,
            new.category_name, new.seller_alias);
END
"""

_TRIGGER_STMTS = (_CREATE_TRIGGER_AI, _CREATE_TRIGGER_AD, _CREATE_TRIGGER_AU)


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------


class Database:
    """Manages the local SQLite store for indexed Tradera listings.

    Usage::

        with Database("tradera_index.db") as db:
            db.upsert_items(items)
            results = db.search("cykel")
    """

    def __init__(self, db_path: str = "tradera_index.db") -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> Database:
        self.connect()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def connect(self) -> None:
        """Open the database connection and initialise the schema."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._conn

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        conn = self._require_conn()
        conn.execute(_CREATE_ITEMS)
        conn.execute(_CREATE_FTS)
        for stmt in _TRIGGER_STMTS:
            conn.execute(stmt)
        conn.commit()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def upsert_item(self, item: Item) -> None:
        """Insert or replace a single item."""
        self.upsert_items([item])

    def upsert_items(self, items: list[Item]) -> int:
        """Bulk upsert a list of items. Returns the number inserted/updated."""
        if not items:
            return 0
        conn = self._require_conn()
        now = datetime.now(tz=UTC).isoformat()
        rows = []
        for it in items:
            rows.append((
                it.item_id,
                it.title,
                it.description or "",
                it.price,
                it.buy_now_price,
                it.shipping_cost,
                it.seller_alias or "",
                it.seller_id,
                it.category_id,
                it.category_name or "",
                it.thumbnail_url or "",
                it.item_url or "",
                str(it.auction_type),
                str(it.status),
                it.end_time.isoformat() if it.end_time else None,
                it.bid_count or 0,
                it.indexed_at.isoformat() if it.indexed_at else now,
            ))
        conn.executemany(
            """
            INSERT INTO items
                (item_id, title, description, price, buy_now_price, shipping_cost,
                 seller_alias, seller_id, category_id, category_name,
                 thumbnail_url, item_url, auction_type, status,
                 end_time, bid_count, indexed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(item_id) DO UPDATE SET
                title         = excluded.title,
                description   = excluded.description,
                price         = excluded.price,
                buy_now_price = excluded.buy_now_price,
                shipping_cost = excluded.shipping_cost,
                seller_alias  = excluded.seller_alias,
                seller_id     = excluded.seller_id,
                category_id   = excluded.category_id,
                category_name = excluded.category_name,
                thumbnail_url = excluded.thumbnail_url,
                item_url      = excluded.item_url,
                auction_type  = excluded.auction_type,
                status        = excluded.status,
                end_time      = excluded.end_time,
                bid_count     = excluded.bid_count,
                indexed_at    = excluded.indexed_at
            """,
            rows,
        )
        conn.commit()
        return len(rows)

    def delete_item(self, item_id: str) -> None:
        """Remove an item from the index."""
        conn = self._require_conn()
        conn.execute("DELETE FROM items WHERE item_id = ?", (item_id,))
        conn.commit()

    def clear(self) -> None:
        """Remove all items from the index."""
        conn = self._require_conn()
        conn.execute("DELETE FROM items")
        conn.commit()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_item(self, item_id: str) -> Item | None:
        """Fetch a single item by its Tradera item ID."""
        conn = self._require_conn()
        row = conn.execute(
            "SELECT * FROM items WHERE item_id = ?", (item_id,)
        ).fetchone()
        return _row_to_item(row) if row else None

    def search(
        self,
        query: SearchQuery,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Item]:
        """Search the local index using FTS5 and optional filters.

        When *query.query* is non-empty the FTS5 index is used for ranking.
        Otherwise all items are returned (subject to filters and pagination).
        """
        conn = self._require_conn()

        filters: list[str] = []
        params: list = []

        if query.category is not None:
            filters.append("i.category_id = ?")
            params.append(int(query.category))

        if query.auction_type != AuctionType.all:
            filters.append("i.auction_type = ?")
            params.append(str(query.auction_type))

        if query.price_min is not None:
            filters.append("(i.price >= ? OR i.buy_now_price >= ?)")
            params.extend([query.price_min, query.price_min])

        if query.price_max is not None:
            filters.append("(i.price <= ? OR i.buy_now_price <= ?)")
            params.extend([query.price_max, query.price_max])

        where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

        if query.query.strip():
            fts_params = [query.query.strip()] + params
            sql = f"""
                SELECT i.*
                FROM items i
                JOIN items_fts ON items_fts.item_id = i.item_id
                WHERE items_fts MATCH ?
                {('AND ' + ' AND '.join(filters)) if filters else ''}
                ORDER BY rank
                LIMIT ? OFFSET ?
            """
            fts_params += [limit, offset]
            rows = conn.execute(sql, fts_params).fetchall()
        else:
            sql = f"""
                SELECT * FROM items i
                {where_clause}
                ORDER BY indexed_at DESC
                LIMIT ? OFFSET ?
            """
            params += [limit, offset]
            rows = conn.execute(sql, params).fetchall()

        return [item for row in rows if (item := _row_to_item(row)) is not None]

    def count(self) -> int:
        """Return the total number of indexed items."""
        conn = self._require_conn()
        return conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    def stats(self) -> dict:
        """Return aggregate statistics about the index."""
        conn = self._require_conn()
        total = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        categories = conn.execute(
            "SELECT category_name, COUNT(*) AS cnt "
            "FROM items GROUP BY category_name ORDER BY cnt DESC LIMIT 20"
        ).fetchall()
        last_indexed = conn.execute(
            "SELECT MAX(indexed_at) FROM items"
        ).fetchone()[0]
        return {
            "total_items": total,
            "last_indexed": last_indexed,
            "top_categories": [
                {"name": row["category_name"], "count": row["cnt"]}
                for row in categories
            ],
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_item(row: sqlite3.Row) -> Item | None:
    """Convert a database row to an :class:`Item`."""
    try:
        end_time = None
        if row["end_time"]:
            try:
                end_time = datetime.fromisoformat(row["end_time"])
            except ValueError:
                pass

        indexed_at = None
        if row["indexed_at"]:
            try:
                indexed_at = datetime.fromisoformat(row["indexed_at"])
            except ValueError:
                pass

        return Item(
            item_id=row["item_id"],
            title=row["title"],
            description=row["description"] or "",
            price=row["price"],
            buy_now_price=row["buy_now_price"],
            shipping_cost=row["shipping_cost"],
            seller_alias=row["seller_alias"] or "",
            seller_id=row["seller_id"],
            category_id=row["category_id"],
            category_name=row["category_name"] or "",
            thumbnail_url=row["thumbnail_url"] or "",
            item_url=row["item_url"] or "",
            auction_type=AuctionType(row["auction_type"]),
            status=ItemStatus(row["status"]),
            end_time=end_time,
            bid_count=int(row["bid_count"] or 0),
            indexed_at=indexed_at,
        )
    except Exception:
        return None
