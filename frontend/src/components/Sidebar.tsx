import { NavLink } from 'react-router-dom'
import { usePageCandidates } from '../hooks/usePageCandidates'
import { NAV_GROUPS, groupPages } from '../navConfig'

export default function Sidebar() {
  const { candidates } = usePageCandidates()
  const pages = candidates.filter((c) => c.category === 'page')
  const grouped = groupPages(pages)

  return (
    <nav className="w-56 shrink-0 overflow-y-auto border-r border-bg-secondary bg-bg-secondary/40 p-4">
      {NAV_GROUPS.map((group) => (
        <div key={group} className="mb-6">
          <div className="mb-2 text-xs uppercase tracking-wide text-text-muted">
            {group}
          </div>
          {grouped[group].map((page) => (
            <NavLink
              key={page.url_path}
              to={`/${page.url_path}`}
              className={({ isActive }) =>
                `block rounded px-3 py-1.5 text-sm ${
                  isActive
                    ? 'bg-accent-gold/20 text-accent-gold'
                    : 'text-text hover:bg-bg-secondary'
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
