# Auth Frontend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Frontend から `/api/auth/*` を same-origin 前提で扱えるようにし、login / logout / current user の最小 UI を React 側へ統合する。

**Architecture:** Vite dev server では `/api` を backend へ proxy し、本番では相対パスのまま backend 配信へ寄せる。データ取得は React Query に寄せ、unsafe method は `csrf_token` cookie を `X-CSRF-Token` header へ転写する薄い API client に統一する。

**Tech Stack:** React 19, Vite 7, TanStack Router, TanStack Query, TypeScript, Vitest, Testing Library

---

## File Structure

- Create: `frontend/src/lib/apiClient.ts`
- Create: `frontend/src/lib/cookies.ts`
- Create: `frontend/src/lib/queryKeys.ts`
- Create: `frontend/src/hooks/useAuthSession.ts`
- Create: `frontend/src/hooks/useAuthSession.test.tsx`
- Create: `frontend/src/components/organisms/Auth/AuthBootstrap.tsx`
- Create: `frontend/src/components/organisms/Auth/LoginForm.tsx`
- Create: `frontend/src/components/organisms/Auth/LoginForm.test.tsx`
- Create: `frontend/src/lib/apiClient.test.ts`
- Create: `frontend/src/routes/login.tsx`
- Modify: `frontend/src/routes/__root.tsx`
- Modify: `frontend/src/components/organisms/Header/index.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`
- Modify: `frontend/vite.config.ts`

## Task 1: `/api` proxy と共通 API client を作る

**Files:**
- Create: `frontend/src/lib/apiClient.ts`
- Create: `frontend/src/lib/cookies.ts`
- Create: `frontend/src/lib/queryKeys.ts`
- Create: `frontend/src/lib/apiClient.test.ts`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: CSRF header 付与の失敗テストを書く**

```ts
import { afterEach, expect, test, vi } from 'vitest'

import { apiClient } from './apiClient'

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

test('unsafe request に csrf header を付与する', async () => {
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
```

Run: `cd frontend && npm test -- src/lib/apiClient.test.ts`
Expected: FAIL with module not found

- [ ] **Step 2: cookie helper と API client を最小実装する**

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
import { readCookie } from './cookies'

async function request<T>(input: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const method = (init.method ?? 'GET').toUpperCase()

  if (method !== 'GET' && method !== 'HEAD') {
    const csrfToken = readCookie('csrf_token')
    if (csrfToken) {
      headers.set('X-CSRF-Token', csrfToken)
    }
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(input, {
    ...init,
    headers,
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(`${response.status}`)
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

`frontend/src/lib/queryKeys.ts`:

```ts
export const queryKeys = {
  auth: {
    root: ['auth'] as const,
    me: ['auth', 'me'] as const,
  },
}
```

- [ ] **Step 3: Vite proxy を追加する**

```ts
import { loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendOrigin = env.VITE_BACKEND_ORIGIN || 'http://localhost:8000'

  return {
    server: {
      proxy: {
        '/api': {
          target: backendOrigin,
          changeOrigin: true,
        },
      },
    },
  }
})
```

- [ ] **Step 4: API client test を通す**

Run: `cd frontend && npm test -- src/lib/apiClient.test.ts`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add frontend/src/lib/apiClient.ts frontend/src/lib/cookies.ts frontend/src/lib/queryKeys.ts frontend/src/lib/apiClient.test.ts frontend/vite.config.ts
git commit -m "feat(auth): add frontend api client and dev proxy"
```

## Task 2: React Query ベースの auth hook と bootstrap を追加する

**Files:**
- Create: `frontend/src/hooks/useAuthSession.ts`
- Create: `frontend/src/hooks/useAuthSession.test.tsx`
- Create: `frontend/src/components/organisms/Auth/AuthBootstrap.tsx`
- Modify: `frontend/src/routes/__root.tsx`

- [ ] **Step 1: `me` 取得を表現する hook の失敗テストを書く**

```ts
import type { ReactNode } from 'react'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi, expect, test } from 'vitest'

import { useAuthSession } from './useAuthSession'

test('useAuthSession は current user を取得する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'user-1', email: 'user@example.com' }), {
        status: 200,
      }),
    ),
  )

  const queryClient = new QueryClient()
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  const { result } = renderHook(() => useAuthSession(), { wrapper })

  await waitFor(() => expect(result.current.user?.email).toBe('user@example.com'))
})
```

Run: `cd frontend && npm test -- src/hooks/useAuthSession.test.tsx`
Expected: FAIL with file not found

- [ ] **Step 2: hook と bootstrap を最小実装する**

```ts
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'

import { apiClient } from '@/lib/apiClient'
import { queryKeys } from '@/lib/queryKeys'

type AuthUser = { id: string; email: string }

export function useAuthSession() {
  const queryClient = useQueryClient()

  const meQuery = useQuery<AuthUser | null>({
    queryKey: queryKeys.auth.me,
    queryFn: async () => {
      try {
        return await apiClient.get<AuthUser>('/api/auth/me')
      } catch (error) {
        return null
      }
    },
    retry: false,
  })

  const logout = useMutation({
    mutationFn: () => apiClient.post<void>('/api/auth/logout'),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.root })
    },
  })

  return {
    user: meQuery.data ?? null,
    isLoading: meQuery.isLoading,
    logout,
    refetch: meQuery.refetch,
  }
}
```

`AuthBootstrap.tsx`:

```tsx
import { useEffect } from 'react'

import { apiClient } from '@/lib/apiClient'
import { useAuthSession } from '@/hooks/useAuthSession'

export default function AuthBootstrap() {
  const { refetch } = useAuthSession()

  useEffect(() => {
    void apiClient.get<{ csrfToken: string }>('/api/auth/csrf').finally(() => {
      void refetch()
    })
  }, [refetch])

  return null
}
```

`frontend/src/routes/__root.tsx` では先頭で bootstrap を読む。

```tsx
<>
  <AuthBootstrap />
  <Header />
  <Outlet />
  <RouteDevtools />
</>
```

- [ ] **Step 3: hook test を通す**

Run: `cd frontend && npm test -- src/hooks/useAuthSession.test.tsx`
Expected: PASS

- [ ] **Step 4: 既存 route test が壊れていないことを確認する**

Run: `cd frontend && npm test -- src/components/organisms/LandingPage/index.test.tsx`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add frontend/src/hooks/useAuthSession.ts frontend/src/components/organisms/Auth/AuthBootstrap.tsx frontend/src/routes/__root.tsx frontend/src/hooks/useAuthSession.test.tsx
git commit -m "feat(auth): add auth session hook and bootstrap"
```

## Task 3: login route と LoginForm を作る

**Files:**
- Create: `frontend/src/components/organisms/Auth/LoginForm.tsx`
- Create: `frontend/src/components/organisms/Auth/LoginForm.test.tsx`
- Create: `frontend/src/routes/login.tsx`

- [ ] **Step 1: form の失敗テストを書く**

```ts
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'

import LoginForm from './LoginForm'

test('LoginForm は email / password を submit する', async () => {
  const onSubmit = vi.fn().mockResolvedValue(undefined)

  render(<LoginForm onSubmit={onSubmit} isPending={false} />)

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

Run: `cd frontend && npm test -- src/components/organisms/Auth/LoginForm.test.tsx`
Expected: FAIL

- [ ] **Step 2: 最小 UI と route を実装する**

`LoginForm.tsx`:

```tsx
import { FormEvent, useState } from 'react'

type LoginValues = {
  email: string
  password: string
}

export default function LoginForm({
  onSubmit,
  isPending,
}: {
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
        <input value={email} onChange={(event) => setEmail(event.target.value)} />
      </label>
      <label>
        パスワード
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      <button disabled={isPending} type="submit">
        ログイン
      </button>
    </form>
  )
}
```

`frontend/src/routes/login.tsx`:

```tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import LoginForm from '@/components/organisms/Auth/LoginForm'
import { apiClient } from '@/lib/apiClient'
import { queryKeys } from '@/lib/queryKeys'

export const Route = createFileRoute('/login')({
  component: LoginPage,
})

function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const login = useMutation({
    mutationFn: (payload: { email: string; password: string }) =>
      apiClient.post('/api/auth/login', payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.root })
      await navigate({ to: '/' })
    },
  })

  return <LoginForm isPending={login.isPending} onSubmit={login.mutateAsync} />
}
```

- [ ] **Step 3: form test を通す**

Run: `cd frontend && npm test -- src/components/organisms/Auth/LoginForm.test.tsx`
Expected: PASS

- [ ] **Step 4: login route の型生成と build を確認する**

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add frontend/src/components/organisms/Auth/LoginForm.tsx frontend/src/components/organisms/Auth/LoginForm.test.tsx frontend/src/routes/login.tsx frontend/src/routeTree.gen.ts
git commit -m "feat(auth): add login route and form"
```

## Task 4: Header に auth 状態を統合し、回帰テストを通す

**Files:**
- Modify: `frontend/src/components/organisms/Header/index.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`

- [ ] **Step 1: Header の失敗テストを追加する**

```ts
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  RouterProvider,
  createMemoryHistory,
  createRouter,
} from '@tanstack/react-router'

import { routeTree } from '@/routeTree.gen'

test('未ログイン時はログイン導線を表示する', async () => {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: ['/'] }),
    context: {},
  })

  render(
    <QueryClientProvider client={new QueryClient()}>
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

- [ ] **Step 2: pathname と auth state に応じて Header を出し分ける**

```tsx
import { Link, useRouterState } from '@tanstack/react-router'

import { useAuthSession } from '@/hooks/useAuthSession'

export default function Header() {
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  })
  const { user, logout } = useAuthSession()
  const isLandingPage = pathname === '/'

  return (
    <>
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
            <button onClick={() => logout.mutate()} type="button">
              ログアウト
            </button>
          ) : (
            <Link to="/login">ログイン</Link>
          )}
        </div>
      </header>
    </>
  )
}
```

- [ ] **Step 3: Header と既存 landing page test を両方通す**

Run: `cd frontend && npm test -- src/components/organisms/Header/index.test.tsx src/components/organisms/LandingPage/index.test.tsx`
Expected: PASS

- [ ] **Step 4: frontend 品質ゲートを通す**

Run: `cd frontend && npm run check`
Expected: PASS

Run: `cd frontend && npm test`
Expected: PASS

Run: `cd frontend && npm run build`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add frontend/src/components/organisms/Header/index.tsx frontend/src/components/organisms/Header/index.test.tsx
git commit -m "feat(auth): surface auth state in header"
```
