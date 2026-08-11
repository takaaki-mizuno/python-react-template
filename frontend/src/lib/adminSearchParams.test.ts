import { expect, test } from 'vitest'

import {
  parseAdminUserSearchParams,
  serializeAdminUserSearchParams,
} from './adminSearchParams'

test('admin user search params は invalid offset を 0 に丸める', () => {
  expect(parseAdminUserSearchParams({ offset: '-1' }).offset).toBe(0)
  expect(parseAdminUserSearchParams({ offset: 'abc' }).offset).toBe(0)
})

test('admin user search params は unknown boolean を undefined にする', () => {
  expect(parseAdminUserSearchParams({ isActive: 'unknown' }).isActive).toBe(
    undefined,
  )
  expect(parseAdminUserSearchParams({ isActive: 'true' }).isActive).toBe(true)
  expect(parseAdminUserSearchParams({ isActive: 'false' }).isActive).toBe(false)
})

test('admin user search params は空 search を undefined にする', () => {
  expect(parseAdminUserSearchParams({ search: '   ' }).search).toBe(undefined)
})

test('admin user search params は role と filter を serialize する', () => {
  expect(
    serializeAdminUserSearchParams({
      offset: 20,
      search: 'admin',
      isActive: false,
      role: 'admin',
    }),
  ).toEqual({
    offset: '20',
    search: 'admin',
    isActive: 'false',
    role: 'admin',
  })
})
