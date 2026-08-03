# フロントエンド コーディングルール（TypeScript / React）

このドキュメントは、`frontend/` 配下の TypeScript アプリケーションを分析した上でのコーディング規約・構成ルールです。既存コードの実態（Vite + React + TanStack Router + Tailwind CSS）に基づき、プロジェクト共通ルールとして明文化しています。

---

## 1. 基本原則

- **TypeScript の徹底**: すべて TypeScript で記述し、`any` 型は原則禁止（`tsconfig.json` は `strict: true`）。
- **SPA / クライアントサイド前提**: 本プロジェクトは Vite + React の SPA として動作するため、Server Components / Server Actions は存在しない。
- **関心の分離**: UI・状態管理・データ取得の責務を分離する。
- **命名規則**: コンポーネント名・ディレクトリ名・ファイル名は一貫させる（詳細は後述）。
- **ディレクトリ構造**: Atomic Design（atoms / molecules / organisms）＋機能単位を維持する。
- **PWA対応**: ヘッダー・フッター等、画面端に接する UI には `env(safe-area-inset-*)` を考慮する。
- **サーバ処理**: 本 SPA では Server Actions は使わない。サーバ処理が必要な場合は、API を経由してクライアントから呼び出す。

---

## 2. ディレクトリ構造（現行）

```
frontend/
├── src/
│   ├── components/
│   │   ├── atoms/
│   │   ├── molecules/
│   │   └── organisms/
│   ├── lib/
│   │   ├── apiClient.ts
│   │   ├── authApi.ts
│   │   ├── queryClient.ts
│   │   ├── queryKeys.ts
│   │   └── css.ts
│   ├── routes/
│   │   ├── __root.tsx
│   │   └── index.tsx
│   ├── routeTree.gen.ts
│   ├── main.tsx
│   ├── styles.css
│   └── reportWebVitals.ts
├── components.json
├── tsconfig.json
├── eslint.config.js
├── prettier.config.js
└── vite.config.ts
```

- `routeTree.gen.ts` は **TanStack Router により自動生成**されるため編集禁止。
- パスエイリアスは `@/* -> src/*`（`tsconfig.json` / `vite.config.ts` で設定）。
- `components.json` のエイリアス:
  - `ui` -> `@/components/atoms`
  - `components` -> `@/components`
  - `utils` -> `@/lib/css`
  - `lib` -> `@/lib`
  - `hooks` -> `@/hooks`（必要に応じて作成）

---

## 3. コンポーネント設計（Atomic Design）

### 3.1 配置ルール

- すべての UI コンポーネントは `components/` 配下に配置。
- 粒度に応じて `atoms`, `molecules`, `organisms` に分類。

### 3.2 各カテゴリの定義

- **atoms**
  - 最小単位の UI。
  - **Shadcn/UI のコンポーネントを配置する場所として固定**。
  - **カスタムコンポーネントの追加は禁止**（必要なら `molecules` 以上でラップ）。
- **molecules**
  - 複数の atom を組み合わせた UI 部品。
- **organisms**
  - 複数の molecule/atom で構成される、セクション単位の UI。

### 3.3 コンポーネントのファイル構成

- `molecules` / `organisms` は **PascalCase のディレクトリ**を作り、直下に `index.tsx` を置く。
- `components/` から `routes/` を import しない。route 固有の data は route 層から props として注入するか、component local の `data.ts` に置く。
- 例:

```
components/
├── molecules/
│   └── PetFilter/
│       └── index.tsx
└── organisms/
    └── AppHeader/
        └── index.tsx
```

---

## 4. ルーティング（TanStack Router）

- ルーティングは **file-based**（`src/routes` 配下のファイルがそのままルート）。
- 各ルートファイルは `createFileRoute` を使い、`Route` を export する。
- ルートレイアウトは `src/routes/__root.tsx`。
  - `<Outlet />` を必ず配置。
  - 共通 UI（例: `<Header />`）をここに置く。
- `Link` は `@tanstack/react-router` のものを使用（SPA ナビゲーション）。
- `routeTree.gen.ts` は自動生成のため編集禁止・フォーマット対象外。

---

## 5. データ取得 / API アクセス

- **API アクセスは TanStack Query を利用する**。
  - ルートコンポーネントや UI から直接 `fetch` せず、`useQuery` 等のフックで扱う。
  - `QueryClient` は `main.tsx` で Provider に設定することを推奨。
- ルート単位での初期データは TanStack Router の `loader` を併用可。
- API 呼び出しの共通処理は `lib/` または `hooks/` に集約する。

---

## 6. スタイリング（Tailwind CSS）

- **Tailwind CSS v4** を利用。
- `styles.css` にて `@import "tailwindcss"` / `@import "tw-animate-css"` を使用。
- クラス結合は `lib/css.ts` の `cn()` ユーティリティを使用（`clsx` + `tailwind-merge`）。
- UI の色・半径などは `styles.css` の CSS 変数・`@theme inline` で管理。
- PWA 対応のため、ヘッダー・フッター等に `env(safe-area-inset-*)` を適用。

---

## 7. TypeScript / Lint / Format

- **TypeScript strict**（`tsconfig.json`）
  - `noUnusedLocals` / `noUnusedParameters` / `noFallthroughCasesInSwitch` など有効。
- ESLint は `@tanstack/eslint-config` を使用。
- Prettier 設定:
  - `semi: false`
  - `singleQuote: true`
  - `trailingComma: "all"`

---

## 8. 型定義

- 共通型は `src/types/index.ts` に集約。
- コンポーネント専用の Props 型は各 `index.tsx` 内に定義する。

---

## 9. 追加運用ルール

- **Shadcn/UI のコンポーネントは `components/atoms` に配置**し、直接編集せず必要なら `molecules` 以上でラップ。
- **命名**:
  - コンポーネント: `PascalCase`
  - ルートファイル: `kebab-case` or `index.tsx`（TanStack Router の file-based ルールに従う）
- **エイリアスを活用**: `@/` を基準に相対パスを短く保つ。

---

## 10. 補足

- ルールの対象は SPA（CSR）であり、RSC/Server Actions は前提にしない。
