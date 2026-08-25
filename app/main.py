from datetime import datetime

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc

from app.advice import build_advice
from app.backtest import run_backtest
from app.db import PositionSnapshot, SessionLocal, TargetAllocation, init_db
from app.firstrade_client import fetch_positions

app = FastAPI(title="StockOrbit")
templates = Jinja2Templates(directory="app/templates")
init_db()


def _latest_snapshots(db) -> list[dict]:
    latest = db.query(PositionSnapshot.snapshot_at).order_by(desc(PositionSnapshot.snapshot_at)).first()
    if not latest:
        return []
    rows = db.query(PositionSnapshot).filter(PositionSnapshot.snapshot_at == latest[0]).all()
    return [
        {"symbol": r.symbol, "quantity": r.quantity, "market_value": r.market_value, "price": r.price}
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
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"snapshots": snapshots, "advice": advice, "targets": targets},
    )


@app.post("/api/refresh")
def refresh():
    try:
        positions = fetch_positions()
    except Exception as e:
        return HTMLResponse(f"<p>抓取失敗: {e}</p><p><a href='/'>返回</a></p>", status_code=400)

    db = SessionLocal()
    try:
        now = datetime.utcnow()
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
