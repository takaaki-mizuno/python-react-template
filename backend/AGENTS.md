# Backend (FastAPI)

FastAPI ベースの Python バックエンド。Single source of truth は **ルートの `/AGENTS.md`** であり、本ファイルはその差分 (Backend 固有) を記述する。

## 技術スタック

- Python 3.12+
- パッケージ管理: **uv** (`uv.lock` を正)
- Web フレームワーク: FastAPI 0.128+
- ORM / モデル: SQLModel
- DI: Injector
- CLI: Typer (`manage.py`)
- 非同期 DB ドライバ: asyncpg (PostgreSQL)
- 設定: python-dotenv
- Lint / Format: isort + yapf

## ディレクトリ構成

```
backend/
├── manage.py                # Typer CLI エントリ
├── pyproject.toml           # 依存・ツール設定
├── uv.lock
├── app/
│   ├── bootstrap/           # アプリ起動・DI コンテナ初期化
│   ├── config/              # 環境変数 / 設定オブジェクト
│   ├── controllers/         # FastAPI ルータ (HTTP 層)
│   ├── interfaces/          # 抽象インターフェース (リポジトリ等)
│   ├── libraries/           # 横断的ユーティリティ
│   ├── models/              # SQLModel エンティティ
│   ├── services/            # 永続化・外部連携
│   └── usecases/            # ビジネスロジック (アプリケーション層)
└── static/                  # frontend ビルド成果物の配置先 (生成物)
```

レイヤ依存方向は **controllers → usecases → services / models** (一方向)。
controllers から services を直接呼ぶのは禁止 (テスト容易性のため usecases を経由)。

## 主要コマンド

```bash
# サーバ起動 (reload 有効、port 8000)
python manage.py serve

# 依存追加
uv add <package>
uv add --dev <package>     # 開発依存

# 同期 (lock からインストール)
uv sync

# Lint / Format
uv run isort .
uv run yapf -ir app/

# テスト
uv run pytest
```

## コードスタイル

- import: isort のセクション順 (stdlib / 3rd party / local)
- フォーマット: yapf (設定は `pyproject.toml`)
- 型ヒント: 関数シグネチャに必須。`Any` は最終手段
- 命名: `snake_case` (関数/変数), `PascalCase` (クラス), `SCREAMING_SNAKE_CASE` (定数)

## 設定

- `AuthSettings`は`CoreModule`のproviderで一度だけ生成し、Injectorのsingletonとして共有する
- controllerは`Depends(get_auth_settings)` dependency経由で起動時snapshotを取得し、requestごとに`AuthSettings`を再生成しない
- `backend/.env`または認証関連環境変数を変更した場合は、backend process/containerを再起動する
- 設定hot reloadは提供しない。必要になった場合は全consumerを同時更新できる別設計として計画する

## モデル / DB

- 新規テーブル追加時はまず `documents/plans/` に ER 設計を残す
- スキーマ変更時はマイグレーション戦略を**事前にユーザー確認**
- auth 領域の永続化は PostgreSQL を正とし、SQLite in-memory は auth の DB integration test には使わない
- auth migration の主要コマンドは `python manage.py db-upgrade` / `python manage.py db-downgrade`
- Alembic revision 生成は `uv run alembic revision --autogenerate ...` を補助用途として使い、生成後に timezone-aware column / expression index / JSONB を必ず手で確認する
- 初期 revision を書き換える場合、既存 DB に残る旧 PK/FK 名は Alembic autogenerate / `db-check` だけでは検出できない。正典確認は fresh test DB を作り直して初期 migration から適用し、`pg_constraint` または targeted test で制約名を確認する

## API 設計

- REST 規約に従う。設計時は `.claude/skills/restful-api-design` を参照
- レスポンスは `usecases` 層が返す DTO/モデルを `controllers` で整形
- controller は `request.app.state.injector.get(...)` を直接呼ばず、`Depends` dependency で依存を受ける
- unsafe `/api` request は純 ASGI の CSRF middleware が既定で検証する。新規 unsafe endpoint に個別 `Depends(require_csrf)` を書かない
- routing 前に CSRF middleware が走るため、CSRF なしの `POST /api/unknown` は 404 ではなく 403 になる。これは unsafe API request を先に拒否する意図的な契約である
- CSRF 除外 path を `AUTH_CSRF_EXEMPT_PATHS` に追加する場合は、なぜ CSRF ではなく別の state 検証で守られるのかを計画書に書く
- auth の CSRF は cookie/header の timing-safe 比較に加え、session がある unsafe request では `auth_sessions.csrf_token_hash` と照合する
- auth の session 検証は `require_current_session` dependency から usecase へ委譲し、controller に DB session を持たせない
- auth controller / usecase / interface は `AuthenticatedSessionContext` を `app.models.auth_context` から import する
- HTTP error は error envelope で返す。新規 controller は `api_error()` または共通例外 handler を使う
- in-memory rate limiter は single-process の最小防御であり、複数 worker / 複数 instance の本番運用では共有 store へ置き換える
- login/register 失敗 rate limit は IP、email+IP、email 単独の 3 bucket で判定する。bucket への記録は失敗時だけ行い、成功時に IP bucket や email 単独 bucket を消してはいけない
- duplicate email など register 由来の失敗は、login の email 単独 bucket へ記録しない。register 409 だけで任意アカウントを email 単位にロックアウトできる経路を作らないためである
- rate limit 到達後の request は audit log INSERT を行わず即時に 429 へ変換する。通常の認証失敗は監査するが、block 後の連打で DB 書き込みを増幅させない
- register 成功 rate limit は `AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP` と `AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS` の別 bucket で扱う
- in-memory rate limiter は触った bucket だけを trim し、`AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE` で scope ごとの bucket 数を bounded にする。上限到達時は active bucket を silent eviction せず、oldest bucket から expired bucket を必要な分だけ償却 reclaim する。expired 掃除後も満杯なら新規 bucket は作らず fail-open で warning を出す。request ごとの全 bucket 走査や shared overflow bucket を追加しない
- bucket 上限到達後の fail-open は全体封鎖を避けるための single-process 向けトレードオフであり、飽和中の新規キーは per-email 防御の追跡対象外になる。本番でこのリスクを許容できない場合は、Redis 等の共有 store または O(1) メモリの rate limiter へ置き換える
- `AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP` / `AUTH_RATE_LIMIT_ATTEMPTS_PER_IP` は Phase 2 で削除され、`AUTH_RATE_LIMIT_FAILURES_*` へ改名された。旧キーは `extra="ignore"` で無視されるため、既存 `.env` は必ず置き換える
- production では `/docs`、`/redoc`、`/openapi.json` を公開しない

## テスト

- Pytest を使用 (依存に未追加なら `uv add --dev pytest pytest-asyncio` から)
- 単体テスト: `tests/unit/`、結合テスト: `tests/integration/` を推奨
- DB を使うテストは実 DB (SQLite in-memory) を使用しモックしない
- auth integration test は `TEST_DATABASE_URL` が指す PostgreSQL を使い、test 間 cleanup は auth tables の `TRUNCATE ... CASCADE` で保証する

## Phase 2 認証セキュリティ規約

- 本番 cookie は `AUTH_COOKIE_SECURE` 未設定なら Secure になる。local HTTP だけ `.env` で `AUTH_COOKIE_SECURE=false` を明示する。本番で `false` を使わない
- auth cookie の Secure 判定に `ENVIRONMENT` を使わない。docs 制御などの環境別挙動は `Config.ENVIRONMENT` だけが担う
- proxy 配下では `AUTH_TRUSTED_PROXY_IPS` に信頼できる直近 proxy の IP/CIDR だけを書く。不正値と `0.0.0.0/0` / `::/0` は起動時の settings validation で落とす。任意の `X-Forwarded-For` は信じず、XFF は右から走査し、不正 token に当たった場合は direct peer へ fallback する
- password-only user と OAuth-only user を区別するため、`users.password_hash` は nullable である。password login では `None` を必ず認証不可にし、dummy hash verify で timing 差を広げない
- Argon2 hash/verify は専用 `PasswordHashExecutor` で実行し、`AUTH_PASSWORD_HASH_CONCURRENCY` で同時実行数を制限する。既定値 4 は Argon2 m=64MiB を前提に約 256MiB までを目安にする。worker 数や memory limit を見ずに上げない
- password hash 過負荷時は 503 ではなく executor queue 待ちによるレイテンシ増加として現れる
- 認証済み request の session touch は `AUTH_SESSION_TOUCH_INTERVAL_SECONDS` で間引く。設定値が idle TTL に対して長すぎる場合は実効値を `AUTH_SESSION_IDLE_TTL_SECONDS // 2` に clamp する
- Phase 2 時点では register 成功時に即 session を発行するため、duplicate email を完全には秘匿しない。409 status が残る限り、code/message だけを generic にしても列挙耐性にならないため、その設定分岐は追加しない
- 完全な register email 列挙耐性が必要な派生プロジェクトでは、email verification または invite flow を設計し、register response を非同期受付型へ変更する

## Phase 1 基盤規約

- transaction 境界は `UnitOfWorkInterface` に置く。repository に `transaction()` を追加しない
- nested `UnitOfWorkInterface.transaction()` は savepoint ではなく外側 transaction へ join する
- 別 instance の `UnitOfWorkInterface.transaction()` / `session_scope()` を同一 async context の transaction 内で開くことは禁止。実装は fail fast する
- 1つの UoW transaction session を `asyncio.gather()` / `create_task()` で並行利用しない
- `AuthSettings.ENVIRONMENT` は Phase 2 で削除された。auth cookie security には環境名を使わない
- local 開発で docs を見たい場合は、`backend/.env.example` を元に `backend/.env` を作り、`ENVIRONMENT=local` を明示する

## 関連スキル

- `python-development` — Python 全般
- `database-schema-design` — モデル設計
- `restful-api-design` — API 設計
