import { createFileRoute } from '@tanstack/react-router'

import { ErrorState } from '@/components/organisms/ErrorState'

const ForbiddenPage = () => {
  return (
    <ErrorState
      message="このページを表示する権限がありません。必要な場合は管理者へ連絡してください。"
      primaryAction={{ label: 'アプリへ戻る', to: '/app' }}
      statusCode="403"
      title="アクセスできません"
    />
  )
}

export const Route = createFileRoute('/forbidden')({
  component: ForbiddenPage,
})
