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

import json
from datetime import date, datetime, timezone

from sqlalchemy import desc, func

from app.infrastructure.db import (
    AllocationAlert,
    ExchangeRateSnapshot,
    FireSettings,
    FirestradeCredential,
    FundamentalsCache,
    InvestmentGoal,
    Liability,
    MoonshotMarketScreenCache,
    PositionNote,
    PositionNoteHistory,
    PositionSnapshot,
    PriceAlert,
    SessionLocal,
    TargetAllocation,
    Transaction,
    TransactionNote,
    User,
    WatchlistSymbol,
)

_USDTWD = "USDTWD"
_owner_id_cache: str | None = None
_UNSET = object()  # sentinel: "caller didn't pass this" - None is a valid value on its own


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

    def account_numbers(self, latest=_UNSET) -> list[str]:
        """Distinct account_numbers in the latest snapshot batch, for the
        account-filter dropdown (issue #97). Sorted for a stable menu order.

        `latest`, if the caller already has it (e.g. from latest_snapshot_at()
        moments earlier in the same request), skips the repeat lookup -
        callers that don't pass it get one computed here as before."""
        if latest is _UNSET:
            latest = self.latest_snapshot_at()
        if latest is None:
            return []
        rows = self._mine(PositionSnapshot).filter(
            PositionSnapshot.snapshot_at == latest
        ).with_entities(PositionSnapshot.account_number).distinct().all()
        return sorted(r[0] for r in rows)

    @staticmethod
    def resolve_account(account: str | None, account_numbers: list[str]) -> str | None:
        """Validate a candidate ?account= against an already-fetched
        account_numbers() list - every route that accepts an account filter
        should route through this rather than passing the raw query param
        straight to latest_snapshots()/all_transactions(), so a stale value
        (an account closed/renamed since the page loaded, or bookmarked)
        quietly falls back to "all accounts" everywhere consistently,
        instead of silently filtering to zero rows in some endpoints while
        the main dashboard (which already did this check) shows the real
        total. Also covers the single-account case, where the filter UI
        isn't even shown."""
        return account if account and account in account_numbers and len(account_numbers) > 1 else None

    def latest_snapshots(self, account: str | None = None, latest=_UNSET) -> list[dict]:
        """One row per symbol. Firstrade fetches positions per account (see
        firstrade_client.fetch_positions), so a login with two accounts both
        holding the same symbol produces two PositionSnapshot rows for it -
        group and sum here rather than returning them as separate rows,
        which would silently double-count that symbol everywhere downstream
        (holdings table, pie charts, target-allocation comparison, risk/
        correlation) since they all key off symbol (issue #96).

        `account` (issue #97) restricts the grouping to one account_number -
        None (the default) keeps today's "all accounts combined" behavior.
        `latest` - see account_numbers()."""
        if latest is _UNSET:
            latest = self.latest_snapshot_at()
        if latest is None:
            return []
        query = self._mine(PositionSnapshot).filter(PositionSnapshot.snapshot_at == latest)
        if account is not None:
            query = query.filter(PositionSnapshot.account_number == account)
        rows = query.all()
        grouped: dict[str, dict] = {}
        for r in rows:
            g = grouped.setdefault(
                r.symbol, {"symbol": r.symbol, "quantity": 0.0, "market_value": 0.0, "cost_basis": 0.0}
            )
            g["quantity"] += r.quantity
            g["market_value"] += r.market_value
            g["cost_basis"] += r.cost_basis
        for g in grouped.values():
            # price re-derived from the summed totals (a same-account single
            # row reduces to its own market_value/quantity, unchanged) so a
            # multi-account symbol gets a genuine weighted-average price
            # instead of one account's raw quote.
            g["price"] = g["market_value"] / g["quantity"] if g["quantity"] else 0.0
        return list(grouped.values())

    def all_snapshot_points(self, account: str | None = None) -> list[dict]:
        """Every snapshot row, trimmed to what the allocation-history chart
        needs. `account` (issue #97) restricts to one account_number."""
        query = self._mine(PositionSnapshot)
        if account is not None:
            query = query.filter(PositionSnapshot.account_number == account)
        return [
            {"snapshot_at": r.snapshot_at, "symbol": r.symbol, "market_value": r.market_value}
            for r in query.all()
        ]

    # --- transactions ------------------------------------------------------------

    def all_transactions(self, account: str | None = None) -> list[dict]:
        """`account` (issue #97) restricts to one account_number - None (the
        default) keeps today's "all accounts combined" behavior."""
        query = self._mine(Transaction)
        if account is not None:
            query = query.filter(Transaction.account_number == account)
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
            for t in query.all()
        ]

    # --- target allocations ----------------------------------------------------

    def targets(self) -> dict[str, float]:
        rows = self._mine(TargetAllocation).order_by(TargetAllocation.sort_order).all()
        return {t.symbol: t.target_weight for t in rows}

    def upsert_target(self, symbol: str, weight: float) -> None:
        symbol = symbol.upper()
        existing = self._mine(TargetAllocation).filter(
            TargetAllocation.symbol == symbol
        ).first()
        if existing:
            existing.target_weight = weight
        else:
            # New rows go to the end of the drag-to-reorder order (issue
            # #336) - max()+1 rather than count(), so a row left mid-list
            # after deletions doesn't get a colliding sort_order.
            max_order = self._db.query(func.max(TargetAllocation.sort_order)).filter(
                TargetAllocation.user_id == self._user_id
            ).scalar()
            next_order = 0 if max_order is None else max_order + 1
            self._db.add(
                TargetAllocation(
                    symbol=symbol, target_weight=weight, user_id=self._user_id,
                    sort_order=next_order,
                )
            )
        self._db.commit()

    def delete_target(self, symbol: str) -> None:
        existing = self._mine(TargetAllocation).filter(
            TargetAllocation.symbol == symbol.upper()
        ).first()
        if existing:
            self._db.delete(existing)
            self._db.commit()

    def reorder_targets(self, symbols: list[str]) -> None:
        """Persist a drag-to-reorder drop (issue #336). Silently ignores any
        symbol that isn't actually one of this user's targets, rather than
        raising - the frontend always sends its own current DOM order, which
        should already match, but a stale/edited-elsewhere client is not
        worth a 500 over.
        """
        rows = {t.symbol: t for t in self._mine(TargetAllocation).all()}
        for idx, symbol in enumerate(symbols):
            row = rows.get(symbol.upper())
            if row:
                row.sort_order = idx
        self._db.commit()

    # --- app-local 自選股 watchlist (issue #348) -------------------------------

    def watchlist_symbols(self) -> list[str]:
        rows = self._mine(WatchlistSymbol).order_by(WatchlistSymbol.added_at).all()
        return [r.symbol for r in rows]

    def add_watchlist_symbol(self, symbol: str) -> None:
        symbol = symbol.upper()
        if self._mine(WatchlistSymbol).filter(WatchlistSymbol.symbol == symbol).first():
            return
        self._db.add(WatchlistSymbol(symbol=symbol, user_id=self._user_id))
        self._db.commit()

    def remove_watchlist_symbol(self, symbol: str) -> None:
        existing = self._mine(WatchlistSymbol).filter(WatchlistSymbol.symbol == symbol.upper()).first()
        if existing:
            self._db.delete(existing)
            self._db.commit()

    # --- 全市場搜尋排程快取 (issue #360) ----------------------------------------
    # 不是 user-scoped - 全市場篩選結果不是個人資料，跟 FundamentalsCache/
    # ExchangeRateSnapshot 一樣全域共用。

    def moonshot_market_screen_cache(self) -> dict:
        rows = (
            self._db.query(MoonshotMarketScreenCache)
            .order_by(desc(MoonshotMarketScreenCache.score), MoonshotMarketScreenCache.symbol)
            .all()
        )
        if not rows:
            return {"results": [], "cached_at": None}
        return {
            "results": [
                {"symbol": r.symbol, "score": r.score, **json.loads(r.criteria_json)}
                for r in rows
            ],
            "cached_at": max(r.fetched_at for r in rows).isoformat(),
        }

    def replace_moonshot_market_screen_cache(self, results: list[dict]) -> None:
        """完全取代舊的快取（不是逐檔 upsert）- 候選名單本身每次重新整理都
        可能整批換掉，不是只有個別代號的數字變動，舊的「曾經符合」留著沒
        意義。criteria_json 欄位名稱沒改，但現在存的是 criteria 以外的
        所有欄位（含 name/sector/industry），用 symbol/score 以外的部分
        原樣塞進去，欄位來源加減不用再改這裡。"""
        self._db.query(MoonshotMarketScreenCache).delete()
        now = datetime.now(timezone.utc)
        for r in results:
            extra = {k: v for k, v in r.items() if k not in ("symbol", "score")}
            self._db.add(MoonshotMarketScreenCache(
                symbol=r["symbol"], score=r["score"],
                criteria_json=json.dumps(extra), fetched_at=now,
            ))
        self._db.commit()

    # --- price alerts (issue #18) ---------------------------------------------

    def price_alerts(self) -> list[dict]:
        rows = self._mine(PriceAlert).order_by(desc(PriceAlert.created_at)).all()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "target_price": r.target_price,
                "direction": r.direction,
                "triggered": r.triggered,
                "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
            }
            for r in rows
        ]

    def add_price_alert(self, symbol: str, target_price: float, direction: str) -> None:
        self._db.add(
            PriceAlert(
                user_id=self._user_id,
                symbol=symbol.upper(),
                target_price=target_price,
                direction=direction,
            )
        )
        self._db.commit()

    def delete_price_alert(self, alert_id: str) -> None:
        existing = self._mine(PriceAlert).filter(PriceAlert.id == alert_id).first()
        if existing:
            self._db.delete(existing)
            self._db.commit()

    # --- allocation drift alerts (issue #320) ----------------------------------

    def allocation_alerts(self) -> list[dict]:
        rows = self._mine(AllocationAlert).order_by(desc(AllocationAlert.created_at)).all()
        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "threshold": r.threshold,
                "triggered": r.triggered,
                "triggered_at": r.triggered_at.isoformat() if r.triggered_at else None,
            }
            for r in rows
        ]

    def add_allocation_alert(self, symbol: str, threshold: float) -> None:
        self._db.add(
            AllocationAlert(
                user_id=self._user_id,
                symbol=symbol.upper(),
                threshold=threshold,
            )
        )
        self._db.commit()

    def delete_allocation_alert(self, alert_id: str) -> None:
        existing = self._mine(AllocationAlert).filter(AllocationAlert.id == alert_id).first()
        if existing:
            self._db.delete(existing)
            self._db.commit()

    # --- liabilities (issue #326) -----------------------------------------------

    def liabilities(self) -> list[dict]:
        rows = self._mine(Liability).order_by(desc(Liability.created_at)).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "principal": r.principal,
                "annual_rate": r.annual_rate,
                "monthly_payment": r.monthly_payment,
                "start_date": r.start_date.isoformat(),
            }
            for r in rows
        ]

    def add_liability(self, name: str, principal: float, annual_rate: float, monthly_payment: float, start_date: date) -> None:
        self._db.add(
            Liability(
                user_id=self._user_id,
                name=name,
                principal=principal,
                annual_rate=annual_rate,
                monthly_payment=monthly_payment,
                start_date=start_date,
            )
        )
        self._db.commit()

    def delete_liability(self, liability_id: str) -> None:
        existing = self._mine(Liability).filter(Liability.id == liability_id).first()
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

    # --- FIRE settings ---------------------------------------------------------

    def fire_settings(self) -> FireSettings | None:
        return self._mine(FireSettings).first()

    def upsert_fire_settings(
        self, annual_expenses: float, swr: float,
        retirement_date: date | None = None, expected_real_return: float | None = None,
    ) -> None:
        existing = self._mine(FireSettings).first()
        if existing:
            existing.annual_expenses = annual_expenses
            existing.swr = swr
            existing.retirement_date = retirement_date
            existing.expected_real_return = expected_real_return
            existing.updated_at = datetime.now(timezone.utc)
        else:
            self._db.add(
                FireSettings(
                    user_id=self._user_id,
                    annual_expenses=annual_expenses,
                    swr=swr,
                    retirement_date=retirement_date,
                    expected_real_return=expected_real_return,
                )
            )
        self._db.commit()

    def delete_fire_settings(self) -> None:
        existing = self._mine(FireSettings).first()
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

    def register_fundamentals_symbol(self, symbol: str) -> bool:
        from app.infrastructure.fundamentals_cache import register_symbol

        inserted = register_symbol(self._db, symbol)
        self._db.commit()
        return inserted

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
