"""Configuration management via environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Application configuration loaded from environment variables.

    Required credentials for publishing (SOAP API):
        TRADERA_APP_ID  – integer application ID issued by Tradera
        TRADERA_APP_KEY – secret application key

    Optional user-level credentials for authenticated SOAP calls:
        TRADERA_USER_TOKEN – OAuth access token
        TRADERA_USER_ID    – Tradera user/seller ID
    """

    # Tradera SOAP API developer credentials
    app_id: int = 0
    app_key: str = ""

    # User-level credentials (required for publishing)
    user_token: str = ""
    user_id: int = 0

    # Local database
    db_path: str = "tradera_index.db"

    # Tradera web base URL (for search / item pages)
    base_url: str = "https://www.tradera.com"

    # Official SOAP API base URL
    soap_api_url: str = "https://api.tradera.com/v3"

    # Use sandbox environment instead of production
    sandbox: bool = False

    # Indexer behaviour
    max_items_per_category: int = 1000
    items_per_page: int = 50
    request_delay: float = 0.5  # seconds to wait between requests

    # Extra HTTP headers forwarded to every request
    extra_headers: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ #

    @classmethod
    def from_env(cls) -> Config:
        """Build a :class:`Config` by reading environment variables."""
        sandbox = os.environ.get("TRADERA_SANDBOX", "false").lower() == "true"
        soap_url = (
            "https://api.sandbox.tradera.com/v3"
            if sandbox
            else os.environ.get("TRADERA_SOAP_API_URL", "https://api.tradera.com/v3")
        )
        return cls(
            app_id=int(os.environ.get("TRADERA_APP_ID", "0") or "0"),
            app_key=os.environ.get("TRADERA_APP_KEY", ""),
            user_token=os.environ.get("TRADERA_USER_TOKEN", ""),
            user_id=int(os.environ.get("TRADERA_USER_ID", "0") or "0"),
            db_path=os.environ.get("TRADERA_DB_PATH", "tradera_index.db"),
            base_url=os.environ.get("TRADERA_BASE_URL", "https://www.tradera.com"),
            soap_api_url=soap_url,
            sandbox=sandbox,
            max_items_per_category=int(
                os.environ.get("TRADERA_MAX_ITEMS_PER_CATEGORY", "1000") or "1000"
            ),
            items_per_page=int(
                os.environ.get("TRADERA_ITEMS_PER_PAGE", "50") or "50"
            ),
            request_delay=float(
                os.environ.get("TRADERA_REQUEST_DELAY", "0.5") or "0.5"
            ),
        )

    @property
    def listing_service_wsdl(self) -> str:
        """WSDL URL for the Tradera ListingService (publishing)."""
        return f"{self.soap_api_url}/listingservice.asmx?wsdl"

    @property
    def search_service_wsdl(self) -> str:
        """WSDL URL for the Tradera SearchService."""
        return f"{self.soap_api_url}/searchservice.asmx?wsdl"
