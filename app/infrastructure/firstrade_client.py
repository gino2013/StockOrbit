"""Wraps the unofficial `firstrade` package to fetch current holdings and
account history (trades, dividends, interest, deposits).

Two credential sources: explicit `FtCreds` (per-user, decrypted by the
caller from `firstrade_credentials` - see app.infrastructure.crypto), or
the FT_USERNAME / FT_PASSWORD / FT_MFA_SECRET env vars (the site owner's
account, when no per-user credentials are passed). FT_MFA_SECRET/
mfa_secret is the TOTP secret, not a backup code, so login can complete
without an interactive prompt for a mailed/texted one-time code.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime

from firstrade import account


@dataclass(frozen=True)
class FtCreds:
    username: str
    password: str
    mfa_secret: str = ""


def _login(creds: FtCreds | None = None) -> account.FTSession:
    if creds is not None:
        username, password, mfa_secret = creds.username, creds.password, creds.mfa_secret
    else:
        username = os.environ.get("FT_USERNAME")
        password = os.environ.get("FT_PASSWORD")
        mfa_secret = os.environ.get("FT_MFA_SECRET", "")
    if not username or not password:
        raise RuntimeError("Firstrade 帳號密碼未設定")

    session = account.FTSession(
        username=username, password=password, mfa_secret=mfa_secret, save_session=True
    )
    if session.login():
        raise RuntimeError(
            "Firstrade 登入需要一次性驗證碼，但 TOTP 密鑰未通過驗證。請確認輸入的是"
            "「驗證應用程式」用的 TOTP 密鑰，不是簡訊/email 收到的驗證碼。"
        )
    return session


def fetch_positions(session: account.FTSession | None = None) -> list[dict]:
    # ponytail: one login shared across fetch_positions()/fetch_transactions()
    # when a session is passed in (see main._refresh_and_save) - logging in
    # twice per refresh would double how often Firstrade sees a fresh login,
    # which risks it flagging the account for unusual activity.
    session = session or _login()
    accounts = account.FTAccountData(session)
    if not accounts.account_numbers:
        raise RuntimeError("Login succeeded but no Firstrade accounts were found")

    rows = []
    for account_number in accounts.account_numbers:
        positions = accounts.get_positions(account=account_number)
        for item in positions.get("items", []):
            market_value = float(item.get("market_value", 0) or 0)
            rows.append(
                {
                    "account_number": account_number,
                    "symbol": item.get("symbol"),
                    "quantity": float(item.get("quantity", 0) or 0),
                    "cost_basis": float(item.get("cost", 0) or 0),
                    "market_value": market_value,
                    "price": float(item.get("last", 0) or 0),
                    "raw_json": json.dumps(item),
                }
            )

        # Use the account's own "cash_balance" field (same number Firstrade's
        # UI shows as "現金結餘") rather than deriving it as account_total minus
        # position market values - the two figures come from different quote
        # snapshots and drift apart by tens of dollars as live prices move.
        balances = accounts.get_account_balances(account=account_number).get("result", {})
        cash = float(balances.get("cash_balance", 0) or 0)
        if abs(cash) > 0.01:
            rows.append(
                {
                    "account_number": account_number,
                    "symbol": "CASH",
                    "quantity": 1.0,
                    "cost_basis": cash,
                    "market_value": cash,
                    "price": cash,
                    "raw_json": json.dumps(balances),
                }
            )
    return rows


def fetch_transactions(session: account.FTSession | None = None) -> list[dict]:
    """Account history: trades (BOUGHT/SOLD), dividends, interest, deposits.

    Always pulls the widest range Firstrade will give us (custom range from
    a far-past date to today), not just "ytd" - FIFO realized-gain matching
    needs the full buy history, not just this year's, or a lot bought last
    year and sold this year would look like it has zero cost basis.
    """
    session = session or _login()
    accounts = account.FTAccountData(session)
    if not accounts.account_numbers:
        raise RuntimeError("Login succeeded but no Firstrade accounts were found")

    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for account_number in accounts.account_numbers:
        history = accounts.get_account_history(
            account_number, date_range="cust", custom_range=["2015-01-01", today]
        )
        for item in history.get("items", []):
            report_date = datetime.strptime(item["report_date"], "%Y-%m-%d").date()
            rows.append(
                {
                    "account_number": account_number,
                    "symbol": item.get("symbol") or None,
                    "trans_type": item.get("trans_str", "OTHER"),
                    "report_date": report_date,
                    "quantity": float(item.get("quantity", 0) or 0),
                    "trade_price": float(item.get("trade_price", 0) or 0),
                    "amount": float(item.get("amount", 0) or 0),
                    "description": item.get("description", ""),
                    "raw_json": json.dumps(item),
                }
            )
    return rows
