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
        # Sorted by score desc, then by rank (insertion order) for ties - NOT
        # symbol (issue #364: that silently broke the "依市值排序" promise,
        # since replace_moonshot_market_screen_cache() is called with results
        # already in market-cap-desc order).
        assert [r["symbol"] for r in cached["results"]] == ["ZZZ", "AAA", "MMM"]
        assert cached["results"][0]["criteria"] == [{"key": "profitability", "value": 0.5, "passed": True}]

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

    # Regression for issue #364: among same-score rows, the cache must
    # follow the order results were written in, not re-derive its own
    # (e.g. alphabetical) order. Flip two tied symbols' input order and
    # confirm the read flips too.
    with Repositories("owner1") as repo:
        repo.replace_moonshot_market_screen_cache([
            {"symbol": "ZZZ", "score": 4, "criteria": []},
            {"symbol": "AAA", "score": 4, "criteria": []},
        ])
        assert [r["symbol"] for r in repo.moonshot_market_screen_cache()["results"]] == ["ZZZ", "AAA"]
        repo.replace_moonshot_market_screen_cache([
            {"symbol": "AAA", "score": 4, "criteria": []},
            {"symbol": "ZZZ", "score": 4, "criteria": []},
        ])
        assert [r["symbol"] for r in repo.moonshot_market_screen_cache()["results"]] == ["AAA", "ZZZ"]


if __name__ == "__main__":
    demo()
    print("OK")
