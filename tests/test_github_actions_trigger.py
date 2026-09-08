import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.infrastructure import github_actions


def demo():
    # no token configured -> silently does nothing, no network call at all.
    with patch.dict("os.environ", {}, clear=True), patch.object(github_actions.urllib.request, "urlopen") as urlopen:
        github_actions.trigger_fundamentals_refresh()
        urlopen.assert_not_called()

    # token configured -> POSTs a workflow_dispatch with it as a bearer token.
    with patch.dict("os.environ", {"GH_ACTIONS_TOKEN": "t0k3n"}), patch.object(github_actions.urllib.request, "urlopen") as urlopen:
        github_actions.trigger_fundamentals_refresh()
        urlopen.assert_called_once()
        req = urlopen.call_args[0][0]
        assert req.full_url.endswith("/actions/workflows/refresh-fundamentals-cache.yml/dispatches")
        assert req.get_header("Authorization") == "Bearer t0k3n"

    # GitHub/network failure must never bubble up - this is best-effort,
    # a failed trigger shouldn't break the /api/stock-detail request that
    # asked for it.
    with patch.dict("os.environ", {"GH_ACTIONS_TOKEN": "t0k3n"}), patch.object(github_actions.urllib.request, "urlopen", side_effect=RuntimeError("boom")):
        github_actions.trigger_fundamentals_refresh()  # must not raise


if __name__ == "__main__":
    demo()
    print("OK")
