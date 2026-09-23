import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.domain.analytics.style_box import classify_style_box


def demo():
    snapshots = [
        {"symbol": "AAPL", "market_value": 4000.0},
        {"symbol": "BRK-B", "market_value": 3000.0},
        {"symbol": "VOO", "market_value": 2000.0},
        {"symbol": "CASH", "market_value": 500.0},
        {"symbol": "XYZ", "market_value": 1000.0},
    ]
    fundamentals = {
        "AAPL": {"quoteType": "EQUITY", "marketCap": 3_000_000_000_000, "trailingPE": 30},
        "BRK-B": {"quoteType": "EQUITY", "marketCap": 900_000_000_000, "trailingPE": 10},
        "VOO": {"quoteType": "ETF", "totalAssets": 500_000_000_000},
        "XYZ": {"quoteType": "EQUITY"},  # no PE/PB/marketCap at all
    }
    result = classify_style_box(snapshots, fundamentals)

    by_cell = {(g["size"], g["style"]): g["weight"] for g in result["grid"]}
    total = 4000 + 3000 + 2000 + 1000  # CASH excluded from the denominator
    assert len(result["grid"]) == 9
    assert abs(by_cell[("Large", "Growth")] - 4000 / total) < 1e-9, "AAPL: mega-cap, PE 30 -> Large/Growth"
    assert abs(by_cell[("Large", "Value")] - 3000 / total) < 1e-9, "BRK-B: mega-cap, PE 10 -> Large/Value"
    assert result["classified_weight"] == by_cell[("Large", "Growth")] + by_cell[("Large", "Value")]

    unclassified_by_symbol = {u["symbol"]: u["reason"] for u in result["unclassified"]}
    assert unclassified_by_symbol["VOO"] == "ETF"
    assert unclassified_by_symbol["XYZ"] == "缺資料"
    assert "CASH" not in unclassified_by_symbol and "CASH" not in {i["symbol"] for i in result["items"]}

    # negative PE (company lost money) must fall back to priceToBook, not be
    # treated as a super-cheap "Value" stock just because the number is < 15.
    fallback = classify_style_box(
        [{"symbol": "LOSS", "market_value": 1000.0}],
        {"LOSS": {"quoteType": "EQUITY", "marketCap": 5_000_000_000, "trailingPE": -8, "priceToBook": 5}},
    )
    assert fallback["items"][0]["style"] == "Growth"  # PB 5 > 4 -> Growth

    assert classify_style_box([], {}) == {"grid": [], "items": [], "unclassified": [], "classified_weight": 0.0}


if __name__ == "__main__":
    demo()
    print("OK")
