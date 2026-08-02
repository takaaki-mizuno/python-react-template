import { createAppRouter } from './appRouter'

const { router } = createAppRouter()

void router.navigate({ to: '/login', search: { redirect: '/app' } })
// @ts-expect-error unknown route must stay rejected
void router.navigate({ to: '/typo' })
