"""Wraps the unofficial `firstrade` package to fetch current holdings.

Requires FT_USERNAME / FT_PASSWORD env vars, and FT_MFA_SECRET (the TOTP
secret, not a backup code) so login can complete without an interactive
prompt for a mailed/texted one-time code.
"""

import json
import os

from firstrade import account


def fetch_positions() -> list[dict]:
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

    accounts = account.FTAccountData(session)
    if not accounts.account_numbers:
        raise RuntimeError("Login succeeded but no Firstrade accounts were found")

    rows = []
    for account_number in accounts.account_numbers:
        positions = accounts.get_positions(account=account_number)
        account_positions_value = 0.0
        for item in positions.get("items", []):
            market_value = float(item.get("market_value", 0) or 0)
            account_positions_value += market_value
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

        # account_balances holds the account's total value (positions + cash,
        # same number Firstrade's own UI shows as "帳戶總值"). The remainder
        # after subtracting position market values is uninvested cash —
        # recorded as a synthetic CASH row so it counts toward total value
        # without distorting per-symbol gain/loss (cost_basis == market_value).
        account_total = float(accounts.account_balances.get(account_number, 0) or 0)
        cash = account_total - account_positions_value
        if abs(cash) > 0.01:
            rows.append(
                {
                    "account_number": account_number,
                    "symbol": "CASH",
                    "quantity": 1.0,
                    "cost_basis": cash,
                    "market_value": cash,
                    "price": cash,
                    "raw_json": json.dumps({"account_total_value": account_total}),
                }
            )
    return rows
