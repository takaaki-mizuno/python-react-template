# Frontend shadcn UI Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 既存の画面レイアウトと visual design は後方互換性を捨て、React/Vite frontend を shadcn/ui 主体のテンプレート UI に再構築する。入力欄、認証フロー、OIDC、redirect、logout、account deletion、route guard などの機能 contract は維持する。

**Architecture:** `frontend/src/components/atoms` は shadcn CLI で生成した UI primitives だけを置く。`molecules` と `organisms` は atoms を合成して auth、header、landing、settings、error state を構成する。旧 `landing-*` / `site-*` CSS class は段階的に撤去し、Tailwind tokens と shadcn variants を UI の正にする。

**Tech Stack:** React 19、TypeScript 5.7、Vite 7.1、TanStack Router、TanStack Query、Tailwind CSS 4、shadcn/ui CLI v4、Radix/Base UI、lucide-react、Vitest、React Testing Library

---

## Verified Current State

- Tailwind CSS は導入済み。`frontend/vite.config.ts` は `@tailwindcss/vite` を使い、`frontend/src/styles.css` は `@import 'tailwindcss'` を読み込んでいる。
- shadcn/ui 設定は導入済み。`frontend/components.json` の `aliases.ui` は `@/components/atoms` を指している。
- 現在の atoms は `frontend/src/components/atoms/button.tsx` と `frontend/src/components/atoms/input.tsx` のみ。`frontend/src/components/ui` は存在しない。
- 現行 UI は `landing-*` / `site-*` class に強く依存しており、Header、LandingPage、ErrorState、auth pages、app/settings に Tailwind 直書きが残っている。
- ユーザー要件により、現行 visual design の維持は不要。機能 contract と accessibility は維持する。

## Review Decisions

- Claude Code review の A/B は修正対象にする。ただし今回は Header を redesign 対象に含めるため、「Header が変わっていないこと」ではなく「Header の機能 contract が維持され、旧 class が消えること」を検証する。
- `frontend/CLAUDE.md` の `(atoms/molecules/ui)` 表記も修正対象に含める。
- `--destructive` は Alert の `text-destructive/90` でも AA を満たすよう `#b91c1c` に固定する。`AuthFormFeedback` では `AlertDescription` に `!text-destructive` を明示し、shadcn destructive Alert の親 selector に詳細度で負けないようにする。
- `.dark` は shadcn dark token として整備して残す。現時点では dark mode toggle を作らないが、将来 `.dark` を付与しても neutral/landing 二重体系に戻らないようにする。
- 視覚検証を full verification に含める。`/`、`/login`、`/register`、`/app`、`/app/settings`、`/forbidden` を desktop/mobile で確認する。
- `CardTitle` 単独に heading semantics を依存しない。`CardHeader` 内の見出しは明示的な `<h1>` / `<h2>` / `<h3>` を使う。
- Generated shadcn v4 components can expose either `asChild` or `render` composition APIs depending on the underlying implementation. After generation, inspect the generated atom exports and trigger/link props before applying the snippets below. If a generated component uses `render` instead of `asChild`, use that generated API while preserving the same DOM role/name/href behavior.
- Radix-backed shadcn components need targeted jsdom polyfills in Vitest before Header tests can open `DropdownMenu` or `Sheet`. Add only missing APIs (`ResizeObserver`, pointer capture methods, `scrollIntoView`) before generating/migrating UI components; do not replace jsdom's built-in `DOMRect` or `PointerEvent`.

## Design Direction

- Tone: quiet, utilitarian, shadcn-native application shell.
- Avoid: old landing-specific palette, oversized rounded panels, decorative bespoke CSS systems, and custom navigation/button styling.
- Prefer: shadcn cards, menus, sheet navigation, badges, tabs, clear form fields, restrained neutral tokens, lucide icons inside actionable controls.
- Functional UI content stays the same; visual hierarchy and layout can change freely.

## Functional Contracts To Preserve

- Login fields: `メールアドレス` email input、`パスワード` password input、submit `ログイン`。
- Register fields: `メールアドレス`、`パスワード`、`パスワード確認`、submit `アカウントを作成`。
- Account deletion fields: `メールアドレスを入力して削除を確認`、`現在のパスワード`、submit `アカウントを削除`。
- Login/register redirect search must keep working.
- OIDC provider buttons must still render `{displayName}で続行` and call existing full-page redirect helpers.
- Account deletion must keep `noValidate`, empty password as `undefined`, field-specific invalid state, form-level alert behavior, reauth buttons, and success redirect to `/`.
- Header must keep unauthenticated login/register links, authenticated email display, logout success redirect to `/login?redirect=/app`, logout error alert, and mobile navigation close behavior.
- Logout pending state keeps the account trigger focusable and exposes progress with `aria-busy`; duplicate logout submission is prevented by disabling the logout menu item while pending.
- Route guards for `/app`, `/admin`, `/app/settings`, `/login`, and `/register` must keep current behavior.

## File Structure

- `frontend/src/styles.css`: replace app-level visual foundation with shadcn-first tokens and remove obsolete `landing-*` / `site-*` component classes.
- `frontend/src/test/setup.ts`: provide jsdom polyfills required by Radix-backed shadcn components.
- `frontend/vite.config.ts`: configure Vitest setup files.
- `frontend/src/components/atoms/*.tsx`: shadcn-generated components only.
- `frontend/src/components/molecules/AuthTextField.tsx`: compose `Field`, `FieldLabel`, and `Input`.
- `frontend/src/components/molecules/AuthFormFeedback.tsx`: compose `Alert` for form-level feedback.
- `frontend/src/components/molecules/OidcProviderButton.tsx`: compose `Button`.
- `frontend/src/components/organisms/Header/*`: rebuild with `NavigationMenu`, `Sheet`, `Button`, `DropdownMenu`, `Avatar`, and `Alert`.
- `frontend/src/components/organisms/LandingPage/*`: rebuild using `Badge`, `Button`, `Card`, `Separator`, `Tabs`, and lucide icons.
- `frontend/src/components/organisms/Auth/*`: rebuild auth shell/forms with `Card`, `Field`, `Alert`, `Separator`, and `Button`.
- `frontend/src/components/organisms/ErrorState/index.tsx`: rebuild with `Card`, `Badge`, and `Button`.
- `frontend/src/routes/_authenticated.app.tsx`: rebuild app page with `Card`, `Button`, and `Badge`.
- `frontend/src/routes/_authenticated.app_.settings.tsx`: rebuild settings layout with `Breadcrumb` and shadcn spacing.
- `frontend/src/routes/_authenticated.admin.tsx`: rebuild admin placeholder with `Card`.
- `frontend/AGENTS.md` / `frontend/CLAUDE.md`: document the shadcn-only atoms workflow and remove `ui` wording ambiguity.

---

### Task 0: Add Vitest jsdom setup for Radix-backed shadcn components

**Files:**
- Create: `frontend/src/test/setup.ts`
- Modify: `frontend/vite.config.ts`

- [x] **Step 1: Create shared test setup file**

Create `frontend/src/test/setup.ts`:

```ts
import { vi } from 'vitest'

class ResizeObserverMock implements ResizeObserver {
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}

Object.defineProperty(globalThis, 'ResizeObserver', {
  configurable: true,
  value: ResizeObserverMock,
})

if (typeof Element !== 'undefined') {
  Object.defineProperty(Element.prototype, 'hasPointerCapture', {
    configurable: true,
    value: vi.fn(() => false),
  })

  Object.defineProperty(Element.prototype, 'setPointerCapture', {
    configurable: true,
    value: vi.fn(),
  })

  Object.defineProperty(Element.prototype, 'releasePointerCapture', {
    configurable: true,
    value: vi.fn(),
  })

  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  })
}
```

Expected:

- Radix Popper/Dialog/Menu tests can run under jsdom.
- Node-environment tests also load this setup file, so DOM prototype polyfills are guarded behind `typeof Element !== 'undefined'`.
- Do not polyfill `DOMRect` or `PointerEvent`; jsdom 27 already provides those APIs and replacing them would make tests less faithful.
- No production bundle imports this file.

- [x] **Step 2: Register setup file in Vite/Vitest config**

In `frontend/vite.config.ts`, change the config imports so `defineConfig` comes from Vitest:

```ts
import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
```

Keep the existing Vite plugins and other imports unchanged. Then add a `test` block inside the returned config:

```ts
    test: {
      setupFiles: ['./src/test/setup.ts'],
    },
```

Expected:

- `vitest run` loads the setup file for all tests.
- TypeScript accepts the `test` property in Vite config.
- Existing per-file `// @vitest-environment jsdom` comments can remain.

- [x] **Step 3: Run current checks and full tests before UI migration**

Run:

```bash
rtk npm --prefix frontend run check:ci
rtk npm --prefix frontend test
```

Expected:

- `check:ci` passes after adding `frontend/src/test/setup.ts` and editing `frontend/vite.config.ts`.
- All current frontend tests pass before any UI component migration starts. This establishes that the global Vitest setup did not change existing test behavior.

- [x] **Step 4: Skip commit per user instruction**

Not run. The user explicitly instructed not to touch git during implementation.

---

### Task 1: Pin shadcn CLI and add required atoms

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/components/atoms/alert.tsx`
- Create: `frontend/src/components/atoms/avatar.tsx`
- Create: `frontend/src/components/atoms/badge.tsx`
- Create: `frontend/src/components/atoms/breadcrumb.tsx`
- Create: `frontend/src/components/atoms/card.tsx`
- Create: `frontend/src/components/atoms/dropdown-menu.tsx`
- Create: `frontend/src/components/atoms/field.tsx`
- Create: `frontend/src/components/atoms/label.tsx`
- Create: `frontend/src/components/atoms/navigation-menu.tsx`
- Create: `frontend/src/components/atoms/separator.tsx`
- Create: `frontend/src/components/atoms/sheet.tsx`
- Create: `frontend/src/components/atoms/tabs.tsx`
- Possibly modify: `frontend/components.json`
- Possibly modify: `frontend/src/styles.css`

- [x] **Step 1: Pin shadcn CLI**

Run from repository root:

```bash
rtk npm --prefix frontend install --save-dev --save-exact shadcn@4
```

Expected:

- `frontend/package.json` contains exact `devDependencies.shadcn`.
- `frontend/package-lock.json` records the resolved version.
- Implementation requires dependency-install approval.

- [x] **Step 2: Skip CLI pin commit per user instruction**

Not run. The user explicitly instructed not to touch git during implementation.

- [x] **Step 3: Add shadcn atoms from registry content**

Attempted:

```bash
rtk npm --prefix frontend exec -- shadcn add alert avatar badge breadcrumb card dropdown-menu field label navigation-menu separator sheet tabs --yes
```

The v4 CLI prompted for a component library and did not write files in non-interactive execution. Used `rtk npm --prefix frontend exec -- shadcn view ...` to inspect official registry content, added `radix-ui`, and created the atoms under `frontend/src/components/atoms` with this repo's `@/lib/css` alias.

Expected:

- All listed files are created under `frontend/src/components/atoms`.
- `frontend/src/components/ui` is not created.
- `frontend/components.json` still maps `"ui": "@/components/atoms"`.
- `frontend/package.json` and `frontend/package-lock.json` may change again because generated components add runtime dependencies such as `radix-ui`; these dependency changes are intended and require approval during implementation.

- [x] **Step 4: Inspect atom placement side effects**

Run:

```bash
rtk ls frontend/src/components/atoms
rtk proxy test ! -d frontend/src/components/ui
```

Expected:

- Any `components.json` diff keeps the atoms alias.
- Any `styles.css` diff is reviewed before proceeding.
- atoms contains only shadcn component files.

- [x] **Step 5: Inspect generated composition APIs**

Run:

```bash
rtk grep -n "asChild|render|Trigger|Link|Content" frontend/src/components/atoms/dropdown-menu.tsx frontend/src/components/atoms/navigation-menu.tsx frontend/src/components/atoms/sheet.tsx frontend/src/components/atoms/breadcrumb.tsx
```

Expected:

- Implementation knows whether `DropdownMenuTrigger`, `SheetTrigger`, `NavigationMenuLink`, and `BreadcrumbLink` use `asChild`, `render`, or direct props.
- Later snippets are adapted to the generated API if needed, without changing accessible role/name/href behavior.

- [x] **Step 6: Format generated files**

Run:

```bash
rtk npm --prefix frontend run check
```

Expected:

- Generated files follow repo style: no semicolons, single quotes, sorted imports.
- TypeScript passes.

- [x] **Step 7: Verify generated atoms compile**

Run:

```bash
rtk npm --prefix frontend run check:ci
```

Expected: PASS

- [x] **Step 8: Skip generated atoms commit per user instruction**

Not run. The user explicitly instructed not to touch git during implementation.

---

### Task 2: Replace global design foundation with shadcn-first tokens

**Files:**
- Modify: `frontend/src/styles.css`

- [x] **Step 1: Remove legacy landing tokens from `@theme inline`**

In `frontend/src/styles.css`, remove these lines from the `@theme inline` block:

```css
  --color-landing-bg: var(--landing-bg);
  --color-landing-surface: var(--landing-surface);
  --color-landing-ink: var(--landing-ink);
  --color-landing-muted: var(--landing-muted);
  --color-landing-line: var(--landing-line);
  --color-landing-accent: var(--landing-accent);
```

Expected:

- No `--color-landing-*` dangling references remain after `--landing-*` variables are removed from `:root`.

- [x] **Step 2: Replace `:root` tokens with shadcn-first palette**

In `frontend/src/styles.css`, keep `@import 'tailwindcss'`, `@import 'tw-animate-css'`, `@custom-variant dark`, and the non-landing entries in `@theme inline`. Replace the current `:root` color variables with:

```css
:root {
  --radius: 0.625rem;
  --background: oklch(0.985 0 0);
  --foreground: oklch(0.145 0 0);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.145 0 0);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.145 0 0);
  --primary: oklch(0.205 0 0);
  --primary-foreground: oklch(0.985 0 0);
  --secondary: oklch(0.97 0 0);
  --secondary-foreground: oklch(0.205 0 0);
  --muted: oklch(0.97 0 0);
  --muted-foreground: oklch(0.556 0 0);
  --accent: oklch(0.97 0 0);
  --accent-foreground: oklch(0.205 0 0);
  --destructive: #b91c1c;
  --border: oklch(0.922 0 0);
  --input: oklch(0.922 0 0);
  --ring: oklch(0.708 0 0);
  --chart-1: oklch(0.646 0.222 41.116);
  --chart-2: oklch(0.6 0.118 184.704);
  --chart-3: oklch(0.398 0.07 227.392);
  --chart-4: oklch(0.828 0.189 84.429);
  --chart-5: oklch(0.769 0.188 70.08);
  --sidebar: oklch(0.985 0 0);
  --sidebar-foreground: oklch(0.145 0 0);
  --sidebar-primary: oklch(0.205 0 0);
  --sidebar-primary-foreground: oklch(0.985 0 0);
  --sidebar-accent: oklch(0.97 0 0);
  --sidebar-accent-foreground: oklch(0.205 0 0);
  --sidebar-border: oklch(0.922 0 0);
  --sidebar-ring: oklch(0.708 0 0);
}
```

Expected:

- `--destructive` uses `#b91c1c`, which remains accessible even when shadcn alert text applies `/90` opacity.
- No `--landing-*` variables remain in `:root`.
- Legacy `--header-height` and old `landing-section` scroll offset classes are removed. The rebuilt Header and auth shell share `--app-header-height`, and landing anchor offset uses `calc(var(--app-header-height) + 1rem)`.

- [x] **Step 3: Keep `.dark` as a complete shadcn dark theme**

Keep a `.dark` block with shadcn-compatible variables, including:

```css
.dark {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  --card: oklch(0.205 0 0);
  --card-foreground: oklch(0.985 0 0);
  --popover: oklch(0.205 0 0);
  --popover-foreground: oklch(0.985 0 0);
  --primary: oklch(0.922 0 0);
  --primary-foreground: oklch(0.205 0 0);
  --secondary: oklch(0.269 0 0);
  --secondary-foreground: oklch(0.985 0 0);
  --muted: oklch(0.269 0 0);
  --muted-foreground: oklch(0.708 0 0);
  --accent: oklch(0.269 0 0);
  --accent-foreground: oklch(0.985 0 0);
  --destructive: #f87171;
  --border: oklch(1 0 0 / 10%);
  --input: oklch(1 0 0 / 15%);
  --ring: oklch(0.556 0 0);
  --chart-1: oklch(0.488 0.243 264.376);
  --chart-2: oklch(0.696 0.17 162.48);
  --chart-3: oklch(0.769 0.188 70.08);
  --chart-4: oklch(0.627 0.265 303.9);
  --chart-5: oklch(0.645 0.246 16.439);
  --sidebar: oklch(0.205 0 0);
  --sidebar-foreground: oklch(0.985 0 0);
  --sidebar-primary: oklch(0.488 0.243 264.376);
  --sidebar-primary-foreground: oklch(0.985 0 0);
  --sidebar-accent: oklch(0.269 0 0);
  --sidebar-accent-foreground: oklch(0.985 0 0);
  --sidebar-border: oklch(1 0 0 / 10%);
  --sidebar-ring: oklch(0.556 0 0);
}
```

Expected:

- Dark mode remains unsupported at the product level because no toggle exists, but the token set is coherent if `.dark` is added later.

- [x] **Step 4: Remove obsolete component classes**

Delete the entire `@layer components` block that defines:

- `.landing-page`
- `.landing-shell`
- `.landing-section`
- `.landing-*`
- `.site-*`

Also delete the standalone `@media (width >= 64rem)` block that only overrides `--header-height`.

Expected:

- Components can no longer accidentally depend on old landing/site design classes.
- The app may look visually broken until Tasks 4-7 replace all remaining component usages. Do not perform final visual acceptance between Task 2 and Task 7; use automated compile/test checks for intermediate commits.

- [x] **Step 5: Replace base body styling with shadcn tokens**

Use:

```css
@layer base {
  * {
    @apply border-border outline-ring/50;
  }

  html {
    @apply bg-background;
  }

  body {
    @apply bg-background text-foreground;
    font-family:
      'Helvetica Neue', Arial, 'Noto Sans JP', 'Noto Sans JP Fallback',
      'Hiragino Kaku Gothic ProN', Meiryo, sans-serif;
    line-height: 1.6;
    word-break: normal;
    overflow-wrap: break-word;
  }

  @media (prefers-reduced-motion: no-preference) {
    html {
      scroll-behavior: smooth;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
      animation-duration: 0.01ms !important;
      animation-iteration-count: 1 !important;
      scroll-behavior: auto !important;
      transition-duration: 0.01ms !important;
    }
  }
}
```

- [x] **Step 6: Verify old class names are gone from CSS**

Run:

```bash
rtk grep -n "landing-|site-" frontend/src/styles.css
```

Expected:

- Command exits with code 1 and prints no matches.

- [x] **Step 7: Run checks**

Run:

```bash
rtk npm --prefix frontend run check:ci
```

Expected: PASS

- [x] **Step 8: Skip commit per user instruction**

Not run. The user explicitly instructed not to touch git during implementation.

---

### Task 3: Rebuild auth molecules with shadcn Field and Alert

**Files:**
- Modify: `frontend/src/components/molecules/AuthTextField.tsx`
- Modify: `frontend/src/components/molecules/AuthFormFeedback.tsx`
- Modify: `frontend/src/components/molecules/OidcProviderButton.tsx`

- [x] **Step 1: Replace `AuthTextField` with Field composition**

Replace `frontend/src/components/molecules/AuthTextField.tsx` with:

```tsx
import { Field, FieldLabel } from '@/components/atoms/field'
import { Input } from '@/components/atoms/input'

type AuthTextFieldProps = {
  autoComplete: string
  describedBy?: string
  disabled?: boolean
  id: string
  invalid?: boolean
  label: string
  onChange: (value: string) => void
  required?: boolean
  type: 'email' | 'password' | 'text'
  value: string
}

export function AuthTextField({
  autoComplete,
  describedBy,
  disabled = false,
  id,
  invalid = false,
  label,
  onChange,
  required = false,
  type,
  value,
}: AuthTextFieldProps) {
  return (
    <Field data-invalid={invalid ? true : undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        aria-describedby={describedBy}
        aria-invalid={invalid ? true : undefined}
        autoComplete={autoComplete}
        disabled={disabled}
        id={id}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        type={type}
        value={value}
      />
    </Field>
  )
}
```

Expected:

- `getByLabelText` tests still pass.
- `aria-describedby`, `aria-invalid`, `autoComplete`, `required`, and `disabled` behavior is unchanged.

- [x] **Step 2: Replace `AuthFormFeedback` with Alert**

Replace `frontend/src/components/molecules/AuthFormFeedback.tsx` with:

```tsx
import { Alert, AlertDescription } from '@/components/atoms/alert'

export type AuthFormFeedbackProps = {
  id: string
  message: string | null
}

export function AuthFormFeedback({ id, message }: AuthFormFeedbackProps) {
  if (!message) {
    return null
  }

  return (
    <Alert id={id} role="alert" variant="destructive">
      <AlertDescription className="!text-destructive">
        {message}
      </AlertDescription>
    </Alert>
  )
}
```

Expected:

- `screen.getByRole('alert')` still finds the message.
- `alert.id` is still the caller-provided id.
- `textContent` remains exactly the Japanese message string.
- `AlertDescription` uses `!text-destructive` because shadcn's destructive alert variant applies `*:data-[slot=alert-description]:text-destructive/90` from the parent, which otherwise wins over a plain child `text-destructive` class.

- [x] **Step 3: Replace `OidcProviderButton` with Button**

Replace `frontend/src/components/molecules/OidcProviderButton.tsx` with:

```tsx
import { Button } from '@/components/atoms/button'
import type { OidcProvider } from '@/lib/authApi'

type OidcProviderButtonProps = {
  isDisabled?: boolean
  onClick: () => void
  provider: OidcProvider
}

export function OidcProviderButton({
  isDisabled = false,
  onClick,
  provider,
}: OidcProviderButtonProps) {
  return (
    <Button
      className="h-11 w-full justify-center"
      disabled={isDisabled}
      onClick={onClick}
      type="button"
      variant="outline"
    >
      {provider.displayName}で続行
    </Button>
  )
}
```

- [x] **Step 4: Run consuming tests**

Run:

```bash
rtk npm --prefix frontend test -- src/components/molecules/AuthFormFeedback.test.tsx src/components/molecules/OidcProviderButton.test.tsx src/components/organisms/Auth/LoginForm.test.tsx src/components/organisms/Auth/RegisterForm.test.tsx src/components/organisms/Auth/AccountDeletionPanel.test.tsx
```

Expected: PASS

- [x] **Step 5: Skip commit per user instruction**

Not run. The user explicitly instructed not to touch git during implementation.

---

### Task 4: Rebuild Header with NavigationMenu, Sheet, DropdownMenu, and Button

**Files:**
- Modify: `frontend/src/components/organisms/Header/AuthMenu.tsx`
- Modify: `frontend/src/components/organisms/Header/HeaderNav.tsx`
- Modify: `frontend/src/components/organisms/Header/index.tsx`
- Modify: `frontend/src/components/organisms/Header/*.test.tsx`

- [x] **Step 1: Rebuild unauthenticated/authenticated menu without changing behavior**

Implementation requirements for `frontend/src/components/organisms/Header/AuthMenu.tsx`:

```tsx
import { Link, useNavigate } from '@tanstack/react-router'
import { Loader2, LogOut, UserRound } from 'lucide-react'
import { useState } from 'react'

import { Alert, AlertDescription } from '@/components/atoms/alert'
import { Avatar, AvatarFallback } from '@/components/atoms/avatar'
import { Button } from '@/components/atoms/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/atoms/dropdown-menu'
import { useAuthSession } from '@/hooks/useAuthSession'

export default function AuthMenu() {
  const navigate = useNavigate()
  const { user, logout } = useAuthSession()
  const [logoutError, setLogoutError] = useState<string | null>(null)

  const handleLogout = async () => {
    setLogoutError(null)

    try {
      await logout.mutateAsync()
      await navigate({ to: '/login', search: { redirect: '/app' } })
    } catch {
      setLogoutError(
        'ログアウトに失敗しました。時間をおいて再度お試しください。',
      )
    }
  }

  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <Button asChild variant="ghost">
          <Link search={{ redirect: '/app' }} to="/login">
            ログイン
          </Link>
        </Button>
        <Button asChild>
          <Link search={{ redirect: '/app' }} to="/register">
            新規登録
          </Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-3">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            aria-label={
              logout.isPending
                ? `${user.email} ログアウト処理中`
                : `${user.email} アカウントメニュー`
            }
            className="gap-2"
            disabled={logout.isPending}
            variant="outline"
          >
            <Avatar className="size-6">
              <AvatarFallback>
                {logout.isPending ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <UserRound className="size-4" aria-hidden="true" />
                )}
              </AvatarFallback>
            </Avatar>
            <span className="hidden max-w-48 truncate sm:inline">
              {user.email}
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>アカウント</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={logout.isPending}
            onSelect={() => {
              void handleLogout()
            }}
          >
            <LogOut className="size-4" aria-hidden="true" />
            ログアウト
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {logoutError ? (
        <Alert className="max-w-sm" role="alert" variant="destructive">
          <AlertDescription>{logoutError}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  )
}
```

Expected:

- Login/register hrefs remain `/login?redirect=%2Fapp` and `/register?redirect=%2Fapp`.
- Logout still calls `logout.mutateAsync()`, then navigates to `/login` with `redirect=/app`.
- Logout error remains an alert.
- Logout pending state is visible after the dropdown closes because the trigger `Button` becomes disabled and changes its accessible name to include `ログアウト処理中`.
- The menu item uses Radix `onSelect`, not `onClick.preventDefault()`.

- [x] **Step 2: Rebuild HeaderNav with NavigationMenu**

Implementation requirements for `frontend/src/components/organisms/Header/HeaderNav.tsx`:

```tsx
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
} from '@/components/atoms/navigation-menu'
import { Button } from '@/components/atoms/button'
import type { NavigationItem } from './types'

type HeaderNavProps = {
  items: ReadonlyArray<NavigationItem>
  mobile?: boolean
  onNavigate?: () => void
}

export default function HeaderNav({
  items,
  mobile = false,
  onNavigate,
}: HeaderNavProps) {
  if (mobile) {
    return (
      <nav aria-label="モバイルページ内ナビゲーション" className="grid gap-2">
        {items.map((item) => (
          <Button asChild className="justify-start" key={item.href} variant="ghost">
            <a href={item.href} onClick={onNavigate}>
              {item.label}
            </a>
          </Button>
        ))}
      </nav>
    )
  }

  return (
    <NavigationMenu aria-label="ページ内ナビゲーション" className="hidden lg:flex" viewport={false}>
      <NavigationMenuList>
        {items.map((item) => (
          <NavigationMenuItem key={item.href}>
            <NavigationMenuLink href={item.href}>
              {item.label}
            </NavigationMenuLink>
          </NavigationMenuItem>
        ))}
      </NavigationMenuList>
    </NavigationMenu>
  )
}
```

Expected:

- Desktop nav remains findable by role/name `ページ内ナビゲーション`.
- Mobile nav links call `onNavigate`.
- The accessible name is on `NavigationMenu` itself, not on `NavigationMenuList`.
- `viewport={false}` is set because this header uses simple anchor links and no `NavigationMenuContent`.
- Mobile nav uses normal links wrapped in `Button asChild`; do not use `NavigationMenuLink` outside a `NavigationMenu` root.

- [x] **Step 3: Rebuild Header mobile menu with Sheet**

Implementation requirements for `frontend/src/components/organisms/Header/index.tsx`:

```tsx
import { Link } from '@tanstack/react-router'
import { Menu } from 'lucide-react'

import AuthMenu from './AuthMenu'
import HeaderNav from './HeaderNav'
import type { NavigationItem } from './types'
import { Button } from '@/components/atoms/button'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/atoms/sheet'

export type { NavigationItem } from './types'

type HeaderProps = {
  navigationItems?: ReadonlyArray<NavigationItem>
}

export default function Header({ navigationItems = [] }: HeaderProps) {
  const hasNavigation = navigationItems.length > 0

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75">
      <div className="mx-auto flex h-[var(--app-header-height)] w-full max-w-6xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link
          aria-label="ページ先頭へ移動"
          className="flex min-h-11 items-center gap-2 font-semibold tracking-tight"
          to="/"
        >
          <img
            alt=""
            aria-hidden="true"
            className="size-7"
            src="/site-mark.svg"
          />
          <span>python-react-template</span>
        </Link>

        {hasNavigation ? <HeaderNav items={navigationItems} /> : null}

        <div className="flex items-center gap-2">
          <AuthMenu />
          {hasNavigation ? (
            <Sheet>
              <SheetTrigger asChild>
                <Button
                  aria-label="メニューを開く"
                  className="lg:hidden"
                  size="icon"
                  type="button"
                  variant="outline"
                >
                  <Menu className="size-5" aria-hidden="true" />
                </Button>
              </SheetTrigger>
              <SheetContent side="right">
                <SheetHeader>
                  <SheetTitle>セクション</SheetTitle>
                </SheetHeader>
                <div className="mt-6">
                  <HeaderNav items={navigationItems} mobile />
                </div>
              </SheetContent>
            </Sheet>
          ) : null}
        </div>
      </div>
    </header>
  )
}
```

Expected:

- Existing function of showing mobile menu only when `navigationItems` exist is preserved.
- Tests are updated to click `メニューを開く` and find mobile links in the sheet.
- Old `aria-controls` assertion is removed because Sheet manages dialog semantics.

- [x] **Step 4: Update Header tests for shadcn semantics**

Required test updates:

- Keep tests for login/register hrefs.
- Keep tests for authenticated email and logout behavior.
- Update logout tests to open the account dropdown with `fireEvent.pointerDown(accountTrigger, { button: 0, ctrlKey: false })`, then click the menu item named `ログアウト`. Do not open the trigger with a click event because Radix `DropdownMenuTrigger` opens on pointer down.
- Keep the repo's existing `fireEvent` test style; do not add `@testing-library/user-event` for this migration.
- Assert the authenticated email from the account trigger before opening the dropdown, or with `within(accountTrigger).getByText(user.email)`. Keep `DropdownMenuLabel` as `アカウント` so the menu content does not duplicate `user.email`.
- Update pending-state tests to click the logout menu item, then assert the account trigger becomes disabled and is findable by role/name `/ログアウト処理中/`. Do not keep direct `getByRole('button', { name: 'ログアウト' })` expectations after logout moves into the menu.
- Keep tests for logout failure alert.
- Replace mobile panel `hidden` assertion with: open sheet, click mobile link, assert the sheet closes or mobile navigation is no longer visible.
- In `Header.structure.test.tsx`, replace the old index-based mobile link selection `getAllByRole('link', { name: '品質' })[1]` with: click `メニューを開く`, query the sheet/dialog content, then click its `品質` link.
- Remove assertions tied to old `aria-controls`.
- Keep `Header は route-specific data を import しない`.

- [x] **Step 5: Run Header tests**

Run:

```bash
rtk npm --prefix frontend test -- src/components/organisms/Header/AuthMenu.test.tsx src/components/organisms/Header/HeaderNav.test.tsx src/components/organisms/Header/Header.structure.test.tsx src/components/organisms/Header/index.test.tsx
```

Expected: PASS

- [x] **Step 6: Skip commit per user instruction**

Not run. The user explicitly instructed not to touch git during implementation.

---

### Task 5: Rebuild landing page with shadcn sections

**Files:**
- Modify: `frontend/src/components/organisms/LandingPage/index.tsx`
- Modify: `frontend/src/components/organisms/LandingPage/InfoCard.tsx`
- Modify: `frontend/src/components/organisms/LandingPage/SectionIntro.tsx`
- Modify: `frontend/src/components/organisms/LandingPage/ArchitectureDiagram.tsx`
- Delete: `frontend/src/components/organisms/LandingPage/AnchorButton.tsx`
- Modify: `frontend/src/components/organisms/LandingPage/index.test.tsx`

- [x] **Step 1: Replace `AnchorButton` usage with shadcn Button**

In `LandingPage/index.tsx`, remove `AnchorButton` import. Use:

```tsx
import { ArrowRight, CheckCircle2 } from 'lucide-react'

import ArchitectureDiagram from './ArchitectureDiagram'
import InfoCard from './InfoCard'
import SectionIntro from './SectionIntro'
import { Badge } from '@/components/atoms/badge'
import { Button } from '@/components/atoms/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/atoms/card'
import { Separator } from '@/components/atoms/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/atoms/tabs'
```

Replace CTA rendering with:

```tsx
<Button asChild>
  <a href={action.href}>
    {action.label}
    <ArrowRight className="size-4" aria-hidden="true" />
  </a>
</Button>
```

For secondary actions use `variant="outline"`.

- [x] **Step 2: Rebuild page layout with shadcn primitives**

Implementation requirements:

- `<main id="top">` remains.
- Every section keeps its current `id` and `aria-labelledby`.
- Use `mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8` for page width.
- Use `Badge` for section labels and hero eyebrow.
- Use `Card` for hero signal panel, overview cards, workflow steps, quality groups, and final CTA panel.
- Use `Tabs` to present `overview` / `architecture` / `workflow` / `quality` as an additional shadcn-driven summary near the hero.
- Keep the existing Japanese copy from `data.ts`.
- Keep the four real `<section id="overview">`, `<section id="architecture">`, `<section id="workflow">`, and `<section id="quality">` outside `Tabs`.
- Do not put existing section content inside `TabsContent`; Radix Tabs can unmount inactive content and would break section/id tests.
- Do not duplicate existing heading ids such as `overview-heading` inside `Tabs`.
- Do not create links in Tabs with the same accessible names as existing hero/final CTA links.

Expected:

- Landing tests still find all sections by id and heading id.
- CTA links still have the same labels and hrefs.
- `screen.getByRole('link', { name: action.label })` remains unambiguous for every hero/final CTA.
- No `landing-*` class remains in LandingPage components.

- [x] **Step 3: Rebuild `InfoCard` with Card**

Replace `InfoCard.tsx` with a component that uses `Card`, `CardHeader`, `CardTitle`, `CardContent`, `Separator`, and `Badge` for `items`.

Expected:

- `title`, `description`, and `items` props remain the same.
- `items` still render visible command text.

- [x] **Step 4: Rebuild `SectionIntro` with Badge and semantic heading**

Replace `SectionIntro.tsx` so it uses `Badge variant="outline"` for `label`, keeps `<h2 id={headingId}>`, and uses token classes (`text-foreground`, `text-muted-foreground`) rather than `landing-*`.

- [x] **Step 5: Update `ArchitectureDiagram` tokens**

Replace `var(--landing-*)` references with shadcn token references:

- `var(--card)`
- `var(--border)`
- `var(--foreground)`
- `var(--muted-foreground)`
- `var(--primary)`

Also rename SVG ids that contain the legacy prefix:

- `id="landing-card-glow"` -> `id="card-glow"`
- `url(#landing-card-glow)` -> `url(#card-glow)`

Expected:

- Diagram keeps `role="img"` and `aria-label`.
- No `landing-*` string remains in the file.

- [x] **Step 6: Delete unused `AnchorButton.tsx`**

Run:

```bash
rtk git rm frontend/src/components/organisms/LandingPage/AnchorButton.tsx
```

- [x] **Step 7: Run landing tests**

Run:

```bash
rtk npm --prefix frontend test -- src/components/organisms/LandingPage/index.test.tsx
```

Expected: PASS

- [x] **Step 8: Skip commit per user instruction**

Not run. The user explicitly instructed not to touch git during implementation.

---

### Task 6: Rebuild auth pages with Card, Field, Separator, and Alert

**Files:**
- Modify: `frontend/src/components/organisms/Auth/AuthFormShell.tsx`
- Modify: `frontend/src/components/organisms/Auth/LoginForm.tsx`
- Modify: `frontend/src/components/organisms/Auth/RegisterForm.tsx`
- Modify: `frontend/src/routes/login.tsx`
- Modify: `frontend/src/routes/register.tsx`

- [x] **Step 1: Replace `AuthFormShell` with a centered Card shell**

Implementation requirements:

```tsx
import type { ReactNode } from 'react'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from '@/components/atoms/card'

type AuthFormShellProps = {
  children: ReactNode
  description?: string
  title: string
}

export function AuthFormShell({
  children,
  description,
  title,
}: AuthFormShellProps) {
  return (
    <main className="mx-auto flex min-h-[calc(100dvh_-_var(--app-header-height))] w-full max-w-md items-center px-4 py-12">
      <Card className="w-full">
        <CardHeader>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description ? (
            <CardDescription>{description}</CardDescription>
          ) : null}
        </CardHeader>
        <CardContent className="grid gap-6">{children}</CardContent>
      </Card>
    </main>
  )
}
```

Expected:

- Real `<h1>` remains.
- Existing route tests that look for heading `ログイン` still pass.

- [x] **Step 2: Use shadcn Button defaults in LoginForm/RegisterForm**

Remove landing color overrides from submit buttons. Keep field labels and submit button labels unchanged.

- [x] **Step 3: Add Separator between password and OIDC login**

In `login.tsx` and `register.tsx`, use `Separator` and text `または` only when providers exist.

- [x] **Step 4: Keep inline auth copy functional, but restyle with shadcn tokens**

The login/register cross-links can use `Button asChild variant="link"` now because old design compatibility is not required, but must remain links with the same href/search.

Expected:

- Login route still exposes a link named `アカウントを作成` with the same redirect search.
- Register route still exposes a link named `ログイン` with the same redirect search.

- [x] **Step 5: Run auth tests**

Run:

```bash
rtk npm --prefix frontend test -- src/components/organisms/Auth/LoginForm.test.tsx src/components/organisms/Auth/RegisterForm.test.tsx src/routes/login.test.tsx src/routes/register.test.tsx src/routes/app.test.tsx
```

Expected: PASS

- [x] **Step 6: Skip commit per user instruction**

Not run. The user explicitly instructed not to touch git during implementation.

---

### Task 7: Rebuild app, settings, admin, and error screens

**Files:**
- Modify: `frontend/src/components/organisms/Auth/AccountDeletionPanel.tsx`
- Modify: `frontend/src/components/organisms/ErrorState/index.tsx`
- Modify: `frontend/src/routes/_authenticated.app.tsx`
- Modify: `frontend/src/routes/_authenticated.app_.settings.tsx`
- Modify: `frontend/src/routes/_authenticated.admin.tsx`
- Modify if assertions need updating: `frontend/src/components/organisms/ErrorState/index.test.tsx`
- Modify: related tests under `frontend/src/routes/*.test.tsx`

- [x] **Step 1: Rebuild `AccountDeletionPanel` with Card and Field**

Use `Card`, `CardHeader`, `CardDescription`, `CardContent`, `AuthTextField`, `AuthFormFeedback`, `OidcProviderButton`, and destructive `Button`.

Requirements:

- Keep `<h2>アカウント削除</h2>`.
- Keep `noValidate`.
- Keep field labels and submit payload behavior.
- Keep OIDC reauth buttons.

- [x] **Step 2: Rebuild settings route with Breadcrumb**

In `frontend/src/routes/_authenticated.app_.settings.tsx`, replace the old back link block with shadcn `Breadcrumb`:

```tsx
<Breadcrumb>
  <BreadcrumbList>
    <BreadcrumbItem>
      <BreadcrumbLink asChild>
        <Link to="/app">アプリ</Link>
      </BreadcrumbLink>
    </BreadcrumbItem>
    <BreadcrumbSeparator />
    <BreadcrumbItem>
      <BreadcrumbPage>アカウント設定</BreadcrumbPage>
    </BreadcrumbItem>
  </BreadcrumbList>
</Breadcrumb>
```

Expected:

- Tests are updated from `アプリに戻る` to link name `アプリ`.
- Link href remains `/app`.

- [x] **Step 3: Rebuild `/app` page with Card grid**

Use `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `Button asChild`, and `Badge`.

Requirements:

- Heading `アプリ` remains.
- Link `アカウント設定` remains and points to `/app/settings`.
- Admin link `管理` remains only when `hasPermission(user, 'admin:access')`.

- [x] **Step 4: Rebuild `/admin` placeholder with Card**

Keep heading `管理`. Use a simple shadcn `Card` to show placeholder content.

- [x] **Step 5: Rebuild ErrorState with Card and Button**

Use:

- `Badge variant="outline"` for `statusCode`
- real `<h1>` for title
- `Button asChild` for `primaryAction`

Functional requirements:

- `title`, `message`, and `statusCode` remain visible.
- Primary action still navigates to `primaryAction.to`.

- [x] **Step 6: Run route and component tests**

Run:

```bash
rtk npm --prefix frontend test -- src/components/organisms/Auth/AccountDeletionPanel.test.tsx src/components/organisms/ErrorState/index.test.tsx src/routes/app.settings.test.tsx src/routes/app.test.tsx
```

Expected: PASS

- [x] **Step 7: Skip commit per user instruction**

Not run. The user explicitly instructed not to touch git during implementation.

---

### Task 8: Update frontend documentation and guardrails

**Files:**
- Modify: `frontend/AGENTS.md`
- Modify: `frontend/CLAUDE.md`

- [x] **Step 1: Remove `components/ui` from `frontend/AGENTS.md` tree**

The tree must list only:

```text
│   │   ├── atoms/           # shadcn/ui 生成コンポーネントのみ
│   │   ├── molecules/       # atoms の組み合わせ
│   │   └── organisms/       # Header / LandingPage / Auth などページ単位に近い複合 UI
```

- [x] **Step 2: Document pinned local CLI**

Add to `frontend/AGENTS.md`:

```markdown
- shadcn/ui コンポーネント追加は `frontend` の pinned local CLI (`npm exec -- shadcn add <name> --yes`) を使い、`npx shadcn@latest` は使わない。生成後は `npm run check` で repo style に整形する
```

- [x] **Step 3: Fix `frontend/CLAUDE.md` wording**

Replace `(atoms/molecules/ui)` with `(atoms/molecules/organisms)`.

Replace `npx shadcn@latest add <name>` with:

```markdown
frontend の pinned local CLI (`npm exec -- shadcn add <name> --yes`)
```

- [x] **Step 4: Verify docs**

Run:

```bash
rtk grep -n "components/ui|atoms/molecules/ui|shadcn@latest" frontend/AGENTS.md frontend/CLAUDE.md
```

Expected:

- The command exits with code 1 and prints no matches.

Run:

```bash
rtk grep -n "components/atoms|atoms/molecules/organisms|npm exec -- shadcn" frontend/AGENTS.md frontend/CLAUDE.md frontend/components.json
```

Expected:

- atoms and local CLI guidance are present.

- [x] **Step 5: Skip commit per user instruction**

Not run. The user explicitly instructed not to touch git during implementation.

---

### Task 9: Remove legacy design dependencies and verify visually

**Files:**
- Verify only, with fixes if grep finds remaining legacy classes

- [x] **Step 1: Verify old design classes are gone from source**

Run:

```bash
rtk grep -n "landing-|site-nav-|site-header|site-brand|site-menu|site-mobile|text-red-600|bg-landing|text-landing|border-landing" frontend/src
```

Expected:

- Command exits with code 1 and prints no matches. The pattern intentionally excludes `/site-mark.svg`, which is an asset path rather than a legacy design class.
- If matches remain in comments or tests only, either remove them or document why the assertion is intentionally checking absence.

- [x] **Step 2: Verify atoms placement**

Run:

```bash
rtk ls frontend/src/components/atoms
rtk proxy test ! -d frontend/src/components/ui
rtk grep -n "from ['\"]@/components/ui|from ['\"]\\.\\./ui|from ['\"]\\.\\./\\.\\./ui" frontend/src
```

Expected:

- atoms contains only shadcn component files.
- `frontend/src/components/ui` does not exist.
- The final grep exits with code 1 and prints no matches.

- [x] **Step 3: Run full frontend verification**

Run:

```bash
rtk npm --prefix frontend run check:ci
rtk npm --prefix frontend test
rtk npm --prefix frontend run build
```

Expected: PASS for all commands.

- [x] **Step 4: Start dev server for visual verification**

Run:

```bash
rtk proxy sh -lc 'rtk npm --prefix frontend run dev -- --host 127.0.0.1 --port 3000 > /tmp/python-react-template-vite.log 2>&1 & echo $! > /tmp/python-react-template-vite.pid'
```

Expected:

- Vite starts on port 3000 unless already occupied.
- If port 3000 is occupied, use the next available port and record it in the final implementation notes.
- The command returns immediately and records the background process PID in `/tmp/python-react-template-vite.pid`.
- Confirm startup with:

```bash
rtk proxy sh -lc 'tail -80 /tmp/python-react-template-vite.log'
```

- [x] **Step 5: Verify desktop and mobile screens**

Open the running app and inspect public routes first:

- `/`
- `/login`
- `/register`
- `/forbidden`

Check at:

- Desktop: 1440px wide
- Mobile: 390px wide

Expected:

- Header uses shadcn navigation and sheet menu.
- Landing page no longer resembles the old landing/site design.
- Auth fields and account deletion fields are unchanged by label and behavior.
- Buttons, cards, alerts, badges, separators, tabs, dropdown, breadcrumb, and sheet render correctly.
- Text does not overlap or overflow controls.
- Mobile menu opens and closes.

- [x] **Step 6: Verify protected screens when a local backend is available**

If the local backend and database are available, start the backend in a separate process using the project-local backend instructions, create or use a test user, log in through `/login`, and inspect:

- `/app`
- `/app/settings`

Expected:

- `/app` renders the shadcn card layout and still links to `/app/settings`.
- `/app/settings` renders the breadcrumb and account deletion card.
- Account deletion fields keep the exact labels from the functional contract.

If backend setup is not available in the implementation environment, do not fake success. Record that protected-route visual verification was skipped, and rely on these required automated checks for protected behavior:

```bash
rtk npm --prefix frontend test -- src/routes/app.test.tsx src/routes/app.settings.test.tsx
```

Implementation note: local backend was not available at `127.0.0.1:8000`, so protected-route browser verification was skipped. The required automated protected-route checks passed: `src/routes/app.test.tsx` and `src/routes/app.settings.test.tsx` (35 tests).

- [x] **Step 7: Stop dev server**

Stop the running Vite process before finalizing:

```bash
rtk proxy sh -lc 'kill "$(cat /tmp/python-react-template-vite.pid)"'
```

If the wrapper process exits but Vite remains running, clean it up with a scoped fallback:

```bash
rtk proxy sh -lc 'pkill -f "vite.*--host 127\\.0\\.0\\.1.*--port 3000" || true'
```

Expected:

- The Vite process for this verification run is stopped.
- Do not kill unrelated dev servers on other hosts or ports.

- [x] **Step 8: Skip final git inspection per user instruction**

Not run. The user explicitly instructed not to touch git during implementation. Final inspection used the verification commands above instead of `git status`.

---

## Explicit Non-Goals

- Do not preserve the old visual design.
- Do not preserve `landing-*` / `site-*` CSS classes.
- Do not keep old layout structure solely to satisfy existing snapshots or class-based expectations.
- Do not move shadcn generated files to `frontend/src/components/ui`.
- Do not add custom non-shadcn components to `frontend/src/components/atoms`.
- Do not change backend auth semantics, API paths, redirect normalization, CSRF handling, OIDC callback handling, or RBAC.

## Final Acceptance Criteria

- `frontend/src/components/atoms` contains only shadcn-generated component files.
- `frontend/src/components/ui` does not exist.
- No `landing-*` / `site-*` classes remain in `frontend/src`.
- Header uses shadcn `NavigationMenu`, `Sheet`, `DropdownMenu`, `Avatar`, and `Button`.
- Landing page uses shadcn `Badge`, `Button`, `Card`, `Separator`, and `Tabs`.
- Auth UI uses shadcn `Card`, `Field`, `Input`, `Alert`, `Separator`, and `Button`.
- App/settings/admin/error screens use shadcn layout primitives.
- Functional tests still verify the same fields, links, redirects, logout behavior, OIDC behavior, account deletion behavior, and route guards.
- `rtk npm --prefix frontend run check:ci`, `rtk npm --prefix frontend test`, and `rtk npm --prefix frontend run build` pass.
- Desktop/mobile visual verification confirms the new UI is shadcn-first and does not depend on the old template design.

## Post-Review Follow-Up

- [x] Restore sticky-header anchor offset on landing sections.
- [x] Restore the hero feature panel landmark by wrapping the shadcn `Card` in an `aside` with a Japanese accessible label.
- [x] Localize shadcn Sheet close button and Breadcrumb accessible labels.
- [x] Set `--background` to `oklch(0.985 0 0)` so page background and card surfaces are visually separated.
- [x] Correct shadcn component-addition documentation: pinned local CLI remains the first choice, but docs now cover the observed `shadcn view` / registry-content fallback when non-interactive add cannot complete.
- [x] Move logout failure alert out of the header flex row and keep destructive alert text contrast consistent.
- [x] Superseded: initially kept logout pending trigger focusable with `aria-disabled`; second follow-up removed `aria-disabled` and kept `aria-busy` only.
- [x] Remove no-op `pt-0`, redundant consumer-side `role="alert"`, prefix important notation, and `field.tsx` React namespace dependency.
- [x] Add regression checks for hero landmark, Sheet close label, Breadcrumb landmark, Japanese dashboard badge, and logout pending trigger state. Anchor offset behavior is covered by browser verification rather than class-string assertions.
- [x] Leave shadcn registry `'use client'` directives in generated atom files. They are harmless in Vite and preserving registry shape keeps future shadcn updates easier to compare.

## Second Post-Review Follow-Up

- [x] Remove `aria-disabled` from the logout pending account trigger. The trigger now exposes progress with `aria-busy` only, while duplicate submit protection remains on the disabled `DropdownMenuItem`.
- [x] Add a dismiss button to the floating logout failure alert so the overlay is not permanent.
- [x] Move Sheet close label localization back to the Header call site with `showCloseButton={false}` and a Japanese `SheetClose`, keeping the shadcn Sheet atom registry-shaped.
- [x] Move Breadcrumb landmark localization back to the `/app/settings` call site with `aria-label="パンくず"`, keeping the shadcn Breadcrumb atom registry-shaped.
- [x] Change the hero complementary landmark from `aria-label` to `aria-labelledby` so the landmark name matches the visible heading.
- [x] Remove the class-string regression assertion for `scroll-mt-20`; sticky-header anchor behavior is covered by browser verification instead.
- [x] Split the `/app` dashboard label assertion into its own route test instead of attaching it to the auth-cache fetch-count test.
- [x] Extract Header test account-menu opening into local helpers so Radix pointerdown details are not repeated across test bodies.
- [x] Replace duplicated landing tab descriptions with short tab-specific summaries.
- [x] Introduce `--app-header-height` and use it from both Header and AuthFormShell, removing the duplicated `4rem` header-height constant.
- [x] Tie landing anchor offset to `--app-header-height` with `scroll-mt-[calc(var(--app-header-height)+1rem)]`.
- [x] Use shadcn `Button` for Header Sheet close and logout-alert dismiss controls instead of hand-copied atom class strings.
- [x] Record atom-local patch policy in `frontend/AGENTS.md`: localization belongs at call sites when possible; the only current atom-local patch is `field.tsx` type import cleanup.
- [x] Verified mobile Sheet anchor navigation in the in-app browser at 390px width: after clicking `品質`, `location.hash` was `#quality`, the dialog was closed, `#quality` top was about 80px, and the sticky header bottom was about 65px.
