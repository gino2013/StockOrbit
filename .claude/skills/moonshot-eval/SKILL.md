---
name: moonshot-eval
description: 千倍股評估 - 依四個投資學派評估單一股票並存進 StockOrbit。使用者打 /moonshot-eval <代號> 時使用。
---

# 千倍股評估

對 `$ARGUMENTS`（一個股票代號）做千倍股評估。名詞見 `GLOSSARY.md`，背景見
`docs/adr/0001`、`0002`。只做框架評估，不給買賣建議。

## 1. 抓數據

```bash
.venv/bin/python scripts/moonshot_eval.py fetch <代號> > <scratchpad>/moonshot_inputs.json
```

exit 1 就停下來，把錯誤訊息告訴使用者，不要評估、不要憑記憶補數據。

## 2. 判斷

讀 `moonshot_inputs.json`。規則：

- **數字只能引用 inputs 裡有的**（`key_metrics`、`fundamentals`）。inputs 裡是 null 的數字就說「無資料」，不可以自己補、不可以憑記憶給數字。
- 定性判斷（護城河、管理層、產品、成長故事）可以用你對這家公司的了解，但理由裡提到的數字必須來自 inputs。
- `fundamentals` 裡的比率（`grossMargins`、`revenueGrowth` 等）是小數（0.25 = 25%）；`key_metrics` 的 `*_pct` 已經是百分比。
- 每個學派 1–5 分（整數），各附一句理由，繁體中文：
  - `phelps_mayer`（百倍股學派，Phelps、Mayer）：起始市值夠不夠小、成長跑道夠不夠長；ROIC 是否長期 > 20% 且有再投資空間；有沒有盈餘成長 + 本益比擴張的雙引擎。
  - `fisher`（成長股學派）：產品與市場能否支撐多年營收成長；管理層開發新產品的能力；利潤率與研發效率。
  - `lynch`（十倍股學派）：公司類型；PEG 是否合理；成長故事是否簡單清楚。另給 `category`，只能是 `快速成長型|緩慢成長型|穩定成長型|景氣循環型|轉機型|資產型`。
  - `buffett_munger`（護城河學派）：護城河類型與強度；資本配置能力；內部人持股與股東利益一致性。另給 `moat_type`（字串 list，沒有護城河給 `[]`）。
- `risks`：剛好 3 個主要風險（稀釋、負債、競爭等）。
- `summary`：100 字以內。

把判斷寫成 `<scratchpad>/moonshot_judgment.json`，只放這些欄位（總分、資料信心度、key_metrics、免責聲明都由程式處理，不要放）：

```json
{
  "schools": {
    "phelps_mayer": {"score": 3, "reason": "..."},
    "fisher": {"score": 4, "reason": "..."},
    "lynch": {"score": 3, "reason": "...", "category": "快速成長型"},
    "buffett_munger": {"score": 4, "reason": "...", "moat_type": ["網路效應"]}
  },
  "risks": ["...", "...", "..."],
  "summary": "..."
}
```

## 3. 存檔

```bash
.venv/bin/python scripts/moonshot_eval.py save <scratchpad>/moonshot_inputs.json <scratchpad>/moonshot_judgment.json --model <你目前的模型 ID>
```

這會寫進 `.env` 裡的正式 DB，是刻意的。驗證失敗會列出全部錯誤、什麼都不存：修正 judgment 後再跑一次。

## 4. 回報

用繁體中文給使用者：四個學派分數與總分、資料信心度、3 個風險、摘要，並提醒到儀表板「個股資訊查詢」查這個代號可以看到評估卡片與歷史紀錄。最後附一句：本評估僅為投資框架參考，不構成投資建議。
