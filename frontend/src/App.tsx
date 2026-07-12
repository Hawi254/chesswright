import { Navigate, Route, Routes } from 'react-router-dom'
import Shell from './components/Shell'
import PageStub from './pages/PageStub'
import OverviewPage from './pages/OverviewPage'
import { STATIC_CANDIDATES } from './lib/navCandidates'

// Routes are generated from the static candidate list, not a live API
// fetch: React Router needs every valid path to exist synchronously at
// app start, before any fetch could resolve. usePageCandidates' live
// result only affects what the Sidebar/CommandPalette *display* -- if
// dashboard/app.py adds a page the live API would report but this
// static list hasn't been updated for, that page's route won't exist
// here until the next frontend build. Same accepted drift risk as
// navConfig.ts's group bucketing.
const pages = STATIC_CANDIDATES.filter((c) => c.category === 'page')

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        {pages.map((page) => (
          <Route
            key={page.url_path}
            path={page.url_path}
            element={
              page.url_path === 'overview' ? <OverviewPage /> : <PageStub title={page.title} />
            }
          />
        ))}
      </Route>
    </Routes>
  )
}
