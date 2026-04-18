# 認証アーキテクチャ決定メモ（2026-04-18）

## 1. この文書の位置づけ

この文書は、`python-react-template` に認証基盤を入れるための**アーキテクチャ決定メモ**である。

- 目的は「何を採用し、何を採用しないか」を固定すること
- 実装手順や作業分解は別文書に切り出すこと
- 実装者が途中で認証方式や DB 方針を再議論しなくてよい状態を作ること

今回のレビューで判明した通り、旧版は「よく調べた設計メモ」ではあったが、「迷わず実装できる計画」ではなかった。
そのため、本稿は決定事項だけに責務を絞り、実装は別の 3 文書へ分離する。

---

## 2. このリポジトリで既に確定している事実

現時点のコードベースから、以下は前提として扱う。

- Backend は FastAPI + `Injector` + `SQLModel` 構成であり、レイヤは `controllers -> usecases -> services / models` を前提にしている
- Frontend は React + Vite + TanStack Router + React Query の SPA である
- Frontend の build 出力先は `backend/static/` であり、本番配信は backend 側の same-origin 配信に寄せやすい
- ローカル開発は `docker-compose.yaml` 上で frontend:3000 / backend:8000 に分離されている
- Backend には `pydantic-settings` が既に入っているため、設定管理は「新規導入」ではなく「整理・正規化」が主眼になる

このため、認証導入は単に API を足す話ではなく、次の 4 点を固定しないと着手順がぶれる。

1. ORM / migration / DB 接続の土台をどうするか
2. ブラウザ認証を Cookie セッションでやるか、JWT ハイブリッドでやるか
3. Frontend との接続を CORS 前提にするか、same-origin 前提にするか
4. PostgreSQL 固有機能とテスト戦略をどう整合させるか

---

## 3. 今回のスコープ

今回の認証導入は、**first-party の Web アプリ向け認証基盤の初期導入**に限定する。

このフェーズでやること:

- PostgreSQL を正式な永続層として導入する
- Alembic による migration 運用を開始する
- `users` / `auth_sessions` / `auth_audit_logs` を作る
- browser 向けのログイン / ログアウト / 現在ユーザー取得を成立させる
- Frontend 側で same-origin 前提の認証クライアントを整える

このフェーズでやらないこと:

- OIDC / 外部 IdP 連携
- MFA
- email verification
- password reset / forgot password
- RBAC / ABAC
- `logout-all` やセッション管理 UI
- Redis 併用のレート制御
- mobile / third-party API client 向けの token 発行

要するに、今回は「認証の全部」ではなく、**このテンプレートに最初に載せるべき最小で破綻しにくい browser auth** を決める。

---

## 4. 固定した 4 つの決定

## 4.1 永続化レイヤは `SQLModel` 継続 + Alembic 追加で進める

### 決定

- 既存の `SQLModel` は継続する
- ただし migration は Alembic を正式導入する
- PostgreSQL 接続は SQLAlchemy 2 系 async engine + `asyncpg` を使う
- 認証導入のタイミングで、既存コードを素の SQLAlchemy へ全面移行することはしない

### 理由

- 現在の backend ガイドとコードが `SQLModel` 前提で揃っているため、ここで ORM 方針まで全面反転するとスコープが膨らむ
- `SQLModel` は SQLAlchemy 2 系の上に乗っているので、モデル定義継続と Alembic 導入は両立できる
- 今必要なのは「認証を入れること」であり、「ORM リライト」ではない

### 実装上の含意

- `SQLModel` はエンティティ定義の層として使う
- 複雑な query や transaction 制御が必要な箇所では、service 層で SQLAlchemy の expression を使ってよい
- 今回の計画では `app/models/` を捨てない

---

## 4.2 ブラウザ認証は JWT ハイブリッドではなく、Opaque Session Cookie を採用する

### 決定

- 初期導入の browser auth は **opaque session cookie** を採用する
- Access Token / Refresh Token 方式は採用しない
- セッション識別子はランダム生成し、DB にはハッシュだけを保存する

### 理由

- このリポジトリは backend が frontend の成果物を same-origin 配信できる構造であり、browser auth に JWT を必須とする理由が薄い
- JWT ハイブリッドは refresh token rotation、再利用検知、token 種別管理、失効戦略まで同時に背負うため、初期導入としては重い
- first-party SPA + same-origin なら、Cookie セッションの方が設計・実装・運用の総コストが低い

### 実装上の含意

- `session_token` Cookie を `HttpOnly` で発行する
- `auth_sessions` テーブルに `session_token_hash` を保存し、生の token は保存しない
- `GET /api/auth/me` は session cookie から現在ユーザーを解決する
- 将来 mobile client や external API client が必要になった時点で、token-based auth を別途検討する

---

## 4.3 ブラウザ接続は same-origin を正とし、ローカル開発は Vite proxy で合わせる

### 決定

- 本番系のブラウザ通信は same-origin を前提にする
- ローカル開発では Vite dev server から backend へ `/api` proxy を張る
- browser auth の通常経路で CORS を前提にしない
- 状態変更系 API では CSRF 対策を必須にする

### 理由

- 既に frontend build が `backend/static/` に入る構造であり、本番 same-origin との整合が高い
- 開発時だけ origin が分かれる問題は proxy で吸収した方が、Cookie / 認証まわりの実装が単純になる
- CORS + credential + Cookie 調整を browser auth の常態にすると、local / dev / prod で挙動差が増える

### 実装上の含意

- Frontend の API 呼び出しは相対パスの `/api/...` に統一する
- `fetch` は `credentials: 'include'` を基本にする
- `session_token` Cookie は `HttpOnly`, `SameSite=Lax`, `Secure` は prod のみ必須にする
- `csrf_token` Cookie は JS から読めるよう `HttpOnly` を付けず、unsafe method では `X-CSRF-Token` header を必須にする
- `GET /api/auth/csrf` を用意して CSRF token bootstrap を行う

---

## 4.4 PostgreSQL を正式系とし、初期スキーマは PG 依存を絞ってテスト整合を取る

### 決定

- 認証基盤の正式 DB は PostgreSQL 17+ とする
- ただし phase 1 では `citext` や `uuidv7()` などの PG 固有機能を必須にしない
- ID は app 側生成の UUIDv4 を使う
- email は lower-case 正規化して `TEXT/VARCHAR + unique index` で運用する
- DB integration test は PostgreSQL で回す
- SQLite は DB 非依存の unit test にのみ使う

### 理由

- 認証周りは DB の実挙動差分が事故になりやすく、SQLite を正式な代替にすると危険
- 一方で phase 1 から `citext` や `uuidv7()` を前提にすると、導入・運用コストの割に得るものが少ない
- app 側で email 正規化し、ID を app 側で振れば、初期導入の複雑さを抑えられる

### 実装上の含意

- `users.email` は保存前に lower-case 化する
- unique 制約は lower-case 化済みの値に対して張る
- `tests/integration/` の DB 系テストは PostgreSQL を使って回す
- backend ガイド上の SQLite 方針は、認証領域については例外扱いにする

---

## 5. Phase 1 で採用する最小設計

## 5.1 テーブル

1. `users`
- `id`
- `email`
- `password_hash`
- `is_active`
- `created_at`
- `updated_at`
- `last_login_at`

2. `auth_sessions`
- `id`
- `user_id`
- `session_token_hash`
- `csrf_token_hash`
- `created_at`
- `last_seen_at`
- `expires_at`
- `revoked_at`
- `ip_address`
- `user_agent`

3. `auth_audit_logs`
- `id`
- `user_id` nullable
- `session_id` nullable
- `event_type`
- `detail_json` nullable
- `ip_address`
- `user_agent`
- `created_at`

`auth_identities` は今回作らない。OIDC 連携を本当に入れる時点で追加する。

## 5.2 API

phase 1 の API surface は以下に絞る。

- `GET /api/auth/csrf`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`

`logout-all`、`password/change`、`password/reset` は phase 2 以降に回す。

## 5.3 Cookie

- `session_token`
  - `HttpOnly`
  - `SameSite=Lax`
  - `Secure` は prod 必須
  - browser にのみ保持させる

- `csrf_token`
  - `HttpOnly` なし
  - `SameSite=Lax`
  - `Secure` は prod 必須
  - unsafe method で `X-CSRF-Token` header と一致必須

---

## 6. 今回の判断で捨てた案

### JWT Access + Refresh Token

今回は採用しない。

理由:

- same-origin browser auth に対して過剰
- 初回導入スコープを大きくしすぎる
- refresh token rotation と再利用検知を最初から背負う必要がない

### `citext` と `uuidv7()`

今回は採用しない。

理由:

- phase 1 で本質的でない
- local / CI / migration の複雑さが先に立つ
- app 側の正規化 + UUIDv4 で十分開始できる

### 外部 IdP 先行

今回は採用しない。

理由:

- このテンプレートに最初に必要なのは、自前 auth の基本骨格
- 外部 IdP はチーム運用・監査要件が固まってからの方が判断しやすい

---

## 7. 実装文書

この決定を前提に、実装は次の 3 文書へ分割する。

1. [20260418-auth-db-migration.md](./20260418-auth-db-migration.md)
2. [20260418-auth-backend-flow.md](./20260418-auth-backend-flow.md)
3. [20260418-auth-frontend-integration.md](./20260418-auth-frontend-integration.md)

分割方針:

- DB / migration / compose / test harness は 1 文書目に閉じる
- backend の認証フロー実装は 2 文書目に閉じる
- frontend の auth client / UI / dev proxy は 3 文書目に閉じる

これにより、認証方式と DB 方針を再議論せず、各層の作業を独立に進められる。

---

## 8. 参考にした一次情報

- FastAPI Security: OAuth2 + JWT
  https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
- OWASP Password Storage Cheat Sheet
  https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- SQLAlchemy AsyncIO Docs
  https://docs.sqlalchemy.org/20/orm/extensions/asyncio.html
- PostgreSQL UUID Functions
  https://www.postgresql.org/docs/current/functions-uuid.html
- Pydantic Settings
  https://docs.pydantic.dev/latest/concepts/pydantic_settings/
