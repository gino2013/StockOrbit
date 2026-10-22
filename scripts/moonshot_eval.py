"""千倍股評估（issue #408）的兩個步驟，給 Claude Code 的 /moonshot-eval skill
用（ADR 0002）：

    python scripts/moonshot_eval.py fetch NVDA > inputs.json
    python scripts/moonshot_eval.py save inputs.json judgment.json --model claude-opus-5-5

fetch 把評估用的數據印成 JSON（基本資料抓不到就 exit 1，不評估）；save 用
同一份 inputs 驗證判斷、算總分跟資料信心度，通過才寫進 moonshot_evaluation，
沒通過就列出全部錯誤 exit 1、什麼都不寫。save 會讀 .env 的 DATABASE_URL，
也就是正式 DB - 這是刻意的，測試時自己帶一個丟棄式的 DATABASE_URL。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.application.moonshot_eval import gather_inputs, save_evaluation  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("symbol")
    p_save = sub.add_parser("save")
    p_save.add_argument("inputs")
    p_save.add_argument("judgment")
    p_save.add_argument("--model", required=True)
    args = parser.parse_args()

    try:
        if args.cmd == "fetch":
            print(json.dumps(gather_inputs(args.symbol), ensure_ascii=False, indent=2))
            return
        inputs = json.loads(Path(args.inputs).read_text())
        judgment = json.loads(Path(args.judgment).read_text())
        from app.infrastructure.db import init_db
        from app.infrastructure.repositories import Repositories

        init_db()
        with Repositories() as repo:
            evaluation = save_evaluation(repo, inputs, judgment, args.model)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    print(f"已存：{evaluation['ticker']} 總分 {evaluation['total_score']}/20，資料信心度 {evaluation['data_confidence']}")


if __name__ == "__main__":
    main()
