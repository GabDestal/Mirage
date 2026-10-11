// Fleet UI (DESIGN.md §1, §2, §6, §11). Opereit-style simplicity and warmth.
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { ArrowRight, Bot, CheckCircle2, ChevronRight, Play, Search, ShieldAlert, ShieldCheck } from 'lucide-react'
import { api, useEvents, useIncidents, useRuns, type Incident, type MirageEvent, type Run } from '@/api/client'
import { resetStream, useConnection, useNow } from '@/api/stream'
import { CleanRestartButton, FreezeButton, ResumeButton, liveRunOwned, runControlNote, useAsk } from '@/components/actions'
import { AgentAvatar } from '@/components/avatar'
import { Button } from '@/components/ui/button'
import { ExposureSummary } from '@/components/exposure-panel'
import { agentName, automaticClearanceText, avatarState, canResume, relTime, rowSentence, runLabel } from '@/lib/runs'
import { isDemo } from '@/lib/demo'
import { agentCount, fleetActivity, fleetStatus, groupByAgent, healthyAgents, latestProductionRuns, sandboxStatus } from './fleet-presentation'
import './fleet.css'

export function Fleet() {
  const { data: runs = [], isPending, isError, error } = useRuns()
  const { data: events = [] } = useEvents()
  const { data: incidents = [] } = useIncidents()
  const now = useNow()
  const connection = useConnection()
  const navigate = useNavigate()
  const ask = useAsk()

  const [filterTab, setFilterTab] = useState<'all' | 'running' | 'frozen'>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [selected, setSelected] = useState(-1)
  const [startingDemo, setStartingDemo] = useState(false)
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  const [view, setView] = useState<'agent' | 'list'>(() => {
    try { return localStorage.getItem('mirage-fleet-view') === 'list' ? 'list' : 'agent' } catch { return 'agent' }
  })
  const chooseView = (next: 'agent' | 'list') => {
    setView(next)
    setSelected(-1)
    try { localStorage.setItem('mirage-fleet-view', next) } catch { /* private mode: keep the choice for this visit */ }
  }

  const filteredRuns = useMemo(() => {
    return runs.filter((r) => {
      if (filterTab === 'running' && r.status !== 'running') return false
      if (filterTab === 'frozen' && r.status !== 'frozen') return false
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const nameMatch = r.agent.toLowerCase().includes(q) || r.id.toLowerCase().includes(q)
        const taskMatch = r.task.toLowerCase().includes(q)
        if (!nameMatch && !taskMatch) return false
      }
      return true
    }).sort((a, b) => b.started_at.localeCompare(a.started_at) || b.id.localeCompare(a.id, undefined, { numeric: true })) // newest first; filter already copied
  }, [runs, filterTab, searchQuery])
  // List view is one headerless group, so rendering and J/K stay shared.
  const groups = useMemo(() => view === 'agent' ? groupByAgent(filteredRuns) : [{ agent: '', runs: filteredRuns }], [view, filteredRuns])
  // J/K and the highlight follow the rows on screen: collapsed groups are skipped.
  const visibleRuns = useMemo(() => groups.flatMap((g) => collapsed.has(g.agent) ? [] : g.runs), [groups, collapsed])
  const toggle = (agent: string) => setCollapsed((prev) => {
    const next = new Set(prev)
    if (!next.delete(agent)) next.add(agent)
    return next
  })

  // Keyboard navigation: J/K move, Enter opens, ⌘U unfreezes, ⌘⌫/⌘X kills (U/X fallbacks).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!visibleRuns.length || e.defaultPrevented || e.altKey || document.querySelector('[role=dialog]')) return
      if (e.target instanceof HTMLElement && (e.target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName))) return
      const command = e.metaKey || e.ctrlKey
      const key = e.key.toLowerCase()
      if (command && (e.shiftKey || !['u', 'x', 'backspace'].includes(key))) return
      const run = visibleRuns[selected]
      if (e.key === 'j') setSelected((i) => Math.min(i + 1, visibleRuns.length - 1))
      else if (e.key === 'k') setSelected((i) => Math.max(i - 1, 0))
      else if (e.key === 'Enter' && run) navigate(`/runs/${run.id}`)
      else if (key === 'u' && run?.status === 'frozen' && (isDemo || liveRunOwned(run, connection))
        && (!incidents.find((i) => i.id === run.incident_id)?.automatic_clearance
          || incidents.find((i) => i.id === run.incident_id)?.automatic_clearance?.status === 'cleared')) {
        e.preventDefault()
        ask('unfreeze', run)
      } else if ((key === 'x' || (command && key === 'backspace')) && run && (isDemo || liveRunOwned(run, connection)) && (run.status === 'running' || run.status === 'frozen')) {
        e.preventDefault()
        ask('kill', run)
      } else if (e.key === 'Escape') setSelected(-1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [visibleRuns, selected, navigate, ask, connection, incidents])

  const stats = useMemo(() => {
    const active = agentCount(runs.filter((r) => r.status === 'running' && (isDemo || liveRunOwned(r, connection))))
    const frozen = runs.filter((r) => r.status === 'frozen').length
    const healthy = healthyAgents(latestProductionRuns(runs).filter((r) => isDemo || r.status !== 'running' || liveRunOwned(r, connection)))
    const toolCalls = runs.reduce((acc, r) => acc + (r.tool_calls || 0), 0)
    return { active, frozen, healthy, toolCalls, total: runs.length }
  }, [runs, connection])

  const handleStartDemo = async () => {
    setStartingDemo(true)
    try {
      await api('/demo/start', {})
      resetStream()
      toast.success(isDemo ? 'Restarted the recorded demo' : 'Started 4-agent demo fleet')
    } catch (e: any) {
      toast.error(e?.message || 'Could not start demo')
    } finally {
      setStartingDemo(false)
    }
  }

  if (isPending) return <Skeleton />
  if (isError) {
    return (
      <div className="fleet-page">
        <div className="fleet-container">
          <div className="fleet-empty">
            <h3>Can't reach the Mirage engine</h3>
            <p>{error.message}</p>
            <Button variant="secondary" onClick={() => location.reload()}>
              Try again
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <section className="fleet-page" aria-label="Agent Fleet">
      <div className="fleet-container">
        {/* Header summary & action */}
        <div className="fleet-header">
          <div className="fleet-title-group">
            <h2>Agent Fleet</h2>
            <p>Real-time protection and transparent observability for autonomous agents.</p>
          </div>
          <div className="fleet-actions">
            <button
              type="button"
              className="fleet-btn fleet-btn-secondary"
              onClick={handleStartDemo}
              disabled={startingDemo}
            >
              <Play size={13} fill="currentColor" />
              {startingDemo ? (isDemo ? 'Redeploying…' : 'Deploying…') : (isDemo ? 'Redeploy Fleet' : 'Deploy Fleet')}
            </button>
            <Button asChild variant="primary">
              <Link to="/">Ask Miragio</Link>
            </Button>
          </div>
        </div>

        {/* Fleet KPI cards */}
        <div className="fleet-stats-grid">
          <div className="fleet-stat-card">
            <div className="fleet-stat-header">
              <span>Active Agents</span>
              <Bot size={15} color="var(--fleet-muted)" />
            </div>
            <div className="fleet-stat-value">{stats.active}</div>
            <div className="fleet-stat-sub">Parallel background workers</div>
          </div>

          <div className="fleet-stat-card">
            <div className="fleet-stat-header">
              <span>Safeguard Freezes</span>
              <ShieldAlert size={15} color={stats.frozen > 0 ? 'var(--fleet-alarm)' : 'var(--fleet-muted)'} />
            </div>
            <div className="fleet-stat-value" style={{ color: stats.frozen > 0 ? 'var(--fleet-alarm)' : 'inherit' }}>
              {stats.frozen}
            </div>
            <div className="fleet-stat-sub">Held before production execution</div>
          </div>

          <div className="fleet-stat-card">
            <div className="fleet-stat-header">
              <span>Healthy Agents</span>
              <CheckCircle2 size={15} color="var(--fleet-emerald)" />
            </div>
            <div className="fleet-stat-value">{stats.healthy}</div>
            <div className="fleet-stat-sub">Working or ready for the next task</div>
          </div>

          <div className="fleet-stat-card">
            <div className="fleet-stat-header">
              <span>Tool Calls Gated</span>
              <ShieldCheck size={15} color="var(--fleet-mirage)" />
            </div>
            <div className="fleet-stat-value" style={{ color: 'var(--fleet-mirage)' }}>
              {stats.toolCalls}
            </div>
            <div className="fleet-stat-sub">Pre-execution policy checks</div>
          </div>
        </div>

        <ExposureSummary />

        {/* Toolbar & Filter Tabs */}
        <div className="fleet-toolbar">
          <div className="fleet-tabs">
            <button
              type="button"
              className={`fleet-tab ${filterTab === 'all' ? 'active' : ''}`}
              onClick={() => setFilterTab('all')}
            >
              All Runs ({runs.length})
            </button>
            <button
              type="button"
              className={`fleet-tab ${filterTab === 'running' ? 'active' : ''}`}
              onClick={() => setFilterTab('running')}
            >
              Working ({stats.active})
            </button>
            <button
              type="button"
              className={`fleet-tab ${filterTab === 'frozen' ? 'active' : ''}`}
              onClick={() => setFilterTab('frozen')}
            >
              Frozen ({stats.frozen})
            </button>
          </div>

          <div className="fleet-toolbar-end">
            <div className="fleet-search-wrap">
              <Search size={14} className="fleet-search-icon" />
              <input
                type="search"
                className="fleet-search-input"
                placeholder="Filter by agent or task…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="fleet-tabs" role="group" aria-label="View">
              <button type="button" className={`fleet-tab ${view === 'agent' ? 'active' : ''}`} aria-pressed={view === 'agent'} onClick={() => chooseView('agent')}>
                By agent
              </button>
              <button type="button" className={`fleet-tab ${view === 'list' ? 'active' : ''}`} aria-pressed={view === 'list'} onClick={() => chooseView('list')}>
                List
              </button>
            </div>
          </div>
        </div>

        {/* Fleet Table Card */}
        <div className="fleet-card">
          {filteredRuns.length === 0 ? (
            <div className="fleet-empty">
              <h3>No agents matching current filter</h3>
              <p>Your fleet will show up in this view as soon as actions begin executing.</p>
              <button type="button" className="fleet-btn fleet-btn-primary" onClick={handleStartDemo}>
                Deploy Fleet
              </button>
            </div>
          ) : (
            <div className="fleet-table-region" role="region" aria-label="Fleet runs" tabIndex={0}>
              <table className="fleet-table">
                <colgroup>
                  <col className="fleet-col-agent" />
                  <col className="fleet-col-status" />
                  <col />
                  <col className="fleet-col-action" />
                  <col className="fleet-col-time" />
                </colgroup>
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Status</th>
                    <th>Activity</th>
                    <th className="fleet-action-cell">Action</th>
                    <th className="fleet-time-cell">Time</th>
                  </tr>
                </thead>
                {groups.map(({ agent, runs: agentRuns }) => {
                  const open = !collapsed.has(agent)
                  return (
                    <tbody key={agent}>
                      {view === 'agent' && <tr className="fleet-group-row">
                        <th colSpan={5} scope="rowgroup">
                          <button type="button" className="fleet-group-toggle" aria-expanded={open} onClick={() => toggle(agent)}>
                            <ChevronRight size={14} className="fleet-group-chevron" aria-hidden="true" />
                            <AgentAvatar agent={agent} state={runControlNote(agentRuns[0], connection) ? 'idle' : avatarState(agentRuns[0])} size={24} />
                            <span className="fleet-group-name">{agentName(agent)}</span>
                            <span className="fleet-group-count">{agentRuns.length} {agentRuns.length === 1 ? 'run' : 'runs'}</span>
                          </button>
                        </th>
                      </tr>}
                      {open && agentRuns.map((run) => (
                        <AgentTableRow
                          key={run.id}
                          run={run}
                          runs={runs}
                          events={events}
                          incident={incidents.find((incident) => incident.id === run.incident_id)}
                          now={now}
                          selected={run === visibleRuns[selected]}
                        />
                      ))}
                    </tbody>
                  )
                })}
              </table>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

function AgentTableRow({
  run,
  runs,
  events,
  incident,
  now,
  selected,
}: {
  run: Run
  runs: Run[]
  events: MirageEvent[]
  incident?: Incident
  now: number
  selected: boolean
}) {
  const navigate = useNavigate()
  const ask = useAsk()
  const label = runLabel(run, runs)
  const connection = useConnection()
  const note = runControlNote(run, connection)
  const sentence = note ?? automaticClearanceText(run, incident) ?? (run.status === 'completed' ? 'Ready for the next task'
    : run.status === 'running' ? run.task
    : run.status === 'frozen' ? 'Held before execution' : run.status === 'queued' ? 'Queued · starting' : rowSentence(run, events).text)
  const when = run.ended_at ?? run.started_at
  const isFrozen = run.status === 'frozen'

  return (
    <tr
      className={`fleet-row ${selected ? 'selected' : ''} ${isFrozen && !note ? 'row-frozen' : ''}`}
      onClick={() => navigate(`/runs/${run.id}`)}
    >
      {/* Agent Avatar & Task */}
      <td>
        <div className="fleet-agent-cell">
          <AgentAvatar agent={run.agent} state={note ? 'idle' : avatarState(run)} size={32} />
          <div className="fleet-agent-info">
            <Link
              to={`/runs/${run.id}`}
              className="fleet-agent-name"
              onClick={(e) => e.stopPropagation()}
            >
              {label}
            </Link>
            <span className="fleet-agent-task" title={sentence || run.task}>
              {sentence || run.task}
            </span>
          </div>
        </div>
      </td>

      {/* Status Pill */}
      <td>
        <span
          className={`fleet-status-pill ${
            isFrozen && !note
              ? 'pill-frozen'
              : run.status === 'running' && !note
              ? 'pill-running'
              : run.status === 'completed'
              ? 'pill-completed'
              : run.status === 'queued'
              ? 'pill-queued'
              : 'pill-killed'
          }`}
        >
          {note ? `Recorded ${run.status}` : fleetStatus(run)}
        </span>
      </td>

      {/* Tool Call Activity Strip */}
      <td>
        <ActivitySummary run={run} events={events} incident={incident} />
        {isFrozen && sandboxStatus(incident, events) && <span className="fleet-replay-status">{sandboxStatus(incident, events)}</span>}
      </td>

      {/* Quick Action Button */}
      <td className="fleet-action-cell">
        <div className="fleet-action-group">
        <FreezeButton run={run} />
        <CleanRestartButton run={run} />
        {isFrozen && run.incident_id ? (
          <Button asChild variant="secondary" onClick={(e) => e.stopPropagation()}>
            <Link to={`/incidents/${run.incident_id}`}>Review Incident</Link>
          </Button>
        ) : isFrozen && liveRunOwned(run, connection) ? (
          <div className="fleet-inline-controls">
            <Button onClick={(e) => { e.stopPropagation(); ask('unfreeze', run) }}>Unfreeze</Button>
            <Button variant="destructive" onClick={(e) => { e.stopPropagation(); ask('kill', run) }}>Kill</Button>
          </div>
        ) : canResume(run, runs) ? (
          <ResumeButton run={run} />
        ) : ['running', 'queued'].includes(run.status) ? null : ( // live runs: the row itself opens the trace
          <Link
            to={`/runs/${run.id}`}
            className="fleet-action-link"
            onClick={(e) => e.stopPropagation()}
          >
            Trace <ArrowRight size={13} />
          </Link>
        )}
        </div>
      </td>

      {/* Relative Time */}
      <td className="fleet-time-cell">
        {relTime(when, now)}
      </td>
    </tr>
  )
}

function ActivitySummary({ run, events, incident }: { run: Run; events: MirageEvent[]; incident?: Incident }) {
  const activity = fleetActivity(run, events, incident)
  return <Link className="fleet-activity-link" to={`/runs/${run.id}`} onClick={(e) => e.stopPropagation()}>
    <span className="fleet-activity-title">{activity.title}</span>
    {activity.results && <span className="fleet-activity-meta">{activity.results}</span>}
    {activity.detail && <span className="fleet-activity-detail">{activity.detail}</span>}
    {activity.blocked && <span className="fleet-activity-blocked">{activity.blocked}</span>}
  </Link>
}

function Skeleton() {
  return (
    <div className="fleet-page">
      <div className="fleet-container">
        <div style={{ height: '32px', width: '200px', background: '#f4f4f5', borderRadius: '8px' }} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
          {[0, 1, 2, 3].map((i) => (
            <div key={i} style={{ height: '80px', background: '#f4f4f5', borderRadius: '12px' }} />
          ))}
        </div>
        <div style={{ height: '240px', background: '#f4f4f5', borderRadius: '14px' }} />
      </div>
    </div>
  )
}
