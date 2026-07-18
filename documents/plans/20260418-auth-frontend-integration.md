# Auth Frontend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** frontend から `/api/auth/*` を same-origin 前提で扱えるようにし、typed error、login/logout、current user 表示、protected route を React 側へ統合する。

**Architecture:** Vite dev server では `/api` を backend へ proxy し、本番では相対パスのまま backend 配信へ寄せる。API client は `ApiError` で status/body を保持し、unsafe method は CSRF cookie が無ければ自動 bootstrap する。protected route は TanStack Router `beforeLoad` で守る。

**Tech Stack:** React 19, Vite 7, TanStack Router, TanStack Query, TypeScript, Vitest, Testing Library

**Dependencies:** [20260418-auth-structure.md](./20260418-auth-structure.md), [20260418-auth-backend-flow.md](./20260418-auth-backend-flow.md), [20260418-auth-delivery-notes.md](./20260418-auth-delivery-notes.md)

**Done When:** `ApiError` による 401 / 422 / 500 の区別が入り、`/login` と `/app` の導線が動き、logout 後の redirect も成立する。あわせて `frontend/AGENTS.md` に auth route guard と `organisms/` 運用が反映される。

---

## File Structure

- Create: `frontend/src/lib/apiError.ts`
- Create: `frontend/src/lib/apiClient.ts`
- Create: `frontend/src/lib/cookies.ts`
- Create: `frontend/src/lib/queryKeys.ts`
- Create: `frontend/src/lib/authApi.ts`
- Create: `frontend/src/hooks/useAuthSession.ts`
- Create: `frontend/src/hooks/useAuthSession.test.tsx`
- Create: `frontend/src/components/organisms/Auth/LoginForm.tsx`
- Create: `frontend/src/components/organisms/Auth/LoginForm.test.tsx`
- Create: `frontend/src/lib/apiClient.test.ts`
- Create: `frontend/src/routes/login.tsx`
- Create: `frontend/src/routes/app.tsx`
- Create: `frontend/src/routes/app.test.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/organisms/Header/index.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/AGENTS.md`

## Task 1: typed `ApiError` と完全な Vite proxy 設定を入れる

**Files:**
- Create: `frontend/src/lib/apiError.ts`
- Create: `frontend/src/lib/apiClient.ts`
- Create: `frontend/src/lib/cookies.ts`
- Create: `frontend/src/lib/queryKeys.ts`
- Create: `frontend/src/lib/apiClient.test.ts`
- Modify: `frontend/vite.config.ts`

- [x] **Step 1: API client の失敗テストを書く**

```ts
import { afterEach, expect, test, vi } from 'vitest'

import { ApiError } from './apiError'
import { apiClient } from './apiClient'

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

test('unsafe request では csrf header を付与する', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'

  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }),
  )

  vi.stubGlobal('fetch', fetchMock)

  await apiClient.post('/api/auth/login', {
    email: 'user@example.com',
    password: 'Password123!',
  })

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/auth/login',
    expect.objectContaining({
      credentials: 'include',
      headers: expect.objectContaining({
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf-123',
      }),
    }),
  )
})


test('non-2xx response では ApiError を投げる', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )

  await expect(apiClient.get('/api/auth/me')).rejects.toEqual(
    expect.objectContaining<ApiError>({
      status: 401,
      body: { message: 'Unauthorized' },
    }),
  )
})
```

Run: `cd frontend && npm test -- src/lib/apiClient.test.ts`
Expected: FAIL with module not found

- [x] **Step 2: `ApiError` / cookie helper / API client を実装する**

`frontend/src/lib/apiError.ts`:

```ts
export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown) {
    super(`API request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}
```

`frontend/src/lib/cookies.ts`:

```ts
export function readCookie(name: string): string | null {
  const prefix = `${name}=`

  for (const item of document.cookie.split(';')) {
    const trimmed = item.trim()
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length))
    }
  }

  return null
}
```

`frontend/src/lib/apiClient.ts`:

```ts
import { ApiError } from './apiError'
import { readCookie } from './cookies'

let csrfBootstrapPromise: Promise<void> | null = null

async function ensureCsrfToken(): Promise<void> {
  if (!csrfBootstrapPromise) {
    csrfBootstrapPromise = fetch('/api/auth/csrf', {
      credentials: 'include',
    }).then(() => undefined)
      .finally(() => {
        csrfBootstrapPromise = null
      })
  }

  await csrfBootstrapPromise
}

async function request<T>(input: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const method = (init.method ?? 'GET').toUpperCase()
  const isUnsafeMethod = !['GET', 'HEAD'].includes(method)

  if (isUnsafeMethod) {
    await ensureCsrfToken()
    const csrfToken = readCookie('csrf_token')
    if (!csrfToken) {
      throw new Error('Missing csrf_token cookie after bootstrap')
    }
    headers.set('X-CSRF-Token', csrfToken)
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(input, {
    ...init,
    headers,
    credentials: 'include',
  })

  if (!response.ok) {
    const body = await response.clone().json().catch(() => null)
    throw new ApiError(response.status, body)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export const apiClient = {
  get: <T>(input: string) => request<T>(input),
  post: <T>(input: string, body?: unknown) =>
    request<T>(input, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),
}
```

`/api/auth/csrf` が non-2xx の場合は typed `ApiError` を送出し、後続の unsafe request は送らない。

`frontend/src/lib/queryKeys.ts`:

```ts
export const queryKeys = {
  auth: {
    root: ['auth'] as const,
    me: ['auth', 'me'] as const,
  },
}
```

- [x] **Step 3: Vite config は既存設定を保ったまま関数形式へ移行する**

`frontend/vite.config.ts`:

```ts
import { URL, fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import { devtools } from '@tanstack/devtools-vite'
import viteReact from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendOrigin = env.VITE_BACKEND_ORIGIN || 'http://localhost:8000'

  return {
    plugins: [
      devtools(),
      tanstackRouter({
        target: 'react',
        autoCodeSplitting: true,
        routeFileIgnorePattern: '\\.data\\.(ts|tsx)$',
      }),
      viteReact(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      proxy: {
        '/api': {
          target: backendOrigin,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: '../backend/static',
      emptyOutDir: true,
    },
  }
})
```

- [x] **Step 4: API client test を通す**

Run: `cd frontend && npm test -- src/lib/apiClient.test.ts`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add frontend/src/lib/apiError.ts frontend/src/lib/apiClient.ts frontend/src/lib/cookies.ts frontend/src/lib/queryKeys.ts frontend/src/lib/apiClient.test.ts frontend/vite.config.ts
git commit -m "feat(frontend/auth): add typed api client and dev proxy"
```

## Task 2: auth API と `useAuthSession` を定義し、401 と障害を分離する

**Files:**
- Create: `frontend/src/lib/authApi.ts`
- Create: `frontend/src/hooks/useAuthSession.ts`
- Create: `frontend/src/hooks/useAuthSession.test.tsx`
- Modify: `frontend/src/main.tsx`

- [x] **Step 1: `useAuthSession` の test を先に書く**

```ts
import type { ReactNode } from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, test, vi } from 'vitest'

import { useAuthSession } from './useAuthSession'

test('401 は未ログインとして null を返す', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  const queryClient = new QueryClient()

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const { result } = renderHook(() => useAuthSession(), { wrapper })

  await waitFor(() => expect(result.current.user).toBeNull())
})


test('500 は未ログインに潰さず error として残す', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ message: 'Server error' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  const queryClient = new QueryClient()

  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const { result } = renderHook(() => useAuthSession(), { wrapper })

  await waitFor(() => expect(result.current.error).toBeTruthy())
})
```

Run: `cd frontend && npm test -- src/hooks/useAuthSession.test.tsx`
Expected: FAIL

- [x] **Step 2: auth API と hook を実装する**

`frontend/src/lib/authApi.ts`:

```ts
import { queryOptions } from '@tanstack/react-query'

import { ApiError } from './apiError'
import { apiClient } from './apiClient'
import { queryKeys } from './queryKeys'

export type AuthUser = {
  id: string
  email: string
}

export type LoginPayload = {
  email: string
  password: string
}

export async function fetchCurrentUserStrict(): Promise<AuthUser> {
  return apiClient.get<AuthUser>('/api/auth/me')
}

export async function fetchCurrentUserOrNull(): Promise<AuthUser | null> {
  try {
    return await fetchCurrentUserStrict()
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null
    }
    throw error
  }
}

export async function loginWithPassword(payload: LoginPayload): Promise<AuthUser> {
  return apiClient.post<AuthUser>('/api/auth/login', payload)
}

export async function logoutCurrentSession(): Promise<void> {
  return apiClient.post<void>('/api/auth/logout')
}

export function currentUserQueryOptions() {
  return queryOptions({
    queryKey: queryKeys.auth.me,
    queryFn: fetchCurrentUserOrNull,
    retry: false,
  })
}

export function currentUserStrictQueryOptions() {
  return queryOptions({
    queryKey: [...queryKeys.auth.me, 'strict'],
    queryFn: fetchCurrentUserStrict,
    retry: false,
  })
}
```

`frontend/src/hooks/useAuthSession.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  currentUserQueryOptions,
  logoutCurrentSession,
} from '@/lib/authApi'
import { queryKeys } from '@/lib/queryKeys'

export function useAuthSession() {
  const queryClient = useQueryClient()

  const meQuery = useQuery(currentUserQueryOptions())

  const logout = useMutation({
    mutationFn: logoutCurrentSession,
    onSuccess: async () => {
      queryClient.setQueryData(queryKeys.auth.me, null)
      queryClient.removeQueries({
        queryKey: queryKeys.auth.strictMe,
        exact: true,
      })
    },
  })

  return {
    user: meQuery.data ?? null,
    isLoading: meQuery.isLoading,
    error: meQuery.error,
    logout,
  }
}
```

- [x] **Step 3: router context に `queryClient` を渡す**

`frontend/src/main.tsx`:

```tsx
const queryClient = new QueryClient()

const router = createRouter({
  routeTree,
  context: {
    queryClient,
  },
  defaultPreload: 'intent',
  scrollRestoration: true,
  defaultStructuralSharing: true,
  defaultPreloadStaleTime: 0,
})
```

補足:

- phase 1 の auth type は hand-written のまま維持する
- OpenAPI codegen はこの段階では入れない
- `['auth', 'me']` は `AuthUser | null`、`['auth', 'me', 'strict']` は `AuthUser` に固定する。queryKey ごとに semantic を分けて衝突を避ける

- [x] **Step 4: hook test を通す**

Run: `cd frontend && npm test -- src/hooks/useAuthSession.test.tsx`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add frontend/src/lib/authApi.ts frontend/src/hooks/useAuthSession.ts frontend/src/hooks/useAuthSession.test.tsx frontend/src/main.tsx
git commit -m "feat(frontend/auth): add auth api and session hook"
```

## Task 3: protected route `/app` と login redirect を実装する

**Files:**
- Create: `frontend/src/routes/login.tsx`
- Create: `frontend/src/routes/app.tsx`
- Create: `frontend/src/routes/app.test.tsx`
- Create: `frontend/src/components/organisms/Auth/LoginForm.tsx`
- Create: `frontend/src/components/organisms/Auth/LoginForm.test.tsx`

- [x] **Step 1: route guard と form の失敗テストを書く**

`frontend/src/routes/app.test.tsx`:

```ts
import { render, screen } from '@testing-library/react'
import {
  RouterProvider,
  createMemoryHistory,
  createRouter,
} from '@tanstack/react-router'
import { QueryClient } from '@tanstack/react-query'
import { expect, test, vi } from 'vitest'

import { routeTree } from '@/routeTree.gen'

test('未ログインで /app へ来たら /login へ送る', async () => {
  const queryClient = new QueryClient()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 }),
  ))

  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ['/app'] }),
    context: { queryClient },
  })

  render(<RouterProvider router={router} />)

  expect(await screen.findByRole('heading', { name: 'ログイン' })).toBeTruthy()
})
```

`frontend/src/components/organisms/Auth/LoginForm.test.tsx`:

```ts
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import LoginForm from './LoginForm'

test('LoginForm は email / password を submit する', async () => {
  const onSubmit = vi.fn().mockResolvedValue(undefined)

  render(<LoginForm errorMessage={null} isPending={false} onSubmit={onSubmit} />)

  fireEvent.change(screen.getByLabelText('メールアドレス'), {
    target: { value: 'user@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: 'ログイン' }))

  expect(onSubmit).toHaveBeenCalledWith({
    email: 'user@example.com',
    password: 'Password123!',
  })
})
```

Run: `cd frontend && npm test -- src/routes/app.test.tsx src/components/organisms/Auth/LoginForm.test.tsx`
Expected: FAIL

- [x] **Step 2: protected route と login route を実装する**

`frontend/src/routes/app.tsx`:

```tsx
import { createFileRoute, redirect } from '@tanstack/react-router'

import { ApiError } from '@/lib/apiError'
import { currentUserStrictQueryOptions } from '@/lib/authApi'

export const Route = createFileRoute('/app')({
  beforeLoad: async ({ context, location }) => {
    try {
      await context.queryClient.fetchQuery(currentUserStrictQueryOptions())
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        throw redirect({
          to: '/login',
          search: { redirect: location.pathname },
        })
      }
      throw error
    }
  },
  component: () => <main><h1>アプリ</h1></main>,
})
```

`frontend/src/routes/login.tsx`:

```tsx
import { useState } from 'react'
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import LoginForm from '@/components/organisms/Auth/LoginForm'
import { ApiError } from '@/lib/apiError'
import { loginWithPassword } from '@/lib/authApi'
import { queryKeys } from '@/lib/queryKeys'

export const Route = createFileRoute('/login')({
  validateSearch: (search: Record<string, unknown>) => {
    const allowList = new Set(['/app'])
    const candidate =
      typeof search.redirect === 'string' ? search.redirect : '/app'
    return {
      redirect: allowList.has(candidate) ? candidate : '/app',
    }
  },
  component: LoginPage,
})

function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { redirect } = Route.useSearch()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const login = useMutation({
    mutationFn: loginWithPassword,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.root })
      await navigate({ to: redirect })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) {
        setErrorMessage('メールアドレスまたはパスワードが正しくありません。')
        return
      }
      if (error instanceof ApiError && error.status === 422) {
        setErrorMessage('入力内容を確認してください。')
        return
      }
      throw error
    },
  })

  return (
    <main>
      <h1>ログイン</h1>
      <LoginForm
        errorMessage={errorMessage}
        isPending={login.isPending}
        onSubmit={login.mutateAsync}
      />
    </main>
  )
}
```

`frontend/src/components/organisms/Auth/LoginForm.tsx`:

```tsx
import { FormEvent, useState } from 'react'

type LoginValues = {
  email: string
  password: string
}

export default function LoginForm({
  errorMessage,
  onSubmit,
  isPending,
}: {
  errorMessage: string | null
  onSubmit: (values: LoginValues) => Promise<void>
  isPending: boolean
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    await onSubmit({ email, password })
  }

  return (
    <form onSubmit={handleSubmit}>
      <label>
        メールアドレス
        <input required value={email} onChange={(event) => setEmail(event.target.value)} />
      </label>
      <label>
        パスワード
        <input
          required
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      {errorMessage ? <p role="alert">{errorMessage}</p> : null}
      <button disabled={isPending} type="submit">
        ログイン
      </button>
    </form>
  )
}
```

補足:

- phase 1 では `react-hook-form` は入れない
- controlled form + HTML `required` + backend validation で開始する

- [x] **Step 3: route / form test を通す**

Run: `cd frontend && npm test -- src/routes/app.test.tsx src/components/organisms/Auth/LoginForm.test.tsx`
Expected: PASS

- [x] **Step 4: build と route type 生成を確認する**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add frontend/src/routes/login.tsx frontend/src/routes/app.tsx frontend/src/routes/app.test.tsx frontend/src/components/organisms/Auth/LoginForm.tsx frontend/src/components/organisms/Auth/LoginForm.test.tsx frontend/src/routeTree.gen.ts
git commit -m "feat(frontend/auth): add protected route and login flow"
```

## Task 4: Header に auth 状態を統合し、logout redirect を入れる

**Files:**
- Modify: `frontend/src/components/organisms/Header/index.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`

- [x] **Step 1: Header の失敗テストを追加する**

```ts
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  RouterProvider,
  createMemoryHistory,
  createRouter,
} from '@tanstack/react-router'

import { routeTree } from '@/routeTree.gen'

test('未ログイン時はログイン導線を表示する', async () => {
  const queryClient = new QueryClient()
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ['/'] }),
    context: { queryClient },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )

  expect(await screen.findByRole('link', { name: 'ログイン' })).toHaveAttribute(
    'href',
    '/login',
  )
})
```

Run: `cd frontend && npm test -- src/components/organisms/Header/index.test.tsx`
Expected: FAIL

- [x] **Step 2: Header で user 表示と logout redirect を扱う**

```tsx
import { Link, useNavigate, useRouterState } from '@tanstack/react-router'

import { useAuthSession } from '@/hooks/useAuthSession'

export default function Header() {
  const navigate = useNavigate()
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const { user, logout } = useAuthSession()
  const isLandingPage = pathname === '/'

  const handleLogout = async () => {
    await logout.mutateAsync()
    await navigate({ to: '/login' })
  }

  return (
    <header className="site-header">
      <div className="landing-shell flex h-[var(--header-height)] items-center justify-between gap-4">
        <Link aria-label="ページ先頭へ移動" className="site-brand" to="/">
          <img alt="" aria-hidden="true" className="size-7" src="/site-mark.svg" />
          <span>python-react-template</span>
        </Link>

        {isLandingPage ? (
          <nav aria-label="ページ内ナビゲーション" className="hidden items-center gap-2 lg:flex">
            {landingNavigation.map((item) => (
              <a className="site-nav-link" href={item.href} key={item.href}>
                {item.label}
              </a>
            ))}
          </nav>
        ) : null}

        {user ? (
          <div className="flex items-center gap-3">
            <span>{user.email}</span>
            <button onClick={handleLogout} type="button">
              ログアウト
            </button>
          </div>
        ) : (
          <Link to="/login">ログイン</Link>
        )}
      </div>
    </header>
  )
}
```

- [x] **Step 3: Header と既存 route test を通す**

Run: `cd frontend && npm test -- src/components/organisms/Header/index.test.tsx src/components/organisms/LandingPage/index.test.tsx`
Expected: PASS

- [x] **Step 4: frontend 品質ゲートを通す**

Run: `cd frontend && npm run check`
Expected: PASS

Run: `cd frontend && npm test`
Expected: PASS

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add frontend/src/components/organisms/Header/index.tsx frontend/src/components/organisms/Header/index.test.tsx
git commit -m "feat(frontend/auth): surface auth state and logout redirect"
```

## Task 5: frontend ガイドを更新する

**Files:**
- Modify: `frontend/AGENTS.md`

- [x] **Step 1: frontend ガイドへ auth 運用を追記する**

```md
- `components/organisms/` は正式な配置先として扱う
- auth を使う route guard は TanStack Router `beforeLoad` を使う
- frontend の API 呼び出しは相対 `/api/...` を正とし、same-origin を前提にする
```

- [x] **Step 2: 文書整合を見直す**

Run: なし
Expected: `20260418-auth-structure.md`, `20260418-auth-delivery-notes.md`, `frontend/AGENTS.md` の auth 記述が矛盾していない。

- [ ] **Step 3: コミットする**

```bash
git add frontend/AGENTS.md documents/plans/20260418-auth-structure.md documents/plans/20260418-auth-delivery-notes.md
git commit -m "docs(frontend/auth): align frontend guide with auth integration"
```
