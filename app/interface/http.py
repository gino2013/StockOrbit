import os
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

load_dotenv()

from app.application.dashboard import build_dashboard_context
from app.application.fire import fire_progress
from app.application.goals import goal_progress
from app.application.tax import overseas_income_report, tax_loss_report
from app.infrastructure import market_data
from app.infrastructure.repositories import Repositories
from app.infrastructure.db import (
    FirestradeCredential,
    SessionLocal,
    User,
    check_schema_matches_models,
    run_pending_migrations,
)
from app.interface import auth
from app.interface.auth import COOKIE_NAME, check_app_secret_key, ensure_owner
from app.infrastructure import crypto, mailer
from app.infrastructure.csv_import import CsvImportError, parse_positions, parse_transactions
from app.infrastructure.export import build_holdings_csv, build_transactions_csv
from app.infrastructure.firstrade_client import FtCreds, _login, fetch_positions, fetch_transactions
from app.infrastructure.fundamentals import fetch_fundamentals
from app.domain.portfolio.advice import build_advice
from app.domain.portfolio.cash_deployment import suggest_cash_deployment
from app.domain.analytics.backtest import max_drawdown_details, run_backtest, run_benchmarks_only
from app.domain.analytics.compound_curve import build_compound_curve, build_portfolio_compound_curve, fetch_annual_returns
from app.domain.analytics.compounder_checklist import build_compounder_checklist
from app.domain.analytics.correlation import compute_correlation_matrix
from app.domain.analytics.dca import run_dca_comparison
from app.domain.analytics.drawdown_periods import find_drawdown_periods
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

async def _bind_request_user(request: Request) -> None:
    """App-level dependency: publish the middleware-loaded user into the
    request ContextVar so `Repositories()` scopes to the caller. Runs in the
    endpoint's own execution context, so it reaches sync threadpool handlers."""
    auth.bind_current_user(getattr(request.state, "user", None))


app = FastAPI(title="StockOrbit", dependencies=[Depends(_bind_request_user)])
templates = Jinja2Templates(directory="app/templates")

_TAIPEI = ZoneInfo("Asia/Taipei")


def _to_taipei(dt: datetime | None) -> datetime | None:
    """DB timestamps are stored as UTC but come back tz-naive (SQLite and
    Postgres both drop tzinfo on a plain DateTime column) - template code
    that renders one to a human needs it converted to the user's actual
    timezone, not shown as if the UTC wall-clock time were local."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_TAIPEI)


templates.env.filters["to_taipei"] = _to_taipei
# Fail fast and legibly at startup, in the deploy log - not a raw 500 on the
# first login/request. See docs/multi-user-architecture.md.
check_app_secret_key()
run_pending_migrations()  # replaces the old init_db()/create_all - see db.py
check_schema_matches_models()  # belt-and-suspenders: verify the migration actually landed
ensure_owner()

# Paths reachable without a session. Everything else requires one.
_PUBLIC_PREFIXES = (
    "/login", "/register", "/logout", "/verify", "/forgot", "/reset",
    "/terms", "/privacy", "/static", "/docs", "/redoc", "/openapi.json", "/favicon",
)


# ponytail: in-process, per-instance counters - resets on redeploy, doesn't
# sync across instances. Fine for open registration abuse on Render's single
# free-tier instance; swap for a shared store (e.g. Redis) if this ever runs
# on more than one instance at once.
_rate_buckets: dict[str, deque] = defaultdict(deque)


def _rate_limited(key: str, limit: int, window_seconds: float) -> bool:
    """True (and records nothing) once `key` has hit `limit` calls within
    the trailing `window_seconds` - a plain sliding-window counter."""
    now = time.monotonic()
    bucket = _rate_buckets[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def _require_login(request: Request, call_next):
    path = request.url.path
    if not any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        user = auth._load_user(request)
        if user is None:
            if path.startswith("/api/"):
                return JSONResponse({"error": "請先登入"}, status_code=401)
            return RedirectResponse("/login", status_code=303)
        request.state.user = user
    return await call_next(request)


def _current_user(request: Request) -> User:
    return request.state.user  # guaranteed by _require_login for non-public paths


def _email_verification_required() -> bool:
    """Whether the Firstrade-credential form and CSV import are gated behind a
    verified email. Default on; set REQUIRE_EMAIL_VERIFICATION=false to lift
    the gate when no SMTP sender is configured (see mailer.py) - at the cost
    of the open-registration abuse protection that gate provides."""
    return os.environ.get("REQUIRE_EMAIL_VERIFICATION", "true").strip().lower() not in ("false", "0", "no")


def _send_verification_email(request: Request, background_tasks: BackgroundTasks, email: str) -> None:
    token = auth.make_email_token("verify", email)
    link = f"{str(request.base_url).rstrip('/')}/verify?token={token}"
    background_tasks.add_task(
        mailer.send, email, "StockOrbit 信箱驗證",
        f"請點以下連結完成信箱驗證（15 分鐘內有效）：\n{link}\n\n如果不是你本人操作，請忽略這封信。",
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {"error": None, "next": next})


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/")):
    if _rate_limited(f"login:{_client_ip(request)}", limit=20, window_seconds=600):
        return templates.TemplateResponse(
            request, "login.html", {"error": "嘗試次數過多，請稍後再試。", "next": next}, status_code=429
        )
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.strip().lower()).first()
        ok = user is not None and auth.verify_password(password, user.password_hash)
        cookie = auth.make_session_cookie(user) if ok else None
    finally:
        db.close()
    if not ok:
        return templates.TemplateResponse(
            request, "login.html", {"error": "帳號或密碼錯誤", "next": next}, status_code=401
        )
    resp = RedirectResponse(next if next.startswith("/") else "/", status_code=303)
    resp.set_cookie(COOKIE_NAME, cookie, max_age=auth.SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"error": None})


@app.post("/register")
def register(request: Request, background_tasks: BackgroundTasks, email: str = Form(...), password: str = Form(...)):
    if _rate_limited(f"register:{_client_ip(request)}", limit=10, window_seconds=3600):
        return templates.TemplateResponse(
            request, "register.html", {"error": "嘗試次數過多，請稍後再試。"}, status_code=429
        )
    email = email.strip().lower()
    err = None
    if "@" not in email or len(email) > 254:
        err = "email 格式不正確"
    elif len(password) < 8:
        err = "密碼至少 8 個字元"
    if err is None:
        db = SessionLocal()
        try:
            if db.query(User).filter(User.email == email).first() is not None:
                err = "這個 email 已經註冊過了"
            else:
                user = User(email=email, password_hash=auth.hash_password(password))
                db.add(user)
                db.commit()
                cookie = auth.make_session_cookie(user)
        finally:
            db.close()
    if err is not None:
        return templates.TemplateResponse(request, "register.html", {"error": err}, status_code=400)
    if _email_verification_required():
        _send_verification_email(request, background_tasks, email)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE_NAME, cookie, max_age=auth.SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.get("/verify", response_class=HTMLResponse)
def verify_email(request: Request, token: str):
    email = auth.read_email_token("verify", token)
    if email is None:
        return HTMLResponse(
            "<p>驗證連結無效或已過期，請登入後在「設定」頁重寄驗證信。</p><p><a href='/login'>回登入</a></p>",
            status_code=400,
        )
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            user.email_verified = True
            db.commit()
    finally:
        db.close()
    return RedirectResponse("/settings", status_code=303)


@app.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.get("/forgot", response_class=HTMLResponse)
def forgot_page(request: Request):
    return templates.TemplateResponse(request, "forgot.html", {"message": None})


@app.post("/forgot")
def forgot(request: Request, background_tasks: BackgroundTasks, email: str = Form(...)):
    if _rate_limited(f"forgot:{_client_ip(request)}", limit=5, window_seconds=600):
        return templates.TemplateResponse(
            request, "forgot.html", {"message": "嘗試次數過多，請稍後再試。"}, status_code=429
        )
    email = email.strip().lower()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
    finally:
        db.close()
    # Honest, and leaks nothing about whether the account exists.
    if not mailer.is_enabled():
        return templates.TemplateResponse(
            request, "forgot.html",
            {"message": "站台尚未設定寄信服務，暫時無法用 email 重設密碼，請聯絡管理員。"},
        )
    if user is not None:
        token = auth.make_email_token("reset", email)
        link = f"{str(request.base_url).rstrip('/')}/reset?token={token}"
        background_tasks.add_task(
            mailer.send, email, "StockOrbit 重設密碼",
            f"請點以下連結重設密碼（15 分鐘內有效）：\n{link}\n\n如果不是你本人操作，請忽略這封信。",
        )
    # Same response either way - don't leak whether the email is registered.
    return templates.TemplateResponse(request, "forgot.html", {"message": "如果這個信箱有註冊，重設密碼信已經寄出。"})


@app.get("/reset", response_class=HTMLResponse)
def reset_page(request: Request, token: str):
    return templates.TemplateResponse(request, "reset.html", {"token": token, "error": None})


@app.post("/reset")
def reset_password(request: Request, token: str = Form(...), new_password: str = Form(...)):
    email = auth.read_email_token("reset", token)
    if email is None:
        return templates.TemplateResponse(
            request, "reset.html", {"token": token, "error": "連結無效或已過期，請重新申請。"}, status_code=400
        )
    if len(new_password) < 8:
        return templates.TemplateResponse(
            request, "reset.html", {"token": token, "error": "密碼至少 8 個字元"}, status_code=400
        )
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            return templates.TemplateResponse(
                request, "reset.html", {"token": token, "error": "找不到帳號"}, status_code=400
            )
        user.password_hash = auth.hash_password(new_password)
        user.session_version += 1  # a reset should log out every session, including a stolen one
        db.commit()
        cookie = auth.make_session_cookie(user)
    finally:
        db.close()
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE_NAME, cookie, max_age=auth.SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    return templates.TemplateResponse(request, "terms.html", {})


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return templates.TemplateResponse(request, "privacy.html", {})


def _settings_context(request: Request, user: User, **extra) -> dict:
    with Repositories(user.id) as repo:
        creds_row = repo.firstrade_credential()
    return {
        "user": user,
        "ft_enabled": crypto.is_enabled(),
        "ft_creds": creds_row,
        "require_email_verification": _email_verification_required(),
        "mail_enabled": mailer.is_enabled(),
        "error": None,
        "message": None,
        **extra,
    }


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    user = _current_user(request)
    return templates.TemplateResponse(request, "settings.html", _settings_context(request, user))


@app.post("/settings/resend-verification")
def resend_verification(request: Request, background_tasks: BackgroundTasks):
    user = _current_user(request)
    if user.email_verified:
        return templates.TemplateResponse(
            request, "settings.html", _settings_context(request, user, message="這個帳號已經驗證過了。")
        )
    if not _email_verification_required():
        return templates.TemplateResponse(
            request, "settings.html",
            _settings_context(request, user, message="此站台目前未要求信箱驗證，不需要驗證。"),
        )
    if not mailer.is_enabled():
        return templates.TemplateResponse(
            request, "settings.html",
            _settings_context(request, user, error="站台尚未設定寄信服務（SMTP），沒辦法寄驗證信，請聯絡管理員。"),
            status_code=503,
        )
    if _rate_limited(f"resend-verify:{user.id}", limit=3, window_seconds=600):
        return templates.TemplateResponse(
            request, "settings.html",
            _settings_context(request, user, error="剛寄過驗證信，請稍後再試。"), status_code=429,
        )
    _send_verification_email(request, background_tasks, user.email)
    return templates.TemplateResponse(
        request, "settings.html", _settings_context(request, user, message="驗證信已寄出，請檢查信箱。")
    )


@app.post("/settings/change-password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
):
    user = _current_user(request)
    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.id == user.id).first()
        if not auth.verify_password(current_password, db_user.password_hash):
            db.expunge(db_user)
            return templates.TemplateResponse(
                request, "settings.html",
                _settings_context(request, user, error="目前密碼不正確"), status_code=400,
            )
        if len(new_password) < 8:
            db.expunge(db_user)
            return templates.TemplateResponse(
                request, "settings.html",
                _settings_context(request, user, error="新密碼至少 8 個字元"), status_code=400,
            )
        db_user.password_hash = auth.hash_password(new_password)
        db_user.session_version += 1  # log out every other session
        db.commit()
        cookie = auth.make_session_cookie(db_user)  # keep this session logged in
    finally:
        db.close()
    resp = templates.TemplateResponse(
        request, "settings.html", _settings_context(request, user, message="密碼已更新，其他登入裝置已被登出。")
    )
    resp.set_cookie(COOKIE_NAME, cookie, max_age=auth.SESSION_MAX_AGE, httponly=True, samesite="lax")
    return resp


@app.post("/settings/firstrade")
def save_firstrade(
    request: Request,
    ft_username: str = Form(...),
    ft_password: str = Form(...),
    ft_mfa_secret: str = Form(""),
):
    user = _current_user(request)
    if not crypto.is_enabled():
        return templates.TemplateResponse(
            request, "settings.html",
            _settings_context(request, user, error="此站台尚未啟用 Firstrade 連結功能"), status_code=400,
        )
    if _email_verification_required() and not user.email_verified:
        return templates.TemplateResponse(
            request, "settings.html",
            _settings_context(request, user, error="此功能需要先完成信箱驗證"), status_code=403,
        )
    with Repositories(user.id) as repo:
        repo.save_firstrade_credentials(
            crypto.encrypt(ft_username.strip()),
            crypto.encrypt(ft_password),
            crypto.encrypt(ft_mfa_secret.strip()),
        )
    return templates.TemplateResponse(
        request, "settings.html", _settings_context(request, user, message="已儲存，下次重新整理首頁會自動同步。")
    )


@app.post("/settings/firstrade/delete")
def delete_firstrade(request: Request):
    user = _current_user(request)
    with Repositories(user.id) as repo:
        repo.delete_firstrade_credentials()
    return templates.TemplateResponse(
        request, "settings.html", _settings_context(request, user, message="已移除 Firstrade 連結。")
    )


@app.post("/settings/delete-account")
def delete_account(request: Request, confirm_email: str = Form(...)):
    user = _current_user(request)
    if confirm_email.strip().lower() != user.email.lower():
        return templates.TemplateResponse(
            request, "settings.html",
            _settings_context(request, user, error="請輸入你的帳號 email 以確認刪除"), status_code=400,
        )
    with Repositories(user.id) as repo:
        repo.delete_account()
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


_IMPORT_MAX_BYTES = 2_000_000


async def _read_upload(file: UploadFile) -> str:
    raw = await file.read()
    if len(raw) > _IMPORT_MAX_BYTES:
        raise CsvImportError("檔案太大（上限 2MB）")
    try:
        return raw.decode("utf-8-sig")  # tolerate an Excel BOM
    except UnicodeDecodeError:
        raise CsvImportError("檔案不是 UTF-8 編碼")


async def _handle_import(request: Request, file: UploadFile, kind: str):
    user = _current_user(request)
    if _email_verification_required() and not user.email_verified:
        return templates.TemplateResponse(
            request, "settings.html",
            _settings_context(request, user, error="匯入功能需要先完成信箱驗證"), status_code=403,
        )
    try:
        text = await _read_upload(file)
        if kind == "positions":
            rows = parse_positions(text)
            with Repositories(user.id) as repo:
                repo.save_refresh(rows, [], None)
            msg = f"已匯入 {len(rows)} 筆持股。"
        else:
            rows = parse_transactions(text)
            with Repositories(user.id) as repo:
                repo.save_refresh([], rows, None)
            msg = f"已匯入 {len(rows)} 筆交易紀錄。"
    except CsvImportError as e:
        return templates.TemplateResponse(
            request, "settings.html",
            _settings_context(request, user, error=f"匯入失敗：{e}"), status_code=400,
        )
    return templates.TemplateResponse(
        request, "settings.html", _settings_context(request, user, message=msg)
    )


@app.post("/settings/import/positions")
async def import_positions(request: Request, file: UploadFile = File(...)):
    return await _handle_import(request, file, "positions")


@app.post("/settings/import/transactions")
async def import_transactions(request: Request, file: UploadFile = File(...)):
    return await _handle_import(request, file, "transactions")


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
        quotes = market_data.search_symbols(q)
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
        history = market_data.ticker_history("USDTWD=X", period="5d")["Close"]
        return None if history.empty else float(history.iloc[-1])
    except Exception:
        return None


def _average_usdtwd_rate(year: int) -> float | None:
    try:
        end = min(datetime.now(), datetime(year, 12, 31)).strftime("%Y-%m-%d")
        history = market_data.download_close("USDTWD=X", start=f"{year}-01-01", end=end)
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


def _stored_creds(repo: Repositories) -> tuple[FtCreds | None, FirestradeCredential | None]:
    """Decrypt this user's stored Firstrade credentials, if any."""
    row = repo.firstrade_credential()
    if row is None:
        return None, None
    if not crypto.is_enabled():
        raise RuntimeError("Firstrade 連結功能目前未啟用（FT_CREDENTIAL_KEY 未設定）")
    creds = FtCreds(
        username=crypto.decrypt(row.username_enc),
        password=crypto.decrypt(row.password_enc),
        mfa_secret=crypto.decrypt(row.mfa_secret_enc) if row.mfa_secret_enc else "",
    )
    return creds, row


def _refresh_and_save(user: User) -> None:
    """Log into Firstrade, fetch positions + transactions + USD/TWD rate, save
    a new snapshot. Raises on failure - callers decide whether that's fatal.

    Uses this user's stored credentials if they've connected one; the owner
    falls back to the FT_* env vars when they haven't stored any. Everyone
    else must connect an account first (see /settings)."""
    with Repositories(user.id) as repo:
        creds, creds_row = _stored_creds(repo)
    if creds is None and not user.is_owner:
        raise RuntimeError("尚未連結 Firstrade 帳號，請先到「設定」頁輸入帳密")
    try:
        session = _login(creds)
        positions = fetch_positions(session)
        transactions = fetch_transactions(session)
    except Exception as e:
        if creds_row is not None:
            with Repositories(user.id) as repo:
                repo.record_sync(ok=False, error=str(e))
        raise
    with Repositories(user.id) as repo:
        repo.save_refresh(positions, transactions, _fetch_usd_twd_rate())
        if creds_row is not None:
            repo.record_sync(ok=True, error=None)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, account: str | None = None):
    user = _current_user(request)
    with Repositories() as repo:
        last_snapshot_at = repo.latest_snapshot_at()
        has_creds = repo.firstrade_credential() is not None

    # The owner auto-refreshes from env credentials by default; anyone else
    # only auto-refreshes once they've connected their own Firstrade account
    # on the settings page. First-ever load after connecting (no snapshot
    # yet) refreshes right away instead of waiting for the staleness window.
    if user.is_owner or has_creds:
        stale = last_snapshot_at is None or (
            last_snapshot_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc) - AUTO_REFRESH_STALE_AFTER
        )
        if stale:
            try:
                _refresh_and_save(user)
            except Exception:
                pass  # fall back to showing the stale snapshot rather than breaking the page

    with Repositories() as repo:
        latest = repo.latest_snapshot_at()
        account_numbers = repo.account_numbers(latest)
        selected_account = repo.resolve_account(account, account_numbers)
        snapshots = repo.latest_snapshots(selected_account, latest)
        context = build_dashboard_context(
            snapshots=snapshots,
            targets=repo.targets(),
            transactions=repo.all_transactions(selected_account),
            fundamentals_meta=repo.fundamentals_meta(),
            snapshot_points=repo.all_snapshot_points(selected_account),
            notes=repo.notes(),
            note_history=repo.note_history(),
            usd_twd_rate=repo.usd_twd_rate() if snapshots else None,
            flex_mode=request.cookies.get(FLEX_MODE_COOKIE) == "1",
            as_of=datetime.now().date(),
        )
    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            **context, "user": user, "ft_connected": has_creds,
            "account_numbers": account_numbers, "selected_account": selected_account,
        },
    )


# ponytail: per-user, in-process only (resets on redeploy/restart) - fine for
# a handful of users on a single Render instance; a shared store only matters
# once this runs on more than one instance.
MANUAL_REFRESH_COOLDOWN = timedelta(minutes=10)


@app.post("/api/refresh")
def refresh(request: Request):
    user = _current_user(request)
    with Repositories(user.id) as repo:
        creds_row = repo.firstrade_credential()
    if creds_row is None and not user.is_owner:
        return HTMLResponse(
            "<p>尚未連結 Firstrade 帳號，請先到「設定」頁輸入帳密。</p>"
            "<p><a href='/settings'>前往設定</a></p>",
            status_code=400,
        )
    if creds_row is not None and creds_row.last_sync_at is not None:
        last = creds_row.last_sync_at.replace(tzinfo=timezone.utc)
        wait = MANUAL_REFRESH_COOLDOWN - (datetime.now(timezone.utc) - last)
        if wait > timedelta(0):
            minutes = max(1, int(wait.total_seconds() // 60) + 1)
            return HTMLResponse(
                f"<p>剛抓取過，請再等 {minutes} 分鐘後再試。</p><p><a href='/'>返回</a></p>",
                status_code=429,
            )
    try:
        _refresh_and_save(user)
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
def cash_deployment(amount: float, account: str | None = None):
    with Repositories() as repo:
        account = repo.resolve_account(account, repo.account_numbers())
        snapshots = repo.latest_snapshots(account)
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
    return JSONResponse({"ok": True})


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
def get_goal(account: str | None = None):
    with Repositories() as repo:
        goal = repo.goal()
        if not goal:
            return JSONResponse({"goal": None})
        account = repo.resolve_account(account, repo.account_numbers())
        progress = goal_progress(
            target_amount=goal.target_amount,
            target_date=goal.target_date,
            snapshots=repo.latest_snapshots(account),
            transactions=repo.all_transactions(account),
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


@app.get("/api/fire")
def get_fire(account: str | None = None):
    with Repositories() as repo:
        settings = repo.fire_settings()
        if not settings:
            return JSONResponse({"fire": None})
        account = repo.resolve_account(account, repo.account_numbers())
        progress = fire_progress(
            annual_expenses=settings.annual_expenses,
            swr=settings.swr,
            snapshots=repo.latest_snapshots(account),
            transactions=repo.all_transactions(account),
            as_of=datetime.now().date(),
            retirement_date=settings.retirement_date,
            expected_real_return=settings.expected_real_return,
        )
    return JSONResponse({"fire": progress})


@app.post("/api/fire")
def set_fire(
    annual_expenses: float = Form(...), swr: float = Form(0.04),
    retirement_date: str = Form(""), expected_real_return: str = Form(""),
):
    if annual_expenses <= 0:
        return JSONResponse({"error": "年支出需大於 0"}, status_code=400)
    if not 0.02 <= swr <= 0.10:
        return JSONResponse({"error": "安全提領率需介於 2% ~ 10%"}, status_code=400)
    # Coast FIRE inputs are optional - both blank means "not set up".
    retirement_date_parsed = None
    expected_real_return_parsed = None
    if retirement_date or expected_real_return:
        if not (retirement_date and expected_real_return):
            return JSONResponse({"error": "Coast FIRE 的退休日期跟預期報酬率要一起填"}, status_code=400)
        try:
            retirement_date_parsed = date.fromisoformat(retirement_date)
        except ValueError:
            return JSONResponse({"error": "退休日期格式錯誤"}, status_code=400)
        try:
            expected_real_return_parsed = float(expected_real_return)
        except ValueError:
            return JSONResponse({"error": "預期報酬率格式錯誤"}, status_code=400)
        if not -0.20 <= expected_real_return_parsed <= 0.20:
            return JSONResponse({"error": "預期報酬率需介於 -20% ~ 20%"}, status_code=400)
        if retirement_date_parsed <= datetime.now().date():
            return JSONResponse({"error": "退休日期需晚於今天"}, status_code=400)
    with Repositories() as repo:
        repo.upsert_fire_settings(annual_expenses, swr, retirement_date_parsed, expected_real_return_parsed)
    return JSONResponse({"ok": True})


@app.post("/api/fire/delete")
def delete_fire():
    with Repositories() as repo:
        repo.delete_fire_settings()
    return JSONResponse({"ok": True})


@app.post("/api/performance-report")
def performance_report(
    start: str = Form(...),
    end: str = Form(...),
    benchmark: str = Form("SPY"),
    account: str | None = Form(None),
):
    with Repositories() as repo:
        account = repo.resolve_account(account, repo.account_numbers())
        snapshots = repo.latest_snapshots(account)
        transactions = repo.all_transactions(account)
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


@app.get("/api/drawdown-periods")
def drawdown_periods(symbol: str, min_duration_days: int = 60):
    try:
        result = find_drawdown_periods(symbol.upper(), min_duration_days=min_duration_days)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(result)
