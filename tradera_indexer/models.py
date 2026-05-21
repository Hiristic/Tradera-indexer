"""Data models used throughout the Tradera indexer."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum

# ---------------------------------------------------------------------------
# Enums (mirror Tradera's vocabulary)
# ---------------------------------------------------------------------------


class Sorting(StrEnum):
    best_hit = "Relevance"
    time_left = "TimeLeft"
    latest_added = "AddedOn"
    highest_price = "HighestPrice"
    lowest_price = "LowestPrice"
    highest_price_with_shipping = "HighestPriceWithShipping"
    lowest_price_with_shipping = "LowestPriceWithShipping"
    most_bids = "MostBids"
    least_bids = "LeastBids"
    popularity = "HighestWishListCount"


class AuctionType(StrEnum):
    all = "All"
    auction = "Auction"
    buy_now = "FixedPrice"


class ItemStatus(StrEnum):
    unsold = "unsold"
    sold = "sold"
    ended = "ended"


class Category(IntEnum):
    """Top-level Tradera categories with their official integer IDs.

    These IDs are assigned by Tradera and may change if Tradera restructures
    their category hierarchy. Verify against https://www.tradera.com/categories
    if categories appear to be missing or returning no results.
    """

    accessoarer = 1612
    antikt_design = 20
    barnartiklar = 1611
    barnklader_barnskor = 33
    barnleksaker = 302571
    biljetter_resor = 34
    bygg_verktyg = 32
    bocker_tidningar = 11
    datorer_tillbehor = 12
    dvd_videofilmer = 13
    fordon_batar_delar = 10
    ovrigt = 28
    foto_kameror_optik = 14
    frimarken = 15
    handgjort_konsthantverk = 36
    hem_hushall = 31
    hemelektronik = 17
    hobby = 18
    klockor = 19
    klader = 16
    konst = 23
    musik = 21
    mynt_sedlar = 22
    samlarsaker = 29
    skor = 1623
    skonhet = 340736
    smycken_adelstenar = 24
    sport_fritid = 25
    telefoni_tablets_wearables = 26
    tradgard_vaxter = 1605
    tv_spel_datorspel = 30
    vykort_bilder = 27


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------


@dataclass
class Item:
    """A Tradera listing item, as stored in the local index."""

    item_id: str
    title: str
    description: str = ""
    price: float | None = None
    buy_now_price: float | None = None
    shipping_cost: float | None = None
    seller_alias: str = ""
    seller_id: int | None = None
    category_id: int | None = None
    category_name: str = ""
    thumbnail_url: str = ""
    item_url: str = ""
    auction_type: AuctionType = AuctionType.auction
    status: ItemStatus = ItemStatus.unsold
    end_time: datetime | None = None
    bid_count: int = 0
    indexed_at: datetime | None = None

    def to_dict(self) -> dict:
        """Serialise to a plain dict (safe for JSON / SQLite storage)."""
        return {
            "item_id": self.item_id,
            "title": self.title,
            "description": self.description,
            "price": self.price,
            "buy_now_price": self.buy_now_price,
            "shipping_cost": self.shipping_cost,
            "seller_alias": self.seller_alias,
            "seller_id": self.seller_id,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "thumbnail_url": self.thumbnail_url,
            "item_url": self.item_url,
            "auction_type": str(self.auction_type),
            "status": str(self.status),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "bid_count": self.bid_count,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
        }


@dataclass
class SearchQuery:
    """Parameters for a search operation (local index *or* live API)."""

    query: str = ""
    category: Category | None = None
    price_min: int | None = None
    price_max: int | None = None
    auction_type: AuctionType = AuctionType.all
    sorting: Sorting = Sorting.best_hit
    page: int = 1
    items_per_page: int = 50


@dataclass
class SearchResult:
    """The outcome of a search operation."""

    items: list[Item] = field(default_factory=list)
    total_count: int = 0
    page: int = 1
    has_more: bool = False


# ---------------------------------------------------------------------------
# Publisher model
# ---------------------------------------------------------------------------

#: Valid listing durations (days) accepted by Tradera.
VALID_DURATIONS = (3, 5, 7, 10, 14, 21)


@dataclass
class NewListing:
    """Data required to create a new Tradera listing via the SOAP API."""

    title: str
    description: str
    category_id: int
    start_price: float

    # Optional fields
    buy_now_price: float | None = None
    duration_days: int = 7
    shipping_options: list[dict] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    accept_bidding: bool = True
    item_condition: str = "used"  # 'new' or 'used'

    def validate(self) -> list[str]:
        """Return a list of validation-error strings (empty ⇒ valid)."""
        errors: list[str] = []
        if not self.title or len(self.title.strip()) < 3:
            errors.append("Title must be at least 3 characters.")
        if len(self.title) > 50:
            errors.append("Title must be at most 50 characters.")
        if not self.description or not self.description.strip():
            errors.append("Description is required.")
        if not self.category_id:
            errors.append("Category ID is required.")
        if self.start_price is None or self.start_price <= 0:
            errors.append("Start price must be a positive number.")
        if (
            self.buy_now_price is not None
            and self.buy_now_price < self.start_price
        ):
            errors.append("Buy-now price must be >= start price.")
        if self.duration_days not in VALID_DURATIONS:
            errors.append(
                f"Duration must be one of {VALID_DURATIONS}, got {self.duration_days}."
            )
        if self.item_condition not in ("new", "used"):
            errors.append("Item condition must be 'new' or 'used'.")
        return errors
