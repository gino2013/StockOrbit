"""Postgres' `alembic_version.version_num` column is VARCHAR(32) by default
(Alembic never widens it). A revision id over 32 chars passes every local
SQLite test - SQLite doesn't enforce column length - then dies on the real
Neon DB with `StringDataRightTruncation`, transactionally rolling back the
whole migration and taking the app down (see 0008's first two deploys).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parent.parent


def demo():
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    script = ScriptDirectory.from_config(cfg)

    too_long = [rev.revision for rev in script.walk_revisions() if len(rev.revision) > 32]
    assert not too_long, f"revision id(s) over 32 chars (breaks on Postgres): {too_long}"


if __name__ == "__main__":
    demo()
    print("OK")
