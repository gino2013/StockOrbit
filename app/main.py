from datetime import datetime, timezone

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc

load_dotenv()

from app.advice import build_advice
from app.backtest import run_backtest
from app.db import PositionSnapshot, SessionLocal, TargetAllocation, init_db
from app.firstrade_client import fetch_positions
from app.holdings_history import portfolio_value_history, resample_for_display

app = FastAPI(title="StockOrbit")
templates = Jinja2Templates(directory="app/templates")
init_db()


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
    compare_symbol: str = Form(""),
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
        portfolio = resample_for_display(portfolio_value_history(holdings, start, end), granularity)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if portfolio.empty:
        return JSONResponse({"error": "查無資料，換個日期區間試試"}, status_code=400)

    compare_symbol = compare_symbol.strip().upper()
    if not compare_symbol:
        return JSONResponse({
            "mode": "value",
            "dates": portfolio.index.strftime("%Y-%m-%d").tolist(),
            "portfolio_value": [round(v, 2) for v in portfolio.tolist()],
            "portfolio_return": portfolio.iloc[-1] / portfolio.iloc[0] - 1,
        })

    try:
        compare_series = resample_for_display(
            portfolio_value_history({compare_symbol: 1}, start, end), granularity
        )
    except Exception as e:
        return JSONResponse({"error": f"比較標的 {compare_symbol} 查詢失敗: {e}"}, status_code=400)

    aligned = pd.DataFrame({"portfolio": portfolio, "compare": compare_series}).dropna()
    if aligned.empty:
        return JSONResponse({"error": "資料無法對齊，換個日期區間試試"}, status_code=400)
    return JSONResponse({
        "mode": "compare",
        "compare_symbol": compare_symbol,
        "dates": aligned.index.strftime("%Y-%m-%d").tolist(),
        "portfolio_pct": [(v / aligned["portfolio"].iloc[0] - 1) * 100 for v in aligned["portfolio"]],
        "compare_pct": [(v / aligned["compare"].iloc[0] - 1) * 100 for v in aligned["compare"]],
        "portfolio_return": aligned["portfolio"].iloc[-1] / aligned["portfolio"].iloc[0] - 1,
        "compare_return": aligned["compare"].iloc[-1] / aligned["compare"].iloc[0] - 1,
    })


@app.post("/api/backtest")
def backtest(start: str = Form(...), end: str = Form(...), rebalance: str = Form("M")):
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
    try:
        result = run_backtest(targets, start, end, rebalance)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(result)
