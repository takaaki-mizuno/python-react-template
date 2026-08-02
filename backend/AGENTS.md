# Backend (FastAPI)

FastAPI ベースの Python バックエンド。Single source of truth は **ルートの `/AGENTS.md`** であり、本ファイルはその差分 (Backend 固有) を記述する。

## 技術スタック

- Python 3.12+
- パッケージ管理: **uv** (`uv.lock` を正)
- Web フレームワーク: FastAPI 0.128+
- ORM / モデル: SQLModel
- DI: Injector
- CLI: Typer (`manage.py`)
- 非同期 DB ドライバ: aiosqlite (非 auth の既定), asyncpg (auth / PostgreSQL)
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

## API 設計

- REST 規約に従う。設計時は `.claude/skills/restful-api-design` を参照
- レスポンスは `usecases` 層が返す DTO/モデルを `controllers` で整形
- controller は `request.app.state.injector.get(...)` を直接呼ばず、`Depends` dependency で依存を受ける
- auth の `register` / `login` / `logout` は FastAPI `Depends` の共通 CSRF 検証を必ず通す
- auth の CSRF は cookie/header の timing-safe 比較に加え、session がある unsafe request では `auth_sessions.csrf_token_hash` と照合する
- auth の session 検証は `require_current_session` dependency から usecase へ委譲し、controller に DB session を持たせない
- auth controller / usecase / interface は `AuthenticatedSessionContext` を `app.models.auth_context` から import する
- HTTP error は error envelope で返す。新規 controller は `api_error()` または共通例外 handler を使う
- in-memory rate limiter は single-process の最小防御であり、複数 worker / 複数 instance の本番運用では共有 store へ置き換える
- production では `/docs`、`/redoc`、`/openapi.json` を公開しない

## テスト

- Pytest を使用 (依存に未追加なら `uv add --dev pytest pytest-asyncio` から)
- 単体テスト: `tests/unit/`、結合テスト: `tests/integration/` を推奨
- DB を使うテストは実 DB (SQLite in-memory) を使用しモックしない
- auth integration test は `TEST_DATABASE_URL` が指す PostgreSQL を使い、test 間 cleanup は auth tables の `TRUNCATE ... CASCADE` で保証する

## Phase 1 基盤規約

- transaction 境界は `UnitOfWorkInterface` に置く。repository に `transaction()` を追加しない
- nested `UnitOfWorkInterface.transaction()` は savepoint ではなく外側 transaction へ join する
- 別 instance の `UnitOfWorkInterface.transaction()` / `session_scope()` を同一 async context の transaction 内で開くことは禁止。実装は fail fast する
- 1つの UoW transaction session を `asyncio.gather()` / `create_task()` で並行利用しない
- Phase 1 完了時点では `Config.ENVIRONMENT` の既定値は docs 非公開のため `production`、`AuthSettings.ENVIRONMENT` の既定値は cookie secure 反転前のため `local` で意図的に分裂している
- Phase 2 の `P1-12` で `AuthSettings` 側も安全側へ反転するまで、上記 2 つの既定値を片方へ安易に揃えない
- local 開発で docs を見たい場合は、`backend/.env.example` を元に `backend/.env` を作り、`ENVIRONMENT=local` を明示する

## 関連スキル

- `python-development` — Python 全般
- `database-schema-design` — モデル設計
- `restful-api-design` — API 設計
