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
        for item in positions.get("items", []):
            rows.append(
                {
                    "account_number": account_number,
                    "symbol": item.get("symbol"),
                    "quantity": float(item.get("quantity", 0) or 0),
                    "cost_basis": float(item.get("cost_basis", 0) or 0),
                    "market_value": float(item.get("market_value", 0) or 0),
                    "price": float(item.get("last_price", item.get("price", 0)) or 0),
                    "raw_json": json.dumps(item),
                }
            )
    return rows
