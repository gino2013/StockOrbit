"""千倍股評估（issue #408）的純計算：關鍵數字、資料信心度、驗證判斷、組成
存檔紀錄。數字一律由這裡從後端資料算，LLM 只給定性判斷（ADR 0001）；判斷
在 Claude Code session 裡產生（ADR 0002），所以沒有 API 端的 schema 強制，
這裡的 validate_judgment 是唯一一道關卡。名詞見 GLOSSARY.md。
"""

SCHOOLS = ("phelps_mayer", "fisher", "lynch", "buffett_munger")
LYNCH_CATEGORIES = ("快速成長型", "緩慢成長型", "穩定成長型", "景氣循環型", "轉機型", "資產型")
SUMMARY_MAX_CHARS = 100
_FALLBACK_TAX_RATE = 0.21  # 美國聯邦公司稅率，有效稅率算不出合理值時用


def _num(v):
    """None/NaN -> None，其他轉 float。yfinance 報表缺值是 NaN。"""
    if v is None:
        return None
    v = float(v)
    return None if v != v else v


def roic_pct(operating_income, tax_provision, pretax_income, total_debt, equity, cash):
    """最近一個會計年度的 ROIC 近似值（%）：營業利益 ×（1 − 有效稅率）÷
    （總負債 + 股東權益 − 現金）。有效稅率只信 0–50%，其他（虧損、稅務利益）
    改用 21%。投入資本 ≤ 0（大量庫藏股買回、權益為負）時沒有意義，回 None。"""
    op, debt, eq = _num(operating_income), _num(total_debt), _num(equity)
    if op is None or eq is None:
        return None
    tax, pretax = _num(tax_provision), _num(pretax_income)
    rate = tax / pretax if tax is not None and pretax else None
    if rate is None or not 0 <= rate <= 0.5:
        rate = _FALLBACK_TAX_RATE
    invested = (debt or 0.0) + eq - (_num(cash) or 0.0)
    if invested <= 0:
        return None
    return round(op * (1 - rate) / invested * 100, 1)


def revenue_cagr_3y_pct(revenues_newest_first):
    """3 年營收年化成長率（%）。需要 4 個年度；三年前營收 ≤ 0 時回 None。"""
    revs = [r for r in (_num(v) for v in revenues_newest_first) if r is not None]
    if len(revs) < 4 or revs[3] <= 0 or revs[0] < 0:
        return None
    return round(((revs[0] / revs[3]) ** (1 / 3) - 1) * 100, 1)


def data_confidence(key_metrics: dict) -> str:
    missing = sum(v is None for v in key_metrics.values())
    return "high" if missing == 0 else "medium" if missing == 1 else "low"


def validate_judgment(j) -> list[str]:
    """回傳所有錯誤（空 list 表示通過），讓 session 一次看到全部問題再修。"""
    if not isinstance(j, dict):
        return ["判斷必須是 JSON 物件"]
    errors = []
    schools = j.get("schools")
    if not isinstance(schools, dict) or set(schools) != set(SCHOOLS):
        errors.append(f"schools 必須剛好有 {', '.join(SCHOOLS)}")
        schools = {}
    for name, s in schools.items():
        if not isinstance(s, dict):
            errors.append(f"{name} 必須是物件")
            continue
        score = s.get("score")
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            errors.append(f"{name}.score 必須是 1–5 的整數")
        if not isinstance(s.get("reason"), str) or not s["reason"].strip():
            errors.append(f"{name}.reason 不能空白")
    if isinstance(schools.get("lynch"), dict) and schools["lynch"].get("category") not in LYNCH_CATEGORIES:
        errors.append(f"lynch.category 必須是 {'|'.join(LYNCH_CATEGORIES)} 之一")
    if isinstance(schools.get("buffett_munger"), dict):
        moat = schools["buffett_munger"].get("moat_type")
        if not isinstance(moat, list) or not all(isinstance(m, str) and m.strip() for m in moat):
            errors.append("buffett_munger.moat_type 必須是字串 list（沒有護城河就給空 list）")
    risks = j.get("risks")
    if not isinstance(risks, list) or len(risks) != 3 or not all(isinstance(r, str) and r.strip() for r in risks):
        errors.append("risks 必須剛好 3 個非空字串")
    summary = j.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("summary 不能空白")
    elif len(summary) > SUMMARY_MAX_CHARS:
        errors.append(f"summary 超過 {SUMMARY_MAX_CHARS} 字（目前 {len(summary)} 字）")
    return errors


def build_evaluation(judgment: dict, inputs: dict) -> dict:
    """judgment 已通過 validate_judgment。總分、信心度、key_metrics 都來自程式，
    judgment 裡就算夾帶同名欄位也不採用。"""
    km = inputs["key_metrics"]
    return {
        "ticker": inputs["symbol"],
        "company_name": inputs["company_name"],
        "schools": {name: judgment["schools"][name] for name in SCHOOLS},
        "total_score": sum(judgment["schools"][name]["score"] for name in SCHOOLS),
        "key_metrics": km,
        "risks": judgment["risks"],
        "summary": judgment["summary"].strip(),
        "data_confidence": data_confidence(km),
    }
