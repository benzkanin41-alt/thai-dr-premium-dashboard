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
SET_DR_MARKETDATA_URL = "https://www.set.or.th/en/market/product/dr/marketdata"
SET_DR_SEARCH_API_PATH = "/api/set/dr/search?tradeDateType=C&lang=en"
SET_DR_TRADE_DATE_API_PATH = "/api/set/dr/search/condition/trade-date"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1m&includePrePost=true"
GOOGLE_FINANCE_QUOTE_URL = "https://www.google.com/finance/quote/{base}-{quote}"

DR_PROFILE_CACHE = CACHE_DIR / "dr_profiles.json"
DASHBOARD_CACHE = CACHE_DIR / "dashboard.json"
MANUAL_MAP_CSV = DATA_DIR / "underlying_map.csv"
LOCAL_DR_OVERRIDES_CSV = DATA_DIR / "local_dr_overrides.csv"

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

EDGE_EXECUTABLE_CANDIDATES = [
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
    Path.home() / "AppData/Local/Microsoft/Edge/Application/msedge.exe",
]


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


def find_browser_executable() -> Path | None:
    env_path = os.environ.get("DR_DASHBOARD_BROWSER_EXECUTABLE")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    for candidate in EDGE_EXECUTABLE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def fetch_set_dr_market_rows_via_browser() -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Python Playwright is required for SET price refresh") from exc

    browser_path = find_browser_executable()
    with sync_playwright() as playwright:
        launch_options: dict[str, Any] = {
            "headless": True,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if browser_path:
            launch_options["executable_path"] = str(browser_path)
        browser = playwright.chromium.launch(**launch_options)
        try:
            page = browser.new_page(locale="en-US", timezone_id="Asia/Bangkok")
            page.goto(SET_DR_MARKETDATA_URL, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(8_000)
            result = page.evaluate(
                """async ([searchPath, tradeDatePath]) => {
                    async function fetchText(path) {
                        const response = await fetch(path, {
                            credentials: "include",
                            headers: { "accept": "application/json, text/plain, */*" }
                        });
                        return { ok: response.ok, status: response.status, text: await response.text() };
                    }
                    const tradeDateResponse = await fetch(tradeDatePath, {
                        credentials: "include",
                        headers: { "accept": "application/json, text/plain, */*" }
                    });
                    const tradeDates = tradeDateResponse.ok ? await tradeDateResponse.json() : [];
                    const types = [...new Set([...tradeDates.map((item) => item.type), "C", "P"].filter(Boolean))];
                    let fallback = null;
                    let best = null;
                    let bestScore = -1;
                    function orderPrice(value) {
                        if (!value || value.price === null || value.price === undefined) return null;
                        const text = String(value.price).replace(/,/g, "").trim();
                        if (!text || text === "-") return null;
                        const parsed = Number(text);
                        return Number.isFinite(parsed) ? parsed : null;
                    }
                    function priceScore(rows) {
                        return rows.filter((row) =>
                            row.last !== null && row.last !== undefined ||
                            row.prior !== null && row.prior !== undefined ||
                            orderPrice(row.bid) !== null ||
                            orderPrice(row.offer) !== null
                        ).length;
                    }
                    for (const type of types) {
                        const path = searchPath.replace("tradeDateType=C", `tradeDateType=${encodeURIComponent(type)}`);
                        const result = await fetchText(path);
                        if (!result.ok) {
                            fallback = fallback || result;
                            continue;
                        }
                        const payload = JSON.parse(result.text);
                        const rows = payload.data || [];
                        const score = priceScore(rows);
                        fallback = fallback || result;
                        if (score > bestScore) {
                            best = result;
                            bestScore = score;
                        }
                        if (rows.length && score >= rows.length) return result;
                    }
                    return best || fallback || { ok: false, status: 500, text: "No SET trade date payload" };
                }""",
                [SET_DR_SEARCH_API_PATH, SET_DR_TRADE_DATE_API_PATH],
            )
        finally:
            browser.close()

    if not result.get("ok"):
        raise RuntimeError(f"SET DR price refresh failed with HTTP {result.get('status')}: {result.get('text', '')[:300]}")
    payload = json.loads(result.get("text") or "{}")
    rows = payload.get("data") or []
    if not rows:
        raise RuntimeError("SET DR price refresh returned no rows")
    return {
        "date": payload.get("date"),
        "trading_date": payload.get("tradingDate"),
        "rows": rows,
    }


def parse_set_order_price(value: Any) -> float | None:
    if isinstance(value, dict):
        return parse_float(value.get("price"))
    return None


def parse_set_dr_market_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for item in payload.get("rows") or []:
        symbol = (item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        dr_last = parse_float(item.get("last"))
        prior = parse_float(item.get("prior"))
        bid_price = parse_set_order_price(item.get("bid"))
        offer_price = parse_set_order_price(item.get("offer"))
        dr_last_source_field = "last"
        if dr_last is None and prior is not None:
            dr_last = prior
            dr_last_source_field = "prior"
        if dr_last is None and bid_price is not None and offer_price is not None:
            dr_last = (bid_price + offer_price) / 2
            dr_last_source_field = "bid_offer_mid"
        elif dr_last is None and bid_price is not None:
            dr_last = bid_price
            dr_last_source_field = "bid"
        elif dr_last is None and offer_price is not None:
            dr_last = offer_price
            dr_last_source_field = "offer"
        dr_percent_change = parse_float(item.get("percentChange"))
        if dr_percent_change is None and dr_last_source_field == "prior":
            dr_percent_change = 0.0
        parsed.append(
            {
                "symbol": symbol,
                "company_name": item.get("name") or symbol,
                "market_cap": item.get("marketCap"),
                "dr_open": parse_float(item.get("open")),
                "dr_high": parse_float(item.get("high")),
                "dr_low": parse_float(item.get("low")),
                "dr_last": dr_last,
                "dr_percent_change": dr_percent_change,
                "dr_bid": bid_price,
                "dr_offer": offer_price,
                "dr_last_source_field": dr_last_source_field,
                "price_source": "SET official DR market data",
                "price_updated_at": payload.get("date"),
                "trade_date": payload.get("trading_date"),
            }
        )
    return parsed


def profile_from_set_dr_market_row(item: dict[str, Any]) -> dict[str, Any] | None:
    symbol = (item.get("symbol") or "").upper().strip()
    conversion_ratio = item.get("conversionRatio")
    underlying = item.get("underlying")
    dr_per_underlying = parse_conversion_ratio(conversion_ratio)
    if not symbol or not conversion_ratio or not underlying or not dr_per_underlying:
        return None
    return {
        "symbol": symbol,
        "set_name": item.get("name"),
        "issuer": item.get("issuer"),
        "issuer_name": item.get("issuerName"),
        "security_type": item.get("securityType") or "X",
        "status": "Listed",
        "first_trade_date": item.get("firstTradeDate"),
        "conversion_ratio": conversion_ratio,
        "dr_per_underlying": dr_per_underlying,
        "underlying": underlying,
        "underlying_name": item.get("underlyingName"),
        "underlying_class": item.get("underlyingClassName"),
        "underlying_exchange": item.get("underlyingExchange"),
        "underlying_url": item.get("underlyingUrl"),
        "indicative_price_symbol": None,
        "indicative_price_url": None,
        "trading_session": item.get("tradingSession"),
        "source_url": SET_FACTSHEET_URL.format(symbol=urllib.parse.quote(symbol)),
        "profile_fetched_at": now_iso(),
        "profile_source": "SET official DR market data",
    }


def update_profile_cache_from_set_market_rows(payload: dict[str, Any]) -> None:
    cache: dict[str, dict[str, Any]] = read_json(DR_PROFILE_CACHE, {})
    changed = False
    for item in payload.get("rows") or []:
        profile = profile_from_set_dr_market_row(item)
        if profile:
            cache[profile["symbol"]] = profile
            changed = True
    if changed:
        write_json(DR_PROFILE_CACHE, cache)


def parse_local_dr_override_rows() -> list[dict[str, Any]]:
    if not LOCAL_DR_OVERRIDES_CSV.exists():
        return []
    parsed: list[dict[str, Any]] = []
    with LOCAL_DR_OVERRIDES_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            symbol = (row.get("symbol") or "").upper().strip()
            if not symbol:
                continue
            parsed.append(
                {
                    "symbol": symbol,
                    "company_name": (row.get("company_name") or symbol).strip(),
                    "market_cap": None,
                    "dr_last": parse_float(row.get("dr_last")),
                    "dr_percent_change": parse_float(row.get("dr_percent_change")),
                    "price_source": row.get("price_source") or "Local SET DR override",
                }
            )
    return parsed


def discover_dr_price_rows(update_dr_prices: bool = False) -> list[dict[str, Any]]:
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
    try:
        for row in parse_local_dr_override_rows():
            combined.setdefault(row["symbol"], row)
    except Exception as exc:
        source_errors.append(f"Local override: {exc}")
    if update_dr_prices:
        try:
            set_payload = fetch_set_dr_market_rows_via_browser()
            update_profile_cache_from_set_market_rows(set_payload)
            for row in parse_set_dr_market_rows(set_payload):
                prior = combined.get(row["symbol"], {})
                if row.get("dr_last") is None and prior.get("dr_last") is not None:
                    row["dr_last"] = prior.get("dr_last")
                    row["dr_last_source_field"] = "previous_source"
                    row["price_source"] = f"SET official DR market data; DR price fallback from {prior.get('price_source', 'previous source')}"
                combined[row["symbol"]] = {**prior, **row}
        except Exception as exc:
            raise RuntimeError(f"SET DR price refresh failed: {exc}") from exc
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


def fetch_yahoo_quotes(symbols: list[str], include_extended: bool = False) -> dict[str, dict[str, Any]]:
    clean = sorted({s for s in symbols if s})
    if not clean:
        return {}
    results: dict[str, dict[str, Any]] = {}
    for i in range(0, len(clean), 70):
        chunk = clean[i : i + 70]
        fields = "regularMarketPrice,currency,bid,ask,regularMarketTime,shortName"
        if include_extended:
            fields += ",preMarketPrice,preMarketTime,postMarketPrice,postMarketTime"
        params = urllib.parse.urlencode({"symbols": ",".join(chunk), "fields": fields})
        url = f"{YAHOO_QUOTE_URL}?{params}"
        try:
            data = json.loads(http_get(url, timeout=20, accept_json=True))
        except Exception:
            continue
        for item in data.get("quoteResponse", {}).get("result", []):
            sym = item.get("symbol")
            if sym:
                normalize_quote_extended_fields(item)
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
    if include_extended:
        needs_extended = [
            symbol
            for symbol in clean
            if symbol in results
            and results[symbol].get("extendedMarketPrice") is None
            and results[symbol].get("preMarketPrice") is None
            and results[symbol].get("postMarketPrice") is None
        ]
        if needs_extended:
            with ThreadPoolExecutor(max_workers=14) as executor:
                futures = {executor.submit(fetch_yahoo_chart_quote, symbol): symbol for symbol in needs_extended}
                for future in as_completed(futures):
                    symbol = futures[future]
                    try:
                        chart_item = future.result()
                    except Exception:
                        chart_item = None
                    if chart_item:
                        results[symbol] = {**chart_item, **results[symbol], **extract_quote_extended_fields(chart_item)}
    return results


def normalize_quote_extended_fields(item: dict[str, Any]) -> None:
    item.update(extract_quote_extended_fields(item))


def extract_quote_extended_fields(item: dict[str, Any]) -> dict[str, Any]:
    if item.get("extendedMarketPrice") is not None:
        return {
            "extendedMarketPrice": item.get("extendedMarketPrice"),
            "extendedMarketSession": item.get("extendedMarketSession"),
            "extendedMarketTime": item.get("extendedMarketTime"),
        }
    if item.get("postMarketPrice") is not None:
        return {
            "extendedMarketPrice": item.get("postMarketPrice"),
            "extendedMarketSession": "Postmarket",
            "extendedMarketTime": item.get("postMarketTime"),
        }
    if item.get("preMarketPrice") is not None:
        return {
            "extendedMarketPrice": item.get("preMarketPrice"),
            "extendedMarketSession": "Premarket",
            "extendedMarketTime": item.get("preMarketTime"),
        }
    return {"extendedMarketPrice": None, "extendedMarketSession": None, "extendedMarketTime": None}


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
    extended = extract_extended_market_quote(result)
    return {
        "symbol": meta.get("symbol") or symbol,
        "regularMarketPrice": price,
        "currency": meta.get("currency"),
        "regularMarketTime": meta.get("regularMarketTime"),
        "extendedMarketPrice": extended.get("price"),
        "extendedMarketSession": extended.get("session"),
        "extendedMarketTime": extended.get("time"),
        "shortName": meta.get("shortName") or meta.get("exchangeName"),
        "exchangeName": meta.get("exchangeName"),
    }


def extract_extended_market_quote(result: dict[str, Any]) -> dict[str, Any]:
    meta = result.get("meta", {})
    if meta.get("postMarketPrice") is not None:
        return {"price": meta.get("postMarketPrice"), "session": "Postmarket", "time": meta.get("postMarketTime")}
    if meta.get("preMarketPrice") is not None:
        return {"price": meta.get("preMarketPrice"), "session": "Premarket", "time": meta.get("preMarketTime")}

    periods = meta.get("currentTradingPeriod") or {}
    pre = periods.get("pre") or {}
    regular = periods.get("regular") or {}
    post = periods.get("post") or {}
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    pairs = [(ts, close) for ts, close in zip(timestamps, closes) if close is not None]
    if not pairs:
        return {"price": None, "session": None, "time": None}

    def latest_between(start: Any, end: Any) -> tuple[Any, Any] | None:
        if start is None or end is None:
            return None
        matches = [(ts, close) for ts, close in pairs if start <= ts < end]
        return matches[-1] if matches else None

    latest = pairs[-1]
    if post.get("start") is not None and latest[0] >= post.get("start"):
        return {"price": latest[1], "session": "Postmarket", "time": latest[0]}

    pre_match = latest_between(pre.get("start"), regular.get("start") or pre.get("end"))
    if pre_match and latest[0] < (regular.get("start") or math.inf):
        return {"price": pre_match[1], "session": "Premarket", "time": pre_match[0]}

    return {"price": None, "session": None, "time": None}


def currency_to_thb_specs(currencies: list[str]) -> dict[str, list[dict[str, Any]]]:
    mapping = {}
    for currency in sorted(set(currencies)):
        if not currency or currency == "THB":
            continue
        if currency == "VND":
            mapping[currency] = [
                {"source": "google_finance", "base": "THB", "quote": "VND", "symbol": "Google Finance THB-VND", "invert": True},
                {"source": "google_finance", "base": "VND", "quote": "THB", "symbol": "Google Finance VND-THB", "invert": False},
                {"source": "yahoo", "symbol": "VNDTHB=X", "invert": False},
            ]
        else:
            mapping[currency] = [{"source": "yahoo", "symbol": f"{currency}THB=X", "invert": False}]
    return mapping


def resolve_fx_to_thb(currency: str, specs: list[dict[str, Any]], quotes: dict[str, dict[str, Any]]) -> tuple[float | None, str | None]:
    for spec in specs:
        symbol = spec["symbol"]
        if spec.get("source") == "google_finance":
            price = fetch_google_finance_fx(str(spec["base"]), str(spec["quote"]))
        else:
            price = parse_float(quotes.get(symbol, {}).get("regularMarketPrice"))
        if not price:
            continue
        if spec.get("invert"):
            return 1 / price, f"{symbol} inverted"
        return price, symbol
    return None, None


def fetch_google_finance_fx(base: str, quote: str) -> float | None:
    url = GOOGLE_FINANCE_QUOTE_URL.format(base=urllib.parse.quote(base), quote=urllib.parse.quote(quote))
    body = http_get(url, timeout=20)
    pair_label = f"{base} / {quote}"
    match = re.search(
        rf'"{re.escape(pair_label)}"\s*,\s*\d+\s*,\s*null\s*,\s*\[\s*([-+]?\d+(?:\.\d+)?)',
        body,
    )
    if match:
        return parse_float(match.group(1))
    return None


def build_dashboard(refresh: bool = False, force_profiles: bool = False, update_dr_prices: bool = False) -> dict[str, Any]:
    ensure_dirs()
    cached = read_json(DASHBOARD_CACHE, {}) if DASHBOARD_CACHE.exists() else {}
    if not refresh and not update_dr_prices and DASHBOARD_CACHE.exists():
        if cached:
            return cached

    try:
        source_rows = discover_dr_price_rows(update_dr_prices=update_dr_prices)
    except Exception:
        if cached:
            cached = dict(cached)
            cached["served_from_stale_cache"] = True
            cached["cache_warning"] = "Live refresh failed; served last cached dashboard data."
            return cached
        raise
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

    underlying_quotes = fetch_yahoo_quotes(yahoo_symbols, include_extended=True)
    currencies = [q.get("currency") for q in underlying_quotes.values() if q.get("currency")]
    fx_specs = currency_to_thb_specs(currencies)
    fx_quote_symbols = [spec["symbol"] for specs in fx_specs.values() for spec in specs if spec.get("source") == "yahoo"]
    fx_quotes = fetch_yahoo_quotes(fx_quote_symbols)
    fx_to_thb: dict[str, float] = {"THB": 1.0}
    fx_sources: dict[str, str] = {"THB": "THB"}
    for currency, specs in fx_specs.items():
        price, source = resolve_fx_to_thb(currency, specs, fx_quotes)
        if price:
            fx_to_thb[currency] = price
            if source:
                fx_sources[currency] = source

    rows: list[dict[str, Any]] = []
    for item in merged:
        quote = underlying_quotes.get(item.get("yahoo_symbol") or "", {})
        underlying_price = parse_float(quote.get("regularMarketPrice"))
        underlying_ext_price = parse_float(quote.get("extendedMarketPrice"))
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
                "underlying_ext_price": underlying_ext_price,
                "underlying_ext_session": quote.get("extendedMarketSession"),
                "underlying_ext_time": quote.get("extendedMarketTime"),
                "underlying_currency": currency,
                "fx_to_thb": fx,
                "fx_source_symbol": fx_sources.get(currency or ""),
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
            "dr_universe_local_override": str(LOCAL_DR_OVERRIDES_CSV),
            "dr_price_manual_refresh": "SET official DR market data via local browser",
            "dr_profile": "SET DR factsheet pages",
            "underlying_quote": "Yahoo Finance quote endpoint",
            "fx_quote": "Yahoo Finance FX pairs; VND uses Google Finance THB-VND inverted",
        },
        "counts": {
            "candidate_symbols": len(source_rows),
            "confirmed_dr": len(rows),
            "with_diff": sum(1 for row in rows if row.get("diff_pct") is not None),
            "needs_mapping": sum(1 for row in rows if row.get("status") == "needs_mapping_or_quote"),
        },
        "manual_price_update": update_dr_prices,
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
        "underlying_ext_price",
        "underlying_ext_session",
        "underlying_ext_time",
        "underlying_currency",
        "fx_to_thb",
        "fx_source_symbol",
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


def write_public_dashboard_files(payload: dict[str, Any]) -> None:
    public_payload = {
        **payload,
        "rows": [to_public_row(row) for row in payload.get("rows", [])],
    }
    (DATA_DIR / "dashboard.json").write_text(
        json.dumps(public_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    csv_text = export_csv(payload)
    if csv_text:
        (DATA_DIR / "dashboard.csv").write_text(csv_text, encoding="utf-8-sig")


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
                update_dr_prices = query.get("update_prices", ["0"])[0] == "1"
                payload = build_dashboard(
                    refresh=refresh or update_dr_prices,
                    force_profiles=force_profiles,
                    update_dr_prices=update_dr_prices,
                )
                if update_dr_prices:
                    write_public_dashboard_files(payload)
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
