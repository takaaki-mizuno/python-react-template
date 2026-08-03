# python-react-template

FastAPI backend、React + Vite frontend、PostgreSQL 17を同居させたモノレポです。frontendのbuild成果物は`backend/static/`へ出力され、backendから静的配信できます。

認証機能はPostgreSQLを正とし、Alembicで`users`、`auth_sessions`、`auth_audit_logs`を管理します。

## 前提

- Docker EngineとDocker Compose v2が利用できる
- hostからbackendのCLIやtestを実行する場合はPython 3.12+と`uv`が利用できる
- 特記がない`docker compose`、`cp`コマンドはrepository rootで実行する
- `app_test`はこのrepository専用で、保持対象データを入れない

## 初回起動

ルートの`.env`はDocker Composeのポート設定、`backend/.env`はbackendとDB・認証設定に使用します。

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

コンテナをbuildして起動します。

```bash
docker compose up -d --build postgres backend frontend
docker compose ps
```

`docker compose ps`で`postgres`が`healthy`、`backend`と`frontend`が`Up`になるまで待ってからmigrationを実行してください。

初回起動時またはmigration追加後は、runtime DBの`app`へmigrationを適用します。

```bash
docker compose exec -T backend \
  uv run python manage.py db-upgrade --revision head
```

デフォルトのアクセス先:

- Frontend: `http://localhost:3000`
- Backend health check: `http://localhost:8000/api/healthz`

portを上書きした場合はアクセス先も同じ値へ読み替えてください。

ポートが使用中の場合はルート`.env`を変更するか、起動時に上書きできます。

```bash
FRONTEND_PORT=3001 BACKEND_PORT=8001 POSTGRES_PORT=5433 \
  docker compose up -d --build
```

## PostgreSQL構成

Docker Composeはローカル開発用に次のDBを使用します。

| DB | 用途 | 接続先 |
|---|---|---|
| `app` | runtime DB | `postgresql://app:app@localhost:5432/app`（標準host port） |
| `app_test` | migration round-trip・認証integration test専用 | `postgresql://app:app@localhost:5432/app_test`（標準host port） |

`app_test`は`docker/postgres/init/01-create-test-database.sql`により、PostgreSQL volumeの初回作成時に生成されます。既存volumeが初期化スクリプト作成前のものなら、存在を確認してから一度だけ作成します。

```bash
docker compose exec -T postgres \
  psql -U app -d postgres -tAc \
  "SELECT datname FROM pg_database WHERE datname = 'app_test';"

docker compose exec -T postgres \
  psql -U app -d postgres -c "CREATE DATABASE app_test;"
```

2つ目のコマンドは確認結果が空の場合だけ実行してください。
正常時の確認結果は`app_test`です。`CREATE DATABASE`にはlocal用`app` roleのdatabase作成権限が必要です。

## DB migration

migrationのCLIは`backend/manage.py`から実行します。

```bash
(
  cd backend
  uv run python manage.py db-upgrade --help
  uv run python manage.py db-downgrade --help
)
```

### Runtime DBを最新化する

Docker Compose内の`app` DBへ適用する場合:

```bash
docker compose exec -T backend \
  uv run python manage.py db-upgrade --revision head
```

hostから実行する場合:

```bash
(
  cd backend
  export APP_POSTGRES_PORT=5432
  DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app" \
    uv run python manage.py db-upgrade --revision head
)
```

`APP_POSTGRES_PORT`はルート`.env`の`POSTGRES_PORT`と同じ値にしてください。

### Downgradeする

直前のrevisionへ戻す例:

```bash
(
  cd backend
  export APP_POSTGRES_PORT=5432
  DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app" \
    uv run python manage.py db-downgrade --revision=-1
)
```

`db-downgrade`はtableやデータを削除し得る破壊的操作です。実行前に接続先DB、対象revision、保持対象データの有無を確認してください。共有環境や本番DBで安易に実行しないでください。

### 専用test DBでround-tripを確認する

新規migrationやdowngrade変更時は、保持対象データを含まない`app_test`だけを対象に、upgrade → downgrade → upgradeを確認します。以下はすべてrepository rootで実行し、事前確認とmigrationを同じCompose network上のPostgreSQLへ向けます。

```bash
docker compose exec -T postgres \
  psql -U app -d app_test -tAc \
  "SELECT current_database(), current_user;"
```

`app_test|app`が返ることを確認してから実行します。

```bash
docker compose exec -T \
  -e DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/app_test \
  backend uv run python manage.py db-upgrade --revision head

docker compose exec -T \
  -e DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/app_test \
  backend uv run python manage.py db-downgrade --revision base

docker compose exec -T \
  -e DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/app_test \
  backend uv run python manage.py db-upgrade --revision head
```

`--revision base`はtest DB内のmigration管理対象tableをすべて削除します。`app`や共有DBへ接続していないことを必ず確認してください。

### Migrationを追加する

ER設計とmigration方針をrepository rootの`documents/plans/`へ記録し、schema変更の合意後にrevisionを作成します。modelを更新し、生成元には専用`app_test`を使います。

先に`app_test`へ既存migrationの`head`を適用します。その後、次の`current`と`heads`が同じrevisionを示し、`current`に`(head)`が表示されることを確認してからautogenerateします。`manage.py` 経由だけでなく bare `alembic` コマンドも `DATABASE_URL` の明示設定を必須にしているため、この手順では同じ shell で `DATABASE_URL` を export してから実行します。

```bash
(
  cd backend
  export APP_POSTGRES_PORT=5432
  export DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app_test"
  uv run python manage.py db-upgrade --revision head
  uv run alembic current
  uv run alembic heads
  uv run alembic revision --autogenerate -m "describe schema change"
)
```

`APP_POSTGRES_PORT`はルート`.env`の`POSTGRES_PORT`と同じ値にしてください。head確認が一致しない場合はrevisionを生成せず、接続先とmigration履歴を修正します。

生成ファイルは`backend/alembic/versions/`へ出力されます。

自動生成結果はそのまま採用せず、特に次を確認します。

- upgradeとdowngradeが対になっている
- PostgreSQL固有のexpression index・JSONB・constraintが意図どおりである
- 日時columnがtimezone-awareである
- 既存データの移行方法とrollback時のdata lossが明確である

確認後はrepository rootでbackend imageを更新し、前節の`app_test` round-tripと後述の品質ゲートを実行します。

```bash
docker compose up -d --build backend
```

## PostgreSQL付き認証テスト

認証integration testはSQLiteへfallbackせず、`TEST_DATABASE_URL`が指すPostgreSQLを使います。環境変数がない場合はskipされるため、次の形で明示的に実行してください。

事前にPostgreSQLを起動し、`app_test`の存在を確認して、前節の`db-upgrade --revision head`を`app_test`へ適用してください。test自体はschemaを作成せず、test間で認証tableを`TRUNCATE ... CASCADE`します。

host接続例は標準port`5432`です。ルート`.env`の`POSTGRES_PORT`を変更した場合は、`APP_POSTGRES_PORT`へ同じ値を設定します。

```bash
(
  cd backend
  export APP_POSTGRES_PORT=5432
  TEST_DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app_test" \
    uv run pytest
)
```

integration testはtest間で認証tableを`TRUNCATE ... CASCADE`します。`TEST_DATABASE_URL`に`app`、共有DB、本番DBを指定しないでください。

schemaとcontrollerだけを個別に確認する場合:

```bash
(
  cd backend
  export APP_POSTGRES_PORT=5432
  TEST_DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app_test" \
    uv run pytest tests/integration/test_auth_schema.py \
      tests/integration/test_auth_controller.py -v
)
```

## 品質ゲート

```bash
(
  cd backend
  export APP_POSTGRES_PORT=5432
  uv run isort . --check-only
  uv run yapf -dr app/ tests/ alembic/
  TEST_DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app_test" \
    uv run pytest
)
```

```bash
(
  cd frontend
  npm run check
  npm test
  npm run build
)
```

## 停止・再build・初期化

通常停止ではDB volumeを保持します。

```bash
docker compose down
```

イメージだけを再buildする場合:

```bash
docker compose build
```

全volumeを削除して初期化する場合:

```bash
docker compose down -v
```

`down -v`は`frontend_node_modules`だけでなく`postgres_data`も削除し、runtime DBの全データを失います。次回の通常起動時にfrontend依存は再インストールされ、`app_test`は初期化スクリプトから自動作成されます。runtime DBのmigrationは改めて明示的に適用してください。

## 環境変数

- ルート`.env`: Composeの`FRONTEND_PORT`、`BACKEND_PORT`、`POSTGRES_PORT`
- `backend/.env`: `ENVIRONMENT`、runtime/test DB URL、pool設定、認証session TTL、rate limit設定
- frontend: 必要に応じて`frontend/.env.local`や`frontend/.env.development`をViteの標準ルールどおり使用。ブラウザへ露出する値には`VITE_`接頭辞が必要

認証設定はbackend起動時に読み込まれます。`backend/.env`または認証関連環境変数を変更した場合は、既存backend process/containerを再起動してください。

```bash
docker compose up -d --force-recreate backend
```

Docker Compose内ではfrontendの`/api` proxyが`http://backend:8000`を向き、backendは`postgres:5432/app`へ接続します。local Compose用の`app/app`認証情報を本番環境で使用しないでください。
