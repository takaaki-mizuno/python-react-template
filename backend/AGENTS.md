# Backend (FastAPI)

FastAPI ベースの Python バックエンド。Single source of truth は **ルートの `/AGENTS.md`** であり、本ファイルはその差分 (Backend 固有) を記述する。

## 技術スタック

- Python 3.12+
- パッケージ管理: **uv** (`uv.lock` を正)
- Web フレームワーク: FastAPI 0.128+
- ORM / モデル: SQLModel
- DI: Injector
- CLI: Typer (`manage.py`)
- 非同期 DB ドライバ: aiosqlite (デフォルト)
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

## モデル / DB

- 新規テーブル追加時はまず `documents/plans/` に ER 設計を残す
- スキーマ変更時はマイグレーション戦略を**事前にユーザー確認**

## API 設計

- REST 規約に従う。設計時は `.claude/skills/restful-api-design` を参照
- レスポンスは `usecases` 層が返す DTO/モデルを `controllers` で整形

## テスト

- Pytest を使用 (依存に未追加なら `uv add --dev pytest pytest-asyncio` から)
- 単体テスト: `tests/unit/`、結合テスト: `tests/integration/` を推奨
- DB を使うテストは実 DB (SQLite in-memory) を使用しモックしない

## 関連スキル

- `python-development` — Python 全般
- `database-schema-design` — モデル設計
- `restful-api-design` — API 設計
