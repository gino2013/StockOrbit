"""Wraps the unofficial `firstrade` package to fetch current holdings and
account history (trades, dividends, interest, deposits).

Requires FT_USERNAME / FT_PASSWORD env vars, and FT_MFA_SECRET (the TOTP
secret, not a backup code) so login can complete without an interactive
prompt for a mailed/texted one-time code.
"""

import json
import os
from datetime import datetime

from firstrade import account


def _login() -> account.FTSession:
    username = os.environ.get("FT_USERNAME")
    password = os.environ.get("FT_PASSWORD")
    mfa_secret = os.environ.get("FT_MFA_SECRET", "")
    if not username or not password:
        raise RuntimeError("FT_USERNAME / FT_PASSWORD are not set")

    session = account.FTSession(
        username=username, password=password, mfa_secret=mfa_secret, save_session=True
    )
    if session.login():
        raise RuntimeError(
            "Firstrade login needs a one-time code and FT_MFA_SECRET was not "
            "accepted. Set FT_MFA_SECRET to your TOTP secret for unattended login."
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
