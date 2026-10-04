import { NavLink, Outlet } from 'react-router'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { PwaStatus } from '../pwa/PwaStatus'

const NAV = [
  { to: '/', label: 'Explore', end: true },
  { to: '/trips', label: 'My trips', end: false },
]

export function AppShell() {
  const online = useOnlineStatus()

  return (
    <div className="mx-auto flex min-h-dvh max-w-2xl flex-col">
      <header className="sticky top-0 z-10 border-b border-stone-200 bg-stone-50/95 px-4 pt-[env(safe-area-inset-top)] backdrop-blur">
        <div className="flex h-14 items-center justify-between gap-3">
          <span className="font-semibold text-green-900">Offline Trip Advisor</span>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
              online ? 'bg-green-100 text-green-900' : 'bg-amber-100 text-amber-900'
            }`}
          >
            <span
              aria-hidden
              className={`size-2 rounded-full ${online ? 'bg-green-600' : 'bg-amber-500'}`}
            />
            {online ? 'Online' : 'Offline'}
          </span>
        </div>
      </header>

      <main className="flex-1 px-4 pt-6 pb-24">
        <Outlet />
      </main>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-10 border-t border-stone-200 bg-white pb-[env(safe-area-inset-bottom)]"
      >
        <ul className="mx-auto flex max-w-2xl">
          {NAV.map((item) => (
            <li key={item.to} className="flex-1">
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex h-14 items-center justify-center text-sm font-medium ${
                    isActive ? 'text-green-800' : 'text-stone-500'
                  }`
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <PwaStatus />
    </div>
  )
}
