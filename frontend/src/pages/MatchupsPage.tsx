import { Tabs, TabsList, TabsPanel, TabsTab } from '../components/ui/tabs'
import RatingFormTab from '../components/RatingFormTab'
import NamedOpponentsTab from '../components/NamedOpponentsTab'

export default function MatchupsPage() {
  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Matchups & Opponents</h1>
      <Tabs defaultValue="rating-form" className="mt-4">
        <TabsList>
          <TabsTab value="rating-form">Rating & Form</TabsTab>
          <TabsTab value="named-opponents">Named Opponents</TabsTab>
        </TabsList>
        <TabsPanel value="rating-form"><RatingFormTab /></TabsPanel>
        <TabsPanel value="named-opponents"><NamedOpponentsTab /></TabsPanel>
      </Tabs>
    </div>
  )
}
