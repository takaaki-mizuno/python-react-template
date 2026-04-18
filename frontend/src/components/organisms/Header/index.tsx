import { useEffect, useState } from 'react'
import { Menu, X } from 'lucide-react'

import { landingNavigation } from '@/routes/index.data'

export default function Header() {
  const [isOpen, setIsOpen] = useState(false)
  const menuId = 'site-menu'

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
          <a aria-label="ページ先頭へ移動" className="site-brand" href="#top">
            <img
              alt=""
              aria-hidden="true"
              className="size-7"
              src="/site-mark.svg"
            />
            <span>python-react-template</span>
          </a>

          <nav
            aria-label="ページ内ナビゲーション"
            className="hidden items-center gap-2 lg:flex"
          >
            {landingNavigation.map((item) => (
              <a className="site-nav-link" href={item.href} key={item.href}>
                {item.label}
              </a>
            ))}
          </nav>

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
        </div>
      </header>

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

          <nav
            aria-label="モバイルページ内ナビゲーション"
            className="grid gap-2"
          >
            {landingNavigation.map((item) => (
              <a
                className="site-mobile-link"
                href={item.href}
                key={item.href}
                onClick={() => setIsOpen(false)}
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
        </div>
      </aside>
    </>
  )
}
