import { createFileRoute } from '@tanstack/react-router'

import LandingPage from '@/components/organisms/LandingPage'

export const Route = createFileRoute('/{-$locale}/')({
  component: LandingPage,
})
