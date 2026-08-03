import { useEffect, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { Menu, X } from 'lucide-react'

import AuthMenu from './AuthMenu'
import HeaderNav from './HeaderNav'
import type { NavigationItem } from './types'

export type { NavigationItem } from './types'

type HeaderProps = {
  navigationItems?: ReadonlyArray<NavigationItem>
}

export default function Header({ navigationItems = [] }: HeaderProps) {
  const [isOpen, setIsOpen] = useState(false)
  const menuId = 'site-menu'
  const hasNavigation = navigationItems.length > 0

  useEffect(() => {
    if (!isOpen) {
      return
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  return (
    <>
      <header className="site-header">
        <div className="landing-shell flex h-[var(--header-height)] items-center justify-between gap-4">
          <Link aria-label="ページ先頭へ移動" className="site-brand" to="/">
            <img
              alt=""
              aria-hidden="true"
              className="size-7"
              src="/site-mark.svg"
            />
            <span>python-react-template</span>
          </Link>

          {hasNavigation ? <HeaderNav items={navigationItems} /> : null}

          <div className="flex items-center gap-3">
            <AuthMenu />

            {hasNavigation ? (
              <button
                aria-controls={menuId}
                aria-expanded={isOpen}
                aria-label="メニューを開く"
                className="site-menu-toggle lg:hidden"
                onClick={() => setIsOpen(true)}
                type="button"
              >
                <Menu size={20} />
              </button>
            ) : null}
          </div>
        </div>
      </header>

      {hasNavigation ? (
        <aside
          className="site-mobile-panel lg:hidden"
          hidden={!isOpen}
          id={menuId}
        >
          <div className="landing-shell space-y-6 py-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="landing-eyebrow">セクション</p>
                <h2 className="text-xl font-semibold text-landing-ink">
                  必要な場所へ直接移動
                </h2>
              </div>

              <button
                aria-label="メニューを閉じる"
                className="site-menu-toggle"
                onClick={() => setIsOpen(false)}
                type="button"
              >
                <X size={20} />
              </button>
            </div>

            <HeaderNav
              items={navigationItems}
              mobile
              onNavigate={() => setIsOpen(false)}
            />
          </div>
        </aside>
      ) : null}
    </>
  )
}
