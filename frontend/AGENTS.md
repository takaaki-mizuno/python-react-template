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
│   │   └── ui/              # shadcn/ui 生成コンポーネント
│   ├── routes/              # TanStack Router file-based ルート
│   ├── hooks/               # カスタムフック
│   ├── lib/                 # ユーティリティ
│   └── main.tsx
└── public/
```

新規 UI コンポーネントは **atomic design** に従って配置する。

## 主要コマンド

```bash
# 開発サーバ (port 3000)
npm run dev

# 本番ビルド (../backend/static/ に出力)
npm run build

# 整形 (Prettier write + ESLint fix)
npm run check

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

## データ取得 (TanStack Query)

- サーバ状態は React Query で管理。`useState` での手動キャッシュは禁止
- クエリキーは集約管理 (例: `src/lib/queryKeys.ts`)

## スタイル (Tailwind + shadcn/ui)

- ユーティリティクラス優先。任意 CSS は最小限
- 共通スタイルは shadcn/ui のバリアント機構で表現
- デザインシステムは `.claude/skills/ui-design` を参照

## ビルド連携

- `npm run build` の出力は `../backend/static/` に書き込まれ、Backend が静的配信する
- ビルド成果物 (`backend/static/`) はコミット対象**ではない** (`.gitignore` で除外想定)

## テスト

- Vitest で単体テスト
- コンポーネントテストは React Testing Library 推奨

## 関連スキル

- `typescript-development` — TS 全般
- `ui-design` — デザインシステム
