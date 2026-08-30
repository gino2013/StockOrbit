import hashlib
import os
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./stockorbit.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


def _user_id_col():
    """Tenancy FK. Nullable for now (multi-user step 2); step 4 makes it
    NOT NULL and folds it into the composite primary keys."""
    return Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )


class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"

    id = Column(String, primary_key=True, default=lambda: os.urandom(8).hex())
    user_id = _user_id_col()
    account_number = Column(String, nullable=False)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    cost_basis = Column(Float, default=0)
    market_value = Column(Float, default=0)
    price = Column(Float, default=0)
    # ponytail: raw item JSON kept as a fallback in case Firstrade changes
    # field names again - cost_basis/market_value/price map to its
    # cost/market_value/last keys as of the 2026-08-25 live test.
    raw_json = Column(Text)
    snapshot_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class TargetAllocation(Base):
    __tablename__ = "target_allocations"

    symbol = Column(String, primary_key=True)
    user_id = _user_id_col()
    target_weight = Column(Float, nullable=False)


class ExchangeRateSnapshot(Base):
    __tablename__ = "exchange_rate_snapshots"

    id = Column(String, primary_key=True, default=lambda: os.urandom(8).hex())
    pair = Column(String, nullable=False, default="USDTWD")
    rate = Column(Float, nullable=False)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class FundamentalsCache(Base):
    """Last-known-good yfinance fundamentals/earnings-date per symbol.

    Render's outbound IP gets a 401 Invalid Crumb from Yahoo's quoteSummary
    API (see issue #9) so it can never populate this itself - a scheduled
    GitHub Actions job (unaffected by that block) refreshes this table, and
    the dashboard falls back to it whenever a live fetch comes back empty.
    """

    __tablename__ = "fundamentals_cache"

    symbol = Column(String, primary_key=True)
    quoteType = Column(String)
    sector = Column(String)
    industry = Column(String)
    marketCap = Column(Float)
    trailingPE = Column(Float)
    forwardPE = Column(Float)
    pegRatio = Column(Float)
    returnOnEquity = Column(Float)
    profitMargins = Column(Float)
    revenueGrowth = Column(Float)
    earningsGrowth = Column(Float)
    debtToEquity = Column(Float)
    beta = Column(Float)
    fiftyTwoWeekLow = Column(Float)
    fiftyTwoWeekHigh = Column(Float)
    targetMeanPrice = Column(Float)
    recommendationKey = Column(String)
    next_earnings_date = Column(String)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Transaction(Base):
    """Raw account history from Firstrade's get_account_history() - trades,
    dividends, interest, deposits, etc. Append-only, like PositionSnapshot.

    Firstrade's API gives no transaction id, so `id` is a hash of the fields
    that make a row unique, letting repeated fetches of overlapping date
    ranges upsert instead of duplicating (see fetch_transactions()).
    """

    __tablename__ = "transactions"

    id = Column(String, primary_key=True)
    user_id = _user_id_col()
    account_number = Column(String, nullable=False)
    symbol = Column(String, index=True)
    trans_type = Column(String, nullable=False, index=True)  # BOUGHT/SOLD/DIV/INTEREST/DEPOSIT/OTHER
    report_date = Column(Date, nullable=False, index=True)
    quantity = Column(Float, default=0)
    trade_price = Column(Float, default=0)
    amount = Column(Float, default=0)  # signed cash flow: negative = cash out (buy), positive = cash in
    description = Column(Text)
    raw_json = Column(Text)
    fetched_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    @staticmethod
    def make_id(row: dict) -> str:
        key = "|".join(
            str(row.get(k, ""))
            for k in (
                "account_number", "report_date", "trans_type", "symbol",
                "quantity", "trade_price", "amount", "description",
            )
        )
        return hashlib.sha256(key.encode()).hexdigest()[:32]


class PositionNote(Base):
    """Freeform note per symbol - why you bought it, target price, whatever
    you want to remember later. Upserted by symbol, no history kept."""

    __tablename__ = "position_notes"

    symbol = Column(String, primary_key=True)
    user_id = _user_id_col()
    note = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class TransactionNote(Base):
    """Freeform note bound to a single Transaction row (its content-hash id,
    see Transaction.make_id) - why you made that specific buy/sell, what
    you were thinking at the time. Unlike PositionNote (one note per
    symbol), this is per trade event, so you can look back at each
    individual decision later. Upserted by transaction_id, no history kept."""

    __tablename__ = "transaction_notes"

    transaction_id = Column(String, primary_key=True)
    user_id = _user_id_col()
    note = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class InvestmentGoal(Base):
    """Single long-term target (amount + date) to track progress against.
    Singleton row keyed by a fixed id, same upsert-by-key shape as
    PositionNote - only one goal at a time, no history kept."""

    __tablename__ = "investment_goals"

    id = Column(String, primary_key=True, default="default")
    user_id = _user_id_col()
    target_amount = Column(Float, nullable=False)
    target_date = Column(Date, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class User(Base):
    """An account. Data in every other user-scoped table is keyed by user_id.

    `session_version` is bumped to invalidate all of a user's signed session
    cookies at once (password reset, "log out everywhere"). `is_owner` marks
    the single account named by the OWNER_EMAIL env var, which may fall back
    to the FT_* env credentials for Firstrade sync (see firstrade_client).
    """

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    email = Column(String, nullable=False, unique=True, index=True)  # stored lower-cased
    password_hash = Column(String, nullable=False)
    email_verified = Column(Boolean, nullable=False, default=False)
    session_version = Column(Integer, nullable=False, default=1)
    is_owner = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class FirestradeCredential(Base):
    """A user's Firstrade login, each field Fernet-encrypted with
    FT_CREDENTIAL_KEY (see app.infrastructure.crypto). One row per user.

    Storing brokerage credentials is a deliberate, high-risk choice: a DB
    dump plus the key is full account takeover. The key lives only in the
    environment, never in this table or git.
    """

    __tablename__ = "firstrade_credentials"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    username_enc = Column(Text, nullable=False)
    password_enc = Column(Text, nullable=False)
    mfa_secret_enc = Column(Text, nullable=False, default="")
    last_sync_at = Column(DateTime)
    last_sync_error = Column(Text)


def init_db():
    Base.metadata.create_all(engine)
