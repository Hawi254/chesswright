import { useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

const CATEGORIES = [
  { path: 'account-data', title: 'Account & Data' },
  { path: 'analysis-engine', title: 'Analysis Engine' },
  { path: 'analytics-display', title: 'Analytics & Display' },
  { path: 'ingestion', title: 'Ingestion' },
  { path: 'advanced', title: 'Advanced' },
  { path: 'api-key', title: 'Anthropic API key' },
  { path: 'pro', title: 'Chesswright Pro' },
  { path: 'support', title: 'Support' },
]

export default function SettingsShell() {
  const location = useLocation()

  useEffect(() => {
    if (!location.hash) return
    const id = location.hash.slice(1)
    const el = document.getElementById(id)
    if (!el) return
    const ancestorDetails = el.closest('details')
    if (ancestorDetails && !ancestorDetails.open) ancestorDetails.open = true
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('settings-field-highlight')
    const timeout = setTimeout(() => el.classList.remove('settings-field-highlight'), 1600)
    return () => clearTimeout(timeout)
  }, [location.pathname, location.hash])

  return (
    <div className="flex min-h-full" data-testid="settings-shell">
      <nav className="w-[220px] shrink-0 overflow-y-auto border-r border-[var(--cw-line)] p-4">
        {CATEGORIES.map((category) => (
          <NavLink
            key={category.path}
            to={`/settings/${category.path}`}
            className={({ isActive }) =>
              `block rounded border-l-2 px-3 py-1.5 text-sm ${
                isActive
                  ? 'border-[var(--cw-copper)] bg-[var(--cw-copper)]/10 text-[var(--cw-copper)]'
                  : 'border-transparent text-[var(--cw-text)] hover:bg-[var(--cw-line)]/40'
              }`
            }
          >
            {category.title}
          </NavLink>
        ))}
      </nav>
      <div className="flex-1 overflow-y-auto p-8">
        <Outlet />
      </div>
    </div>
  )
}
