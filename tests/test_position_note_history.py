import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_DB = Path(tempfile.mkdtemp()) / "note_history_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["APP_SECRET_KEY"] = "x" * 40

from app.infrastructure.db import Base, SessionLocal, User, engine  # noqa: E402
from app.infrastructure.repositories import Repositories  # noqa: E402


def demo():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    db.add(User(id="u1", email="a@x.com", password_hash="h", is_owner=True))
    db.commit()
    db.close()

    with Repositories("u1") as repo:
        # every save appends a history row, current note keeps the latest
        repo.upsert_note("AAPL", "v1: 剛建倉")
        repo.upsert_note("AAPL", "v2: 加碼")
        repo.upsert_note("AAPL", "v3: 目標價調整")
        repo.upsert_note("MSFT", "only one version")

    with Repositories("u1") as repo:
        assert repo.notes()["AAPL"] == "v3: 目標價調整"  # current note = latest save

        history = repo.note_history()
        assert set(history.keys()) == {"AAPL", "MSFT"}

        aapl_versions = [h["note"] for h in history["AAPL"]]
        assert len(aapl_versions) == 3
        assert aapl_versions == ["v3: 目標價調整", "v2: 加碼", "v1: 剛建倉"]  # newest first
        assert len(history["MSFT"]) == 1

        # a save of an empty string (clearing the note) is still logged,
        # so the history shows exactly when a note was removed.
        repo.upsert_note("MSFT", "")

    with Repositories("u1") as repo:
        assert repo.notes()["MSFT"] == ""
        msft_history = repo.note_history()["MSFT"]
        assert len(msft_history) == 2
        assert msft_history[0]["note"] == ""


if __name__ == "__main__":
    demo()
    print("OK")
