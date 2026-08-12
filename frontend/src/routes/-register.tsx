import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import type { LanguageCode } from '@/lib/i18n/languages'
import { Button } from '@/components/atoms/button'
import { Separator } from '@/components/atoms/separator'
import { OidcProviderButton } from '@/components/molecules/OidcProviderButton'
import { AuthFormShell } from '@/components/organisms/Auth/AuthFormShell'
import RegisterForm from '@/components/organisms/Auth/RegisterForm'
import { toUserMessage } from '@/lib/apiError'
import {
  fetchOidcProviders,
  registerWithPassword,
  startOidcLogin,
} from '@/lib/authApi'
import { queryKeys } from '@/lib/queryKeys'

export function RegisterPage({
  locale,
  redirectHref,
}: {
  locale: LanguageCode
  redirectHref: string
}) {
  const { t } = useTranslation('auth')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const providers = useQuery({
    queryKey: queryKeys.auth.oidcProviders,
    queryFn: fetchOidcProviders,
    retry: false,
  })

  const register = useMutation({
    mutationFn: registerWithPassword,
    onSuccess: async (user) => {
      queryClient.setQueryData(queryKeys.auth.me, user)
      await navigate({ href: redirectHref })
    },
    onError: (error) => {
      setErrorMessage(
        toUserMessage(error, {
          code: {
            EMAIL_ALREADY_REGISTERED: t('feedback.emailAlreadyRegistered'),
            REGISTER_RATE_LIMITED: t('feedback.registerRateLimited'),
            WEAK_PASSWORD: t('feedback.weakPassword'),
          },
          status: { 422: t('feedback.checkInput') },
          fallback: t('feedback.registerFailed'),
        }),
      )
    },
  })

  return (
    <AuthFormShell title={t('register.title')}>
      <RegisterForm
        errorMessage={errorMessage}
        isPending={register.isPending}
        onSubmit={(values) => {
          setErrorMessage(null)
          register.mutate({ ...values, languageCode: locale })
        }}
      />
      {providers.data && providers.data.length > 0 ? (
        <div className="grid gap-3">
          <div className="flex items-center gap-3">
            <Separator className="flex-1" />
            <span className="text-xs text-muted-foreground">
              {t('register.divider')}
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
        {t('register.loginPrompt')}{' '}
        <Button asChild className="h-auto p-0" variant="link">
          <Link
            params={{ locale }}
            search={{ redirect: redirectHref }}
            to="/{-$locale}/login"
          >
            {t('register.loginLink')}
          </Link>
        </Button>
      </p>
    </AuthFormShell>
  )
}
