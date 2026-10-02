"""「千倍股」篩選 - 不是技術分析也不是題材追蹤，套用實證資產定價／
企業金融學文獻裡，被證實跟長期超額報酬相關的四個維度做篩選（使用者提
供的研究摘要，issue #348）：

1. 獲利能力護城河（Novy-Marx 2013 的 gross profitability，對應
   Fama-French 五因子的 RMW 因子）：毛利率高代表在產業鏈裡有定價權。
2. 盈餘/營收動能：原文獻用 3-5 年 CAGR，這裡用 yfinance 能拿到的
   YoY revenueGrowth/earningsGrowth 當代理指標，不是真正的多年
   CAGR，差異看這裡的註解，不假裝更精確。
3. 輕資產小股本（對應 Cooper, Gulen, & Schill 2008 的 asset growth
   anomaly 反面）：原文獻用台股的「股本 < 20 億元」（面額概念），這裡
   是美股 Firstrade 持股/自選股，沒有「股本」這個概念，改用市值門檻
   當小型股的代理指標。
4. 估值溢價（對應 Chan, Lakonishok, & Sougiannis 2001 的無形資產溢
   價）：原文獻同時要求高研發費用佔比，這裡沒有算 - yfinance 的
   get_info() 不含研發費用，要抓損益表是另一個額外的 API 呼叫，先不
   做，只用 PEG 估值合理區間當這個維度的代理指標。

四個維度各自二元判斷（True/False），分數 = 通過幾個維度（0-4），用來
排序，不是連續分數；任何資料缺漏的維度一律算「未通過」，缺資料跟真的
不符合條件一視同仁，不會因為缺資料而跳過或加分。純資訊呈現，不是選股
建議，更不保證下一檔千倍股。
"""

from __future__ import annotations

GROSS_MARGIN_THRESHOLD = 0.40
GROWTH_THRESHOLD = 0.20
SMALL_CAP_THRESHOLD = 5_000_000_000.0  # USD，股本 < 20 億台幣這個概念換成美股市值的代理門檻
PEG_MAX = 2.0


def score_moonshot(fundamentals: dict) -> dict:
    """fundamentals: 單一代號的欄位（來自 FundamentalsCache／yfinance），
    看 grossMargins / revenueGrowth / earningsGrowth / marketCap /
    pegRatio。回傳四個維度（各自 {key, label, value, passed}）加總分
    `score`（0-4）。"""
    gross_margin = fundamentals.get("grossMargins")
    revenue_growth = fundamentals.get("revenueGrowth")
    earnings_growth = fundamentals.get("earningsGrowth")
    market_cap = fundamentals.get("marketCap")
    peg = fundamentals.get("pegRatio")

    # 營收、獲利任一有成長動能即可 - 不要求兩個同時滿足，很多高成長公司
    # 這兩個數字本來就不會同步（例如還在擴張期、獲利率被投資壓低）。
    growth = max((v for v in (revenue_growth, earnings_growth) if v is not None), default=None)

    criteria = [
        {
            "key": "profitability",
            "label": "獲利能力護城河（毛利率）",
            "value": gross_margin,
            "passed": gross_margin is not None and gross_margin > GROSS_MARGIN_THRESHOLD,
        },
        {
            "key": "growth",
            "label": "盈餘/營收動能（YoY，非多年 CAGR）",
            "value": growth,
            "passed": growth is not None and growth > GROWTH_THRESHOLD,
        },
        {
            "key": "small_cap",
            "label": "輕資產小股本（市值門檻，美股代理指標）",
            "value": market_cap,
            "passed": market_cap is not None and 0 < market_cap < SMALL_CAP_THRESHOLD,
        },
        {
            "key": "valuation",
            "label": "估值溢價（PEG 合理區間）",
            "value": peg,
            "passed": peg is not None and 0 < peg < PEG_MAX,
        },
    ]
    return {"criteria": criteria, "score": sum(1 for c in criteria if c["passed"])}


def rank_moonshot_candidates(fundamentals_by_symbol: dict[str, dict]) -> list[dict]:
    """幫一批代號評分，依分數高到低排序（同分用代號字母序，排序穩定）。
    name/sector/industry 直接從同一份 fundamentals 資料帶出來（反正
    fetch_fundamentals()／FundamentalsCache 本來就有抓這幾欄），讓每次
    查詢結果自帶公司是做什麼的，不用另外呼叫 API，也不會因為候選名單
    每次排程都換掉而需要維護一份寫死的介紹清單。"""
    results = [
        {
            "symbol": symbol,
            "name": f.get("longName"),
            "sector": f.get("sector"),
            "industry": f.get("industry"),
            **score_moonshot(f),
        }
        for symbol, f in fundamentals_by_symbol.items()
    ]
    return sorted(results, key=lambda r: (-r["score"], r["symbol"]))


def market_screen_symbols(limit: int = 30) -> list[str]:
    """掃全市場找出真的通過全部四項門檻的代號（issue #356），不是只能評分
    使用者自己清單裡的代號 - 直接把這裡的門檻常數套進 yfinance 的
    EquityQuery，Yahoo 自己的伺服器端做篩選（不是抓全市場報價回來自己算），
    一次撈出真正的候選名單，依市值大到小排序。

    Yahoo screener 的數值欄位用的是百分比整數（40 代表 40%），跟這個檔案
    其他地方用小數（0.4）不同，這裡轉換一次。拿到的代號清單還是要再走一次
    fetch_fundamentals()/快取（跟清單篩選共用同一條路徑）才能顯示實際數字
    - Yahoo screener 回傳的 quote 物件本身不含 grossMargins/pegRatio 這些
    用來篩選的欄位。
    """
    from app.infrastructure import market_data

    quotes = market_data.screen_equities(
        filters=[
            ("grossprofitmargin.lasttwelvemonths", "gt", GROSS_MARGIN_THRESHOLD * 100),
            ("intradaymarketcap", "lt", SMALL_CAP_THRESHOLD),
            ("totalrevenues1yrgrowth.lasttwelvemonths", "gt", GROWTH_THRESHOLD * 100),
            ("pegratio_5y", "btwn", (0, PEG_MAX)),
        ],
        count=limit,
    )
    return [q["symbol"] for q in quotes if q.get("symbol")]
