# Changelog

專案的詳細修改紀錄，依日期分組、時間順序排列。每筆附上 commit hash，可以用 `git show <hash>` 查完整 diff。

摘要版功能總覽請看 [README](README.md#功能)。

## 2026-09-02

- `4cc08b8` 新增 FIRE 進度（4% 法則，issue #213，見 epic #212）：輸入年支出跟安全提領率（預設 4%）算出 FIRE 數字（年支出 ÷ 提領率）、目前進度、還差多少、以目前 XIRR 推估的達成日期。新表 `fire_settings`（比照 `investment_goals` 的「每人一列」模式），新 partial `sections/fire.html` 擺在「目標達成進度追蹤」之前，AJAX 自載
- `2511e93` 新增 Coast FIRE 檢查（issue #214）：`fire_settings` 加兩個選填欄位（退休日期、預期實質報酬率），算「今天起不再投入，靠複利能否長到 FIRE 數字」——今天需要有多少才能躺平、還差多少、退休時的預估市值。併入既有 FIRE 進度表單跟 `/api/fire`，兩個欄位要一起填或都不填

## 2026-09-01

- `74fcc62` 修正時間戳記顯示成原始 UTC、跟台北時區（UTC+8）差 8 小時的問題（issue #205）：資料庫存的是 UTC，但存進去後 tzinfo 會被拿掉，範本直接 `.strftime()` 等於把 UTC 時鐘數字原封不動印出來；新增 `_to_taipei()`（標準庫 `zoneinfo`）轉換工具，套用到持股筆記歷史版本、設定頁 Firstrade 最後同步時間、基本面/風險表格的快取日期
- `84a6156` 持股筆記新增歷史版本（issue #201）：每次儲存除了更新目前顯示的筆記，也額外記一筆帶時間戳記的版本（新表 `position_note_history`），筆記下方新增「歷史版本」摺疊列表由新到舊列出；同時「接下來預測」長期欄位數字過於誇張時（累積變動超過 +1000%）加上 ⚠️ 警告標示跟說明文字（issue #202）——數學沒有錯，但短窗口 XIRR 複利拉遠本來就容易失真，這只是提醒
- `805ef74` **修正真實帳戶資料外洩到公開截圖的問題**（issue #195）：`scripts/seed_demo_data.py` 的 `TODAY` 常數是寫死的日期，過期後種出來的「拋棄式」demo DB 一開機就會被判定持股快照過舊，靜默觸發 dashboard 的自動 Firstrade 刷新；因為本機測試帳號沒有個人 Firstrade 憑證，會 fallback 到 `.env` 裡的真實帳密，實際登入真實帳戶並把真實資料寫進「拋棄式」的本機測試 DB。確認 `docs/screenshot-pace-projection.png`（PR #145）曾經含有真實帳戶數字且已 push 到公開 repo；已重新產生純假資料版本覆蓋掉。`TODAY` 改成 `date.today()` 修掉根因，並在腳本加上明確警告
- 多使用者化補強：新增 `REQUIRE_EMAIL_VERIFICATION` 環境變數（預設 `true`）。設成 `false` 時，Firstrade 連結表單跟 CSV 匯入不再檢查 `email_verified`——給沒有要接 SMTP、又想讓其他人直接能用的部署（代價是少了開放註冊的濫用防線）。同時修掉一個誤導訊息：`SMTP_HOST` 沒設時，「重寄驗證信」不再假裝「已寄出」，改回 503 + 「站台尚未設定寄信服務」；`/forgot` 也改成老實說無法用 email 重設（不洩漏帳號是否存在）。`REQUIRE_EMAIL_VERIFICATION=false` 時「重寄驗證信」按鈕與「尚未驗證信箱」提示都收起來。新增 `tests/test_email_verification_toggle.py`
- `38d8f7c` 登入／註冊頁密碼欄位加上顯示/隱藏切換按鈕（issue #185）：眼睛 icon 點擊切換 type=password ↔ type=text，icon 跟著切換張開/劃掉樣式
- `bc25a87` 把 `dashboard.html`（3134 行單一檔案，27 個功能區塊塞在同一個近 2000 行的 `<script>` 標籤）拆成模組化的 Jinja partials（issue #182）：每個區塊自己的檔案（HTML + 對應的 JS 放一起），跨區塊共用的工具函式（escapeHtml、fmtPct 系列、makeSortable、attachTickerAutocomplete 等）集中在 `sections/_shared.html` 最先載入；純搬移不改邏輯，維持零建置流程。過程中抓到並修掉拆分本身引入的一個 regression：日期欄位預設值腳本被排到所有區塊最後面，但持股歷史走勢／再平衡策略回測各自的自動查詢在載入時就先觸發，required 日期欄位還沒填值就送出表單，被瀏覽器原生驗證靜默擋下（不會噴錯誤，兩個區塊進站直接是空的）；改成兩者的自動查詢都延後到 `DOMContentLoaded` 才觸發解決
- `f7db032` 「重新抓取持股」reload icon 拿掉深黑色按鈕外框（issue #179），改成跟旁邊深色模式切換按鈕一樣的 ghost 風格
- `abacde3` 修正閒置一段時間後回到網站偶爾顯示 Internal Server Error 的問題（issue #176）：正式環境用的 Neon Postgres 會在閒置後把連線關掉，SQLAlchemy engine 沒設 `pool_pre_ping=True` 的情況下，連線池會把已失效的連線借給下一個請求、第一個查詢就直接丟未捕捉例外變成 500；加上 `pool_pre_ping=True` 後每次借出連線前會先用輕量 SELECT 1 測試，失效就自動重連
- `1662b81` 持股筆記儲存改成 AJAX（issue #173）：原本是傳統 form POST，存檔後整頁重新整理會重新觸發首頁所有區塊（含多個 yfinance 即時請求），改一筆筆記等很久；改成跟交易紀錄筆記一樣的 `fetch()` 局部更新，儲存變瞬間完成
- `8df5684` 頁首「重新抓取持股」按鈕改成黑白 reload icon（issue #171）

## 2026-08-31

- 多使用者化第 7 步：CSV 匯入，不需要交出 Firstrade 帳密的替代資料來源（scraper 掛掉時的備援）。新增 `app/infrastructure/csv_import.py`：把使用者上傳的 CSV 解析成跟 `fetch_positions`／`fetch_transactions` 一樣的 dict 形狀，直接餵給 `repo.save_refresh`。持股欄位 `symbol`／`quantity` 必填，`avg_cost`／`cost_basis`／`price`／`market_value`／`account_number` 選填；交易欄位 `date`／`type` 必填，`type` 接受 buy/sell/dividend/interest/deposit，`amount` 留空時買賣自動用 `quantity × price` 帶正負推算。欄名大小寫與空白不拘，對不上會回報是哪一列哪個欄位。日期接受 `YYYY-MM-DD` 與 `MM/DD/YYYY`。`/settings/import/positions`、`/settings/import/transactions` 兩個 multipart 路由，2MB 上限，擋在 `email_verified` 後面；交易用內容雜湊去重，重複上傳同一份不會重複。「設定」頁新增匯入區塊、首頁空狀態文案補上「或直接上傳 CSV」。新增 `tests/test_csv_import.py`（解析各種正常／錯誤情境 + 經 `save_refresh` round-trip）
- 多使用者化第 6 步：開放註冊的安全性補強。新增 `app/infrastructure/mailer.py`（stdlib `smtplib`，不加新套件；`SMTP_HOST` 沒設時改成把信件內容寫進 log，本機／還沒接寄信服務時註冊不會卡住）。註冊後寄信箱驗證信（`/verify?token=`，15 分鐘有效，用 `itsdangerous` 簽章 + purpose salt 防止驗證連結被當重設連結用）；「設定」頁顯示驗證狀態並可「重寄驗證信」。新增忘記密碼流程（`/forgot` → 寄信 → `/reset?token=`），重設成功會 bump `session_version` 讓所有既有 session 失效。`/login`／`/register`／`/forgot` 加上每 IP 的簡易滑動視窗限流（in-process，重啟重置，`deque` 幾行搞定不加 `slowapi`）。新增 `/terms`、`/privacy` 靜態頁，從註冊頁連過去。README 補上「安全性與多使用者風險」段落與 `SMTP_*` 環境變數說明。新增 `tests/test_mailer.py`、`tests/test_email_flows.py`
- 多使用者化第 5 步：`/settings` 頁（帳號資訊、變更密碼、Firstrade 連結、刪除帳號）。Firstrade 帳密用 `FT_CREDENTIAL_KEY` 加密存進 `firstrade_credentials`，只顯示「已連結・最後同步時間／錯誤訊息」，密碼欄位只寫不讀。`_login()` 改吃可選的 `FtCreds`：擁有者沒存帳密時退回 env（`FT_USERNAME`/`PASSWORD`/`MFA_SECRET`），其他使用者要先在設定頁連結才能同步；`/api/refresh` 因此開放給已連結帳密的一般使用者，並加上每人 10 分鐘節流（用 `last_sync_at`）。首頁自動同步比照辦理（擁有者或已連結者），第一次連結後不用等 30 分鐘過期就會馬上抓一次；新增「還沒有資料」空狀態導引到設定頁。Firstrade 表單擋在 `email_verified` 後面（信箱驗證還沒做，目前等於只有擁有者能用，故意保守）。變更密碼會讓其他裝置的登入 session 失效（bump `session_version`）但這個裝置維持登入；刪除帳號需要打字輸入自己的 email 確認，硬刪 8 張表裡屬於這個使用者的所有資料列
- `9405100` 頁首右側控制項排序調整（issue #168）：改成「匯出CSV、匯出PDF、匯出交易紀錄、重新抓取持股、深色模式圖示、信箱、登出」，把跟使用者身分相關的兩個項目（深色模式切換、信箱）移到緊鄰登出按鈕左邊
- `cf5e987` UI 修正一輪（issue #165）：「健康度總覽」nav 標籤還原成「持股健康度總覽」；頁首跟側邊欄的 StockOrbit icon／標題都改成可以點回首頁；側邊欄標題文字太淡沒加粗，拿掉 daisyUI menu-title 預設樣式改成粗體亮白；修正深色/淺色模式切換很慢的問題——原本每次切換都整頁 `location.reload()`，這頁面一堆區塊會在載入時自動打 yfinance API，改成純前端切換 `data-theme`，瞬間完成不用重新整理
- `57a612f` 側邊選單標籤字數落差太大（4~9 字），統一精簡成 4~7 字（issue #161），拿掉跟分組/相鄰標籤重複的「持股」二字；順手修掉 `scripts/seed_demo_data.py` 還在傳已經被 migration 0004 拿掉的 `InvestmentGoal.id` 參數、每次跑都會炸掉的問題
- `2557ae8` README「為什麼這樣分層」改寫成較正式的用詞（拿掉「CP 值」、「一面牆」等口語表達），順便把全文剩下的破折號（——/—）都改成單一連字號 `-`，維持跟站內其他地方一致的用字規則（表格分隔線 `|---|` 跟指令列的 `--reload` 是語法本身，不受影響）
- `1fd4b97` 「定投高點回本風險」新增「買到熊市爛點的機率」（issue #154）：整段查詢區間內隨機挑一天買進，落在上面列出的熊市崩跌區間內的機率（區間總天數 / 整段歷史總天數）
- `d8d64dc` 登入／註冊頁標題加上 StockOrbit 柴犬 logo（重用 dashboard.html 頁首已內嵌的同一張 base64 圖片，縮小成 8x8）
- `45c131e` 補上「接下來預測」跟「定投高點回本風險」的 README 截圖跟說明（兩個功能上線時漏掉沒更新 README），順便更新功能摘要清單、更新紀錄、專案結構模組列表
- 多使用者化第 4 步：收緊 tenancy migration（`0004`）——`user_id` 改 NOT NULL，5 張表的主鍵改成複合鍵（`target_allocations`/`position_notes`：`(user_id, symbol)`；`transaction_notes`：`(user_id, transaction_id)`；`transactions`：`(user_id, id)`），讓不同使用者可以持有同一個標的代號/交易筆記而不會撞鍵；`investment_goals` 拿掉獨立的 `id` 欄位，改用 `user_id` 直接當主鍵。`position_snapshots` 維持原本的 `id` 單獨主鍵不變。SQLite／PostgreSQL 都支援（PostgreSQL 分支動態查詢既有主鍵約束名稱，不寫死假設）。新增 `tests/test_migration_0004.py`，含「Render 現況」情境驗證：既有資料在 migration 後完整保留並正確歸戶
- 修正 owner 帳號登不進去的問題：`OWNER_EMAIL`/`OWNER_INITIAL_PASSWORD` 設定之前就先部署過的話，`ensure_owner()` 會用內建預設值（`owner@localhost` / `owner`）建一個佔位 owner 帳號並寫進資料庫；之後補設定這兩個環境變數重新部署，程式只會把既有 owner 那筆的 `is_owner` 繼續設成 True，不會更新它的 email/密碼，導致「明明設定了卻登不進去、密碼其實是舊的預設值」。改成：找不到 email 對應的使用者、但已有一筆 `is_owner=True` 的佔位帳號時，把該筆的 email/密碼改成現在設定的值（同一筆資料，不會產生重複帳號）；一旦改好，之後開機 email 直接對得上，不會再被動到，之後真的改密碼也不會被蓋回去
- 多使用者化第 3 步：新增 email + 密碼登入（`/login` `/register` `/logout` + 樣板），中介層擋掉未登入的請求（`/api/*` 回 401、其他轉 `/login`）。首頁跟所有 `/api/*` 現在都綁在使用者身上（透過 request ContextVar → `Repositories()` 自動按使用者隔離，不用改 40 個路由簽章）。首頁 header 顯示 email + 登出；非擁有者看到「連結 Firstrade 開發中」空狀態；`/api/refresh` 只開放給擁有者。實測兩個帳號 HTTP 層完全隔離
- `87c95c9` 全系統 bug 稽核修正三個問題（issue #148）：分析師評等欄位 Yahoo 回傳字串 "none" 時被誤當成真評等顯示（用真實資料重現，IONQ）；大盤下跌情境模擬對算不出 Beta 的標的靜默當成 beta=0、低估跌幅卻沒有提示，現在會揭露哪些標的被排除；配息月曆「本月」預測沒有排除已發放過的股利，同標的本月已領過的股利可能又被列成即將發放
- 修正正式環境登入一律 500 的問題：Render 免費方案沒有 Shell，手動跑 `alembic upgrade head`這條路走不通，改成 app 開機時自動跑 migration（`run_pending_migrations()`）；沒有 `alembic_version` 記錄的資料庫會先推斷目前的表結構對應到哪個版本再補跑剩下的，處理「`users`/`firstrade_credentials` 表已被舊版 `create_all()` 建出來、但 6 張表還缺 `user_id`」這種卡在中間的真實情境，既有資料保留並回填給 owner，不會被清空。另外 `APP_SECRET_KEY` 沒設 / DB 結構跟現在的 model 對不上時，改成開機當下就在 log 報清楚錯誤（`check_app_secret_key()` / `check_schema_matches_models()`），不再是點登入才跳出一片空白的 Internal Server Error

## 2026-08-30

- `bec6ad4` 「定投高點回本風險」新增 3個月/半年/1年/2年 門檻快選按鈕（issue #136），點下去直接帶入對應天數重新查詢，自訂天數欄位留給更長的門檻用；核心邏輯（issue #122）不變，純前端 UX 改善
- 多使用者化第 1 步（見 `docs/multi-user-architecture.md`）：新增 `users` / `firstrade_credentials` model、`app/interface/auth.py`（bcrypt 密碼雜湊 + itsdangerous 簽名 session cookie）、`app/infrastructure/crypto.py`（Fernet 加密 Firstrade 憑證），導入 Alembic（`0001_baseline` 基準線 + `0002_users_creds`）。純基礎建設，還沒接進任何路由
- 多使用者化第 2 步：6 張使用者資料表加上 `user_id`（nullable + index，migration `0003`），從 `OWNER_EMAIL` 建立 owner 帳號並把既有資料全部歸戶給它；`Repositories` 改成 `Repositories(user_id)`，每個查詢都按使用者隔離（`user_id=None` 暫時解析成 owner，第 3 步才由 `current_user` 帶入）。新增 `tests/test_repositories_tenancy.py`。仍未擋登入、無行為改動
- `196996e` 「定投高點回本風險」新增折線圖（issue #140）：完整歷史股價圖上把每個符合門檻的熊市區間淺紅底標出、高低點各標一個紅點，滑鼠移過去 tooltip 顯示細節；表格「花費時間」欄位依嚴重程度上色（<3個月綠、3個月-1年黃、1-2年紅、2年以上紅底粗體）；順便修掉 12 個月會誤顯示成「X 年 12 個月」沒進位成「X+1 年」的 bug

## 2026-08-29

大量新增功能，每個功能都走 feature branch → PR → squash merge 流程：

- `d5d8507` 配置歷史走勢改成每天只取最後一筆快照畫一個點，不再是每次刷新都新增一個點
- `650f606` 修正複利曲線圖表 hover 不會顯示數字的 bug
- `7fc1741` 把基本面/財報日/新聞等逐檔序列的 yfinance 請求改成並行抓取，明顯縮短查詢時間（3-5倍）
- `6689e01` 修正持股歷史走勢／再平衡回測圖表 hover tooltip 需要多次嘗試才會顯示的 bug
- `e63cee7` `98ce48b` 新增「個股複利體質檢查清單」（issue #36）：獲利能力、財務體質、成長性、規模、歷史長度、歷史複利是否成立等客觀檢查，不給總分
- `9c44559` `b6d6c83` 新增「持股相關性矩陣」（issue #45）：近 1 年每日報酬率皮爾森相關係數，顏色矩陣呈現
- `5346fb0` `dfe4b48` 新增「貝塔調整建議」（issue #46）：風險平價簡化版，1/波動度加權
- `33bf08c` `abfa83e` 新增「情境模擬」（issue #47）：輸入假設大盤跌幅，用貝塔粗算組合估計跌幅
- `735880a` `419b21f` 新增「匯出 PDF」（issue #48）：瀏覽器列印 + 專用列印樣式
- `e51f7d5` `8dcfce1` 新增「匯出交易紀錄」CSV（issue #49）：完整交易紀錄 + 已實現損益明細
- `697f51d` `df45371` `6fcfd28` `cfb2dda` 新增「定期定額比較」（issue #50）：DCA vs 一次投入，後續加上多條比較標的、半年頻率、多筆投入方案比較
- `c15cae3` `2c38e1f` 新增「股利再投入試算」（issue #62）：DRIP vs 領出現金的長期複利差異
- `cadd6b6` `77fc791` 新增「稅務效率分析」（issue #63）：未實現虧損部位的節稅候選估算
- `897a045` `120ee50` 新增「持股集中度歷史走勢」（issue #64）：HHI 指數跟最大單一持股佔比走勢
- `af82546` `a66573c` 新增「配息月曆」（issue #65）：依歷史股利月份規律推算未來 12 個月配息
- `833a141` `9dc8436` 新增「目標達成進度追蹤」（issue #66）：設定目標金額/日期，追蹤進度跟所需年化報酬率
- `b11cb27` `c47854a` `e4acf4f` 全站破折號 `—`/`–` 統一改成單一 `-`，精簡多個側邊選單標籤
- `51b113c` `6704484` `f2b375a` `705d34f` UI 調整：修正統計數字區塊換行/重疊問題（daisyUI `.stats` 改用 grid 而非 flex）、HHI 圖表說明改白話文、DCA 表單縮小成單行、比較投入方案跟主表單重複時自動去重避免圖表線條重疊、持股筆記預設唯讀顯示（點「編輯」才變成可編輯表單）
- `6315e45` 重寫 README 功能列表，涵蓋這批新增的所有分析工具
- `a9a3487` firstrade 套件安全查核：人工確認套件只會呼叫 `api3x.firstrade.com`，鎖定套件版本（`firstrade==0.0.39`），新增 `scripts/verify_firstrade_domains.py` 自動掃描套件原始碼裡的網址，並接進 CI（`requirements.txt` 有異動時自動跑一次），避免未來套件升級時網域悄悄改變卻沒發現
- `2a5fa9f` 新增「定投高點回本風險」（issue #122）：掃描標的完整歷史股價，列出每一次買在高點要等很久（預設超過 60 天，可調整）才回到原本高點的時間區間，含高點/最低點日期價格、最大跌幅、回本日期或「尚未回本」、花費時間
- `bcd6d3b` 修正空持股/未設定目標配置時整頁 JS 崩潰的 bug（issue #126）：目標達成進度追蹤／持股健康度總覽的 JS 綁定沒跟著 HTML 的 `{% if snapshots %}` 一起擋，未捕捉的例外會讓同一個 `<script>` 區塊後面所有功能（股利再投入試算、複利曲線等）全部失效；另外複利曲線「隱藏我的持股」勾選框在沒設定目標配置時也會有同樣問題，一併補上 null 檢查
- `f484b3d` 總覽統計卡片下方新增「接下來預測」（issue #129）：以目前 XIRR 年化報酬率複利推算 1 個月／1 季／半年／1 年後的預估市值跟預估變動金額/百分比，純粹是「照現在速度走下去」的參考，不是報酬預測
- `8559167` 「接下來預測」新增 3/5/10/20 年後（issue #132），放在可收合的區塊裡、進站時預設收合，避免極端年化報酬率複利多年後的誇張數字一進站就直接顯示
- `e6ae3f6` 月度/年度績效報告多兩個報酬數字（issue #48 相關）：原本只有「用目前股數回推期間市值」的組合價格報酬，容易被誤會；新增「本期資金加權報酬 (XIRR)」（用交易紀錄還原起始日持股，期間內每筆買賣按實際日期計入，年化）跟「自買入以來總報酬」（相對實際成本、不分期間），三個數字各自標清楚定義
- `2503986` 目標達成進度追蹤新增「以目前 XIRR 推估達標日期」跟一條投影曲線：`current_value·(1+XIRR)^t = target` 反推達標時間，畫出照目前速度走下去的市值軌跡 vs 目標水平線；報酬率為 0/負時顯示「達不到」
- `901332d` 重截 README 全部 26 張截圖為深色模式（先前混雜白天模式、各區塊假資料不一致），新增 `scripts/seed_demo_data.py`：可重現的拋棄式假資料 fixture，含持股/交易/筆記/目標/月度快照，`_check()` 自我驗證，拒絕非 sqlite 的 DATABASE_URL
- `7081f34` DDD 重構第一、二階段：31 個扁平 `app/*.py` 依職責搬進 `domain/{portfolio,analytics,income,goals}`／`infrastructure/`／`interface/` 分層；新增 `infrastructure/repositories.py`（`Repositories` context manager），路由層所有 `SessionLocal()` + `db.query` 拔掉，改走 repository，`interface/http.py` 淨 -196 行。`app/main.py` 變 1 行 ASGI 薄殼，`uvicorn app.main:app` 不變，render/CI 照舊。無行為改動、25/25 測試通過
- `1e0c5e5` DDD 重構第三階段：新增 `application/`（`dashboard.py`／`goals.py`／`tax.py`），首頁那段 ~90 行的 context 組裝跟其他有編排邏輯的路由搬進 service 層；新增 `infrastructure/market_data.py` 作為唯一 import `yfinance` 的地方，11 個 domain 模組改走這個 gateway。README 專案結構章節重寫，附分層職責表跟「為什麼這樣分層」說明。無行為改動、首頁 HTML 逐 byte 相同

## 2026-08-28

- `9936fc1` `58873b8` 新增「投資組合複利曲線」：累積報酬統計、隱藏切換、進站預設自動載入
- `22bd7c0` `4deaf64` 新增「複利曲線估算」（issue #35）：實際複利路徑 vs 幾何／算術平均平滑曲線推算
- `84f88f0` 目標配置存檔／刪除後自動重跑回測，不用手動再按一次
- `b7f80ab` 修正目標配置權重加總檢查門檻誤判正常 1% 誤差的 bug
- `75fce75` 修正 XIRR 在槓桿（flex）模式下算出離譜數值的 bug
- `37ad9c2` `68565b1` 目標配置新增／編輯／刪除改成局部更新（optimistic update），不用整頁重新整理

## 2026-08-27

- `d3fe65c` `9c45c32` 新增「匯出報告」CSV（issue #20）
- `a3d72e2` `0681d03` 新增「持股筆記」（issue #19）
- `7a97976` 現金部署建議新增「調整前後配置」對照
- `d22805d` 產業分類名稱改英文，「ETF／其他」拆成已確認 ETF 跟未分類兩類
- `412bf12` `9a29ce1` 新增「現金部署建議」（issue #16）：只用新資金加碼，不賣出既有部位
- `c90c818` `1ff5f4c` 配置圓餅圖跟走勢圖顏色統一，「其他」改名
- `8241770` `3072a32` 新增「配置歷史走勢」圖表（issue #15）
- `d67dc93` 新增「產業別配置圖」（issue #14），擴充「建議」卡片規則
- `115f4bc` `6ac49bd` 新增「股利追蹤」（issue #21）：近 12 個月股息收入與殖利率
- `295cf96` `1be921c` 新增 XIRR（資金加權年化報酬率）
- `0e9de77` `9de004d` 新增「海外所得試算」：台灣稅務居民適用
- `55b4772` `6ff7073` 新增交易紀錄同步跟 FIFO 已實現損益追蹤（issue #22）
- `6486ecd` 「建議」卡片新增進階規則：近期大幅波動、即將公布財報、歷史最大回撤
- `0195c00` `1656961` `fea65ac` 新聞關鍵字多空上色、基本面／風險／分析師評等數字上色、破折號改連字號、槓桿模式數字四捨五入
- `6698293` `56f1888` 表格欄位標題可點擊排序
- `a88abcf` 儀表板細節優化：側邊欄 logo、缺財報日期留空、抑制 ETF 誤導快取徽章
- `278243b` 修正 `_fetch_ok` 誤判成功的 bug（只有 PEG 欄位的回應被誤判為正常資料）
- `0649bbf` `fb3e9b9` `54f7250` `535d1ad` `f98ab97` `bd5f2b7` `aa803b1` `3d4e64b` `b75853b` `ec9fcaf` 排查 Render 上 Yahoo quoteSummary API 回 Invalid Crumb 導致基本面資料抓不到的問題，一連串診斷 log／CSRF 實驗後確認是 Render 的 IP 被擋，改成用 GitHub Actions 排程抓資料存進資料庫繞過（issue #9）
- `91f7fad` 新增左側導覽選單，方便跳轉各區塊
- `7102669` `219d42c` 新增風險／波動度指標、持股基本面資料、大盤熱門標的走勢
- `d225e0c` 修正 CASH 現金列改用 Firstrade 官方 `cash_balance`，不再用會隨即時報價漂移的殘差計算

## 2026-08-26

- `6d28b27` 修正「近期市場動態」把合成的 `CASH` 現金列誤當成真實股票代號查詢的 bug（跟 Nasdaq 上市代號 CASH 撞名，導致顯示不相關公司新聞），刷新 README 截圖跟更新紀錄
- `274bfc0` 拿掉頁首圖示不必要的白底圈（圖示本身已有實色背景），放大圖示
- `043c173` 換成使用者提供的柴犬圖片，壓縮到 128px 內嵌（原圖 1254px、1.1MB 太大）
- `e730193` 改用使用者提供的柴犬 PNG 圖片（base64 內嵌）取代手繪 SVG，當作 favicon 跟頁首圖示
- `6da9286` 加寬圖示臉型/腮幫子，更像柴犬
- `f5213e7` 重畫 favicon/頁首圖示，更接近參考圖的柴犬風格（原創畫作，非直接使用有浮水印的參考圖）
- `905eede` `def8719` 每次「重新抓取持股」時，連同 USD/TWD 匯率一起存一筆快照（`exchange_rate_snapshots` 表），首頁改讀資料庫最新一筆，不再每次載入頁面都即時查匯率；再平衡回測改成一進頁面就自動載入（前提是已設定目標配置），跟持股歷史走勢一致
- `7b5beb6` 刷新 README 截圖反映目前介面，補上功能更新紀錄
- `9403837` 縮小過大的深色模式切換圖示
- `c89d05f` 持股歷史走勢／再平衡回測新增「移除我的持股組合」勾選框，比較線不再被持股中最晚上市的標的（例如比特幣現貨 ETF）限制住最早的可比較日期
- `a4378b0` 再平衡回測支援多條比較基準（分號分隔），各自列出報酬率、最大回撤、年化波動度；確認台股代號（如 `0050.TW`）可以直接拿來比較
- `b2ab0da` 持股歷史走勢的「比較標的」從單一加權組合改成支援多條線（分號分隔）
- `709a2d9` 持股同步新增現金部位：改用 Firstrade 帳戶官方總值反推未投入現金，存成合成的 `CASH` 列，計入總市值但不計入集中度風險提醒；欄位標題拿掉多餘的 `(USD)`

## 2026-08-25

- `6fa2d18` 目標配置表格的「差距」欄位改成依正負號上色（正綠負紅）
- `0290af8` 目前持股表格新增「漲跌幅」欄位（現價相對買入均價的百分比）
- `bdf0907` 再平衡回測圖表加上重大波動日標註、hover 提示，跟持股歷史走勢一致
- `63ed847` 重畫 favicon/頁首圖示、放大配置圓餅圖、現價依漲跌上色、目標配置表格加上「目前」佔比欄
- `5378a2d` 刷新 README 截圖（台幣卡片、買入均價欄、不再平衡對照線、代號自動完成）
- `0bdbfd7` `71c2e91` `5c6b26f` 新增總市值／未實現損益的台幣換算（USD/TWD 參考匯率）
- `cc9099f` 新增黑白手繪柴犬 favicon 跟頁首圖示
- `eef99b6` 目前持股表格新增買入均價／現價欄位，配置圓餅圖移到表格下方
- `48719e2` 新增代號自動完成（目標配置、比較標的、比較基準），回測圖表加上「不再平衡」對照線、重大波動標記 hover 提示
- `231122d` README 截圖拆成各區塊分開的深色模式截圖
- `6a36e63` 修正最大回撤比較的方向判斷反了的 bug，拿掉破折號，分析文字分行顯示
- `a32255f` 目前持股表格加上目前／目標佔比並排、新增「近期市場動態」（大漲大跌提醒 + 新聞標題）、持股歷史走勢圖表加上重大波動日標註跟回撤/波動度分析
- `cbdd72c` 防止選到未來或空區間的日期範圍導致回測算出無意義結果，日期選擇器預設抓最近一年並限制不能選未來
- `eb62672` `5db52a0` 重寫 README（含截圖），按鈕改成黑白配色
- `6d78362` 修正圓餅圖顏色遺失的 bug、換成黑白 SVG 深色模式圖示、重新設計區塊標題
- `69fe4d5` 改用 daisyUI 重新設計介面（含可用的深色模式）、支援自訂加權組合比較基準、縮小圓餅圖並加上明細提示
- `bf66daa` 修正「每月再平衡」在月曆最後一天非交易日時會整月靜默跳過的 bug，新增持股歷史走勢／目標配置編輯刪除／回測圖表標註
- `5bc5f46` 修正 Firstrade 持股欄位對應（正確欄位是 `cost`/`last`，不是文件猜測的 `cost_basis`/`last_price`），加上 dotenv 讀取，`.gitignore` 排除 session cookie 檔
- `2e26afa` 改用 Tailwind CSS 重新設計介面、加上統計卡片、修正 `datetime.utcnow()` 棄用警告
- `2fec883` MVP：Firstrade 自動登入同步、配置建議引擎、再平衡回測引擎、網頁儀表板
- `aa02da1` 新增專案 README
- `158253f` 初始 commit
