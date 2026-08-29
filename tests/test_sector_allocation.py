import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.portfolio.sector_allocation import compute_sector_allocation, symbol_buckets


def demo():
    snapshots = [
        {"symbol": "AAPL", "market_value": 3000},
        {"symbol": "MSFT", "market_value": 2000},
        {"symbol": "QQQ", "market_value": 1000},  # confirmed ETF
        {"symbol": "WEIRD", "market_value": 400},  # no sector, not an ETF
        {"symbol": "CASH", "market_value": 500},
    ]
    info_by_symbol = {
        "AAPL": {"quoteType": "EQUITY", "sector": "Technology"},
        "MSFT": {"quoteType": "EQUITY", "sector": "Technology"},
        "QQQ": {"quoteType": "ETF", "sector": None},
    }
    result = compute_sector_allocation(snapshots, info_by_symbol)
    assert result["Technology"] == 5000
    assert result["ETF"] == 1000
    assert result["CASH"] == 500
    # unclassified symbol (missing from info_by_symbol entirely) gets its
    # own bucket named after itself, not lumped into a shared "other".
    assert result["WEIRD"] == 400
    assert sum(result.values()) == 6900

    buckets = symbol_buckets(snapshots, info_by_symbol)
    assert buckets == {
        "AAPL": "Technology",
        "MSFT": "Technology",
        "QQQ": "ETF",
        "WEIRD": "WEIRD",
        "CASH": "CASH",
    }


if __name__ == "__main__":
    demo()
    print("OK")
