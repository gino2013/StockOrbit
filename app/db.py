import hashlib
import os
from datetime import date, datetime, timezone

from sqlalchemy import Column, Date, DateTime, Float, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./stockorbit.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class PositionSnapshot(Base):
    __tablename__ = "position_snapshots"

    id = Column(String, primary_key=True, default=lambda: os.urandom(8).hex())
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
    note = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class InvestmentGoal(Base):
    """Single long-term target (amount + date) to track progress against.
    Singleton row keyed by a fixed id, same upsert-by-key shape as
    PositionNote - only one goal at a time, no history kept."""

    __tablename__ = "investment_goals"

    id = Column(String, primary_key=True, default="default")
    target_amount = Column(Float, nullable=False)
    target_date = Column(Date, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(engine)
