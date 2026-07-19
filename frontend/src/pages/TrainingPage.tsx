import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsList, TabsPanel, TabsTab } from '../components/ui/tabs'
import WeaknessesTab from '../components/training/WeaknessesTab'
import BuildSetTab from '../components/training/BuildSetTab'
import ReviewTab from '../components/training/ReviewTab'

const VALID_TABS = new Set(['weaknesses', 'build', 'review'])

export default function TrainingPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const rawTab = searchParams.get('tab')
  const activeTab = rawTab && VALID_TABS.has(rawTab) ? rawTab : 'review'

  function handleTabChange(value: string) {
    const next = new URLSearchParams(searchParams)
    next.set('tab', value)
    next.delete('preset')
    setSearchParams(next)
  }

  return (
    <div className="min-h-full p-8">
      <h1 className="font-condensed text-2xl text-[var(--cw-text)]">Training</h1>
      <p className="mt-2 max-w-[70ch] text-xs text-[var(--cw-muted)]">
        Spot a weakness, turn it into a practice set, and drill it with spaced repetition.
      </p>
      <Tabs value={activeTab} onValueChange={(value) => handleTabChange(value as string)} className="mt-4">
        <TabsList>
          <TabsTab value="weaknesses">Weaknesses</TabsTab>
          <TabsTab value="build">Build Set</TabsTab>
          <TabsTab value="review">Review ✦</TabsTab>
        </TabsList>
        <TabsPanel value="weaknesses">
          <WeaknessesTab />
        </TabsPanel>
        <TabsPanel value="build">
          <BuildSetTab />
        </TabsPanel>
        <TabsPanel value="review">
          <ReviewTab />
        </TabsPanel>
      </Tabs>
    </div>
  )
}
