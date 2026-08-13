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
│   │   ├── atoms/           # shadcn/ui 生成コンポーネントのみ
│   │   ├── molecules/       # atoms の組み合わせ
│   │   └── organisms/       # Header / LandingPage / Auth などページ単位に近い複合 UI
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
- shadcn/ui 由来の atom は `src/components/atoms/` に配置する。`src/components/atoms/` には shadcn/ui 生成コンポーネント以外を置かない
- shadcn/ui コンポーネント追加は `frontend` の pinned local CLI (`npm exec -- shadcn add <name> --yes`) を第一候補にし、`npx` で latest 指定した CLI は使わない。CLI が registry / component library の対話プロンプトやネットワーク制約で完走しない場合は、同じ pinned CLI の `npm exec -- shadcn view <name>` で公式 registry content を確認し、この repo の alias (`@/lib/css`, `@/components/atoms`) に合わせて `src/components/atoms/` へ追加する。生成・追加後は `npm run check` で repo style に整形する
- shadcn atom のローカル差分は最小限にする。日本語 accessible label など呼び出し側で指定できるものは atoms を直接書き換えず、呼び出し側で `aria-label` / `showCloseButton={false}` / `SheetClose` などを使って上書きする。現時点の local patch は `field.tsx` の型 import 整理のみで、再生成時はこの差分を確認して維持または意図的に破棄する
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
- Backend error response は RFC 9457 Problem Details (`application/problem+json`) であり、`ApiError` は `type` / `title` / `status` / `detail` / `instance` / `code` / `errors` を読む。旧 `{ error: ... }` envelope fallback は追加しない
- API boundary の TypeScript 型は Backend wire format と同じ `snake_case` を使う。UI 内部で別名にする場合は API client 境界で明示変換する
- API 由来の日時は Unix timestamp seconds として扱い、表示には `formatUnixTimestampSeconds()` を使う。JavaScript milliseconds と混同しない
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

## i18n

- 翻訳本文の正は `src/lib/i18n/locales/{ja,en}/*.json`。`src/lib/i18n/resources.ts` は JSON import と集約だけを行い、翻訳本文を直書きしない
- 新規 UI 文言は component / route に直書きせず、用途に応じて `common` / `auth` / `landing` / `app` / `admin` namespace に追加する。日本語と英語の JSON key 構造は `src/lib/i18n/resources.test.ts` で一致させる
- current language の書き手は `src/lib/i18n/LanguageSyncManager.tsx` に集約する。mutation handler や login/register handler から `i18n.changeLanguage()` を直接呼ばない
- public route は `/ja/...` / `/en/...` の URL locale を優先し、authenticated route は `/app` / `/admin` のように locale prefix を持たず `AuthUser.language_code` を優先する
- React component 外の翻訳は `src/lib/i18n/i18n.ts` の i18n instance を使う。`src/lib/apiError.ts` のような pure utility で `useTranslation()` を呼ばない
- 日付・数値など locale 依存 format は `src/lib/i18n/formatters.ts` に集約し、画面で `Intl.DateTimeFormat('ja-JP')` などを直書きしない
- 新しい言語を追加する場合は、backend の `SUPPORTED_LANGUAGE_CODES`、`users.language_code` CHECK、`auth_oidc_authorization_states.language_code` CHECK、frontend の `languageOptions`、locale JSON、formatter locale map、translation key parity test を同じ変更で更新する

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

- OAuth/OIDC login button は login/register の既存 password form と併置する。provider list は backend の `/api/auth/oidc/providers` から読み、`provider_id` と `display_name` だけを使う。provider 未設定、loading、error の場合は password form だけを表示し、実装説明文を画面に出さない。
- OIDC 開始は JSON API ではなく full-page redirect helper を使う。login は `/api/auth/oidc/{provider_id}/start?redirect=...`、account deletion reauth は `/api/auth/oidc/{provider_id}/reauth?redirect=/app/settings` へ遷移する。redirect は `URLSearchParams` で percent-encode し、query / hash を壊さない。
- Frontend callback route は作らない。backend callback が authorization code を交換し、session cookie / CSRF cookie を発行し、保存済み internal redirect path への最終 redirect まで完結する。SPA route、frontend state、browser history に authorization code、ID token、`access_token`、`refresh_token` を置かない。
- Login callback failure は `/login?oidc_error=<machine-code>` を form-level message に変換する。`OIDC_IDENTITY_LINK_REQUIRED`、`OIDC_IDENTITY_LINK_DISABLED`、`OIDC_EMAIL_NOT_VERIFIED`、`OIDC_PROVISIONING_DISABLED` は user-facing message を持たせる。`account_deletion_oidc_reauth_required` は DELETE `/api/auth/me` の JSON error code であり、login callback query には使わない。
- Login page は `OIDC_AUTHORIZATION_RATE_LIMITED`、`OIDC_PROVIDER_UNAVAILABLE`、`OIDC_PROVIDER_METADATA_INVALID`、`OIDC_PROVIDER_ACCESS_DENIED`、`OIDC_IDENTITY_UNAVAILABLE`、`OIDC_REAUTH_AUTHENTICATION_REQUIRED` も専用 message を持つ。未知の OIDC query code は generic OAuth/OIDC failure message にする。
- Account deletion が `account_deletion_oidc_reauth_required` を返した場合、Problem Details `errors` の linked providers (`provider_id`, `display_name`) から reauth button を表示する。field に紐づかない error なので confirm email / password input を invalid にしない。
- linked providers が空配列の場合は reauth button を表示せず、再認証できる provider がないため support/admin deletion が必要である form-level message を表示する。
- Account deletion reauth callback result は settings page の form-level feedback として扱う。`oidc_reauth=success` は success message、`OIDC_REAUTH_SUBJECT_MISMATCH`、`OIDC_REAUTH_STALE`、`OIDC_REAUTH_AUTH_TIME_REQUIRED`、`OIDC_PROVIDER_ACCESS_DENIED`、`OIDC_PROVIDER_UNAVAILABLE`、`OIDC_IDENTITY_UNAVAILABLE` は account deletion 用 error message にする。login page へ遷移させない。
- OIDC callback 後の unsafe request は現在の `csrf_token` cookie から `X-CSRF-Token` を読む。個別 route/component から `/api/auth/csrf` を直接 fetch せず、必ず `apiClient` を使う。
- Reauth callback 後は full-page load と `queryKeys.auth.me` の initial fetch で現在 user を読む。stale user cache を前提に account deletion submit を進めない。
