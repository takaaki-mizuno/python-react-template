@AGENTS.md
@../CLAUDE.md

# Frontend 固有 (Claude Code)

Frontend 作業時の追加指針:

- 実装前に `frontend/AGENTS.md` のディレクトリ規約 (atoms/molecules/organisms) を再確認
- shadcn/ui のコンポーネント追加は frontend の pinned local CLI (`npm exec -- shadcn add <name> --yes`) を第一候補にする。CLI が対話プロンプトやネットワーク制約で完走しない場合は `npm exec -- shadcn view <name>` で公式 registry content を確認し、この repo の alias に合わせて `frontend/src/components/atoms/` へ追加する
- スタイル / レイアウト調整は `Skill` で `ui-design` を先に呼ぶ
- TS 作業前に `Skill` で `typescript-development` を先に呼ぶ
- ビルド成果物 (`../backend/static/`) を直接編集しない
