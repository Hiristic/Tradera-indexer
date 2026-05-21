"""Tests for tradera_indexer.config."""
from __future__ import annotations

from tradera_indexer.config import Config


def test_defaults():
    cfg = Config()
    assert cfg.app_id == 0
    assert cfg.app_key == ""
    assert cfg.db_path == "tradera_index.db"
    assert cfg.base_url == "https://www.tradera.com"
    assert cfg.sandbox is False
    assert cfg.max_items_per_category == 1000
    assert cfg.request_delay == 0.5


def test_from_env(monkeypatch):
    monkeypatch.setenv("TRADERA_APP_ID", "42")
    monkeypatch.setenv("TRADERA_APP_KEY", "secret")
    monkeypatch.setenv("TRADERA_USER_TOKEN", "tok")
    monkeypatch.setenv("TRADERA_USER_ID", "7")
    monkeypatch.setenv("TRADERA_DB_PATH", "/tmp/x.db")
    monkeypatch.setenv("TRADERA_MAX_ITEMS_PER_CATEGORY", "500")
    monkeypatch.setenv("TRADERA_REQUEST_DELAY", "1.5")

    cfg = Config.from_env()
    assert cfg.app_id == 42
    assert cfg.app_key == "secret"
    assert cfg.user_token == "tok"
    assert cfg.user_id == 7
    assert cfg.db_path == "/tmp/x.db"
    assert cfg.max_items_per_category == 500
    assert cfg.request_delay == 1.5


def test_sandbox_url(monkeypatch):
    monkeypatch.setenv("TRADERA_SANDBOX", "true")
    cfg = Config.from_env()
    assert cfg.sandbox is True
    assert "sandbox" in cfg.soap_api_url


def test_wsdl_urls():
    cfg = Config(soap_api_url="https://api.tradera.com/v3")
    assert cfg.listing_service_wsdl.endswith("/listingservice.asmx?wsdl")
    assert cfg.search_service_wsdl.endswith("/searchservice.asmx?wsdl")
