import { Navigate, Route, Routes } from 'react-router-dom'
import Shell from './components/Shell'
import PageStub from './pages/PageStub'
import OverviewPage from './pages/OverviewPage'
import GameExplorerPage from './pages/GameExplorerPage'
import GameDetailPage from './pages/GameDetailPage'
import TrainingPage from './pages/TrainingPage'
import OpeningsPage from './pages/OpeningsPage'
import InsightsPage from './pages/InsightsPage'
import MatchupsPage from './pages/MatchupsPage'
import PatternsPage from './pages/PatternsPage'
import AnalysisJobsPage from './pages/AnalysisJobsPage'
import TacticalHighlightsPage from './pages/TacticalHighlightsPage'
import GameEndingsPage from './pages/GameEndingsPage'
import EvolutionPage from './pages/EvolutionPage'
import PointsPage from './pages/PointsPage'
import BatchImpactPage from './pages/BatchImpactPage'
import OpeningTreePage from './pages/OpeningTreePage'
import OpponentPrepPage from './pages/OpponentPrepPage'
import AskPage from './pages/AskPage'
import SettingsShell from './pages/settings/SettingsShell'
import AccountDataSettingsPage from './pages/settings/AccountDataSettingsPage'
import AnalysisEngineSettingsPage from './pages/settings/AnalysisEngineSettingsPage'
import AnalyticsDisplaySettingsPage from './pages/settings/AnalyticsDisplaySettingsPage'
import IngestionSettingsPage from './pages/settings/IngestionSettingsPage'
import AdvancedSettingsPage from './pages/settings/AdvancedSettingsPage'
import ApiKeySettingsPage from './pages/settings/ApiKeySettingsPage'
import ProSettingsPage from './pages/settings/ProSettingsPage'
import SupportSettingsPage from './pages/settings/SupportSettingsPage'
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

// Lookup table, not a growing ternary chain -- Overview was the only
// real page for a while, but Game Explorer is the second, and slices
// 3-5 of the port-view-slice roadmap will each add one more here.
const PAGE_COMPONENTS: Partial<Record<string, () => JSX.Element>> = {
  overview: OverviewPage,
  'game-explorer': GameExplorerPage,
  training: TrainingPage,
  openings: OpeningsPage,
  insights: InsightsPage,
  matchups: MatchupsPage,
  patterns: PatternsPage,
  'analysis-jobs': AnalysisJobsPage,
  'tactical-highlights': TacticalHighlightsPage,
  'game-endings': GameEndingsPage,
  evolution: EvolutionPage,
  points: PointsPage,
  'batch-impact': BatchImpactPage,
  'opening-tree': OpeningTreePage,
  'opponent-prep': OpponentPrepPage,
  ask: AskPage,
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        {pages
          .filter((page) => page.url_path !== 'settings')
          .map((page) => {
            const Component = PAGE_COMPONENTS[page.url_path]
            return (
              <Route
                key={page.url_path}
                path={page.url_path}
                element={Component ? <Component /> : <PageStub title={page.title} />}
              />
            )
          })}
        <Route path="settings" element={<SettingsShell />}>
          <Route index element={<Navigate to="account-data" replace />} />
          <Route path="account-data" element={<AccountDataSettingsPage />} />
          <Route path="analysis-engine" element={<AnalysisEngineSettingsPage />} />
          <Route path="analytics-display" element={<AnalyticsDisplaySettingsPage />} />
          <Route path="ingestion" element={<IngestionSettingsPage />} />
          <Route path="advanced" element={<AdvancedSettingsPage />} />
          <Route path="api-key" element={<ApiKeySettingsPage />} />
          <Route path="pro" element={<ProSettingsPage />} />
          <Route path="support" element={<SupportSettingsPage />} />
        </Route>
        {/* Hidden -- reached only via drill-down, not the sidebar/command
            palette, mirroring Streamlit's st.Page(..., visibility="hidden"). */}
        <Route path="game-explorer/:gameId" element={<GameDetailPage />} />
        <Route path="matchups/:gameId" element={<GameDetailPage />} />
        <Route path="tactical-highlights/:gameId" element={<GameDetailPage />} />
        <Route path="game-endings/:gameId" element={<GameDetailPage />} />
        <Route path="points/:gameId" element={<GameDetailPage />} />
        <Route path="batch-impact/:gameId" element={<GameDetailPage />} />
      </Route>
    </Routes>
  )
}
