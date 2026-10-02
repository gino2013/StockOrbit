"""Scheduled cache refresh - see .github/workflows/refresh-moonshot-market-screen.yml.

Same Render-can't-reach-Yahoo limitation as refresh_fundamentals_cache.py
(issue #9), but for the 全市場搜尋 screen (issue #356): yfinance's
EquityQuery screener goes through the same crumb-authenticated session as
quoteSummary, so it's blocked on Render too, not just per-symbol
fundamentals. Runs here on a schedule (GitHub Actions runners aren't
blocked) and wholesale-replaces the cached candidate list - today's
non-candidates shouldn't linger just because they qualified 6 hours ago.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.application.moonshot import score_symbols
from app.domain.screening.moonshot import market_screen_symbols
from app.infrastructure.db import init_db
from app.infrastructure.repositories import Repositories


def main():
    init_db()
    symbol_list = market_screen_symbols(limit=30)
    if not symbol_list:
        print("No candidates found, leaving old cache untouched.")
        return
    with Repositories() as repo:
        results = score_symbols(repo, symbol_list)
        repo.replace_moonshot_market_screen_cache(results)
    print(f"Cached {len(results)} candidates: {', '.join(r['symbol'] for r in results)}")


if __name__ == "__main__":
    main()
