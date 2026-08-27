import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sector_allocation import compute_sector_allocation


def demo():
    snapshots = [
        {"symbol": "AAPL", "market_value": 3000},
        {"symbol": "MSFT", "market_value": 2000},
        {"symbol": "QQQ", "market_value": 1000},  # ETF, no sector on file
        {"symbol": "CASH", "market_value": 500},
    ]
    sector_by_symbol = {"AAPL": "Technology", "MSFT": "Technology", "QQQ": None}
    result = compute_sector_allocation(snapshots, sector_by_symbol)
    assert result["Technology"] == 5000
    assert result["其他"] == 1000
    assert result["現金"] == 500
    assert sum(result.values()) == 6500

    # a symbol with no cache entry at all (missing from the dict) falls
    # back to "其他" the same as an explicit None, rather than KeyError.
    result2 = compute_sector_allocation([{"symbol": "IONQ", "market_value": 100}], {})
    assert result2["其他"] == 100


if __name__ == "__main__":
    demo()
    print("OK")
