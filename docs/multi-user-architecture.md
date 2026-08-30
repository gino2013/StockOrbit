# Multi-user architecture

StockOrbit started as a single-user personal app. This is the design for
letting other people sign up with their own portfolios. Shipped as a
sequence of small PRs; this document is the plan of record.

## Decisions

| Question | Choice |
|---|---|
| How guests' portfolio data enters | Store each user's Firstrade credentials, Fernet-encrypted |
| Auth | Email + password |
| Registration | Open |
| Owner env-cred auto-sync | Kept (the `OWNER_EMAIL` account) |

## Security note (surface in README + settings UI)

Storing Firstrade username / password / TOTP-secret means **a DB dump plus
`FT_CREDENTIAL_KEY` = full takeover of every user's brokerage account**.
`firstrade` is an unofficial scraper; the risk scales with user count, and
many logins from Render's IP invite account-flagging. Mitigations:
`FT_CREDENTIAL_KEY` is env-only and separate from `APP_SECRET_KEY`;
decrypted values are never logged; per-user sync is rate-limited; the
settings form is gated behind a verified email; account deletion hard-wipes
the credential row. **Recommendation:** keep the Firstrade-credential
feature allowlist-only even with open registration, and offer CSV import as
the path for everyone else.

## Data model

New tables:

- **`users`** — `id` (uuid hex), `email` (unique, lower-cased),
  `password_hash` (bcrypt via `app/interface/auth.py`), `email_verified`,
  `session_version` (bump = log out everywhere), `is_owner`, `created_at`.
- **`firstrade_credentials`** — `user_id` PK/FK, `username_enc`,
  `password_enc`, `mfa_secret_enc` (Fernet ciphertext via
  `app/infrastructure/crypto.py`), `last_sync_at`, `last_sync_error`.

Add `user_id` (indexed FK) to `position_snapshots`, `transactions`,
`target_allocations`, `position_notes`, `transaction_notes`,
`investment_goals`. PK changes: `target_allocations` →
`(user_id, symbol)`, `position_notes` → `(user_id, symbol)`,
`transaction_notes` → `(user_id, transaction_id)`, `transactions` →
`(user_id, id)`, `investment_goals` → `user_id` (drop the `"default"`
singleton).

Stay global (no `user_id`): `fundamentals_cache`,
`exchange_rate_snapshots` — shared market data.

## Migrations (Alembic)

- `0001_baseline` — the pre-multi-user schema. On the existing prod DB
  (tables already created by `create_all`): run once
  `alembic stamp 0001_baseline`. On a fresh DB, `upgrade head` creates them.
- `0002_users_creds` — `users` + `firstrade_credentials` (additive, safe).
- *(step 2)* nullable `user_id` on the six tables + owner bootstrap from
  `OWNER_EMAIL` + backfill all existing rows to the owner.
- *(step 4)* `user_id` NOT NULL, composite PKs, FKs.

`init_db()` (`create_all`) stays for the local sqlite quickstart; prod runs
`alembic upgrade head` (added to `render.yaml` build in step 2).

## Auth (`app/interface/auth.py`)

bcrypt (sha256-prehashed to dodge the 72-byte truncation) + stateless
`itsdangerous` signed cookie `{uid, sv}`, 30-day. `current_user` (401) and
`current_user_html` (303 → `/login`) dependencies; `require_owner` (403).
Email verification + password reset use short-lived signed tokens and a
`mailer.py` wrapping `RESEND_API_KEY` / SMTP. `slowapi` rate-limits
`/login`, `/register`, `/forgot`.

## Tenancy enforcement

The DDD phase-2 refactor already removed every raw `db.query` from the
interface layer, so `app/infrastructure/repositories.py` is the single
chokepoint: `Repositories(user_id)` scopes every read/write. The three
global-data methods stay unscoped. Every `http.py` handler:
`user = Depends(current_user)` → `Repositories(user.id)`.

## Owner mode

`OWNER_EMAIL` account is bootstrapped on startup (`is_owner`,
`email_verified`, password from `OWNER_INITIAL_PASSWORD`). Its refresh uses
a stored `firstrade_credentials` row if present, else the `FT_*` env vars —
today's workflow is unchanged. The GitHub Actions fundamentals-cache job
touches only global tables and is untouched.

## Frontend

Server-rendered + `fetch`, no SPA. New templates `login.html`,
`register.html`, `settings.html`, `terms.html`, `privacy.html`.
`dashboard.html` gains an empty state ("connect Firstrade in settings") and
a header email + logout link.

## Rollout (one PR each)

1. Alembic + `users`/`firstrade_credentials` models + `crypto.py` +
   `auth.py` + tests. **(this PR)**
2. Nullable `user_id` migration + owner bootstrap/backfill +
   `Repositories(user_id)` scoping + tenancy tests. No auth gate yet.
3. Auth routes + templates; `/` and `/api/*` behind `current_user`;
   dashboard empty state.
4. Tighten migration: `user_id` NOT NULL, composite PKs, FKs.
5. `/settings` + Firstrade credential storage + per-user sync + account
   deletion.
6. Open-registration hardening: email verification, rate limiting,
   `/terms` + `/privacy`, README security section.
7. *(optional)* CSV import as a no-credential path.
