// Placeholders: another worker builds the run and incident pages.
import { Link, useParams } from 'react-router'
import { useIncidents, useRuns } from '@/api/client'
import { runLabel } from '@/lib/runs'

export function RunPage() {
  const { id } = useParams()
  return <Placeholder>Run <span className="font-mono text-code">{id}</span>. The full trace lands here.</Placeholder>
}

export function IncidentPage() {
  const { id } = useParams()
  return <Placeholder>Incident <span className="font-mono text-code">{id}</span>. The incident story lands here.</Placeholder>
}

export function Incidents() {
  const { data: incidents = [] } = useIncidents()
  const { data: runs = [] } = useRuns()
  if (!incidents.length) return <Placeholder>Nothing to look at. Your agents are behaving.</Placeholder>
  return (
    <ul className="flex max-w-[1080px] flex-col py-2">
      {incidents.map((i) => {
        const run = runs.find((r) => r.id === i.run_id)
        return (
          <li key={i.id}>
            <Link to={`/incidents/${i.id}`} className="flex h-[52px] items-center gap-4 px-6 hover:bg-paper-2">
              <span className="flex-1 truncate font-medium">{run ? runLabel(run, runs) : i.run_id}</span>
              <span className="text-ink-2">{i.trigger.explanation}</span>
              <span className="font-mono text-code text-ink-3">{i.id}</span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}

const Placeholder = ({ children }: { children: React.ReactNode }) => (
  <p className="mx-auto max-w-[880px] px-6 py-24 text-center text-ink-2">{children}</p>
)
