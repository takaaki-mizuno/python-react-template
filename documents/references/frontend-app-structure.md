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
- account settings route は `/app/settings`。認証必須 route なので `_authenticated` 配下に置く。
- 保護された route が `<Outlet />` を持たない page route と path prefix を共有する場合、TanStack Router の trailing underscore を使う。`/app/settings` は `routes/_authenticated.app_.settings.tsx` として定義し、`_authenticated.app.tsx` に nest させない。
- `/admin/users` も同じ理由で `routes/_authenticated.admin_.users.tsx` として定義する。`_authenticated.admin.tsx` は管理トップ page であり `<Outlet />` を持たない。

---

## 5. データ取得 / API アクセス

- **API アクセスは TanStack Query を利用する**。
  - ルートコンポーネントや UI から直接 `fetch` せず、`useQuery` 等のフックで扱う。
  - `QueryClient` は `main.tsx` で Provider に設定することを推奨。
- ルート単位での初期データは TanStack Router の `loader` を併用可。
- API 呼び出しの共通処理は `lib/` または `hooks/` に集約する。

## 5.1 Auth / Permission Guard

- `AuthUser` は `id`、`email`、`roles`、`permissions` を持つ。Frontend の role / permission は表示制御と navigation guard 用であり、最終的な認可境界ではない。
- permission check helper は `src/lib/permissions.ts` の `hasPermission()` / `hasAnyPermission()` を使う。role 名ではなく permission code を見る。
- 認証必須 route は `_authenticated` parent route の `requireAuth()` で守る。個別 permission が必要な route は `requirePermission("permission:code")` または `requireAnyPermission([...])` を `beforeLoad` に追加する。
- `_authenticated` 配下の child guard は `queryClient.ensureQueryData(currentUserQueryOptions())` を使い、parent `requireAuth()` が直前に取得した `/api/auth/me` cache を再利用する。
- user がいない場合は `/login?redirect=<current href>` へ送る。user はいるが permission がない場合は `/forbidden` へ送る。`/api/auth/me` の 5xx は redirect に変換しない。
- Header などの共通 UI で admin link を出す場合も `hasPermission(user, "admin:access")` で表示制御するだけに留め、Backend API は必ず permission dependency で守る。
- 自分自身の role / permission を変更する UI を後続で作る場合は、成功後に `queryClient.invalidateQueries({ queryKey: queryKeys.auth.me })` を呼び、auth cache を更新する。

## 5.2 Admin CRUD

- Admin API client は `src/lib/<feature>Api.ts` に置き、HTTP query は `URLSearchParams` で組み立てる。
- Admin 一覧の route search は `offset` を必須の内部状態とし、`search`、`isActive`、`role` は未指定時に省略する。
- Reusable UI は `molecules` に置く。検索 toolbar、data table、offset pagination、confirm dialog は user 固有の副作用を持たせない。
- Feature screen は `organisms/<Feature>/` に置く。React Query、mutation、error message、form state はこの層で扱う。
- Admin 画面は表中心の業務 UI にし、landing page 的な hero や card の入れ子を避ける。

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
