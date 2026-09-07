# StockOrbit — 開發流程

## 每一項工作都走：issue → branch → PR → merge

即使是單人專案，也**不要直接 push 到 `main`**。順序固定：

1. **先開 GitHub issue** — 描述需求／bug、做法、驗收條件。
   `gh issue create --title "..." --body "..."`
2. **從最新的 `main` 開 feature branch**：
   `git checkout main && git pull && git checkout -b <type>/<short-name>`
   （`type` 用 `feat` / `fix` / `chore` / `docs`）
3. **在 branch 上實作 + 測試**，commit 訊息結尾加：
   `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
4. **開 PR，內文第一行寫 `Closes #<issue>`**（GitHub 才會自動雙向連結，
   issue 頁面才看得到 "Linked pull requests"）：
   `gh pr create --title "..." --body "Closes #<n>\n\n..."`
5. **把 PR 連到 GitHub Project #3 並 assign 給 gino2013**：
   `gh project item-add 3 --owner gino2013 --url <PR-URL>`
   `gh pr edit <n> --add-assignee gino2013`
6. **squash merge 回 `main`，刪掉 branch**：
   `gh pr merge <n> --squash --delete-branch`
7. merge 後 `git checkout main && git pull && git fetch --prune`。

小修正（typo、一行 config）可以斟酌，但只要算得上一個「功能」或「bug 修正」
就走完整流程。判斷有疑慮時，走完整流程。

## 文件

- 每個功能／修正都要更新 `CHANGELOG.md`（依日期分組，附 commit hash）。
- 影響到使用者可見行為的，也要更新 `README.md` 的功能清單。
- 新的儀表板區塊要一併更新 `README.md` 的截圖（見 `scripts/seed_demo_data.py`）。

## 測試

- 沒有測試框架，就是 `assert` 為主的 `tests/test_*.py`，可逐一跑或一次跑全部。
- 非平凡的邏輯（分支、迴圈、解析、金錢／安全路徑）至少留一個會失敗的檢查。
- 跑任何會 import `app.main` / `app.infrastructure.db` 的臨時指令時，**一定要**
  帶一個丟棄式的 `DATABASE_URL`（例如 `sqlite:////tmp/x.db`），否則會 fallback
  到 `.env` 裡真正的 Neon 正式資料庫。

## 分層

`interface/` → `application/` → `domain/`；`infrastructure/` 只被 `interface`／
`application` 用。I/O（yfinance、爬蟲、DB）留在 `infrastructure/`，純計算留在
`domain/`。細節見 `README.md` 的「專案結構」。
