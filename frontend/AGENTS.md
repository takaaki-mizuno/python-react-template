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
- `AuthUser.roles` / `AuthUser.permissions` は UI 表示制御と route guard 用であり、セキュリティ境界ではない。権限が必要な Backend endpoint は必ず Backend 側の permission dependency で守る
- permission 判定は `src/lib/permissions.ts` を使う。protected route では `_authenticated` parent の `requireAuth()` が `/api/auth/me` を server-confirming fetch した後、子 route の permission guard は `ensureQueryData(currentUserQueryOptions())` で同じ cache を読む
- 新しい file-based route を追加した場合は `src/routeTree.gen.ts` を再生成し、差分に含める
- login/register form は `AuthTextField` / `AuthFormShell` / `Button` / `Input` を使い、field の label・autocomplete・aria 紐付けを共通部品へ寄せる
- destructive account operations は typed confirmation と `toUserMessage()` による日本語 error message を使う。account deletion の確認 email field は誤操作防止のため `autoComplete="off"` にし、削除 error 表示時は error code に対応する field だけへ `aria-invalid` を立てる。429 や CSRF など field に紐づかない error では input を invalid にしない。account deletion success は `/login?redirect=/app` ではなく `/` へ遷移する
- auth form feedback は field-specific error と form-level error を区別する。field-specific error は該当 field だけに `aria-invalid` を立て、表示する alert の id を `aria-describedby` で関連付ける。無関係な field を invalid にしない
- form-level error は `role="alert"` で表示し、無関係な field に `aria-invalid` を立てない。現状の login / register / account deletion component は、form-level error がある場合に対象 form 内の input から alert id を `aria-describedby` で参照する
- 429、CSRF validation failure、network / fallback error など field に紐づかない error は form-level error として扱う。account deletion では input を invalid にしないが、現状どおり input は form alert を `aria-describedby` で参照してよい
- login の invalid credentials は現状 form-level error として扱い、email / password を invalid にしない。register の backend duplicate email や rate limit は現状 form-level error として扱う。register の client-side password length / confirmation mismatch は現状 field-specific error として password / password confirmation を invalid にする
- P8-FE-1 / P8-FE-2 / P8-FE-3 はこの契約に従う。login / register / account deletion の feedback 挙動変更が必要な場合は、component / route tests を明記した別 Task として扱い、shared feedback component 抽出に混ぜない

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

## Phase 8 OAuth/OIDC UI 規約

- OAuth/OIDC login button は login/register の既存 password form と併置する。provider list は backend の `/api/auth/oidc/providers` から読み、`providerId` と `displayName` だけを使う。provider 未設定、loading、error の場合は password form だけを表示し、実装説明文を画面に出さない。
- OIDC 開始は JSON API ではなく full-page redirect helper を使う。login は `/api/auth/oidc/{providerId}/start?redirect=...`、account deletion reauth は `/api/auth/oidc/{providerId}/reauth?redirect=/app/settings` へ遷移する。redirect は `URLSearchParams` で percent-encode し、query / hash を壊さない。
- Frontend callback route は作らない。backend callback が authorization code を交換し、session cookie / CSRF cookie を発行し、保存済み internal redirect path への最終 redirect まで完結する。SPA route、frontend state、browser history に authorization code、ID token、`access_token`、`refresh_token` を置かない。
- Login callback failure は `/login?oidcError=<machine-code>` を form-level message に変換する。`OIDC_IDENTITY_LINK_REQUIRED`、`OIDC_IDENTITY_LINK_DISABLED`、`OIDC_EMAIL_NOT_VERIFIED`、`OIDC_PROVISIONING_DISABLED` は user-facing message を持たせる。`ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` は DELETE `/api/auth/me` の JSON error code であり、login callback query には使わない。
- Login page は `OIDC_AUTHORIZATION_RATE_LIMITED`、`OIDC_PROVIDER_UNAVAILABLE`、`OIDC_PROVIDER_METADATA_INVALID`、`OIDC_PROVIDER_ACCESS_DENIED`、`OIDC_IDENTITY_UNAVAILABLE`、`OIDC_REAUTH_AUTHENTICATION_REQUIRED` も専用 message を持つ。未知の OIDC query code は generic OAuth/OIDC failure message にする。
- Account deletion が `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` を返した場合、`error.details` の linked providers (`providerId`, `displayName`) から reauth button を表示する。field に紐づかない error なので confirm email / password input を invalid にしない。
- linked providers が空配列の場合は reauth button を表示せず、再認証できる provider がないため support/admin deletion が必要である form-level message を表示する。
- Account deletion reauth callback result は settings page の form-level feedback として扱う。`oidcReauth=success` は success message、`OIDC_REAUTH_SUBJECT_MISMATCH`、`OIDC_REAUTH_STALE`、`OIDC_REAUTH_AUTH_TIME_REQUIRED`、`OIDC_PROVIDER_ACCESS_DENIED`、`OIDC_PROVIDER_UNAVAILABLE`、`OIDC_IDENTITY_UNAVAILABLE` は account deletion 用 error message にする。login page へ遷移させない。
- OIDC callback 後の unsafe request は現在の `csrf_token` cookie から `X-CSRF-Token` を読む。個別 route/component から `/api/auth/csrf` を直接 fetch せず、必ず `apiClient` を使う。
- Reauth callback 後は full-page load と `queryKeys.auth.me` の initial fetch で現在 user を読む。stale user cache を前提に account deletion submit を進めない。
