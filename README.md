# python-react-template

FastAPI backend と React + Vite frontend を同居させたモノレポです。frontend の build 成果物は `backend/static/` に出力され、backend から静的配信できます。

## 起動

ルートの `.env` は compose 用、`backend/.env` は backend 用です。必要なら example をコピーしてから起動します。

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

```bash
docker compose up --build
```

アクセス先:

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000/api/healthz`

ポートが使用中の場合は環境変数で上書きできます。

```bash
FRONTEND_PORT=3001 BACKEND_PORT=8001 docker compose up --build
```

## 停止

```bash
docker compose down
```

`docker compose down -v` を使うと `frontend_node_modules` ボリュームも削除されるため、次回起動時に frontend 依存の再インストールが走ります。

## 再ビルド

```bash
docker compose build
```

イメージの build と同時に frontend も build され、成果物が backend イメージ内の `static/` に取り込まれます。

## 環境変数

- ルート `.env`: compose のポート上書き用です。`FRONTEND_PORT` と `BACKEND_PORT` を定義します。
- `backend/.env`: backend コンテナへ `env_file` で注入されます。現状の example には `ENVIRONMENT` のみ入れています。
- frontend は `./frontend` を bind mount しているため、必要なら `frontend/.env.local` や `frontend/.env.development` を Vite の標準ルールどおり使えます。ブラウザへ露出する値は `VITE_` 接頭辞が必要です。
