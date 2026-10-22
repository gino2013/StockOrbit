"""千倍股評估編排（issue #408）：抓評估要用的數據、驗證後存檔。由
scripts/moonshot_eval.py 在 Claude Code session 裡呼叫（ADR 0002），
不走 HTTP。"""

import logging

from app.domain.screening.moonshot_eval import (
    build_evaluation,
    revenue_cagr_3y_pct,
    roic_pct,
    validate_judgment,
)
from app.infrastructure.fundamentals import FIELDS
from app.infrastructure.market_data import annual_statements, ticker_info

logger = logging.getLogger(__name__)


def _row(frame, name, col=0):
    if frame is None or frame.empty or name not in frame.index:
        return None
    values = frame.loc[name].dropna().tolist()
    return values[col] if len(values) > col else None


def gather_inputs(symbol: str) -> dict:
    """評估要給 LLM 看的全部數據。基本資料（名稱、市值）抓不到就丟
    ValueError - 沒數據的評估等於叫 LLM 憑記憶編（ADR 0001）；只是報表
    缺幾個欄位則照常回傳，對應的 key_metrics 是 None。"""
    symbol = symbol.strip().upper()
    try:
        info = ticker_info(symbol) or {}
    except Exception as e:
        raise ValueError(f"抓不到 {symbol} 的基本資料：{type(e).__name__}: {e}") from e
    name = info.get("longName") or info.get("shortName")
    if not name or info.get("marketCap") is None:
        raise ValueError(f"抓不到 {symbol} 的公司名稱或市值，代號可能不存在，不做評估")

    try:
        income, balance = annual_statements(symbol)
    except Exception as e:
        logger.warning("annual_statements(%s) failed: %s", symbol, e)
        income = balance = None
    revenues = income.loc["Total Revenue"].dropna().tolist() if income is not None and "Total Revenue" in income.index else []
    insiders = info.get("heldPercentInsiders")
    return {
        "symbol": symbol,
        "company_name": name,
        "business_summary": info.get("longBusinessSummary"),
        "fundamentals": {f: info.get(f) for f in FIELDS if f not in ("longName", "regularMarketTime")},
        "key_metrics": {
            "market_cap_usd": info.get("marketCap"),
            "roic_pct": roic_pct(
                _row(income, "Operating Income"), _row(income, "Tax Provision"), _row(income, "Pretax Income"),
                _row(balance, "Total Debt"), _row(balance, "Stockholders Equity"), _row(balance, "Cash And Cash Equivalents"),
            ),
            "revenue_growth_3y_pct": revenue_cagr_3y_pct(revenues),
            "insider_ownership_pct": round(insiders * 100, 2) if insiders is not None else None,
        },
    }


def save_evaluation(repo, inputs: dict, judgment: dict, model: str) -> dict:
    """驗證失敗丟 ValueError（訊息列出全部錯誤），不存任何東西。"""
    errors = validate_judgment(judgment)
    if errors:
        raise ValueError("判斷沒通過驗證：\n- " + "\n- ".join(errors))
    evaluation = build_evaluation(judgment, inputs)
    repo.add_moonshot_evaluation(inputs["symbol"], model, evaluation)
    return evaluation
