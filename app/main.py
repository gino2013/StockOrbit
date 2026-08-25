from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc

load_dotenv()

from app.advice import build_advice
from app.backtest import max_drawdown_details, run_backtest
from app.db import PositionSnapshot, SessionLocal, TargetAllocation, init_db
from app.firstrade_client import fetch_positions
from app.holdings_history import (
    notable_moves,
    parse_weights,
    portfolio_value_history,
    resample_for_display,
    weighted_return_series,
)
from app.market_moves import price_swings, recent_news

app = FastAPI(title="StockOrbit")
templates = Jinja2Templates(directory="app/templates")
init_db()


def _parse_weighted_basket(raw: str) -> tuple[dict[str, float] | None, str | None]:
    """Parse a "SYM:weight,SYM:weight" string, validating it sums to 100%.
    Returns (weights, None) or (None, error_message)."""
    try:
        weights = parse_weights(raw)
    except ValueError:
        return None, "格式錯誤，範例：QQQ:0.6,VOO:0.4 或單純 QQQ"
    if not weights:
        return None, None
    total = sum(weights.values())
    if abs(total - 1) > 0.01:
        return None, f"權重總和需為 100%，目前為 {total:.0%}"
    return weights, None


def _latest_snapshots(db) -> list[dict]:
    latest = db.query(PositionSnapshot.snapshot_at).order_by(desc(PositionSnapshot.snapshot_at)).first()
    if not latest:
        return []
    rows = db.query(PositionSnapshot).filter(PositionSnapshot.snapshot_at == latest[0]).all()
    return [
        {
            "symbol": r.symbol,
            "quantity": r.quantity,
            "market_value": r.market_value,
            "price": r.price,
            "cost_basis": r.cost_basis,
        }
        for r in rows
    ]


@app.get("/api/symbol-search")
def symbol_search(q: str = ""):
    q = q.strip()
    if len(q) < 2:
        return JSONResponse([])
    try:
        quotes = yf.Search(q, max_results=8).quotes
    except Exception:
        return JSONResponse([])
    seen = set()
    results = []
    for quote in quotes:
        symbol = quote.get("symbol")
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        results.append({"symbol": symbol, "name": quote.get("shortname") or quote.get("longname") or ""})
    return JSONResponse(results)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    db = SessionLocal()
    try:
        snapshots = _latest_snapshots(db)
        targets = {t.symbol: t.target_weight for t in db.query(TargetAllocation).all()}
    finally:
        db.close()
    advice = build_advice(snapshots, targets) if snapshots else None
    total_value = sum(s["market_value"] for s in snapshots)
    total_cost = sum(s["cost_basis"] for s in snapshots)
    total_gain = total_value - total_cost
    stats = {
        "total_value": total_value,
        "total_gain": total_gain,
        "total_gain_pct": (total_gain / total_cost) if total_cost else 0,
        "position_count": len(snapshots),
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"snapshots": snapshots, "advice": advice, "targets": targets, "stats": stats},
    )


@app.post("/api/refresh")
def refresh():
    try:
        positions = fetch_positions()
    except Exception as e:
        return HTMLResponse(f"<p>抓取失敗: {e}</p><p><a href='/'>返回</a></p>", status_code=400)

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for p in positions:
            db.add(PositionSnapshot(snapshot_at=now, **p))
        db.commit()
    finally:
        db.close()
    return RedirectResponse("/", status_code=303)


@app.get("/api/market-moves")
def market_moves():
    db = SessionLocal()
    try:
        snapshots = _latest_snapshots(db)
    finally:
        db.close()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    symbols = [s["symbol"] for s in snapshots]
    try:
        swings = price_swings(symbols)
        news = recent_news(symbols)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"swings": swings, "news": news})


@app.post("/api/targets")
def set_target(symbol: str = Form(...), target_weight: float = Form(...)):
    db = SessionLocal()
    try:
        existing = db.get(TargetAllocation, symbol.upper())
        if existing:
            existing.target_weight = target_weight
        else:
            db.add(TargetAllocation(symbol=symbol.upper(), target_weight=target_weight))
        db.commit()
    finally:
        db.close()
    return RedirectResponse("/", status_code=303)


@app.post("/api/targets/delete")
def delete_target(symbol: str = Form(...)):
    db = SessionLocal()
    try:
        existing = db.get(TargetAllocation, symbol.upper())
        if existing:
            db.delete(existing)
            db.commit()
    finally:
        db.close()
    return RedirectResponse("/", status_code=303)


@app.post("/api/holdings-history")
def holdings_history(
    start: str = Form(...),
    end: str = Form(...),
    granularity: str = Form("D"),
    compare: str = Form(""),
):
    db = SessionLocal()
    try:
        snapshots = _latest_snapshots(db)
    finally:
        db.close()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    holdings = {s["symbol"]: s["quantity"] for s in snapshots}

    try:
        portfolio_daily = portfolio_value_history(holdings, start, end)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    portfolio = resample_for_display(portfolio_daily, granularity)
    if portfolio.empty:
        return JSONResponse({"error": "查無資料，換個日期區間試試"}, status_code=400)
    # Notable-move dates only make sense pinned to real daily labels, so we
    # only surface them when the chart itself is showing daily granularity.
    moves = notable_moves(portfolio_daily) if granularity == "D" else []

    compare_weights, error = _parse_weighted_basket(compare)
    if error:
        return JSONResponse({"error": f"比較標的：{error}"}, status_code=400)
    if not compare_weights:
        return JSONResponse({
            "mode": "value",
            "dates": portfolio.index.strftime("%Y-%m-%d").tolist(),
            "portfolio_value": [round(v, 2) for v in portfolio.tolist()],
            "portfolio_return": portfolio.iloc[-1] / portfolio.iloc[0] - 1,
            "notable_moves": [
                {"date": m["date"].strftime("%Y-%m-%d"), "change": m["change"]} for m in moves
            ],
        })

    compare_label = " + ".join(f"{s} {w:.0%}" for s, w in compare_weights.items())
    try:
        compare_series = resample_for_display(
            weighted_return_series(compare_weights, start, end), granularity
        )
    except Exception as e:
        return JSONResponse({"error": f"比較標的查詢失敗: {e}"}, status_code=400)

    aligned = pd.DataFrame({"portfolio": portfolio, "compare": compare_series}).dropna()
    if aligned.empty:
        return JSONResponse({"error": "資料無法對齊，換個日期區間試試"}, status_code=400)

    periods_per_year = {"D": 252, "M": 12, "Q": 4, "A": 1}[granularity]
    portfolio_dd, _, _ = max_drawdown_details(aligned["portfolio"])
    compare_dd, _, _ = max_drawdown_details(aligned["compare"])
    portfolio_vol = aligned["portfolio"].pct_change().std() * periods_per_year**0.5
    compare_vol = aligned["compare"].pct_change().std() * periods_per_year**0.5

    return JSONResponse({
        "mode": "compare",
        "compare_label": compare_label,
        "dates": aligned.index.strftime("%Y-%m-%d").tolist(),
        "portfolio_pct": [(v / aligned["portfolio"].iloc[0] - 1) * 100 for v in aligned["portfolio"]],
        "compare_pct": [(v / aligned["compare"].iloc[0] - 1) * 100 for v in aligned["compare"]],
        "portfolio_return": aligned["portfolio"].iloc[-1] / aligned["portfolio"].iloc[0] - 1,
        "compare_return": aligned["compare"].iloc[-1] / aligned["compare"].iloc[0] - 1,
        "portfolio_max_drawdown": portfolio_dd,
        "compare_max_drawdown": compare_dd,
        "portfolio_volatility": None if pd.isna(portfolio_vol) else portfolio_vol,
        "compare_volatility": None if pd.isna(compare_vol) else compare_vol,
        "notable_moves": [
            {"date": m["date"].strftime("%Y-%m-%d"), "change": m["change"]}
            for m in moves
            if m["date"] in aligned.index
        ],
    })


@app.post("/api/backtest")
def backtest(
    start: str = Form(...),
    end: str = Form(...),
    rebalance: str = Form("M"),
    benchmark: str = Form("SPY"),
):
    db = SessionLocal()
    try:
        targets = {t.symbol: t.target_weight for t in db.query(TargetAllocation).all()}
    finally:
        db.close()
    if not targets:
        return JSONResponse({"error": "尚未設定目標配置"}, status_code=400)
    total_weight = sum(targets.values())
    if abs(total_weight - 1) > 0.01:
        return JSONResponse(
            {"error": f"目標配置權重總和需為 100%，目前為 {total_weight:.0%}"}, status_code=400
        )

    benchmark_weights, error = _parse_weighted_basket(benchmark or "SPY")
    if error:
        return JSONResponse({"error": f"比較基準：{error}"}, status_code=400)
    benchmark_weights = benchmark_weights or {"SPY": 1.0}
    benchmark_label = " + ".join(f"{s} {w:.0%}" for s, w in benchmark_weights.items())

    try:
        result = run_backtest(targets, start, end, rebalance, benchmark_weights=benchmark_weights)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    result["benchmark_label"] = benchmark_label
    return JSONResponse(result)
