@AGENTS.md
@../CLAUDE.md

# Backend 固有 (Claude Code)

Backend 作業時の追加指針:

- 実装前に `backend/AGENTS.md` のレイヤ依存ルールを再確認する
- 新規エンドポイント追加時は `controllers → usecases → services` の順に実装をサブエージェントへ委譲する
- DB スキーマに触る変更は **ユーザー確認** を必ず取る
- Python 関連の作業前に `Skill` で `python-development` を呼び出す
