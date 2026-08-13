# ローカル起動ガイド

このドキュメントは、このリポジトリの中身をまだ知らない人が、FastAPI + React テンプレートをローカルで起動して画面を確認するまでの手順です。

一番簡単な方法は Docker Compose を使う方法です。Python、Node.js、PostgreSQL をホスト側へ個別に入れなくても、コンテナだけで PostgreSQL、Backend、Frontend を起動できます。

## 起動できるもの

このリポジトリは次の 3 つを同時に起動します。Redis は認証 rate limit の共有 store 検証用に用意されていますが、通常起動では必須ではありません。

| 名前 | 役割 | デフォルト URL / Port |
|---|---|---|
| Frontend | React + Vite の画面 | http://localhost:3000 |
| Backend | FastAPI API サーバ | http://localhost:8000 |
| PostgreSQL | アプリ用 DB | localhost:5432 |
| Redis | 認証 rate limit の共有 store 検証用 | localhost:6379 |

Backend の疎通確認は次の URL で行います。

- http://localhost:8000/api/healthz
- http://localhost:8000/docs

`/docs` は `backend/.env` の `ENVIRONMENT=local` で有効になります。

## 前提条件

Docker Compose で起動する場合に必要なものは次の 2 つです。

- Docker Engine または Docker Desktop
- Docker Compose v2

確認コマンド:

```bash
docker --version
docker compose version
```

どちらも version が表示されれば準備できています。

ホスト側で Backend や Frontend を直接起動する場合だけ、追加で次が必要です。

- Python 3.12+
- uv
- Node.js 22 系
- npm

まずは Docker Compose で起動する方法を推奨します。

## 1. リポジトリのルートへ移動する

以降のコマンドは、特に指定がない限りリポジトリのルートで実行します。

```bash
cd /path/to/python-react-template
```

このリポジトリでは、ルートに `docker-compose.yaml`、`backend/`、`frontend/`、`documents/` がある状態が正しい位置です。

確認コマンド:

```bash
ls
```

`backend` と `frontend` が表示されれば OK です。

## 2. 環境変数ファイルを作る

テンプレートからローカル用の `.env` ファイルを作ります。

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

それぞれの役割は次の通りです。

| ファイル | 役割 |
|---|---|
| `.env` | Docker Compose の公開 port 設定 |
| `backend/.env` | FastAPI の環境、DB 接続、認証 cookie、rate limit など |

初回起動だけなら中身を変更しなくて構いません。

## 3. Docker Compose で起動する

次のコマンドで PostgreSQL、Backend、Frontend を build して起動します。

```bash
docker compose up -d --build postgres backend frontend
```

このリポジトリの `docker-compose.yaml` では、Backend コンテナ起動時に次の処理も自動で実行されます。

1. `uv sync --frozen --group dev`
2. `uv run python manage.py db-upgrade`
3. `uv run python manage.py serve --host 0.0.0.0 --port 8000 --reload`

つまり、通常の初回起動では依存関係の同期、DB migration、FastAPI 起動までまとめて行われます。

認証 rate limiter は既定で in-memory です。ログイン、ユーザー登録、OIDC 開始、アカウント削除再認証の通常確認ではこのままで構いません。複数 worker / instance 間で試行回数が共有されることを確認したい場合だけ Redis を起動し、`backend/.env` を切り替えます。

```env
AUTH_RATE_LIMIT_BACKEND=redis
AUTH_RATE_LIMIT_REDIS_URL=redis://redis:6379/0
```

```bash
docker compose up -d redis postgres backend frontend
```

host 側から Redis integration test を実行する場合は、Compose 内の service 名ではなく公開 port を使います。

```bash
(
  cd backend
  TEST_REDIS_URL="redis://localhost:${REDIS_PORT:-6379}/1" \
    uv run pytest tests/integration/test_redis_rate_limiter.py -q
)
```

## 4. 起動状態を確認する

コンテナの状態を確認します。

```bash
docker compose ps
```

目安は次の状態です。

- `postgres` が `healthy`
- `backend` が `Up` または `healthy`
- `frontend` が `Up`

初回は image build、Python 依存関係の同期、npm install、DB migration が走るため数分かかることがあります。

ログを見ながら待つ場合:

```bash
docker compose logs -f postgres backend frontend
```

ログ表示を止めるには `Ctrl+C` を押します。コンテナ自体は停止しません。

## 5. ブラウザで確認する

Frontend:

```text
http://localhost:3000
```

Backend health check:

```text
http://localhost:8000/api/healthz
```

FastAPI docs:

```text
http://localhost:8000/docs
```

Frontend は Vite dev server で起動しています。画面から `/api/...` を呼ぶ場合、Vite proxy が Backend へ転送します。

## 6. ログイン系の画面を確認する

画面側には次のルートがあります。

| URL | 用途 |
|---|---|
| http://localhost:3000/ | ランディングページ |
| http://localhost:3000/register | ユーザー登録 |
| http://localhost:3000/login | ログイン |
| http://localhost:3000/app | ログイン後のアプリ画面 |
| http://localhost:3000/app/settings | アカウント設定 |

初回は登録ユーザーがいないため、通常は `/register` からユーザーを作成して動作確認します。

## 7. 停止する

コンテナを停止します。DB データは `docker/postgres/data/` に残ります。

```bash
docker compose down
```

次回は次のコマンドで再起動できます。

```bash
docker compose up -d postgres backend frontend
```

## 8. DB も含めて完全に初期化する

登録ユーザーや DB データも消して初期状態からやり直したい場合だけ実行します。

PostgreSQL データは bind mount された `docker/postgres/data/` にあります。DB も初期化する場合は、停止後にこのディレクトリを削除してください。

```bash
docker compose down
rm -rf docker/postgres/data
docker compose up -d --build postgres backend frontend
```

ローカルで必要なデータがある場合は `docker/postgres/data/` を削除しないでください。

## Port がすでに使われている場合

デフォルトでは次の port を使います。

- Frontend: `3000`
- Backend: `8000`
- PostgreSQL: `5432`
- Redis: `6379`

すでに使われている場合は、ルートの `.env` を編集して port を変えます。

例:

```env
FRONTEND_PORT=3001
BACKEND_PORT=8001
POSTGRES_PORT=5433
REDIS_PORT=6380
```

変更後に起動します。

```bash
docker compose up -d --build postgres backend frontend
```

この場合のアクセス先は次のように読み替えます。

- Frontend: http://localhost:3001
- Backend: http://localhost:8001
- PostgreSQL: localhost:5433

## よくあるトラブル

### `docker compose` が見つからない

Docker Compose v2 が使える状態ではありません。Docker Desktop または Docker Engine + Compose plugin をインストールしてください。

確認:

```bash
docker compose version
```

### `port is already allocated` と表示される

別のプロセスが port を使っています。

対応方法はどちらかです。

1. 使っているプロセスを停止する
2. ルート `.env` の `FRONTEND_PORT`、`BACKEND_PORT`、`POSTGRES_PORT` を変更する

### Frontend は開くが API が失敗する

Backend がまだ起動中、または migration に失敗している可能性があります。

確認:

```bash
docker compose ps
docker compose logs backend
```

Backend が起動しているかを直接確認します。

```bash
curl http://localhost:8000/api/healthz
```

`BACKEND_PORT` を変更した場合は port も読み替えてください。

### Backend の migration を手動でやり直したい

通常は Backend コンテナ起動時に `db-upgrade` が自動実行されます。途中で失敗した場合や、migration だけを明示的に再実行したい場合は次を実行します。

```bash
docker compose exec backend uv run python manage.py db-upgrade --revision head
```

### 初期 migration を作り直した後にローカル DB を作り直したい

未デプロイ前提で初期 migration file の中身を作り直した場合は、ローカル DB も作り直します。既存 DB に同じ revision id が適用済みだと、Alembic は新しい migration 内容を再実行しません。

登録ユーザーや開発中データが消えてよいことを確認してから実行してください。

```bash
docker compose down
rm -rf docker/postgres/data
docker compose up -d --build postgres backend frontend
```

Backend コンテナは起動時に migration を実行します。明示的に確認したい場合は次を実行します。

```bash
docker compose exec -T backend uv run python manage.py db-upgrade --revision head
docker compose exec -T backend uv run python manage.py db-check
```

管理画面を確認する場合は、migration 後に seed admin を入れます。

```bash
docker compose exec -T backend \
  env ENVIRONMENT=local \
      DATABASE_URL=postgresql+asyncpg://app:app@postgres:5432/app \
  uv run python manage.py seed-admin
```

作成される管理者は `admin@example.com` / `Password@123!` です。

### 依存関係が古い、またはコンテナ内の状態がおかしい

まず build し直します。

```bash
docker compose build backend frontend
docker compose up -d postgres backend frontend
```

それでも解決しない場合は、DB データを消してよいか確認してから `docker/postgres/data/` を削除します。

```bash
docker compose down
rm -rf docker/postgres/data
docker compose up -d --build postgres backend frontend
```

## ホスト側で個別に起動する方法

Docker Compose で全部起動する方法が基本ですが、Backend や Frontend をホスト側で直接起動したい場合はこの手順を使います。

この方法では PostgreSQL だけ Docker Compose で起動し、Backend と Frontend はホスト側で動かします。

### 1. PostgreSQL だけ起動する

```bash
docker compose up -d postgres
```

標準 port のままなら、DB 接続先は次です。

```text
postgresql+asyncpg://app:app@localhost:5432/app
```

### 2. Backend を起動する

別ターミナルで実行します。

```bash
cd backend
uv sync --group dev
uv run python manage.py db-upgrade --revision head
uv run python manage.py serve --host 0.0.0.0 --port 8000 --reload
```

`backend/.env` の `DATABASE_URL` はデフォルトで `localhost:5432/app` を向いているため、標準 port ならそのまま使えます。

`POSTGRES_PORT=5433` のように変更している場合は、`backend/.env` の `DATABASE_URL` と `TEST_DATABASE_URL` の port も同じ値へ変更してください。

### 3. Frontend を起動する

さらに別ターミナルで実行します。

```bash
cd frontend
npm ci
npm run dev
```

標準設定では http://localhost:3000 で起動します。

Backend の port を `8001` などへ変更している場合は、Frontend 起動時に Backend origin を指定します。

```bash
VITE_BACKEND_ORIGIN=http://localhost:8001 npm run dev
```

## 最短コマンドまとめ

初回:

```bash
cp .env.example .env
cp backend/.env.example backend/.env
docker compose up -d --build postgres backend frontend
docker compose ps
```

確認:

```text
http://localhost:3000
http://localhost:8000/api/healthz
http://localhost:8000/docs
```

停止:

```bash
docker compose down
```
