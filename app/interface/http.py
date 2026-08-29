from datetime import date, datetime, timedelta, timezone

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

load_dotenv()

from app.application.dashboard import build_dashboard_context
from app.application.goals import goal_progress
from app.application.tax import overseas_income_report, tax_loss_report
from app.infrastructure.repositories import Repositories
from app.infrastructure.db import init_db
from app.infrastructure.export import build_holdings_csv, build_transactions_csv
from app.infrastructure.firstrade_client import _login, fetch_positions, fetch_transactions
from app.infrastructure.fundamentals import fetch_fundamentals
from app.domain.portfolio.advice import build_advice
from app.domain.portfolio.cash_deployment import suggest_cash_deployment
from app.domain.analytics.backtest import max_drawdown_details, run_backtest, run_benchmarks_only
from app.domain.analytics.compound_curve import build_compound_curve, build_portfolio_compound_curve, fetch_annual_returns
from app.domain.analytics.compounder_checklist import build_compounder_checklist
from app.domain.analytics.correlation import compute_correlation_matrix
from app.domain.analytics.dca import run_dca_comparison
from app.domain.analytics.drip import simulate_drip
from app.domain.analytics.health_dashboard import build_health_overview
from app.domain.analytics.holdings_history import (
    notable_moves,
    parse_weights,
    portfolio_value_history,
    resample_for_display,
    weighted_return_series,
)
from app.domain.analytics.market_moves import price_swings, recent_news
from app.domain.analytics.performance_report import build_performance_report
from app.domain.income.realized_gains import compute_realized_gains
from app.domain.analytics.risk import compute_risk_metrics
from app.domain.analytics.risk_parity import suggest_risk_parity
from app.domain.analytics.scenario import simulate_market_drop
from app.domain.analytics.technical_indicators import compute_technical_indicators
from app.domain.analytics.trending import SCREENERS, trending_tickers

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


def _average_usdtwd_rate(year: int) -> float | None:
    try:
        end = min(datetime.now(), datetime(year, 12, 31)).strftime("%Y-%m-%d")
        history = yf.download(
            "USDTWD=X", start=f"{year}-01-01", end=end, auto_adjust=True, progress=False
        )["Close"]
        return None if history.empty else float(history.mean().iloc[0])
    except Exception:
        return None


# ponytail: refreshing on every page load would mean a full Firstrade login
# (password + TOTP) per visit - slow, and risks Firstrade flagging repeated
# logins. Only auto-refresh when the last snapshot is older than this.
AUTO_REFRESH_STALE_AFTER = timedelta(minutes=30)

# ponytail: hidden easter-egg toggle (see the invisible button next to the
# "StockOrbit" header) - a purely cosmetic display multiplier, never written
# to the database. The scaling itself lives in app.application.dashboard.
FLEX_MODE_COOKIE = "flex_mode"


def _refresh_and_save() -> None:
    """Log into Firstrade, fetch positions + transactions + USD/TWD rate, save
    a new snapshot. Raises on failure - callers decide whether that's fatal."""
    session = _login()
    positions = fetch_positions(session)
    transactions = fetch_transactions(session)
    with Repositories() as repo:
        repo.save_refresh(positions, transactions, _fetch_usd_twd_rate())


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    with Repositories() as repo:
        last_snapshot_at = repo.latest_snapshot_at()

    if last_snapshot_at is not None:
        stale = last_snapshot_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc) - AUTO_REFRESH_STALE_AFTER
        if stale:
            try:
                _refresh_and_save()
            except Exception:
                pass  # fall back to showing the stale snapshot rather than breaking the page

    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
        context = build_dashboard_context(
            snapshots=snapshots,
            targets=repo.targets(),
            transactions=repo.all_transactions(),
            fundamentals_meta=repo.fundamentals_meta(),
            snapshot_points=repo.all_snapshot_points(),
            notes=repo.notes(),
            usd_twd_rate=repo.usd_twd_rate() if snapshots else None,
            flex_mode=request.cookies.get(FLEX_MODE_COOKIE) == "1",
            as_of=datetime.now().date(),
        )
    return templates.TemplateResponse(request, "dashboard.html", context)


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
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    # "CASH" is our synthetic cash-balance row, not a real ticker - but it
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
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
        if not snapshots:
            return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
        symbols = [s["symbol"] for s in snapshots if s["symbol"] != "CASH"]
        try:
            data = fetch_fundamentals(symbols, debug=debug)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        # Render can't reach Yahoo's quoteSummary API (issue #9) - fall back to
        # the last cache a GitHub Actions job (unaffected by that block) wrote.
        stale_symbols = [s for s in symbols if not data.get(s, {}).get("_fetch_ok")]
        if stale_symbols:
            cached = repo.fundamentals_cache(stale_symbols)
            for symbol, cached_fields in cached.items():
                fetched_at = cached_fields.pop("fetched_at", None)
                data[symbol] = {**data[symbol], **cached_fields, "_cached_at": fetched_at}
    return JSONResponse({"fundamentals": data})


@app.get("/api/health-overview")
def health_overview():
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    try:
        result = build_health_overview(snapshots)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(result)


@app.get("/api/risk")
def risk():
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
        if not snapshots:
            return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
        symbols = [s["symbol"] for s in snapshots if s["symbol"] != "CASH"]
        try:
            items = compute_risk_metrics(symbols)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        # Render can't reach Yahoo's calendar API (issue #9) - fall back to the
        # last cache a GitHub Actions job (unaffected by that block) wrote.
        stale_symbols = [item["symbol"] for item in items if not item.pop("earnings_fetch_ok")]
        if stale_symbols:
            cached = repo.fundamentals_cache(stale_symbols)
            by_symbol = {item["symbol"]: item for item in items}
            for symbol, cached_fields in cached.items():
                next_earnings = cached_fields.get("next_earnings_date")
                if next_earnings:
                    days = (date.fromisoformat(next_earnings) - datetime.now().date()).days
                    by_symbol[symbol]["next_earnings_date"] = next_earnings
                    by_symbol[symbol]["earnings_soon"] = 0 <= days <= 14
                    by_symbol[symbol]["_cached_at"] = cached_fields.get("fetched_at")
    return JSONResponse({"items": items})


@app.get("/api/technical-indicators")
def technical_indicators():
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    symbols = [s["symbol"] for s in snapshots if s["symbol"] != "CASH"]
    try:
        items = compute_technical_indicators(symbols)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"items": items})


@app.get("/api/overseas-income")
def overseas_income(year: int | None = None):
    year = year or datetime.now().year
    with Repositories() as repo:
        transactions = repo.all_transactions()
    return JSONResponse(overseas_income_report(transactions, year, _average_usdtwd_rate(year)))


@app.get("/api/tax-loss-harvesting")
def tax_loss_harvesting(year: int | None = None):
    year = year or datetime.now().year
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
        transactions = repo.all_transactions()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    rate = _average_usdtwd_rate(year)
    if rate is None:
        return JSONResponse({"error": "無法取得今年的美元/台幣匯率資料"}, status_code=400)
    return JSONResponse(tax_loss_report(snapshots, transactions, year, rate))


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

    with Repositories() as repo:
        targets = repo.targets()
    if targets:
        try:
            portfolio = build_portfolio_compound_curve(targets, start_year, end_year, future_years)
        except Exception:
            portfolio = None  # best-effort: the symbol curve above is the main result
        result["portfolio"] = portfolio

    return JSONResponse(result)


@app.get("/api/compounder-checklist")
def compounder_checklist(symbol: str):
    symbol = symbol.upper()
    with Repositories() as repo:
        fundamentals = fetch_fundamentals([symbol]).get(symbol, {})
        if not fundamentals.get("_fetch_ok"):
            cached = repo.fundamentals_cache([symbol]).get(symbol)
            if cached:
                fundamentals = {**fundamentals, **cached}
    try:
        result = build_compounder_checklist(symbol, fundamentals)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(result)


@app.get("/api/correlation")
def correlation():
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    symbols = [s["symbol"] for s in snapshots if s["symbol"] != "CASH"]
    try:
        result = compute_correlation_matrix(symbols)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if len(result["symbols"]) < 2:
        return JSONResponse({"error": "持股數量不足，至少需要 2 檔才能算相關性"}, status_code=400)
    return JSONResponse(result)


@app.get("/api/risk-parity")
def risk_parity():
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    try:
        items = suggest_risk_parity(snapshots)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"items": items})


@app.get("/api/scenario")
def scenario(market_change: float):
    if market_change > 0:
        return JSONResponse({"error": "請輸入負值或 0（大盤跌幅）"}, status_code=400)
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    try:
        result = simulate_market_drop(snapshots, market_change)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(result)


@app.get("/api/export/csv")
def export_csv():
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
        targets = repo.targets()
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


@app.get("/api/export/transactions-csv")
def export_transactions_csv():
    with Repositories() as repo:
        transactions = repo.all_transactions()
    if not transactions:
        return JSONResponse({"error": "還沒有交易紀錄，請先按「重新抓取持股」"}, status_code=400)
    realized = compute_realized_gains(transactions)
    csv_text = build_transactions_csv(transactions, realized, as_of=datetime.now().date())
    filename = f"stockorbit_transactions_{datetime.now().date().isoformat()}.csv"
    return Response(
        content="﻿" + csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/cash-deployment")
def cash_deployment(amount: float):
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
        targets = repo.targets()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)
    if not targets:
        return JSONResponse({"error": "還沒有設定目標配置，請先在「目標配置」設定"}, status_code=400)
    plan = suggest_cash_deployment(snapshots, targets, amount)
    return JSONResponse({"plan": plan})


@app.post("/api/notes")
def set_note(symbol: str = Form(...), note: str = Form("")):
    with Repositories() as repo:
        repo.upsert_note(symbol, note)
    return RedirectResponse("/#section-notes", status_code=303)


@app.post("/api/targets")
def set_target(symbol: str = Form(...), target_weight: float = Form(...)):
    with Repositories() as repo:
        repo.upsert_target(symbol, target_weight)
    return RedirectResponse("/", status_code=303)


@app.post("/api/targets/delete")
def delete_target(symbol: str = Form(...)):
    with Repositories() as repo:
        repo.delete_target(symbol)
    return RedirectResponse("/", status_code=303)


@app.get("/api/goal")
def get_goal():
    with Repositories() as repo:
        goal = repo.goal()
        if not goal:
            return JSONResponse({"goal": None})
        progress = goal_progress(
            target_amount=goal.target_amount,
            target_date=goal.target_date,
            snapshots=repo.latest_snapshots(),
            transactions=repo.all_transactions(),
            as_of=datetime.now().date(),
        )
    return JSONResponse({"goal": progress})


@app.post("/api/goal")
def set_goal(target_amount: float = Form(...), target_date: str = Form(...)):
    if target_amount <= 0:
        return JSONResponse({"error": "目標金額需大於 0"}, status_code=400)
    try:
        target_date_parsed = date.fromisoformat(target_date)
    except ValueError:
        return JSONResponse({"error": "日期格式錯誤"}, status_code=400)
    with Repositories() as repo:
        repo.upsert_goal(target_amount, target_date_parsed)
    return JSONResponse({"ok": True})


@app.post("/api/goal/delete")
def delete_goal():
    with Repositories() as repo:
        repo.delete_goal()
    return JSONResponse({"ok": True})


@app.post("/api/performance-report")
def performance_report(
    start: str = Form(...),
    end: str = Form(...),
    benchmark: str = Form("SPY"),
):
    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
        transactions = repo.all_transactions()
    if not snapshots:
        return JSONResponse({"error": "還沒有持股資料，請先按「重新抓取持股」"}, status_code=400)

    benchmark_weights, error = _parse_weighted_basket(benchmark or "SPY")
    if error:
        return JSONResponse({"error": f"比較基準：{error}"}, status_code=400)

    try:
        result = build_performance_report(snapshots, transactions, start, end, benchmark_weights)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    with Repositories() as repo:
        notes_by_id = repo.transaction_notes([t["id"] for t in result["transactions"]])
    result["transactions"] = [
        {**t, "report_date": t["report_date"].isoformat(), "note": notes_by_id.get(t["id"], "")}
        for t in result["transactions"]
    ]
    return JSONResponse(result)


@app.post("/api/transaction-notes")
def set_transaction_note(transaction_id: str = Form(...), note: str = Form("")):
    with Repositories() as repo:
        if not repo.transaction_exists(transaction_id):
            return JSONResponse({"error": "找不到這筆交易"}, status_code=404)
        repo.upsert_transaction_note(transaction_id, note)
    return JSONResponse({"ok": True})


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
        # Skip fetching the user's own holdings entirely - useful because
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

    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
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

    with Repositories() as repo:
        targets = repo.targets()
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


_DCA_FREQUENCY_LABELS = {"M": "月", "Q": "季", "H": "半年", "A": "年"}


def _parse_contribution_plans(raw: str) -> tuple[list[tuple[str, float, str]] | None, str | None]:
    """Parse one or more ";"-separated "金額/頻率" plans (e.g. "1000/M;10000/A")
    for multi-line contribution-schedule comparison. Returns (list of
    (label, amount, frequency)) or (None, error_message)."""
    plans = []
    for segment in raw.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        parts = segment.split("/")
        if len(parts) != 2:
            return None, f"「{segment}」格式錯誤，範例：1000/M（M=月 Q=季 H=半年 A=年）"
        amount_str, freq = parts[0].strip(), parts[1].strip().upper()
        try:
            amount = float(amount_str)
        except ValueError:
            return None, f"「{segment}」金額格式錯誤"
        if amount <= 0:
            return None, f"「{segment}」金額需大於 0"
        if freq not in _DCA_FREQUENCY_LABELS:
            return None, f"「{segment}」頻率需為 M/Q/H/A"
        plans.append((f"${amount:,.0f}/{_DCA_FREQUENCY_LABELS[freq]}", amount, freq))
    return plans, None


@app.post("/api/dca")
def dca(
    start: str = Form(...),
    end: str = Form(...),
    contribution: float = Form(...),
    frequency: str = Form("M"),
    compare: str = Form(""),
    plans: str = Form(""),
):
    if contribution <= 0:
        return JSONResponse({"error": "每期投入金額需大於 0"}, status_code=400)
    with Repositories() as repo:
        targets = repo.targets()

    baskets = []
    if targets:
        total_weight = sum(targets.values())
        if abs(total_weight - 1) > 0.01:
            return JSONResponse(
                {"error": f"目標配置權重總和需為 100%，目前為 {total_weight:.0%}"}, status_code=400
            )
        baskets.append(("我的目標配置", targets))

    if compare:
        extra, error = _parse_multi_basket(compare)
        if error:
            return JSONResponse({"error": f"比較標的：{error}"}, status_code=400)
        baskets += extra or []

    # Same overlapping-line problem as the contribution-plan dedup below,
    # but for baskets with identical weights (e.g. "比較標的" accidentally
    # repeating the target allocation's own composition).
    seen_baskets = set()
    deduped_baskets = []
    for basket_label, weights in baskets:
        key = frozenset(weights.items())
        if key not in seen_baskets:
            seen_baskets.add(key)
            deduped_baskets.append((basket_label, weights))
    baskets = deduped_baskets

    if not baskets:
        return JSONResponse({"error": "尚未設定目標配置，且沒有輸入比較標的"}, status_code=400)

    contribution_plans = [(f"${contribution:,.0f}/{_DCA_FREQUENCY_LABELS.get(frequency, frequency)}", contribution, frequency)]
    if plans:
        extra_plans, error = _parse_contribution_plans(plans)
        if error:
            return JSONResponse({"error": f"比較投入方案：{error}"}, status_code=400)
        contribution_plans += extra_plans or []
    # A duplicate (amount, frequency) pair - e.g. the "比較投入方案" field
    # accidentally repeating what's already in the main 每期投入金額/投入頻率
    # fields - produces two datasets with byte-identical values that draw
    # exactly on top of each other, making one line look like it vanished.
    seen_plans = set()
    deduped_plans = []
    for plan_label, plan_amount, plan_frequency in contribution_plans:
        key = (plan_amount, plan_frequency)
        if key not in seen_plans:
            seen_plans.add(key)
            deduped_plans.append((plan_label, plan_amount, plan_frequency))
    contribution_plans = deduped_plans

    items = []
    for basket_label, weights in baskets:
        for plan_label, plan_amount, plan_frequency in contribution_plans:
            label_parts = []
            if len(baskets) > 1:
                label_parts.append(basket_label)
            if len(contribution_plans) > 1:
                label_parts.append(plan_label)
            label = " ".join(label_parts) or basket_label
            try:
                result = run_dca_comparison(weights, start, end, plan_amount, plan_frequency)
            except Exception as e:
                return JSONResponse({"error": f"{label}：{e}"}, status_code=400)
            result["label"] = label
            items.append(result)
    return JSONResponse({"items": items})


@app.get("/api/drip")
def drip(symbol: str, start: str, end: str, initial_investment: float = 10000):
    try:
        result = simulate_drip(symbol.upper(), start, end, initial_investment)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    result["symbol"] = symbol.upper()
    return JSONResponse(result)
