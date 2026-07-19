import { useState } from 'react'
import { Tabs, TabsList, TabsPanel, TabsTab } from '../components/ui/tabs'
import TendencyScorecard from '../components/TendencyScorecard'
import ClockTimeTab from '../components/ClockTimeTab'
import TurningPointsTab from '../components/TurningPointsTab'
import PieceHandlingTab from '../components/PieceHandlingTab'
import PositionsTab from '../components/PositionsTab'
import GameContextTab from '../components/GameContextTab'
import ComparisonsTab from '../components/ComparisonsTab'
import SessionsTab from '../components/SessionsTab'

export default function PatternsPage() {
  const [activeTab, setActiveTab] = useState('clock-time')

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Patterns & Tendencies</h1>
      <div className="mt-4">
        <TendencyScorecard onSelectTab={setActiveTab} />
      </div>
      <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as string)} className="mt-4">
        <TabsList>
          <TabsTab value="clock-time">Clock & Time</TabsTab>
          <TabsTab value="turning-points">Turning Points</TabsTab>
          <TabsTab value="piece-handling">Piece Handling</TabsTab>
          <TabsTab value="positions">Positions</TabsTab>
          <TabsTab value="game-context">Game Context</TabsTab>
          <TabsTab value="comparisons">Comparisons</TabsTab>
          <TabsTab value="sessions">Playing Sessions</TabsTab>
        </TabsList>
        <TabsPanel value="clock-time">
          <ClockTimeTab />
        </TabsPanel>
        <TabsPanel value="turning-points">
          <TurningPointsTab />
        </TabsPanel>
        <TabsPanel value="piece-handling">
          <PieceHandlingTab />
        </TabsPanel>
        <TabsPanel value="positions">
          <PositionsTab />
        </TabsPanel>
        <TabsPanel value="game-context">
          <GameContextTab />
        </TabsPanel>
        <TabsPanel value="comparisons">
          <ComparisonsTab />
        </TabsPanel>
        <TabsPanel value="sessions">
          <SessionsTab />
        </TabsPanel>
      </Tabs>
    </div>
  )
}
