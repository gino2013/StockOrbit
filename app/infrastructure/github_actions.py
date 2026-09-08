"""Fire-and-forget trigger for the fundamentals-cache-refresh GitHub Actions
workflow (.github/workflows/refresh-fundamentals-cache.yml). That job runs
on GitHub's runners, which Yahoo doesn't block (unlike Render's outbound
IP - see app/infrastructure/fundamentals.py), so it's the only way to get
real fundamentals for a symbol nobody holds. Normally it just runs on its
own schedule; this lets a fresh lookup (fundamentals_cache.register_symbol
returning True - never looked up before) kick it off immediately instead
of waiting for the next scheduled run.

Requires the GH_ACTIONS_TOKEN env var (a fine-grained PAT scoped to this
repo's Actions:write) - unset means this silently no-ops, so a first-time
lookup still just waits for the schedule like before.
"""

import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

_REPO = "gino2013/StockOrbit"
_WORKFLOW = "refresh-fundamentals-cache.yml"


def trigger_fundamentals_refresh() -> None:
    token = os.environ.get("GH_ACTIONS_TOKEN")
    if not token:
        return
    url = f"https://api.github.com/repos/{_REPO}/actions/workflows/{_WORKFLOW}/dispatches"
    req = urllib.request.Request(
        url,
        data=json.dumps({"ref": "main"}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        logger.warning("failed to trigger fundamentals refresh workflow: %s", e)
