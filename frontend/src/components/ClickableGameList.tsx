import { Link } from 'react-router-dom'

export default function ClickableGameList({ gameIds, basePath }: { gameIds: string[]; basePath: string }) {
  if (gameIds.length === 0) return <p className="text-xs text-[var(--cw-muted)]">None.</p>
  return (
    <ul className="mt-2 space-y-1 text-xs">
      {gameIds.map((id) => (
        <li key={id}>
          <Link to={`/${basePath}/${id}`} className="text-[var(--cw-copper)] hover:underline">
            {id}
          </Link>
        </li>
      ))}
    </ul>
  )
}
