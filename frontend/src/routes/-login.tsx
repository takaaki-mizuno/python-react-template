import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'

import type { LanguageCode } from '@/lib/i18n/languages'
import { Button } from '@/components/atoms/button'
import { Separator } from '@/components/atoms/separator'
import { OidcProviderButton } from '@/components/molecules/OidcProviderButton'
import { AuthFormShell } from '@/components/organisms/Auth/AuthFormShell'
import LoginForm from '@/components/organisms/Auth/LoginForm'
import { toUserMessage } from '@/lib/apiError'
import {
  fetchOidcProviders,
  loginWithPassword,
  startOidcLogin,
} from '@/lib/authApi'
import { queryKeys } from '@/lib/queryKeys'

export function LoginPage({
  locale,
  oidcError,
  redirectHref,
}: {
  locale: LanguageCode
  oidcError?: string
  redirectHref: string
}) {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [errorMessage, setErrorMessage] = useState<string | null>(() =>
    oidcLoginErrorMessage(oidcError, t),
  )
  const providers = useQuery({
    queryKey: queryKeys.auth.oidcProviders,
    queryFn: fetchOidcProviders,
    retry: false,
  })

  const login = useMutation({
    mutationFn: loginWithPassword,
    onSuccess: async (user) => {
      queryClient.setQueryData(queryKeys.auth.me, user)
      await navigate({ href: redirectHref })
    },
    onError: (error) => {
      setErrorMessage(
        toUserMessage(error, {
          code: {
            INVALID_CREDENTIALS: t('feedback.invalidCredentials'),
            LOGIN_RATE_LIMITED: t('feedback.loginRateLimited'),
          },
          status: { 422: t('feedback.checkInput') },
          fallback: t('feedback.loginFailed'),
        }),
      )
    },
  })

  return (
    <AuthFormShell title={t('login.title')}>
      <LoginForm
        errorMessage={errorMessage}
        isPending={login.isPending}
        onSubmit={(values) => {
          setErrorMessage(null)
          login.mutate(values)
        }}
      />
      {providers.data && providers.data.length > 0 ? (
        <div className="grid gap-3">
          <div className="flex items-center gap-3">
            <Separator className="flex-1" />
            <span className="text-xs text-muted-foreground">
              {t('login.divider')}
            </span>
            <Separator className="flex-1" />
          </div>
          {providers.data.map((provider) => (
            <OidcProviderButton
              key={provider.providerId}
              isDisabled={providers.isFetching}
              onClick={() =>
                startOidcLogin(
                  provider.providerId,
                  redirectHref,
                  undefined,
                  locale,
                )
              }
              provider={provider}
            />
          ))}
        </div>
      ) : null}
      <p className="text-sm text-muted-foreground">
        {t('login.registerPrompt')}{' '}
        <Button asChild className="h-auto p-0" variant="link">
          <Link
            params={{ locale }}
            search={{ redirect: redirectHref }}
            to="/{-$locale}/register"
          >
            {t('login.registerLink')}
          </Link>
        </Button>
      </p>
    </AuthFormShell>
  )
}

export function oidcLoginErrorMessage(
  code: string | undefined,
  t: TFunction<'auth'>,
): string | null {
  if (!code) {
    return null
  }
  const messages: Record<string, string> = {
    OIDC_IDENTITY_LINK_REQUIRED: t('oidc.identityLinkRequired'),
    OIDC_IDENTITY_LINK_DISABLED: t('oidc.identityLinkDisabled'),
    OIDC_EMAIL_NOT_VERIFIED: t('oidc.emailNotVerified'),
    OIDC_PROVISIONING_DISABLED: t('oidc.provisioningDisabled'),
    OIDC_AUTHORIZATION_RATE_LIMITED: t('oidc.authorizationRateLimited'),
    OIDC_PROVIDER_UNAVAILABLE: t('oidc.providerUnavailable'),
    OIDC_PROVIDER_METADATA_INVALID: t('oidc.providerMetadataInvalid'),
    OIDC_PROVIDER_ACCESS_DENIED: t('oidc.providerAccessDenied'),
    OIDC_IDENTITY_UNAVAILABLE: t('oidc.identityUnavailable'),
    OIDC_REAUTH_AUTHENTICATION_REQUIRED: t('oidc.reauthAuthenticationRequired'),
  }
  return messages[code] ?? t('oidc.fallback')
}
