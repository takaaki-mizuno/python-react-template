// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'

import { AdminUsersPage } from './AdminUsersPage'
import type {
  AdminRole,
  AdminUser,
  AdminUserListItem,
  AdminUserListResponse,
} from '@/lib/adminUsersApi'
import { ApiError } from '@/lib/apiError'
import { queryKeys } from '@/lib/queryKeys'

const api = vi.hoisted(() => ({
  fetchAdminRoles: vi.fn<() => Promise<Array<AdminRole>>>(),
  fetchAdminUsers: vi.fn<() => Promise<AdminUserListResponse>>(),
  createAdminUser: vi.fn(),
  updateAdminUser: vi.fn(),
  deleteAdminUser: vi.fn(),
}))

vi.mock('@/lib/adminUsersApi', () => ({
  fetchAdminRoles: api.fetchAdminRoles,
  fetchAdminUsers: api.fetchAdminUsers,
  createAdminUser: api.createAdminUser,
  updateAdminUser: api.updateAdminUser,
  deleteAdminUser: api.deleteAdminUser,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

test('AdminUsersPage は一覧と empty state を表示する', async () => {
  api.fetchAdminRoles.mockResolvedValue([role()])
  api.fetchAdminUsers.mockResolvedValue({
    items: [user()],
    total: 1,
    offset: 0,
    limit: 20,
  })

  renderPage()

  expect(await screen.findByText('admin@example.com')).toBeTruthy()
  expect(screen.getByText('1-1 / 1')).toBeTruthy()
})

test('AdminUsersPage は create / edit / delete mutation を呼び出す', async () => {
  api.fetchAdminRoles.mockResolvedValue([role()])
  api.fetchAdminUsers.mockResolvedValue({
    items: [user()],
    total: 1,
    offset: 0,
    limit: 20,
  })
  api.createAdminUser.mockResolvedValue(user({ email: 'new@example.com' }))
  api.updateAdminUser.mockResolvedValue(user({ email: 'edited@example.com' }))
  api.deleteAdminUser.mockResolvedValue(undefined)

  renderPage()

  expect(await screen.findByText('admin@example.com')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'ユーザー作成' }))
  fireEvent.change(screen.getByLabelText('メールアドレス'), {
    target: { value: 'new@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password@123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: '作成する' }))
  await waitFor(() => expect(api.createAdminUser).toHaveBeenCalled())

  fireEvent.click(
    screen.getByRole('button', { name: 'admin@example.com を編集' }),
  )
  fireEvent.change(screen.getByLabelText('メールアドレス'), {
    target: { value: 'edited@example.com' },
  })
  fireEvent.click(screen.getByRole('button', { name: '保存する' }))
  await waitFor(() => expect(api.updateAdminUser).toHaveBeenCalled())
  expect(api.updateAdminUser).toHaveBeenCalledWith('user-1', {
    email: 'edited@example.com',
  })

  fireEvent.click(
    screen.getByRole('button', { name: 'admin@example.com を削除' }),
  )
  fireEvent.click(screen.getByRole('button', { name: '削除する' }))
  await waitFor(() =>
    expect(api.deleteAdminUser).toHaveBeenCalledWith('user-1'),
  )
})

test('AdminUsersPage は API error を日本語表示する', async () => {
  api.fetchAdminRoles.mockResolvedValue([role()])
  api.fetchAdminUsers.mockResolvedValue({
    items: [user()],
    total: 1,
    offset: 0,
    limit: 20,
  })
  api.createAdminUser.mockRejectedValue(
    new ApiError(409, {
      error: { code: 'EMAIL_ALREADY_REGISTERED', message: 'duplicate' },
    }),
  )

  renderPage()

  expect(await screen.findByText('admin@example.com')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'ユーザー作成' }))
  fireEvent.change(screen.getByLabelText('メールアドレス'), {
    target: { value: 'admin@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password@123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: '作成する' }))

  const dialog = screen.getByRole('dialog')
  expect((await within(dialog).findByRole('alert')).textContent).toContain(
    'このメールアドレスは既に登録されています。',
  )
})

test('AdminUsersPage は送信中の Escape で作成ダイアログを閉じない', async () => {
  let rejectCreate!: (reason?: unknown) => void
  const createPromise = new Promise<AdminUser>((_, reject) => {
    rejectCreate = reject
  })
  api.fetchAdminRoles.mockResolvedValue([role()])
  api.fetchAdminUsers.mockResolvedValue({
    items: [user()],
    total: 1,
    offset: 0,
    limit: 20,
  })
  api.createAdminUser.mockImplementation(() => createPromise)

  renderPage()

  expect(await screen.findByText('admin@example.com')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'ユーザー作成' }))
  fireEvent.change(screen.getByLabelText('メールアドレス'), {
    target: { value: 'admin@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password@123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: '作成する' }))
  await waitFor(() => expect(api.createAdminUser).toHaveBeenCalled())

  fireEvent.keyDown(document, { key: 'Escape' })

  expect(screen.getByRole('dialog')).toBeTruthy()
  rejectCreate(
    new ApiError(409, {
      error: { code: 'EMAIL_ALREADY_REGISTERED', message: 'duplicate' },
    }),
  )
  expect(
    (await within(screen.getByRole('dialog')).findByRole('alert')).textContent,
  ).toContain('このメールアドレスは既に登録されています。')
})

test('AdminUsersPage は Escape で作成ダイアログを閉じる', async () => {
  api.fetchAdminRoles.mockResolvedValue([role()])
  api.fetchAdminUsers.mockResolvedValue({
    items: [user()],
    total: 1,
    offset: 0,
    limit: 20,
  })

  renderPage()

  expect(await screen.findByText('admin@example.com')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'ユーザー作成' }))
  expect(screen.getByRole('dialog')).toBeTruthy()

  fireEvent.keyDown(document, { key: 'Escape' })

  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
})

test('AdminUsersPage は mutation 成功後に admin users と auth cache を invalidate する', async () => {
  const queryClient = createTestQueryClient()
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
  api.fetchAdminRoles.mockResolvedValue([role()])
  api.fetchAdminUsers.mockResolvedValue({
    items: [user()],
    total: 1,
    offset: 0,
    limit: 20,
  })
  api.createAdminUser.mockResolvedValue(user({ email: 'new@example.com' }))

  renderPage(queryClient)

  expect(await screen.findByText('admin@example.com')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'ユーザー作成' }))
  fireEvent.change(screen.getByLabelText('メールアドレス'), {
    target: { value: 'new@example.com' },
  })
  fireEvent.change(screen.getByLabelText('パスワード'), {
    target: { value: 'Password@123!' },
  })
  fireEvent.click(screen.getByRole('button', { name: '作成する' }))

  await waitFor(() => {
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: queryKeys.adminUsers.root,
    })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: queryKeys.auth.me })
  })
})

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderPage(queryClient = createTestQueryClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <AdminUsersPage
        filters={{ offset: 0 }}
        onFiltersChange={() => undefined}
      />
    </QueryClientProvider>,
  )
}

function role(): AdminRole {
  return {
    code: 'admin',
    displayName: 'Admin',
    description: null,
    permissions: ['admin:access'],
  }
}

function user(overrides: Partial<AdminUserListItem> = {}): AdminUserListItem {
  return {
    id: 'user-1',
    email: 'admin@example.com',
    isActive: true,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-02T00:00:00Z',
    lastLoginAt: null,
    roles: ['admin'],
    ...overrides,
  }
}
