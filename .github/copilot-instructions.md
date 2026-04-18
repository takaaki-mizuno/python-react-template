# GitHub Copilot Instructions

このリポジトリの共通指針は **ルートの `AGENTS.md`** に集約されている。
Copilot は提案を生成する際に必ず以下を参照すること:

- `/AGENTS.md` — プロジェクト全体共通
- `/backend/AGENTS.md` — Backend (FastAPI) 作業時
- `/frontend/AGENTS.md` — Frontend (React/Vite) 作業時

主な原則:
- ドキュメント・コメントは日本語
- Conventional Commits
- Backend: FastAPI / uv / SQLModel / Injector、レイヤ依存は `controllers → usecases → services`
- Frontend: React 19 / Vite / TanStack Router & Query / Tailwind / shadcn/ui、atomic design
- セキュリティ: `.env` や認証情報をコミットしない
