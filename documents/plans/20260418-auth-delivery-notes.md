# Auth Delivery Notes

認証導入を 3 本の実装計画へ分割した結果、順序・環境変数・CI・E2E・本番前チェックは別ノートにまとめた方が読みやすい。
この文書は、その横断事項の single source of truth とする。

---

## 1. 実行順序と並列条件

実装順序の正:

1. `20260418-auth-db-migration.md`
2. `20260418-auth-backend-flow.md`
3. `20260418-auth-frontend-integration.md`

理由:

- backend auth は DB schema と Alembic が先に固まらないと不安定
- frontend の protected route は backend の `/api/auth/me` と error semantics が固まってからの方が安全

限定的に並列で進めてよいもの:

- frontend の `ApiError` / `apiClient` / Vite proxy は backend schema 完成後であれば先行可能
- ただし protected route と login redirect は backend の contract test が通った後に進める

各計画の Done Definition:

- DB plan:
  - `manage.py db-upgrade` / `db-downgrade` が通る
  - PostgreSQL integration test が test 間 clean で安定する
  - `backend/AGENTS.md` の DB テスト方針と Alembic 導線が更新される

- Backend plan:
  - register / login / me / logout の happy path と failure path が通る
  - session expiry / revoke / CSRF / rate limiting の責務がコード上で一意になる
  - `backend/AGENTS.md` の認証例外が更新される

- Frontend plan:
  - `ApiError` で 401 とそれ以外を分離する
  - `useAuthSession().error` は未ログイン扱いに潰さず保持する。phase 1 では専用表示を作らず、route / global error UI が入るまでは header 等の auth UI には出さない
  - `/login` と `/app` の導線が通る
  - logout 後に `/login` へ戻る
  - `frontend/AGENTS.md` に `organisms/` と auth route guard の運用が反映される

---

## 2. 環境変数一覧

phase 1 で使う環境変数は次に固定する。

### backend

- `ENVIRONMENT`
  - `local`, `development`, `test`, `production`

- `DATABASE_URL`
  - runtime 用
  - 例: `postgresql+asyncpg://app:app@localhost:5432/app`

- `ALEMBIC_DATABASE_URL`
  - Alembic 用
  - 例: `postgresql://app:app@localhost:5432/app`

- `TEST_DATABASE_URL`
  - integration test 用
  - 例: `postgresql+asyncpg://app:app@localhost:5432/app_test`

- `DATABASE_POOL_SIZE`
  - 既定値 `10`

- `DATABASE_MAX_OVERFLOW`
  - 既定値 `20`

- `DATABASE_POOL_RECYCLE_SECONDS`
  - 既定値 `1800`

- `DATABASE_ECHO`
  - 既定値 `false`

- `AUTH_SESSION_ABSOLUTE_TTL_SECONDS`
  - 既定値 `604800`

- `AUTH_SESSION_IDLE_TTL_SECONDS`
  - 既定値 `86400`

- `AUTH_RATE_LIMIT_WINDOW_SECONDS`
  - 既定値 `900`

- `AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP`
  - 既定値 `5`

- `AUTH_RATE_LIMIT_ATTEMPTS_PER_IP`
  - 既定値 `20`

### frontend

- `VITE_BACKEND_ORIGIN`
  - dev proxy 用
  - 既定値 `http://localhost:8000`

補足:

- 本番 same-origin では frontend から backend origin を直接設定しない
- frontend の API 呼び出しは常に `/api/...` 相対パスを使う

---

## 3. CI 方針

phase 1 の CI は、少なくとも次を満たす。

1. PostgreSQL 17 service を起動する
2. backend に対して `TEST_DATABASE_URL` を注入する
3. `cd backend && uv run python manage.py db-upgrade`
4. `cd backend && uv run pytest`
5. `cd backend && uv run isort . --check-only && uv run yapf -dr app/`
6. `cd frontend && npm run check`
7. `cd frontend && npm test`
8. `cd frontend && npm run build`

pytest の運用:

- 認証の PostgreSQL 依存テストには `integration` marker を付ける
- auth 追加後も、fast path と full path を分けたければ `not integration` と `integration` を job 分離してよい
- ただし template のデフォルト CI では、auth 領域は PostgreSQL 付きの full path を通す

---

## 4. 手動 E2E 確認シナリオ

最低限、次のシナリオを毎回回す。

1. `docker compose up -d postgres backend frontend`
2. `/login` を開く
3. 間違った credential で login し、`401` 系 UI が出ることを確認する
4. backend fixture か API でユーザーを作成する
5. 正しい credential で login し、`/app` に遷移することを確認する
6. `/api/auth/me` が現在ユーザーを返すことを確認する
7. ブラウザリロード後も `/app` を維持することを確認する
8. logout し、`/login` に戻ることを確認する
9. その状態で `/app` に直接アクセスし、`/login` にリダイレクトされることを確認する

---

## 5. 本番前チェックリスト

- frontend と backend を same-origin で配信する
- HTTPS 終端の位置を明確化する
- `uvicorn --proxy-headers` 相当を正とし、reverse proxy から `X-Forwarded-Proto` を渡して `request.url.scheme` が HTTPS として解決されるようにする
- controller の `is_secure_request()` は proxy 設定漏れへの防御的 fallback として残す
- `session_token` は本番で必ず `Secure=true`
- CORS はデフォルトで閉じ、same-origin 以外を不要に許可しない
- in-memory rate limiter は multi-instance 本番では shared store に置き換える
- `.env` 直置き secrets を本番へ持ち込まない

---

## 6. 実装と同時に更新する文書

- `backend/AGENTS.md`
  - auth 領域の DB テストは PostgreSQL を正とすること
  - `manage.py db-upgrade` / `db-downgrade` を主要コマンドへ追加すること
  - SQLite 方針が auth 領域には適用されないこと

- `frontend/AGENTS.md`
  - `components/organisms/` を正式な配置先として明記すること
  - auth route guard が TanStack Router `beforeLoad` を使うこと
  - frontend の API 呼び出しが相対 `/api/...` を正とすること
