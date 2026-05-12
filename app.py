from __future__ import annotations

import csv
import html
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
CACHE_DIR = DATA_DIR / "cache"

STOCKANALYSIS_URL = "https://stockanalysis.com/list/stock-exchange-of-thailand/"
STOCKPRICEPREDICTIONS_URL = "https://stockpricepredictions.com/asia-pacific/thailand/set/"
SET_FACTSHEET_URL = "https://www.set.or.th/en/market/product/dr/quote/{symbol}/factsheet"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"

DR_PROFILE_CACHE = CACHE_DIR / "dr_profiles.json"
DASHBOARD_CACHE = CACHE_DIR / "dashboard.json"
MANUAL_MAP_CSV = DATA_DIR / "underlying_map.csv"

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


BUILTIN_UNDERLYING_MAP: dict[str, str] = {
    "BRKB": "BRK-B",
    "JPMUS": "JPM",
    "GSUS": "GS",
    "MS": "MS",
    "TENCENT": "0700.HK",
    "BABA": "9988.HK",
    "XIAOMI": "1810.HK",
    "MEITUAN": "3690.HK",
    "AIA": "1299.HK",
    "BYDCOM": "1211.HK",
    "PINGAN": "2318.HK",
    "CHMOBILE": "0941.HK",
    "CMBANK": "3968.HK",
    "ICBC": "1398.HK",
    "PETROCN": "0857.HK",
    "HKEX": "0388.HK",
    "SMIC": "0981.HK",
    "ZIJIN": "2899.HK",
    "GEELY": "0175.HK",
    "WUXI": "2269.HK",
    "WUXIAT": "2359.HK",
    "TRIPCOM": "9961.HK",
    "HAIERS": "6690.HK",
    "HUAHONG": "1347.HK",
    "NONGFU": "9633.HK",
    "NETEASE": "9999.HK",
    "SENSE": "0020.HK",
    "UBTECH": "9880.HK",
    "CATL": "3750.HK",
    "GANFENG": "1772.HK",
    "NAURA": "002371.SZ",
    "CYPC": "600900.SS",
    "ZJINNO": "300308.SZ",
    "CAMBRI": "688256.SS",
    "TOYOTA": "7203.T",
    "SOFTBANK": "9984.T",
    "SONY": "6758.T",
    "NINTENDO": "7974.T",
    "MITSU": "7011.T",
    "ITOCHU": "8001.T",
    "TEL": "8035.T",
    "ADVANT": "6857.T",
    "KEYENCE": "6861.T",
    "UNIQLO": "9983.T",
    "DISCO": "6146.T",
    "HITACHI": "6501.T",
    "FANUC": "6954.T",
    "ASICS": "7936.T",
    "HONDA": "7267.T",
    "LVMH": "MC.PA",
    "LOREAL": "OR.PA",
    "HERMES": "RMS.PA",
    "ASML": "ASML.AS",
    "NOVOB": "NOVO-B.CO",
    "SANOFI": "SAN.PA",
    "FERRARI": "RACE.MI",
    "DBS": "D05.SI",
    "UOB": "U11.SI",
    "SINGTEL": "Z74.SI",
    "SGX": "S68.SI",
    "SEMB": "U96.SI",
    "WORLDA ETF": "SMSWLD.MI",
    "WORLDA": "SMSWLD.MI",
    "THAIBEV": "Y92.SI",
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def http_get(url: str, timeout: int = 25, accept_json: bool = False) -> str:
    headers = dict(HTTP_HEADERS)
    if accept_json:
        headers["Accept"] = "application/json,text/plain,*/*"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def strip_tags(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "n/a", "N/A", "None"}:
        return None
    text = text.rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def parse_stockanalysis_rows() -> list[dict[str, Any]]:
    body = http_get(STOCKANALYSIS_URL, timeout=30)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S | re.I)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)
        if len(cells) < 6:
            continue
        symbol_match = re.search(r"/quote/bkk/([^/]+)/[^>]*>([^<]+)</a>", cells[1], flags=re.I)
        if not symbol_match:
            continue
        symbol = html.unescape(symbol_match.group(2)).upper().strip()
        if not is_dr_candidate(symbol):
            continue
        parsed.append(
            {
                "symbol": symbol,
                "company_name": strip_tags(cells[2]),
                "market_cap": strip_tags(cells[3]),
                "dr_last": parse_float(strip_tags(cells[4])),
                "dr_percent_change": parse_float(strip_tags(cells[5])),
                "price_source": "StockAnalysis SET list",
            }
        )
    return parsed


def parse_stockpricepredictions_rows() -> list[dict[str, Any]]:
    body = http_get(STOCKPRICEPREDICTIONS_URL, timeout=35)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body, flags=re.S | re.I)
    parsed: list[dict[str, Any]] = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)
        if len(cells) < 8:
            continue
        symbol_match = re.search(r">([A-Z0-9.]+)</a>", cells[0], flags=re.I)
        if not symbol_match:
            continue
        symbol = html.unescape(symbol_match.group(1)).upper().strip()
        name = strip_tags(cells[1])
        name_lower = name.lower()
        if not is_dr_candidate(symbol):
            continue
        if "depositary receipt" not in name_lower and "depositery receipt" not in name_lower and "depository receipt" not in name_lower:
            continue
        parsed.append(
            {
                "symbol": symbol,
                "company_name": re.split(r"\s+(?:Units|Shs|nits)\s+Thailand", name, maxsplit=1)[0].strip() or name,
                "market_cap": None,
                "dr_open": parse_float(strip_tags(cells[3])),
                "dr_high": parse_float(strip_tags(cells[4])),
                "dr_low": parse_float(strip_tags(cells[5])),
                "dr_last": parse_float(strip_tags(cells[6])),
                "dr_percent_change": parse_float(strip_tags(cells[7])),
                "price_source": "StockPricePredictions SET page",
            }
        )
    return parsed


def discover_dr_price_rows() -> list[dict[str, Any]]:
    combined: dict[str, dict[str, Any]] = {}
    source_errors: list[str] = []
    try:
        for row in parse_stockpricepredictions_rows():
            combined[row["symbol"]] = row
    except Exception as exc:
        source_errors.append(f"StockPricePredictions: {exc}")
    try:
        for row in parse_stockanalysis_rows():
            prior = combined.get(row["symbol"], {})
            combined[row["symbol"]] = {**prior, **row, "price_source": "StockAnalysis SET list"}
    except Exception as exc:
        source_errors.append(f"StockAnalysis: {exc}")
    rows = list(combined.values())
    for row in rows:
        if source_errors:
            row["source_warnings"] = "; ".join(source_errors)
    return rows


def is_dr_candidate(symbol: str) -> bool:
    if "." in symbol:
        return False
    return bool(re.match(r"^[A-Z][A-Z0-9]{1,18}\d{2}$", symbol))


def js_unescape(text: str) -> str:
    text = text.replace("\\u002F", "/")
    text = text.replace("\\/", "/")
    text = text.replace('\\"', '"')
    return html.unescape(text)


def extract_js_string(block: str, key: str) -> str | None:
    match = re.search(rf'{re.escape(key)}:"((?:\\.|[^"\\])*)"', block)
    return js_unescape(match.group(1)) if match else None


def fetch_set_profile(symbol: str) -> dict[str, Any] | None:
    url = SET_FACTSHEET_URL.format(symbol=urllib.parse.quote(symbol))
    body = http_get(url, timeout=25)
    marker = "DR:{companyProfile:{"
    start = body.find(marker)
    if start < 0:
        return None
    end = body.find("},price:", start)
    block = body[start:end] if end > start else body[start : start + 5000]
    conversion_ratio = extract_js_string(block, "conversionRatio")
    underlying = extract_js_string(block, "underlying")
    if not conversion_ratio or not underlying:
        return None
    return {
        "symbol": symbol,
        "set_name": extract_js_string(block, "name"),
        "issuer": extract_js_string(block, "issuer"),
        "issuer_name": extract_js_string(block, "issuerName"),
        "security_type": extract_js_string(block, "securityType"),
        "status": extract_js_string(block, "status"),
        "first_trade_date": extract_js_string(block, "firstTradeDate"),
        "conversion_ratio": conversion_ratio,
        "dr_per_underlying": parse_conversion_ratio(conversion_ratio),
        "underlying": underlying,
        "underlying_name": extract_js_string(block, "underlyingName"),
        "underlying_class": extract_js_string(block, "underlyingClassName"),
        "underlying_exchange": extract_js_string(block, "underlyingExchange"),
        "underlying_url": extract_js_string(block, "underlyingUrl"),
        "indicative_price_symbol": extract_js_string(block, "indicativePriceSymbol"),
        "indicative_price_url": extract_js_string(block, "indicativePriceUrl"),
        "trading_session": extract_js_string(block, "tradingSession"),
        "source_url": url,
        "profile_fetched_at": now_iso(),
    }


def parse_conversion_ratio(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"([\d,.]+)\s*:\s*([\d,.]+)", text)
    if not match:
        return None
    left = parse_float(match.group(1))
    right = parse_float(match.group(2))
    if not left or not right:
        return None
    return left / right


def refresh_set_profiles(symbols: list[str], force: bool = False) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = read_json(DR_PROFILE_CACHE, {})
    missing = [symbol for symbol in symbols if force or symbol not in cache]
    if not missing:
        return cache
    lock = threading.Lock()
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_set_profile, symbol): symbol for symbol in missing}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                profile = future.result()
            except Exception as exc:
                profile = {"symbol": symbol, "error": str(exc), "profile_fetched_at": now_iso()}
            with lock:
                if profile and profile.get("dr_per_underlying"):
                    cache[symbol] = profile
                else:
                    cache.setdefault(symbol, {"symbol": symbol, "error": "Not confirmed as SET DR", "profile_fetched_at": now_iso()})
    write_json(DR_PROFILE_CACHE, cache)
    return cache


def load_manual_map() -> dict[str, dict[str, str]]:
    if not MANUAL_MAP_CSV.exists():
        return {}
    with MANUAL_MAP_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        rows = csv.DictReader(f)
        return {
            (row.get("set_underlying") or row.get("dr_symbol") or "").strip().upper(): {
                k: (v or "").strip() for k, v in row.items()
            }
            for row in rows
            if (row.get("yahoo_symbol") or "").strip()
        }


def resolve_yahoo_symbol(record: dict[str, Any], manual_map: dict[str, dict[str, str]]) -> tuple[str | None, str]:
    symbol = str(record.get("symbol", "")).upper()
    underlying = str(record.get("underlying") or "").upper()
    underlying_name = str(record.get("underlying_name") or "").upper()
    underlying_exchange = str(record.get("underlying_exchange") or "").lower()
    if symbol in manual_map:
        return manual_map[symbol]["yahoo_symbol"], "manual_dr_symbol"
    if underlying in manual_map:
        return manual_map[underlying]["yahoo_symbol"], "manual_underlying"
    if underlying in BUILTIN_UNDERLYING_MAP:
        return BUILTIN_UNDERLYING_MAP[underlying], "built_in_alias"
    ticker_code = None
    paren_codes = re.findall(r"\(([A-Z0-9.\-]{1,16})\)", underlying_name)
    if paren_codes:
        ticker_code = paren_codes[-1]
    numeric_code = ticker_code if ticker_code and re.fullmatch(r"\d{3,6}", ticker_code) else None
    if ticker_code and ticker_code.endswith(".HK"):
        return ticker_code, "exchange_rule_explicit_code"
    if "hong kong" in underlying_exchange:
        if numeric_code:
            return f"{numeric_code.zfill(4)}.HK", "exchange_rule_hk"
        return None, "needs_mapping_hk"
    if "hochiminh" in underlying_exchange or "ho chi minh" in underlying_exchange:
        return f"{ticker_code or underlying}.VN", "exchange_rule_vietnam"
    if "singapore" in underlying_exchange:
        return f"{ticker_code or underlying}.SI", "exchange_rule_singapore"
    if "tokyo" in underlying_exchange:
        return f"{ticker_code or underlying}.T", "exchange_rule_tokyo"
    if "shanghai" in underlying_exchange:
        return f"{ticker_code or underlying}.SS", "exchange_rule_shanghai"
    if "shenzhen" in underlying_exchange:
        return f"{ticker_code or underlying}.SZ", "exchange_rule_shenzhen"
    if "taiwan" in underlying_exchange:
        return f"{ticker_code or underlying}.TW", "exchange_rule_taiwan"
    us_exchange = any(
        key in underlying_exchange
        for key in ["nasdaq", "new york stock exchange", "nyse", "nyse arca", "cboe", "american stock exchange"]
    )
    if us_exchange:
        candidate = ticker_code or underlying
        if candidate and re.match(r"^[A-Z.]{1,8}$", candidate):
            return candidate.replace(".", "-"), "same_as_set_underlying"
    return None, "needs_mapping"


def fetch_yahoo_quotes(symbols: list[str]) -> dict[str, dict[str, Any]]:
    clean = sorted({s for s in symbols if s})
    if not clean:
        return {}
    results: dict[str, dict[str, Any]] = {}
    for i in range(0, len(clean), 70):
        chunk = clean[i : i + 70]
        params = urllib.parse.urlencode({"symbols": ",".join(chunk), "fields": "regularMarketPrice,currency,bid,ask,regularMarketTime,shortName"})
        url = f"{YAHOO_QUOTE_URL}?{params}"
        try:
            data = json.loads(http_get(url, timeout=20, accept_json=True))
        except Exception:
            continue
        for item in data.get("quoteResponse", {}).get("result", []):
            sym = item.get("symbol")
            if sym:
                results[sym] = item
    missing = [symbol for symbol in clean if symbol not in results]
    if missing:
        with ThreadPoolExecutor(max_workers=14) as executor:
            futures = {executor.submit(fetch_yahoo_chart_quote, symbol): symbol for symbol in missing}
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    item = future.result()
                except Exception:
                    item = None
                if item:
                    results[symbol] = item
    return results


def fetch_yahoo_chart_quote(symbol: str) -> dict[str, Any] | None:
    encoded = urllib.parse.quote(symbol, safe="")
    data = json.loads(http_get(YAHOO_CHART_URL.format(symbol=encoded), timeout=14, accept_json=True))
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        return None
    meta = result.get("meta", {})
    price = meta.get("regularMarketPrice")
    if price is None:
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        closes = [v for v in quote.get("close", []) if v is not None]
        price = closes[-1] if closes else None
    if price is None:
        return None
    return {
        "symbol": meta.get("symbol") or symbol,
        "regularMarketPrice": price,
        "currency": meta.get("currency"),
        "regularMarketTime": meta.get("regularMarketTime"),
        "shortName": meta.get("shortName") or meta.get("exchangeName"),
        "exchangeName": meta.get("exchangeName"),
    }


def currency_to_thb_symbols(currencies: list[str]) -> dict[str, str]:
    mapping = {}
    for currency in sorted(set(currencies)):
        if not currency or currency == "THB":
            continue
        mapping[currency] = f"{currency}THB=X"
    return mapping


def build_dashboard(refresh: bool = False, force_profiles: bool = False) -> dict[str, Any]:
    ensure_dirs()
    if not refresh and DASHBOARD_CACHE.exists():
        cached = read_json(DASHBOARD_CACHE, {})
        if cached and time.time() - DASHBOARD_CACHE.stat().st_mtime < 900:
            return cached

    source_rows = discover_dr_price_rows()
    symbols = [row["symbol"] for row in source_rows]
    profiles = refresh_set_profiles(symbols, force=force_profiles)
    manual_map = load_manual_map()

    merged: list[dict[str, Any]] = []
    yahoo_symbols: list[str] = []
    for row in source_rows:
        profile = profiles.get(row["symbol"], {})
        if not profile.get("dr_per_underlying"):
            continue
        item = {**row, **profile}
        yahoo_symbol, mapping_source = resolve_yahoo_symbol(item, manual_map)
        item["yahoo_symbol"] = yahoo_symbol
        item["mapping_source"] = mapping_source
        if yahoo_symbol:
            yahoo_symbols.append(yahoo_symbol)
        merged.append(item)

    underlying_quotes = fetch_yahoo_quotes(yahoo_symbols)
    currencies = [q.get("currency") for q in underlying_quotes.values() if q.get("currency")]
    fx_symbols = currency_to_thb_symbols(currencies)
    fx_quotes = fetch_yahoo_quotes(list(fx_symbols.values()))
    fx_to_thb: dict[str, float] = {"THB": 1.0}
    for currency, fx_symbol in fx_symbols.items():
        price = parse_float(fx_quotes.get(fx_symbol, {}).get("regularMarketPrice"))
        if price:
            fx_to_thb[currency] = price

    rows: list[dict[str, Any]] = []
    for item in merged:
        quote = underlying_quotes.get(item.get("yahoo_symbol") or "", {})
        underlying_price = parse_float(quote.get("regularMarketPrice"))
        currency = quote.get("currency") or None
        fx = fx_to_thb.get(currency or "")
        dr_per_underlying = parse_float(item.get("dr_per_underlying"))
        dr_last = parse_float(item.get("dr_last"))
        fair_dr = None
        diff_pct = None
        implied_underlying = None
        if underlying_price and fx and dr_per_underlying and dr_last:
            fair_dr = underlying_price * fx / dr_per_underlying
            diff_pct = (dr_last / fair_dr - 1) * 100 if fair_dr else None
            implied_underlying = dr_last * dr_per_underlying / fx
        status = "ok" if diff_pct is not None else "needs_mapping_or_quote"
        if diff_pct is not None:
            if diff_pct > 2:
                status = "premium"
            elif diff_pct < -2:
                status = "discount"
        rows.append(
            {
                **item,
                "underlying_price": underlying_price,
                "underlying_currency": currency,
                "fx_to_thb": fx,
                "fair_dr": fair_dr,
                "diff_pct": diff_pct,
                "implied_underlying": implied_underlying,
                "underlying_short_name": quote.get("shortName"),
                "underlying_quote_time": quote.get("regularMarketTime"),
                "status": status,
            }
        )

    rows.sort(key=lambda r: (math.inf if r.get("diff_pct") is None else abs(r["diff_pct"])), reverse=True)
    payload = {
        "generated_at": now_iso(),
        "sources": {
            "dr_price_list": STOCKANALYSIS_URL,
            "dr_universe_fallback": STOCKPRICEPREDICTIONS_URL,
            "dr_profile": "SET DR factsheet pages",
            "underlying_quote": "Yahoo Finance quote endpoint",
        },
        "counts": {
            "candidate_symbols": len(source_rows),
            "confirmed_dr": len(rows),
            "with_diff": sum(1 for row in rows if row.get("diff_pct") is not None),
            "needs_mapping": sum(1 for row in rows if row.get("status") == "needs_mapping_or_quote"),
        },
        "rows": rows,
    }
    write_json(DASHBOARD_CACHE, payload)
    return payload


def to_public_row(row: dict[str, Any]) -> dict[str, Any]:
    keep = [
        "symbol",
        "company_name",
        "issuer",
        "underlying",
        "underlying_name",
        "underlying_exchange",
        "yahoo_symbol",
        "dr_last",
        "underlying_price",
        "underlying_currency",
        "fx_to_thb",
        "conversion_ratio",
        "dr_per_underlying",
        "fair_dr",
        "diff_pct",
        "implied_underlying",
        "dr_percent_change",
        "trading_session",
        "status",
        "mapping_source",
        "price_source",
        "source_url",
    ]
    return {key: row.get(key) for key in keep}


def export_csv(payload: dict[str, Any]) -> str:
    rows = [to_public_row(row) for row in payload.get("rows", [])]
    if not rows:
        return ""
    from io import StringIO

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


class Handler(BaseHTTPRequestHandler):
    server_version = "DRDashboard/1.0"

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path in {"/", "/index.html"}:
                self.serve_file(BASE_DIR / "index.html", "text/html; charset=utf-8")
            elif parsed.path.startswith("/web/"):
                target = WEB_DIR / parsed.path.removeprefix("/web/")
                content_type = "text/css" if target.suffix == ".css" else "application/javascript" if target.suffix == ".js" else "text/plain"
                self.serve_file(target, content_type)
            elif parsed.path == "/api/dashboard":
                refresh = query.get("refresh", ["0"])[0] == "1"
                force_profiles = query.get("force_profiles", ["0"])[0] == "1"
                payload = build_dashboard(refresh=refresh, force_profiles=force_profiles)
                self.send_json({**payload, "rows": [to_public_row(row) for row in payload.get("rows", [])]})
            elif parsed.path == "/api/export.csv":
                payload = build_dashboard(refresh=False)
                self.send_bytes(export_csv(payload).encode("utf-8-sig"), "text/csv; charset=utf-8")
            elif parsed.path == "/api/health":
                self.send_json({"ok": True, "time": now_iso()})
            else:
                self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self.send_json({"error": str(exc), "time": now_iso()}, status=500)

    def serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists() or not path.resolve().is_relative_to(BASE_DIR):
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        self.send_bytes(path.read_bytes(), content_type)

    def send_json(self, data: Any, status: int = 200) -> None:
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status=status)

    def send_bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), format % args))


def main() -> None:
    ensure_dirs()
    port = int(os.environ.get("PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"DR dashboard running at http://127.0.0.1:{port}")
    print("First refresh may take a few minutes while SET DR profiles are cached.")
    server.serve_forever()


if __name__ == "__main__":
    main()
