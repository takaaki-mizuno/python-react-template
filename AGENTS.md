# python-react-template

Full-stack ボイラープレート。FastAPI (Python) バックエンド + React (Vite) フロントエンドのモノレポ構成。

このリポジトリは AI コーディングエージェント (Claude Code / Codex / Copilot / Cursor / Aider など) を主要な開発インターフェースとして想定しており、本ファイルが**全エージェント共通の正典**となる。

## プロジェクト構成

```
.
├── AGENTS.md                       # ← このファイル (全エージェント共通)
├── CLAUDE.md                       # Claude Code 固有 (AGENTS.md を import)
├── .github/copilot-instructions.md # GitHub Copilot 用 (AGENTS.md を参照)
├── backend/                        # FastAPI アプリ。詳細は backend/AGENTS.md
├── frontend/                       # React + Vite。詳細は frontend/AGENTS.md
└── documents/
    ├── plans/                      # 実装計画書 (yyyymmdd-feature.md)
    └── references/                 # アーキテクチャ・API 参考資料
```

サブディレクトリで作業する際は **必ず該当する `<dir>/AGENTS.md` を先に読む**こと。

## 開発フロー (PDCA)

新規機能・変更は以下のサイクルで進める:
1. **Plan** — `documents/plans/yyyymmdd-<feature>.md` に計画を書く (要件 / 影響範囲 / 段取り)
2. **Do** — 計画に沿って小さなコミット単位で実装
3. **Check** — テスト / Lint / 型検査をすべて通す (下記「品質ゲート」参照)
4. **Act** — 学びを計画書または本ドキュメント群へ反映

## 主要コマンド

| 目的 | コマンド | 作業ディレクトリ |
|---|---|---|
| Backend 起動 | `python manage.py serve` | `backend/` |
| Frontend 起動 (dev) | `npm run dev` | `frontend/` |
| Frontend ビルド | `npm run build` | `frontend/` (出力先 `backend/static/`) |
| Frontend 整形 | `npm run check` | `frontend/` (`prettier --write` / `eslint --fix` を実行する mutating command) |
| Frontend CI 検査 | `npm run check:ci` | `frontend/` (`prettier --check` / `eslint` / `typecheck`) |
| Backend 依存追加 | `uv add <pkg>` | `backend/` |
| Frontend 依存追加 | `npm install <pkg>` | `frontend/` |

詳細は各サブディレクトリの `AGENTS.md` を参照。

## 品質ゲート (Check)

PR をマージする前に **必ず** 以下を通す:
- Backend static: `cd backend && uv run ruff check .`、`uv run isort . --check-only`、`uv run yapf -dr app/ tests/ alembic/ manage.py`、`uv run mypy app manage.py`
- Backend unit: `cd backend && uv run pytest tests/unit`
- Backend integration: PostgreSQL 起動後、`cd backend && ALEMBIC_DATABASE_URL=... uv run python manage.py db-upgrade`、`TEST_DATABASE_URL=... uv run pytest tests/integration -q -ra`、`ALEMBIC_DATABASE_URL=... uv run python manage.py db-check`
- Frontend: `cd frontend && npm run check:ci`、`npm test`、`npm run build`
- Docker: `docker compose config`、`docker build --target runtime ...`、`docker build --target backend-dev ...`
  - 注意: `npm run check` は check-only ではなく整形・自動修正を行う。CI とレビュー前確認では `npm run check:ci` を使う。
  - integration tests は `TEST_DATABASE_URL` 未設定で fail する。unit だけを実行する場合は `tests/unit` を明示する。

エージェントは「完了」を報告する前に上記コマンドを実行し、結果を確認すること。

## コードスタイル

- Backend: isort + yapf。インポート順は isort、フォーマットは yapf に従う
- Frontend: ESLint (TanStack config) + Prettier。設定ファイルが正
- コミット: Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `refactor:` 等)
- コメント: WHY を書く。WHAT は読めばわかる
- ドキュメント (本ファイル含む) は日本語

## セキュリティ

- `.env` / 認証情報 / API キーをコミットしない (`.gitignore` 設定済み)
- シークレットは環境変数経由のみ
- 依存追加時はライセンスと既知脆弱性を確認

## 安全な操作 / 確認が必要な操作

**確認なしで実行可**:
- ファイル読み取り、検索 (Grep/Glob)
- 単一ファイルの Lint / Format
- ローカルテスト実行
- Plan モードでの計画立案

**ユーザー確認が必要**:
- 依存追加 (`uv add` / `npm install`)
- DB スキーマ変更 / マイグレーション
- `git push`、ブランチ削除、force push
- 外部 API への破壊的操作

## PR ガイドライン

- タイトル: `<type>(<scope>): <summary>` (Conventional Commits)
- 本文: **Summary** / **Test Plan** の 2 セクション
- 全ての品質ゲートをクリア
- 関連する `documents/plans/` を更新

## 参考資料

- `documents/references/` — アーキテクチャ詳細
- `.claude/skills/` — 領域別の詳細ガイド (Python / TypeScript / DB / REST API / UI)
