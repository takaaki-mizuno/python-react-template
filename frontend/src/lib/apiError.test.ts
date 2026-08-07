// @vitest-environment jsdom

import { describe, expect, test } from 'vitest'

import {
  ApiError,
  accountDeletionOidcReauthProviders,
  toUserMessage,
} from './apiError'

describe('ApiError', () => {
  test('backend error envelope から code/detail/details を取得できる', () => {
    const error = new ApiError(422, {
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Validation failed',
        details: [{ loc: ['body', 'email'], message: 'Invalid email' }],
      },
    })

    expect(error.code).toBe('VALIDATION_ERROR')
    expect(error.detail).toBe('Validation failed')
    expect(error.details).toEqual([
      { loc: ['body', 'email'], message: 'Invalid email' },
    ])
  })

  test('legacy detail と plain message を扱える', () => {
    expect(new ApiError(401, { detail: 'Unauthorized' }).detail).toBe(
      'Unauthorized',
    )
    expect(new ApiError(500, { message: 'Internal Server Error' }).detail).toBe(
      'Internal Server Error',
    )
  })

  test('legacy FastAPI validation detail array を details として扱える', () => {
    const detail = [{ loc: ['body', 'confirmEmail'], msg: 'Field required' }]

    expect(new ApiError(422, { detail }).details).toEqual(detail)
  })

  test('numeric Retry-After header を retryAfterSeconds として扱える', () => {
    const error = new ApiError(429, null, new Headers({ 'Retry-After': '60' }))

    expect(error.retryAfterSeconds).toBe(60)
  })

  test.each([null, new Headers(), new Headers({ 'Retry-After': 'soon' })])(
    'Retry-After がないか不正な場合は retryAfterSeconds を null にする',
    (headers) => {
      expect(new ApiError(429, null, headers).retryAfterSeconds).toBeNull()
    },
  )

  test('null や JSON object でない body でも throw しない', () => {
    expect(new ApiError(500, null).code).toBeNull()
    expect(new ApiError(500, 'Internal Server Error').detail).toBeNull()
  })

  test('account deletion OIDC reauth provider details を型安全に取り出す', () => {
    const error = new ApiError(400, {
      error: {
        code: 'ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED',
        message: 'OIDC reauth required',
        details: [
          { providerId: 'google', displayName: 'Google' },
          { providerId: 'broken' },
          { providerSubject: 'secret-subject' },
        ],
      },
    })

    expect(accountDeletionOidcReauthProviders(error)).toEqual([
      { providerId: 'google', displayName: 'Google' },
    ])
  })
})

describe('toUserMessage', () => {
  test('code override を最優先する', () => {
    const error = new ApiError(401, {
      error: { code: 'INVALID_CREDENTIALS', message: 'Unauthorized' },
    })

    expect(
      toUserMessage(error, {
        code: {
          INVALID_CREDENTIALS:
            'メールアドレスまたはパスワードが正しくありません。',
        },
        status: { 401: 'ログインしてください。' },
        fallback: 'ログインに失敗しました。',
      }),
    ).toBe('メールアドレスまたはパスワードが正しくありません。')
  })

  test('status override、組み込み status 既定、fallback の順に使う', () => {
    expect(
      toUserMessage(new ApiError(422, { detail: 'Invalid' }), {
        status: { 422: '入力を修正してください。' },
      }),
    ).toBe('入力を修正してください。')

    expect(toUserMessage(new ApiError(401, null))).toBe('ログインが必要です。')
    expect(toUserMessage(new ApiError(409, null))).toBe(
      '現在の状態では処理できません。',
    )

    expect(
      toUserMessage(new Error('Network error'), {
        fallback: '通信できませんでした。',
      }),
    ).toBe('通信できませんでした。')
  })

  test('CSRF_VALIDATION_FAILED の既定文言を返す', () => {
    expect(
      toUserMessage(
        new ApiError(403, {
          error: {
            code: 'CSRF_VALIDATION_FAILED',
            message: 'CSRF validation failed',
          },
        }),
      ),
    ).toBe(
      'セッションの確認に失敗しました。ページを再読み込みして、もう一度お試しください。',
    )
  })
})
