"""Parse a user-supplied CSV of positions or transactions into the same
row dicts firstrade_client.fetch_positions / fetch_transactions produce,
so Repositories.save_refresh can store them unchanged.

This is the no-credential way to get data in (and the fallback if the
Firstrade scraper breaks). The accepted format is a plain header row plus
data rows - documented in the /settings import box and the README. Headers
are matched case-insensitively after trimming; a required column that's
missing, or a column we don't recognise, is a clear error naming the row.
"""

import csv
import io
import json
from datetime import datetime


class CsvImportError(ValueError):
    """A user-fixable problem with the uploaded file. The message is shown
    to the user verbatim, so keep it specific (which row, which column)."""


_POSITION_COLS = {"symbol", "quantity", "avg_cost", "cost_basis", "price", "market_value", "account_number"}
_TRANSACTION_COLS = {"date", "type", "symbol", "quantity", "price", "amount", "description", "account_number"}

_TYPE_MAP = {
    "buy": "BOUGHT", "bought": "BOUGHT",
    "sell": "SOLD", "sold": "SOLD",
    "div": "DIV", "dividend": "DIV",
    "interest": "INTEREST", "int": "INTEREST",
    "deposit": "DEPOSIT", "dep": "DEPOSIT",
}

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d")


def parse_positions(text: str) -> list[dict]:
    rows = _read(text, required={"symbol", "quantity"}, known=_POSITION_COLS)
    out = []
    for line, r in rows:
        symbol = r["symbol"].strip().upper()
        if not symbol:
            raise CsvImportError(f"第 {line} 列：symbol 空白")
        qty = _num(r, "quantity", line, required=True)
        price = _num(r, "price", line, default=0.0)
        if r.get("cost_basis", "").strip():
            cost_basis = _num(r, "cost_basis", line, default=0.0)
        else:
            cost_basis = _num(r, "avg_cost", line, default=0.0) * qty
        market_value = _num(r, "market_value", line, default=0.0) if r.get("market_value", "").strip() else price * qty
        out.append({
            "account_number": (r.get("account_number") or "").strip() or "IMPORT",
            "symbol": symbol,
            "quantity": qty,
            "cost_basis": cost_basis,
            "market_value": market_value,
            "price": price,
            "raw_json": json.dumps({"imported": True}),
        })
    if not out:
        raise CsvImportError("檔案沒有任何資料列")
    return out


def parse_transactions(text: str) -> list[dict]:
    rows = _read(text, required={"date", "type"}, known=_TRANSACTION_COLS)
    out = []
    for line, r in rows:
        report_date = _date(r["date"].strip(), line)
        raw_type = r["type"].strip().lower()
        trans_type = _TYPE_MAP.get(raw_type, raw_type.upper() or "OTHER")
        symbol = (r.get("symbol") or "").strip().upper() or None
        qty = _num(r, "quantity", line, default=0.0)
        price = _num(r, "price", line, default=0.0)
        if r.get("amount", "").strip():
            amount = _num(r, "amount", line, default=0.0)
        elif trans_type == "BOUGHT":
            amount = -(qty * price)
        elif trans_type == "SOLD":
            amount = qty * price
        else:
            amount = 0.0
        out.append({
            "account_number": (r.get("account_number") or "").strip() or "IMPORT",
            "symbol": symbol,
            "trans_type": trans_type,
            "report_date": report_date,
            "quantity": qty,
            "trade_price": price,
            "amount": amount,
            "description": (r.get("description") or "").strip(),
            "raw_json": json.dumps({"imported": True}),
        })
    if not out:
        raise CsvImportError("檔案沒有任何資料列")
    return out


def _read(text: str, required: set[str], known: set[str]) -> list[tuple[int, dict]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CsvImportError("檔案是空的或沒有標題列")
    norm = {name: name.strip().lower() for name in reader.fieldnames if name is not None}
    present = set(norm.values())
    missing = required - present
    if missing:
        raise CsvImportError(
            f"缺少必要欄位：{', '.join(sorted(missing))}"
            f"（讀到的欄位：{', '.join(reader.fieldnames)}）"
        )
    unknown = present - known
    if unknown:
        raise CsvImportError(f"不認得的欄位：{', '.join(sorted(unknown))}（可用欄位：{', '.join(sorted(known))}）")
    rows = []
    for i, raw in enumerate(reader, start=2):  # row 1 is the header
        rows.append((i, {norm[k]: (v or "") for k, v in raw.items() if k in norm}))
    return rows


def _num(row: dict, key: str, line: int, default: float | None = None, required: bool = False) -> float:
    val = (row.get(key) or "").strip().replace(",", "").replace("$", "")
    if not val:
        if required:
            raise CsvImportError(f"第 {line} 列：{key} 空白")
        return default
    try:
        return float(val)
    except ValueError:
        raise CsvImportError(f"第 {line} 列：{key}「{val}」不是數字")


def _date(s: str, line: int):
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise CsvImportError(f"第 {line} 列：date「{s}」格式不支援（用 YYYY-MM-DD 或 MM/DD/YYYY）")
