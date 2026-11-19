#!/usr/bin/env python3
"""Fetch public market quotes and write quotes.json.

Public sources only (no brokerage credentials):
  * Yahoo Finance chart API — stocks, ETFs, Hang Seng Index, COMEX gold futures
  * Gold API (api.gold-api.com) — XAUUSD indicative mid

Never read or write Futu / brokerage tokens.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")
NY = ZoneInfo("America/New_York")
UTC = timezone.utc

YAHOO_UA = (
    "Mozilla/5.0 (compatible; PredictWatch/1.0; "
    "+https://github.com/RILAKKUMA-KUKI/predict)"
)
GOLD_API_URL = "https://api.gold-api.com/price/XAU"
YAHOO_HOSTS = (
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
    "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
)

US_HOLIDAYS = {
    date(2025, 1, 1), date(2025, 1, 20), date(2025, 2, 17), date(2025, 4, 18),
    date(2025, 5, 26), date(2025, 6, 19), date(2025, 7, 4), date(2025, 9, 1),
    date(2025, 11, 27), date(2025, 12, 25),
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3),
    date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7),
    date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
    date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6),
    date(2027, 11, 25), date(2027, 12, 24),
}

HK_HOLIDAYS = {
    date(2025, 1, 1), date(2025, 1, 29), date(2025, 1, 30), date(2025, 1, 31),
    date(2025, 4, 4), date(2025, 4, 18), date(2025, 4, 21), date(2025, 5, 1),
    date(2025, 5, 5), date(2025, 7, 1), date(2025, 10, 1), date(2025, 10, 7),
    date(2025, 10, 29), date(2025, 12, 25), date(2025, 12, 26),
    date(2026, 1, 1), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19),
    date(2026, 4, 3), date(2026, 4, 6), date(2026, 4, 7), date(2026, 5, 1),
    date(2026, 6, 19), date(2026, 7, 1), date(2026, 10, 1), date(2026, 10, 19),
    date(2026, 12, 25), date(2026, 12, 26),
    date(2027, 1, 1), date(2027, 2, 8), date(2027, 2, 9), date(2027, 2, 10),
    date(2027, 3, 26), date(2027, 4, 5), date(2027, 5, 3), date(2027, 6, 9),
    date(2027, 7, 1), date(2027, 10, 1), date(2027, 10, 19), date(2027, 12, 27),
}

# Default table order: US ETFs (VOO first), US stocks, Hong Kong, gold.
SYMBOLS: list[dict[str, str]] = [
    {"code": "US.VOO", "yahoo": "VOO", "name": "標普500（Vanguard）", "unit": "USD", "tab": "us_etf"},
    {"code": "US.SPY", "yahoo": "SPY", "name": "標普500（SPDR）", "unit": "USD", "tab": "us_etf"},
    {"code": "US.IVV", "yahoo": "IVV", "name": "標普500（iShares）", "unit": "USD", "tab": "us_etf"},
    {"code": "US.VTI", "yahoo": "VTI", "name": "整體美股", "unit": "USD", "tab": "us_etf"},
    {"code": "US.VT", "yahoo": "VT", "name": "全球股市", "unit": "USD", "tab": "us_etf"},
    {"code": "US.QQQ", "yahoo": "QQQ", "name": "納指100", "unit": "USD", "tab": "us_etf"},
    {"code": "US.QQQM", "yahoo": "QQQM", "name": "納指100（較低價）", "unit": "USD", "tab": "us_etf"},
    {"code": "US.DIA", "yahoo": "DIA", "name": "道指 ETF", "unit": "USD", "tab": "us_etf"},
    {"code": "US.AAPL", "yahoo": "AAPL", "name": "蘋果", "unit": "USD", "tab": "us_stock"},
    {"code": "US.MSFT", "yahoo": "MSFT", "name": "微軟", "unit": "USD", "tab": "us_stock"},
    {"code": "US.AMZN", "yahoo": "AMZN", "name": "亞馬遜", "unit": "USD", "tab": "us_stock"},
    {"code": "US.GOOGL", "yahoo": "GOOGL", "name": "谷歌（A 股）", "unit": "USD", "tab": "us_stock"},
    {"code": "US.META", "yahoo": "META", "name": "Meta", "unit": "USD", "tab": "us_stock"},
    {"code": "US.TSLA", "yahoo": "TSLA", "name": "特斯拉", "unit": "USD", "tab": "us_stock"},
    {"code": "US.NVDA", "yahoo": "NVDA", "name": "英偉達", "unit": "USD", "tab": "us_stock"},
    {"code": "US.AVGO", "yahoo": "AVGO", "name": "博通", "unit": "USD", "tab": "us_stock"},
    {"code": "HK.800000", "yahoo": "^HSI", "name": "恒生指數", "unit": "POINT", "tab": "hk"},
    {"code": "HK.00700", "yahoo": "0700.HK", "name": "騰訊", "unit": "HKD", "tab": "hk"},
    {"code": "HK.09988", "yahoo": "9988.HK", "name": "阿里巴巴", "unit": "HKD", "tab": "hk"},
    {"code": "HK.03690", "yahoo": "3690.HK", "name": "美團", "unit": "HKD", "tab": "hk"},
    {"code": "HK.01810", "yahoo": "1810.HK", "name": "小米", "unit": "HKD", "tab": "hk"},
    {"code": "HK.00005", "yahoo": "0005.HK", "name": "滙豐", "unit": "HKD", "tab": "hk"},
    {"code": "HK.00388", "yahoo": "0388.HK", "name": "港交所", "unit": "HKD", "tab": "hk"},
    {"code": "HK.00941", "yahoo": "0941.HK", "name": "中國移動", "unit": "HKD", "tab": "hk"},
    {"code": "HK.02800", "yahoo": "2800.HK", "name": "盈富基金", "unit": "HKD", "tab": "hk"},
    {"code": "HK.03033", "yahoo": "3033.HK", "name": "恒生科技 ETF", "unit": "HKD", "tab": "hk"},
    {"code": "XAUUSD", "yahoo": "GC=F", "name": "現貨黃金（主要黃金）", "unit": "USD", "tab": "gold"},
    {"code": "US.GLDM", "yahoo": "GLDM", "name": "黃金 ETF（MiniShares）", "unit": "USD", "tab": "gold"},
    {"code": "US.GLD", "yahoo": "GLD", "name": "黃金 ETF（SPDR）", "unit": "USD", "tab": "gold"},
]


def now_hk() -> datetime:
    return datetime.now(tz=HK)


def fmt_hkt(dt: datetime | None, with_seconds: bool = True) -> str | None:
    if dt is None:
        return None
    local = dt.astimezone(HK)
    return local.strftime("%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M")


def fmt_clock(dt: datetime) -> str:
    return dt.astimezone(HK).strftime("%H:%M")


def parse_unix(ts: int | float | None) -> datetime | None:
    if ts is None:
        return None
    value = float(ts)
    if value > 10_000_000_000:
        value = value / 1000.0
    return datetime.fromtimestamp(value, tz=UTC)


def http_get_json(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> Any:
    hdrs = {"User-Agent": YAHOO_UA, "Accept": "application/json,text/plain,*/*"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def http_get_json_retry(url: str, attempts: int = 3, timeout: int = 20, headers: dict[str, str] | None = None) -> Any:
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            return http_get_json(url, timeout=timeout, headers=headers)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_err = exc
            time.sleep(0.6 * (i + 1))
    assert last_err is not None
    raise last_err


def yahoo_chart(symbol: str, range_: str, interval: str, include_prepost: bool = False) -> dict[str, Any]:
    params = {"range": range_, "interval": interval, "includePrePost": "true" if include_prepost else "false"}
    query = urllib.parse.urlencode(params)
    last_err: Exception | None = None
    for host in YAHOO_HOSTS:
        url = host.format(symbol=urllib.parse.quote(symbol, safe="")) + "?" + query
        try:
            data = http_get_json_retry(url, attempts=2)
        except Exception as exc:  # noqa: BLE001 — try the next host
            last_err = exc
            continue
        chart = data.get("chart") or {}
        result = chart.get("result") or []
        error = chart.get("error")
        if result:
            return result[0]
        last_err = RuntimeError(f"{symbol}: {error or 'empty Yahoo result'}")
    raise last_err or RuntimeError(f"{symbol}: Yahoo chart failed")


def extract_bars(chart: dict[str, Any], tz: ZoneInfo) -> list[dict[str, Any]]:
    timestamps = chart.get("timestamp") or []
    quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or [None] * len(timestamps)
    highs = quote.get("high") or [None] * len(timestamps)
    lows = quote.get("low") or [None] * len(timestamps)
    closes = quote.get("close") or [None] * len(timestamps)
    volumes = quote.get("volume") or [None] * len(timestamps)
    bars: list[dict[str, Any]] = []
    for ts, o, h, l, c, v in zip(timestamps, opens, highs, lows, closes, volumes):
        if c is None:
            continue
        dt = parse_unix(ts)
        if dt is None:
            continue
        bars.append({
            "date": dt.astimezone(tz).date().isoformat(),
            "ts": int(ts),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": v,
        })
    return bars


def weekly_from_daily(daily: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for bar in daily:
        d = date.fromisoformat(bar["date"])
        iso = d.isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(bar)
    weekly: list[dict[str, Any]] = []
    for key in order:
        chunk = groups[key]
        highs = [b["high"] for b in chunk if b.get("high") is not None]
        lows = [b["low"] for b in chunk if b.get("low") is not None]
        weekly.append({
            "date": chunk[-1]["date"],
            "open": chunk[0].get("open"),
            "high": max(highs) if highs else chunk[-1]["close"],
            "low": min(lows) if lows else chunk[-1]["close"],
            "close": chunk[-1]["close"],
            "volume": sum(b["volume"] or 0 for b in chunk),
        })
    return weekly


def returns(closes: list[float], n: int) -> float | None:
    if len(closes) <= n or not closes[-1 - n]:
        return None
    return (closes[-1] / closes[-1 - n] - 1.0) * 100.0


def sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    window = values[-n:]
    return sum(window) / n


def is_us_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in US_HOLIDAYS


def is_hk_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in HK_HOLIDAYS


def next_us_session_open(now: datetime) -> datetime:
    """Next US regular cash open (09:30 America/New_York) after `now`."""
    local = now.astimezone(NY)
    candidate = datetime.combine(local.date(), dt_time(9, 30), tzinfo=NY)
    if local >= candidate:
        candidate = datetime.combine(local.date() + timedelta(days=1), dt_time(9, 30), tzinfo=NY)
    while not is_us_trading_day(candidate.date()):
        candidate = datetime.combine(candidate.date() + timedelta(days=1), dt_time(9, 30), tzinfo=NY)
    return candidate


def us_state(now: datetime) -> str:
    """Return pre / regular / post / closed."""
    local = now.astimezone(NY)
    if not is_us_trading_day(local.date()):
        return "closed"
    t = local.timetz().replace(tzinfo=None) if False else local.time()
    if dt_time(4, 0) <= t < dt_time(9, 30):
        return "pre"
    if dt_time(9, 30) <= t < dt_time(16, 0):
        return "regular"
    if dt_time(16, 0) <= t < dt_time(20, 0):
        return "post"
    return "closed"


def hk_state(now: datetime) -> str:
    local = now.astimezone(HK)
    if not is_hk_trading_day(local.date()):
        return "closed"
    t = local.time()
    if dt_time(9, 30) <= t < dt_time(12, 0):
        return "morning"
    if dt_time(12, 0) <= t < dt_time(13, 0):
        return "lunch"
    if dt_time(13, 0) <= t < dt_time(16, 0):
        return "afternoon"
    return "closed"


def session_date_label(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    # US regular close at 16:00 ET is already the next calendar day in HKT.
    # Label the session by the exchange's local date.
    return dt.astimezone(NY).strftime("%Y-%m-%d") if dt.tzinfo else None


def build_session_labels(
    now: datetime,
    us_regular_dt: datetime | None,
    hk_regular_dt: datetime | None,
    xau_dt: datetime | None,
    xau_price: float | None,
) -> dict[str, Any]:
    us = us_state(now)
    hk = hk_state(now)
    nxt = next_us_session_open(now)
    open_hkt = fmt_clock(nxt)
    us_date = None
    if us_regular_dt is not None:
        us_date = us_regular_dt.astimezone(NY).strftime("%Y-%m-%d")
    if us == "regular":
        us_regular_label = f"現為美股正市（至 {fmt_clock(datetime.combine(now.astimezone(NY).date(), dt_time(16, 0), tzinfo=NY))} 香港時間）"
        us_ext_label = "正市進行中"
    elif us == "pre":
        us_regular_label = (
            f"正市報價仍為 {us_date} 收市。"
            f"今日正市 {open_hkt}（香港時間）才開"
            if us_date else f"今日正市 {open_hkt}（香港時間）才開"
        )
        us_ext_label = "現為盤前時段"
    elif us == "post":
        us_regular_label = f"正市報價為 {us_date} 收市" if us_date else "正市已收市"
        us_ext_label = "現為夜盤／盤後時段"
    else:
        us_regular_label = (
            f"已收市。正市報價仍為 {us_date} 收市。"
            f"下一場正市 {open_hkt}（香港時間）才開"
            if us_date else f"已收市。下一場正市 {open_hkt}（香港時間）才開"
        )
        us_ext_label = "延伸時段已完，或尚未開始"

    hk_date = hk_regular_dt.astimezone(HK).strftime("%Y-%m-%d") if hk_regular_dt else None
    if hk == "morning":
        hk_label = "現為上午時段（09:30–12:00，香港時間）"
    elif hk == "lunch":
        hk_label = "現為午休（12:00–13:00，香港時間）"
    elif hk == "afternoon":
        hk_label = "現為下午時段（13:00–16:00，香港時間）"
    else:
        if hk_date:
            weekday = now.astimezone(HK)
            if is_hk_trading_day(weekday.date()) and weekday.time() < dt_time(9, 30):
                hk_label = f"尚未開市。報價仍為 {hk_date} 收市（香港時間）"
            else:
                hk_label = f"已收市。報價為 {hk_date} 收市（香港時間）"
        else:
            hk_label = "港股時段未有可用報價時間"

    # Gold / FX-style session: roughly Sun 18:00 ET to Fri 17:00 ET.
    gold_open = False
    ny = now.astimezone(NY)
    wd = ny.weekday()  # Mon=0
    t = ny.time()
    if wd == 5:
        gold_open = False
    elif wd == 6:
        gold_open = t >= dt_time(18, 0)
    elif wd == 4:
        gold_open = t < dt_time(17, 0)
    else:
        gold_open = True
    if xau_price is None:
        xau_label = "未能取得 XAUUSD 公開指示價"
    else:
        when = fmt_hkt(xau_dt) or "時間不詳"
        mid = f"指示中間價 {xau_price:,.2f}"
        if gold_open:
            xau_label = f"交易時段。{when}（香港時間），{mid}"
        else:
            xau_label = f"金市通常已休市。最近指示價於 {when}（香港時間），{mid}"

    return {
        "usRegular": {"state": us, "label": us_regular_label},
        "usExtended": {"state": us, "label": us_ext_label},
        "hk": {"state": hk, "label": hk_label},
        "xauusd": {"state": "open" if gold_open else "closed", "label": xau_label},
    }


def pos_desc(pos52: float | None) -> str:
    if pos52 is None:
        return ""
    if pos52 < 30:
        return "偏下"
    if pos52 < 70:
        return "中間"
    if pos52 < 90:
        return "偏上"
    return "高位"


def signed_pct(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ("−" if value < 0 else "")
    return f"{sign}{abs(value):.{digits}f}%"


def fmt_px(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "POINT":
        return f"{value:,.2f}"
    if abs(value) < 10:
        return f"{value:,.3f}"
    return f"{value:,.2f}"



def px_decimals(value: float | None, unit: str) -> int:
    if unit == "POINT":
        return 2
    if value is None:
        return 2
    if abs(value) < 10:
        return 3
    return 2


def round_px(value: float | None, unit: str, last: float | None = None) -> float | None:
    if value is None:
        return None
    return round(float(value), px_decimals(last if last is not None else value, unit))


def min_level_gap(last: float, unit: str) -> float:
    return max(abs(last) * 0.0015, 10 ** (-px_decimals(last, unit)))


def compute_levels(
    last: float,
    session_low: float | None,
    session_high: float | None,
    daily: list[dict[str, Any]],
    low52: float | None,
    high52: float | None,
    unit: str = "USD",
) -> dict[str, Any]:
    eps = min_level_gap(last, unit)
    recent = daily[-20:] if daily else []
    candidates_below: list[tuple[float, str]] = []
    candidates_above: list[tuple[float, str]] = []

    if session_low is not None and session_low < last - eps:
        candidates_below.append((float(session_low), "今趟低位"))
    if session_high is not None and session_high > last + eps:
        candidates_above.append((float(session_high), "今趟高位"))

    seen_lo: set[float] = set()
    seen_hi: set[float] = set()
    for bar in recent:
        lo, hi = bar.get("low"), bar.get("high")
        if lo is not None and lo < last - eps:
            key = round(float(lo), 6)
            if key not in seen_lo:
                seen_lo.add(key)
                candidates_below.append((float(lo), "近期低位"))
        if hi is not None and hi > last + eps:
            key = round(float(hi), 6)
            if key not in seen_hi:
                seen_hi.add(key)
                candidates_above.append((float(hi), "近期高位"))

    if low52 is not None and low52 < last - eps:
        candidates_below.append((float(low52), "近一年低位"))
    if high52 is not None and high52 > last + eps:
        candidates_above.append((float(high52), "近一年高位"))

    near_year_low = bool(low52 is not None and last <= float(low52) * 1.008)

    # Support may use the 1-year low only when it is the nearest real low
    # (no nearer short-term low). 跌穿 / breakDown never uses the 1-year low.
    short_term_below = [item for item in candidates_below if item[1] != "近一年低位"]

    if short_term_below:
        support_val, support_note = max(short_term_below, key=lambda x: x[0])
    elif near_year_low and low52 is not None:
        support_val, support_note = float(low52), "近一年低位"
    elif candidates_below:
        support_val, support_note = max(candidates_below, key=lambda x: x[0])
    else:
        support_val, support_note = None, "暫無更近真實成交"

    short_below_support = [
        item for item in short_term_below
        if support_val is not None and item[0] < support_val - eps
    ]
    # Do not invent a target below the observed ~1-year low.
    if low52 is not None:
        short_below_support = [
            item for item in short_below_support
            if item[0] >= float(low52) - eps
        ]

    if short_below_support:
        down_val, down_note = max(short_below_support, key=lambda x: x[0])
    elif near_year_low:
        # Already at / very near a ~1-year low: do not invent a lower target.
        down_val, down_note = None, "已近一年低位，暫無更近短線低位"
        if support_val is None and low52 is not None:
            support_val, support_note = float(low52), "近一年低位"
    else:
        down_val, down_note = None, "暫無更近短線低位"

    if candidates_above:
        up_val, up_note = min(candidates_above, key=lambda x: x[0])
    else:
        up_val, up_note = None, "已近高位或暫無更近真實成交"

    return {
        "support": {"value": round_px(support_val, unit, last), "note": support_note},
        "breakUp": {"value": round_px(up_val, unit, last), "note": up_note},
        "breakDown": {"value": round_px(down_val, unit, last), "note": down_note},
        "nearYearLow": near_year_low,
    }


def outlook_for(row: dict[str, Any], daily: list[dict[str, Any]], us_state_now: str, hk_state_now: str) -> dict[str, str]:
    last = row["last"]
    unit = row["unit"]
    closes = [float(b["close"]) for b in daily]
    ret5 = returns(closes, 5)
    ret21 = returns(closes, 21)
    sma20 = sma(closes, 20)
    sma20_prev = sma(closes[:-1], 20) if len(closes) > 20 else None
    pos52 = row.get("pos52Pct")
    dist_high = row.get("distHighPct")
    pct = row.get("changePct")
    pre_pct = row.get("preChangePct")
    post_pct = row.get("postChangePct")
    levels = row["levels"]
    near_year_low = levels.get("nearYearLow")

    score = 0
    if sma20 is not None:
        if last > sma20 * 1.002:
            score += 1
        elif last < sma20 * 0.998:
            score -= 1
        if sma20_prev is not None:
            if sma20 > sma20_prev:
                score += 1
            elif sma20 < sma20_prev:
                score -= 1
    if ret5 is not None:
        if ret5 > 1.5:
            score += 1
        elif ret5 < -1.5:
            score -= 1
    if pct is not None:
        if pct > 1.0:
            score += 1
        elif pct < -1.0:
            score -= 1
    if pos52 is not None and pos52 < 10:
        score -= 1
    if near_year_low:
        score = min(score, -1)

    # Extended-session move can nudge the score, but does not flip a closed cash session alone.
    ext = pre_pct if us_state_now == "pre" else (post_pct if us_state_now == "post" else None)
    if ext is not None and abs(ext) > 1.0:
        score += 1 if ext > 0 else -1

    if score >= 2:
        bias = "偏多"
    elif score <= -2:
        bias = "偏空"
    else:
        bias = "觀望"

    # Context sentence.
    bits: list[str] = []
    regular_dt = parse_unix(row.get("regularTimeUnix"))
    if row["tab"] in {"us_etf", "us_stock"} or row["code"] in {"US.GLD", "US.GLDM"}:
        sess = regular_dt.astimezone(NY).strftime("%m-%d") if regular_dt else None
        if us_state_now == "regular":
            head = f"正市 {fmt_px(last, unit)}（{signed_pct(pct)}）"
        elif sess:
            head = f"正市仍為 {sess} 收市 {fmt_px(last, unit)}（{signed_pct(pct)}）"
        else:
            head = f"正市 {fmt_px(last, unit)}（{signed_pct(pct)}）"
        bits.append(head)
        if pos52 is not None:
            bits.append(f"處於近一年區間{pos_desc(pos52)}（約 {pos52:.1f}%）")
        if dist_high is not None:
            bits.append(f"距高約 {abs(dist_high):.1f}%")
        if ret21 is not None:
            bits.append(f"近月約 {signed_pct(ret21)}")
        if us_state_now == "pre" and row.get("prePrice") is not None:
            bits.append(f"盤前 {fmt_px(row['prePrice'], unit)}（{signed_pct(pre_pct)}）")
        elif us_state_now == "post" and row.get("postPrice") is not None:
            bits.append(f"夜盤 {fmt_px(row['postPrice'], unit)}（{signed_pct(post_pct)}）")
    elif row["code"] == "XAUUSD":
        prev = row.get("prevClose")
        bits.append(
            f"現貨指示中間價約 {fmt_px(last, unit)}"
            + (f"，較前收 {fmt_px(prev, unit)} {signed_pct(pct)}" if prev is not None else f"（{signed_pct(pct)}）")
        )
        if row.get("low") is not None and row.get("high") is not None:
            bits.append(f"參考日線曾低見 {fmt_px(row['low'], unit)}、高見 {fmt_px(row['high'], unit)}")
        if pos52 is not None:
            bits.append(f"近一年區間{pos_desc(pos52)}（約 {pos52:.1f}%）")
        bits.append("日線高低及走勢參考 COMEX 黃金期貨（GC=F）")
    else:
        sess = regular_dt.astimezone(HK).strftime("%m-%d") if regular_dt else None
        if hk_state_now in {"morning", "afternoon", "lunch"}:
            head = f"現價 {fmt_px(last, unit)}（{signed_pct(pct)}）"
        elif sess:
            head = f"{sess} 收市 {fmt_px(last, unit)}（{signed_pct(pct)}）"
        else:
            head = f"報價 {fmt_px(last, unit)}（{signed_pct(pct)}）"
        bits.append(head)
        if pos52 is not None:
            bits.append(f"處於近一年區間{pos_desc(pos52)}（約 {pos52:.1f}%）")
        if dist_high is not None:
            bits.append(f"距高約 {abs(dist_high):.1f}%")
        if ret5 is not None:
            bits.append(f"近一週約 {signed_pct(ret5)}")
        elif ret21 is not None:
            bits.append(f"近月約 {signed_pct(ret21)}")

    view = "，".join(bits) + "。"
    if near_year_low:
        view += "接近近一年低位。"

    def level_txt(item: dict[str, Any] | None) -> str | None:
        if not item:
            return None
        if item.get("value") is not None:
            return fmt_px(item["value"], unit)
        return None

    support_txt = level_txt(levels.get("support"))
    up_txt = level_txt(levels.get("breakUp"))
    down_txt = level_txt(levels.get("breakDown"))

    if support_txt:
        weaken = f"跌破並失守約 {support_txt}，短線看法轉弱。"
    elif near_year_low:
        weaken = "已接近近一年低位，暫無更近短線低位可作跌穿參考。"
    else:
        weaken = "若失守近期低位，短線看法轉弱。"

    risk_parts: list[str] = []
    if up_txt:
        risk_parts.append(f"上行參考 {up_txt}")
    if support_txt and down_txt:
        risk_parts.append(f"下行失守 {support_txt} 後，短線跌穿參考 {down_txt}")
    elif support_txt and near_year_low:
        risk_parts.append(f"下行失守 {support_txt} 後已近一年低位，暫無更近短線低位")
    elif near_year_low:
        risk_parts.append("已近一年低位，暫無更近短線低位")
    elif support_txt:
        risk_parts.append(f"下行失守 {support_txt} 後暫無更近短線低位")
    risk = "；".join(risk_parts) + "。短線看法按規則重計，並非保證。" if risk_parts else "短線看法按規則重計，並非保證。"

    return {"bias": bias, "view": view, "weaken": weaken, "risk": risk}


def empty_quote(spec: dict[str, str], status: str, error: str | None) -> dict[str, Any]:
    return {
        "code": spec["code"],
        "yahoo": spec["yahoo"],
        "name": spec["name"],
        "unit": spec["unit"],
        "tab": spec["tab"],
        "status": status,
        "error": error,
        "last": None,
        "change": None,
        "changePct": None,
        "open": None,
        "high": None,
        "low": None,
        "volume": None,
        "prevClose": None,
        "high52": None,
        "low52": None,
        "distHighPct": None,
        "pos52Pct": None,
        "prePrice": None,
        "preChangePct": None,
        "postPrice": None,
        "postChangePct": None,
        "regularTimeHKT": None,
        "regularTimeUnix": None,
        "quoteTimeHKT": None,
        "bias": None,
        "view": None,
        "weaken": None,
        "risk": None,
        "levels": {
            "support": {"value": None, "note": None},
            "breakUp": {"value": None, "note": None},
            "breakDown": {"value": None, "note": None},
            "nearYearLow": False,
        },
        "historyDaily": [],
        "historyWeekly": [],
    }


def fetch_gold_spot() -> dict[str, Any] | None:
    try:
        data = http_get_json_retry(GOLD_API_URL, attempts=3, timeout=15)
    except Exception as exc:  # noqa: BLE001
        print(f"Gold API failed: {exc}", file=sys.stderr)
        return None
    price = data.get("price")
    if not isinstance(price, (int, float)):
        print(f"Gold API unexpected payload: {data!r}", file=sys.stderr)
        return None
    updated = data.get("updatedAt")
    dt = None
    if isinstance(updated, str):
        try:
            dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        except ValueError:
            dt = None
    return {"price": float(price), "time": dt, "raw": data}


def build_quote(spec: dict[str, str], gold_spot: dict[str, Any] | None, us_now: str, hk_now: str) -> dict[str, Any]:
    is_xau = spec["code"] == "XAUUSD"
    exchange_tz = HK if spec["code"].startswith("HK.") else NY
    try:
        year = yahoo_chart(spec["yahoo"], "1y", "1d", include_prepost=False)
    except Exception as exc:  # noqa: BLE001
        return empty_quote(spec, "error", str(exc))

    meta = year.get("meta") or {}
    daily = extract_bars(year, exchange_tz)
    if not daily and meta.get("regularMarketPrice") is None and not (is_xau and gold_spot):
        return empty_quote(spec, "error", "Yahoo 沒有可用價格")

    last_regular = meta.get("regularMarketPrice")
    high = meta.get("regularMarketDayHigh")
    low = meta.get("regularMarketDayLow")
    volume = meta.get("regularMarketVolume")
    high52 = meta.get("fiftyTwoWeekHigh")
    low52 = meta.get("fiftyTwoWeekLow")
    regular_dt = parse_unix(meta.get("regularMarketTime"))
    prev_close = meta.get("previousClose")
    # chartPreviousClose equals the close before the *requested range*; ignore it for 1y.
    if prev_close is None and len(daily) >= 2:
        last_date = daily[-1]["date"]
        session_date = regular_dt.astimezone(exchange_tz).date().isoformat() if regular_dt else None
        if session_date and last_date >= session_date:
            prev_close = daily[-2]["close"]
            open_px = daily[-1].get("open")
            high = daily[-1].get("high") if high is None else high
            low = daily[-1].get("low") if low is None else low
            volume = daily[-1].get("volume") if volume is None else volume
        else:
            prev_close = daily[-1]["close"]
            open_px = None
    else:
        open_px = daily[-1].get("open") if daily else None
        # If last daily bar is the regular session, prefer its OHLC when meta is missing.
        if daily and regular_dt:
            if daily[-1]["date"] == regular_dt.astimezone(exchange_tz).date().isoformat():
                open_px = daily[-1].get("open") if open_px is None else open_px

    if last_regular is None and daily:
        last_regular = daily[-1]["close"]

    fullday = meta.get("fulldayPrice")
    fullday_pct = meta.get("fulldayChangePercent")
    pre_price = pre_pct = post_price = post_pct = None
    if spec["tab"] in {"us_etf", "us_stock", "gold"} and spec["code"] != "XAUUSD":
        if us_now == "pre" and fullday is not None:
            pre_price = float(fullday)
            if last_regular:
                pre_pct = (pre_price / float(last_regular) - 1.0) * 100.0
            elif fullday_pct is not None:
                pre_pct = float(fullday_pct)
        elif us_now == "post" and fullday is not None:
            post_price = float(fullday)
            if last_regular:
                post_pct = (post_price / float(last_regular) - 1.0) * 100.0
            elif fullday_pct is not None:
                post_pct = float(fullday_pct)

    last = float(last_regular) if last_regular is not None else None
    quote_dt = regular_dt
    note_extra = None

    if is_xau:
        if gold_spot:
            last = float(gold_spot["price"])
            quote_dt = gold_spot.get("time") or regular_dt
        elif last is None:
            return empty_quote(spec, "error", "現貨及期貨公開報價均未能取得")
        # Include the observed spot in the displayed session range; do not invent other values.
        if last is not None:
            if high is not None:
                high = max(float(high), last)
            else:
                high = last
            if low is not None:
                low = min(float(low), last)
            else:
                low = last
            if high52 is not None:
                high52 = max(float(high52), last)
            if low52 is not None:
                low52 = min(float(low52), last)
        note_extra = "spot"

    if last is None:
        return empty_quote(spec, "error", "沒有最新價")

    prev = float(prev_close) if prev_close is not None else None
    change = (last - prev) if prev not in (None, 0) else None
    change_pct = ((last / prev) - 1.0) * 100.0 if prev not in (None, 0) else None

    if high52 not in (None, 0) and last is not None:
        dist_high = (last / float(high52) - 1.0) * 100.0
    else:
        dist_high = None
    if high52 not in (None, 0) and low52 is not None and float(high52) != float(low52):
        pos52 = (last - float(low52)) / (float(high52) - float(low52)) * 100.0
        pos52 = max(0.0, min(100.0, pos52))
    else:
        pos52 = None

    hist_d = [{"date": b["date"], "close": round_px(b["close"], spec["unit"], last)} for b in daily[-60:]]
    weekly = weekly_from_daily(daily)
    hist_w = [{"date": b["date"], "close": round_px(b["close"], spec["unit"], last)} for b in weekly[-26:]]

    row: dict[str, Any] = {
        "code": spec["code"],
        "yahoo": spec["yahoo"],
        "name": spec["name"],
        "unit": spec["unit"],
        "tab": spec["tab"],
        "status": "ok",
        "error": None,
        "last": round_px(last, spec["unit"]),
        "change": round_px(change, spec["unit"]) if change is not None else None,
        "changePct": round(change_pct, 4) if change_pct is not None else None,
        "open": round_px(float(open_px) if open_px is not None else None, spec["unit"], last),
        "high": round_px(float(high) if high is not None else None, spec["unit"], last),
        "low": round_px(float(low) if low is not None else None, spec["unit"], last),
        "volume": int(volume) if isinstance(volume, (int, float)) and volume is not None else None,
        "prevClose": round_px(prev, spec["unit"], last),
        "high52": round_px(float(high52) if high52 is not None else None, spec["unit"], last),
        "low52": round_px(float(low52) if low52 is not None else None, spec["unit"], last),
        "distHighPct": round(dist_high, 2) if dist_high is not None else None,
        "pos52Pct": round(pos52, 1) if pos52 is not None else None,
        "prePrice": round_px(float(pre_price) if pre_price is not None else None, spec["unit"], last),
        "preChangePct": round(pre_pct, 4) if pre_pct is not None else None,
        "postPrice": round_px(float(post_price) if post_price is not None else None, spec["unit"], last),
        "postChangePct": round(post_pct, 4) if post_pct is not None else None,
        "regularTimeHKT": fmt_hkt(regular_dt),
        "regularTimeUnix": int(regular_dt.timestamp()) if regular_dt else None,
        "quoteTimeHKT": fmt_hkt(quote_dt),
        "goldSpot": bool(note_extra),
    }
    row["levels"] = compute_levels(row["last"], row["low"], row["high"], daily, row["low52"], row["high52"], unit=row["unit"])
    outlook = outlook_for(row, daily, us_now, hk_now)
    row.update(outlook)
    row["historyDaily"] = hist_d
    row["historyWeekly"] = hist_w
    return row


def mark_stale(previous: dict[str, Any], error: str) -> dict[str, Any]:
    row = dict(previous)
    row["status"] = "stale"
    row["error"] = error
    return row


def apply_outlooks(quotes: list[dict[str, Any]], us_now: str, hk_now: str) -> None:
    # Outlook already computed per row in build_quote. Kept as a hook for future batch rules.
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh public market quotes")
    parser.add_argument("--out", required=True, help="Output quotes.json path")
    parser.add_argument("--prev", help="Previous quotes.json to carry stale rows forward")
    args = parser.parse_args()

    generated = now_hk()
    us_now = us_state(generated)
    hk_now = hk_state(generated)

    prev_map: dict[str, dict[str, Any]] = {}
    if args.prev:
        try:
            with open(args.prev, "r", encoding="utf-8") as fh:
                prev_doc = json.load(fh)
            for item in prev_doc.get("quotes") or []:
                if item.get("code") and item.get("status") in {"ok", "stale"} and item.get("last") is not None:
                    prev_map[item["code"]] = item
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Could not read previous snapshot: {exc}", file=sys.stderr)

    pulled_start = now_hk()
    gold_spot = fetch_gold_spot()
    gold_source_used = "Gold API（api.gold-api.com）公開指示中間價" if gold_spot else "Yahoo Finance COMEX 黃金期貨（GC=F）指示價（現貨來源未能取得）"

    results: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []

    def work(spec: dict[str, str]) -> tuple[str, dict[str, Any]]:
        return spec["code"], build_quote(spec, gold_spot, us_now, hk_now)

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(work, spec) for spec in SYMBOLS]
        for fut in as_completed(futures):
            try:
                code, row = fut.result()
            except Exception as exc:  # noqa: BLE001
                print(f"Worker failed: {exc}", file=sys.stderr)
                continue
            results[code] = row

    quotes: list[dict[str, Any]] = []
    for spec in SYMBOLS:
        row = results.get(spec["code"])
        if row is None:
            row = empty_quote(spec, "error", "內部錯誤，未有結果")
        if row["status"] == "error":
            prev = prev_map.get(spec["code"])
            if prev:
                row = mark_stale(prev, row.get("error") or "本輪未能更新，顯示上次成功報價")
                # Recompute outlook from stored last + stored history so commentary is not left stale.
                daily = [
                    {"date": p["date"], "close": p["close"], "high": p["close"], "low": p["close"]}
                    for p in (prev.get("historyDaily") or [])
                ]
                if row.get("last") is not None:
                    row["levels"] = compute_levels(
                        row["last"], row.get("low"), row.get("high"), daily, row.get("low52"), row.get("high52"),
                        unit=row.get("unit") or "USD",
                    )
                    row.update(outlook_for(row, daily, us_now, hk_now))
            errors.append({"code": spec["code"], "error": row.get("error") or "failed"})
        quotes.append(row)

    pulled_end = now_hk()

    us_regular_dt = None
    hk_regular_dt = None
    for q in quotes:
        if q["code"].startswith("US.") and q.get("regularTimeUnix"):
            dt = parse_unix(q["regularTimeUnix"])
            if dt and (us_regular_dt is None or dt > us_regular_dt):
                us_regular_dt = dt
        if q["code"].startswith("HK.") and q.get("regularTimeUnix"):
            dt = parse_unix(q["regularTimeUnix"])
            if dt and (hk_regular_dt is None or dt > hk_regular_dt):
                hk_regular_dt = dt

    xau = next((q for q in quotes if q["code"] == "XAUUSD"), None)
    xau_dt = None
    xau_price = xau.get("last") if xau else None
    if xau and xau.get("quoteTimeHKT"):
        try:
            xau_dt = datetime.strptime(xau["quoteTimeHKT"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=HK)
        except ValueError:
            xau_dt = gold_spot["time"] if gold_spot else None
    elif gold_spot:
        xau_dt = gold_spot["time"]

    sessions = build_session_labels(generated, us_regular_dt, hk_regular_dt, xau_dt, xau_price)

    failures = [e["code"] for e in errors]
    doc = {
        "schemaVersion": 1,
        "generatedAtHKT": fmt_hkt(generated),
        "sourcePulledAtHKT": fmt_hkt(pulled_end),
        "source": {
            "name": "Yahoo Finance、Gold API",
            "label": "Yahoo Finance 公開市場數據（非富途官方報價）",
            "stocks": "Yahoo Finance 公開圖表／報價",
            "goldSpot": gold_source_used,
            "goldHistory": "Yahoo Finance COMEX 黃金期貨（GC=F），用作 XAUUSD 日線高低、近一年區間及走勢參考",
            "pulledAtHKT": fmt_hkt(pulled_end),
            "pulledStartedAtHKT": fmt_hkt(pulled_start),
        },
        "sessions": sessions,
        "pollHintSeconds": 45,
        "quotes": quotes,
        "failures": failures,
    }

    out_path = args.out
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")

    ok = sum(1 for q in quotes if q["status"] == "ok")
    stale = sum(1 for q in quotes if q["status"] == "stale")
    bad = sum(1 for q in quotes if q["status"] == "error")
    print(f"Wrote {out_path}  ok={ok} stale={stale} error={bad} failures={failures}")
    print(f"Gold source: {gold_source_used}")
    if gold_spot:
        print(f"XAUUSD mid: {gold_spot['price']} at {fmt_hkt(gold_spot['time'])}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
