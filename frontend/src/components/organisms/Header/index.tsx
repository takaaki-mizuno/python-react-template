import { Link } from '@tanstack/react-router'
import { Menu, XIcon } from 'lucide-react'
import { useState } from 'react'

import AuthMenu from './AuthMenu'
import HeaderNav from './HeaderNav'
import type { NavigationItem } from './types'
import { Button } from '@/components/atoms/button'
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/atoms/sheet'

export type { NavigationItem } from './types'

type HeaderProps = {
  navigationItems?: ReadonlyArray<NavigationItem>
}

export default function Header({ navigationItems = [] }: HeaderProps) {
  const [isOpen, setIsOpen] = useState(false)
  const hasNavigation = navigationItems.length > 0

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75">
      <div className="mx-auto flex h-[var(--app-header-height)] w-full max-w-6xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link
          aria-label="ページ先頭へ移動"
          className="flex min-h-11 items-center gap-2 font-semibold tracking-tight"
          to="/"
        >
          <img
            alt=""
            aria-hidden="true"
            className="size-7"
            src="/site-mark.svg"
          />
          <span>python-react-template</span>
        </Link>

        {hasNavigation ? <HeaderNav items={navigationItems} /> : null}

        <div className="flex items-center gap-2">
          <AuthMenu />

          {hasNavigation ? (
            <Sheet open={isOpen} onOpenChange={setIsOpen}>
              <SheetTrigger asChild>
                <Button
                  aria-label="メニューを開く"
                  className="lg:hidden"
                  size="icon"
                  type="button"
                  variant="outline"
                >
                  <Menu className="size-5" aria-hidden="true" />
                </Button>
              </SheetTrigger>
              <SheetContent showCloseButton={false} side="right">
                <SheetHeader>
                  <SheetTitle>セクション</SheetTitle>
                </SheetHeader>
                <div className="mt-6 px-4">
                  <HeaderNav
                    items={navigationItems}
                    mobile
                    onNavigate={() => setIsOpen(false)}
                  />
                </div>
                <SheetClose asChild>
                  <Button
                    aria-label="メニューを閉じる"
                    className="absolute top-4 right-4"
                    size="icon"
                    type="button"
                    variant="ghost"
                  >
                    <XIcon className="size-4" aria-hidden="true" />
                  </Button>
                </SheetClose>
              </SheetContent>
            </Sheet>
          ) : null}
        </div>
      </div>
    </header>
  )
}
