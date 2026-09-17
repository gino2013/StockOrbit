"""Tax-lot comparison use case: given a symbol and a hypothetical sell
quantity, compare FIFO vs HIFO lot selection at today's live price. Pure
orchestration."""

from app.domain.analytics.stock_detail import today_ohlc
from app.domain.income.realized_gains import open_lots_by_symbol
from app.domain.income.tax_lot_comparison import compare_lot_selection


def tax_lot_report(transactions: list[dict], symbol: str, quantity: float) -> dict:
    lots = open_lots_by_symbol(transactions).get(symbol, [])
    price = today_ohlc(symbol).get("price") if lots else None
    comparison = compare_lot_selection(lots, quantity, price) if price is not None else None
    return {
        "symbol": symbol,
        "price": price,
        "lots": [
            {"buy_date": lot["buy_date"].isoformat(), "quantity": lot["quantity"], "price": lot["price"]}
            for lot in lots
        ],
        "comparison": comparison,
    }
