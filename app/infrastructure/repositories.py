"""Persistence gateway for the interface layer.

Every DB read/write the HTTP layer needs goes through `Repositories`, so the
routes never touch SQLAlchemy sessions or models directly - and, since
multi-user step 2, this is also the single place that scopes queries to one
user. Use it as a context manager, one instance per unit of work:

    with Repositories(user.id) as repo:
        snapshots = repo.latest_snapshots()
        repo.upsert_goal(100000, date(2032, 1, 1))

`user_id=None` is a transitional convenience: it resolves to the `is_owner`
account (see app.interface.auth.ensure_owner). Step 3 makes every caller
pass an explicit id from `current_user`.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import desc

from app.infrastructure.db import (
    ExchangeRateSnapshot,
    FirestradeCredential,
    FundamentalsCache,
    InvestmentGoal,
    PositionNote,
    PositionNoteHistory,
    PositionSnapshot,
    SessionLocal,
    TargetAllocation,
    Transaction,
    TransactionNote,
    User,
)

_USDTWD = "USDTWD"
_owner_id_cache: str | None = None


def _resolve_owner_id() -> str:
    global _owner_id_cache
    if _owner_id_cache is None:
        db = SessionLocal()
        try:
            row = db.query(User.id).filter(User.is_owner.is_(True)).first()
        finally:
            db.close()
        if row is None:
            from app.interface.auth import ensure_owner

            _owner_id_cache = ensure_owner()
        else:
            _owner_id_cache = row[0]
    return _owner_id_cache


class Repositories:
    def __init__(self, user_id: str | None = None) -> None:
        if user_id is None:
            from app.interface.auth import current_user_id

            user_id = current_user_id()
        self._user_id = user_id or _resolve_owner_id()
        self._db = SessionLocal()

    def __enter__(self) -> "Repositories":
        return self

    def __exit__(self, *exc) -> None:
        self._db.close()

    def _mine(self, model):
        return self._db.query(model).filter(model.user_id == self._user_id)

    # --- position snapshots ---------------------------------------------------

    def latest_snapshot_at(self) -> datetime | None:
        row = self._mine(PositionSnapshot).with_entities(
            PositionSnapshot.snapshot_at
        ).order_by(desc(PositionSnapshot.snapshot_at)).first()
        return row[0] if row else None

    def latest_snapshots(self) -> list[dict]:
        latest = self.latest_snapshot_at()
        if latest is None:
            return []
        rows = self._mine(PositionSnapshot).filter(
            PositionSnapshot.snapshot_at == latest
        ).all()
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
            for r in self._mine(PositionSnapshot).all()
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
            for t in self._mine(Transaction).all()
        ]

    # --- target allocations ----------------------------------------------------

    def targets(self) -> dict[str, float]:
        return {t.symbol: t.target_weight for t in self._mine(TargetAllocation).all()}

    def upsert_target(self, symbol: str, weight: float) -> None:
        symbol = symbol.upper()
        existing = self._mine(TargetAllocation).filter(
            TargetAllocation.symbol == symbol
        ).first()
        if existing:
            existing.target_weight = weight
        else:
            self._db.add(
                TargetAllocation(symbol=symbol, target_weight=weight, user_id=self._user_id)
            )
        self._db.commit()

    def delete_target(self, symbol: str) -> None:
        existing = self._mine(TargetAllocation).filter(
            TargetAllocation.symbol == symbol.upper()
        ).first()
        if existing:
            self._db.delete(existing)
            self._db.commit()

    # --- notes ----------------------------------------------------------------

    def notes(self) -> dict[str, str]:
        return {n.symbol: n.note for n in self._mine(PositionNote).all()}

    def upsert_note(self, symbol: str, note: str) -> None:
        symbol = symbol.upper()
        existing = self._mine(PositionNote).filter(PositionNote.symbol == symbol).first()
        if existing:
            existing.note = note
            existing.updated_at = datetime.now(timezone.utc)
        else:
            self._db.add(PositionNote(symbol=symbol, note=note, user_id=self._user_id))
        # Every save is also logged here so past versions stay visible
        # instead of being overwritten - even a save to "" (cleared note)
        # is logged, so the history shows exactly when a note was removed.
        self._db.add(PositionNoteHistory(symbol=symbol, note=note, user_id=self._user_id))
        self._db.commit()

    def note_history(self) -> dict[str, list[dict]]:
        """Every past version of every symbol's note, newest first,
        grouped by symbol - for the "歷史版本" view under each note."""
        rows = self._mine(PositionNoteHistory).order_by(desc(PositionNoteHistory.saved_at)).all()
        by_symbol: dict[str, list[dict]] = {}
        for r in rows:
            by_symbol.setdefault(r.symbol, []).append({"note": r.note, "saved_at": r.saved_at})
        return by_symbol

    def transaction_notes(self, transaction_ids: list[str]) -> dict[str, str]:
        return {
            n.transaction_id: n.note
            for n in self._mine(TransactionNote).filter(
                TransactionNote.transaction_id.in_(transaction_ids)
            ).all()
        }

    def transaction_exists(self, transaction_id: str) -> bool:
        return self._mine(Transaction).filter(Transaction.id == transaction_id).first() is not None

    def upsert_transaction_note(self, transaction_id: str, note: str) -> None:
        existing = self._mine(TransactionNote).filter(
            TransactionNote.transaction_id == transaction_id
        ).first()
        if existing:
            existing.note = note
            existing.updated_at = datetime.now(timezone.utc)
        else:
            self._db.add(
                TransactionNote(
                    transaction_id=transaction_id, note=note, user_id=self._user_id
                )
            )
        self._db.commit()

    # --- investment goal -----------------------------------------------------

    def goal(self) -> InvestmentGoal | None:
        return self._mine(InvestmentGoal).first()

    def upsert_goal(self, target_amount: float, target_date: date) -> None:
        existing = self._mine(InvestmentGoal).first()
        if existing:
            existing.target_amount = target_amount
            existing.target_date = target_date
            existing.updated_at = datetime.now(timezone.utc)
        else:
            self._db.add(
                InvestmentGoal(
                    user_id=self._user_id,
                    target_amount=target_amount,
                    target_date=target_date,
                )
            )
        self._db.commit()

    def delete_goal(self) -> None:
        existing = self._mine(InvestmentGoal).first()
        if existing:
            self._db.delete(existing)
            self._db.commit()

    # --- firstrade credentials -------------------------------------------------

    def firstrade_credential(self) -> FirestradeCredential | None:
        return self._db.query(FirestradeCredential).filter(
            FirestradeCredential.user_id == self._user_id
        ).first()

    def save_firstrade_credentials(
        self, username_enc: str, password_enc: str, mfa_secret_enc: str
    ) -> None:
        existing = self.firstrade_credential()
        if existing:
            existing.username_enc = username_enc
            existing.password_enc = password_enc
            existing.mfa_secret_enc = mfa_secret_enc
            existing.last_sync_error = None
        else:
            self._db.add(
                FirestradeCredential(
                    user_id=self._user_id,
                    username_enc=username_enc,
                    password_enc=password_enc,
                    mfa_secret_enc=mfa_secret_enc,
                )
            )
        self._db.commit()

    def delete_firstrade_credentials(self) -> None:
        self._db.query(FirestradeCredential).filter(
            FirestradeCredential.user_id == self._user_id
        ).delete()
        self._db.commit()

    def record_sync(self, *, ok: bool, error: str | None) -> None:
        row = self.firstrade_credential()
        if row is None:
            return
        row.last_sync_at = datetime.now(timezone.utc)
        row.last_sync_error = None if ok else error
        self._db.commit()

    # --- account deletion --------------------------------------------------

    def delete_account(self) -> None:
        """Hard-delete every row this user owns, then the user itself.

        Not reversible - the caller (a route behind the user's own confirmed
        click, see /settings/delete-account) is responsible for that being
        intentional.
        """
        for model in (
            PositionSnapshot, Transaction, TargetAllocation,
            PositionNote, TransactionNote, InvestmentGoal,
        ):
            self._mine(model).delete()
        self._db.query(FirestradeCredential).filter(
            FirestradeCredential.user_id == self._user_id
        ).delete()
        self._db.query(User).filter(User.id == self._user_id).delete()
        self._db.commit()

    # --- global market data (NOT user-scoped) -----------------------------

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
            self._db.add(PositionSnapshot(snapshot_at=now, user_id=self._user_id, **p))
        for t in transactions:
            tid = Transaction.make_id(t)
            if self.transaction_exists(tid):
                continue
            self._db.add(Transaction(id=tid, fetched_at=now, user_id=self._user_id, **t))
        if rate is not None:  # exchange rate is global, not user-scoped
            self._db.add(ExchangeRateSnapshot(pair=_USDTWD, rate=rate, fetched_at=now))
        self._db.commit()
