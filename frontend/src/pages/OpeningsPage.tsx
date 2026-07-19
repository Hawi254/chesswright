import { Tabs, TabsList, TabsPanel, TabsTab } from '../components/ui/tabs'
import OpeningsTableSection from '../components/OpeningsTableSection'
import RepeatedPositionsSection from '../components/RepeatedPositionsSection'
import RepertoireHolesSection from '../components/RepertoireHolesSection'
import PlyAccuracySection from '../components/PlyAccuracySection'

export default function OpeningsPage() {
  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Openings & Repertoire</h1>
      <Tabs defaultValue="your-openings" className="mt-4">
        <TabsList>
          <TabsTab value="your-openings">Your openings</TabsTab>
          <TabsTab value="repeated-positions">Most-repeated positions</TabsTab>
          <TabsTab value="repertoire-holes">Repertoire holes</TabsTab>
          <TabsTab value="ply-accuracy">Where does accuracy drop</TabsTab>
        </TabsList>
        <TabsPanel value="your-openings"><OpeningsTableSection /></TabsPanel>
        <TabsPanel value="repeated-positions"><RepeatedPositionsSection /></TabsPanel>
        <TabsPanel value="repertoire-holes"><RepertoireHolesSection /></TabsPanel>
        <TabsPanel value="ply-accuracy"><PlyAccuracySection /></TabsPanel>
      </Tabs>
    </div>
  )
}
