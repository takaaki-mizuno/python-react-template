# Backend

FastAPI + SQLModel + PostgreSQL のバックエンド。

## 前提

- Python 3.12
- uv
- PostgreSQL 17
- Docker Compose

## ローカル起動

```bash
cp .env.example .env
uv sync
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app uv run python manage.py db-upgrade
python manage.py serve
```

hot reload は `ENVIRONMENT=local` または `ENVIRONMENT=development` のとき既定で有効になる。`.env` を作らない場合、既定は production 扱いで reload なしになる。

明示的に指定する場合:

```bash
python manage.py serve --host 0.0.0.0 --port 8000 --reload
python manage.py serve --host 0.0.0.0 --port 8000 --no-reload --workers 2
```

## DB

```bash
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app uv run python manage.py db-upgrade
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app uv run python manage.py db-check
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app uv run python manage.py db-revision --message "change name" --autogenerate --rev-id YYYYMMDD_NNNN
```

schema 変更と migration 作成は、事前に `documents/plans/` に計画を書き、ユーザー確認を取ってから行う。

auth の古い audit log、期限切れ session、期限切れ OIDC authorization state は `db-prune-auth` で削除する。日時は timezone offset 付き ISO 8601 を指定する。

```bash
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app uv run python manage.py db-prune-auth \
  --audit-logs-before 2026-08-01T00:00:00+00:00 \
  --expired-sessions-before 2026-08-01T00:00:00+00:00 \
  --oidc-states-before 2026-08-01T00:00:00+00:00
```

## テストと品質ゲート

```bash
uv run ruff check .
uv run isort . --check-only
uv run yapf -dr app/ tests/ alembic/ manage.py
uv run mypy app manage.py
uv run pytest tests/unit -q
```

integration tests は PostgreSQL が必要で、`TEST_DATABASE_URL` 未設定時は fail する。

```bash
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration -q -ra
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run python manage.py db-check
```

## Docker Compose

```bash
docker compose up -d postgres backend frontend
```

backend service は `backend-dev` target を使い、`./backend:/app/backend` を mount する。container 内で `pytest`、`alembic`、`db-check` を実行できる。

`docker-compose.yaml` の backend service は `/app/backend/.venv` に anonymous volume を使う。`backend/uv.lock` を変更した後に container 内の依存が古い場合は、次で volume を作り直す。

```bash
docker compose down -v
docker compose up -d postgres backend
```

## Sample CRUD

`/api/samples` は新規 resource 実装のコピー元になる user-owned CRUD sample。

```bash
curl -c /tmp/sample-cookies.txt -b /tmp/sample-cookies.txt http://127.0.0.1:8000/api/auth/csrf
```

取得した `csrfToken` を `X-CSRF-Token` に入れる。

```bash
curl -c /tmp/sample-cookies.txt -b /tmp/sample-cookies.txt \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-Token: <csrfToken>' \
  -d '{"email":"sample@example.com","password":"Password123!"}' \
  http://127.0.0.1:8000/api/auth/register

curl -c /tmp/sample-cookies.txt -b /tmp/sample-cookies.txt \
  -H 'Content-Type: application/json' \
  -H 'X-CSRF-Token: <csrfToken>' \
  -d '{"title":"First item","description":"Use camelCase JSON."}' \
  http://127.0.0.1:8000/api/samples

curl -b /tmp/sample-cookies.txt http://127.0.0.1:8000/api/samples
```

public request / response JSON は camelCase を正とする。`PATCH /api/samples/{id}` は `description: null` で説明を clear できる。`title` / `isCompleted` の `null` と未知 field は 422、empty body は no-op 200 になる。

## OAuth/OIDC login 設定

OAuth/OIDC は汎用 provider 設定で追加する。`backend/.env.example` と同じ env 名を使い、JSON 1 本ではなく provider id 別 env 群で管理する。

```env
AUTH_OIDC_ENABLED_PROVIDERS=google
AUTH_OIDC_REDIRECT_BASE_URL=http://localhost:8000
AUTH_OIDC_REAUTH_FRESHNESS_SECONDS=300
AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP=20
AUTH_OIDC_STATE_TTL_SECONDS=300
AUTH_OIDC_PROVIDER_GOOGLE_DISPLAY_NAME=Google
AUTH_OIDC_PROVIDER_GOOGLE_ISSUER=https://accounts.google.com
AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_ID=<client-id>
AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_SECRET=<client-secret>
AUTH_OIDC_PROVIDER_GOOGLE_SCOPE=openid email profile
AUTH_OIDC_PROVIDER_GOOGLE_TRUST_VERIFIED_EMAIL=true
AUTH_OIDC_PROVIDER_GOOGLE_AUTO_PROVISION=enabled
AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE=auto
AUTH_OIDC_PROVIDER_GOOGLE_CALLBACK_PATH=/api/auth/oidc/google/callback
AUTH_OIDC_PROVIDER_GOOGLE_CLAIMS_ALLOWLIST=
```

Provider に登録する redirect URI は `AUTH_OIDC_REDIRECT_BASE_URL` と callback path を連結した absolute URL である。local 例は `http://localhost:8000/api/auth/oidc/google/callback`。request host から redirect URI は組み立てない。

`trusted verified email` を使う自動作成・自動 link は provider ごとに明示する。`AUTH_OIDC_PROVIDER_GOOGLE_AUTO_PROVISION=link-only` にすると既存 user への link のみ許可し、新規 user を作らない。`AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE=manual` または `disabled` は verified email 一致での自動 link を拒否する。

token 非保存が契約である。Provider `access_token` / `refresh_token` は保存しない。DB へ保存するのは provider subject と allowlist 済み ID token claims だけで、audit log にも raw provider error や token を残さない。

OAuth-only account deletion は `last_oidc_auth_time_at` と `AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` で fresh 判定する。削除 reauth callback では `auth_time` が必須で、`OIDC_REAUTH_SUBJECT_MISMATCH`、`OIDC_REAUTH_STALE`、`OIDC_REAUTH_AUTH_TIME_REQUIRED` は settings redirect の machine code として扱う。`ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` の JSON details は linked providers (`providerId`, `displayName`) だけを返す。

OIDC callback は DB-backed state、PKCE、nonce、safe ID token alg、JWKS、browser binding cookie を検証する。browser binding cookie は state ごとに発行し、callback consume 後または terminal failure 後に削除する。State cleanup は明示的に実行する。

```bash
DATABASE_URL="postgresql+asyncpg://app:app@localhost:5432/app" \
  uv run python manage.py db-prune-auth --oidc-states-before "2026-08-01T00:00:00+00:00"
```
