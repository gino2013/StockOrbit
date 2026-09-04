"""Scrape LINE Bank's board-rate page for today's USD spot buy/sell.

Their site is a Next.js app, but the rate table is embedded server-side as
a CMS HTML blob inside the page's inline data - so a plain GET is enough,
no JS execution. This is *today's* quote only; LINE Bank publishes no
history, so the fx-history chart's line comes from yfinance instead and
this is just a "current" readout on top.
"""

import html as _html
import json
import re
import urllib.request

_URL = "https://www.linebank.com.tw/board-rate/exchange-rate"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122 Safari/537.36"


def _cms_html(page: str) -> str | None:
    """The `cmsHtmlContent` JSON-string value for the exchange-rate block."""
    i = page.find('"infoId":"exchange-rate"')
    if i == -1:
        return None
    key = '"cmsHtmlContent":"'
    j = page.find(key, i)
    if j == -1:
        return None
    j += len(key)
    buf, k = [], j
    while k < len(page):
        c = page[k]
        if c == "\\":
            buf.append(page[k:k + 2])
            k += 2
            continue
        if c == '"':
            break
        buf.append(c)
        k += 1
    try:
        return json.loads('"' + "".join(buf) + '"')
    except json.JSONDecodeError:
        return None


def fetch_usd_spot() -> dict | None:
    """{"buy": float, "sell": float, "as_of": "2026年09月04日 18:04:01"} or
    None on any fetch/parse failure - the caller shows the chart without the
    live readout in that case."""
    try:
        req = urllib.request.Request(_URL, headers={"User-Agent": _UA})
        page = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
    except Exception:
        return None

    cms = _cms_html(page)
    if not cms:
        return None

    plain = _html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cms)))
    # 即期 table row: "美金 (USD)  <買進>  <賣出>"
    m = re.search(r"(?:美金|USD)[^0-9]*([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)", plain)
    if not m:
        return None
    tm = re.search(r"資料時間：([0-9]{4}年[0-9]{2}月[0-9]{2}日[ 0-9:]*)", plain)
    return {
        "buy": float(m.group(1)),
        "sell": float(m.group(2)),
        "as_of": tm.group(1).strip() if tm else None,
    }
