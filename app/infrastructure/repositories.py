"""Persistence gateway for the interface layer.

Every DB read/write the HTTP layer needs goes through `Repositories` so the
routes never touch SQLAlchemy sessions or models directly. Use it as a
context manager - one session per unit of work:

    with Repositories() as repo:
        snapshots = repo.latest_snapshots()
        repo.upsert_goal(100000, date(2032, 1, 1))
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import desc

from app.infrastructure.db import (
    ExchangeRateSnapshot,
    FundamentalsCache,
    InvestmentGoal,
    PositionNote,
    PositionSnapshot,
    SessionLocal,
    TargetAllocation,
    Transaction,
    TransactionNote,
)

_GOAL_ID = "default"
_USDTWD = "USDTWD"


class Repositories:
    def __init__(self) -> None:
        self._db = SessionLocal()

    def __enter__(self) -> "Repositories":
        return self

    def __exit__(self, *exc) -> None:
        self._db.close()

    # --- position snapshots ---------------------------------------------------

    def latest_snapshot_at(self) -> datetime | None:
        row = (
            self._db.query(PositionSnapshot.snapshot_at)
            .order_by(desc(PositionSnapshot.snapshot_at))
            .first()
        )
        return row[0] if row else None

    def latest_snapshots(self) -> list[dict]:
        latest = (
            self._db.query(PositionSnapshot.snapshot_at)
            .order_by(desc(PositionSnapshot.snapshot_at))
            .first()
        )
        if not latest:
            return []
        rows = (
            self._db.query(PositionSnapshot)
            .filter(PositionSnapshot.snapshot_at == latest[0])
            .all()
        )
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

    def all_snapshot_points(self) -> list[dict]:
        """Every snapshot row, trimmed to what the allocation-history chart needs."""
        return [
            {"snapshot_at": r.snapshot_at, "symbol": r.symbol, "market_value": r.market_value}
            for r in self._db.query(PositionSnapshot).all()
        ]

    # --- transactions ------------------------------------------------------------

    def all_transactions(self) -> list[dict]:
        return [
            {
                "id": t.id,
                "symbol": t.symbol,
                "trans_type": t.trans_type,
                "report_date": t.report_date,
                "quantity": t.quantity,
                "trade_price": t.trade_price,
                "amount": t.amount,
            }
            for t in self._db.query(Transaction).all()
        ]

    # --- target allocations ----------------------------------------------------

    def targets(self) -> dict[str, float]:
        return {t.symbol: t.target_weight for t in self._db.query(TargetAllocation).all()}

    def upsert_target(self, symbol: str, weight: float) -> None:
        symbol = symbol.upper()
        existing = self._db.get(TargetAllocation, symbol)
        if existing:
            existing.target_weight = weight
        else:
            self._db.add(TargetAllocation(symbol=symbol, target_weight=weight))
        self._db.commit()

    def delete_target(self, symbol: str) -> None:
        existing = self._db.get(TargetAllocation, symbol.upper())
        if existing:
            self._db.delete(existing)
            self._db.commit()

    # --- notes ----------------------------------------------------------------

    def notes(self) -> dict[str, str]:
        return dict(self._db.query(PositionNote.symbol, PositionNote.note).all())

    def upsert_note(self, symbol: str, note: str) -> None:
        symbol = symbol.upper()
        existing = self._db.get(PositionNote, symbol)
        if existing:
            existing.note = note
            existing.updated_at = datetime.now(timezone.utc)
        else:
            self._db.add(PositionNote(symbol=symbol, note=note))
        self._db.commit()

    def transaction_notes(self, transaction_ids: list[str]) -> dict[str, str]:
        return dict(
            self._db.query(TransactionNote.transaction_id, TransactionNote.note)
            .filter(TransactionNote.transaction_id.in_(transaction_ids))
            .all()
        )

    def transaction_exists(self, transaction_id: str) -> bool:
        return self._db.get(Transaction, transaction_id) is not None

    def upsert_transaction_note(self, transaction_id: str, note: str) -> None:
        existing = self._db.get(TransactionNote, transaction_id)
        if existing:
            existing.note = note
            existing.updated_at = datetime.now(timezone.utc)
        else:
            self._db.add(TransactionNote(transaction_id=transaction_id, note=note))
        self._db.commit()

    # --- investment goal -----------------------------------------------------

    def goal(self) -> InvestmentGoal | None:
        return self._db.get(InvestmentGoal, _GOAL_ID)

    def upsert_goal(self, target_amount: float, target_date: date) -> None:
        existing = self._db.get(InvestmentGoal, _GOAL_ID)
        if existing:
            existing.target_amount = target_amount
            existing.target_date = target_date
            existing.updated_at = datetime.now(timezone.utc)
        else:
            self._db.add(
                InvestmentGoal(id=_GOAL_ID, target_amount=target_amount, target_date=target_date)
            )
        self._db.commit()

    def delete_goal(self) -> None:
        existing = self._db.get(InvestmentGoal, _GOAL_ID)
        if existing:
            self._db.delete(existing)
            self._db.commit()

    # --- fx + fundamentals metadata ----------------------------------------

    def usd_twd_rate(self) -> float | None:
        row = (
            self._db.query(ExchangeRateSnapshot)
            .filter(ExchangeRateSnapshot.pair == _USDTWD)
            .order_by(desc(ExchangeRateSnapshot.fetched_at))
            .first()
        )
        return row.rate if row else None

    def fundamentals_meta(self) -> dict[str, dict]:
        return {
            row.symbol: {"quoteType": row.quoteType, "sector": row.sector}
            for row in self._db.query(FundamentalsCache).all()
        }

    def fundamentals_cache(self, symbols: list[str]) -> dict[str, dict]:
        from app.infrastructure.fundamentals_cache import load_fundamentals

        return load_fundamentals(self._db, symbols)

    # --- refresh write path -------------------------------------------------

    def save_refresh(self, positions: list[dict], transactions: list[dict], rate: float | None) -> None:
        now = datetime.now(timezone.utc)
        for p in positions:
            self._db.add(PositionSnapshot(snapshot_at=now, **p))
        for t in transactions:
            tid = Transaction.make_id(t)
            if self._db.get(Transaction, tid) is None:
                self._db.add(Transaction(id=tid, fetched_at=now, **t))
        if rate is not None:
            self._db.add(ExchangeRateSnapshot(pair=_USDTWD, rate=rate, fetched_at=now))
        self._db.commit()
