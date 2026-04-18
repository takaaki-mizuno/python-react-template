@AGENTS.md
@../CLAUDE.md

# Frontend 固有 (Claude Code)

Frontend 作業時の追加指針:

- 実装前に `frontend/AGENTS.md` のディレクトリ規約 (atoms/molecules/ui) を再確認
- shadcn/ui のコンポーネント追加は CLI (`npx shadcn@latest add <name>`) を使い、手書きしない
- スタイル / レイアウト調整は `Skill` で `ui-design` を先に呼ぶ
- TS 作業前に `Skill` で `typescript-development` を先に呼ぶ
- ビルド成果物 (`../backend/static/`) を直接編集しない
