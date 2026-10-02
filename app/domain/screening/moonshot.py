"""「千倍股」篩選 - 不是技術分析也不是題材追蹤，套用實證資產定價／
企業金融學文獻裡，被證實跟長期超額報酬相關的四個維度做篩選（使用者提
供的研究摘要，issue #348）：

1. 獲利能力護城河（Novy-Marx 2013 的 gross profitability，對應
   Fama-French 五因子的 RMW 因子）：毛利率高代表在產業鏈裡有定價權。
   金融股（銀行/放款/REIT/保險/資產管理）的毛利率定義鬆散、常常天生
   就逼近 100%（見 `_is_financial_sector`），這個門檻對它們等於沒在篩，
   改用 ROE/P-B 當替代指標（issue #366）。
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
   做，只用 PEG 估值合理區間當這個維度的代理指標。PEG 自己算，不信
   `pegRatio` 這個資料源欄位（人工核對發現常常是 null 或失真，issue
   #366）：PE 用 `trailingPE`，成長率用 `(forwardEps-trailingEps)/
   trailingEps`（分析師對下一年 EPS 共識估計隱含的成長率，不是另外打
   一個分析師預估 API）；EPS、PE、成長率只要有一個 <=0 或缺資料，直接
   判「未通過」，不是略過這個維度。

四個維度各自二元判斷（True/False），分數 = 通過幾個維度（0-4），用來
排序，不是連續分數；任何資料缺漏的維度一律算「未通過」，缺資料跟真的
不符合條件一視同仁，不會因為缺資料而跳過或加分。純資訊呈現，不是選股
建議，更不保證下一檔千倍股。

人工核對 25 檔全市場搜尋結果後（issue #366），額外加了幾個不改變分數、
只是提醒「這個分數可能有水分」的 flag，用的都是 fetch_fundamentals()
本來就有抓的欄位，沒有多打任何新 API：
- 獲利品質：營業利益 <=0，或淨利明顯高於營業利益（業外/稅務利益灌水）
- 成長品質：預估本益比高於目前本益比（分析師預期獲利成長要放緩）
- 邊界：任一指標距門檻 5% 以內

原規格裡還有幾項這次沒做，因為需要完整損益表（稅前淨利、所得稅費用）
或股數歷史（YoY 稀釋）這類目前完全沒在追蹤、得另外打更重 API 的資料，
會重新遇到 Render 連不到 Yahoo quoteSummary 的問題（issue #9/#360），
之後有需要再開新 issue 處理，不在這裡硬做近似值。

另外加了 ticker 存活檢查：`regularMarketTime`（最近一次報價時間）太舊
的直接從結果裡排除，不計分、不顯示 - 但只在「有抓到這個欄位且真的舊」
時才排除，缺資料（例如快取還沒重新整理過）不當作「確認不活躍」，不然
會把一堆只是還沒刷新快取的正常持股也一起藏起來。
"""

from __future__ import annotations

import time

GROSS_MARGIN_THRESHOLD = 0.40
GROWTH_THRESHOLD = 0.20
SMALL_CAP_THRESHOLD = 5_000_000_000.0  # USD，股本 < 20 億台幣這個概念換成美股市值的代理門檻
PEG_MAX = 2.0
FINANCIAL_ROE_THRESHOLD = 0.12
FINANCIAL_PB_MAX = 3.0
STALE_TICKER_SECONDS = 9 * 24 * 3600  # ~5 個交易日的日曆天近似（含週末），跟 YoY-vs-CAGR 同一種簡化
PROFIT_QUALITY_NET_VS_OP_RATIO = 1.5  # 淨利 > 營業利益 x 這個倍數 -> 懷疑業外/稅務利益灌水
BOUNDARY_BUFFER = 0.05  # 距門檻 5% 以內算「邊界」


def _is_financial_sector(fundamentals: dict) -> bool:
    sector = fundamentals.get("sector")
    gross_margin = fundamentals.get("grossMargins")
    return sector == "Financial Services" or (gross_margin is not None and gross_margin >= 0.99)


def _compute_peg(fundamentals: dict) -> float | None:
    """PEG = 本益比 / 預估 EPS 成長率(%)，兩個輸入都要是正數才有意義；
    成長率用 forwardEps 相對 trailingEps 的隱含成長，不信 yfinance 自己
    算的 pegRatio（issue #366，人工核對發現常是 null 或失真）。"""
    pe = fundamentals.get("trailingPE")
    trailing_eps = fundamentals.get("trailingEps")
    forward_eps = fundamentals.get("forwardEps")
    if pe is None or pe <= 0 or not trailing_eps or trailing_eps <= 0 or forward_eps is None:
        return None
    growth = (forward_eps - trailing_eps) / trailing_eps
    if growth <= 0:
        return None
    return pe / (growth * 100)


def _profit_quality_flags(fundamentals: dict) -> list[str]:
    flags = []
    op_margin = fundamentals.get("operatingMargins")
    net_income = fundamentals.get("netIncomeToCommon")
    revenue = fundamentals.get("totalRevenue")
    if op_margin is not None and op_margin <= 0:
        flags.append("營業利益為負或零")
    if op_margin is not None and op_margin > 0 and revenue and net_income is not None:
        op_income = op_margin * revenue
        if net_income > op_income * PROFIT_QUALITY_NET_VS_OP_RATIO:
            flags.append("淨利遠高於營業利益，可能有業外或稅務利益灌水")
    return flags


def _growth_source_flags(fundamentals: dict) -> list[str]:
    flags = []
    forward_pe = fundamentals.get("forwardPE")
    trailing_pe = fundamentals.get("trailingPE")
    if forward_pe is not None and trailing_pe is not None and forward_pe > trailing_pe:
        flags.append("預估本益比高於目前本益比，分析師預期獲利成長放緩")
    return flags


def _boundary_flags(criteria: list[dict]) -> list[str]:
    flags = []
    for c in criteria:
        value, threshold = c["value"], c.get("threshold")
        if value is None or not threshold:
            continue
        if abs(value - threshold) / threshold <= BOUNDARY_BUFFER:
            flags.append(f"{c['label']}：數值接近邊界（距門檻 5% 內），建議再確認")
    return flags


def _is_ticker_stale(fundamentals: dict) -> bool:
    """只在真的有 regularMarketTime 且夠舊時才回傳 True - 缺資料不算確認
    不活躍（見檔案開頭說明）。"""
    t = fundamentals.get("regularMarketTime")
    if t is None:
        return False
    return time.time() - t > STALE_TICKER_SECONDS


def score_moonshot(fundamentals: dict) -> dict:
    """fundamentals: 單一代號的欄位（來自 FundamentalsCache／yfinance）。
    回傳四個維度（各自 {key, label, value, passed, threshold}）、加總分
    `score`（0-4），以及 `flags`（不影響分數，只是提醒分數可能有水分）、
    `is_financial`（這檔是不是被判定成金融股、profitability 維度改用
    ROE/P-B）。"""
    financial = _is_financial_sector(fundamentals)
    if financial:
        roe = fundamentals.get("returnOnEquity")
        pb = fundamentals.get("priceToBook")
        profitability = {
            "key": "profitability",
            "label": "獲利能力護城河（金融股改用 ROE/P-B，毛利率對金融股不適用）",
            "value": roe,
            "threshold": FINANCIAL_ROE_THRESHOLD,
            "passed": roe is not None and roe > FINANCIAL_ROE_THRESHOLD and pb is not None and pb < FINANCIAL_PB_MAX,
        }
    else:
        gross_margin = fundamentals.get("grossMargins")
        profitability = {
            "key": "profitability",
            "label": "獲利能力護城河（毛利率）",
            "value": gross_margin,
            "threshold": GROSS_MARGIN_THRESHOLD,
            "passed": gross_margin is not None and gross_margin > GROSS_MARGIN_THRESHOLD,
        }

    # 營收、獲利任一有成長動能即可 - 不要求兩個同時滿足，很多高成長公司
    # 這兩個數字本來就不會同步（例如還在擴張期、獲利率被投資壓低）。
    revenue_growth = fundamentals.get("revenueGrowth")
    earnings_growth = fundamentals.get("earningsGrowth")
    growth = max((v for v in (revenue_growth, earnings_growth) if v is not None), default=None)
    market_cap = fundamentals.get("marketCap")
    peg = _compute_peg(fundamentals)

    criteria = [
        profitability,
        {
            "key": "growth",
            "label": "盈餘/營收動能（YoY，非多年 CAGR）",
            "value": growth,
            "threshold": GROWTH_THRESHOLD,
            "passed": growth is not None and growth > GROWTH_THRESHOLD,
        },
        {
            "key": "small_cap",
            "label": "輕資產小股本（市值門檻，美股代理指標）",
            "value": market_cap,
            "threshold": SMALL_CAP_THRESHOLD,
            "passed": market_cap is not None and 0 < market_cap < SMALL_CAP_THRESHOLD,
        },
        {
            "key": "valuation",
            "label": "估值溢價（PEG 自算，不信資料源；EPS/本益比/成長率任一不成立視為不通過）",
            "value": peg,
            "threshold": PEG_MAX,
            "passed": peg is not None and 0 < peg < PEG_MAX,
        },
    ]

    flags = _profit_quality_flags(fundamentals) + _growth_source_flags(fundamentals) + _boundary_flags(criteria)

    return {
        "criteria": criteria,
        "score": sum(1 for c in criteria if c["passed"]),
        "flags": flags,
        "is_financial": financial,
    }


def rank_moonshot_candidates(fundamentals_by_symbol: dict[str, dict]) -> list[dict]:
    """幫一批代號評分，依分數高到低排序。同分的保留 fundamentals_by_symbol
    原本的順序（Python dict 保留插入順序，sorted() 本身是穩定排序，這裡
    拿掉次要排序鍵就好）——呼叫端（市場搜尋）傳進來的 dict 順序就是
    market_screen_symbols() 向 Yahoo 要的市值大到小順序，這裡不能再用
    字母序蓋過去，不然「依市值排序」就是假的（issue #364）。

    name/sector/industry 直接從同一份 fundamentals 資料帶出來（反正
    fetch_fundamentals()／FundamentalsCache 本來就有抓這幾欄），讓每次
    查詢結果自帶公司是做什麼的，不用另外呼叫 API，也不會因為候選名單
    每次排程都換掉而需要維護一份寫死的介紹清單。

    確認不活躍（_is_ticker_stale）的代號直接從結果排除，不計分、不顯示
    （issue #366 Rule 1）- 已下市/併購後 ticker 可能被重新分配給別家公司
    （真的發生過，見 PR #366 討論的 ARIS），所以排除依據是「這個 ticker
    最近真的有在報價」，不是去查這家公司的公司名稱/身分有沒有換過。"""
    results = [
        {
            "symbol": symbol,
            "name": f.get("longName"),
            "sector": f.get("sector"),
            "industry": f.get("industry"),
            **score_moonshot(f),
        }
        for symbol, f in fundamentals_by_symbol.items()
        if not _is_ticker_stale(f)
    ]
    ranked = sorted(results, key=lambda r: -r["score"])
    assert all(ranked[i]["score"] >= ranked[i + 1]["score"] for i in range(len(ranked) - 1)), "分數排序壞了"
    return ranked


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
