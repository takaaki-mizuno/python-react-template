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
- shadcn/ui 由来の atom は `src/components/atoms/` に配置する。`components/ui` はこの repo では採用しない
- shared utility は `src/lib/` に置く。クラス結合は `src/lib/css.ts` の `cn()` を使う
- `components/` から `routes/` を import しない。Header のような共通 UI は route-specific data を props で受け取る

## ルーティング (TanStack Router)

- file-based ルートを採用。`src/routes/` 配下のファイルがそのまま URL になる
- 型安全な遷移を必ず使う (`<Link to="/...">`)
- auth を使う route guard は TanStack Router `beforeLoad` で実装し、未ログイン時は `/login` へ redirect する
- 認証必須 route は `_authenticated` pathless layout 配下へ置き、個別 route ごとに認証 guard を重複実装しない
- login/register redirect は `src/lib/authRedirect.ts` で internal href として正規化し、遷移時は `href` を使って search/hash を保持する
- account management UI は `/app/settings` に置く。`_authenticated.app.tsx` は page で `<Outlet />` を持たないため、settings route は `routes/_authenticated.app_.settings.tsx` の trailing underscore を使い、`_authenticated` guard 配下に置きつつ `/app` の子 route としては nest させない
- Phase 6 では Header / AuthMenu に settings link を追加しない。`/app` が `/app/settings` への導線を持つ

## データ取得 (TanStack Query)

- サーバ状態は React Query で管理。`useState` での手動キャッシュは禁止
- クエリキーは集約管理 (例: `src/lib/queryKeys.ts`)
- auth query key は `queryKeys.auth.me` の 1 本を正とし、厳格版などの派生 key を増やさない
- frontend の API 呼び出しは相対 `/api/...` を正とし、same-origin 配信を前提にする
- dev server では Vite proxy が `/api` を backend origin へ転送する
- account deletion success は logout と同じ cache policy を使う。全 TanStack Query cache を clear し、その後 `queryKeys.auth.me` を `null` にする

## API / Auth UI

- API error の画面表示は `src/lib/apiError.ts` の `toUserMessage()` を使い、各画面で `ApiError.body` を直接 parse しない
- unsafe request は `src/lib/apiClient.ts` を使い、個別 component / route から `/api/auth/csrf` を直接 fetch しない
- login/register form は `AuthTextField` / `AuthFormShell` / `Button` / `Input` を使い、field の label・autocomplete・aria 紐付けを共通部品へ寄せる
- destructive account operations は typed confirmation と `toUserMessage()` による日本語 error message を使う。account deletion の確認 email field は誤操作防止のため `autoComplete="off"` にし、削除 error 表示時は error code に対応する field だけへ `aria-invalid` を立てる。429 や CSRF など field に紐づかない error では input を invalid にしない。account deletion success は `/login?redirect=/app` ではなく `/` へ遷移する

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
