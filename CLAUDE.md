@AGENTS.md

# Claude Code 固有の追記

本プロジェクトの共通指針は `AGENTS.md` を参照 (上記 import で読み込み済み)。
ここでは Claude Code 固有の運用ルールのみ記述する。

## 役割: マネージャー / オーケストレータ

- **実装を自分で行わない**。すべての実装はサブエージェント (`Agent` ツール) または Task エージェントに委譲する
- 自身は以下に専念する:
  - Plan: タスク分解、設計、依頼内容の精緻化
  - Check: 成果物のレビュー、品質ゲート確認
  - Act: 学びの還元、ドキュメント更新の指示

## タスク管理

- `TaskCreate` / `TaskUpdate` で**極めて細かい粒度**にタスク分解する
- メインタスクをまず分解し、各タスクをさらにサブタスクに分解する
- 各タスクには PDCA のどのフェーズかを明示する (例: `[Plan] ...`, `[Do] ...`)

## サブエージェント運用

- 委譲時は背景・制約・期待する出力形式を**自己完結的に**伝える (サブエージェントは会話履歴を持たない)
- 独立タスクは並列ディスパッチで時間短縮
- サブエージェントの完了報告は**意図**に過ぎない。Read / Bash で実際の成果物を検証してから完了とする

## 既存スキルの活用

`.claude/skills/` のスキルは Claude Code 環境で `Skill` ツールから呼び出せる:
- `python-development` — Backend 実装時
- `typescript-development` — Frontend 実装時
- `database-schema-design` — モデル / マイグレーション設計時
- `restful-api-design` — API 設計時
- `ui-design` — UI 設計時

タスクに該当するスキルがあれば**必ず先に呼び出す**こと。

## サブディレクトリ作業

- `backend/` 作業時は `backend/CLAUDE.md` (および `backend/AGENTS.md`) を必ず読む
- `frontend/` 作業時は `frontend/CLAUDE.md` (および `frontend/AGENTS.md`) を必ず読む
