from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc

load_dotenv()

from app.advice import build_advice
from app.backtest import max_drawdown_details, run_backtest, run_benchmarks_only
from app.db import ExchangeRateSnapshot, PositionSnapshot, SessionLocal, TargetAllocation, init_db
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


def _parse_multi_basket(raw: str) -> tuple[list[tuple[str, dict[str, float]]] | None, str | None]:
    """Parse one or more ";"-separated baskets (each "SYM:weight,..." or a
    bare symbol) for multi-line comparison. Returns (list of (label, weights))
    or (None, error_message)."""
    baskets = []
    for segment in raw.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        weights, error = _parse_weighted_basket(segment)
        if error:
            return None, f"「{segment}」{error}"
        if weights:
            label = " + ".join(f"{s} {w:.0%}" for s, w in weights.items())
            baskets.append((label, weights))
    return baskets, None


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


def _fetch_usd_twd_rate() -> float | None:
    try:
        history = yf.Ticker("USDTWD=X").history(period="5d")["Close"]
        return None if history.empty else float(history.iloc[-1])
    except Exception:
        return None


def _latest_usd_twd_rate(db) -> float | None:
    row = db.query(ExchangeRateSnapshot).filter(ExchangeRateSnapshot.pair == "USDTWD").order_by(
        desc(ExchangeRateSnapshot.fetched_at)
    ).first()
    return row.rate if row else None


def _latest_snapshot_at(db) -> datetime | None:
    row = db.query(PositionSnapshot.snapshot_at).order_by(desc(PositionSnapshot.snapshot_at)).first()
    return row[0] if row else None


# ponytail: refreshing on every page load would mean a full Firstrade login
# (password + TOTP) per visit — slow, and risks Firstrade flagging repeated
# logins. Only auto-refresh when the last snapshot is older than this.
AUTO_REFRESH_STALE_AFTER = timedelta(minutes=30)


def _refresh_and_save() -> None:
    """Log into Firstrade, fetch positions + USD/TWD rate, save a new snapshot.
    Raises on failure — callers decide whether that's fatal."""
    positions = fetch_positions()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for p in positions:
            db.add(PositionSnapshot(snapshot_at=now, **p))
        rate = _fetch_usd_twd_rate()
        if rate is not None:
            db.add(ExchangeRateSnapshot(pair="USDTWD", rate=rate, fetched_at=now))
        db.commit()
    finally:
        db.close()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    db = SessionLocal()
    try:
        last_snapshot_at = _latest_snapshot_at(db)
    finally:
        db.close()

    if last_snapshot_at is not None:
        stale = last_snapshot_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc) - AUTO_REFRESH_STALE_AFTER
        if stale:
            try:
                _refresh_and_save()
            except Exception:
                pass  # fall back to showing the stale snapshot rather than breaking the page

    db = SessionLocal()
    try:
        snapshots = _latest_snapshots(db)
        targets = {t.symbol: t.target_weight for t in db.query(TargetAllocation).all()}
        usd_twd_rate = _latest_usd_twd_rate(db) if snapshots else None
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
        "usd_twd_rate": usd_twd_rate,
        "total_value_twd": (total_value * usd_twd_rate) if usd_twd_rate else None,
        "total_gain_twd": (total_gain * usd_twd_rate) if usd_twd_rate else None,
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"snapshots": snapshots, "advice": advice, "targets": targets, "stats": stats},
    )


@app.post("/api/refresh")
def refresh():
    try:
        _refresh_and_save()
    except Exception as e:
        return HTMLResponse(f"<p>抓取失敗: {e}</p><p><a href='/'>返回</a></p>", status_code=400)
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
    # "CASH" is our synthetic cash-balance row, not a real ticker — but it
    # collides with an actual Nasdaq symbol (Pathward Financial), so leaving
    # it in would pull that unrelated company's price swings/news.
    symbols = [s["symbol"] for s in snapshots if s["symbol"] != "CASH"]
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
    exclude_portfolio: bool = Form(False),
):
    baskets, error = _parse_multi_basket(compare)
    if error:
        return JSONResponse({"error": f"比較標的：{error}"}, status_code=400)

    if exclude_portfolio:
        # Skip fetching the user's own holdings entirely — useful because
        # portfolio_value_history() requires every held symbol to have data
        # on every date, so one recently-listed holding (e.g. an ETF that
        # IPO'd in 2024) otherwise truncates how far back ANY comparison can
        # go, even when the comparison tickers themselves have longer history.
        if not baskets:
            return JSONResponse({"error": "已移除你的持股組合，至少要填一個比較標的才有東西可畫"}, status_code=400)
        compare_series_by_label = {}
        for label, weights in baskets:
            try:
                compare_series_by_label[label] = resample_for_display(
                    weighted_return_series(weights, start, end), granularity
                )
            except Exception as e:
                return JSONResponse({"error": f"比較標的「{label}」查詢失敗: {e}"}, status_code=400)
        aligned = pd.DataFrame(compare_series_by_label).dropna()
        if aligned.empty:
            return JSONResponse({"error": "資料無法對齊，換個日期區間試試"}, status_code=400)

        periods_per_year = {"D": 252, "M": 12, "Q": 4, "A": 1}[granularity]
        compare_stats = []
        compare_pct_series = {}
        for label, _ in baskets:
            series = aligned[label]
            dd, _, _ = max_drawdown_details(series)
            vol = series.pct_change().std() * periods_per_year**0.5
            compare_stats.append({
                "label": label,
                "return": series.iloc[-1] / series.iloc[0] - 1,
                "max_drawdown": dd,
                "volatility": None if pd.isna(vol) else vol,
            })
            compare_pct_series[label] = [(v / series.iloc[0] - 1) * 100 for v in series]

        return JSONResponse({
            "mode": "compare",
            "portfolio_excluded": True,
            "dates": aligned.index.strftime("%Y-%m-%d").tolist(),
            "compare_series": compare_pct_series,
            "compare_stats": compare_stats,
            "notable_moves": [],
        })

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

    if not baskets:
        return JSONResponse({
            "mode": "value",
            "dates": portfolio.index.strftime("%Y-%m-%d").tolist(),
            "portfolio_value": [round(v, 2) for v in portfolio.tolist()],
            "portfolio_return": portfolio.iloc[-1] / portfolio.iloc[0] - 1,
            "notable_moves": [
                {"date": m["date"].strftime("%Y-%m-%d"), "change": m["change"]} for m in moves
            ],
        })

    compare_series_by_label = {}
    for label, weights in baskets:
        try:
            compare_series_by_label[label] = resample_for_display(
                weighted_return_series(weights, start, end), granularity
            )
        except Exception as e:
            return JSONResponse({"error": f"比較標的「{label}」查詢失敗: {e}"}, status_code=400)

    aligned = pd.DataFrame({"portfolio": portfolio, **compare_series_by_label}).dropna()
    if aligned.empty:
        return JSONResponse({"error": "資料無法對齊，換個日期區間試試"}, status_code=400)

    periods_per_year = {"D": 252, "M": 12, "Q": 4, "A": 1}[granularity]
    portfolio_dd, _, _ = max_drawdown_details(aligned["portfolio"])
    portfolio_vol = aligned["portfolio"].pct_change().std() * periods_per_year**0.5

    compare_stats = []
    compare_pct_series = {}
    for label, _ in baskets:
        series = aligned[label]
        dd, _, _ = max_drawdown_details(series)
        vol = series.pct_change().std() * periods_per_year**0.5
        compare_stats.append({
            "label": label,
            "return": series.iloc[-1] / series.iloc[0] - 1,
            "max_drawdown": dd,
            "volatility": None if pd.isna(vol) else vol,
        })
        compare_pct_series[label] = [(v / series.iloc[0] - 1) * 100 for v in series]

    return JSONResponse({
        "mode": "compare",
        "dates": aligned.index.strftime("%Y-%m-%d").tolist(),
        "portfolio_pct": [(v / aligned["portfolio"].iloc[0] - 1) * 100 for v in aligned["portfolio"]],
        "compare_series": compare_pct_series,
        "portfolio_return": aligned["portfolio"].iloc[-1] / aligned["portfolio"].iloc[0] - 1,
        "portfolio_max_drawdown": portfolio_dd,
        "portfolio_volatility": None if pd.isna(portfolio_vol) else portfolio_vol,
        "compare_stats": compare_stats,
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
    exclude_portfolio: bool = Form(False),
):
    benchmarks, error = _parse_multi_basket(benchmark or "SPY")
    if error:
        return JSONResponse({"error": f"比較基準：{error}"}, status_code=400)
    benchmarks = benchmarks or [("SPY 100%", {"SPY": 1.0})]

    if exclude_portfolio:
        try:
            result = run_benchmarks_only(benchmarks, start, end)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return JSONResponse(result)

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
        result = run_backtest(targets, start, end, rebalance, benchmarks=benchmarks)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(result)
