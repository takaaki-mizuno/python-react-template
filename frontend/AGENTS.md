# Frontend (React + Vite)

React 19 / Vite ベースの SPA。Single source of truth は **ルートの `/AGENTS.md`** であり、本ファイルはその差分 (Frontend 固有) を記述する。

## 技術スタック

- React 19.2
- TypeScript 5.7
- ビルド: Vite 7.1 (出力先 `../backend/static/`)
- ルーティング: TanStack Router v1.132 (file-based)
- データ取得: TanStack Query v5.90
- スタイル: Tailwind CSS 4.0
- UI コンポーネント: shadcn/ui (Radix UI ベース)
- テスト: Vitest 3.0
- Lint: ESLint (`@tanstack/eslint-config`)
- Format: Prettier

## ディレクトリ構成

```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── components/
│   │   ├── atoms/           # 最小単位 UI (atomic design): shadcn/ui のコンポーネントのみ
│   │   ├── molecules/       # atoms の組み合わせ
│   │   ├── organisms/       # Header / LandingPage / Auth などページ単位に近い複合 UI
│   │   └── ui/              # shadcn/ui 生成コンポーネント
│   ├── routes/              # TanStack Router file-based ルート
│   ├── hooks/               # カスタムフック
│   ├── lib/                 # ユーティリティ
│   └── main.tsx
└── public/
```

新規 UI コンポーネントは **atomic design** に従って配置する。
`components/organisms/` は正式な配置先として扱い、ページ構成に近い複合 UI を置く。

## 主要コマンド

```bash
# 開発サーバ (port 3000)
npm run dev

# 本番ビルド (../backend/static/ に出力)
npm run build

# 型検査
npm run typecheck

# 整形 (Prettier write + ESLint fix)
npm run check

# CI / review 前検査 (書き換えなし)
npm run check:ci

# テスト
npm test               # Vitest
npm run test:watch     # watch モード (存在する場合)

# 依存追加
npm install <pkg>
npm install -D <pkg>   # devDependencies
```

## コードスタイル

- TypeScript strict mode 前提。`any` は禁止 (やむを得ない場合は理由をコメント)
- コンポーネント命名: `PascalCase`
- フック命名: `useXxx`
- ファイル名: コンポーネントは `PascalCase.tsx`、その他は `camelCase.ts`
- shadcn/ui 由来のファイルは `src/components/ui/` に配置し直接編集を避ける

## ルーティング (TanStack Router)

- file-based ルートを採用。`src/routes/` 配下のファイルがそのまま URL になる
- 型安全な遷移を必ず使う (`<Link to="/...">`)
- auth を使う route guard は TanStack Router `beforeLoad` で実装し、未ログイン時は `/login` へ redirect する
- 認証必須 route は `_authenticated` pathless layout 配下へ置き、個別 route ごとに認証 guard を重複実装しない
- login/register redirect は `src/lib/authRedirect.ts` で internal href として正規化し、遷移時は `href` を使って search/hash を保持する

## データ取得 (TanStack Query)

- サーバ状態は React Query で管理。`useState` での手動キャッシュは禁止
- クエリキーは集約管理 (例: `src/lib/queryKeys.ts`)
- auth query key は `queryKeys.auth.me` の 1 本を正とし、厳格版などの派生 key を増やさない
- frontend の API 呼び出しは相対 `/api/...` を正とし、same-origin 配信を前提にする
- dev server では Vite proxy が `/api` を backend origin へ転送する

## API / Auth UI

- API error の画面表示は `src/lib/apiError.ts` の `toUserMessage()` を使い、各画面で `ApiError.body` を直接 parse しない
- unsafe request は `src/lib/apiClient.ts` を使い、個別 component / route から `/api/auth/csrf` を直接 fetch しない
- login/register form は `AuthTextField` / `AuthFormShell` / `Button` / `Input` を使い、field の label・autocomplete・aria 紐付けを共通部品へ寄せる

## スタイル (Tailwind + shadcn/ui)

- ユーティリティクラス優先。任意 CSS は最小限
- 共通スタイルは shadcn/ui のバリアント機構で表現
- デザインシステムは `.claude/skills/ui-design` を参照

## ビルド連携

- `npm run build` の出力は `../backend/static/` に書き込まれ、Backend が静的配信する
- `npm run build` は `npm run typecheck` を先に実行してから Vite build を行う
- ビルド成果物 (`backend/static/`) はコミット対象**ではない** (`.gitignore` で除外想定)
- `npm run check` は Prettier / ESLint の自動修正を行う。CI や差分確認だけをしたい場合は `npm run check:ci` を使う

## テスト

- Vitest で単体テスト
- コンポーネントテストは React Testing Library 推奨

## 関連スキル

- `typescript-development` — TS 全般
- `ui-design` — デザインシステム
