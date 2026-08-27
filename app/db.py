import os
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, String, Text, create_engine
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
    # field names again — cost_basis/market_value/price map to its
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
    API (see issue #9) so it can never populate this itself — a scheduled
    GitHub Actions job (unaffected by that block) refreshes this table, and
    the dashboard falls back to it whenever a live fetch comes back empty.
    """

    __tablename__ = "fundamentals_cache"

    symbol = Column(String, primary_key=True)
    sector = Column(String)
    industry = Column(String)
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


def init_db():
    Base.metadata.create_all(engine)
