import { createAppRouter } from './appRouter'

const { router } = createAppRouter()

void router.navigate({
  to: '/{-$locale}/login',
  params: { locale: 'ja' },
  search: { redirect: '/app' },
})
// @ts-expect-error unknown route must stay rejected
void router.navigate({ to: '/typo' })
