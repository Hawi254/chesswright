import { usePatternsSummary } from '../hooks/usePatternsSummary'
import TendencyCard from './TendencyCard'

export default function TendencyScorecard({ onSelectTab }: { onSelectTab: (tabId: string) => void }) {
  const { cards, loading, error } = usePatternsSummary()
  if (loading || error || !cards || cards.length === 0) return null

  return (
    <div className="flex gap-3">
      {cards.map((card) => (
        <TendencyCard
          key={card.tab_id}
          label={card.label}
          headline={card.headline}
          detail={card.detail}
          onClick={() => onSelectTab(card.tab_id)}
        />
      ))}
    </div>
  )
}
