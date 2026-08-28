from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc

load_dotenv()

from app.advice import build_advice, build_rebalance_plan
from app.allocation_history import allocation_history, chart_series
from app.backtest import max_drawdown_details, run_backtest, run_benchmarks_only
from app.cash_deployment import suggest_cash_deployment
from app.compound_curve import build_compound_curve, fetch_annual_returns
from app.db import (
    ExchangeRateSnapshot,
    FundamentalsCache,
    PositionNote,
    PositionSnapshot,
    SessionLocal,
    TargetAllocation,
    Transaction,
    init_db,
)
from app.dividends import trailing_twelve_month_dividends, with_yield
from app.export import build_holdings_csv
from app.firstrade_client import _login, fetch_positions, fetch_transactions
from app.fundamentals import fetch_fundamentals
from app.fundamentals_cache import load_fundamentals
from app.holdings_history import (
    notable_moves,
    parse_weights,
    portfolio_value_history,
    resample_for_display,
    weighted_return_series,
)
from app.market_moves import price_swings, recent_news
from app.overseas_income import (
    dividend_income_for_year,
    estimate_overseas_income,
    realized_gains_for_year,
)
from app.realized_gains import compute_realized_gains, summarize_realized_gains
from app.risk import compute_risk_metrics
from app.sector_allocation import compute_sector_allocation, symbol_buckets
from app.trending import SCREENERS, trending_tickers
from app.xirr import portfolio_cashflows, xirr

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


def _average_usdtwd_rate(year: int) -> float | None:
    try:
        end = min(datetime.now(), datetime(year, 12, 31)).strftime("%Y-%m-%d")
        history = yf.download(
            "USDTWD=X", start=f"{year}-01-01", end=end, auto_adjust=True, progress=False
        )["Close"]
        return None if history.empty else float(history.mean().iloc[0])
    except Exception:
        return None


def _all_transactions(db) -> list[dict]:
    return [
        {
            "symbol": t.symbol,
            "trans_type": t.trans_type,
            "report_date": t.report_date,
            "quantity": t.quantity,
            "trade_price": t.trade_price,
            "amount": t.amount,
        }
        for t in db.query(Transaction).all()
    ]


def _latest_snapshot_at(db) -> datetime | None:
    row = db.query(PositionSnapshot.snapshot_at).order_by(desc(PositionSnapshot.snapshot_at)).first()
    return row[0] if row else None


# ponytail: refreshing on every page load would mean a full Firstrade login
# (password + TOTP) per visit — slow, and risks Firstrade flagging repeated
# logins. Only auto-refresh when the last snapshot is older than this.
AUTO_REFRESH_STALE_AFTER = timedelta(minutes=30)

# ponytail: hidden easter-egg toggle (see the invisible button next to the
# "StockOrbit" header) — a purely cosmetic display multiplier, never written
# to the database, so toggling it can never corrupt real holdings data.
FLEX_MODE_COOKIE = "flex_mode"
FLEX_MODE_MULTIPLIER = 10.1


def _apply_flex_mode(snapshots: list[dict]) -> list[dict]:
    # round() to avoid float artifacts (e.g. 23.85817 * 10.1 == 240.967517000000002)
    # showing up raw in the un-formatted {{ s.quantity }} template cell.
    return [
        {
            **s,
            "quantity": round(s["quantity"] * FLEX_MODE_MULTIPLIER, 6),
            "cost_basis": round(s["cost_basis"] * FLEX_MODE_MULTIPLIER, 2),
            "market_value": round(s["market_value"] * FLEX_MODE_MULTIPLIER, 2),
        }
        for s in snapshots
    ]


def _refresh_and_save() -> None:
    """Log into Firstrade, fetch positions + transactions + USD/TWD rate, save
    a new snapshot. Raises on failure — callers decide whether that's fatal."""
    session = _login()
    positions = fetch_positions(session)
    transactions = fetch_transactions(session)
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for p in positions:
            db.add(PositionSnapshot(snapshot_at=now, **p))
        for t in transactions:
            tid = Transaction.make_id(t)
            if db.get(Transaction, tid) is None:
                db.add(Transaction(id=tid, fetched_at=now, **t))
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
        transactions = _all_transactions(db)
        fundamentals_info_by_symbol = {
            row.symbol: {"quoteType": row.quoteType, "sector": row.sector}
            for row in db.query(FundamentalsCache).all()
        }
        snapshot_rows = [
            {"snapshot_at": r.snapshot_at, "symbol": r.symbol, "market_value": r.market_value}
            for r in db.query(PositionSnapshot).all()
        ]
        notes_by_symbol = dict(db.query(PositionNote.symbol, PositionNote.note).all())
    finally:
        db.close()
    sector_allocation = compute_sector_allocation(snapshots, fundamentals_info_by_symbol) if snapshots else {}
    symbol_sector_buckets = symbol_buckets(snapshots, fundamentals_info_by_symbol) if snapshots else {}
    allocation_chart_data = chart_series(allocation_history(snapshot_rows)) if snapshot_rows else None
    realized = compute_realized_gains(transactions)
    realized_summary = {
        "all_time": summarize_realized_gains(realized),
        "this_year": summarize_realized_gains(realized, year=datetime.now().year),
    }
    # XIRR needs the *real* total value as its terminal cashflow — real
    # deposit history compared against a flex-mode-inflated ending value
    # would look like a 10.1x gain that never happened, blowing up the rate
    # into nonsense (seen: 20078% instead of the real ~45%). Capture it
    # before flex mode scales snapshots, same way total_gain_pct already
    # stays correct under flex mode because both its inputs scale together.
    real_total_value = sum(s["market_value"] for s in snapshots)
    if request.cookies.get(FLEX_MODE_COOKIE) == "1":
        snapshots = _apply_flex_mode(snapshots)
    advice = build_advice(snapshots, targets, sector_allocation=sector_allocation) if snapshots else None
    rebalance_plan = build_rebalance_plan(snapshots, targets) if snapshots and targets else None
    # Targets are edited one symbol at a time, so nothing stops the stored
    # set from drifting away from summing to 100% (e.g. adding a 6th target
    # without re-trimming the other five). When that happens, each row's
    # dollar figure is still individually correct, but total buys won't
    # equal total sells — the plan silently implies a deposit/withdrawal.
    target_weight_sum = sum(targets.values()) if targets else 0
    total_value = sum(s["market_value"] for s in snapshots)
    total_cost = sum(s["cost_basis"] for s in snapshots)
    total_gain = total_value - total_cost
    cashflows = portfolio_cashflows(transactions, real_total_value, datetime.now().date())
    annualized_return = xirr(cashflows)
    market_value_by_symbol = {s["symbol"]: s["market_value"] for s in snapshots}
    ttm_dividends = trailing_twelve_month_dividends(transactions, datetime.now().date())
    dividend_rows = with_yield(ttm_dividends, market_value_by_symbol)
    total_ttm_dividends = sum(r["ttm_dividends"] for r in dividend_rows)
    stats = {
        "total_value": total_value,
        "total_gain": total_gain,
        "total_gain_pct": (total_gain / total_cost) if total_cost else 0,
        "annualized_return": annualized_return,
        "position_count": len(snapshots),
        "usd_twd_rate": usd_twd_rate,
        "total_value_twd": (total_value * usd_twd_rate) if usd_twd_rate else None,
        "total_gain_twd": (total_gain * usd_twd_rate) if usd_twd_rate else None,
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "snapshots": snapshots,
            "advice": advice,
            "targets": targets,
            "stats": stats,
            "rebalance_plan": rebalance_plan,
            "target_weight_sum": target_weight_sum,
            "realized_summary": realized_summary,
            "realized_trades": sorted(realized, key=lambda r: r["report_date"], reverse=True),
            "dividend_rows": dividend_rows,
            "sector_allocation": sector_allocation,
            "symbol_sector_buckets": symbol_sector_buckets,
            "allocation_chart_data": allocation_chart_data,
            "notes_by_symbol": notes_by_symbol,
            "total_ttm_dividends": total_ttm_dividends,
        },
    )


@app.post("/api/refresh")
def refresh():
    try:
        _refresh_and_save()
    except Exception as e:
        return HTMLResponse(f"<p>抓取失敗: {e}</p><p><a href='/'>返回</a></p>", status_code=400)
    return RedirectResponse("/", status_code=303)


@app.post("/api/toggle-flex-mode")
def toggle_flex_mode(request: Request):
    response = RedirectResponse("/", status_code=303)
    if request.cookies.get(FLEX_MODE_COOKIE) == "1":
        response.delete_cookie(FLEX_MODE_COOKIE)
    else:
        response.set_cookie(FLEX_MODE_COOKIE, "1", max_age=60 * 60 * 24 * 365)
    return response


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


@app.get("/api/fundamentals")
def fundamentals(debug: bool = False):
    db = SessionLocal()
    try:
        snapshots = _latest_snapshots(db)
        if not snapshots:
            return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
        symbols = [s["symbol"] for s in snapshots if s["symbol"] != "CASH"]
        try:
            data = fetch_fundamentals(symbols, debug=debug)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        # Render can't reach Yahoo's quoteSummary API (issue #9) — fall back to
        # the last cache a GitHub Actions job (unaffected by that block) wrote.
        stale_symbols = [s for s in symbols if not data.get(s, {}).get("_fetch_ok")]
        if stale_symbols:
            cached = load_fundamentals(db, stale_symbols)
            for symbol, cached_fields in cached.items():
                fetched_at = cached_fields.pop("fetched_at", None)
                data[symbol] = {**data[symbol], **cached_fields, "_cached_at": fetched_at}
    finally:
        db.close()
    return JSONResponse({"fundamentals": data})


@app.get("/api/risk")
def risk():
    db = SessionLocal()
    try:
        snapshots = _latest_snapshots(db)
        if not snapshots:
            return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
        symbols = [s["symbol"] for s in snapshots if s["symbol"] != "CASH"]
        try:
            items = compute_risk_metrics(symbols)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        # Render can't reach Yahoo's calendar API (issue #9) — fall back to the
        # last cache a GitHub Actions job (unaffected by that block) wrote.
        stale_symbols = [item["symbol"] for item in items if not item.pop("earnings_fetch_ok")]
        if stale_symbols:
            cached = load_fundamentals(db, stale_symbols)
            by_symbol = {item["symbol"]: item for item in items}
            for symbol, cached_fields in cached.items():
                next_earnings = cached_fields.get("next_earnings_date")
                if next_earnings:
                    days = (date.fromisoformat(next_earnings) - datetime.now().date()).days
                    by_symbol[symbol]["next_earnings_date"] = next_earnings
                    by_symbol[symbol]["earnings_soon"] = 0 <= days <= 14
                    by_symbol[symbol]["_cached_at"] = cached_fields.get("fetched_at")
    finally:
        db.close()
    return JSONResponse({"items": items})


@app.get("/api/overseas-income")
def overseas_income(year: int | None = None):
    year = year or datetime.now().year
    db = SessionLocal()
    try:
        transactions = _all_transactions(db)
    finally:
        db.close()
    realized = compute_realized_gains(transactions)
    capital_gains = realized_gains_for_year(realized, year)
    dividends = dividend_income_for_year(transactions, year)
    rate = _average_usdtwd_rate(year)
    result = estimate_overseas_income(capital_gains, dividends, rate)
    result["year"] = year
    return JSONResponse(result)


@app.get("/api/trending")
def trending(screener: str = "day_gainers"):
    if screener not in SCREENERS:
        return JSONResponse({"error": "未知的篩選器"}, status_code=400)
    try:
        items = trending_tickers(screener)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"items": items})


@app.get("/api/compound-curve")
def compound_curve(symbol: str, start_year: int, end_year: int, future_years: int = 5):
    if end_year < start_year:
        return JSONResponse({"error": "結束年份不能早於起始年份"}, status_code=400)
    if end_year - start_year > 40:
        return JSONResponse({"error": "區間太長，請縮小到 40 年以內"}, status_code=400)
    try:
        returns = fetch_annual_returns(symbol.upper(), start_year, end_year)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not returns:
        return JSONResponse({"error": f"抓不到 {symbol.upper()} 這段期間的歷史股價"}, status_code=400)
    result = build_compound_curve(returns, future_periods=future_years)
    result["symbol"] = symbol.upper()
    result["start_year"] = start_year
    result["end_year"] = end_year
    result["annual_returns"] = returns
    return JSONResponse(result)


@app.get("/api/export/csv")
def export_csv():
    db = SessionLocal()
    try:
        snapshots = _latest_snapshots(db)
        targets = {t.symbol: t.target_weight for t in db.query(TargetAllocation).all()}
    finally:
        db.close()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    advice = build_advice(snapshots, targets)
    csv_text = build_holdings_csv(
        snapshots, advice["allocation"], targets, advice["advice"], as_of=datetime.now().date()
    )
    filename = f"stockorbit_{datetime.now().date().isoformat()}.csv"
    return Response(
        content="﻿" + csv_text,  # BOM so Excel opens the UTF-8 file with correct Chinese text
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/cash-deployment")
def cash_deployment(amount: float):
    db = SessionLocal()
    try:
        snapshots = _latest_snapshots(db)
        targets = {t.symbol: t.target_weight for t in db.query(TargetAllocation).all()}
    finally:
        db.close()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    if not targets:
        return JSONResponse({"error": "還沒有設定目標配置，請先在「目標配置」設定"}, status_code=400)
    plan = suggest_cash_deployment(snapshots, targets, amount)
    return JSONResponse({"plan": plan})


@app.post("/api/notes")
def set_note(symbol: str = Form(...), note: str = Form("")):
    db = SessionLocal()
    try:
        existing = db.get(PositionNote, symbol.upper())
        if existing:
            existing.note = note
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(PositionNote(symbol=symbol.upper(), note=note))
        db.commit()
    finally:
        db.close()
    return RedirectResponse("/#section-notes", status_code=303)


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
