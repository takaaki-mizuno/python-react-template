# Dockerfile と docker-compose.yaml を作成

ローカル環境を簡単にセットアップするためのDockerfileと起動用のdocker-compose.yamlを作成する
Frontend をビルドして、 static にいれるところまで。

また、docker-compose.yaml はローカル環境要なので backend をマウントし、変更が即座に反映できるようにする。
（ローカル環境用、とか無駄なことはコメントなどに書くな）

さらにREADME.md を作成し、人間向けのリポジトリの説明とローカル環境のセットアップ方法を書いて
（人間向け、とか無駄なことは書くな）

## 追加計画（2026-04-17 / レビュー反映後）

### 背景
- 現状のリポジトリにはルートの `Dockerfile`、`docker-compose.yaml`、`README.md` がなく、ローカル起動の入口が不足している。
- `frontend/vite.config.ts` はすでに `../backend/static` へ build 出力する設定であり、「frontend を build して backend/static に入れる」という要件とは整合している。
- `backend/app/bootstrap/route.py` は `static/` を常時マウントしているため、開発時に frontend を別サービスで配る場合でも `backend/static` ディレクトリ自体は存在している必要がある。
- 事前確認で「frontend の変更も自動反映したい場合はどうするか」を詰めた結果、この計画では `docker-compose.yaml` を `backend` と `frontend` の 2 サービス構成にし、frontend 側の即時反映は Vite dev server で担保する前提で進める。
- 一方で、この作業の主眼はあくまでローカル開発環境の整備であり、本番向け構成やアプリケーションコードの改修まで広げない。

### 方針とその理由
- ルート `Dockerfile` は 2 ステージ構成に絞る。
  - `frontend-builder`: Node.js で frontend を build し、成果物を `backend/static` 相当のパスに出力する。
  - `runtime`: Python + uv で backend 依存を導入し、backend ソースと build 済み静的ファイルを持つ。
  - 理由: 「frontend を build して static に入れる」要件は満たしつつ、dev 専用ターゲットや本番用の派生構成を増やさずに済むため。
- `docker-compose.yaml` は 2 サービス構成にするが、Dockerfile で dev 専用ターゲットは作らない。
  - `backend` サービスはルート `Dockerfile` から build したイメージを使い、backend のソースコードだけを bind mount する。
  - `frontend` サービスは公式 Node.js イメージを使い、`npm run dev -- --host 0.0.0.0` で Vite dev server を起動する。
  - 理由: frontend の自動反映を満たすために 2 サービスは必要だが、`backend-dev` / `frontend-dev` のような専用ステージまでは不要なため。
- backend は「ディレクトリ全体」ではなく「反映が必要なコードだけ」を mount する。
  - 対象は最低限 `backend/app` と `backend/manage.py` とし、イメージ内で作った Python 実行環境を bind mount で隠さない。
  - 理由: `./backend` を丸ごと mount すると、イメージ内の `.venv` や依存環境が隠れて起動が壊れやすいため。
- `backend/manage.py`、`backend/app/bootstrap/route.py`、`frontend/vite.config.ts` には今回手を入れない。
  - 理由: 既存要件は Dockerfile / compose / README の調整で達成可能であり、アプリ側の改修は別タスクに切り出すべきため。
- backend の起動コマンドは compose 側で `mkdir -p static && uv run python manage.py serve --host 0.0.0.0 --port 8000` とする。
  - 理由: `route.py` を変えずに `static/` の存在条件を満たしつつ、既存の reload 動作も維持できるため。
- README の対象は「概要」「起動」「停止」「再ビルド」に限定する。
  - 理由: 今回はローカル開発環境の導線を作る作業であり、単体 `docker run` 手順や本番運用説明はスコープ外のため。
- backend 用の `env_file` と example は追加するが、proxy / CORS / healthcheck は今回の計画に含めない。
  - 理由: backend の `.env` 導線だけは用意しておく価値がある一方、frontend の API 接続設計や healthcheck までは現状未使用の前提を増やすため。

### 完成イメージ
- `docker compose up --build` で `backend` と `frontend` が起動する。
- ブラウザは `http://localhost:3000` を開けば frontend を確認できる。
- backend API は `http://localhost:8000/api/healthz` で確認できる。
- frontend の変更は Vite dev server により即時反映される。
- backend の Python コード変更は既存の `uvicorn` reload により即時反映される。
- Dockerfile の build 結果には frontend の成果物が `backend/static` として含まれる。

### スコープ外
- 本番向けのコンテナ最適化、配布用 `docker run` 手順、Kubernetes / ECS / Cloud Run などのデプロイ定義。
- DB や外部サービス、healthcheck、複数 compose ファイルへの分割。
- frontend から backend API を透過的に呼ぶための proxy / CORS / 環境変数設計。
- `backend/manage.py`、`backend/app/bootstrap/route.py`、`frontend/vite.config.ts` の振る舞い変更。

### 想定変更ファイル
- 作成: `/Users/takaaki/Development/rocket/python-react-template/Dockerfile`
- 作成: `/Users/takaaki/Development/rocket/python-react-template/.dockerignore`
- 作成: `/Users/takaaki/Development/rocket/python-react-template/.env.example`
- 作成: `/Users/takaaki/Development/rocket/python-react-template/docker-compose.yaml`
- 作成: `/Users/takaaki/Development/rocket/python-react-template/README.md`
- 作成: `/Users/takaaki/Development/rocket/python-react-template/backend/.env.example`

### 具体的なタスク

#### 1. 前提条件を固定する
- [x] `frontend/vite.config.ts` の `build.outDir = '../backend/static'` を前提に、Dockerfile の frontend build は `WORKDIR /app/frontend` から実行し、生成先を `/app/backend/static` に揃える。
- [x] `backend/app/bootstrap/route.py` が `static/` ディレクトリの存在を前提にしていることを確認し、compose の backend 起動前に `mkdir -p static` を実行する方針を採用する。
- [x] 今回は Docker 周りのみで完結させるため、backend / frontend のアプリコードは変更対象に含めないことを計画上で明示する。

#### 2. Dockerfile を作成する
- [x] ルート `Dockerfile` に `frontend-builder` ステージを作成し、`node:22-bookworm-slim` 系イメージを使う。
- [x] `frontend-builder` では `frontend/package.json` と `frontend/package-lock.json` を先にコピーして `npm ci` を実行し、その後に frontend ソースをコピーする。build キャッシュを壊しにくい順序にする。
- [x] `frontend-builder` では `RUN mkdir -p /app/backend` を先に実行し、`WORKDIR /app/frontend` で `npm run build` を実行して、既存の `outDir` 設定どおり `/app/backend/static` に成果物が生成されるようにする。
- [x] `runtime` ステージには `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` 系イメージを使い、uv の導入方法を Dockerfile 内で別途増やさない。
- [x] `runtime` では `backend/pyproject.toml` と `backend/uv.lock` を先にコピーし、依存キャッシュ用の `uv sync --frozen --no-dev --no-install-project` と、ソースコピー後の `uv sync --frozen --no-dev` を分けて実行する。
- [x] `runtime` では `frontend-builder` から `/app/backend/static` をコピーし、backend の静的配信用ディレクトリをイメージ内に含める。
- [x] `runtime` のデフォルトコマンドは `uv run python manage.py serve --host 0.0.0.0 --port 8000` とし、compose からも同系統のコマンドを呼び出す。

#### 3. .dockerignore を作成する
- [x] ルート `.dockerignore` を作成し、`.git`、`.venv`、`backend/.venv`、`frontend/node_modules`、`backend/static`、`__pycache__`、`.pytest_cache`、`dist` などを build context から除外する。
- [x] `.dockerignore` では `frontend/src`、`frontend/public`、`backend/app`、`backend/manage.py`、`backend/pyproject.toml`、`backend/uv.lock` が除外されていないことを確認する。

#### 4. docker-compose.yaml を作成する
- [x] ルート `docker-compose.yaml` に `backend` サービスを定義し、ルート `Dockerfile` を使って build する。公開ポートは既定で `8000:8000`、必要に応じて `BACKEND_PORT` で上書きできるようにする。
- [x] `backend` サービスには `./backend/.env` を optional な `env_file` として定義し、backend 用の `.env` を compose から注入できるようにする。
- [x] `backend` サービスの `working_dir` は `/app/backend` とし、bind mount は `./backend/app:/app/backend/app` と `./backend/manage.py:/app/backend/manage.py` を最低限含める。
- [x] `backend` サービスのコマンドは `sh -c "mkdir -p static && uv run python manage.py serve --host 0.0.0.0 --port 8000"` とし、`static/` が無い fresh clone でも起動できるようにする。
- [x] ルート `docker-compose.yaml` に `frontend` サービスを定義し、公式 `node:22-bookworm-slim` 系イメージを使う。公開ポートは既定で `3000:3000`、必要に応じて `FRONTEND_PORT` で上書きできるようにする。
- [x] `frontend` サービスの `working_dir` は `/app/frontend` とし、bind mount は `./frontend:/app/frontend`、依存退避用に `frontend_node_modules:/app/frontend/node_modules` の named volume を追加する。
- [x] `frontend` サービスのコマンドは `sh -c "if [ ! -x node_modules/.bin/vite ]; then npm ci; fi && npm run dev -- --host 0.0.0.0"` とし、初回起動時だけ依存を導入する。
- [x] `frontend_node_modules` は bind mount の下に重ねる構成なので、README に「`docker compose down -v` を行うと依存キャッシュも消える」ことを一言入れる。
- [x] `depends_on` は `frontend -> backend` の最小構成に留め、healthcheck は今回追加しない。

#### 5. ルート README.md を作成する
- [x] ルート `README.md` を新規作成し、このリポジトリが FastAPI backend + React/Vite frontend のモノレポであることを最初に説明する。
- [x] `README.md` に起動手順として `docker compose up --build`、アクセス先として `http://localhost:3000` と `http://localhost:8000/api/healthz` を記載する。
- [x] `README.md` と example ファイルに、ルート `.env` は compose 用、`backend/.env` は backend 用であることを記載する。
- [x] `README.md` に停止手順として `docker compose down` を記載する。
- [x] `README.md` に再ビルド手順として `docker compose build` または `docker compose up --build` を記載する。
- [x] `README.md` には本番運用手順や `docker run` 単体実行手順を書かない。

#### 6. 動作確認と品質ゲートを行う
- [x] `docker compose build` を実行し、backend イメージ build の中で frontend build が成功し、compose 全体が build できることを確認する。
- [ ] `docker compose up` を実行し、`http://localhost:3000` で frontend が表示され、`http://localhost:8000/api/healthz` で backend API が確認できることを確認する。
- [ ] frontend の表示文言を一箇所変更し、Vite dev server によりブラウザへ即時反映されることを確認する。
- [ ] backend のレスポンス文言を一箇所変更し、コンテナ再作成なしで reload 反映されることを確認する。
- [x] `cd frontend && npm run check` を実行し、整形と ESLint を通す。
- [x] `cd frontend && npm run build` を実行し、既存の frontend build がローカルでも成功することを確認する。
- [ ] `cd frontend && npm run test` を実行し、Vitest を通す。
- [x] `cd backend && uv run pytest` を実行し、結果を確認する。失敗した場合は追加の回避策をこのタスクでは入れず、失敗内容をそのまま報告する。
- [x] 最後に、計画書と `README.md` の記述が実際の compose 構成と矛盾していないことを見直す。

確認メモ:
- sandbox から `localhost:8000` / `localhost:3000` / `localhost:3001` への `curl` は接続できず、URL 応答そのものはこのセッションでは確認できていない。一方で `docker ps` と `docker logs` では backend の Uvicorn 起動、frontend の Vite 起動を確認済み。
- `npm run test` は `No test files found, exiting with code 1` で未通過。
- `uv run pytest` は sandbox 内で `uv` が panic し、あわせて `backend/.venv/bin/pytest` も存在しないため、現状の backend 側には pytest 実行基盤が揃っていない。
