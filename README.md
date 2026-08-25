# StockOrbit

一個個人用的 Firstrade 投資組合追蹤網站：自動同步持股、依配置給出建議、對任意再平衡策略跑歷史回測，全部透過一個零建置流程的網頁儀表板操作。

## 畫面

以下截圖用假資料（不是真實持股）示範各區塊，深色模式。

### 總覽

![總覽：頂部統計卡片](docs/screenshot-overview.png)

一進頁面就看到總市值、未實現損益、報酬率、持股檔數。

### 持股與配置

![持股與配置：持股表格、配置圓餅圖、建議、近期市場動態、目標配置](docs/screenshot-holdings.png)

- 左邊是目前持股表格，每檔股票的「目前佔比」跟「目標佔比」並排，偏離超過 5% 會標紅，跟右下角的「目標配置」是同一份資料、改了會一起動
- 右上「建議」：依集中度跟配置偏離規則列出的提醒，不是投資建議
- 「近期市場動態」：按查詢會抓每檔持股最近的大漲大跌（規則判斷）跟最新新聞標題（原文列出，不做利多利空判斷）
- 「目標配置」：可以新增/編輯/刪除每檔的目標權重，權重總和要是 100%

### 持股歷史走勢

![持股歷史走勢：報酬率比較圖、最大回撤與波動度分析、重大波動日標註](docs/screenshot-history.png)

用「目前」的股數回推過去市值，可選每日／每月／每季／每年顯示。填「比較標的」（可以是單一標的，或像 `QQQ:0.6,VOO:0.4` 這樣的加權組合）會切換成報酬率比較，並算出最大回撤跟年化波動度的比較文字。圖上的直線標出單日 ±3% 以上的「重大波動日」——只標出哪天波動大，沒辦法自動回溯當天的新聞原因（yfinance 的新聞功能只保留最新報導，查不到歷史上某一天發生了什麼事）。

### 再平衡策略回測

![再平衡策略回測：投組表現走勢圖、再平衡日與最大回撤標註](docs/screenshot-backtest.png)

用「目標配置」的權重模擬過去表現，可選再平衡頻率，比較基準預設 SPY、同樣支援自訂加權組合。圖上虛線標出每次再平衡發生的日期，陰影區塊是最大回撤發生的區間。不含手續費/稅金，僅供參考，不是真實交易模擬。

## 功能

- **持股同步**：透過非官方 Firstrade API 自動登入（支援 TOTP 兩步驟驗證），抓取目前帳戶持倉並存成歷史快照
- **配置建議**：依目前持股計算集中度風險，並比對自訂的目標配置，列出偏離提醒
- **持股歷史走勢**：用「目前」的股數回推過去市值，可選每日／每月／每季／每年顯示；也可以填一個比較標的或加權組合（如 `QQQ:0.6,VOO:0.4`），看你的組合對比大盤或任意基準的報酬率，並標出單日大漲大跌的節點
- **再平衡策略回測**：用目標配置模擬過去表現，可選再平衡頻率（不再平衡／每月／每季／每年），比較基準同樣支援自訂加權組合；圖表會標出每次再平衡發生的日期跟最大回撤區間
- **近期市場動態**：規則判斷的大漲大跌提醒，加上各檔最新新聞標題（原文列出，不做利多利空判斷）
- **儀表板**：單頁網頁介面，含深色模式，資料存在本機（開發）或 Postgres（正式環境）

## 技術棧

- **後端**：FastAPI + SQLAlchemy（開發用 SQLite，正式環境用 Postgres）
- **前端**：Jinja2 樣板 + [daisyUI](https://daisyui.com/)（Tailwind CSS 元件庫） + [Chart.js](https://www.chartjs.org/)，全部透過 CDN 引入，沒有 npm 建置流程
- **市場資料**：[yfinance](https://github.com/ranaroussi/yfinance)
- **持股資料來源**：[firstrade-api](https://github.com/MaxxRK/firstrade-api)（非官方，reverse-engineered）

## 專案結構

```
app/
  main.py              # FastAPI 路由
  db.py                # SQLAlchemy models
  firstrade_client.py  # Firstrade 登入與持股抓取
  advice.py            # 配置建議邏輯
  backtest.py          # 再平衡回測引擎
  holdings_history.py  # 持股歷史走勢／加權組合比較
  templates/
    dashboard.html      # 唯一的前端頁面
tests/                 # 純函式的 assert-based 自我檢查（無需啟動伺服器）
render.yaml            # Render 部署設定
```

## 本機開發

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # 填入下面的環境變數
.venv/bin/uvicorn app.main:app --reload
```

打開 http://127.0.0.1:8000。

### 環境變數（`.env`）

| 變數 | 說明 |
|---|---|
| `FT_USERNAME` / `FT_PASSWORD` | Firstrade 登入帳密 |
| `FT_MFA_SECRET` | 2FA 的 TOTP 密鑰（**不是**簡訊/email 收到的驗證碼，也不是備用代碼）。在 Firstrade 網站設定「驗證應用程式」2FA 時，QR code 旁邊「無法掃描/手動輸入」連結會顯示這組字串。留空的話，帳號若開了 2FA，自動抓取會直接失敗 |
| `DATABASE_URL` | 資料庫連線字串，本機預設 `sqlite:///./stockorbit.db`，正式環境填 Postgres 連線字串 |

`.env` 已加進 `.gitignore`，不會被提交。

## 部署（Render + Neon）

1. 在 [Neon](https://neon.tech) 建一個免費的 Postgres，拿到連線字串
2. 在 [Render](https://render.com) 選 **New → Blueprint**，連結這個 GitHub repo，Render 會讀 `render.yaml` 自動建立服務
3. 在 Render 的環境變數畫面填入 `FT_USERNAME` / `FT_PASSWORD` / `FT_MFA_SECRET` / `DATABASE_URL`（`render.yaml` 裡標了 `sync: false`，所以這幾個要手動填，不會被推進版控）

## 測試

沒有用測試框架，就是幾個 `assert` 為主的檔案，可以直接跑：

```bash
.venv/bin/python tests/test_advice.py
.venv/bin/python tests/test_backtest.py
.venv/bin/python tests/test_holdings_history.py
```

## 注意事項

- `firstrade-api` 是**非官方**套件，Firstrade 隨時可能改介面導致它失效
- 回測沒有計入手續費、稅金、滑價，僅供研究參考，不是真實交易模擬
- 這不是投資建議工具，「建議」區塊只是簡單的集中度／配置偏離規則，不構成任何財務建議
