import { NavLink } from 'react-router-dom'
import { usePageCandidates } from '../hooks/usePageCandidates'
import { NAV_GROUPS, groupPages } from '../navConfig'

export default function Sidebar() {
  const { candidates } = usePageCandidates()
  const pages = candidates.filter((c) => c.category === 'page')
  const grouped = groupPages(pages)

  return (
    <nav className="w-56 shrink-0 overflow-y-auto border-r border-[var(--cw-line)] bg-[var(--cw-panel)]/40 p-4">
      {NAV_GROUPS.map((group) => (
        <div key={group} className="mb-6">
          <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--cw-muted)]">
            {group}
          </div>
          {grouped[group].map((page) => (
            <NavLink
              key={page.url_path}
              to={`/${page.url_path}`}
              className={({ isActive }) =>
                `block rounded border-l-2 px-3 py-1.5 text-sm ${
                  isActive
                    ? 'border-[var(--cw-copper)] bg-[var(--cw-copper)]/10 text-[var(--cw-copper)]'
                    : 'border-transparent text-[var(--cw-text)] hover:bg-[var(--cw-line)]/40'
                }`
              }
            >
              {page.title}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  )
}
