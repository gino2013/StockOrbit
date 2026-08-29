"""Security check: verify every URL the installed `firstrade` package talks
to points at Firstrade's own domain, not some third party.

This app hands the package your real FT_USERNAME/FT_PASSWORD (and uses
FT_MFA_SECRET locally to compute a TOTP code) - the package's own code is
what actually sends that login request over the network, so it's the one
trust boundary worth checking automatically whenever the pinned version in
requirements.txt changes (a future release could add a new URL without
anyone here reading the diff line by line).

Run manually:
    .venv/bin/python scripts/verify_firstrade_domains.py

Exits non-zero (and prints the offending URL/file) if any http(s) URL in
the installed package's source doesn't belong to a firstrade.com hostname.
"""

import re
import sys
from pathlib import Path

import firstrade

ALLOWED_HOST_SUFFIX = "firstrade.com"
URL_PATTERN = re.compile(r"https?://[^\s\"'\)]+")


def extract_host(url: str) -> str:
    # Strip scheme, then take everything up to the first '/', ':', or '?'.
    without_scheme = url.split("://", 1)[1]
    return re.split(r"[/:?]", without_scheme, maxsplit=1)[0]


def main() -> int:
    package_dir = Path(firstrade.__file__).parent
    offenders = []
    for py_file in package_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        for match in URL_PATTERN.finditer(text):
            host = extract_host(match.group())
            if not host.endswith(ALLOWED_HOST_SUFFIX):
                offenders.append((py_file.relative_to(package_dir), match.group()))

    if offenders:
        print(f"FAIL: found {len(offenders)} URL(s) outside *.{ALLOWED_HOST_SUFFIX} "
              f"in the installed firstrade package:")
        for file, url in offenders:
            print(f"  {file}: {url}")
        return 1

    print(f"OK: every URL in the installed firstrade package ({firstrade.__file__}) "
          f"points at *.{ALLOWED_HOST_SUFFIX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
