import json
from src.config.settings import CONFIG
from src.config.asset_symbols import get_asset_symbol_map, resolve_asset_symbol, get_default_market_symbols


def test_get_asset_symbol_map_from_file(tmp_path, monkeypatch):
    mapping_file = tmp_path / "asset_symbols.json"
    mapping_file.write_text(json.dumps({"silver": "SI=F", "eurusd": "EURUSD=X"}), encoding="utf-8")
    monkeypatch.setattr(CONFIG, "asset_symbols_file", str(mapping_file))

    mapping = get_asset_symbol_map()
    assert mapping["silver"] == "SI=F"
    assert mapping["eurusd"] == "EURUSD=X"


def test_resolve_asset_symbol_with_override_map(tmp_path, monkeypatch):
    mapping_file = tmp_path / "asset_symbols.json"
    mapping_file.write_text(json.dumps({"gold": "GC=F"}), encoding="utf-8")
    monkeypatch.setattr(CONFIG, "asset_symbols_file", str(mapping_file))

    override = {"silver": "SI=F", "gold": "XAUUSD=X"}
    assert resolve_asset_symbol("Silver", override) == "SI=F"
    assert resolve_asset_symbol("Gold", override) == "XAUUSD=X"


def test_get_asset_symbol_map_fallback_when_file_missing(monkeypatch):
    monkeypatch.setattr(CONFIG, "asset_symbols_file", "src/config/not-exists.json")
    mapping = get_asset_symbol_map()
    assert mapping["gold"] == "GC=F"


def test_get_default_market_symbols_unique_and_limited(tmp_path, monkeypatch):
    mapping_file = tmp_path / "asset_symbols.json"
    mapping_file.write_text(
        json.dumps({
            "gold": "GC=F",
            "xau": "GC=F",
            "oil": "CL=F",
            "bitcoin": "BTC-USD",
            "ethereum": "ETH-USD"
        }),
        encoding="utf-8"
    )
    monkeypatch.setattr(CONFIG, "asset_symbols_file", str(mapping_file))

    symbols = get_default_market_symbols(limit=3)
    assert symbols == ["GC=F", "CL=F", "BTC-USD"]
