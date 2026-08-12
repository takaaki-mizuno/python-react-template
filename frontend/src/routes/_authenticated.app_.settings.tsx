import { useState } from 'react'
import { Link, createFileRoute, useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'

import type { AccountDeletionInvalidField } from '@/components/organisms/Auth/AccountDeletionPanel'
import type { AccountDeletionOidcReauthProvider } from '@/lib/apiError'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/atoms/breadcrumb'
import { AccountDeletionPanel } from '@/components/organisms/Auth/AccountDeletionPanel'
import {
  ApiError,
  accountDeletionOidcReauthProviders,
  toUserMessage,
} from '@/lib/apiError'
import { startOidcReauth } from '@/lib/authApi'
import { useAccountDeletion } from '@/hooks/useAccountDeletion'
import { useAuthSession } from '@/hooks/useAuthSession'
import { detectPreferredPublicLanguage } from '@/lib/i18n/publicLocale'

type AccountDeletionErrorFeedback = {
  message: string
  invalidField: AccountDeletionInvalidField | null
  linkedProviders?: Array<AccountDeletionOidcReauthProvider>
}

const SettingsPage = () => {
  const { t: appT } = useTranslation('app')
  const { t: authT } = useTranslation('auth')
  const navigate = useNavigate()
  const search = Route.useSearch()
  const { user } = useAuthSession()
  const [errorFeedback, setErrorFeedback] =
    useState<AccountDeletionErrorFeedback | null>(null)
  const [dismissedQueryFeedbackKey, setDismissedQueryFeedbackKey] = useState<
    string | null
  >(null)
  const accountDeletion = useAccountDeletion()
  const queryFeedback = accountDeletionQueryFeedback(search, authT)
  const queryFeedbackKey = queryFeedback
    ? `${search.oidcError ?? ''}:${search.oidcReauth ?? ''}`
    : null
  const displayedQueryFeedback =
    queryFeedbackKey === dismissedQueryFeedbackKey ? null : queryFeedback
  const displayedFeedback = errorFeedback ?? displayedQueryFeedback

  if (!user) {
    return null
  }

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="grid gap-8">
        <div className="grid gap-2">
          <Breadcrumb aria-label={appT('settings.breadcrumbLabel')}>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link to="/app">{appT('settings.appLink')}</Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{appT('settings.title')}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <h1 className="text-2xl font-semibold tracking-tight">
            {appT('settings.title')}
          </h1>
        </div>
        <AccountDeletionPanel
          currentEmail={user.email}
          errorMessage={displayedFeedback?.message ?? null}
          invalidField={displayedFeedback?.invalidField ?? null}
          isPending={accountDeletion.isPending}
          linkedProviders={displayedFeedback?.linkedProviders ?? []}
          onFieldChange={(field) => {
            if (queryFeedbackKey) {
              setDismissedQueryFeedbackKey(queryFeedbackKey)
            }
            setErrorFeedback((current) =>
              current?.invalidField === field ? null : current,
            )
          }}
          onReauth={(providerId) => {
            startOidcReauth(providerId, '/app/settings')
          }}
          onSubmit={(payload) => {
            if (queryFeedbackKey) {
              setDismissedQueryFeedbackKey(queryFeedbackKey)
            }
            setErrorFeedback(null)
            accountDeletion.mutate(payload, {
              onSuccess: () => {
                void navigate({
                  params: { locale: detectPreferredPublicLanguage() },
                  to: '/{-$locale}',
                })
              },
              onError: (error) => {
                setErrorFeedback(toAccountDeletionErrorFeedback(error, authT))
              },
            })
          }}
        />
      </div>
    </main>
  )
}

export const Route = createFileRoute('/_authenticated/app_/settings')({
  validateSearch: (
    search: Record<string, unknown>,
  ): { oidcError?: string; oidcReauth?: string } => ({
    ...(typeof search.oidcError === 'string'
      ? { oidcError: search.oidcError }
      : {}),
    ...(typeof search.oidcReauth === 'string'
      ? { oidcReauth: search.oidcReauth }
      : {}),
  }),
  component: SettingsPage,
})

function accountDeletionQueryFeedback(
  search: {
    oidcError?: string
    oidcReauth?: string
  },
  t: TFunction<'auth'>,
): AccountDeletionErrorFeedback | null {
  if (search.oidcReauth === 'success') {
    return {
      message: t('accountDeletion.reauthSuccess'),
      invalidField: null,
    }
  }
  if (!search.oidcError) {
    return null
  }
  const messages: Record<string, string> = {
    OIDC_REAUTH_SUBJECT_MISMATCH: t('accountDeletion.subjectMismatch'),
    OIDC_REAUTH_STALE: t('accountDeletion.reauthStale'),
    OIDC_REAUTH_AUTH_TIME_REQUIRED: t('accountDeletion.authTimeRequired'),
    OIDC_PROVIDER_ACCESS_DENIED: t('accountDeletion.providerAccessDenied'),
    OIDC_PROVIDER_UNAVAILABLE: t('accountDeletion.providerUnavailable'),
    OIDC_IDENTITY_UNAVAILABLE: t('accountDeletion.identityUnavailable'),
  }
  return {
    message: messages[search.oidcError] ?? t('accountDeletion.reauthFailed'),
    invalidField: null,
  }
}

function toAccountDeletionErrorFeedback(
  error: unknown,
  t: TFunction<'auth'>,
): AccountDeletionErrorFeedback {
  const validationField = accountDeletionValidationField(error)
  if (validationField) {
    return {
      message:
        validationField === 'confirmEmail'
          ? t('accountDeletion.emailRequired')
          : t('accountDeletion.passwordRequired'),
      invalidField: validationField,
    }
  }

  const retryAfterMessage = accountDeletionRetryAfterMessage(error, t)
  if (retryAfterMessage) {
    return {
      message: retryAfterMessage,
      invalidField: null,
    }
  }

  return {
    message: toUserMessage(error, {
      code: {
        ACCOUNT_DELETION_CONFIRMATION_MISMATCH: t(
          'accountDeletion.emailMismatch',
        ),
        ACCOUNT_DELETION_REAUTH_REQUIRED: t(
          'accountDeletion.passwordReauthRequired',
        ),
        ACCOUNT_DELETION_INVALID_PASSWORD: t('accountDeletion.invalidPassword'),
        ACCOUNT_DELETION_REAUTH_RATE_LIMITED: t('accountDeletion.rateLimited'),
        ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED:
          accountDeletionOidcReauthProviders(error).length > 0
            ? t('accountDeletion.oidcReauthRequired')
            : t('accountDeletion.noReauthProvider'),
      },
      status: { 422: t('feedback.checkInput') },
      fallback: t('accountDeletion.deleteFailed'),
    }),
    invalidField: accountDeletionInvalidField(error),
    linkedProviders: accountDeletionOidcReauthProviders(error),
  }
}

function accountDeletionRetryAfterMessage(
  error: unknown,
  t: TFunction<'auth'>,
): string | null {
  if (
    !(error instanceof ApiError) ||
    error.status !== 429 ||
    error.code !== 'ACCOUNT_DELETION_REAUTH_RATE_LIMITED' ||
    error.retryAfterSeconds === null
  ) {
    return null
  }

  return t('accountDeletion.retryAfter', {
    duration: formatRetryAfter(error.retryAfterSeconds, t),
  })
}

function formatRetryAfter(seconds: number, t: TFunction<'auth'>): string {
  if (seconds < 60) {
    return t('accountDeletion.durationSeconds', { count: seconds })
  }

  const minutes = Math.ceil(seconds / 60)
  if (minutes < 60) {
    return t('accountDeletion.durationMinutes', { count: minutes })
  }

  return t('accountDeletion.durationHours', { count: Math.ceil(minutes / 60) })
}

function accountDeletionValidationField(
  error: unknown,
): AccountDeletionInvalidField | null {
  if (!(error instanceof ApiError) || error.status !== 422) {
    return null
  }
  for (const detail of error.details) {
    const field = validationDetailField(detail)
    if (field === 'confirmEmail' || field === 'password') {
      return field
    }
  }
  return null
}

function validationDetailField(detail: unknown): string | null {
  if (typeof detail !== 'object' || detail === null || Array.isArray(detail)) {
    return null
  }
  const loc = (detail as { loc?: unknown }).loc
  if (!Array.isArray(loc)) {
    return null
  }
  const field = loc.at(-1)
  return typeof field === 'string' ? field : null
}

function accountDeletionInvalidField(
  error: unknown,
): AccountDeletionInvalidField | null {
  if (!(error instanceof ApiError)) {
    return null
  }
  if (error.code === 'ACCOUNT_DELETION_CONFIRMATION_MISMATCH') {
    return 'confirmEmail'
  }
  if (
    error.code === 'ACCOUNT_DELETION_REAUTH_REQUIRED' ||
    error.code === 'ACCOUNT_DELETION_INVALID_PASSWORD'
  ) {
    return 'password'
  }
  return null
}
