import { createFileRoute } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { ErrorState } from '@/components/organisms/ErrorState'

const ForbiddenPage = () => {
  const { t } = useTranslation('common')

  return (
    <ErrorState
      message={t('errors.forbidden.message')}
      primaryAction={{ label: t('actions.backToApp'), to: '/app' }}
      statusCode="403"
      title={t('errors.forbidden.title')}
    />
  )
}

export const Route = createFileRoute('/forbidden')({
  component: ForbiddenPage,
})
