import { Link, NavLink, Outlet, useLocation } from 'react-router'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { PwaStatus } from '../pwa/PwaStatus'
import { BookmarkIcon, CloudOffIcon, CompassIcon } from './icons'

export const APP_NAME = 'Offline AI Trip Advisor'

const NAV = [
  { to: '/', label: 'Explore', Icon: CompassIcon, match: (p: string) => p === '/' || p.startsWith('/places') },
  { to: '/trips', label: 'My trips', Icon: BookmarkIcon, match: (p: string) => p.startsWith('/trips') },
]

/** The app mark: a granite outcrop and sun, as in public/icon.svg. */
export function BrandMark({ className = 'size-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 512 512" aria-hidden className={className}>
      <rect width="512" height="512" rx="120" fill="var(--color-forest-800)" />
      <path d="M64 384 L200 176 L264 272 L320 208 L448 384 Z" fill="var(--color-sand-50)" />
      <circle cx="368" cy="144" r="40" fill="#e0a43a" />
    </svg>
  )
}

export function AppShell() {
  const online = useOnlineStatus()
  const { pathname } = useLocation()

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col">
      <header className="sticky top-0 z-10 border-b border-stone-200/70 bg-sand-50/90 px-4 pt-[env(safe-area-inset-top)] backdrop-blur-md">
        <div className="flex h-14 items-center justify-between gap-3">
          <Link to="/" className="flex min-w-0 items-center gap-2.5">
            <BrandMark className="size-7 shrink-0" />
            <span className="truncate text-[15px] font-semibold tracking-tight text-forest-900">
              {APP_NAME}
            </span>
          </Link>
          <span
            className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors ${
              online
                ? 'border-forest-200 bg-forest-50 text-forest-800'
                : 'border-amber-300 bg-amber-50 text-amber-900'
            }`}
          >
            {online ? (
              <span aria-hidden className="size-1.5 rounded-full bg-forest-500" />
            ) : (
              <CloudOffIcon className="size-3.5" />
            )}
            {online ? 'Online' : 'Offline'}
          </span>
        </div>
      </header>

      <main className="flex-1 px-4 pt-5 pb-28">
        <Outlet />
      </main>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-10 border-t border-stone-200/80 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md"
      >
        <ul className="mx-auto flex max-w-2xl px-6">
          {NAV.map(({ to, label, Icon, match }) => {
            const active = match(pathname)
            return (
              <li key={to} className="flex-1">
                <NavLink
                  to={to}
                  aria-current={active ? 'page' : undefined}
                  className={`group flex h-16 flex-col items-center justify-center gap-1 text-xs font-medium transition-colors ${
                    active ? 'text-forest-800' : 'text-stone-500 hover:text-stone-800'
                  }`}
                >
                  <span
                    className={`flex h-7 w-14 items-center justify-center rounded-full transition-colors ${
                      active ? 'bg-forest-100' : 'group-hover:bg-stone-100'
                    }`}
                  >
                    <Icon className="size-5" strokeWidth={active ? 2.1 : 1.8} />
                  </span>
                  {label}
                </NavLink>
              </li>
            )
          })}
        </ul>
      </nav>

      <PwaStatus />
    </div>
  )
}
