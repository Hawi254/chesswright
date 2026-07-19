import InsightCard from './InsightCard'
import type { Finding } from '../hooks/useOverviewData'

// Large single-card variant of InsightCard for the top-severity finding --
// matches IdentityZone's radial-gradient copper-accent hero treatment.
export default function HeroInsight({ finding }: { finding: Finding }) {
  return <InsightCard finding={finding} variant="hero" />
}
