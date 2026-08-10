import type { NavigationItem } from './types'
import { Button } from '@/components/atoms/button'
import {
  NavigationMenu,
  NavigationMenuItem,
  NavigationMenuLink,
  NavigationMenuList,
} from '@/components/atoms/navigation-menu'

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
          <Button
            asChild
            className="justify-start"
            key={item.href}
            variant="ghost"
          >
            <a href={item.href} onClick={onNavigate}>
              {item.label}
            </a>
          </Button>
        ))}
      </nav>
    )
  }

  return (
    <NavigationMenu
      aria-label="ページ内ナビゲーション"
      className="hidden lg:flex"
      viewport={false}
    >
      <NavigationMenuList>
        {items.map((item) => (
          <NavigationMenuItem key={item.href}>
            <NavigationMenuLink href={item.href}>
              {item.label}
            </NavigationMenuLink>
          </NavigationMenuItem>
        ))}
      </NavigationMenuList>
    </NavigationMenu>
  )
}
