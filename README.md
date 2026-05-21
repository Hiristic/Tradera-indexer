# Tradera-indexer

A Python tool that **indexes all Tradera listings** for fast local full-text
search and **publishes new listings** automatically through the Tradera API.

> **Tradera** is Sweden's largest online marketplace, offering auctions and
> fixed-price listings across all product categories.

---

## Features

| Feature | Description |
|---|---|
| 🔍 **Index** | Crawl all Tradera listings (by search term or category) and store them in a local SQLite database with FTS5 full-text search. |
| 🔎 **Search** | Fast offline full-text search with filters for category, price range and auction type. |
| 📢 **Publish** | Create, update and end Tradera listings programmatically using the official Tradera SOAP API. |
| 🖥️ **CLI** | A simple command-line interface for all operations. |
| 🐍 **Python API** | Use the library directly in your own Python scripts. |

---

## Requirements

- Python 3.11 or newer
- `pip install -r requirements.txt`
- For **publishing** listings, also install: `pip install zeep`

---

## Installation

```bash
git clone https://github.com/Hiristic/Tradera-indexer.git
cd Tradera-indexer
pip install -e ".[soap]"   # installs zeep for SOAP support as well
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `TRADERA_APP_ID` | Yes (publishing) | Your Tradera developer App ID |
| `TRADERA_APP_KEY` | Yes (publishing) | Your Tradera developer App Key |
| `TRADERA_USER_TOKEN` | Yes (publishing) | OAuth access token for the seller account |
| `TRADERA_USER_ID` | Yes (publishing) | Tradera user/seller ID |
| `TRADERA_DB_PATH` | No | Path to the local SQLite database (default: `tradera_index.db`) |
| `TRADERA_MAX_ITEMS_PER_CATEGORY` | No | Maximum items to index per category (default: `1000`) |
| `TRADERA_REQUEST_DELAY` | No | Seconds between API requests (default: `0.5`) |
| `TRADERA_SANDBOX` | No | Set to `true` to use the Tradera sandbox (default: `false`) |

---

## CLI Usage

### Index listings

```bash
# Index by search term
tradera-indexer index --query "cykel"

# Index a specific category
tradera-indexer index --category sport_fritid

# Index all categories (full crawl)
tradera-indexer index --all-categories

# Index with price and auction-type filters
tradera-indexer index --query "kamera" --price-min 100 --price-max 5000 --auction-type Auction
```

### Search the local index

```bash
# Full-text search
tradera-indexer search "retro cykel"

# Filter by category and price
tradera-indexer search "lampa" --category hem_hushall --price-max 500

# JSON output for scripting
tradera-indexer search "dator" --json-output | jq '.[].title'
```

### Publish a listing

Using a JSON file:

```bash
cat listing.json
{
  "title": "Retro cykel från 80-talet",
  "description": "Fint skick, ny kedja. Passar 170–185 cm.",
  "category_id": 25,
  "start_price": 200,
  "buy_now_price": 500,
  "duration_days": 7,
  "item_condition": "used"
}

tradera-indexer publish --file listing.json
```

Or inline:

```bash
tradera-indexer publish \
  --title "Retro cykel" \
  --description "Fint skick." \
  --category-id 25 \
  --start-price 200 \
  --duration 7
```

### Show index statistics

```bash
tradera-indexer stats
```

---

## Python API

```python
from tradera_indexer import Config, Indexer, Searcher, Publisher, NewListing, Category

config = Config.from_env()

# --- Index ---
with Indexer(config) as indexer:
    n = indexer.index_category(Category.sport_fritid)
    print(f"Indexed {n} items")

# --- Search ---
with Searcher(config) as searcher:
    result = searcher.search("cykel", price_max=1000, limit=10)
    for item in result.items:
        print(item.title, item.price)

# --- Publish ---
listing = NewListing(
    title="Retro cykel",
    description="Fint skick, inga repor.",
    category_id=25,
    start_price=200,
    buy_now_price=500,
    duration_days=7,
)
with Publisher(config) as pub:
    result = pub.publish(listing)
    print("Published item ID:", result["ItemId"])
```

---

## Available categories

| Name | ID |
|---|---|
| accessoarer | 1612 |
| antikt_design | 20 |
| barnartiklar | 1611 |
| barnklader_barnskor | 33 |
| bocker_tidningar | 11 |
| datorer_tillbehor | 12 |
| fordon_batar_delar | 10 |
| hemelektronik | 17 |
| hobby | 18 |
| klockor | 19 |
| klader | 16 |
| konst | 23 |
| musik | 21 |
| samlarsaker | 29 |
| sport_fritid | 25 |
| telefoni_tablets_wearables | 26 |
| tv_spel_datorspel | 30 |
| … | … |

See `tradera_indexer/models.py` for the full list.

---

## Development

```bash
pip install -e ".[dev,soap]"
pytest
ruff check tradera_indexer tests
```

---

## Publishing credentials

To use the **publish** feature you need:

1. A **Tradera developer account** — register at
   [https://developer.tradera.com/](https://developer.tradera.com/) to get
   `TRADERA_APP_ID` and `TRADERA_APP_KEY`.

2. A **user OAuth token** (`TRADERA_USER_TOKEN` and `TRADERA_USER_ID`) for the
   seller account whose listings you want to manage. Tradera's OAuth flow
   issues these tokens.

> **Sandbox:** Set `TRADERA_SANDBOX=true` in your `.env` to make all
> publishing calls against the Tradera sandbox environment rather than
> production.

---

## License

MIT