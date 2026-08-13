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

`docker-compose.yaml` の backend service は `/app/backend/.venv` に anonymous volume を使う。`backend/uv.lock` を変更した後に container 内の依存が古い場合は、次で backend dependency volume を作り直す。PostgreSQL の実データは `docker/postgres/data/` にあるため、この操作では DB データは削除されない。

```bash
docker compose down -v
docker compose up -d postgres backend
```

## Redis rate limiter

認証 rate limiter は既定で in-memory 実装を使う。ローカルで login / register / OIDC / account deletion の基本動作を確認するだけなら追加設定は不要である。

複数 worker / instance 間で試行回数を共有する検証では、Redis service を起動して `backend/.env` を切り替える。

```env
AUTH_RATE_LIMIT_BACKEND=redis
AUTH_RATE_LIMIT_REDIS_URL=redis://redis:6379/0
AUTH_RATE_LIMIT_REDIS_UNAVAILABLE_POLICY=fail_closed
AUTH_RATE_LIMIT_REDIS_SOCKET_TIMEOUT_SECONDS=0.25
AUTH_RATE_LIMIT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS=0.25
AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS=0.8
AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_FAILURES=5
AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_COOLDOWN_SECONDS=10
AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS=100
```

```bash
docker compose up -d redis postgres backend frontend
docker compose up -d --force-recreate backend
```

Compose 内の backend からは `redis://redis:6379/0` を使う。host 側で Redis integration test を実行する場合は公開 port を使う。

```bash
TEST_REDIS_URL="redis://localhost:${REDIS_PORT:-6379}/1" \
  uv run pytest tests/integration/test_redis_rate_limiter.py -q
```

`AUTH_RATE_LIMIT_BACKEND` や Redis timeout / deadline / connection pool 設定は起動時に読み込まれるため、変更後は backend process/container を再起動する。

Redis 障害時の既定は `fail_closed` で、通常ユーザーの login も 429 になり得る。availability を優先する環境では `fail_open` を明示できるが、障害中は rate limit が一時的に効かない。どちらの場合も `auth_rate_limiter.redis_unavailable` log code で通常の bucket 到達と区別する。

Redis connection pool は `AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS` で worker ごとに上限を持ち、枯渇時は operation deadline の半分だけ接続取得を待つ。pool 枯渇は circuit breaker の連続失敗には数えず、同じ process では warning log を 1 秒に 1 回へ抑制する。既定 deadline 0.8 秒では、breaker が開く前の worst-case latency は login 失敗で最大 1.6 秒、register の一部 failure path で最大 2.4 秒である。同時 in-flight request が多いほど、この待ち時間を受ける request 数も増える。

production では rate limit 専用 Redis instance / DB、全 key の TTL、容量監視、`maxmemory-policy volatile-ttl` を推奨する。`allkeys-lru` は攻撃中の key を evict し得るため推奨しない。容量監視なしの `noeviction` は write failure と fail-closed の組み合わせで認証停止につながる。

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
