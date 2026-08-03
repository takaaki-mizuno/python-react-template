import type { NavigationItem } from './types'

type HeaderNavProps = {
  items: ReadonlyArray<NavigationItem>
  mobile?: boolean
  onNavigate?: () => void
}

export default function HeaderNav({
  items,
  mobile = false,
  onNavigate,
}: HeaderNavProps) {
  if (mobile) {
    return (
      <nav aria-label="モバイルページ内ナビゲーション" className="grid gap-2">
        {items.map((item) => (
          <a
            className="site-mobile-link"
            href={item.href}
            key={item.href}
            onClick={onNavigate}
          >
            <span className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="size-2 shrink-0 rounded-full bg-landing-accent"
              />
              <span>{item.label}</span>
            </span>
          </a>
        ))}
      </nav>
    )
  }

  return (
    <nav
      aria-label="ページ内ナビゲーション"
      className="hidden items-center gap-2 lg:flex"
    >
      {items.map((item) => (
        <a className="site-nav-link" href={item.href} key={item.href}>
          {item.label}
        </a>
      ))}
    </nav>
  )
}
