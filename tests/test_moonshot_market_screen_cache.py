import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "moonshot_cache_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "x" * 40

from app.infrastructure.db import Base, User, engine  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402


def demo():
    Base.metadata.create_all(engine)
    from app.infrastructure.db import SessionLocal

    db = SessionLocal()
    db.add(User(id="owner1", email="owner@x.com", password_hash="h", is_owner=True))
    db.commit()
    db.close()

    with Repositories("owner1") as repo:
        # Empty cache: a distinct state from "has results", not a crash.
        empty = repo.moonshot_market_screen_cache()
        assert empty == {"results": [], "cached_at": None}

        results = [
            {"symbol": "ZZZ", "score": 4, "criteria": [{"key": "profitability", "value": 0.5, "passed": True}]},
            {"symbol": "AAA", "score": 4, "criteria": [{"key": "profitability", "value": 0.6, "passed": True}]},
            {"symbol": "MMM", "score": 2, "criteria": [{"key": "profitability", "value": 0.1, "passed": False}]},
        ]
        repo.replace_moonshot_market_screen_cache(results)

    with Repositories("owner1") as repo:
        cached = repo.moonshot_market_screen_cache()
        assert cached["cached_at"] is not None
        # Sorted by score desc, then symbol asc for ties - same order rank_moonshot_candidates uses.
        assert [r["symbol"] for r in cached["results"]] == ["AAA", "ZZZ", "MMM"]
        assert cached["results"][0]["criteria"] == [{"key": "profitability", "value": 0.6, "passed": True}]

        # Not user-scoped: a second user's Repositories sees the same global cache.
    with Repositories() as owner_repo:
        assert len(owner_repo.moonshot_market_screen_cache()["results"]) == 3

    # A later refresh wholesale-replaces, not upserts - stale rows from the
    # previous run (e.g. MMM, which no longer qualifies) must not linger.
    with Repositories("owner1") as repo:
        repo.replace_moonshot_market_screen_cache([
            {"symbol": "BBB", "score": 3, "criteria": []},
        ])
        replaced = repo.moonshot_market_screen_cache()
        assert [r["symbol"] for r in replaced["results"]] == ["BBB"]

    # name/sector/industry round-trip through the cache too (not just
    # criteria) - the UI shows a company blurb on every query, including
    # the cache-fallback path, so these can't be dropped on write.
    with Repositories("owner1") as repo:
        repo.replace_moonshot_market_screen_cache([
            {"symbol": "CCC", "score": 4, "criteria": [], "name": "Ccc Corp", "sector": "Technology", "industry": "Software"},
        ])
        with_meta = repo.moonshot_market_screen_cache()["results"][0]
        assert with_meta["name"] == "Ccc Corp"
        assert with_meta["sector"] == "Technology"
        assert with_meta["industry"] == "Software"


if __name__ == "__main__":
    demo()
    print("OK")
