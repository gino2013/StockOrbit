"""千倍股篩選查詢編排（issue #348/#360）：即時抓 + 快取退回 + 評分，給
即時查詢（app.interface.http）跟排程重新整理腳本（scripts/
refresh_moonshot_market_screen.py）共用，兩邊要套用一樣的退回規則 - 之前
這段邏輯只活在 interface 層，寫 #348 的時候還沒有排程腳本要共用它。
"""

from app.domain.screening.moonshot import rank_moonshot_candidates
from app.infrastructure import github_actions
from app.infrastructure.fundamentals import fetch_fundamentals


def score_symbols(repo, symbol_list: list[str]) -> list[dict]:
    """repo: 呼叫端已經開好的 Repositories 實例（global 的
    fundamentals_cache/register_fundamentals_symbol，不受 user_id 影響，
    傳哪個使用者的 repo 都一樣）。"""
    live = fetch_fundamentals(symbol_list)
    fundamentals_by_symbol = {}
    newly_registered = False
    for symbol in symbol_list:
        fields = live.get(symbol, {})
        if not fields.get("_fetch_ok"):
            cached = repo.fundamentals_cache([symbol]).get(symbol)
            if cached:
                fields = {**fields, **cached}
            elif repo.register_fundamentals_symbol(symbol):
                newly_registered = True
        fundamentals_by_symbol[symbol] = fields
    if newly_registered:
        github_actions.trigger_fundamentals_refresh()
    return rank_moonshot_candidates(fundamentals_by_symbol)
