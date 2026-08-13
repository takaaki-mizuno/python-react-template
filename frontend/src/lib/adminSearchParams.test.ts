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
  expect(parseAdminUserSearchParams({ is_active: 'unknown' }).is_active).toBe(
    undefined,
  )
  expect(parseAdminUserSearchParams({ is_active: 'true' }).is_active).toBe(true)
  expect(parseAdminUserSearchParams({ is_active: 'false' }).is_active).toBe(
    false,
  )
})

test('admin user search params は空 search を undefined にする', () => {
  expect(parseAdminUserSearchParams({ query: '   ' }).query).toBe(undefined)
})

test('admin user search params は role と filter を serialize する', () => {
  expect(
    serializeAdminUserSearchParams({
      offset: 20,
      query: 'admin',
      is_active: false,
      role: 'admin',
    }),
  ).toEqual({
    offset: '20',
    query: 'admin',
    is_active: 'false',
    role: 'admin',
  })
})
