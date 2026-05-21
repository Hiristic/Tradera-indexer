"""Click-based command-line interface for the Tradera indexer."""
from __future__ import annotations

import json
import logging
import sys

import click

from .config import Config
from .indexer import Indexer
from .models import AuctionType, Category, NewListing
from .publisher import Publisher, PublisherError
from .searcher import Searcher

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
    )


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.option("-v", "--verbose", is_flag=True, default=False, help="Enable debug logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Tradera indexer – index, search and publish Tradera listings."""
    _configure_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config"] = Config.from_env()


# ---------------------------------------------------------------------------
# index command
# ---------------------------------------------------------------------------


@cli.command("index")
@click.option(
    "-q", "--query", default="", show_default=True,
    help="Search term to index (leave empty to index an entire category).",
)
@click.option(
    "-c", "--category",
    type=click.Choice([c.name for c in Category], case_sensitive=False),
    default=None,
    help="Tradera category to index.",
)
@click.option(
    "--auction-type",
    type=click.Choice([a.value for a in AuctionType], case_sensitive=False),
    default=AuctionType.all.value,
    show_default=True,
    help="Restrict to a specific auction type.",
)
@click.option(
    "--price-min", type=int, default=None, help="Minimum price filter (SEK)."
)
@click.option(
    "--price-max", type=int, default=None, help="Maximum price filter (SEK)."
)
@click.option(
    "--max-pages", type=int, default=20, show_default=True,
    help="Maximum pages to fetch per query.",
)
@click.option(
    "--all-categories", is_flag=True, default=False,
    help="Index every top-level Tradera category (overrides --category).",
)
@click.pass_context
def cmd_index(
    ctx: click.Context,
    query: str,
    category: str | None,
    auction_type: str,
    price_min: int | None,
    price_max: int | None,
    max_pages: int,
    all_categories: bool,
) -> None:
    """Fetch listings from Tradera and store them in the local index."""
    config: Config = ctx.obj["config"]
    cat = Category[category] if category else None
    at = AuctionType(auction_type)

    with Indexer(config) as indexer:
        if all_categories:
            total = indexer.index_all_categories(
                auction_type=at, max_pages_per_category=max_pages
            )
        elif cat and not query:
            total = indexer.index_category(cat, auction_type=at, max_pages=max_pages)
        else:
            total = indexer.index_query(
                query,
                category=cat,
                auction_type=at,
                price_min=price_min,
                price_max=price_max,
                max_pages=max_pages,
            )

    click.echo(f"Indexed {total} item(s).")


# ---------------------------------------------------------------------------
# search command
# ---------------------------------------------------------------------------


@cli.command("search")
@click.argument("query", default="")
@click.option(
    "-c", "--category",
    type=click.Choice([c.name for c in Category], case_sensitive=False),
    default=None,
    help="Filter by Tradera category.",
)
@click.option(
    "--price-min", type=int, default=None, help="Minimum price (SEK)."
)
@click.option(
    "--price-max", type=int, default=None, help="Maximum price (SEK)."
)
@click.option(
    "--auction-type",
    type=click.Choice([a.value for a in AuctionType], case_sensitive=False),
    default=AuctionType.all.value,
    show_default=True,
)
@click.option(
    "-n", "--limit", type=int, default=20, show_default=True,
    help="Maximum number of results to display.",
)
@click.option(
    "--offset", type=int, default=0, show_default=True,
    help="Number of results to skip (pagination).",
)
@click.option("--json-output", is_flag=True, default=False, help="Output raw JSON.")
@click.pass_context
def cmd_search(
    ctx: click.Context,
    query: str,
    category: str | None,
    price_min: int | None,
    price_max: int | None,
    auction_type: str,
    limit: int,
    offset: int,
    json_output: bool,
) -> None:
    """Search the local Tradera index."""
    config: Config = ctx.obj["config"]
    cat = Category[category] if category else None
    at = AuctionType(auction_type)

    with Searcher(config) as searcher:
        result = searcher.search(
            query,
            category=cat,
            price_min=price_min,
            price_max=price_max,
            auction_type=at,
            limit=limit,
            offset=offset,
        )

    if json_output:
        click.echo(json.dumps([i.to_dict() for i in result.items], ensure_ascii=False, indent=2))
        return

    if not result.items:
        click.echo("No results found.")
        return

    click.echo(f"Found {result.total_count} indexed item(s), showing {len(result.items)}:\n")
    for item in result.items:
        price_str = f"{item.price:.0f} kr" if item.price else "–"
        buy_now_str = (
            f" / BuyNow {item.buy_now_price:.0f} kr" if item.buy_now_price else ""
        )
        click.echo(
            f"  [{item.item_id}] {item.title}\n"
            f"    Pris: {price_str}{buy_now_str}  |  "
            f"Typ: {item.auction_type}  |  "
            f"Kategori: {item.category_name or '–'}\n"
            f"    URL: {item.item_url}\n"
        )


# ---------------------------------------------------------------------------
# publish command
# ---------------------------------------------------------------------------


@cli.command("publish")
@click.option(
    "-f", "--file", "listing_file",
    type=click.Path(exists=True, readable=True),
    default=None,
    help="Path to a JSON file containing the listing data.",
)
@click.option("--title", default=None, help="Listing title (max 50 chars).")
@click.option("--description", default=None, help="Listing description.")
@click.option("--category-id", type=int, default=None, help="Tradera category ID.")
@click.option("--start-price", type=float, default=None, help="Starting bid / price (SEK).")
@click.option("--buy-now-price", type=float, default=None, help="Buy-now price (SEK).")
@click.option(
    "--duration", type=int, default=7, show_default=True,
    help="Listing duration in days.",
)
@click.option(
    "--condition",
    type=click.Choice(["new", "used"], case_sensitive=False),
    default="used",
    show_default=True,
    help="Item condition.",
)
@click.pass_context
def cmd_publish(
    ctx: click.Context,
    listing_file: str | None,
    title: str | None,
    description: str | None,
    category_id: int | None,
    start_price: float | None,
    buy_now_price: float | None,
    duration: int,
    condition: str,
) -> None:
    """Publish a new listing to Tradera via the SOAP API."""
    config: Config = ctx.obj["config"]

    # Build listing data from file or CLI flags.
    data: dict = {}
    if listing_file:
        with open(listing_file, encoding="utf-8") as fh:
            data = json.load(fh)

    # CLI flags override file values.
    if title:
        data["title"] = title
    if description:
        data["description"] = description
    if category_id is not None:
        data["category_id"] = category_id
    if start_price is not None:
        data["start_price"] = start_price
    if buy_now_price is not None:
        data["buy_now_price"] = buy_now_price
    data.setdefault("duration_days", duration)
    data.setdefault("item_condition", condition)

    required = ("title", "description", "category_id", "start_price")
    missing = [k for k in required if not data.get(k)]
    if missing:
        click.echo(
            f"Missing required fields: {', '.join(missing)}\n"
            "Provide them via --flags or a JSON --file.",
            err=True,
        )
        sys.exit(1)

    listing = NewListing(
        title=data["title"],
        description=data["description"],
        category_id=int(data["category_id"]),
        start_price=float(data["start_price"]),
        buy_now_price=float(data["buy_now_price"]) if data.get("buy_now_price") else None,
        duration_days=int(data.get("duration_days", 7)),
        shipping_options=data.get("shipping_options", []),
        images=data.get("images", []),
        accept_bidding=bool(data.get("accept_bidding", True)),
        item_condition=data.get("item_condition", "used"),
    )

    try:
        with Publisher(config) as pub:
            result = pub.publish(listing)
    except PublisherError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    item_id = result.get("ItemId") or result.get("itemId", "unknown")
    click.echo(f"Listing published successfully! Tradera Item ID: {item_id}")


# ---------------------------------------------------------------------------
# stats command
# ---------------------------------------------------------------------------


@cli.command("stats")
@click.pass_context
def cmd_stats(ctx: click.Context) -> None:
    """Show statistics about the local Tradera index."""
    config: Config = ctx.obj["config"]
    with Searcher(config) as searcher:
        data = searcher.stats()

    click.echo(f"Total indexed items : {data['total_items']}")
    click.echo(f"Last indexed        : {data['last_indexed'] or 'never'}")
    if data["top_categories"]:
        click.echo("\nTop categories:")
        for cat in data["top_categories"]:
            click.echo(f"  {cat['name'] or '(unknown)':<35} {cat['count']:>6}")


# ---------------------------------------------------------------------------
# Entry-point helper (used by pyproject.toml scripts)
# ---------------------------------------------------------------------------


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
