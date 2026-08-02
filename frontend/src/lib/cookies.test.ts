// @vitest-environment jsdom

import { afterEach, expect, test } from 'vitest'

import { readCookie } from './cookies'

afterEach(() => {
  document.cookie = 'csrf_token=; Max-Age=0; Path=/'
  document.cookie = 'csrf_token_extra=; Max-Age=0; Path=/'
  document.cookie = 'encoded=; Max-Age=0; Path=/'
})

test('readCookie は存在する cookie を返す', () => {
  document.cookie = 'csrf_token=csrf-123; Path=/'

  expect(readCookie('csrf_token')).toBe('csrf-123')
})

test('readCookie は URL encoded 値を decode する', () => {
  document.cookie = `encoded=${encodeURIComponent('value with spaces')}; Path=/`

  expect(readCookie('encoded')).toBe('value with spaces')
})

test('readCookie は prefix が似ている別 cookie を誤読しない', () => {
  document.cookie = 'csrf_token_extra=wrong; Path=/'
  document.cookie = 'csrf_token=right; Path=/'

  expect(readCookie('csrf_token')).toBe('right')
})

test('readCookie は存在しない cookie では null を返す', () => {
  document.cookie = 'csrf_token_extra=wrong; Path=/'

  expect(readCookie('csrf_token')).toBeNull()
})
