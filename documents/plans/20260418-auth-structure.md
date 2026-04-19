# 認証アーキテクチャ決定メモ（2026-04-18）

## 1. この文書の位置づけ

この文書は、`python-react-template` に認証基盤を入れるための**アーキテクチャ決定メモ**である。

- 目的は「何を採用し、何を採用しないか」を固定すること
- 実装手順や作業分解は別文書に切り出すこと
- 実装者が**主要な認証方式・DB 方針・検証方針**を途中で再議論しなくてよい状態を作ること

前版は設計メモとしては有用だったが、実装エージェントに渡すには決定漏れが多かった。
そのため本稿では、phase 1 を始める前に固定しておくべき判断を追加し、実装は別の計画文書へ分離する。

---

## 2. このリポジトリで既に確定している事実

- Backend は FastAPI + `Injector` + `SQLModel` 構成であり、レイヤは `controllers -> usecases -> services / models` を前提にしている
- Frontend は React + Vite + TanStack Router + React Query の SPA である
- Frontend の build 出力先は `backend/static/` であり、本番配信は backend 側の same-origin 配信に寄せやすい
- ローカル開発は `docker-compose.yaml` 上で frontend:3000 / backend:8000 に分離されている
- Backend には `pydantic-settings` が既に入っているため、設定管理は「新規導入」ではなく「整理・正規化」が主眼になる

このため、認証導入は単に API を足す話ではなく、次の論点を最初に固定しないと着手順がぶれる。

1. ORM / migration / DB 接続の土台をどうするか
2. browser auth を Cookie session でやるか、JWT 系でやるか
3. frontend との接続を CORS 前提にするか、same-origin 前提にするか
4. PostgreSQL 固有機能とテスト戦略をどう整合させるか
5. password / session / CSRF / rate limiting の最低ラインをどこに置くか

---

## 3. 今回のスコープ

今回の認証導入は、**first-party の Web アプリ向け認証基盤の初期導入**に限定する。

このフェーズでやること:

- PostgreSQL を正式な永続層として導入する
- Alembic による migration 運用を開始する
- `users` / `auth_sessions` / `auth_audit_logs` を作る
- browser 向けの register / login / logout / current user 取得を成立させる
- frontend 側で same-origin 前提の認証クライアントと protected route を整える

このフェーズでやらないこと:

- OIDC / 外部 IdP 連携
- MFA
- password reset / email verification
- RBAC / ABAC
- Redis 前提の分散 rate limiting
- mobile / third-party API client 向け token 発行
- OpenAPI からの型自動生成

要するに、今回は「認証の全部」ではなく、**このテンプレートに最初に載せるべき最小で破綻しにくい browser auth** を決める。

---

## 4. 固定したアーキテクチャ判断

## 4.1 永続化レイヤは `SQLModel` 継続 + Alembic 追加で進める

### 決定

- 既存の `SQLModel` は継続する
- migration は Alembic を正式導入する
- PostgreSQL 接続は SQLAlchemy 2 系 async engine + `asyncpg` を使う
- 認証導入のタイミングで、既存コードを素の SQLAlchemy へ全面移行することはしない
- phase 1 の互換ターゲットは PostgreSQL 15+ とし、local / CI の基準イメージは PostgreSQL 17 を使う

### 理由

- 現在の backend ガイドとコードが `SQLModel` 前提で揃っているため、ここで ORM 方針まで全面反転するとスコープが膨らむ
- `SQLModel` は SQLAlchemy 2 系の上に乗っているので、モデル定義継続と Alembic 導入は両立できる
- phase 1 では PostgreSQL 17 固有機能を使わないため、互換ターゲットを不必要に上げる理由がない

### 実装上の含意

- `SQLModel` はエンティティ定義の層として使う
- 複雑な query や transaction 制御が必要な箇所では、service 層で SQLAlchemy expression を使ってよい
- engine のデフォルトは `pool_size=10`、`max_overflow=20`、`pool_recycle=1800`、`pool_pre_ping=True`、`echo=False` とする
- migration 操作の正は `manage.py` のラッパーコマンドとし、`alembic` 直打ちは補助用途に留める
- `aiosqlite` は既存テンプレートの非認証領域がまだ参照しているため、この作業では削除しない

---

## 4.2 browser auth は opaque session cookie を採用する

### 決定

- 初期導入の browser auth は **opaque session cookie** を採用する
- stateless JWT を browser session の正としない
- access token + refresh token のペアも phase 1 では採用しない
- セッション識別子は高 entropy のランダム値を使い、DB にはハッシュだけを保存する

### 理由

- このリポジトリは backend が frontend の成果物を same-origin 配信できる構造であり、browser auth に JWT を必須とする理由が薄い
- stateless JWT も access/refresh 方式も、失効・再利用検知・種別管理・保管戦略まで同時に背負うため、初期導入としては重い
- first-party SPA + same-origin なら、Cookie session の方が設計・実装・運用の総コストが低い

### 実装上の含意

- `session_token` Cookie を `HttpOnly` で発行する
- `auth_sessions.session_token_hash` に SHA-256 ハッシュを保存し、生 token は保存しない
- `GET /api/auth/me` は session cookie から現在ユーザーを解決する
- 将来 mobile client や external API client が必要になった時点で、token-based auth を別途検討する

---

## 4.3 password / email / session の基準を先に固定する

### password hashing

- `pwdlib[argon2]` を採用する
- `PasswordHash.recommended()` のデフォルトを phase 1 の標準値として許容する
- phase 1 では Argon2 パラメータを独自に上書きしない

理由:

- FastAPI 公式方針と整合する
- `passlib` より現在の推奨寄りで、余計な選択肢を増やさずに済む
- phase 1 の段階でコストパラメータをチューニングするより、まず一貫した安全な初期値を採る方がよい

### email validation

- request DTO では `EmailStr` を使う
- 保存前に `trim + lower-case` で canonicalize する
- DB では `LOWER(email)` の unique index を張り、app 側の漏れがあっても重複登録を防ぐ

### password policy

- password 長は `12 <= len(password) <= 128` を最低条件とする
- phase 1 では大文字・小文字・数字・記号の composition rule は採用しない

理由:

- composition rule は UX を悪化させやすく、実効性も低い
- 最低長を明示し、argon2id を使う方が template の初期値として素直

### session lifetime

- absolute timeout は 7 日
- idle timeout は 24 時間
- sliding renewal を有効にし、認証済みリクエスト成功時に `last_seen_at` と `expires_at` を更新する
- `expires_at` は `min(created_at + absolute_ttl, last_seen_at + idle_ttl)` を保存する
- phase 1 では認証済みリクエストごとに session を touch する。高頻度 API で write 負荷が問題になったら、前回 touch から N 秒経過時だけ更新する debounce を phase 2 で検討する

### session fixation

- `register` と `login` は、既存の `session_token` Cookie があればそれを revoke してから新規 session を発行する
- `logout` は現在 session を revoke する
- phase 2 以降の `password change` は全 session revoke を前提にする

---

## 4.4 browser transport は same-origin を正とし、CSRF は defense-in-depth で二重化する

### 決定

- 本番系のブラウザ通信は same-origin を前提にする
- ローカル開発では Vite dev server から backend へ `/api` proxy を張る
- browser auth の通常経路で CORS を前提にしない
- `SameSite=Lax` を採りつつ、unsafe method では double-submit cookie 方式の CSRF 検証も行う

### 理由

- 本番配信経路は same-origin に寄せやすく、ここを正とする方が cookie 運用が単純
- `SameSite=Lax` は有効だが、reverse proxy 設定ミスや same-site 判定の想定ズレまで完全に防げない
- そのため、phase 1 でも CSRF token を明示的に検証して defense-in-depth を取る

### 実装上の含意

- frontend の API 呼び出しは相対パスの `/api/...` に統一する
- `fetch` は `credentials: 'include'` を基本にする
- `session_token` Cookie は `HttpOnly`, `SameSite=Lax`, `Secure` は prod のみ必須にする
- `csrf_token` Cookie は JS から読めるよう `HttpOnly` を付けず、unsafe method では `X-CSRF-Token` header と一致必須にする
- CSRF 検証は controller 内の手書き関数ではなく、FastAPI `Depends` で共通化する

---

## 4.5 最低限の防御・エラー規約・frontend ガード方式も決める

### rate limiting

- phase 1 では in-memory の best-effort limiter を入れる
- 対象は `register` / `login`
- 基本値は「同一 IP + email に対して 15 分で 5 回」「同一 IP 全体で 15 分で 20 回」とする
- phase 1 では `register` と `login` が同じ bucket を共有する。登録直後の login も同じ試行回数を消費する前提にする
- これは single-process 前提の最小防御であり、multi-instance 本番では共有ストアへの置換が必要

### audit event vocabulary

- phase 1 で使う `event_type` は次に固定する
  - `register_success`
  - `register_failed`
  - `login_success`
  - `login_failed`
  - `logout`
  - `session_rejected`
- `detail_json` は phase 1 では常に `NULL` とし、event_type ごとの追加情報は phase 2 以降で入れる

### backend error semantics

- invalid credential は「メールアドレスが存在しない」と「password が違う」を区別せず `401 Unauthorized` に統一する
- duplicate email は `409 Conflict` に統一する
- DTO validation と password policy 違反は `422`
- rate limit は `429`

### frontend error semantics

- frontend は `ApiError` を使って `status` と `body` を保持する
- `401` だけを「未ログイン」に解釈する
- `500` / network error / `422` は `null` に潰さず、UI 側でエラーとして扱う

### protected route strategy

- protected route は TanStack Router の `beforeLoad` で守る
- phase 1 では最低 1 つの protected route (`/app`) を作り、auth 導線を実証する

### API 型の単一ソース

- phase 1 の auth payload は frontend 側に手書き TS 型を置く
- OpenAPI からの型生成はまだ入れない

理由:

- auth API の面積がまだ小さい
- template 初期状態に generator 依存を増やすコストの方が大きい

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

## 5.3 frontend 最小導線

- `/login` を作る
- `/app` を protected route として作る
- login 成功時は `redirect` query があればそこへ、なければ `/app` へ遷移する
- logout 成功時は `/login` へ戻す

---

## 6. 今回の判断で捨てた案

### stateless JWT

今回は採用しない。

理由:

- first-party browser auth の正としては過剰
- token 失効とクライアント保管戦略を複雑化させる

### access token + refresh token

今回は採用しない。

理由:

- refresh token rotation / reuse detection を phase 1 から背負う必要がない
- same-origin browser auth の MVP としては重い

### `citext` と `uuidv7()`

今回は採用しない。

理由:

- phase 1 で本質的でない
- PG 依存を減らして migration / test / local setup を素直にしたい
- app 側 UUIDv4 と `LOWER(email)` index で十分開始できる

### 外部 IdP 先行

今回は採用しない。

理由:

- このテンプレートに最初に必要なのは自前 auth の基本骨格
- チーム運用・監査要件が固まる前に決める話ではない

---

## 7. 実装文書

この決定を前提に、実装は次の 3 文書へ分割する。

1. [20260418-auth-db-migration.md](./20260418-auth-db-migration.md)
2. [20260418-auth-backend-flow.md](./20260418-auth-backend-flow.md)
3. [20260418-auth-frontend-integration.md](./20260418-auth-frontend-integration.md)

加えて、順序・環境変数・CI・E2E・本番チェックは横断ノートにまとめる。

- [20260418-auth-delivery-notes.md](./20260418-auth-delivery-notes.md)

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
