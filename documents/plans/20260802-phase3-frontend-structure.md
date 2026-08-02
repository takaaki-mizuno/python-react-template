# Phase 3 フロントエンド構造 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Worktree、`git add`、`git commit`、`git push`は使用しない。

**Goal:** `documents/reviews/20260801-review.md` の Phase 3「フロントエンド構造」を実装し、認証必須ルート、API error 処理、register UI、logout/cache 処理をテンプレートとして再利用しやすい形へ整える。

**Architecture:** TanStack Router の pathless layout route で認証必須ページを束ね、TanStack Query の auth query key を 1 本化する。Router と QueryClient の本番配線は `createAppRouter()` に切り出し、main と test helper の両方が同じ 401/403 handler と default error component を使う。API error は backend の error envelope に合わせて `ApiError` / `toUserMessage()` で正規化し、redirect は query string を含む internal `href` として扱う。UI は既存の landing token と shadcn 風 `atoms` を使い、依存追加なしで login/register form を共通部品へ寄せる。

**Tech Stack:** React 19、TypeScript 5.7、Vite 7.1、TanStack Router v1.132、TanStack Query v5.90、Tailwind CSS 4、Vitest、React Testing Library

---

## 背景

Phase 0 では backend/static 起動、SPA fallback、migration 整合などの即日修正を完了した。Phase 1 では backend の DI / UoW / error envelope / docs 制御を整えた。Phase 2 では認証セキュリティを強化し、unsafe `/api` request は CSRF middleware で守られ、backend の error は `{"error":{"code": "...", "message": "...", "details": [...]}}` 形式へ揃っている。

レビュー文書の推奨順序では、次に Phase 3 としてフロントエンド構造を扱う。

- `P1-19`: `/api/auth/me` の query key が `me` と `strictMe` の 2 系統に分かれ、二重取得と invalidate 事故を招く。
- `P1-18`: 認証必須ページの追加が route guard コピペと login redirect allowlist の 2 箇所同期になっている。
- `P1-17`: 画面滞在中の 401/403 を共通処理できず、セッション切れでユーザーが行き止まりになる。
- `P2-30`: `ApiError.body` が `unknown` のままで、画面ごとのエラーメッセージ処理が散る。
- `P0-4`: backend register API はあるが、frontend の register API / route / form がない。
- `P2-26`: logout 成功時に auth 以外の query cache が残る。
- `P2-27`: logout 失敗が unhandled rejection になり、ユーザーに失敗が伝わらない。
- `P2-28`: unsafe request が毎回 `/api/auth/csrf` へ往復する。
- `P2-29`: `apiClient` に PUT/PATCH/DELETE と AbortSignal 透過がない。
- `P2-31`: router の 404 / error page がない。
- `P2-32`: ログイン済みユーザーが `/login` を開ける。
- `P2-33`: `LoginForm` が shadcn 風 atoms を使わず、`autoComplete` / a11y 属性も不足している。
- `P2-34`: frontend tests に成功系、redirect allowlist、Header ログイン済み状態、cookies 単体などの穴がある。

## 現行コードの分析

- `frontend/src/lib/queryKeys.ts` は `auth.me` と `auth.strictMe` を持つ。`frontend/src/lib/authApi.ts` も `currentUserQueryOptions()` と `currentUserStrictQueryOptions()` に分かれている。
- `frontend/src/routes/app.tsx` は `currentUserStrictQueryOptions()` を `beforeLoad` 内で直接呼び、401 だけ `/login` へ redirect している。
- `frontend/src/routes/login.tsx` は `allowList = new Set(['/app'])` を route 内に持ち、認証必須 route が増えるたびに更新漏れが起きる。
- `frontend/src/main.tsx` は `new QueryClient()` の既定設定で、QueryCache / MutationCache の global error handler がない。
- `frontend/src/lib/apiError.ts` は `status` と `body: unknown` だけを保持し、backend error envelope の `error.code` を安全に取り出せない。
- `frontend/src/lib/apiClient.ts` は unsafe method 前に必ず `ensureCsrfToken()` を呼ぶ。cookie が既にあっても `/api/auth/csrf` へ往復する。
- `apiClient.post()` は `body ? JSON.stringify(body) : undefined` のため、`false`、`0`、`''` の body を送れない。
- `frontend/src/hooks/useAuthSession.ts` は logout 成功時に `auth.me` を `null` にし、`auth.strictMe` だけ削除する。ユーザー別の他 query cache は残る。
- `frontend/src/components/organisms/Header/index.tsx` は `await logout.mutateAsync()` を catch せず、失敗時は unhandled rejection になる。さらに `landingNavigation` を import しており、components から routes への逆依存がある。
- `frontend/src/components/organisms/Auth/LoginForm.tsx` は生 `<input>` / `<button>` を使い、既存 `frontend/src/components/atoms/button.tsx` を使っていない。`autoComplete` と `aria-invalid` もない。
- `components.json` の alias では `ui` が `@/components/atoms` を指している。`frontend/AGENTS.md` には `components/ui/` も書かれているが実体はないため、本 Phase では既存実体の `atoms` を正として扱い、依存追加はしない。
- TanStack Router v1 の file-based routing では `_` prefix の pathless layout route が URL path に出ない。`_authenticated.tsx` と `_authenticated.app.tsx` の構成で `/app` を認証 layout 配下に置ける。

## 方針とその理由

### 採用方針

1. test helper と `createAppRouter()` を先に作り、以降の route test が本番と同じ QueryClient / Router 配線を検証できる状態にする。
2. Query key 一本化を行い、guard、Header、login/register 成功後の cache 更新がすべて `queryKeys.auth.me` を見る状態にする。
3. 認証 redirect の判定を `frontend/src/lib/authRedirect.ts` に切り出し、allowlist 列挙ではなく「same-origin の内部 href だけ許可」という汎用判定にする。
4. guard は `staleTime: 0` の再確認を維持し、失効済み session を stale cache で通さない。P1-19 の二重取得は、Header の `useQuery(currentUserQueryOptions())` が `refetchOnMount: false` で guard 直後の cache に相乗りすることで解消する。
5. TanStack Router の pathless layout route `_authenticated` を追加し、認証必須 route はその子として置く。`/app` は `app.tsx` から `_authenticated.app.tsx` へ移す。
6. `ApiError` は backend の error envelope を理解し、`code` / `message` / `details` を型安全に取り出せるようにする。画面表示文言は `toUserMessage()` に集約する。
7. QueryClient を `createAppQueryClient()` factory 経由で生成し、401 は auth cache を `null` にして `/login?redirect=<現在 href>` へ送る。403 は `ApiError.code` を見て、`CSRF_VALIDATION_FAILED` は画面遷移させず form 側の error として残し、権限不足系だけ `/forbidden` へ送る。
8. `apiClient` は cookie に `csrf_token` があれば即使い、CSRF 403 のときだけ token を再 bootstrap して 1 回だけ retry する。PUT/PATCH/DELETE、AbortSignal、headers、falsy body を同時に直す。
9. login/register form は同じフォーム部品を使い、`Button` と新規 `Input` atom、`AuthFormShell` / `AuthTextField` molecules へ寄せる。
10. register UI は error message 共通化後に実装し、409/422/429/VALIDATION_ERROR を code 単位で表示し分ける。成功時は `queryKeys.auth.me` に user を入れて redirect 先へ遷移する。
11. 404/error/forbidden 画面は共通 `ErrorState` component で実装し、router default と `/forbidden` route で使い回す。
12. テストは各構造変更の直前に追加し、レビューの `P2-34` にある穴を Task 内へ分散して埋める。新規 jsdom test には必ず `// @vitest-environment jsdom` を先頭に置く。

### 採用理由

- `P1-19` を先に済ませると、後続の `_authenticated` layout、global 401 handler、register 成功時 cache 更新がすべて 1 つの query key に乗る。
- allowlist を列挙から内部 path 判定に変えると、認証必須 route を追加するたびに `/login` を編集する必要がなくなる。
- pathless layout は TanStack Router の公式機能であり、URL を `/app` のまま保ちながら認証 guard を 1 箇所へ閉じられる。
- backend は Phase 1 で error envelope に統一済みのため、frontend も status だけでなく `error.code` を扱う方が register / rate limit / CSRF で分岐しやすい。
- `/app?tab=settings` のような redirect は TanStack Router の `to` ではなく `href` で扱う。`to` は pathname 用であり、query string を含めると route match が崩れるためである。
- logout 失敗時に session cookie は HTTP-only のため frontend から消せない。失敗時に強制的に `/login` へ送ると、`/login` の logged-in redirect と矛盾する可能性がある。本計画では成功時だけ cache clear と遷移を行い、失敗時は Header 内に明示的な error を表示して「ログアウトできた」と誤認させない。
- `npx shadcn add label` は新規依存が必要になる可能性がある。Phase 3 では依存追加なしで既存 `Button` と同じ style 方針の `Input` atom を作り、label は native `<label>` を使う molecule に閉じる。

## 重要な設計決定

### 決定1: 保存済み redirect 先へ戻る遷移は `href` として扱い、`to` に query string を入れない

TanStack Router の `to` は pathname を表す。`/app?tab=settings` を `navigate({ to })` や `redirect({ to })` に入れると、`/app?tab=settings` という pathname として扱われ、`/app` route に match しない。Phase 3 では redirect search を「internal href」として正規化し、保存済み redirect 先へ戻る遷移は `navigate({ href })` / `redirect({ href })` を使う。一方で `/login` へ送る遷移は `to: '/login'` と `search: { redirect: currentHref }` を使い、手組み query string を避ける。

### 決定2: internal redirect 判定は WHATWG URL 解決後の origin/path で行う

`value.startsWith('/') && !value.startsWith('//')` だけでは、`/\evil.example` や `/<TAB>/evil.example` がブラウザで外部 origin へ解決される。`authRedirect.ts` は `new URL(value, window.location.origin)` で解決し、解決後の `url.origin === window.location.origin` を確認する。さらに `\` と ASCII 制御文字を含む値、`/login`、`/register` は fallback へ落とす。これにより logged-in redirect の自己ループと open redirect を防ぐ。

### 決定3: guard は毎回 `/api/auth/me` を再確認し、二重取得は `refetchOnMount: false` で解消する

既存 test `logout 後は cached user を使わず /me を再確認する` は、guard が stale cache を信用しないことを保証している。これを維持するため、`requireAuth()` は `staleTime: 0` 相当でサーバ確認する。`/app` 表示時の二重取得は、Header の `useQuery(currentUserQueryOptions())` が mount 時に stale data を再取得する構造が原因なので、`currentUserQueryOptions()` に `refetchOnMount: false` を設定し、guard が直前に埋めた同一 query cache を Header がそのまま使う。public route で cache が空の場合は通常どおり初回 fetch される。

### 決定4: 403 global handler は `CSRF_VALIDATION_FAILED` を `/forbidden` へ送らない

Phase 3 時点で role / permission は未実装であり、ユーザーが最も踏みやすい 403 は CSRF 失敗である。`apiClient` の retry 後も `CSRF_VALIDATION_FAILED` が残った場合は、form や mutation の error 表示に任せる。`/forbidden` へ送るのは `ApiError.status === 403` かつ `error.code !== 'CSRF_VALIDATION_FAILED'` の場合だけにする。

### 決定5: 本番 router 配線を `createAppRouter()` に切り出す

`main.tsx` は import 時に render するため、global 401/403 handler や default error component を直接置くとテスト不能になる。`frontend/src/lib/appRouter.tsx` に `createAppRouter()` を置き、QueryClient 生成、Router 生成、401/403 navigation、defaultNotFoundComponent、defaultErrorComponent をまとめる。`createAppRouter()` は外部生成済み QueryClient を受け取らず、`queryClientOptions` だけを受け取って handler 付き QueryClient を内部生成する。`createAppRouter()` の返り値型は明示注釈を付けず、`createRouter()` の推論で route tree の型を保持する。handler の循環参照だけ `AnyRouter | undefined` の `routerRef` に閉じ込め、アプリ全体の `Register.router` には `export type AppRouter = ReturnType<typeof createAppRouter>['router']` を登録する。`main.tsx` と route tests は同じ factory を使い、`main.tsx` から module augmentation を取り除く。

### 決定6: Phase 3 は 3a / 3b の実行ブロックに分けて進める

ユーザー指示により commit はしない。ただし Phase 3 は新規・変更ファイル数が多いため、計画内で 2 つの実行ブロックに分ける。Phase 3a は router/API/auth 基盤、Phase 3b は auth UI/register/error page を扱う。各 Task 完了後に `.superpowers/checkpoints/phase3/` へ patch と untracked 一覧を保存する。

## デザイン方針

- 対象は開発者向けテンプレートの認証・管理系 UI なので、**Utility & Function** を主軸にする。
- 色は既存の `landing-*` token と shadcn token を使い、アクセントは既存の blue (`--landing-accent`) に限定する。
- auth form は page section の中の単独フォームとして扱い、過度な装飾 card は増やさない。フォーム面は border と 8px 前後の radius、4px grid の spacing で整理する。
- ボタンは `frontend/src/components/atoms/button.tsx` を使う。text-only の logout / nav は既存 `site-nav-link` を維持しつつ error state は近接表示する。
- 入力欄は `Input` atom で `aria-invalid`、`aria-describedby`、focus ring、disabled state を統一する。

## スコープ外

- OAuth/OIDC login button と callback route は扱わない。
- role / permission / `_admin` layout は扱わない。ただし 403 handler と `/forbidden` route は将来の role guard の前提として作る。
- password reset、email verification、password change は扱わない。
- backend API は変更しない。
- `P3-15` の `npm run build` 順序変更、typecheck script 追加は Phase 4 / DX で扱う。
- Header の `landingNavigation` 逆依存解消 (`P3-17`) は、Phase 3 の auth 導線に必要な最小範囲だけに留める。全面的な dumb component 化は Phase 5 以降で扱う。
- `components.json` と `frontend/AGENTS.md` の `components/ui/` 不一致は本 Phase では実装に合わせて `atoms` を使う。ドキュメント全面同期は Phase 5 で扱う。

## 変更予定ファイル

### 作成するファイル

- `frontend/src/lib/authRedirect.ts`
  - redirect search の正規化、内部 path 判定、auth page 判定を置く。
- `frontend/src/lib/authGuard.ts`
  - `_authenticated` route から呼ぶ `requireAuth()` を置く。
- `frontend/src/lib/appRouter.tsx`
  - 本番とテストで共有する `createAppRouter()`、`AppRouter` 型、TanStack Router の module augmentation を置く。
- `frontend/src/lib/appRouter.type-test.ts`
  - `createAppRouter()` の返り値 router が route tree 型を保持していることを `tsc --noEmit` で検証する。
- `frontend/src/lib/queryClient.ts`
  - `createAppQueryClient()` と 401/403 判定 helper を置く。
- `frontend/src/lib/queryClient.test.ts`
  - QueryClient retry と global error callback を検証する。
- `frontend/src/lib/apiError.test.ts`
  - backend error envelope、legacy `detail`、plain message の抽出を検証する。
- `frontend/src/lib/authRedirect.test.ts`
  - `/app`、`/app?tab=x`、`//evil.example`、`https://evil.example`、`/\evil.example`、制御文字、auth page 自己参照、空値の正規化を検証する。
- `frontend/src/lib/cookies.test.ts`
  - cookie 読み取り、URL decode、存在しない cookie を検証する。
- `frontend/src/components/atoms/input.tsx`
  - shadcn 風 `Input` atom を定義する。
- `frontend/src/components/molecules/AuthTextField.tsx`
  - label、input、error/help text を 1 単位にした auth form field を定義する。
- `frontend/src/components/organisms/Auth/AuthFormShell.tsx`
  - login/register form の見出し、補助リンク、submit area の共通 shell を定義する。
- `frontend/src/components/organisms/Auth/RegisterForm.tsx`
  - register form を定義する。
- `frontend/src/components/organisms/Auth/RegisterForm.test.tsx`
  - register form の submit、required/a11y 属性、pending state を検証する。
- `frontend/src/components/organisms/ErrorState/index.tsx`
  - 404/error/forbidden で使う共通表示 component を定義する。
- `frontend/src/components/organisms/ErrorState/index.test.tsx`
  - ErrorState の表示と action を検証する。
- `frontend/src/routes/_authenticated.tsx`
  - 認証必須 route の pathless layout を定義する。
- `frontend/src/routes/register.tsx`
  - register page を定義する。
- `frontend/src/routes/register.test.tsx`
  - register 成功、409/422/429、redirect 正規化を検証する。
- `frontend/src/routes/forbidden.tsx`
  - 403 用 page を定義する。
- `frontend/src/test/renderRouter.tsx`
  - `createAppRouter()` を使う route test 用の `renderWithRouter()` helper を置く。
- `frontend/src/test/queryClient.ts`
  - router を伴わない unit test 専用の retry なし test QueryClient factory を置く。

### 変更するファイル

- `frontend/src/lib/queryKeys.ts`
  - `auth.strictMe` を削除し、`auth.me` だけにする。
- `frontend/src/lib/authApi.ts`
  - `fetchCurrentUserStrict()` / `currentUserStrictQueryOptions()` を削除し、`fetchCurrentUserOrNull()` を直接 `apiClient.get('/api/auth/me', { signal })` へ接続する。`registerWithPassword()` を追加する。
- `frontend/src/lib/apiError.ts`
  - `ApiError.code`、`ApiError.detail`、`toUserMessage()`、type guard を追加する。
- `frontend/src/lib/apiClient.ts`
  - CSRF 楽観利用、403 CSRF retry、PUT/PATCH/DELETE、AbortSignal/headers 透過、falsy body 対応を実装する。
- `frontend/src/hooks/useAuthSession.ts`
  - logout 成功時に `queryClient.clear()` し、失敗時は error を返せる形にする。
- `frontend/src/main.tsx`
  - `createAppRouter()` を呼んで render するだけにする。
- `frontend/src/routes/__root.tsx`
  - `RouterContext` に `auth` を足さない。root 表示と Header / Outlet 構成だけを維持する。
- `frontend/src/routes/app.tsx`
  - `_authenticated.app.tsx` へ移動し、個別 `beforeLoad` を削除する。既存 `/app` URL は維持する。
- `frontend/src/routes/login.tsx`
  - redirect 正規化 helper、logged-in user redirect、`toUserMessage()`、LoginForm 型変更へ追随する。
- `frontend/src/components/organisms/Header/index.tsx`
  - register 導線、ログイン済み表示 test、logout 失敗表示、logout 成功時 navigation を整える。
- `frontend/src/components/organisms/Auth/LoginForm.tsx`
  - `Button` / `Input` / `AuthTextField` を使い、`autoComplete` と `aria-invalid` を追加し、`onSubmit` 型を同期 `void` にする。
- `frontend/src/components/organisms/Auth/LoginForm.test.tsx`
  - submit、autocomplete、pending、error の a11y を検証する。
- `frontend/src/routes/login.test.tsx`
  - 成功系、401、redirect 汎用判定、ログイン済み `/login` redirect を追加する。
- `frontend/src/routes/app.test.tsx`
  - `_authenticated` layout 後の `/app` guard と query key 一本化へ更新する。
- `frontend/src/hooks/useAuthSession.test.tsx`
  - logout 成功時の `queryClient.clear()` と失敗時の error を検証する。
- `frontend/src/components/organisms/Header/index.test.tsx`
  - ログイン済み Header、register link、logout 成功/失敗を検証する。
- `frontend/src/lib/apiClient.test.ts`
  - CSRF cookie がある場合の no-bootstrap、CSRF 403 retry、PUT/PATCH/DELETE、AbortSignal、falsy body を検証する。
- `frontend/src/routeTree.gen.ts`
  - TanStack Router plugin が自動更新する。手編集しない。
- `frontend/AGENTS.md`
  - Phase 3 後の auth route 追加手順、query key 規約、API error 表示規約を追記する。
- `documents/plans/20260802-phase3-frontend-structure.md`
  - 実装中に進捗と検証結果を更新する。

### 変更しないファイル

- `backend/*`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/components.json`
- `docker-compose.yaml`

## チェックポイント方針

この作業では `git add` と `git commit` を使わない。Task 単位で復旧できるよう、各 Task 完了後に `.superpowers/checkpoints/phase3/task<N>-<short-name>/` へ patch と untracked 一覧を保存する。ただし checkpoint 自体を次回 archive に含めると再帰的に肥大するため、untracked 一覧では `.superpowers` を除外する。

```bash
rtk proxy mkdir -p .superpowers/checkpoints/phase3/task<N>-<short-name>
rtk git diff --binary -- > .superpowers/checkpoints/phase3/task<N>-<short-name>/tracked.patch
rtk git ls-files --others --exclude-standard -- ':!.superpowers' > .superpowers/checkpoints/phase3/task<N>-<short-name>/untracked-files.txt
```

`untracked-files.txt` が空でない場合だけ archive を作る。

```bash
rtk proxy tar -czf .superpowers/checkpoints/phase3/task<N>-<short-name>/untracked-files.tgz -T .superpowers/checkpoints/phase3/task<N>-<short-name>/untracked-files.txt
```

## 具体的なタスク

### Phase 3a: Router / API / Auth 基盤

### Task 1: baseline と Phase 3 境界を固定する

**Files:**
- Inspect: `documents/reviews/20260801-review.md`
- Inspect: `documents/plans/20260801-phase1-backend-foundation.md`
- Inspect: `documents/plans/20260802-phase2-auth-security.md`
- Inspect: `documents/plans/20260802-phase2-review-fixes.md`
- Inspect: `frontend/AGENTS.md`
- Inspect: `frontend/src/lib/`
- Inspect: `frontend/src/routes/`
- Inspect: `frontend/src/components/organisms/Auth/`

- [x] **Step 1.1: working tree と禁止事項を確認する**

```bash
rtk git status --short
rtk git branch --show-current
rtk git rev-parse --short HEAD
```

Expected:

- 既存の未コミット変更があれば Phase 3 と競合しないか読む。
- 既存変更を reset / checkout / clean しない。
- `git add`、`git commit`、`git push` を実行しない。

- [x] **Step 1.2: Phase 3 対象 ID をレビュー本文で確認する**

```bash
rtk grep -n "Phase 3|P1-17|P1-18|P1-19|P0-4|P2-26|P2-27|P2-28|P2-29|P2-30|P2-31|P2-32|P2-33|P2-34" documents/reviews/20260801-review.md
```

Expected:

- Phase 3 の順序と対象 ID を確認する。
- `P2-34` のテスト穴は各 Task の RED test に分散して埋める。

- [x] **Step 1.3: frontend baseline test と型検査を実行する**

```bash
cd frontend
rtk npm test
rtk npx tsc --noEmit
rtk npm run build
```

Expected:

- 既存 Vitest がすべて成功する。
- `tsc --noEmit` が成功する。
- `npm run build` が成功する。
- `%VITE_SITE_URL% is not defined` warning が出る場合は既存 warning として記録する。

### Task 2: test helper と app router factory を先に作る

**Review ID:** `P1-17`, `P2-31`, `P2-34`

**Files:**
- Create: `frontend/src/lib/appRouter.tsx`
- Create: `frontend/src/lib/appRouter.type-test.ts`
- Create: `frontend/src/lib/queryClient.ts`
- Create: `frontend/src/test/renderRouter.tsx`
- Create: `frontend/src/test/queryClient.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/routes/login.test.tsx`
- Modify: `frontend/src/routes/app.test.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`
- Modify: `frontend/src/components/organisms/LandingPage/index.test.tsx`

- [x] **Step 2.1: test helper を作る**

新規 test file は必要に応じて `// @vitest-environment jsdom` を先頭に置く。`frontend/src/test/queryClient.ts` は router を伴わない unit test 専用として、retry false の `createTestQueryClient()` を export する。route test はこの helper で作った QueryClient を `createAppRouter()` へ注入しない。`frontend/src/test/renderRouter.tsx` は `createAppRouter()` を使い、`QueryClientProvider` と `RouterProvider` を本番と同じ配線で返す。

`renderWithRouter()` は render 前に QueryClient cache を seed できる口を持つ。guard や Header mount が初期 render 中に走るため、render 後に返り値の `queryClient` へ `setQueryData()` しても間に合わない。

```ts
export function renderWithRouter(options?: {
  initialEntries?: Array<string>
  queryClientOptions?: DefaultOptions
  seed?: (queryClient: QueryClient) => void
}): {
  router: AppRouter
  queryClient: QueryClient
}
```

`@testing-library/user-event` は依存にないため返さない。既存テストと同じく `@testing-library/react` の `fireEvent` / `screen` を使う。`seed` は `const { router, queryClient } = createAppRouter(...)` の直後、`render(<QueryClientProvider ...>)` の前に呼ぶ。devtools の `vi.mock('@tanstack/react-devtools', ...)` と `vi.mock('@tanstack/react-router-devtools', ...)` は hoist の都合で共有 helper へ移さず、各 test file に残す。

- [x] **Step 2.2: `createAppRouter()` を作る**

`frontend/src/lib/appRouter.tsx` に次を定義する。

```ts
import type { DefaultOptions } from '@tanstack/react-query'
import {
  createRouter,
  type AnyRouter,
  type RouterHistory,
} from '@tanstack/react-router'

import { routeTree } from '@/routeTree.gen'

import { createAppQueryClient } from './queryClient'

export function createAppRouter(options?: {
  history?: RouterHistory
  queryClientOptions?: DefaultOptions
}) {
  let routerRef: AnyRouter | undefined
  const queryClient = createAppQueryClient({
    defaultOptions: options?.queryClientOptions,
    onUnauthorized: () => {
      void routerRef?.navigate({ to: '/login', search: { redirect: '/app' } })
    },
    onForbidden: () => undefined,
  })
  const router = createRouter({
    routeTree,
    history: options?.history,
    context: { queryClient },
    defaultPreload: 'intent',
    scrollRestoration: true,
    defaultStructuralSharing: true,
    defaultPreloadStaleTime: 0,
  })
  routerRef = router
  return { router, queryClient }
}

export type AppRouter = ReturnType<typeof createAppRouter>['router']

declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter
  }
}
```

この時点では既存 router 設定を移すだけで、401/403 handler と default error component は後続 Task で実装する。`createAppRouter()` は handler 付き QueryClient を内部生成できる形を先に固定するため、外部生成済み `queryClient` は受け取らない。返り値型に `{ router: Router; queryClient: QueryClient }` のような明示注釈を付けない。`Router` は型引数必須であり、`AnyRouter` を返り値に使うと `Link` / `navigate` / `redirect` / `Route.useSearch()` の route tree 型が失われるためである。handler が router を参照する循環は、`let routerRef: AnyRouter | undefined` を先に宣言し、QueryClient の callback closure が初回実行時に代入済み router を遅延参照する形で解く。`AnyRouter` の利用は handler 内の navigation に限定する。`main.tsx` は `const { router, queryClient } = createAppRouter()` を呼んで render するだけにし、既存の `declare module '@tanstack/react-router'` は `appRouter.tsx` へ移す。

`createAppQueryClient()` は Task 7 で本実装するが、Task 2 時点で `frontend/src/lib/queryClient.ts` を作り、retry などの既定値だけを持つ最小実装を置く。これにより Task 2 の `createAppRouter()` が存在しない module に依存しない。

Task 2 時点の最小実装でも、引数シグネチャは Task 7.2 の完成形と同じにする。`onUnauthorized` / `onForbidden` は Task 2 では QueryCache / MutationCache にまだ配線しなくてよいが、`createAppRouter()` のコードサンプルが型エラーにならないよう受け取れる形にしておく。`/forbidden` route は Task 7 まで存在しないため、Task 2 の `onForbidden` は no-op に留める。

- [x] **Step 2.3: 既存 route tests を helper へ移す**

対象:

- `frontend/src/routes/login.test.tsx`
- `frontend/src/routes/app.test.tsx`
- `frontend/src/components/organisms/Header/index.test.tsx`
- `frontend/src/components/organisms/LandingPage/index.test.tsx`

render を伴わない検証、たとえば既存 `app.test.tsx` の 500 test のように `await router.load()` 後の `router.state.matches.at(-1)?.status` だけを見る test は、`renderWithRouter()` へ無理に寄せず `createAppRouter()` を直接使う。

- [x] **Step 2.4: route 型の退化を防ぐ type-only test を作る**

`frontend/src/lib/appRouter.type-test.ts` を作成し、`createAppRouter()` の返り値 router が `AnyRouter` に広がっていないことを `tsc --noEmit` で検証する。`.d.ts` では実行文を書けないため使わない。`frontend/tsconfig.json` は `**/*.ts` / `**/*.tsx` を include しているため、この file は通常の型検査で拾われる。Vitest の標準実行対象になる `.test.ts` ではなく `.type-test.ts` にする。

```ts
import { createAppRouter } from './appRouter'

const { router } = createAppRouter()

void router.navigate({ to: '/login', search: { redirect: '/app' } })
// @ts-expect-error unknown route must stay rejected
void router.navigate({ to: '/typo' })
```

- [x] **Step 2.5: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- login.test.tsx app.test.tsx Header/index.test.tsx LandingPage/index.test.tsx
rtk npx tsc --noEmit
```

Expected:

- `createAppRouter()` の返り値 router から route tree 型が落ちていない。
- `main.tsx` に TanStack Router の module augmentation が残っていない。
- `frontend/src/lib/appRouter.type-test.ts` の `// @ts-expect-error unknown route must stay rejected` が有効で、`router.navigate({ to: '/typo' })` が型エラーになる状態を継続的に検査できる。

### Task 3: `ApiError` と user-facing message を共通化する

**Review ID:** `P2-30`

**Files:**
- Modify: `frontend/src/lib/apiError.ts`
- Create: `frontend/src/lib/apiError.test.ts`
- Modify: `frontend/src/routes/login.tsx`
- Modify: `frontend/src/routes/login.test.tsx`

- [x] **Step 3.1: error envelope の RED test を書く**

`frontend/src/lib/apiError.test.ts` の先頭には `// @vitest-environment jsdom` を置く。次を検証する。

- backend error envelope から `code` と `detail` を取得できる。
- legacy `{ detail: string }` と `{ message: string }` を扱える。
- null / JSON でない body でも throw しない。
- `toUserMessage()` の優先順位は `code override > status override > 組み込み status 既定 > fallback` である。
- code 既定として `CSRF_VALIDATION_FAILED` は `セッションの確認に失敗しました。ページを再読み込みして、もう一度お試しください。` を返す。

- [x] **Step 3.2: `ApiError` と `toUserMessage()` を実装する**

既定文言:

- `CSRF_VALIDATION_FAILED`: `セッションの確認に失敗しました。ページを再読み込みして、もう一度お試しください。`
- 400/422: `入力内容を確認してください。`
- 401: `ログインが必要です。`
- 403: `この操作を実行する権限がありません。`
- 409: `現在の状態では処理できません。`
- 429: `試行回数が多すぎます。時間をおいて再度お試しください。`
- fallback: `通信に失敗しました。時間をおいて再度お試しください。`

- [x] **Step 3.3: login route の error 分岐を `toUserMessage()` に置き換える**

Login 用 overrides:

- `INVALID_CREDENTIALS`: `メールアドレスまたはパスワードが正しくありません。`
- `LOGIN_RATE_LIMITED`: `ログイン試行回数が多すぎます。時間をおいて再度お試しください。`
- 422: `入力内容を確認してください。`
- fallback: `ログインに失敗しました。時間をおいて再度お試しください。`

- [x] **Step 3.4: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- apiError.test.ts login.test.tsx
rtk npx tsc --noEmit
```

### Task 4: redirect 正規化と logged-in redirect をまとめて実装する

**Review ID:** `P1-18`, `P2-32`

**Files:**
- Create: `frontend/src/lib/authRedirect.ts`
- Create: `frontend/src/lib/authRedirect.test.ts`
- Modify: `frontend/src/routes/login.tsx`
- Modify: `frontend/src/routes/login.test.tsx`

- [x] **Step 4.1: redirect helper の RED test を書く**

`frontend/src/lib/authRedirect.test.ts` の先頭には `// @vitest-environment jsdom` を置く。jsdom では cross-origin の `history.pushState()` が `SecurityError` になるため、origin は既定の `http://localhost:3000` のまま使う。必要な場合は同一 origin path だけ `window.history.pushState(null, '', '/app?tab=settings')` のように設定して、次を検証する。

- `/app`、`/app?tab=settings`、`/reports/2026.08` は同じ href として許可する。
- `//evil.example`、`https://evil.example/app`、`/\evil.example`、`/\tevil.example`、制御文字を含む値は fallback `/app` へ落とす。
- `/login`、`/login?redirect=/app`、`/register` は fallback `/app` へ落とす。
- 空値、`undefined`、`null` は fallback `/app` へ落とす。

- [x] **Step 4.2: helper を実装する**

契約:

- `normalizeRedirectHref(value, fallback = '/app')` を export する。
- `new URL(value, window.location.origin)` で解決後、`url.origin === window.location.origin` を確認する。
- `url.pathname` が `/login` または `/register` なら fallback を返す。
- raw value に `\` または ASCII 制御文字が含まれる場合は fallback を返す。
- 戻り値は `pathname + search + hash` の internal href とする。

- [x] **Step 4.3: login route の validateSearch と beforeLoad を実装する**

- `validateSearch` は `normalizeRedirectHref(search.redirect)` を使う。
- logged-in user が `/login` を開いた場合は `redirect({ href: redirect })` する。
- `/api/auth/me` が 500 の場合は catch して form を表示する。
- `loginWithPassword()` は `AuthUser` を返すため、login 成功時は `queryClient.invalidateQueries({ queryKey: queryKeys.auth.root })` ではなく `queryClient.setQueryData(queryKeys.auth.me, user)` を使う。
- login 成功時の遷移は `navigate({ href: redirect })` とする。
- `queryKeys.auth.root` は `queryKeys.auth.me` の親 key として残す。ただし認証成功時の即時同期には使わず、将来 auth 配下 query をまとめて invalidate/remove する必要がある場合だけ使う。

- [x] **Step 4.4: login redirect tests を追加する**

`frontend/src/routes/login.test.tsx`:

- login 成功後に `navigate({ href: redirect })` 相当で `/app?tab=settings` へ遷移する。
- login 成功後に `queryKeys.auth.me` へ response user が入り、余分な `/api/auth/me` 往復に依存しない。
- external / protocol-relative / backslash redirect は `/app` へ正規化される。
- `/login?redirect=/login` は自己ループせず `/app` へ正規化される。
- logged-in user は form を表示せず redirect 先へ送られる。
- `/api/auth/me` が 500 の場合は form を表示する。

- [x] **Step 4.5: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- authRedirect.test.ts login.test.tsx
rtk npx tsc --noEmit
```

### Task 5: auth query key を 1 本化し、guard の再確認方針を固定する

**Review ID:** `P1-19`

**Files:**
- Modify: `frontend/src/lib/queryKeys.ts`
- Modify: `frontend/src/lib/authApi.ts`
- Modify: `frontend/src/hooks/useAuthSession.ts`
- Modify: `frontend/src/routes/app.tsx`
- Modify: `frontend/src/routes/app.test.tsx`
- Modify: `frontend/src/hooks/useAuthSession.test.tsx`

- [x] **Step 5.1: `strictMe` 削除と guard 再確認の RED test を書く**

`app.test.tsx` / `useAuthSession.test.tsx` で次を検証する。

- `queryKeys.auth.strictMe` を使わない。
- guard は cached user があっても stale cache だけでは通さず、`/api/auth/me` を再確認する。
- Header の `useAuthSession()` は guard が直前に埋めた `queryKeys.auth.me` cache がある場合、mount 時に追加 fetch しない。

- [x] **Step 5.2: auth API を 1 本化する**

実装内容:

- `queryKeys.auth.strictMe` を削除する。
- `fetchCurrentUserStrict()` を削除し、`fetchCurrentUserOrNull()` 内で直接 `apiClient.get<AuthUser>('/api/auth/me')` を呼ぶ。
- `currentUserQueryOptions()` は `queryKeys.auth.me`、`fetchCurrentUserOrNull()`、`retry: false` を持つ。
- `staleTime` は設定しない、または明示的に `0` として guard の再確認を維持する。
- `refetchOnMount: false` を設定し、Header が guard 直後の cache を持つ場合に二重取得しないようにする。
- `frontend/src/routes/app.tsx` の既存 `beforeLoad` は、Task 6 で route file を移動するまでの暫定形として `currentUserQueryOptions()` ベースへ書き換える。`currentUserStrictQueryOptions()` import を残さない。

- [x] **Step 5.3: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- app.test.tsx useAuthSession.test.tsx
rtk npx tsc --noEmit
rtk grep -n "strictMe|currentUserStrict" frontend/src
```

Expected:

- grep は 0 件。`rtk grep` が no match で非 0 exit になる場合は、出力 0 件であることを確認できればよい。

### Task 6: `_authenticated` pathless layout を追加する

**Review ID:** `P1-18`, `P1-19`

**Files:**
- Create: `frontend/src/lib/authGuard.ts`
- Create: `frontend/src/routes/_authenticated.tsx`
- Move: `frontend/src/routes/app.tsx` -> `frontend/src/routes/_authenticated.app.tsx`
- Modify: `frontend/src/routes/app.test.tsx`
- Modify: `frontend/src/routeTree.gen.ts` (generated)

- [x] **Step 6.1: pathless layout の RED test を書く**

`app.test.tsx`:

- `/app` に未ログインで来ると `/login?redirect=/app` へ遷移する。
- `/app` にログイン済みで来ると page heading `アプリ` が表示される。
- 500 は login redirect に潰さず route error になる。
- Header の二重取得は Task 5 の `refetchOnMount: false` で既に固定されているため、この Task では pathless layout の guard 境界だけを確認する。

- [x] **Step 6.2: `requireAuth()` を実装する**

- `context.queryClient.fetchQuery(currentUserQueryOptions())` で毎回再確認する。
- user が `null` なら `redirect({ to: '/login', search: { redirect: currentHref } })` を投げる。`to` へ query string を直接入れない。
- user がある場合は redirect せず処理を続ける。RouterContext には `auth` を足さない。

- [x] **Step 6.3: `_authenticated` route と app route 移動を実装する**

- `_authenticated.tsx` は `Outlet` と `beforeLoad: requireAuth` を持つ。
- `app.tsx` は `_authenticated.app.tsx` へ移動し、個別 `beforeLoad` を削除する。
- `__root.tsx` の `RouterContext` に `auth` は足さない。Header も route context を掘らない。

- [x] **Step 6.4: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- app.test.tsx
rtk npx tsc --noEmit
rtk npm run build
```

### Task 7: QueryClient global 401/403 handler を appRouter へ実装する

**Review ID:** `P1-17`

**Files:**
- Modify: `frontend/src/lib/queryClient.ts`
- Create: `frontend/src/lib/queryClient.test.ts`
- Modify: `frontend/src/lib/appRouter.tsx`
- Create: `frontend/src/routes/forbidden.tsx`
- Modify: `frontend/src/routes/app.test.tsx`

- [x] **Step 7.1: QueryClient factory の RED test を書く**

`frontend/src/lib/queryClient.test.ts` の先頭には `// @vitest-environment jsdom` を置く。次を検証する。

- query / mutation が `ApiError(401)` で失敗すると `onUnauthorized` が呼ばれる。
- `ApiError(403, { error: { code: 'FORBIDDEN', ... } })` では `onForbidden` が呼ばれる。`PERMISSION_DENIED` など将来の合成 code も「CSRF 以外の 403」として同じ分岐に入る。
- `ApiError(403, { error: { code: 'CSRF_VALIDATION_FAILED', ... } })` では `onForbidden` を呼ばない。
- 401/403 は retry しない。

- [x] **Step 7.2: `createAppQueryClient()` を実装する**

`frontend/src/lib/queryClient.ts` の契約:

```ts
export function createAppQueryClient(handlers?: {
  onUnauthorized?: () => void
  onForbidden?: (error: ApiError) => void
  defaultOptions?: DefaultOptions
}): QueryClient
```

`queries.retry` は 401/403 で false、それ以外は `failureCount < 2`。`mutations.retry` は false。`onForbidden` は `CSRF_VALIDATION_FAILED` を除外する。test で retry を変えたい場合は、外部 QueryClient を注入せず `defaultOptions` で上書きする。

- [x] **Step 7.3: `createAppRouter()` に navigation handler を配線する**

- `createAppRouter(options?: { history?: RouterHistory; queryClientOptions?: DefaultOptions })` は、`createAppQueryClient({ defaultOptions: options?.queryClientOptions, ...handlers })` を内部で呼ぶ。
- handler は `router.navigate()` を呼ぶため、`let routerRef: AnyRouter | undefined` を先に宣言し、handler closure が初回実行時に代入済み router を遅延参照する。`createAppRouter()` の返り値は Task 2 と同じく推論に任せ、`AnyRouter` を返り値型に広げない。
- 401 handler の最初に `queryClient.setQueryData(queryKeys.auth.me, null)` を実行する。これにより `/login` へ移った直後に Header が古い user cache を一瞬表示しない。
- 現在 path は `router.state.location.pathname` / `router.state.location.search` から取る。`window.location` は使わない。
- `/login`、`/register` 表示中の 401 は redirect しない。
- それ以外の 401 は `router.navigate({ to: '/login', search: { redirect: currentHref } })`。
- 403 は `/forbidden` 表示中でなければ `router.navigate({ to: '/forbidden' })`。

- [x] **Step 7.4: route test を追加する**

- `/app` 表示後に query が 401 になった場合、`/login?redirect=/app` へ移る。
- `/login` 表示中の 401 は redirect loop しない。
- 403 `CSRF_VALIDATION_FAILED` は `/forbidden` へ遷移しない。
- 403 `FORBIDDEN` または合成 `PERMISSION_DENIED` は `/forbidden` へ遷移する。
- mutation 403 の route test では、test 専用の小さな component を test file 内に作り、button click で `useMutation()` を発火させる。production route にテスト用 UI は追加しない。

- [x] **Step 7.5: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- queryClient.test.ts app.test.tsx
rtk npx tsc --noEmit
```

### Task 8: `apiClient` の CSRF と method/options を整える

**Review ID:** `P2-28`, `P2-29`

**Files:**
- Modify: `frontend/src/lib/apiClient.ts`
- Modify: `frontend/src/lib/apiClient.test.ts`
- Modify: `frontend/src/lib/authApi.ts`

- [x] **Step 8.1: CSRF 楽観利用と retry の RED test を書く**

`frontend/src/lib/apiClient.test.ts` の先頭には既存どおり `// @vitest-environment jsdom` を置く。次を追加する。

- `csrf_token` cookie がある unsafe request は `/api/auth/csrf` を呼ばない。
- cookie がない unsafe request は `/api/auth/csrf` を 1 回呼ぶ。
- 403 `CSRF_VALIDATION_FAILED` は token 再取得後に 1 回だけ retry する。
- retry 後も 403 の場合は `ApiError` を投げる。

- [x] **Step 8.2: method/options/body の RED test を書く**

- PUT/PATCH/DELETE が使える。
- AbortSignal が fetch に渡る。
- `false`、`0`、`''` の body が送信される。
- 呼び出し側 headers を壊さず CSRF header を追加する。

- [x] **Step 8.3: `apiClient` と auth queryFn を実装する**

- `apiClient.get<T>(input, options?: ApiRequestOptions)` を追加し、signal を透過する。
- `post` / `put` / `patch` / `delete` は `{ body, signal, headers }` を受ける。
- `body !== undefined` で JSON stringify する。
- `fetchCurrentUserOrNull()` は `queryFn: ({ signal })` から渡された signal を `apiClient.get()` へ渡す。

- [x] **Step 8.4: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- apiClient.test.ts apiError.test.ts
rtk npx tsc --noEmit
```

### Task 9: logout cache と失敗 UX を修正する

**Review ID:** `P2-26`, `P2-27`

**Files:**
- Modify: `frontend/src/hooks/useAuthSession.ts`
- Modify: `frontend/src/hooks/useAuthSession.test.tsx`
- Modify: `frontend/src/components/organisms/Header/index.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`

- [x] **Step 9.1: logout 成功時 cache clear の RED test を書く**

`useAuthSession.test.tsx`:

- `queryClient.setQueryData(['projects'], ...)` など auth 以外の cache を置く。
- logout 成功後に `['projects']` の query data が消えることを検証する。
- `queryClient.getQueryCache().getAll()` が空であることは assert しない。active observer が query を再生成し得るためである。

- [x] **Step 9.2: logout 失敗時 error の RED test を書く**

`Header/index.test.tsx`:

- logged-in Header で logout request が 500 の場合、`ログアウトに失敗しました。時間をおいて再度お試しください。` を `role="alert"` で表示する。
- 失敗時に `/login` へ遷移しない。
- unhandled rejection が発生しない。

- [x] **Step 9.3: hook と Header を実装する**

- logout mutation `onSuccess` で `queryClient.clear()`。
- `onError` では cache を消さない。
- Header は `try/catch` で `mutateAsync()` を扱い、成功時だけ `navigate({ to: '/login', search: { redirect: '/app' } })`。
- pending 中は logout button を disabled にする。

- [x] **Step 9.4: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- useAuthSession.test.tsx Header/index.test.tsx
rtk npx tsc --noEmit
```

### Phase 3b: Auth UI / Register / Error 表示

### Task 10: auth form の共通 UI と LoginForm を整える

**Review ID:** `P2-33`, carry-over `P3-16`

**Files:**
- Create: `frontend/src/components/atoms/input.tsx`
- Create: `frontend/src/components/molecules/AuthTextField.tsx`
- Create: `frontend/src/components/organisms/Auth/AuthFormShell.tsx`
- Modify: `frontend/src/components/organisms/Auth/LoginForm.tsx`
- Modify: `frontend/src/components/organisms/Auth/LoginForm.test.tsx`
- Modify: `frontend/src/routes/login.tsx`
- Modify: `frontend/src/routes/login.test.tsx`

- [x] **Step 10.1: LoginForm a11y の RED test を書く**

- email input は `autoComplete="email"`。
- password input は `autoComplete="current-password"`。
- form 全体の error 表示時は input に `aria-describedby` を付けるが、原因 field を特定できないため `aria-invalid` は付けない。
- frontend validation で原因 field を特定できる場合だけ、その field に `aria-invalid="true"` を付ける。
- pending 中 submit button は disabled。
- `onSubmit` は `(values) => void` 型で扱える。

- [x] **Step 10.2: `Input` atom と `AuthTextField` を作る**

`Input` は既存 `Button` と同じ shadcn 由来の function component style に揃える。`React.FC` は使わない。`AuthTextField` は native `<label htmlFor>` と、呼び出し側が指定する `aria-describedby` / `aria-invalid` の関連付けを管理する。form-level message 自体の描画は form 側に置き、field component 内に二重の help/error text 経路を持たせない。

- [x] **Step 10.3: `AuthFormShell` の責務を route page に置く**

`AuthFormShell` は h1 を出す page shell とし、`LoginForm` の中では使わない。`frontend/src/routes/login.tsx` の既存 h1 は `AuthFormShell` へ移し、h1 が二重にならないようにする。

- [x] **Step 10.4: LoginForm を共通部品へ移す**

- `Button` / `AuthTextField` を使う。
- `onSubmit` 型を `(values: LoginValues) => void` にする。
- `handleSubmit` は async にしない。

- [x] **Step 10.5: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- LoginForm.test.tsx login.test.tsx
rtk npx tsc --noEmit
```

### Task 11: register API / route / form を追加する

**Review ID:** `P0-4`

**Files:**
- Modify: `frontend/src/lib/authApi.ts`
- Create: `frontend/src/components/organisms/Auth/RegisterForm.tsx`
- Create: `frontend/src/components/organisms/Auth/RegisterForm.test.tsx`
- Create: `frontend/src/routes/register.tsx`
- Create: `frontend/src/routes/register.test.tsx`
- Modify: `frontend/src/routes/login.tsx`
- Modify: `frontend/src/components/organisms/Header/index.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`
- Modify: `frontend/src/routeTree.gen.ts` (generated)

- [x] **Step 11.1: RegisterForm の RED test を書く**

`RegisterForm.test.tsx` の先頭には `// @vitest-environment jsdom` を置く。次を検証する。

- email/password/password confirmation を submit する。
- password input は `autoComplete="new-password"`。
- confirmation 不一致では API submit を呼ばず、`パスワードが一致しません。` を表示する。
- pending 中 submit button は disabled。
- backend 由来 error message を `role="alert"` で表示する。

- [x] **Step 11.2: `registerWithPassword()` と RegisterForm を実装する**

- `registerWithPassword(payload)` は `apiClient.post<AuthUser>('/api/auth/register', { body: payload })` を呼ぶ。
- frontend validation は required、confirmation 一致、password minLength 12 に限定する。

- [x] **Step 11.3: register route の RED test を書く**

`register.test.tsx` の先頭には `// @vitest-environment jsdom` を置く。次を検証する。

- register 成功時、`queryKeys.auth.me` に user が入り、`href` redirect 先へ遷移する。
- `/register?redirect=/app%3Ftab%3Dsettings` が成功後 `/app?tab=settings` へ遷移する。
- 409 `EMAIL_ALREADY_REGISTERED` は `このメールアドレスはすでに登録されています。ログインしてください。`。
- 422 `VALIDATION_ERROR` は `入力内容を確認してください。` または `パスワードの条件を確認してください。`。
- 429 `REGISTER_RATE_LIMITED` は rate limit 文言。
- logged-in user は `redirect({ href: redirect })` で redirect 先へ送られる。
- `WEAK_PASSWORD` は API 直呼び出し向けの defense-in-depth として override に残してよいが、ブラウザ経由の主テストは `VALIDATION_ERROR` を使う。

- [x] **Step 11.4: register route を実装する**

- `validateSearch` は `normalizeRedirectHref()` を使う。
- logged-in user は `redirect({ href: redirect })`。
- submit 成功時は `queryClient.setQueryData(queryKeys.auth.me, user)` 後に `navigate({ href: redirect })`。
- error message は `toUserMessage()` の code override で出し分ける。

- [x] **Step 11.5: register の cache 更新が login と同じ規約に沿うことを確認する**

- Task 4 で login 成功時は `queryClient.setQueryData(queryKeys.auth.me, user)` に統一済みである。
- register 成功時も同じく `queryClient.setQueryData(queryKeys.auth.me, user)` 後に `navigate({ href: redirect })` とし、`invalidateQueries({ queryKey: queryKeys.auth.root })` には戻さない。

- [x] **Step 11.6: login/register 相互リンクと Header 導線を追加する**

- `/login` には「アカウントを作成」リンクを置き、redirect href を `/register` に引き継ぐ。
- `/register` には「ログイン」リンクを置き、redirect href を `/login` に引き継ぐ。
- Header 未ログイン時は `ログイン` と `新規登録` を表示し、どちらも `/app` redirect を持つ。

- [x] **Step 11.7: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- RegisterForm.test.tsx register.test.tsx login.test.tsx Header/index.test.tsx
rtk npx tsc --noEmit
rtk npm run build
```

### Task 12: 404 / error / forbidden 表示を追加する

**Review ID:** `P2-31`

**Files:**
- Create: `frontend/src/components/organisms/ErrorState/index.tsx`
- Create: `frontend/src/components/organisms/ErrorState/index.test.tsx`
- Modify: `frontend/src/lib/appRouter.tsx`
- Modify: `frontend/src/routes/forbidden.tsx`
- Modify: `frontend/src/routes/app.test.tsx`

- [x] **Step 12.1: ErrorState component test を書く**

`ErrorState/index.test.tsx` の先頭には `// @vitest-environment jsdom` を置く。title / message / statusCode / primary action を検証する。

- [x] **Step 12.2: ErrorState を実装する**

`landing-shell` と既存 token を使い、compact な error state にする。内部 error message はそのまま表示しない。

- [x] **Step 12.3: `createAppRouter()` に router default を設定する**

- `defaultNotFoundComponent`: 404 用 `ErrorState`
- `defaultErrorComponent`: unknown error 用 `ErrorState`

`main.tsx` ではなく `createAppRouter()` に置く。

- [x] **Step 12.4: forbidden route を ErrorState へ置き換える**

`/forbidden` は 403 文言を表示する。primary action は固定で `/app` へ戻す。

- [x] **Step 12.5: route tests を追加する**

- 未定義 route は 404 ErrorState。
- render error は default error component。
- `/forbidden` は 403 文言。

- [x] **Step 12.6: targeted GREEN と型検査を確認する**

```bash
cd frontend
rtk npm test -- ErrorState/index.test.tsx app.test.tsx
rtk npx tsc --noEmit
```

### Task 13: cookies test と残りの Header test を補強する

**Review ID:** `P2-34`

**Files:**
- Create: `frontend/src/lib/cookies.test.ts`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`

- [x] **Step 13.1: cookies.ts 単体テストを追加する**

`cookies.test.ts` の先頭には `// @vitest-environment jsdom` を置く。存在する cookie、URL encoded 値、prefix が似ている別 cookie、存在しない cookie を検証する。

- [x] **Step 13.2: Header ログイン済み状態 test を補強する**

- `/api/auth/me` が user を返すと email と logout button が表示される。
- login/register link は表示されない。

- [x] **Step 13.3: frontend full test と型検査を確認する**

```bash
cd frontend
rtk npm test
rtk npx tsc --noEmit
```

### Task 14: frontend/AGENTS.md と計画書を更新する

**Files:**
- Modify: `frontend/AGENTS.md`
- Modify: `documents/plans/20260802-phase3-frontend-structure.md`

- [x] **Step 14.1: frontend/AGENTS.md に Phase 3 規約を追記する**

追記内容:

- auth query key は `queryKeys.auth.me` の 1 本だけを使う。
- 認証必須 route は `_authenticated` pathless layout 配下へ置く。
- redirect は `authRedirect.ts` で internal href として正規化し、`href` で遷移する。
- API error 表示は `toUserMessage()` を使い、画面ごとに `ApiError.body` を直接 parse しない。
- unsafe request は `apiClient` を使い、個別に `/api/auth/csrf` を fetch しない。
- login/register form は `AuthTextField` / `AuthFormShell` / `Button` / `Input` を使う。

- [x] **Step 14.2: 計画書の進捗と実行結果欄を更新する**

本計画の「進捗サマリー」「実行結果」「未対応事項」を更新する。

### Task 15: 品質ゲートと smoke を実行する

**Files:**
- Inspect: frontend 全体
- Inspect: backend static build output
- Modify: `documents/plans/20260802-phase3-frontend-structure.md`

- [x] **Step 15.1: frontend format/lint を実行する**

```bash
cd frontend
rtk npm run check
```

Expected:

- Prettier / ESLint が成功する。
- `npm run check` は write/fix を行うため、実行後に差分を確認する。

- [x] **Step 15.2: frontend tests を実行する**

```bash
cd frontend
rtk npm test
```

Expected:

- 全 Vitest が成功する。

- [x] **Step 15.3: frontend build を実行する**

```bash
cd frontend
rtk npm run build
```

Expected:

- build が成功する。
- `frontend/src/routeTree.gen.ts` が最新 route 構成に追随している。
- `backend/static/` への build output は生成物として扱い、commit 対象にしない。

- [x] **Step 15.4: backend static smoke を実行する**

backend を background で起動し、同じ shell 内で HTTP 確認と終了処理を行う。port 8000 が使用中の場合は 8001 以降の空き port を使う。

```bash
cd backend
rtk uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!
cleanup() {
  rtk kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT
rtk curl --retry 10 --retry-connrefused --retry-delay 1 -i http://127.0.0.1:8000/login
rtk curl -i http://127.0.0.1:8000/register
rtk curl -i http://127.0.0.1:8000/app
cleanup
if rtk curl --max-time 2 -sSf http://127.0.0.1:8000/login >/dev/null 2>&1; then
  echo "server still responds after cleanup"
  exit 1
fi
```

Expected:

- build 済み static がある場合、各 deep link が `200 text/html` を返す。
- `manage.py serve` は reload=True の uvicorn 子プロセスを持ち `$!` だけでは確実に落ちないため、smoke では reload なしの `uvicorn app.main:app` を直接起動する。
- cleanup 後に同じ port が応答しないことを確認する。
- curl では SPA 内 redirect は検証できないため、ここでは backend の SPA fallback だけを確認する。
- 未ログイン `/app` の client-side redirect は route test で検証済みであることを確認する。

- [x] **Step 15.5: repository diff を確認する**

```bash
rtk git diff --check
rtk git status --short -- ':!.superpowers'
```

Expected:

- whitespace error がない。
- 変更ファイルが Phase 3 範囲に収まっている。
- `git add` は実行しない。

### Task 16: Phase 3 コードレビュー指摘を修正する

**Review source:** Claude Code Phase 3 frontend structure code review

**Files:**
- Modify: `frontend/src/hooks/useAuthSession.ts`
- Modify: `frontend/src/hooks/useAuthSession.test.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`
- Modify: `frontend/src/lib/appRouter.tsx`
- Modify: `frontend/src/components/organisms/ErrorState/index.tsx`
- Modify: `frontend/src/components/organisms/ErrorState/index.test.tsx`
- Modify: `frontend/src/lib/apiError.ts`
- Modify: `frontend/src/lib/apiError.test.ts`
- Modify: `frontend/src/components/molecules/AuthTextField.tsx`
- Modify: `frontend/src/components/organisms/Auth/LoginForm.tsx`
- Modify: `frontend/src/components/organisms/Auth/LoginForm.test.tsx`
- Modify: `frontend/src/components/organisms/Auth/RegisterForm.tsx`
- Modify: `frontend/src/components/organisms/Auth/RegisterForm.test.tsx`
- Regenerate: `frontend/src/components/atoms/input.tsx`
- Modify: `frontend/src/routes/login.tsx`
- Modify: `frontend/src/lib/authRedirect.ts`
- Modify: `frontend/src/lib/authRedirect.test.ts`
- Modify: `frontend/src/lib/authGuard.ts`
- Modify: `frontend/src/lib/apiClient.ts`
- Modify: `frontend/src/lib/apiClient.test.ts`
- Modify: `frontend/src/routes/app.test.tsx`

- [x] **Step 16.1: logout 後の再ログインで Header が復帰しない回帰を修正する**

`useAuthSession()` の component-local `hasLoggedOut` state を削除し、`queryKeys.auth.me` の cache を user 表示の唯一の情報源に戻す。logout 成功時は `queryClient.clear()` 後に auth cache を `null` で再作成する。Header を常駐させたまま logout、login、`/app` 復帰まで行い、新しい user が表示される統合テストを追加する。テストは旧 `hasLoggedOut` 実装を一時的に再導入すると失敗することを確認する。

- [x] **Step 16.2: router と error state の規約違反を修正する**

`appRouter.tsx` の import 崩れを修正する。`ErrorState` の primary action は生の `<a href>` ではなく型安全な TanStack Router `Link` とし、現行の遷移先 `/` と `/app` を union 型で制約する。global 401 handler は auth page 判定より前に `queryKeys.auth.me` を `null` に更新し、現行 API では発火経路が限定的で将来の authenticated API query/mutation 向けであることをコメントに残す。

- [x] **Step 16.3: API error と auth form の a11y を修正する**

`toUserMessage()` に 409 の組み込み文言を追加する。Login の backend error と Register の form-level error は input へ `aria-describedby` だけを関連付け、原因 field を特定できる password length / confirmation mismatch のときだけ該当 password field に `aria-invalid` を付ける。未使用の `AuthTextField.errorMessage` / `helpText` 経路は削除し、説明関連付けを `describedBy` に一本化する。

- [x] **Step 16.4: shadcn Input と login submit handler を規約へ合わせる**

`Input` は `npx shadcn@latest add input --yes --overwrite` で再生成する。login route の `onSubmit` から不要な `return Promise.resolve()` を削除し、LoginForm / RegisterForm とも `(values) => void` の契約へ揃える。

- [x] **Step 16.5: redirect、auth guard、CSRF retry の将来リスクを抑える**

auth page 判定は trailing slash を除去して `/login/` と `/register/` も拒否する。auth guard の `staleTime: 0` と intent preload の往復コストは、認証必須 route 増加時に auth 専用 staleTime を検討する判断条件としてコメントに残す。CSRF validation retry は進行中 bootstrap を強制的に置き換え、古い bootstrap の完了が新しい共有 Promise を解除しないよう Promise 同一性を確認する。競合を再現する test を追加し、修正前に bootstrap が3回走って失敗することを確認する。

- [x] **Step 16.6: 弱い二重取得 test を補強する**

Header 描画成立直後だけの `waitFor(fetch count === 1)` をやめ、後続の React 処理が一巡した後にも `/api/auth/me` が1回だけであることを検証する。

- [x] **Step 16.7: second review の軽微な指摘を精査して修正する**

- `/api/auth/me` 二重取得 test の固定 `setTimeout(10)` を削除し、router が `idle` になった後に React の pending effect を `act` で flush してから fetch 回数を検証する。
- `useAuthSession` の cache 更新 test は logout を実行していないため、テスト名を「未ログイン状態から auth cache が更新されると user を返す」へ訂正する。logout -> login の実フローは Header integration test を正とする。
- TanStack Router は `caseSensitive` 未指定時に false であるため、redirect の auth page 判定も pathname を小文字化し、`/LOGIN` と `/REGISTER/` を自己参照として拒否する。修正前に `/LOGIN` がそのまま返って test が失敗することを確認する。
- `ErrorState.primaryAction.to` の union は現時点の遷移先 `/` と `/app` を明示的に制約できているため維持し、利用先追加時に route 型からの導出を検討する。
- auth guard の毎回 `/me` fetch は stale cache を信用しない決定3を維持する。認証必須 route 増加時の再検討条件は `authGuard.ts` のコメントを正とする。

- [x] **Step 16.8: review fix 後の品質ゲートを実行する**

```bash
cd frontend
rtk npm run check
rtk npm test
rtk npx tsc --noEmit
rtk npm run build
cd ..
rtk git diff --check
rtk git status --short -- ':!.superpowers'
```

## 進捗サマリー

- [x] Task 1: baseline と Phase 3 境界を固定する
- [x] Task 2: test helper と app router factory を先に作る
- [x] Task 3: `ApiError` と user-facing message を共通化する
- [x] Task 4: redirect 正規化と logged-in redirect をまとめて実装する
- [x] Task 5: auth query key を 1 本化し、guard の再確認方針を固定する
- [x] Task 6: `_authenticated` pathless layout を追加する
- [x] Task 7: QueryClient global 401/403 handler を appRouter へ実装する
- [x] Task 8: `apiClient` の CSRF と method/options を整える
- [x] Task 9: logout cache と失敗 UX を修正する
- [x] Task 10: auth form の共通 UI と LoginForm を整える
- [x] Task 11: register API / route / form を追加する
- [x] Task 12: 404 / error / forbidden 表示を追加する
- [x] Task 13: cookies test と残りの Header test を補強する
- [x] Task 14: frontend/AGENTS.md と計画書を更新する
- [x] Task 15: 品質ゲートと smoke を実行する
- [x] Task 16: Phase 3 コードレビュー指摘を修正する

## 完了条件

- [x] `queryKeys.auth.strictMe` と `currentUserStrictQueryOptions()` が削除されている。
- [x] `/api/auth/me` は `queryKeys.auth.me` だけで取得・cache・invalidate される。
- [x] guard は stale cache を信用せず `/api/auth/me` を再確認する。
- [x] Header は `refetchOnMount: false` により guard 直後の `queryKeys.auth.me` cache に相乗りし、`/app` 表示時に `/api/auth/me` を二重取得しない。
- [x] `/app` は `_authenticated` pathless layout 配下にあり、URL は `/app` のままである。
- [x] 認証必須 route の追加時に page ごとの `beforeLoad` コピペが不要になっている。
- [x] `createAppRouter()` の返り値は `createRouter()` の推論型を保ち、TanStack Router の `Register.router` は `AppRouter` として `appRouter.tsx` に登録されている。
- [x] `to: '/typo'` のような存在しない route が型エラーになる状態を維持し、`AnyRouter` は handler 内の遅延参照にだけ使われている。
- [x] `/login` と `/register` の redirect search は外部 URL、protocol-relative URL、backslash、制御文字、auth page 自己参照を拒否する。
- [x] query string / hash を含む redirect は `href` で遷移し、`to` に query string を入れていない。
- [x] `createAppRouter()` が QueryClient、Router、401/403 handler、default error component の本番配線を持ち、外部生成済み QueryClient を注入しない。
- [x] QueryClient global handler が 401 を `/login?redirect=<現在 href>` へ処理し、403 のうち `CSRF_VALIDATION_FAILED` 以外を `/forbidden` へ処理する。
- [x] QueryClient global 401 handler は `queryKeys.auth.me` を `null` に更新してから `/login` へ遷移する。
- [x] 401/403 は QueryClient retry の対象外である。
- [x] `ApiError` が backend error envelope の `error.code` と `error.message` を型安全に取り出せる。
- [x] `toUserMessage()` の優先順位が `code override > status override > 組み込み status 既定 > fallback` で固定されている。
- [x] 画面表示文言は `toUserMessage()` に集約され、route component が `ApiError.body` を直接 parse していない。
- [x] `apiClient` が PUT/PATCH/DELETE、AbortSignal、headers、falsy body を扱える。
- [x] TanStack Query の queryFn から渡される AbortSignal が `fetchCurrentUserOrNull()` と `apiClient.get()` を通って fetch へ届く。
- [x] unsafe request は既存 `csrf_token` cookie を使い、cookie があるだけなら `/api/auth/csrf` へ毎回往復しない。
- [x] CSRF 403 `CSRF_VALIDATION_FAILED` のときだけ 1 回 token 再取得 + retry する。
- [x] logout 成功時に auth 以外の QueryClient cache も消える。active observer による query 再生成を前提に、cache 件数が空であることには依存しない。
- [x] logout 後に同じ SPA 上で再ログインすると、Header が新しい `queryKeys.auth.me` user を表示する。
- [x] logout 失敗時に unhandled rejection が出ず、ユーザーに失敗が表示される。
- [x] `LoginForm` が `Button` / `Input` / `AuthTextField` を使い、`autoComplete` と a11y 属性を持つ。
- [x] login/register 成功時はどちらも `queryClient.setQueryData(queryKeys.auth.me, user)` で auth cache を同期し、認証成功直後の余分な `/api/auth/me` 往復に依存しない。
- [x] `AuthFormShell` の h1 は route page 側にあり、LoginForm 内と二重になっていない。
- [x] `RegisterForm` と `/register` route が追加され、409/422 `VALIDATION_ERROR` / 429 を user-facing message として表示できる。
- [x] Header 未ログイン時に login/register 導線が表示される。
- [x] ログイン済みユーザーが `/login` / `/register` を開いた場合、redirect 先へ送られる。
- [x] router の 404 / default error / `/forbidden` が `ErrorState` で表示される。
- [x] `frontend/AGENTS.md` に Phase 3 後の auth route / query key / error message 規約が書かれている。
- [x] frontend `npm run check`、`npm test`、`npx tsc --noEmit`、`npm run build` が成功している。
- [x] `git diff --check` が clean である。
- [x] `git add`、`git commit`、`git push` を実行していない。

## 実行結果

実行日時: 2026-08-02

- branch / HEAD: `feature/db-auth` / `615077f`
- targeted GREEN:
  - `rtk npm test -- login.test.tsx app.test.tsx Header/index.test.tsx LandingPage/index.test.tsx`
  - `rtk npm test -- apiError.test.ts login.test.tsx`
  - `rtk npm test -- authRedirect.test.ts login.test.tsx`
  - `rtk npm test -- app.test.tsx useAuthSession.test.tsx`
  - `rtk npm test -- app.test.tsx`
  - `rtk npm test -- queryClient.test.ts app.test.tsx`
  - `rtk npm test -- apiClient.test.ts apiError.test.ts`
  - `rtk npm test -- useAuthSession.test.tsx Header/index.test.tsx`
  - `rtk npm test -- LoginForm.test.tsx login.test.tsx`
  - `rtk npm test -- RegisterForm.test.tsx register.test.tsx login.test.tsx Header/index.test.tsx`
  - `rtk npm test -- ErrorState/index.test.tsx app.test.tsx`
- 型検査: 各 targeted step で `rtk npx tsc --noEmit` 成功。
- frontend format/lint: `rtk npm run check` 成功。初回は ESLint 指摘を修正後、再実行で成功。
- frontend full test: `rtk npm test` 成功。14 files / 78 tests passed。
- frontend build: `rtk npm run build` 成功。既存 warning として `%VITE_SITE_URL% is not defined` が出る。
- static deep link smoke: `uvicorn app.main:app --host 127.0.0.1 --port 8017` で起動し、`/login`、`/register`、`/app` がすべて `200 OK` / `text/html`。port 8000 は停止確認時に既存プロセスが応答したため、既存プロセスへ触れず 8017 で再実行した。
- smoke cleanup: port 8017 の uvicorn 停止後、`curl --max-time 2 -sSf http://127.0.0.1:8017/login` が connection refused になることを確認。
- `git diff --check`: clean。
- `rtk git status --short -- ':!.superpowers'`: Phase 3 範囲の frontend / documents 差分のみ。`git add` / `git commit` / `git push` は未実行。
- Phase 3 code review fix:
  - Header の logout -> login 回帰 test は修正版で成功し、旧 `hasLoggedOut` 実装を一時再導入すると `next@example.com` を表示できず失敗することを確認した。
  - CSRF bootstrap 競合 test は修正前に bootstrap 3 回で失敗し、Promise 同一性を確認する修正後は bootstrap 2 回で成功した。
  - review fix 後に `rtk npm run check` を再実行し、全対象ファイルが unchanged、exit 0 であることを確認した。
  - review fix 後に `rtk npm test` 14 files / 78 tests、`rtk npx tsc --noEmit`、`rtk npm run build`、`rtk git diff --check` が成功した。
  - build warning は既存の `%VITE_SITE_URL% is not defined` のみ。
- Second review fix:
  - `normalizeRedirectHref('/LOGIN')` は修正前に `/LOGIN` を返して test が失敗し、case-insensitive な auth page 判定へ修正後は fallback `/app` を返すことを確認した。`/REGISTER/` も同じ test で固定した。
  - `/api/auth/me` 二重取得 test から固定10ms待ちを削除し、router idle 後の React effect flush へ置き換えた。
  - `useAuthSession` の cache 更新 test 名を実際の操作に合わせて訂正した。
  - `ErrorState.primaryAction.to` union と auth guard の毎回 `/me` fetch は現時点の明示的な設計判断として維持した。
  - second review fix 後に `rtk npm run check`、`rtk npm test` 14 files / 78 tests、`rtk npx tsc --noEmit`、`rtk npm run build` が成功した。

## 未対応事項

- OAuth/OIDC login UI と callback route は Phase 5 以降で扱う。
- role / permission guard と `_admin` layout は権限管理 Phase で扱う。
- password reset、email verification、password change は別 Phase で扱う。
- `P3-15`: `npm run build` を `typecheck && vite build` にする作業は Phase 4 / DX で扱う。
- `P3-17`: Header の完全な dumb component 化と `landingNavigation` 逆依存解消は、Phase 3 では auth 導線に必要な最小限に留め、別途扱う。
- `components.json` と `frontend/AGENTS.md` の `components/ui/` 不一致は、Phase 5 のドキュメント同期で整理する。
- logout 失敗時に HTTP-only `session_token` cookie を frontend から削除することはできない。失敗時の強制 logout 体験が必要なら、backend 側で失敗時にも cookie clearing response を返す設計を別 Phase で検討する。

## 参考

- TanStack Router v1 docs: `_` prefix の file route segment は pathless layout route として URL path に出ない。
- TanStack Router v1 docs: `createFileRoute()` の path string は bundler plugin / CLI が route file に合わせて管理する。
