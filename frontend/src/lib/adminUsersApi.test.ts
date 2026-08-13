// @vitest-environment jsdom

import { afterEach, expect, test, vi } from 'vitest'

import {
  createAdminUser,
  deleteAdminUser,
  fetchAdminRoles,
  fetchAdminUser,
  fetchAdminUsers,
  updateAdminUser,
} from './adminUsersApi'

afterEach(() => {
  vi.unstubAllGlobals()
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
})

test('fetchAdminUsers は query を snake_case で serialize する', async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        data: [],
        count: 0,
        offset: 20,
        limit: 20,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ),
  )
  vi.stubGlobal('fetch', fetchMock)

  await fetchAdminUsers({
    offset: 20,
    limit: 20,
    query: 'admin',
    is_active: false,
    role: 'admin',
  })

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/admin/users?offset=20&limit=20&query=admin&is_active=false&role=admin',
    expect.objectContaining({ credentials: 'include' }),
  )
})

test('admin user unsafe requests は apiClient の CSRF header を使う', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  const fetchMock = vi.fn().mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify(adminUser()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
  vi.stubGlobal('fetch', fetchMock)

  await createAdminUser({
    email: 'admin@example.com',
    password: 'Password@123!',
    is_active: true,
    roles: ['admin'],
  })
  await updateAdminUser('user-1', { roles: ['admin'] })

  const createHeaders = new Headers(fetchMock.mock.calls[0][1]?.headers)
  const updateHeaders = new Headers(fetchMock.mock.calls[1][1]?.headers)
  expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/users')
  expect(fetchMock.mock.calls[1][0]).toBe('/api/admin/users/user-1')
  expect(createHeaders.get('x-csrf-token')).toBe('csrf-123')
  expect(updateHeaders.get('x-csrf-token')).toBe('csrf-123')
})

test('deleteAdminUser は 204 を void として扱う', async () => {
  document.cookie = 'csrf_token=csrf-123; path=/'
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(deleteAdminUser('user-1')).resolves.toBeUndefined()
})

test('fetchAdminUser と fetchAdminRoles は既存 admin API を読む', async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify(adminUser()), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          data: [{ code: 'admin', display_name: 'Admin', permissions: [] }],
          permissions: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
  vi.stubGlobal('fetch', fetchMock)

  await fetchAdminUser('user-1')
  const roles = await fetchAdminRoles()

  expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/users/user-1')
  expect(fetchMock.mock.calls[1][0]).toBe('/api/admin/roles')
  expect(roles).toEqual([
    { code: 'admin', display_name: 'Admin', permissions: [] },
  ])
})

function adminUser() {
  return {
    id: 'user-1',
    email: 'admin@example.com',
    is_active: true,
    created_at: 1767225600,
    updated_at: 1767225600,
    last_login_at: null,
    roles: ['admin'],
    permissions: ['admin:access'],
  }
}
