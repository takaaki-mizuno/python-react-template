import type { OidcProvider } from '@/lib/authApi'

type OidcProviderButtonProps = {
  isDisabled?: boolean
  onClick: () => void
  provider: OidcProvider
}

export function OidcProviderButton({
  isDisabled = false,
  onClick,
  provider,
}: OidcProviderButtonProps) {
  return (
    <button
      className="inline-flex h-11 w-full items-center justify-center rounded-md border border-landing-line bg-white px-4 text-sm font-medium text-landing-ink transition hover:bg-landing-soft disabled:cursor-not-allowed disabled:opacity-60"
      disabled={isDisabled}
      onClick={onClick}
      type="button"
    >
      {provider.displayName}で続行
    </button>
  )
}
