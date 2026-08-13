// @vitest-environment jsdom

import { describe, expect, test } from 'vitest'

import {
  ApiError,
  accountDeletionOidcReauthProviders,
  toUserMessage,
} from './apiError'

describe('ApiError', () => {
  test('Problem Details から code/detail/errors を取得できる', () => {
    const error = new ApiError(422, {
      type: '/problems/validation_error',
      title: 'Validation error',
      status: 422,
      detail: 'Request validation failed.',
      instance: '/api/auth/login',
      code: 'validation_error',
      errors: [
        { location: 'body', pointer: '#/email', detail: 'Invalid email' },
      ],
    })

    expect(error.type).toBe('/problems/validation_error')
    expect(error.title).toBe('Validation error')
    expect(error.code).toBe('validation_error')
    expect(error.detail).toBe('Request validation failed.')
    expect(error.instance).toBe('/api/auth/login')
    expect(error.errors).toEqual([
      { location: 'body', pointer: '#/email', detail: 'Invalid email' },
    ])
  })

  test('Problem Details detail を扱える', () => {
    expect(new ApiError(401, { detail: 'Unauthorized' }).detail).toBe(
      'Unauthorized',
    )
    expect(
      new ApiError(500, { message: 'Internal Server Error' }).detail,
    ).toBeNull()
  })

  test('Problem Details errors array を errors として扱える', () => {
    const errors = [
      {
        location: 'body',
        pointer: '#/confirm_email',
        detail: 'Field required',
      },
    ]

    expect(new ApiError(422, { errors }).errors).toEqual(errors)
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

  test('account deletion OIDC reauth provider extension を型安全に取り出す', () => {
    const error = new ApiError(400, {
      type: '/problems/account_deletion_oidc_reauth_required',
      title: 'Account deletion OIDC reauthentication required',
      status: 400,
      detail: 'OIDC reauth required',
      code: 'account_deletion_oidc_reauth_required',
      providers: [
        { provider_id: 'google', display_name: 'Google' },
        { provider_id: 'broken' },
        { providerSubject: 'secret-subject' },
      ],
    })

    expect(accountDeletionOidcReauthProviders(error)).toEqual([
      { provider_id: 'google', display_name: 'Google' },
    ])
  })
})

describe('toUserMessage', () => {
  test('code override を最優先する', () => {
    const error = new ApiError(401, {
      type: '/problems/invalid_credentials',
      title: 'Invalid credentials',
      status: 401,
      detail: 'Unauthorized',
      code: 'invalid_credentials',
    })

    expect(
      toUserMessage(error, {
        code: {
          invalid_credentials:
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

  test('csrf_validation_failed の既定文言を返す', () => {
    expect(
      toUserMessage(
        new ApiError(403, {
          type: '/problems/csrf_validation_failed',
          title: 'CSRF validation failed',
          status: 403,
          detail: 'CSRF validation failed',
          code: 'csrf_validation_failed',
        }),
      ),
    ).toBe(
      'セッションの確認に失敗しました。ページを再読み込みして、もう一度お試しください。',
    )
  })
})
